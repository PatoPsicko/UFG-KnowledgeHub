/**
 * Panel de seguridad (sólo administradores).
 *
 * Lo limpio se publica solo: aquí llega lo que el vigilante dejó en cuarentena
 * (dudoso o peligroso), con su motivo, para aprobarlo o rechazarlo uno por uno
 * o en lote. Pestañas:
 *   Archivos         actividad, motivos, registro con búsqueda y la cuarentena
 *   Estudiantes      quién acumula rechazos y la suspensión de subidas
 *   Huellas vetadas  archivos que no se pueden volver a subir
 *   Política e IA    límites de subida, cuota de los modelos y espacio en disco
 *   Bitácora         eventos de seguridad
 * Con ADMIN_REQUIRE_2FA, antes pide la verificación en dos pasos.
 */

import { api } from '../core/api.js';
import { $, debounce, fileSize, html, longDate, on, setHtml, timeAgo } from '../core/dom.js';
import { resolve } from '../core/router.js';
import { store } from '../core/store.js';
import { avatar, empty, loading, meter, scanBadge } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { closeDrawer, confirmDialog, openDialog, openDrawer, toast } from '../ui/overlay.js';
import { openStepUp, openTwoFactorSetup } from '../ui/twofactor.js';

const TIPO = { public: 'Biblioteca', group: 'Grupo', private: 'Mi espacio', avatar: 'Foto de perfil' };
const FILTROS = [['quarantine', 'En cuarentena'], ['', 'Todos'], ['blocked', 'Bloqueados'], ['reviewed', 'Decididos por un admin'],
    ['pending', 'En proceso'], ['clean', 'Limpios']];
const CARPETAS = { library: 'Biblioteca', private: 'Mi espacio', groups: 'Grupos', profile: 'Fotos de perfil', tmp: 'Subidas en curso' };
const MOTIVOS = {
    executable: 'Ejecutable disfrazado', type_mismatch: 'Tipo real distinto a la extensión', pdf_javascript: 'PDF con JavaScript',
    pdf_launch: 'PDF que abre programas', pdf_embedded: 'PDF con archivos incrustados', pdf_active: 'PDF con contenido activo',
    pdf_autoaction: 'PDF que abre enlaces solo', macros: 'Documento con macros', remote_template: 'Plantilla remota (tipo Follina)',
    activex: 'Controles ActiveX', ole_object: 'Objetos OLE incrustados', zip_executable: 'ZIP con ejecutables',
    zip_bomb: 'Zip bomb', zip_traversal: 'ZIP con rutas ../', zip_encrypted: 'ZIP cifrado', bad_zip: 'Comprimido dañado',
    polyglot: 'Imagen con código escondido', appended_zip: 'Imagen con ZIP pegado', double_extension: 'Doble extensión',
    rtf_autoobject: 'RTF con objetos automáticos', rtf_object: 'RTF con objetos', blocked_hash: 'Huella vetada', eicar: 'Prueba EICAR',
    empty: 'Archivo vacío', antivirus: 'Detectado por el antivirus', ia_block: 'IA: contenido no apto', ia_review: 'IA: contenido dudoso',
};
const miles = (n) => (n ?? 0).toLocaleString('es-SV');

/* --- Piezas de la pestaña Archivos ----------------------------------------------- */

function capa(n, titulo, texto, estado, activo) {
    return html`<section class="panel layer"><span class="layer__n">${n}</span><h3>${titulo}</h3><p>${texto}</p>
        <div class="layer__state"><span class="dot ${activo ? '' : 'is-off'}"></span>${estado}</div></section>`;
}

/** Barras apiladas por día: publicados solos, marcados y en proceso. */
function actividad(dias = []) {
    const max = Math.max(1, ...dias.map((d) => d.clean + d.flagged + d.pending));
    const dia = new Intl.DateTimeFormat('es-SV', { day: 'numeric', month: 'short' });
    const total = dias.reduce((a, d) => a + d.clean + d.flagged + d.pending, 0);
    if (!total) return html`<p class="muted" style="font-size:14px">Todavía no se ha subido nada en este periodo.</p>`;
    return html`<div class="activity" role="img" aria-label="Archivos revisados por día">
        ${dias.map((d) => {
            const n = d.clean + d.flagged + d.pending;
            return html`<div class="activity__col" title="${dia.format(new Date(`${d.date}T12:00:00`))}: ${d.clean} publicados, ${d.flagged} marcados, ${d.pending} en proceso">
                <div class="activity__bar" style="height:${Math.round((n / max) * 100)}%">
                    ${d.flagged ? html`<span class="activity__seg activity__seg--flagged" style="flex:${d.flagged}"></span>` : ''}
                    ${d.pending ? html`<span class="activity__seg activity__seg--pending" style="flex:${d.pending}"></span>` : ''}
                    ${d.clean ? html`<span class="activity__seg activity__seg--clean" style="flex:${d.clean}"></span>` : ''}
                </div>
                <span class="activity__label">${new Date(`${d.date}T12:00:00`).getDate()}</span>
            </div>`;
        })}
    </div>
    <div class="activity__legend"><span><i class="activity__seg--clean"></i>Publicados solos</span>
        <span><i class="activity__seg--flagged"></i>Marcados por el vigilante</span><span><i class="activity__seg--pending"></i>En proceso</span></div>`;
}

function motivos(lista = []) {
    if (!lista.length) return html`<p class="muted" style="font-size:14px">Sin archivos marcados en este periodo.</p>`;
    const max = Math.max(...lista.map((m) => m.count));
    return html`<ul class="reasons">${lista.map((m) => html`<li>
        <span class="reasons__name">${MOTIVOS[m.code] || m.code}</span>
        <span class="reasons__bar"><span style="width:${Math.round((m.count / max) * 100)}%"></span></span>
        <strong>${m.count}</strong></li>`)}</ul>`;
}

function hallazgos(lista = []) {
    if (!lista.length) return html`<p style="color:var(--ink-3);font-size:14px">Sin hallazgos.</p>`;
    const sev = { block: 'blocked', review: 'review', info: 'pending' };
    const nombre = { block: 'Bloquea', review: 'Revisar', info: 'Info' };
    return html`${lista.map((f) => html`<div class="finding"><span class="status status--${sev[f.severity]}">${nombre[f.severity]}</span><span>${f.message}</span></div>`)}`;
}

