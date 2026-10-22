/** Grupos de trabajo: lista y detalle (chat, tareas, archivos y miembros). */

import { api } from '../core/api.js';
import { $, fileSize, html, longDate, on, raw, setHtml, timeAgo } from '../core/dom.js';
import { go } from '../core/router.js';
import { store } from '../core/store.js';
import { typeLabel } from '../data/categories.js';
import { avatar, countBadge, empty, loading, scanBadge } from '../ui/components.js';
import { mountChat } from '../ui/chatlog.js';
import { icon } from '../ui/icons.js';
import { confirmDialog, openDialog, openMenu, toast } from '../ui/overlay.js';
import { askAboutDocument } from './assistant.js';
import { openUserProfile } from './people.js';

const ESTADOS = [
    ['pending', 'Pendiente', 'var(--ink-3)'],
    ['in_progress', 'En progreso', 'var(--ufg-orange)'],
    ['completed', 'Hecha', 'var(--success)'],
];

function badgeLetra(nombre) {
    return (nombre || '?').trim().slice(0, 1).toUpperCase();
}

/* --- Crear / editar grupo -------------------------------------------------------- */
async function groupDialog(grupo = null, onDone = () => {}) {
    let amigos = [];
    if (!grupo) {
        try { amigos = (await api.get('/api/contacts')).contacts; } catch { /* opcional */ }
    }
    openDialog({
        title: grupo ? 'Editar grupo' : 'Crear grupo de trabajo',
        description: grupo ? '' : 'Organiza un proyecto: chat, tareas y archivos en un mismo lugar.',
        submitLabel: grupo ? 'Guardar' : 'Crear grupo',
        body: html`
            <label class="field"><span class="field__label">Nombre</span>
                <input class="input" name="name" required maxlength="200" value="${grupo?.name || ''}" placeholder="Ej. Proyecto final de Bases de Datos"></label>
            <label class="field"><span class="field__label">Materia</span>
                <input class="input" name="subject" maxlength="120" value="${grupo?.subject || ''}" placeholder="Ej. Bases de Datos II"></label>
            <label class="field"><span class="field__label">Descripción</span>
                <textarea class="textarea" name="description" rows="3" maxlength="2000" placeholder="Objetivo, entregas, acuerdos...">${grupo?.description || ''}</textarea></label>
            ${!grupo && amigos.length ? html`<div class="field"><span class="field__label">Agregar amigos</span>
                <div class="chips">${amigos.map((c) => html`<button type="button" class="chip" data-member="${c.user.id}" aria-pressed="false">${c.name}</button>`)}</div></div>` : ''}`,
        onOpen: (dlg) => dlg.querySelectorAll('[data-member]').forEach((b) => b.addEventListener('click', () =>
            b.setAttribute('aria-pressed', String(b.getAttribute('aria-pressed') !== 'true')))),
        onSubmit: async (form, dlg) => {
            const datos = Object.fromEntries(new FormData(form));
            if (!datos.name.trim()) throw new Error('Ponle un nombre al grupo.');
            if (grupo) {
                await api.put(`/api/groups/${grupo.id}`, datos);
                toast('Grupo actualizado');
                onDone(grupo.id);
            } else {
                datos.member_ids = [...dlg.querySelectorAll('[data-member][aria-pressed="true"]')].map((b) => Number(b.dataset.member));
                const r = await api.post('/api/groups', datos);
                toast('Grupo creado');
                onDone(r.group_id);
            }
        },
    });
}

