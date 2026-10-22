/** Panel de seguridad (sólo administradores): lo que revisó el vigilante de archivos. */

import { api } from '../core/api.js';
import { $, fileSize, html, longDate, on, setHtml, timeAgo } from '../core/dom.js';
import { store } from '../core/store.js';
import { avatar, empty, loading, scanBadge } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { closeDrawer, confirmDialog, openDrawer, toast } from '../ui/overlay.js';

const TIPO = { public: 'Biblioteca', group: 'Grupo', private: 'Privado', avatar: 'Foto de perfil' };
const FILTROS = [['', 'Todos'], ['review', 'Por revisar'], ['blocked', 'Bloqueados'], ['pending', 'En proceso'], ['clean', 'Limpios']];

function capa(n, titulo, texto, estado, activo) {
    return html`<section class="panel layer"><span class="layer__n">${n}</span><h3>${titulo}</h3><p>${texto}</p>
        <div class="layer__state"><span class="dot ${activo ? '' : 'is-off'}"></span>${estado}</div></section>`;
}

function hallazgos(lista = []) {
    if (!lista.length) return html`<p style="color:var(--ink-3);font-size:14px">Sin hallazgos.</p>`;
    const sev = { block: 'blocked', review: 'review', info: 'pending' };
    const nombre = { block: 'Bloquea', review: 'Revisar', info: 'Info' };
    return html`${lista.map((f) => html`<div class="finding"><span class="status status--${sev[f.severity]}">${nombre[f.severity]}</span><span>${f.message}</span></div>`)}`;
}

function detalle(s) {
    const av = s.antivirus || {};
    const ia = s.ai || {};
    return html`<div class="drawer__head"><div style="flex:1;min-width:0"><h2 style="font-size:19px;word-break:break-all">${s.original_name}</h2>
            <p style="color:var(--ink-3);font-size:14px;margin-top:4px">${TIPO[s.kind]}, ${longDate(s.created_at)}</p></div>
            <button class="icon-btn" data-close aria-label="Cerrar">${icon('x')}</button></div>
        <div class="drawer__body">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${scanBadge(s.status, { onlyIssues: false })}<span style="color:var(--ink-2)">${s.summary || ''}</span></div>
            <dl class="kv">
                <dt>Subido por</dt><dd style="display:flex;gap:8px;align-items:center">${avatar(s.user, 'sm')}${s.user?.name || 'Desconocido'}</dd>
                <dt>Tamaño</dt><dd>${fileSize(s.size)}</dd>
                <dt>Tipo real</dt><dd>${s.detected_type || 'sin analizar'}</dd>
                <dt>SHA-256</dt><dd style="font-family:var(--font-mono);font-size:12px;word-break:break-all">${s.sha256 || ''}</dd>
            </dl>
            <div class="layer-report"><h4><span class="layer__n">1</span>Análisis estático</h4>${hallazgos(s.static?.findings)}</div>
            <div class="layer-report"><h4><span class="layer__n">2</span>Antivirus</h4>
                <p style="font-size:14px">${av.engine ? `${av.engine}: ` : ''}${av.verdict === 'clean' ? 'sin amenazas' : av.verdict === 'infected' ? 'amenaza detectada' : av.verdict === 'skipped' ? 'no hizo falta (bloqueado antes)' : 'no disponible'}${av.detail && av.verdict !== 'clean' ? `. ${av.detail}` : ''}</p></div>
            <div class="layer-report"><h4><span class="layer__n">3</span>Revisión con IA</h4>
                <p style="font-size:14px">${s.ai ? html`<strong>${ia.verdict === 'ok' ? 'Apto' : ia.verdict === 'review' ? 'Dudoso' : ia.verdict === 'block' ? 'No apto' : 'No disponible'}</strong>${ia.model ? ` (${ia.model})` : ''}. ${ia.reason || ''}
                    ${ia.prompt_guard !== undefined ? html`<br><span style="color:var(--ink-3)">Prompt Guard: ${Math.round(ia.prompt_guard * 100)} % de probabilidad de instrucciones ocultas.</span>` : ''}`
                    : s.kind === 'private' ? 'No se aplica a archivos privados.' : 'Todavía no se ejecutó.'}</p></div>
            <div style="display:flex;gap:8px;margin-top:22px;flex-wrap:wrap">
                ${s.status !== 'clean' ? html`<button class="btn btn--primary" data-decide="approve">${icon('check')}Aprobar y publicar</button>` : ''}
                ${s.status !== 'blocked' ? html`<button class="btn btn--danger" data-decide="block">${icon('lock')}Bloquear</button>` : ''}
                <button class="btn btn--secondary" data-decide="rescan">${icon('refresh')}Volver a revisar</button>
            </div>
            <p style="font-size:13px;color:var(--ink-3);margin-top:10px">Bloquear borra el archivo del servidor y veta su huella para que no se pueda volver a subir.</p>
        </div>`;
}