function filaArchivo(s, seleccion, conCasillas) {
    return html`<tr class="is-clickable" data-scan="${s.id}">
        ${conCasillas ? html`<td class="table__check" data-stop><input type="checkbox" data-pick="${s.id}" aria-label="Seleccionar ${s.original_name}" ${seleccion.has(s.id) ? 'checked' : ''}></td>` : ''}
        <td style="max-width:260px;word-break:break-all;font-weight:600">${s.original_name}<div class="muted">${fileSize(s.size)}${s.detected_type ? `, ${s.detected_type}` : ''}</div></td>
        <td>${TIPO[s.kind]}</td>
        <td>${s.user?.name || ''}${s.user?.uploads_blocked ? html`<div><span class="status status--blocked">${icon('lock')}Suspendido</span></div>` : ''}</td>
        <td>${scanBadge(s.status, { onlyIssues: false })}${s.reviewed_by ? html`<div class="muted">por un admin</div>` : ''}</td>
        <td class="muted" style="max-width:340px">${s.summary || ''}</td>
        <td class="muted" title="${longDate(s.created_at)}">${timeAgo(s.created_at)}</td></tr>`;
}

function detalle(s) {
    const av = s.antivirus || {};
    const ia = s.ai || {};
    const u = s.user;
    const decidir = s.awaiting_decision || (s.status !== 'clean' && s.status !== 'blocked') || s.status === 'clean';
    return html`<div class="drawer__head"><div style="flex:1;min-width:0"><h2 style="font-size:19px;word-break:break-all">${s.original_name}</h2>
            <p style="color:var(--ink-3);font-size:14px;margin-top:4px">${TIPO[s.kind]}, ${longDate(s.created_at)}</p></div>
            <button class="icon-btn" data-close aria-label="Cerrar">${icon('x')}</button></div>
        <div class="drawer__body">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${scanBadge(s.status, { onlyIssues: false })}<span style="color:var(--ink-2)">${s.summary || ''}</span></div>
            ${s.admin_note ? html`<p class="note-box">${icon('edit')}<span><strong>Nota del administrador:</strong> ${s.admin_note}</span></p>` : ''}
            ${u ? html`<div class="uploader-card">${avatar(u, 'sm')}<div style="min-width:0;flex:1"><strong>${u.name}</strong>
                    <div class="muted">${u.email || ''}</div></div>
                    <div class="uploader-card__actions">
                        <button class="btn btn--ghost btn--sm" data-uploader-files="${u.email || u.name}">${icon('search')}Sus archivos</button>
                        ${u.uploads_blocked ? html`<button class="btn btn--secondary btn--sm" data-unsuspend="${u.id}">${icon('check')}Reactivar subidas</button>`
                            : html`<button class="btn btn--secondary btn--sm" data-suspend="${u.id}" data-name="${u.name}">${icon('lock')}Suspender subidas</button>`}
                    </div></div>` : ''}
            <dl class="kv">
                <dt>Tamaño</dt><dd>${fileSize(s.size)}</dd>
                <dt>Tipo real</dt><dd>${s.detected_type || 'sin analizar'}</dd>
                <dt>SHA-256</dt><dd style="font-family:var(--font-mono);font-size:12px;word-break:break-all">${s.sha256 || ''}</dd>
                ${s.reviewed_at ? html`<dt>Decidido</dt><dd>${longDate(s.reviewed_at)}</dd>` : ''}
            </dl>
            <div class="layer-report"><h4><span class="layer__n">1</span>Análisis estático</h4>${hallazgos(s.static?.findings)}</div>
            <div class="layer-report"><h4><span class="layer__n">2</span>Antivirus</h4>
                <p style="font-size:14px">${av.engine ? `${av.engine}: ` : ''}${av.verdict === 'clean' ? 'sin amenazas' : av.verdict === 'infected' ? 'amenaza detectada' : av.verdict === 'skipped' ? 'no hizo falta (bloqueado antes)' : 'no disponible'}${av.detail && av.verdict !== 'clean' ? `. ${av.detail}` : ''}</p></div>
            <div class="layer-report"><h4><span class="layer__n">3</span>Revisión con IA</h4>
                <p style="font-size:14px">${s.ai ? html`<strong>${ia.verdict === 'ok' ? 'Apto' : ia.verdict === 'review' ? 'Dudoso' : ia.verdict === 'block' ? 'No apto' : 'No disponible'}</strong>${ia.model ? ` (${ia.model})` : ''}. ${ia.reason || ''}
                    ${ia.prompt_guard !== undefined ? html`<br><span style="color:var(--ink-3)">Prompt Guard: ${Math.round(ia.prompt_guard * 100)} % de probabilidad de instrucciones ocultas.</span>` : ''}`
                    : s.kind === 'private' ? 'No se aplica a archivos privados.' : 'Todavía no se ejecutó.'}</p></div>
            <div class="layer-report"><h4>${icon('eye')}Contenido</h4>
                <div data-slot="preview"><button class="btn btn--secondary btn--sm" data-preview>${icon('file')}Ver el texto del archivo</button>
                <p class="field__hint" style="margin-top:6px">Se muestra el texto extraído, sin abrir el archivo original.</p></div></div>
            ${decidir ? html`<div class="decision">
                <label class="field"><span class="field__label">Nota para el estudiante (opcional)</span>
                    <textarea class="textarea" rows="2" maxlength="500" data-note placeholder="Ej. El documento trae datos personales de otros estudiantes."></textarea></label>
                <div style="display:flex;gap:8px;flex-wrap:wrap">
                    ${s.awaiting_decision || (s.status !== 'clean' && s.status !== 'blocked') ? html`<button class="btn btn--primary" data-decide="approve">${icon('check')}Aprobar y publicar</button>` : ''}
                    ${s.awaiting_decision || s.status === 'clean' ? html`<button class="btn btn--danger" data-decide="reject">${icon('lock')}Rechazar</button>` : ''}
                    <button class="btn btn--secondary" data-decide="rescan">${icon('refresh')}Volver a revisar</button>
                </div>
                <p class="field__hint" style="margin-top:8px">Rechazar borra el archivo y veta su huella. Tras ${store.securityPolicy?.strikes ?? 3} rechazos en ${store.securityPolicy?.strike_days ?? 30} días las subidas del estudiante se suspenden solas.</p>
            </div>` : html`<div style="margin-top:18px"><button class="btn btn--secondary" data-decide="rescan">${icon('refresh')}Volver a revisar</button></div>`}
        </div>`;
}

/* --- Política e IA ---------------------------------------------------------------- */