/* --- Lista -------------------------------------------------------------------------- */
export async function groupsView(root, params, signal) {
    if (params.id) return groupDetail(root, Number(params.id), signal, params.query?.tab);

    setHtml(root, html`<div class="page">
        <div class="page-head">
            <div><h1>Grupos de trabajo</h1><p>Reúne a tu equipo, reparte tareas y comparte archivos que sólo ven los miembros.</p></div>
            <div class="page-head__actions"><button class="btn btn--primary" data-action="create">${icon('plus')}Crear grupo</button></div>
        </div>
        <div data-slot="list">${loading()}</div>
    </div>`);

    async function cargar() {
        try {
            const { groups } = await api.get('/api/groups');
            setHtml($('[data-slot="list"]', root), groups.length ? html`<div class="groups-grid">${groups.map((g) => html`
                <a class="group-card" href="#/grupos/${g.id}">
                    <div class="group-card__top">
                        <span class="group-card__badge">${badgeLetra(g.name)}</span>
                        <div style="min-width:0;flex:1"><h3>${g.name}</h3>
                            <div class="group-card__subject">${g.subject || (g.is_owner ? 'Eres líder' : `Líder: ${g.owner_name}`)}</div></div>
                        ${countBadge(g.unread)}
                    </div>
                    ${g.description ? html`<p class="group-card__desc">${g.description}</p>` : ''}
                    ${g.last_message ? html`<p style="font-size:13.5px;color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
                        <strong style="color:var(--ink-2)">${g.last_message.user_name.split(' ')[0]}:</strong> ${g.last_message.message}</p>` : ''}
                    <div class="group-card__foot">
                        <span>${icon('users')}${g.member_count}</span>
                        <span>${icon('tasks')}${g.open_tasks} abiertas</span>
                        <span>${icon('folder')}${g.resource_count}</span>
                        <span style="margin-left:auto">${g.last_message ? timeAgo(g.last_message.timestamp) : timeAgo(g.created_at)}</span>
                    </div>
                </a>`)}</div>`
                : html`<div class="panel">${empty({ icon: 'users', title: 'Todavía no estás en ningún grupo', text: 'Crea uno para tu próximo proyecto e invita a tus amigos.',
                    action: html`<button class="btn btn--primary" data-action="create">${icon('plus')}Crear grupo</button>` })}</div>`);
        } catch (err) {
            setHtml($('[data-slot="list"]', root), empty({ icon: 'alert', title: 'No se pudieron cargar tus grupos', text: err.message }));
        }
    }

    on(root, 'click', '[data-action="create"]', () => groupDialog(null, (id) => go(`/grupos/${id}`)), signal);
    store.on('pulse', ({ pulse, previo }) => { if (pulse.groups_unread_total !== previo?.groups_unread_total) cargar(); }, signal);
    cargar();
}