export async function securityView(root, _params, signal) {
    if (!store.user.is_admin) {
        setHtml(root, html`<div class="page">${empty({ icon: 'lock', title: 'Sólo para administradores', text: 'Pide a la coordinación que agregue tu correo a ADMIN_EMAILS.' })}</div>`);
        return;
    }
    let filtro = 'review';
    let escaneos = [];

    setHtml(root, html`<div class="page page--wide">
        <div class="page-head"><div><h1>Seguridad</h1><p>Todo archivo que suben los estudiantes pasa por tres barreras antes de publicarse. Aquí decides sobre lo dudoso.</p></div>
            <div class="page-head__actions"><button class="btn btn--secondary" data-action="refresh">${icon('refresh')}Actualizar</button></div></div>
        <div data-slot="overview">${loading()}</div>
        <div class="chips" style="margin:6px 0 14px" data-slot="filters"></div>
        <section class="panel table-wrap" data-slot="table">${loading()}</section>
    </div>`);

    async function resumen() {
        try {
            const o = await api.get('/api/admin/overview');
            const ia = o.ai || {};
            const sc = o.scans || {};
            setHtml($('[data-slot="overview"]', root), html`<div class="layers">
                ${capa(1, 'Análisis estático', 'Tipo real del archivo, macros, JavaScript en PDF, ejecutables dentro de ZIP, plantillas remotas y zip bombs.', 'Siempre activo', true)}
                ${capa(2, 'Antivirus del sistema', 'Escanea cada archivo con el antivirus del servidor antes de publicarlo.', o.antivirus || 'No disponible en este servidor', !!o.antivirus)}
                ${capa(3, 'Vigilante con IA', 'Un segundo modelo revisa el contenido: phishing, contenido inapropiado, datos personales e instrucciones ocultas para el asistente.',
                    ia.security ? `${ia.security.provider}: ${ia.security.model}` : 'Sin modelo configurado', !!ia.security)}
            </div>
            <div class="stats-line" style="margin:0 0 6px">
                <span><strong>${sc.review || 0}</strong>por revisar</span><span><strong>${sc.blocked || 0}</strong>bloqueados</span>
                <span><strong>${sc.clean || 0}</strong>limpios</span><span><strong>${o.scan_queue}</strong>en cola</span>
                <span><strong>${o.blocked_hashes}</strong>huellas vetadas</span>
                <span><strong>${o.index?.documentos ?? 0}</strong>documentos indexados para el asistente</span>
            </div>`);
            setHtml($('[data-slot="filters"]', root), html`${FILTROS.map(([k, l]) => html`<button class="chip" data-filter="${k}" aria-pressed="${filtro === k}">${l}${k && sc[k] ? html` <span class="chip__n">${sc[k]}</span>` : ''}</button>`)}`);
        } catch (err) {
            setHtml($('[data-slot="overview"]', root), empty({ icon: 'alert', title: 'No se pudo cargar el resumen', text: err.message }));
        }
    }

    async function tabla() {
        try {
            escaneos = (await api.get(`/api/admin/scans?limit=200${filtro ? `&status=${filtro}` : ''}`)).scans;
            setHtml($('[data-slot="table"]', root), escaneos.length ? html`<table class="table"><thead><tr>
                    <th>Archivo</th><th>Dónde</th><th>Subido por</th><th>Resultado</th><th>Motivo</th><th>Fecha</th></tr></thead>
                <tbody>${escaneos.map((s) => html`<tr class="is-clickable" data-scan="${s.id}">
                    <td style="max-width:260px;word-break:break-all;font-weight:600">${s.original_name}<div class="muted">${fileSize(s.size)}</div></td>
                    <td>${TIPO[s.kind]}</td><td>${s.user?.name || ''}</td><td>${scanBadge(s.status, { onlyIssues: false })}</td>
                    <td class="muted" style="max-width:340px">${s.summary || ''}</td><td class="muted">${timeAgo(s.created_at)}</td></tr>`)}</tbody></table>`
                : empty({ icon: 'shield', title: filtro === 'review' ? 'Nada pendiente de revisión' : 'Sin registros', text: 'El vigilante no ha marcado archivos en esta categoría.' }));
        } catch (err) {
            setHtml($('[data-slot="table"]', root), empty({ icon: 'alert', title: 'No se pudo cargar', text: err.message }));
        }
    }

    on(root, 'click', '[data-filter]', (_e, b) => {
        filtro = b.dataset.filter;
        root.querySelectorAll('[data-filter]').forEach((c) => c.setAttribute('aria-pressed', String(c === b)));
        tabla();
    }, signal);
    on(root, 'click', '[data-action="refresh"]', () => { resumen(); tabla(); }, signal);
    on(root, 'click', '[data-scan]', (_e, tr) => {
        const s = escaneos.find((x) => x.id === Number(tr.dataset.scan));
        const drawer = openDrawer(detalle(s));
        drawer.addEventListener('click', async (e) => {
            const b = e.target.closest('[data-decide]');
            if (!b) return;
            try {
                if (b.dataset.decide === 'rescan') {
                    await api.post(`/api/admin/scans/${s.id}/rescan`);
                    toast('Enviado de nuevo al vigilante');
                } else {
                    if (b.dataset.decide === 'block' && !await confirmDialog({ title: 'Bloquear archivo', text: 'Se borrará del servidor y no se podrá volver a subir.', confirmLabel: 'Bloquear' })) return;
                    await api.post(`/api/admin/scans/${s.id}/decision`, { decision: b.dataset.decide });
                    toast(b.dataset.decide === 'approve' ? 'Archivo aprobado y publicado' : 'Archivo bloqueado');
                }
                closeDrawer();
                resumen();
                tabla();
            } catch (err) { toast(err.message, 'error'); }
        });
    }, signal);

    await resumen();
    tabla();
}