function cuotas(lista = []) {
    if (!lista.length) {
        return html`<p class="muted" style="font-size:14px">Todavía no hay datos: aparecen tras la primera respuesta de cada modelo.</p>`;
    }
    return html`<div class="quota-grid">${lista.map((q) => html`<div class="quota">
        <h4>${q.model.replace(/^groq\//, '')}</h4>
        ${q.tokens_limit ? meter({ label: 'Tokens este minuto', value: q.tokens_limit - (q.tokens_remaining ?? q.tokens_limit), max: q.tokens_limit,
            text: `${miles(q.tokens_limit - (q.tokens_remaining ?? q.tokens_limit))} de ${miles(q.tokens_limit)}` }) : ''}
        ${q.requests_limit ? meter({ label: 'Peticiones hoy', value: q.requests_limit - (q.requests_remaining ?? q.requests_limit), max: q.requests_limit,
            text: `${miles(q.requests_limit - (q.requests_remaining ?? q.requests_limit))} de ${miles(q.requests_limit)}` }) : ''}
        ${q.cooldown_seconds ? html`<span class="meter__status">${icon('clock')}En pausa ${q.cooldown_seconds} s por límite de cuota</span>` : ''}
    </div>`)}</div>`;
}

function disco(st) {
    if (!st) return '';
    const total = Object.values(st.folders).reduce((a, f) => a + f.bytes, 0);
    return html`<div class="stats-line" style="margin:4px 0 0">
        ${Object.entries(st.folders).filter(([k]) => k !== 'tmp').map(([k, f]) => html`<span><strong>${miles(f.files)}</strong>${CARPETAS[k] || k} (${fileSize(f.bytes) || '0 B'})</span>`)}
        <span><strong>${fileSize(total) || '0 B'}</strong>en total</span>
        ${st.free_bytes != null ? html`<span><strong>${fileSize(st.free_bytes)}</strong>libres en el disco</span>` : ''}
    </div>`;
}

function politica(o) {
    const p = o.policy || {};
    return html`<div class="sec-split">
        <section class="panel"><div class="panel__head"><h2>Reglas de subida</h2></div><div class="panel__body">
            <dl class="kv kv--policy">
                <dt>Tamaño máximo</dt><dd>${p.max_upload_mb} MB por archivo (fotos de perfil: ${p.avatar_max_mb} MB)</dd>
                <dt>Espacio por estudiante</dt><dd>${p.user_quota_mb} MB</dd>
                <dt>Subidas por día</dt><dd>${p.uploads_per_day} por estudiante</dd>
                <dt>Sin IA disponible</dt><dd>${p.require_ai ? 'el archivo espera en cuarentena hasta que la IA lo revise' : 'se publica con las dos primeras barreras'}</dd>
                <dt>Suspensión automática</dt><dd>${p.strikes ? `${p.strikes} rechazos en ${p.strike_days} días suspenden las subidas ${p.block_days} días` : 'desactivada'}</dd>
                <dt>Formatos aceptados</dt><dd class="chips chips--static">${(p.extensions || []).map((e) => html`<span class="tag">.${e}</span>`)}</dd>
            </dl>
            <p class="field__hint">Se cambian en el archivo .env (MAX_UPLOAD_MB, USER_QUOTA_MB, UPLOADS_PER_DAY, SCAN_REQUIRE_AI, UPLOAD_STRIKES...).</p>
        </div></section>
        <section class="panel"><div class="panel__head"><h2>Archivos en el servidor</h2></div><div class="panel__body">${disco(o.storage)}</div></section>
    </div>
    <section class="panel" style="margin-top:16px"><div class="panel__head"><h2>Respaldos</h2>
            <button class="btn btn--secondary btn--sm" data-action="backup">${icon('download')}Crear respaldo ahora</button></div>
        <div class="panel__body">${respaldos(o.backups)}</div></section>
    <section class="panel" style="margin-top:16px"><div class="panel__head"><h2>Cuota gratuita de la IA</h2></div>
        <div class="panel__body">${cuotas(o.ai?.quotas)}</div></section>`;
}

function respaldos(lista = []) {
    const info = html`<p class="field__hint" style="margin-top:10px">Se hace uno solo cada día con el servidor encendido y se guardan los 7 más
        recientes en instance/backups (base de datos y archivos, sin el .env). Para restaurar: apaga el servidor y ejecuta
        <code>python manage.py restore instance/backups/respaldo_....zip</code>.</p>`;
    if (!lista.length) return html`<p class="muted" style="font-size:14px">Todavía no hay respaldos.</p>${info}`;
    return html`<ul class="backups">${lista.map((b) => html`<li>${icon('folder')}<span>${b.name}</span>
        <span class="muted">${fileSize(b.bytes)}</span><span class="muted" title="${longDate(b.created_at)}">${timeAgo(b.created_at)}</span></li>`)}</ul>${info}`;
}

/* --- Reportes de estudiantes --------------------------------------------------------- */

function tarjetaReporte(d) {
    const doc = d.document;
    return html`<article class="panel report-card" data-report-kind="${d.kind}" data-report-id="${d.resource_id}">
        <div class="report-card__head">
            <div style="min-width:0;flex:1"><h3>${doc.title}</h3>
                <p class="muted">${d.kind === 'group' ? `Grupo ${doc.group || ''}` : 'Biblioteca'}${doc.owner ? `, subido por ${doc.owner.name}` : ''}${doc.filename ? `, ${doc.filename}` : ''}</p></div>
            <span class="report-card__count">${d.count} ${d.count === 1 ? 'reporte' : 'reportes'}</span>
        </div>
        <div class="chips chips--static">${d.reasons.map((m) => html`<span class="tag">${m.label} (${m.count})</span>`)}
            ${doc.scan_status === 'review' ? html`<span class="status status--review">${icon('alert')}Oculto mientras se revisa</span>` : ''}</div>
        ${d.reports.some((r) => r.comment) ? html`<ul class="report-card__comments">${d.reports.filter((r) => r.comment).map((r) => html`
            <li><strong>${r.reporter?.name || 'Estudiante'}:</strong> ${r.comment} <span class="muted">${timeAgo(r.created_at)}</span></li>`)}</ul>` : ''}
        ${doc.exists ? html`<div class="report-card__actions">
            <input class="input" data-report-note maxlength="300" placeholder="Nota (opcional): se guarda en la bitácora y la recibe quien lo subió si se elimina">
            <button class="btn btn--secondary btn--sm" data-report-action="dismiss">${icon('check')}Mantener publicado</button>
            <button class="btn btn--secondary btn--sm" data-report-action="hide">${icon('eye')}Ocultar y revisar</button>
            <button class="btn btn--danger btn--sm" data-report-action="remove">${icon('trash')}Eliminar</button>
        </div>` : html`<p class="muted" style="font-size:14px">El documento ya no existe. <button class="btn btn--ghost btn--sm" data-report-action="dismiss">Cerrar reportes</button></p>`}
    </article>`;
}

/* --- Bitácora ----------------------------------------------------------------------- */

// [texto, tono]: tono «bad» = intento sospechoso, «warn» = cambio importante, «ok» = normal.
const ACCIONES = {
    login_ok: ['Inició sesión', 'ok'],
    login_failed: ['Contraseña incorrecta', 'bad'],
    login_blocked: ['Intento con el correo bloqueado', 'bad'],
    login_2fa_failed: ['Código de verificación incorrecto', 'bad'],
    logout: ['Cerró sesión', ''],
    session_revoked: ['Cerró una sesión de otro dispositivo', ''],
    sessions_revoked_others: ['Cerró sus otras sesiones', ''],
    token_reuse: ['Sesión cerrada por posible robo', 'bad'],
    password_changed: ['Cambió su contraseña', 'warn'],
    register: ['Creó su cuenta', 'ok'],
    email_verified: ['Confirmó su correo', 'ok'],
    '2fa_enabled': ['Activó la verificación en dos pasos', 'ok'],
    '2fa_disabled': ['Desactivó la verificación en dos pasos', 'warn'],
    '2fa_step_up': ['Confirmó la sesión con su código', ''],
    '2fa_recovery_used': ['Usó un código de respaldo', 'warn'],
    '2fa_recovery_regenerated': ['Generó códigos de respaldo nuevos', ''],
    '2fa_reset': ['Le quitaron la verificación en dos pasos', 'warn'],
    scan_approved: ['Aprobó un archivo en cuarentena', 'ok'],
    scan_rejected: ['Rechazó un archivo', 'warn'],
    scan_rescan: ['Mandó a revisar de nuevo un archivo', ''],
    scan_export: ['Exportó el registro del vigilante', ''],
    hash_unblocked: ['Quitó el veto a una huella', 'warn'],
    uploads_suspended: ['Suspendió las subidas de un estudiante', 'warn'],
    uploads_restored: ['Reactivó las subidas de un estudiante', ''],
    uploads_auto_suspended: ['Suspensión automática por rechazos', 'warn'],
    report_dismiss: ['Descartó reportes de un documento', ''],
    report_hide: ['Ocultó un documento reportado', 'warn'],
    report_remove: ['Eliminó un documento reportado', 'warn'],
    backup_created: ['Creó un respaldo', 'ok'],
    data_export: ['Descargó sus datos', ''],
    account_deleted: ['Borró su cuenta', 'warn'],
    role_granted: ['Recibió el rol de administrador', 'warn'],
    role_removed: ['Perdió el rol de administrador', 'warn'],
};
const GRUPOS = [['', 'Todo'], ['failed', 'Intentos fallidos'], ['login', 'Entradas'], ['sessions', 'Sesiones'],
    ['2fa', 'Dos pasos'], ['files', 'Archivos'], ['privacy', 'Privacidad'], ['admin', 'Panel']];

function detalleEvento(e) {
    const d = e.details || {};
    const partes = [];
    if (d.reason === 'unknown_email') partes.push('el correo no tiene cuenta');
    else if (d.reason) partes.push(d.reason);
    if (d.file) partes.push(d.file);
    if (d.note) partes.push(`nota: ${d.note}`);
    if (d.days) partes.push(`${d.days} días`);
    if (d.rows !== undefined) partes.push(`${d.rows} filas`);
    if (d.device && e.action !== 'login_ok') partes.push(d.device);
    if (d.closed !== undefined) partes.push(d.closed === 1 ? '1 sesión cerrada' : `${d.closed} sesiones cerradas`);
    if (d.two_factor) partes.push('con código');
    if (d.left !== undefined) partes.push(`le quedan ${d.left}`);
    if (d.via) partes.push(`por ${d.via}`);
    return partes.join(', ');
}

function tablaBitacora(eventos, haySiguiente) {
    if (!eventos.length) return empty({ icon: 'history', title: 'Sin eventos', text: 'No hay registros con este filtro.' });
    return html`<table class="table audit"><thead><tr><th>Cuándo</th><th>Quién</th><th>Qué pasó</th><th>Dispositivo e IP</th></tr></thead>
        <tbody>${eventos.map((e) => {
            const [texto, tono] = ACCIONES[e.action] || [e.action, ''];
            const extra = detalleEvento(e);
            return html`<tr>
                <td class="muted" title="${longDate(e.created_at)}">${timeAgo(e.created_at)}</td>
                <td><strong>${e.name || e.email || 'Sin cuenta'}</strong>${e.name && e.email ? html`<div class="muted">${e.email}</div>` : ''}</td>
                <td><span class="audit-dot audit-dot--${tono || 'none'}"></span>${texto}${extra ? html`<div class="muted">${extra}</div>` : ''}</td>
                <td class="muted">${e.device || ''}${e.ip ? html`<div>${e.ip}</div>` : ''}</td>
            </tr>`;
        })}</tbody></table>
        ${haySiguiente ? html`<div style="padding:12px;text-align:center"><button class="btn btn--secondary btn--sm" data-action="audit-more">Cargar más</button></div>` : ''}`;
}

/* --- Puerta: verificación en dos pasos ---------------------------------------------- */

function puerta(root, err) {
    const configurar = err.code === 'two_factor_setup';
    setHtml(root, html`<div class="page"><section class="panel gate">
        <span class="gate__icon">${icon('shield')}</span>
        <h2>${configurar ? 'Activa la verificación en dos pasos' : 'Confirma que eres tú'}</h2>
        <p>${err.message}</p>
        <p class="muted">El panel decide qué archivos se publican y guarda la bitácora de la plataforma, por eso pide algo más que la contraseña.</p>
        <button class="btn btn--primary" data-action="gate">${icon(configurar ? 'shield' : 'key')}${configurar ? 'Activar ahora' : 'Escribir código'}</button>
    </section></div>`);
    $('[data-action="gate"]', root).addEventListener('click', () =>
        (configurar ? openTwoFactorSetup : openStepUp)({ onDone: () => resolve() }));
}

/** Diálogo para suspender las subidas de un estudiante. Devuelve true si se aplicó. */
function suspenderDialogo(userId, nombre) {
    return new Promise((ok) => {
        let hecho = false;
        const dlg = openDialog({
            title: `Suspender las subidas de ${nombre}`,
            description: 'Podrá seguir entrando y descargando, pero no subir archivos. Recibe un aviso con el motivo.',
            submitLabel: 'Suspender',
            danger: true,
            body: html`<label class="field"><span class="field__label">Duración</span>
                    <select class="select" name="days"><option value="1">1 día</option><option value="3">3 días</option>
                    <option value="7" selected>7 días</option><option value="30">30 días</option></select></label>
                <label class="field"><span class="field__label">Motivo</span>
                    <input class="input" name="reason" maxlength="200" required placeholder="Ej. Subió material con datos personales de otros"></label>`,
            onSubmit: async (form) => {
                if (!form.reason.value.trim()) throw new Error('Escribe el motivo: el estudiante lo verá.');
                const r = await api.post(`/api/admin/users/${userId}/uploads`, { days: Number(form.days.value), reason: form.reason.value.trim() });
                toast(r.message);
                hecho = true;
            },
        });
        dlg.addEventListener('close', () => ok(hecho));
    });
}

/* --- Vista ------------------------------------------------------------------------- */

export async function securityView(root, _params, signal) {
    if (!store.user.is_admin) {
        setHtml(root, html`<div class="page">${empty({ icon: 'lock', title: 'Sólo para administradores', text: 'Pide a la coordinación que agregue tu correo a ADMIN_EMAILS.' })}</div>`);
        return;
    }
    setHtml(root, html`<div class="page">${loading()}</div>`);
    let inicial = null;
    try {
        inicial = await api.get('/api/admin/overview');
    } catch (err) {
        if (['two_factor_setup', 'two_factor_step_up'].includes(err.code)) return puerta(root, err);
    }
    store.securityPolicy = inicial?.policy;

    let pestana = 'files';
    let filtro = 'quarantine';
    let tipo = '';
    let texto = '';
    let escaneos = [];
    let siguienteScan = null;
    const seleccion = new Set();
    let grupo = '';
    let busqueda = '';
    let eventos = [];
    let siguiente = null;

    const TABS = [['files', 'Archivos', 'shield'], ['reports', 'Reportes', 'flag'], ['students', 'Estudiantes', 'users'], ['hashes', 'Huellas vetadas', 'lock'],
        ['policy', 'Política e IA', 'filter'], ['audit', 'Bitácora', 'history']];

    setHtml(root, html`<div class="page page--wide">
        <div class="page-head"><div><h1>Seguridad</h1><p>Todo archivo pasa por tres barreras. Lo limpio se publica solo: aquí decides sobre lo que quedó en cuarentena y sobre quién sube qué.</p></div>
            <div class="page-head__actions"><button class="btn btn--secondary" data-action="refresh">${icon('refresh')}Actualizar</button></div></div>
        <div class="tabs" role="tablist">${TABS.map(([k, l, ic]) => html`<button class="tab" role="tab" data-tab="${k}" aria-selected="${k === pestana}">${icon(ic)}${l}<span data-tab-count="${k}"></span></button>`)}</div>
        <div data-pane="files">
            <div data-slot="overview">${loading()}</div>
            <div class="scan-tools">
                <div class="chips" data-slot="filters"></div>
                <select class="select" data-kind aria-label="Dónde se subió"><option value="">Todo el sitio</option>
                    ${Object.entries(TIPO).map(([k, l]) => html`<option value="${k}">${l}</option>`)}</select>
                <div class="search">${icon('search')}<input class="input" type="search" data-scan-q placeholder="Archivo, estudiante, correo o huella" aria-label="Buscar en el registro del vigilante"></div>
                <button class="btn btn--secondary btn--sm" data-action="export">${icon('download')}Exportar CSV</button>
            </div>
            <div class="bulk-bar" data-slot="bulk" hidden></div>
            <section class="panel table-wrap" data-slot="table">${loading()}</section>
        </div>
        <div data-pane="reports" hidden>
            <p class="field__hint" style="margin-bottom:12px" data-slot="reports-hint">Los estudiantes pueden reportar documentos de la biblioteca o de sus grupos.</p>
            <div data-slot="reports">${loading()}</div>
        </div>
        <div data-pane="students" hidden><section class="panel table-wrap" data-slot="students">${loading()}</section></div>
        <div data-pane="hashes" hidden><section class="panel table-wrap" data-slot="hashes">${loading()}</section></div>
        <div data-pane="policy" hidden><div data-slot="policy">${loading()}</div></div>
        <div data-pane="audit" hidden>
            <div class="audit-tools">
                <div class="chips">${GRUPOS.map(([k, l]) => html`<button class="chip" data-group="${k}" aria-pressed="${k === grupo}">${l}</button>`)}</div>
                <div class="search">${icon('search')}<input class="input" type="search" data-audit-q placeholder="Buscar por correo, IP o archivo" aria-label="Buscar en la bitácora"></div>
            </div>
            <section class="panel table-wrap" data-slot="audit">${loading()}</section>
            <p class="field__hint" style="margin-top:10px">Se guardan los últimos 180 días (AUDIT_RETENTION_DAYS).</p>
        </div>
    </div>`);

    const contar = (k, n) => setHtml($(`[data-tab-count="${k}"]`, root), n ? html`<span class="nav__count">${n}</span>` : '');

    async function resumen(precargado) {
        try {
            const [o, stats] = await Promise.all([precargado ? Promise.resolve(precargado) : api.get('/api/admin/overview'),
                api.get('/api/admin/scans/stats?days=14')]);
            inicial = o;
            store.securityPolicy = o.policy;
            const ia = o.ai || {};
            const sc = o.scans || {};
            contar('files', o.quarantine);
            contar('students', o.suspended_uploaders);
            setHtml($('[data-slot="overview"]', root), html`
            <div class="sec-kpis">
                <div class="sec-kpi ${o.quarantine ? 'is-alert' : ''}"><strong>${o.quarantine ?? 0}</strong><span>en cuarentena esperando decisión</span></div>
                <div class="sec-kpi"><strong>${miles(o.scans_24h)}</strong><span>archivos revisados en 24 h</span></div>
                <div class="sec-kpi"><strong>${miles(sc.blocked)}</strong><span>bloqueados en total</span></div>
                <div class="sec-kpi"><strong>${o.suspended_uploaders ?? 0}</strong><span>estudiantes con subidas suspendidas</span></div>
                <div class="sec-kpi"><strong>${o.scan_queue ?? 0}</strong><span>en cola del vigilante</span></div>
            </div>
            <div class="sec-split">
                <section class="panel"><div class="panel__head"><h2>Actividad de los últimos 14 días</h2></div><div class="panel__body">${actividad(stats.days)}</div></section>
                <section class="panel"><div class="panel__head"><h2>Por qué se marcaron</h2></div><div class="panel__body">${motivos(stats.reasons)}</div></section>
            </div>
            <div class="layers layers--compact">
                ${capa(1, 'Análisis estático', 'Tipo real, macros, JavaScript en PDF, ejecutables en ZIP, plantillas remotas y zip bombs.', 'Siempre activo', true)}
                ${capa(2, 'Antivirus del sistema', 'Escanea cada archivo con el antivirus del servidor.', o.antivirus || 'No disponible en este servidor', !!o.antivirus)}
                ${capa(3, 'Vigilante con IA', 'Revisa el contenido: phishing, contenido inapropiado, datos personales e instrucciones ocultas.',
                    ia.security ? `${ia.security.provider}: ${ia.security.model}` : 'Sin modelo configurado', !!ia.security)}
            </div>`);
            const cuenta = { quarantine: o.quarantine, blocked: sc.blocked, pending: sc.pending };
            setHtml($('[data-slot="filters"]', root), html`${FILTROS.map(([k, l]) => html`<button class="chip" data-filter="${k}" aria-pressed="${filtro === k}">${l}${cuenta[k] ? html` <span class="chip__n">${cuenta[k]}</span>` : ''}</button>`)}`);
            if (pestana === 'policy') setHtml($('[data-slot="policy"]', root), politica(o));
        } catch (err) {
            setHtml($('[data-slot="overview"]', root), empty({ icon: 'alert', title: 'No se pudo cargar el resumen', text: err.message }));
        }
    }

    function parametrosScans(extra = {}) {
        const p = new URLSearchParams({ limit: '50', ...extra });
        if (filtro) p.set('status', filtro);
        if (tipo) p.set('kind', tipo);
        if (texto) p.set('q', texto);
        return p;
    }

    function pintarBulk() {
        const barra = $('[data-slot="bulk"]', root);
        barra.hidden = !seleccion.size;
        if (!seleccion.size) return;
        setHtml(barra, html`<strong>${seleccion.size} ${seleccion.size === 1 ? 'archivo seleccionado' : 'archivos seleccionados'}</strong>
            <input class="input" data-bulk-note maxlength="500" placeholder="Nota para los estudiantes (opcional)" aria-label="Nota para los estudiantes">
            <button class="btn btn--primary btn--sm" data-bulk="approve">${icon('check')}Aprobar</button>
            <button class="btn btn--danger btn--sm" data-bulk="reject">${icon('lock')}Rechazar</button>
            <button class="btn btn--ghost btn--sm" data-bulk="clear">Quitar selección</button>`);
    }

    function pintarTabla() {
        const conCasillas = filtro === 'quarantine';
        const todos = conCasillas && escaneos.length && escaneos.every((s) => seleccion.has(s.id));
        setHtml($('[data-slot="table"]', root), escaneos.length ? html`<table class="table"><thead><tr>
                ${conCasillas ? html`<th class="table__check"><input type="checkbox" data-pick-all aria-label="Seleccionar todos" ${todos ? 'checked' : ''}></th>` : ''}
                <th>Archivo</th><th>Dónde</th><th>Subido por</th><th>Resultado</th><th>Motivo</th><th>Fecha</th></tr></thead>
            <tbody>${escaneos.map((s) => filaArchivo(s, seleccion, conCasillas))}</tbody></table>
            ${siguienteScan ? html`<div style="padding:12px;text-align:center"><button class="btn btn--secondary btn--sm" data-action="scan-more">Cargar más</button></div>` : ''}`
            : empty({ icon: 'shield', title: filtro === 'quarantine' && !texto && !tipo ? 'Nada en cuarentena' : 'Sin resultados',
                text: filtro === 'quarantine' && !texto && !tipo ? 'Todo lo que se subió pasó las tres barreras y se publicó solo.' : 'Prueba con otro filtro o búsqueda.' }));
        pintarBulk();
    }

    async function tabla(mas = false) {
        try {
            const r = await api.get(`/api/admin/scans?${parametrosScans(mas && siguienteScan ? { before: String(siguienteScan) } : {})}`);
            escaneos = mas ? escaneos.concat(r.scans) : r.scans;
            siguienteScan = r.next_before;
            if (!mas) [...seleccion].forEach((id) => { if (!escaneos.some((s) => s.id === id)) seleccion.delete(id); });
            pintarTabla();
        } catch (err) {
            setHtml($('[data-slot="table"]', root), empty({ icon: 'alert', title: 'No se pudo cargar', text: err.message }));
        }
    }

    async function estudiantes() {
        const slot = $('[data-slot="students"]', root);
        try {
            const { uploaders: lista, policy: p } = await api.get('/api/admin/uploaders');
            setHtml(slot, lista.length ? html`<table class="table"><thead><tr><th>Estudiante</th><th>Subidas (${p.strike_days} días)</th>
                    <th>Marcadas</th><th>Rechazos</th><th>Estado</th><th></th></tr></thead>
                <tbody>${lista.map((u) => html`<tr>
                    <td><div style="display:flex;gap:10px;align-items:center">${avatar(u, 'sm')}<div><strong>${u.name}</strong><div class="muted">${u.email}</div></div></div></td>
                    <td>${u.uploads}</td><td>${u.flagged}</td>
                    <td><span class="strikes ${u.strikes >= p.strikes ? 'is-full' : ''}">${u.strikes} / ${p.strikes}</span></td>
                    <td>${u.blocked_until ? html`<span class="status status--blocked">${icon('lock')}Suspendido</span>
                        <div class="muted">hasta ${longDate(u.blocked_until)}${u.block_reason ? `, ${u.block_reason}` : ''}</div>` : html`<span class="status status--clean">${icon('check')}Puede subir</span>`}</td>
                    <td style="white-space:nowrap">
                        <button class="btn btn--ghost btn--sm" data-uploader-files="${u.email}">${icon('search')}Archivos</button>
                        ${u.blocked_until ? html`<button class="btn btn--secondary btn--sm" data-unsuspend="${u.id}">Reactivar</button>`
                            : html`<button class="btn btn--secondary btn--sm" data-suspend="${u.id}" data-name="${u.name}">Suspender</button>`}
                    </td></tr>`)}</tbody></table>`
                : empty({ icon: 'users', title: 'Nadie con archivos marcados', text: `Aquí aparecen los estudiantes con archivos en cuarentena o rechazados en los últimos ${p.strike_days} días.` }));
        } catch (err) {
            setHtml(slot, empty({ icon: 'alert', title: 'No se pudo cargar', text: err.message }));
        }
    }

    async function reportes() {
        const slot = $('[data-slot="reports"]', root);
        try {
            const r = await api.get('/api/admin/reports');
            contar('reports', r.open);
            setHtml($('[data-slot="reports-hint"]', root), html`Los estudiantes pueden reportar documentos de la biblioteca o de sus grupos.
                Con ${r.hide_threshold} reportes de personas distintas el documento se oculta solo hasta que decidas (REPORT_HIDE_THRESHOLD).`);
            setHtml(slot, r.documents.length ? html`<div class="report-list">${r.documents.map(tarjetaReporte)}</div>`
                : html`<section class="panel">${empty({ icon: 'flag', title: 'Sin reportes pendientes', text: 'Cuando un estudiante reporte un documento aparecerá aquí.' })}</section>`);
        } catch (err) {
            setHtml(slot, empty({ icon: 'alert', title: 'No se pudo cargar', text: err.message }));
        }
    }

    async function huellas() {
        const slot = $('[data-slot="hashes"]', root);
        try {
            const { hashes } = await api.get('/api/admin/blocked-hashes');
            contar('hashes', 0);
            setHtml(slot, hashes.length ? html`<table class="table"><thead><tr><th>Archivo</th><th>Motivo</th><th>Huella SHA-256</th><th>Vetado</th><th></th></tr></thead>
                <tbody>${hashes.map((h) => html`<tr>
                    <td style="font-weight:600;word-break:break-all;max-width:220px">${h.original_name || 'Sin nombre'}</td>
                    <td class="muted" style="max-width:320px">${h.reason || ''}</td>
                    <td><code class="hash" title="${h.sha256}">${h.sha256.slice(0, 16)}…</code></td>
                    <td class="muted">${timeAgo(h.created_at)}${h.created_by_name ? html`<div>por ${h.created_by_name}</div>` : html`<div>por el vigilante</div>`}</td>
                    <td><button class="btn btn--ghost btn--sm" data-unban="${h.sha256}" data-name="${h.original_name || 'este archivo'}">Quitar veto</button></td></tr>`)}</tbody></table>`
                : empty({ icon: 'lock', title: 'Ninguna huella vetada', text: 'Cuando rechazas un archivo o el antivirus encuentra malware, su huella se veta para que no se pueda volver a subir.' }));
        } catch (err) {
            setHtml(slot, empty({ icon: 'alert', title: 'No se pudo cargar', text: err.message }));
        }
    }

    async function bitacora(mas = false) {
        const slot = $('[data-slot="audit"]', root);
        const params = new URLSearchParams({ limit: '50' });
        if (grupo) params.set('group', grupo);
        if (busqueda) params.set('q', busqueda);
        if (mas && siguiente) params.set('before', String(siguiente));
        try {
            const r = await api.get(`/api/admin/audit?${params}`);
            eventos = mas ? eventos.concat(r.events) : r.events;
            siguiente = r.next_before;
            setHtml(slot, tablaBitacora(eventos, !!siguiente));
        } catch (err) {
            setHtml(slot, empty({ icon: 'alert', title: 'No se pudo cargar la bitácora', text: err.message }));
        }
    }

    function cambiarPestana(k) {
        pestana = k;
        root.querySelectorAll('[data-tab]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === k)));
        root.querySelectorAll('[data-pane]').forEach((p) => { p.hidden = p.dataset.pane !== k; });
        if (k === 'audit') bitacora();
        if (k === 'students') estudiantes();
        if (k === 'reports') reportes();
        if (k === 'hashes') huellas();
        if (k === 'policy') setHtml($('[data-slot="policy"]', root), inicial ? politica(inicial) : loading());
    }

    function verArchivosDe(correo) {
        closeDrawer();
        cambiarPestana('files');
        filtro = '';
        texto = correo;
        $('[data-scan-q]', root).value = correo;
        root.querySelectorAll('[data-filter]').forEach((c) => c.setAttribute('aria-pressed', String(c.dataset.filter === '')));
        tabla();
    }

    async function refrescarTodo() {
        await resumen();
        tabla();
        if (pestana === 'students') estudiantes();
        if (pestana === 'hashes') huellas();
        if (pestana === 'reports') reportes();
    }

    /* Eventos */
    on(root, 'click', '[data-tab]', (_e, b) => cambiarPestana(b.dataset.tab), signal);
    on(root, 'click', '[data-group]', (_e, b) => {
        grupo = b.dataset.group;
        root.querySelectorAll('[data-group]').forEach((c) => c.setAttribute('aria-pressed', String(c === b)));
        bitacora();
    }, signal);
    $('[data-audit-q]', root).addEventListener('input', debounce((e) => { busqueda = e.target.value.trim(); bitacora(); }, 350), { signal });
    on(root, 'click', '[data-action="audit-more"]', (_e, b) => { b.disabled = true; bitacora(true); }, signal);

    on(root, 'click', '[data-filter]', (_e, b) => {
        filtro = b.dataset.filter;
        seleccion.clear();
        root.querySelectorAll('[data-filter]').forEach((c) => c.setAttribute('aria-pressed', String(c === b)));
        tabla();
    }, signal);
    $('[data-kind]', root).addEventListener('change', (e) => { tipo = e.target.value; tabla(); }, { signal });
    $('[data-scan-q]', root).addEventListener('input', debounce((e) => { texto = e.target.value.trim(); tabla(); }, 350), { signal });
    on(root, 'click', '[data-action="scan-more"]', (_e, b) => { b.disabled = true; tabla(true); }, signal);
    on(root, 'click', '[data-action="refresh"]', () => (pestana === 'audit' ? bitacora() : refrescarTodo()), signal);
    on(root, 'click', '[data-action="export"]', async (_e, b) => {
        b.disabled = true;
        try {
            const blob = await api.blob(`/api/admin/scans/export.csv?${parametrosScans()}`);
            const url = URL.createObjectURL(blob);
            const a = Object.assign(document.createElement('a'), { href: url, download: 'vigilante_ufg_hub.csv' });
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 5000);
        } catch (err) { toast(err.message, 'error'); } finally { b.disabled = false; }
    }, signal);

    // Selección para decidir en lote (sólo en «En cuarentena»).
    on(root, 'click', '[data-stop]', (e) => e.stopPropagation(), signal);
    on(root, 'change', '[data-pick]', (_e, c) => {
        const id = Number(c.dataset.pick);
        if (c.checked) seleccion.add(id); else seleccion.delete(id);
        pintarBulk();
        const todos = $('[data-pick-all]', root);
        if (todos) todos.checked = escaneos.every((s) => seleccion.has(s.id));
    }, signal);
    on(root, 'change', '[data-pick-all]', (_e, c) => {
        escaneos.forEach((s) => (c.checked ? seleccion.add(s.id) : seleccion.delete(s.id)));
        pintarTabla();
    }, signal);
    on(root, 'click', '[data-bulk]', async (_e, b) => {
        const accion = b.dataset.bulk;
        if (accion === 'clear') { seleccion.clear(); pintarTabla(); return; }
        const n = seleccion.size;
        if (accion === 'reject' && !await confirmDialog({ title: `Rechazar ${n} ${n === 1 ? 'archivo' : 'archivos'}`,
            text: 'Se borrarán del servidor y sus huellas quedarán vetadas. Los estudiantes reciben un aviso.', confirmLabel: 'Rechazar' })) return;
        b.disabled = true;
        try {
            const r = await api.post('/api/admin/scans/bulk', { ids: [...seleccion], decision: accion,
                note: $('[data-bulk-note]', root)?.value.trim() || '' });
            toast(`${r.done} ${r.done === 1 ? 'archivo' : 'archivos'} ${accion === 'approve' ? 'aprobados' : 'rechazados'}`
                + (r.uploaders_suspended ? `. ${r.uploaders_suspended} estudiante(s) quedaron suspendidos por acumular rechazos.` : ''));
            if (r.failed.length) toast(`${r.failed.length} no se pudieron procesar: ya no estaban en cuarentena.`, 'info');
            seleccion.clear();
            refrescarTodo();
        } catch (err) { toast(err.message, 'error'); b.disabled = false; }
    }, signal);

    // Estudiantes: suspender, reactivar y ver sus archivos (desde la tabla o el detalle).
    async function suspender(b) {
        if (await suspenderDialogo(Number(b.dataset.suspend), b.dataset.name)) { closeDrawer(); refrescarTodo(); }
    }
    async function reactivar(b) {
        try {
            const r = await api.post(`/api/admin/users/${b.dataset.unsuspend}/uploads`, { days: 0 });
            toast(r.message);
            closeDrawer();
            refrescarTodo();
        } catch (err) { toast(err.message, 'error'); }
    }
    on(root, 'click', '[data-suspend]', (_e, b) => suspender(b), signal);
    on(root, 'click', '[data-unsuspend]', (_e, b) => reactivar(b), signal);
    on(root, 'click', '[data-uploader-files]', (_e, b) => verArchivosDe(b.dataset.uploaderFiles), signal);
    on(root, 'click', '[data-unban]', async (_e, b) => {
        if (!await confirmDialog({ title: 'Quitar el veto', text: `«${b.dataset.name}» se podrá volver a subir. Igual pasará otra vez por las tres barreras.`, confirmLabel: 'Quitar veto', danger: false })) return;
        try {
            toast((await api.del(`/api/admin/blocked-hashes/${b.dataset.unban}`)).message);
            huellas();
            resumen();
        } catch (err) { toast(err.message, 'error'); }
    }, signal);

    // Detalle de un archivo.
    on(root, 'click', '[data-scan]', (_e, tr) => {
        const s = escaneos.find((x) => x.id === Number(tr.dataset.scan));
        const drawer = openDrawer(detalle(s));
        let urlImagen = null;
        drawer.addEventListener('click', async (e) => {
            if (e.target.closest('[data-uploader-files]')) return verArchivosDe(e.target.closest('[data-uploader-files]').dataset.uploaderFiles);
            if (e.target.closest('[data-suspend]')) return suspender(e.target.closest('[data-suspend]'));
            if (e.target.closest('[data-unsuspend]')) return reactivar(e.target.closest('[data-unsuspend]'));
            if (e.target.closest('[data-preview]')) {
                const slot = drawer.querySelector('[data-slot="preview"]');
                setHtml(slot, loading());
                try {
                    const p = await api.get(`/api/admin/scans/${s.id}/preview`);
                    if (p.image) {
                        urlImagen = URL.createObjectURL(await api.blob(`/api/admin/scans/${s.id}/image`));
                        setHtml(slot, html`<img class="scan-preview__img" src="${urlImagen}" alt="Imagen en revisión">`);
                    } else {
                        setHtml(slot, p.text ? html`<pre class="scan-preview">${p.text}</pre>`
                            : html`<p class="muted" style="font-size:14px">No hay texto que mostrar (${p.status === 'sin_texto' ? 'PDF escaneado' : 'formato sin texto'}).</p>`);
                    }
                } catch (err) {
                    setHtml(slot, html`<p class="muted" style="font-size:14px">${err.message}</p>`);
                }
                return;
            }
            const b = e.target.closest('[data-decide]');
            if (!b) return;
            const nota = drawer.querySelector('[data-note]')?.value.trim() || '';
            try {
                if (b.dataset.decide === 'rescan') {
                    await api.post(`/api/admin/scans/${s.id}/rescan`);
                    toast('Enviado de nuevo al vigilante');
                } else {
                    if (b.dataset.decide === 'reject' && !await confirmDialog({ title: 'Rechazar archivo', text: 'Se borrará del servidor y no se podrá volver a subir.', confirmLabel: 'Rechazar' })) return;
                    const r = await api.post(`/api/admin/scans/${s.id}/decision`, { decision: b.dataset.decide, note: nota });
                    toast(b.dataset.decide === 'approve' ? 'Archivo aprobado y publicado' : 'Archivo rechazado');
                    if (r.uploader_suspended) toast(`Las subidas de ${s.user?.name || 'este estudiante'} se suspendieron por acumular rechazos.`, 'info', 6000);
                }
                closeDrawer();
                refrescarTodo();
            } catch (err) { toast(err.message, 'error'); }
        });
        drawer.addEventListener('transitionend', () => { if (!drawer.isConnected && urlImagen) URL.revokeObjectURL(urlImagen); });
    }, signal);

    on(root, 'click', '[data-report-action]', async (_e, b) => {
        const card = b.closest('[data-report-kind]');
        const accion = b.dataset.reportAction;
        if (accion === 'remove' && !await confirmDialog({ title: 'Eliminar documento',
            text: 'Se borrará el archivo, su huella quedará vetada y cuenta como un rechazo para quien lo subió.', confirmLabel: 'Eliminar' })) return;
        b.disabled = true;
        try {
            const r = await api.post('/api/admin/reports/resolve', { kind: card.dataset.reportKind, resource_id: Number(card.dataset.reportId),
                action: accion, note: card.querySelector('[data-report-note]')?.value.trim() || '' });
            toast(r.message);
            refrescarTodo();
            reportes();
        } catch (err) { toast(err.message, 'error'); b.disabled = false; }
    }, signal);
    on(root, 'click', '[data-action="backup"]', async (_e, b) => {
        b.disabled = true;
        try {
            const r = await api.post('/api/admin/backups');
            toast(r.message);
            inicial = { ...inicial, backups: r.backups };
            setHtml($('[data-slot="policy"]', root), politica(inicial));
        } catch (err) { toast(err.message, 'error'); b.disabled = false; }
    }, signal);

    await resumen(inicial);
    tabla();
    api.get('/api/admin/reports').then((r) => contar('reports', r.open)).catch(() => {});
}