/* --- Detalle ------------------------------------------------------------------------ */
async function groupDetail(root, gid, signal, tabInicial = 'chat') {
    setHtml(root, html`<div class="page page--wide">${loading()}</div>`);
    let datos;
    try {
        datos = await api.get(`/api/groups/${gid}`);
    } catch (err) {
        setHtml(root, html`<div class="page">${empty({ icon: 'lock', title: 'No puedes ver este grupo', text: err.message,
            action: html`<a class="btn btn--secondary" href="#/grupos">Volver a tus grupos</a>` })}</div>`);
        return;
    }
    let tab = ['chat', 'tareas', 'archivos', 'miembros'].includes(tabInicial) ? tabInicial : 'chat';
    const yo = store.user.id;

    function cabecera() {
        const g = datos.group;
        return html`<div class="group-head">
            <a class="icon-btn" href="#/grupos" aria-label="Volver a tus grupos">${icon('chevronLeft')}</a>
            <span class="group-card__badge">${badgeLetra(g.name)}</span>
            <div style="min-width:0"><h1>${g.name}</h1><p>${[g.subject, `${datos.members.length} miembros`].filter(Boolean).join(', ')}</p></div>
            <div class="group-head__actions">
                <div class="faces">${datos.members.slice(0, 5).map((m) => avatar(m, 'sm'))}</div>
                <button class="icon-btn" data-action="group-menu" aria-label="Opciones del grupo">${icon('more')}</button>
            </div>
        </div>
        <div class="tabs" role="tablist">
            ${[['chat', 'Chat', 'chat'], ['tareas', 'Tareas', 'tasks'], ['archivos', 'Archivos', 'folder'], ['miembros', 'Miembros', 'users']].map(([k, l, ic]) =>
                html`<button class="tab" role="tab" data-tab="${k}" aria-selected="${tab === k}">${icon(ic)}${l}${k === 'tareas' && datos.group.open_tasks ? html` <span class="tag">${datos.group.open_tasks}</span>` : ''}</button>`)}
        </div>`;
    }

    setHtml(root, html`<div class="page page--wide"><div data-slot="head"></div><div data-slot="body"></div></div>`);
    const cuerpo = $('[data-slot="body"]', root);
    let chat = null;

    async function recargar() {
        datos = await api.get(`/api/groups/${gid}`);
        setHtml($('[data-slot="head"]', root), cabecera());
        if (tab !== 'chat') pintar();
    }

    function pintar() {
        setHtml($('[data-slot="head"]', root), cabecera());
        if (tab === 'chat') pintarChat();
        if (tab === 'tareas') pintarTareas();
        if (tab === 'archivos') pintarArchivos();
        if (tab === 'miembros') pintarMiembros();
    }

    function pintarChat() {
        setHtml(cuerpo, html`<div class="group-layout">
            <section class="panel group-chat" data-slot="chat"></section>
            <aside class="panel"><div class="panel__head"><h3>Próximas tareas</h3><button class="btn btn--ghost btn--sm" data-tab="tareas">Ver todas</button></div>
                <div class="mini-list">${datos.tasks.filter((t) => t.status !== 'completed').slice(0, 5).map((t) => html`
                    <button class="mini-item" data-tab="tareas"><span style="width:9px;height:9px;border-radius:50%;flex:none;background:${ESTADOS.find((e) => e[0] === t.status)[2]}"></span>
                    <span style="min-width:0"><span class="mini-item__title">${t.title}</span><span class="mini-item__meta" style="display:block">${t.assigned_to || 'Sin responsable'}${t.due_date ? `, entrega ${longDate(t.due_date + 'T12:00:00')}` : ''}</span></span></button>`)}
                ${!datos.tasks.some((t) => t.status !== 'completed') ? html`<p style="padding:14px 18px;color:var(--ink-3);font-size:14px">No hay tareas pendientes.</p>` : ''}</div></aside>
        </div>`);
        chat = mountChat($('[data-slot="chat"]', cuerpo), {
            signal,
            placeholder: `Escribe a ${datos.group.name}`,
            load: async (after) => (await api.get(`/api/groups/${gid}/messages${after ? `?after=${after}` : ''}`)).messages,
            send: async (texto) => (await api.post(`/api/groups/${gid}/messages`, { message: texto })).data,
            toMsg: (m) => ({ id: m.id, userId: m.user_id, user: m.user || { name: m.user_name }, text: m.message, time: m.timestamp }),
        });
    }

    function tareaHtml(t) {
        const vencida = t.due_date && t.status !== 'completed' && new Date(t.due_date + 'T23:59:59') < new Date();
        const idx = ESTADOS.findIndex((e) => e[0] === t.status);
        return html`<div class="task ${t.status === 'completed' ? 'task--done' : ''}" data-task="${t.id}">
            <div style="display:flex;gap:6px;align-items:flex-start"><div class="task__title" style="flex:1">${t.title}</div>
                <button class="icon-btn icon-btn--sm" data-task-menu="${t.id}" aria-label="Opciones de la tarea" style="margin:-6px -6px 0 0">${icon('more')}</button></div>
            ${t.description ? html`<div class="task__desc">${t.description}</div>` : ''}
            <div class="task__meta">
                <span>${icon('user')}${t.assigned_to || 'Sin responsable'}</span>
                ${t.due_date ? html`<span class="${vencida ? 'is-late' : ''}">${icon('calendar')}${longDate(t.due_date + 'T12:00:00')}${vencida ? ' (vencida)' : ''}</span>` : ''}
            </div>
            <div class="task__actions">
                ${idx > 0 ? html`<button class="btn btn--ghost btn--sm" data-move="${t.id}" data-to="${ESTADOS[idx - 1][0]}">${icon('chevronLeft')}${ESTADOS[idx - 1][1]}</button>` : ''}
                ${idx < 2 ? html`<button class="btn btn--secondary btn--sm" data-move="${t.id}" data-to="${ESTADOS[idx + 1][0]}" style="margin-left:auto">${ESTADOS[idx + 1][1]}${icon('chevronRight')}</button>` : ''}
            </div>
        </div>`;
    }

    function pintarTareas() {
        setHtml(cuerpo, html`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:12px;flex-wrap:wrap">
                <p style="color:var(--ink-2)">Cualquier miembro puede crear tareas y moverlas de columna.</p>
                <button class="btn btn--primary" data-action="new-task">${icon('plus')}Nueva tarea</button></div>
            <div class="board">${ESTADOS.map(([k, l, c]) => {
                const tareas = datos.tasks.filter((t) => (t.status || 'pending') === k);
                return html`<section class="board__col"><h3><i style="background:${c}"></i>${l} <span class="n">${tareas.length}</span></h3>
                    ${tareas.length ? tareas.map(tareaHtml) : html`<p style="font-size:13.5px;color:var(--ink-3);padding:4px 6px">Nada por aquí.</p>`}</section>`;
            })}</div>`);
    }

    function taskDialog(tarea = null) {
        openDialog({
            title: tarea ? 'Editar tarea' : 'Nueva tarea',
            submitLabel: tarea ? 'Guardar' : 'Crear tarea',
            body: html`<label class="field"><span class="field__label">Título</span>
                    <input class="input" name="title" required maxlength="200" value="${tarea?.title || ''}" placeholder="Ej. Diagrama entidad-relación"></label>
                <label class="field"><span class="field__label">Detalle</span>
                    <textarea class="textarea" name="description" rows="3" maxlength="2000">${tarea?.description || ''}</textarea></label>
                <div class="row">
                    <label class="field"><span class="field__label">Responsable</span>
                        <select class="select" name="assigned_to"><option value="">Sin responsable</option>
                        ${datos.members.map((m) => html`<option value="${m.id}" ${tarea?.assigned_to_id === m.id ? raw('selected') : ''}>${m.name}${m.id === yo ? ' (tú)' : ''}</option>`)}</select></label>
                    <label class="field"><span class="field__label">Fecha de entrega</span>
                        <input class="input" type="date" name="due_date" value="${tarea?.due_date || ''}"></label>
                </div>`,
            onSubmit: async (form) => {
                const d = Object.fromEntries(new FormData(form));
                if (!d.title.trim()) throw new Error('Escribe qué hay que hacer.');
                d.assigned_to = d.assigned_to ? Number(d.assigned_to) : null;
                d.due_date = d.due_date || null;
                if (tarea) await api.put(`/api/groups/${gid}/tasks/${tarea.id}`, d);
                else await api.post(`/api/groups/${gid}/tasks`, d);
                toast(tarea ? 'Tarea actualizada' : 'Tarea creada');
                await recargar();
            },
        });
    }

    function pintarArchivos() {
        setHtml(cuerpo, html`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:12px;flex-wrap:wrap">
                <p style="color:var(--ink-2)">Sólo los miembros del grupo pueden ver estos archivos.</p>
                <button class="btn btn--primary" data-action="upload">${icon('upload')}Subir archivo</button></div>
            <section class="panel doc-list">${datos.resources.length ? datos.resources.map((r) => html`
                <article class="doc" style="--spine: var(--navy-3)" data-res="${r.id}">
                    <span class="doc__type">${typeLabel(r.extension)}</span>
                    <div class="doc__main"><span class="doc__title" style="cursor:default">${r.title}</span>
                        <div class="doc__meta"><span>${r.uploaded_by}</span><span>${timeAgo(r.uploaded_at)}</span>${r.file_size ? html`<span>${fileSize(r.file_size)}</span>` : ''}${scanBadge(r.scan_status)}</div>
                        ${r.description ? html`<p style="font-size:14px;color:var(--ink-2);margin-top:4px">${r.description}</p>` : ''}</div>
                    <div class="doc__actions">
                        <button class="icon-btn icon-btn--sm" data-res-act="ask" aria-label="Preguntar al asistente" title="Preguntar al asistente">${icon('bulb')}</button>
                        <button class="icon-btn icon-btn--sm" data-res-act="download" aria-label="Descargar" title="Descargar">${icon('download')}</button>
                        ${r.can_delete ? html`<button class="icon-btn icon-btn--sm" data-res-act="delete" aria-label="Eliminar" title="Eliminar">${icon('trash')}</button>` : ''}
                    </div>
                </article>`) : empty({ icon: 'folder', title: 'Sin archivos todavía', text: 'Sube avances, guías o entregas para que todo el grupo los tenga.' })}</section>`);
    }

    function pintarMiembros() {
        const soyLider = datos.group.is_owner;
        setHtml(cuerpo, html`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:12px;flex-wrap:wrap">
                <p style="color:var(--ink-2)">${soyLider ? 'Como líder puedes agregar a cualquier estudiante y retirar miembros.' : 'Puedes agregar a tus amigos al grupo.'}</p>
                <button class="btn btn--primary" data-action="invite">${icon('userPlus')}Agregar miembro</button></div>
            <section class="panel people">${datos.members.map((m) => html`<div class="person">
                ${avatar(m)}<div class="person__body"><button class="person__name" data-profile="${m.id}">${m.name}${m.id === yo ? ' (tú)' : ''}</button>
                <div class="person__meta">${m.is_owner ? 'Líder del grupo' : `Desde ${longDate(m.joined_at)}`}</div></div>
                <div class="person__actions">${m.is_owner ? html`<span class="status status--review">${icon('crown')}Líder</span>` : ''}
                ${soyLider && !m.is_owner ? html`<button class="btn btn--ghost btn--sm" data-remove="${m.id}" data-name="${m.name}">Retirar</button>` : ''}</div></div>`)}</section>`);
    }

    async function inviteDialog() {
        const soyLider = datos.group.is_owner;
        let amigos = [];
        try { amigos = (await api.get('/api/contacts')).contacts.filter((c) => !datos.members.some((m) => m.id === c.user.id)); } catch { /* */ }
        const dlg = openDialog({
            title: 'Agregar al grupo',
            description: soyLider ? 'Elige a tus amigos o busca a cualquier estudiante.' : 'Puedes agregar a tus amigos.',
            footer: false,
            body: html`${soyLider ? html`<div class="search" style="margin-bottom:10px">${icon('search')}<input class="input" data-slot="q" type="search" placeholder="Buscar estudiantes"></div>` : ''}
                <div class="people" data-slot="people">${amigos.length ? amigos.map((c) => html`<div class="person">${avatar(c.user)}
                    <div class="person__body"><div class="person__name">${c.name}</div><div class="person__meta">${c.user.career || ''}</div></div>
                    <button class="btn btn--secondary btn--sm" data-add="${c.user.id}">Agregar</button></div>`)
                    : html`<p style="color:var(--ink-3)">${soyLider ? 'Busca por nombre o correo.' : 'Todos tus amigos ya están en el grupo, o aún no tienes amigos agregados.'}</p>`}</div>`,
        });
        dlg.addEventListener('click', async (e) => {
            const b = e.target.closest('[data-add]');
            if (!b) return;
            try {
                const r = await api.post(`/api/groups/${gid}/invite`, { user_id: Number(b.dataset.add) });
                toast(r.message);
                b.disabled = true;
                b.textContent = 'Agregado';
                await recargar();
            } catch (err) { toast(err.message, 'error'); }
        });
        const q = dlg.querySelector('[data-slot="q"]');
        let t;
        q?.addEventListener('input', () => {
            clearTimeout(t);
            t = setTimeout(async () => {
                if (q.value.trim().length < 2) return;
                const { users } = await api.get(`/api/contacts/search?q=${encodeURIComponent(q.value.trim())}`);
                const fuera = users.filter((u) => !datos.members.some((m) => m.id === u.id));
                setHtml(dlg.querySelector('[data-slot="people"]'), fuera.length ? html`${fuera.map((u) => html`<div class="person">${avatar(u)}
                    <div class="person__body"><div class="person__name">${u.name}</div><div class="person__meta">${u.career || ''}</div></div>
                    <button class="btn btn--secondary btn--sm" data-add="${u.id}">Agregar</button></div>`)}` : html`<p style="color:var(--ink-3)">Sin resultados.</p>`);
            }, 300);
        });
    }

    function uploadDialog() {
        openDialog({
            title: 'Subir archivo al grupo',
            description: 'Pasa por el vigilante de seguridad antes de que el resto lo pueda descargar.',
            submitLabel: 'Subir',
            body: html`<label class="dropzone">${icon('upload')}<span><strong>Elige un archivo</strong></span>
                    <span class="dropzone__file" data-slot="fn"></span><input type="file" name="file" required></label>
                <label class="field" style="margin-top:14px"><span class="field__label">Título</span><input class="input" name="title" required maxlength="200"></label>
                <label class="field"><span class="field__label">Descripción</span><textarea class="textarea" name="description" rows="2" maxlength="2000"></textarea></label>`,
            onOpen: (dlg, form) => form.file.addEventListener('change', () => {
                const f = form.file.files[0];
                dlg.querySelector('[data-slot="fn"]').textContent = f ? `${f.name} (${fileSize(f.size)})` : '';
                if (f && !form.title.value) form.title.value = f.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ');
            }),
            onSubmit: async (form) => {
                if (!form.file.files.length) throw new Error('Elige un archivo.');
                if (!form.title.value.trim()) throw new Error('Ponle un título.');
                const r = await api.upload(`/api/groups/${gid}/resources`, new FormData(form));
                toast(r.message, 'success', 5000);
                await recargar();
            },
        });
    }

    on(root, 'click', '[data-tab]', (_e, b) => { tab = b.dataset.tab; pintar(); }, signal);
    on(root, 'click', '[data-action="new-task"]', () => taskDialog(), signal);
    on(root, 'click', '[data-action="upload"]', () => uploadDialog(), signal);
    on(root, 'click', '[data-action="invite"]', () => inviteDialog(), signal);
    on(root, 'click', '[data-profile]', (_e, b) => openUserProfile(Number(b.dataset.profile)), signal);
    on(root, 'click', '[data-move]', async (_e, b) => {
        try {
            await api.put(`/api/groups/${gid}/tasks/${b.dataset.move}`, { status: b.dataset.to });
            await recargar();
        } catch (err) { toast(err.message, 'error'); }
    }, signal);
    on(root, 'click', '[data-task-menu]', (_e, b) => {
        const tarea = datos.tasks.find((t) => t.id === Number(b.dataset.taskMenu));
        openMenu(b, [
            { label: 'Editar', icon: 'edit', onSelect: () => taskDialog(tarea) },
            { label: 'Eliminar', icon: 'trash', danger: true, onSelect: async () => {
                if (!await confirmDialog({ title: 'Eliminar tarea', text: `Se eliminará «${tarea.title}».`, confirmLabel: 'Eliminar' })) return;
                try { await api.del(`/api/groups/${gid}/tasks/${tarea.id}`); await recargar(); } catch (err) { toast(err.message, 'error'); }
            } },
        ]);
    }, signal);
    on(root, 'click', '[data-res-act]', async (_e, b) => {
        const r = datos.resources.find((x) => x.id === Number(b.closest('[data-res]').dataset.res));
        try {
            if (b.dataset.resAct === 'download') await api.download(r.download_url, r.original_filename);
            if (b.dataset.resAct === 'ask') askAboutDocument(r.doc_key, r.title);
            if (b.dataset.resAct === 'delete') {
                if (!await confirmDialog({ title: 'Eliminar archivo', text: `«${r.title}» se borrará para todo el grupo.`, confirmLabel: 'Eliminar' })) return;
                await api.del(`/api/groups/${gid}/resources/${r.id}`);
                toast('Archivo eliminado');
                await recargar();
            }
        } catch (err) { toast(err.message, 'error'); }
    }, signal);
    on(root, 'click', '[data-remove]', async (_e, b) => {
        if (!await confirmDialog({ title: 'Retirar del grupo', text: `${b.dataset.name} dejará de ver el chat, las tareas y los archivos.`, confirmLabel: 'Retirar' })) return;
        try { await api.del(`/api/groups/${gid}/members/${b.dataset.remove}`); await recargar(); } catch (err) { toast(err.message, 'error'); }
    }, signal);
    on(root, 'click', '[data-action="group-menu"]', (_e, b) => {
        const g = datos.group;
        const items = [];
        if (g.is_owner) items.push({ label: 'Editar grupo', icon: 'edit', onSelect: () => groupDialog(g, () => recargar()) });
        items.push({ label: 'Salir del grupo', icon: 'door', danger: !g.is_owner, onSelect: async () => {
            const texto = g.is_owner ? 'Eres líder: el liderazgo pasará al miembro más antiguo.' : 'Dejarás de ver el chat, las tareas y los archivos.';
            if (!await confirmDialog({ title: 'Salir del grupo', text: texto, confirmLabel: 'Salir' })) return;
            try { const r = await api.post(`/api/groups/${gid}/leave`); toast(r.message); go('/grupos'); } catch (err) { toast(err.message, 'error'); }
        } });
        if (g.is_owner) items.push({ label: 'Eliminar grupo', icon: 'trash', danger: true, onSelect: async () => {
            if (!await confirmDialog({ title: 'Eliminar grupo', text: 'Se borrarán el chat, las tareas y los archivos para todos. No se puede deshacer.', confirmLabel: 'Eliminar grupo' })) return;
            try { await api.del(`/api/groups/${gid}`); toast('Grupo eliminado'); go('/grupos'); } catch (err) { toast(err.message, 'error'); }
        } });
        openMenu(b, items);
    }, signal);

    // El chat abierto pide los mensajes nuevos en cada pulso (consulta muy ligera).
    store.on('pulse', () => { if (tab === 'chat') chat?.refresh(); }, signal);

    pintar();
}
