/** Inicio: el asistente ocupa la columna derecha (donde estaba el chat global). */

import { api } from '../core/api.js';
import { $, html, on, setHtml, timeAgo } from '../core/dom.js';
import { go } from '../core/router.js';
import { store } from '../core/store.js';
import { avatar, countBadge, empty, skeletonRows } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { mountAssistant } from './assistant.js';
import { bindDocActions, docRow, uploadDialog } from './library.js';

function saludo() {
    const h = new Date().getHours();
    if (h < 12) return 'Buenos días';
    if (h < 19) return 'Buenas tardes';
    return 'Buenas noches';
}

export async function homeView(root, _params, signal) {
    const user = store.user;
    const nombre = user.name.split(' ')[0];
    let recursos = [];

    setHtml(root, html`<div class="page page--wide">
        <div class="home">
            <div>
                <div class="greeting">
                    <h1>${saludo()}, ${nombre}</h1>
                    <p>Busca material de tus materias o pregúntale al asistente de la derecha.</p>
                </div>
                <form class="home__search" data-slot="search">
                    <div class="search">${icon('search')}<input class="input" name="q" type="search" placeholder="¿Qué necesitas estudiar hoy?" aria-label="Buscar en la biblioteca"></div>
                </form>
                <div class="stats-line" data-slot="stats"></div>
                <div class="shortcuts">
                    <button class="shortcut" data-action="upload"><span class="shortcut__icon">${icon('upload')}</span><span><strong>Subir documento</strong><span>Comparte con tu facultad</span></span></button>
                    <a class="shortcut shortcut--orange" href="#/grupos"><span class="shortcut__icon">${icon('users')}</span><span><strong>Grupos de trabajo</strong><span>Tareas, archivos y chat</span></span></a>
                    <a class="shortcut" href="#/mensajes/global"><span class="shortcut__icon">${icon('globe')}</span><span><strong>Chat global UFG</strong><span>Ahora vive en Mensajes</span></span></a>
                </div>
                <section class="panel">
                    <div class="panel__head"><h2>Recién compartido</h2><a class="btn btn--ghost btn--sm" href="#/biblioteca">Ver la biblioteca</a></div>
                    <div class="doc-list" data-slot="recent">${skeletonRows(4)}</div>
                </section>
                <div class="split">
                    <section class="panel"><div class="panel__head"><h3>Tus grupos</h3><a class="btn btn--ghost btn--sm" href="#/grupos">Todos</a></div>
                        <div class="mini-list" data-slot="groups"></div></section>
                    <section class="panel"><div class="panel__head"><h3>Mensajes recientes</h3><a class="btn btn--ghost btn--sm" href="#/mensajes">Abrir</a></div>
                        <div class="mini-list" data-slot="convs"></div></section>
                </div>
            </div>
            <div class="home__desk" data-slot="desk"></div>
        </div>
    </div>`);

    mountAssistant($('[data-slot="desk"]', root), { compact: true, signal });

    $('[data-slot="search"]', root).addEventListener('submit', (e) => {
        e.preventDefault();
        const q = e.target.q.value.trim();
        go(`/biblioteca${q ? `?q=${encodeURIComponent(q)}` : ''}`);
    }, { signal });

    async function cargarRecientes() {
        try {
            const datos = await api.get('/api/resources?limit=6&sort=recent');
            recursos = datos.resources;
            setHtml($('[data-slot="recent"]', root), recursos.length ? html`${recursos.map(docRow)}`
                : empty({ icon: 'library', title: 'Todavía no hay documentos', text: 'Sube tus apuntes y ayuda a tu facultad.' }));
        } catch (err) {
            setHtml($('[data-slot="recent"]', root), empty({ icon: 'alert', title: 'No se pudo cargar', text: err.message }));
        }
    }

    async function cargarResumen() {
        try {
            const [stats, grupos, convs] = await Promise.all([
                api.get('/api/user/stats'), api.get('/api/groups'), api.get('/api/conversations'),
            ]);
            setHtml($('[data-slot="stats"]', root), html`
                <span><strong>${stats.library_size}</strong>documentos en la biblioteca</span>
                <span><strong>${stats.resources_count}</strong>${stats.resources_count === 1 ? 'aporte tuyo' : 'aportes tuyos'}</span>
                <span><strong>${stats.downloads_received}</strong>descargas de tus aportes</span>
                <span><strong>${stats.registered_users}</strong>estudiantes registrados</span>`);
            setHtml($('[data-slot="groups"]', root), grupos.groups.length ? html`${grupos.groups.slice(0, 4).map((g) => html`
                <a class="mini-item" href="#/grupos/${g.id}"><span class="group-card__badge" style="width:34px;height:34px;font-size:14px;border-radius:9px">${g.name.slice(0, 1).toUpperCase()}</span>
                    <span style="min-width:0"><span class="mini-item__title">${g.name}</span><span class="mini-item__meta" style="display:block">${g.open_tasks} ${g.open_tasks === 1 ? 'tarea abierta' : 'tareas abiertas'}</span></span>
                    ${countBadge(g.unread)}</a>`)}`
                : empty({ icon: 'users', title: 'Sin grupos aún', text: 'Crea uno para organizar un proyecto con tus compañeros.' }));
            setHtml($('[data-slot="convs"]', root), convs.conversations.length ? html`${convs.conversations.slice(0, 4).map((c) => html`
                <a class="mini-item" href="#/mensajes/dm/${c.user.id}">${avatar(c.user, 'sm')}
                    <span style="min-width:0;flex:1"><span class="mini-item__title">${c.user.name}</span>
                    <span class="mini-item__meta" style="display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${c.last_message ? c.last_message.message : 'Sin mensajes todavía'}</span></span>
                    ${c.unread ? countBadge(c.unread) : html`<span class="mini-item__meta">${c.last_message ? timeAgo(c.last_message.timestamp) : ''}</span>`}</a>`)}`
                : empty({ icon: 'chat', title: 'Sin conversaciones', text: 'Agrega amigos en Mensajes para escribirles.' }));
        } catch { /* el resumen es secundario */ }
    }

    bindDocActions(root, (id) => recursos.find((r) => r.id === id), signal, cargarRecientes);
    on(root, 'click', '[data-action="upload"]', () => uploadDialog(null, cargarRecientes), signal);
    store.on('pulse', ({ pulse, previo }) => {
        if (pulse.dm_unread_total !== previo?.dm_unread_total || pulse.groups_unread_total !== previo?.groups_unread_total) cargarResumen();
    }, signal);

    cargarRecientes();
    cargarResumen();
}
