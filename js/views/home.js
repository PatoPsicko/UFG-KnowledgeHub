/**
 * Dashboard: lo de tu carrera. Recién subido y lo más descargado de la carrera
 * del perfil, tus grupos y tus guardados. Francis vive en su propio módulo.
 */

import { api } from '../core/api.js';
import { $, html, on, setHtml } from '../core/dom.js';
import { go } from '../core/router.js';
import { store } from '../core/store.js';
import { typeLabel } from '../data/categories.js';
import { countBadge, empty, skeletonRows } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { bindDocActions, docRow, uploadDialog } from './library.js';

function saludo() {
    const h = new Date().getHours();
    if (h < 12) return 'Buenos días';
    if (h < 19) return 'Buenas tardes';
    return 'Buenas noches';
}

export async function dashboardView(root, _params, signal) {
    const user = store.user;
    const nombre = user.name.split(' ')[0];
    let recursos = [];

    const carrera = user.career || '';
    const deCarrera = carrera ? `&career=${encodeURIComponent(carrera)}` : '';

    setHtml(root, html`<div class="page">
        <div class="greeting">
            <h1>${saludo()}, ${nombre}</h1>
            <p>${carrera ? html`Lo nuevo de <strong>${carrera}</strong>.` : 'Elige tu carrera en tu perfil y aquí verás el material que te sirve.'}</p>
        </div>
        ${carrera ? '' : html`<a class="career-cta" href="#/perfil">${icon('user')}<span><strong>Indica tu carrera</strong><span>Así el dashboard te recomienda material de tus materias y tus documentos la llevan.</span></span>${icon('chevronRight')}</a>`}
        <form class="home__search" data-slot="search">
            <div class="search">${icon('search')}<input class="input" name="q" type="search" placeholder="¿Qué necesitas estudiar hoy?" aria-label="Buscar en la biblioteca"></div>
        </form>
        <div class="stats-line" data-slot="stats"></div>
        <div class="shortcuts">
            <button class="shortcut" data-action="upload"><span class="shortcut__icon">${icon('upload')}</span><span><strong>Subir documento</strong><span>${carrera ? 'Para tu carrera' : 'Comparte con la UFG'}</span></span></button>
            <a class="shortcut shortcut--orange" href="#/francis"><span class="shortcut__icon">${icon('robot')}</span><span><strong>Preguntar a Francis</strong><span>Responde citando documentos</span></span></a>
            <a class="shortcut" href="#/grupos"><span class="shortcut__icon">${icon('users')}</span><span><strong>Grupos de trabajo</strong><span>Tareas, archivos y chat</span></span></a>
        </div>
        <div class="split split--even">
            <section class="panel">
                <div class="panel__head"><h2>Recién subido${carrera ? ' en tu carrera' : ''}</h2><a class="btn btn--ghost btn--sm" href="#/biblioteca${carrera ? '?scope=career' : ''}">Ver todo</a></div>
                <div class="doc-list" data-slot="recent">${skeletonRows(4)}</div>
            </section>
            <section class="panel">
                <div class="panel__head"><h2>${carrera ? 'Lo más usado en tu carrera' : 'Lo más descargado'}</h2></div>
                <div class="doc-list" data-slot="popular">${skeletonRows(4)}</div>
            </section>
        </div>
        <div class="split">
            <section class="panel"><div class="panel__head"><h3>Tus grupos</h3><a class="btn btn--ghost btn--sm" href="#/grupos">Todos</a></div>
                <div class="mini-list" data-slot="groups"></div></section>
            <section class="panel"><div class="panel__head"><h3>Tus guardados</h3><a class="btn btn--ghost btn--sm" href="#/biblioteca?scope=saved">Ver todos</a></div>
                <div class="mini-list" data-slot="convs"></div></section>
        </div>
    </div>`);

    $('[data-slot="search"]', root).addEventListener('submit', (e) => {
        e.preventDefault();
        const q = e.target.q.value.trim();
        go(`/biblioteca${q ? `?q=${encodeURIComponent(q)}` : ''}`);
    }, { signal });

    const vacio = { icon: 'library', title: 'Todavía no hay documentos', text: carrera ? 'Sé el primero en compartir material de tu carrera.' : 'Sube tus apuntes y ayuda a tu facultad.' };
    async function cargarLista(slot, orden) {
        try {
            const datos = await api.get(`/api/resources?limit=5&sort=${orden}${deCarrera}`);
            recursos = [...recursos.filter((r) => !datos.resources.some((d) => d.id === r.id)), ...datos.resources];
            setHtml($(`[data-slot="${slot}"]`, root), datos.resources.length ? html`${datos.resources.map(docRow)}` : empty(vacio));
        } catch (err) {
            setHtml($(`[data-slot="${slot}"]`, root), empty({ icon: 'alert', title: 'No se pudo cargar', text: err.message }));
        }
    }
    const cargarRecientes = () => Promise.all([cargarLista('recent', 'recent'), cargarLista('popular', 'popular')]);

    async function cargarResumen() {
        try {
            const [stats, grupos, convs] = await Promise.all([
                api.get('/api/user/stats'), api.get('/api/groups'), api.get('/api/resources?scope=saved&limit=4'),
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
            setHtml($('[data-slot="convs"]', root), convs.resources.length ? html`${convs.resources.map((r) => html`
                <a class="mini-item" href="#/biblioteca?scope=saved"><span class="file-icon file-icon--sm" data-ext="${r.extension}">${typeLabel(r.extension)}</span>
                    <span style="min-width:0;flex:1"><span class="mini-item__title">${r.title}</span>
                    <span class="mini-item__meta" style="display:block">${r.category}</span></span></a>`)}`
                : empty({ icon: 'bookmark', title: 'Nada guardado aún', text: 'Usa el marcador de un documento para tenerlo a mano aquí.' }));
        } catch { /* el resumen es secundario */ }
    }

    bindDocActions(root, (id) => recursos.find((r) => r.id === id), signal, cargarRecientes);
    on(root, 'click', '[data-action="upload"]', () => uploadDialog(null, cargarRecientes), signal);
    store.on('pulse', ({ pulse, previo }) => {
        if (pulse.groups_unread_total !== previo?.groups_unread_total) cargarResumen();
    }, signal);

    cargarRecientes();
    cargarResumen();
}
