/**
 * Marco de la aplicación: barra lateral, notificaciones y, en el celular,
 * barra superior con el menú y barra inferior con las cinco secciones.
 */

import { api } from '../core/api.js';
import { $, html, on, setHtml, timeAgo } from '../core/dom.js';
import { prefs } from '../core/prefs.js';
import { go } from '../core/router.js';
import { store } from '../core/store.js';
import { avatar, countBadge, empty } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { toast } from '../ui/overlay.js';

const NAV = [
    { path: '/inicio', label: 'Inicio', icon: 'home' },
    { path: '/asistente', label: 'Asistente', icon: 'bulb' },
    { path: '/biblioteca', label: 'Biblioteca', icon: 'library' },
    { path: '/grupos', label: 'Grupos', icon: 'users', badge: (p) => p.groups_unread_total },
    { path: '/anotaciones', label: 'Mi espacio', icon: 'note' },
];

/** Barra inferior del celular: las mismas secciones, al alcance del pulgar. */
function tabbarHtml(pulse, activePath) {
    return html`${NAV.map((it) => html`<a class="tabbar__item" href="#${it.path}" data-path="${it.path}"
        ${activePath.startsWith(it.path) ? html`aria-current="page"` : ''}>${icon(it.icon)}<span>${it.label}</span>${countBadge(it.badge ? it.badge(pulse) : 0)}</a>`)}`;
}

const NOTIF_ICON = {
    contact_request: ['userPlus', ''], contact_accepted: ['userCheck', 'ok'], message: ['chat', ''],
    group_invite: ['users', ''], group_task: ['tasks', ''], group_owner: ['crown', 'ok'],
    group_deleted: ['users', 'warn'], group_removed: ['users', 'warn'],
    scan_result: ['shield', ''], security_alert: ['shield', 'bad'],
};

function notifTarget(n) {
    switch (n.type) {
    case 'contact_request':
    case 'contact_accepted':
    case 'message': return null;
    case 'group_invite':
    case 'group_task':
    case 'group_owner': return n.related_id ? `/grupos/${n.related_id}` : '/grupos';
    case 'group_deleted':
    case 'group_removed': return '/grupos';
    case 'scan_result': return '/biblioteca?scope=mine';
    case 'security_alert': return '/seguridad';
    default: return null;
    }
}

function navHtml(user, pulse, activePath) {
    const items = [...NAV];
    return html`
        ${items.map((it) => html`<a class="nav__item" href="#${it.path}" data-path="${it.path}"
            ${activePath.startsWith(it.path) ? html`aria-current="page"` : ''}>${icon(it.icon)}<span>${it.label}</span>${countBadge(it.badge ? it.badge(pulse) : 0)}</a>`)}
        ${user.is_admin ? html`<div class="nav__group">Administración</div>
            <a class="nav__item" href="#/seguridad" data-path="/seguridad" ${activePath.startsWith('/seguridad') ? html`aria-current="page"` : ''}>${icon('shield')}<span>Seguridad</span></a>` : ''}`;
}

let shellController = null;

export function renderShell(root, { onLogout }) {
    // Al volver a entrar tras cerrar sesión se descartan los escuchadores anteriores.
    shellController?.abort();
    shellController = new AbortController();
    const { signal } = shellController;
    const user = store.user;
    setHtml(root, html`<div class="app" id="app">
        <aside class="sidebar" aria-label="Navegación principal">
            <div class="sidebar__top">
                <a class="sidebar__brand" href="#/inicio" aria-label="Ir al inicio">
                    <img src="img/logo_hub.png" alt="UFG Knowledge Hub">
                    <span class="sidebar__product">Knowledge Hub</span>
                </a>
                <button class="icon-btn icon-btn--sm sidebar__fold" data-action="fold" aria-label="Plegar menú" title="Plegar menú">${icon('foldLeft')}</button>
            </div>
            <nav class="nav" id="nav">${navHtml(user, store.pulse, '/inicio')}</nav>
            <div class="sidebar__footer">
                <div class="sidebar__actions">
                    <button class="theme-switch" type="button" data-action="theme" role="switch" aria-checked="false" aria-label="Modo oscuro">
                        <span class="theme-switch__track"><span class="theme-switch__thumb">${icon('sun')}</span></span><span>Modo oscuro</span></button>
                    <div class="bell-wrap">
                        <button class="icon-btn" data-action="toggle-notifs" data-bell aria-label="Notificaciones" aria-haspopup="true">${icon('bell')}</button>
                    </div>
                </div>
                <button class="nav__item" data-action="install" type="button" hidden>${icon('download')}<span>Instalar app</span></button>
                <a class="me" href="#/perfil" id="me">${avatar({ ...user, online: true })}
                    <span style="min-width:0"><span class="me__name">${user.name}</span><br><span class="me__meta">${user.career || 'Completa tu perfil'}</span></span></a>
                <button class="nav__item" data-action="logout" type="button">${icon('logout')}<span>Cerrar sesión</span></button>
            </div>
        </aside>
        <div class="drawer-backdrop" data-action="close-nav"></div>
        <div class="main">
            <header class="topbar" id="topbar">
                <button class="icon-btn topbar__menu" data-action="open-nav" aria-label="Abrir menú">${icon('menu')}</button>
                <a class="topbar__brand" href="#/inicio" aria-label="Ir al inicio"><img src="img/logo_hub.png" alt="UFG Knowledge Hub"></a>
                <button class="icon-btn topbar__bell" data-action="toggle-notifs" data-bell aria-label="Notificaciones" aria-haspopup="true">${icon('bell')}</button>
            </header>
            <div id="view"></div>
        </div>
        <nav class="tabbar" id="tabbar" aria-label="Secciones">${tabbarHtml(store.pulse, '/inicio')}</nav>
        <div id="notif-slot"></div>
    </div>`);

    const app = $('#app', root);

    // Barra superior con borde al desplazarse.
    const topbar = $('#topbar', root);
    window.addEventListener('scroll', () => topbar.classList.toggle('is-scrolled', window.scrollY > 4), { passive: true, signal });

    on(app, 'click', '[data-action="logout"]', () => onLogout());
    const pintarTema = () => {
        const oscuro = prefs.isDark();
        const sw = $('[data-action="theme"]', root);
        sw.setAttribute('aria-checked', String(oscuro));
        setHtml(sw.querySelector('.theme-switch__thumb'), icon(oscuro ? 'moon' : 'sun'));
    };
    on(app, 'click', '[data-action="theme"]', async () => {
        await prefs.set({ theme: prefs.isDark() ? 'light' : 'dark' });
        pintarTema();
    });
    store.on('prefs', pintarTema, signal);
    pintarTema();

    // «Instalar app» aparece sólo cuando el navegador lo permite (Chrome, Edge).
    const instalar = $('[data-action="install"]', root);
    const pintarInstalar = () => { instalar.hidden = !store.installPrompt; };
    store.on('install', pintarInstalar, signal);
    pintarInstalar();
    on(app, 'click', '[data-action="install"]', async () => {
        const aviso = store.installPrompt;
        if (!aviso) return;
        aviso.prompt();
        await aviso.userChoice.catch(() => null);
        store.installPrompt = null;
        pintarInstalar();
    });
    on(app, 'click', '[data-action="open-nav"]', () => app.classList.add('nav-open'));
    on(app, 'click', '[data-action="close-nav"]', () => app.classList.remove('nav-open'));
    on(app, 'click', '.nav__item[href], .me', () => app.classList.remove('nav-open'));
    // El menú del celular también se cierra al cambiar de sección o con Escape.
    window.addEventListener('hashchange', () => app.classList.remove('nav-open'), { signal });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') app.classList.remove('nav-open'); }, { signal });

    const pintarPliegue = () => {
        const plegado = app.classList.contains('is-folded');
        const b = $('[data-action="fold"]', root);
        b.setAttribute('aria-label', plegado ? 'Desplegar menú' : 'Plegar menú');
        b.title = b.getAttribute('aria-label');
        setHtml(b, icon(plegado ? 'foldRight' : 'foldLeft'));
    };
    try { if (localStorage.getItem('sidebar') === 'folded') app.classList.add('is-folded'); } catch { /* sin almacenamiento */ }
    on(app, 'click', '[data-action="fold"]', () => {
        app.classList.toggle('is-folded');
        try { localStorage.setItem('sidebar', app.classList.contains('is-folded') ? 'folded' : 'open'); } catch { /* */ }
        pintarPliegue();
    });
    pintarPliegue();

    // Notificaciones
    const slot = $('#notif-slot', root);
    let abierto = false;
    const cerrarNotifs = () => { abierto = false; setHtml(slot, ''); };
    async function abrirNotifs() {
        abierto = true;
        setHtml(slot, html`<div class="notif-panel" role="dialog" aria-label="Notificaciones"><div class="loading"><div class="spinner"></div></div></div>`);
        try {
            const { notifications } = await api.get('/api/notifications?limit=25');
            if (!abierto) return;
            setHtml(slot, html`<div class="notif-panel" role="dialog" aria-label="Notificaciones">
                <div class="notif-panel__head"><h3>Notificaciones</h3>
                    ${notifications.some((n) => !n.read) ? html`<button class="btn btn--ghost btn--sm" data-action="read-all">Marcar todo como leído</button>` : ''}</div>
                <div class="notif-list">${notifications.length ? notifications.map((n) => {
                    const [ic, tono] = NOTIF_ICON[n.type] || ['bell', ''];
                    return html`<button class="notif ${n.read ? '' : 'is-unread'}" data-id="${n.id}" data-target="${notifTarget(n) || ''}">
                        <span class="notif__icon ${tono ? `notif__icon--${tono}` : ''}">${icon(ic)}</span>
                        <span><span class="notif__title">${n.title}</span><span class="notif__msg" style="display:block">${n.message}</span>
                        <span class="notif__time" style="display:block">${timeAgo(n.created_at)}</span></span></button>`;
                }) : empty({ icon: 'bell', title: 'Todo al día', text: 'Aquí verás solicitudes de amistad, invitaciones a grupos y avisos de tus archivos.' })}</div>
            </div>`);
        } catch (err) {
            toast(err.message, 'error');
            cerrarNotifs();
        }
    }
    on(app, 'click', '[data-action="toggle-notifs"]', (e) => {
        e.stopPropagation();
        if (abierto) cerrarNotifs(); else abrirNotifs();
    });
    on(slot, 'click', '[data-action="read-all"]', async (e) => {
        e.stopPropagation();
        await api.put('/api/notifications/read-all');
        store.setPulse({ ...store.pulse, notifications_unread: 0 });
        abrirNotifs();
    });
    on(slot, 'click', '.notif', async (_e, btn) => {
        const destino = btn.dataset.target;
        if (btn.classList.contains('is-unread')) {
            api.put(`/api/notifications/${btn.dataset.id}/read`).catch(() => {});
            store.setPulse({ ...store.pulse, notifications_unread: Math.max(0, store.pulse.notifications_unread - 1) });
        }
        cerrarNotifs();
        if (destino) go(destino);
    });
    document.addEventListener('click', (e) => {
        if (abierto && !e.target.closest('.notif-panel') && !e.target.closest('[data-bell]')) cerrarNotifs();
    }, { signal });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && abierto) cerrarNotifs(); }, { signal });

    // Contadores al ritmo del pulso.
    store.on('pulse', ({ pulse, previo }) => {
        const activo = $('#nav [aria-current="page"]', root)?.dataset.path || '';
        setHtml($('#nav', root), navHtml(store.user, pulse, activo));
        setHtml($('#tabbar', root), tabbarHtml(pulse, activo));
        root.querySelectorAll('[data-bell]').forEach((bell) => {
            bell.querySelector('.badge-dot')?.remove();
            if (pulse.notifications_unread > 0) {
                bell.insertAdjacentHTML('beforeend', `<span class="badge-dot">${Math.min(pulse.notifications_unread, 99)}</span>`);
            }
        });
        if (previo && pulse.notifications_unread > previo.notifications_unread && previo.server_time) {
            toast('Tienes una notificación nueva', 'info', 2600);
        }
        actualizarTitulo(pulse);
    }, signal);

    store.on('user', (u) => {
        setHtml($('#me', root), html`${avatar({ ...u, online: true })}
            <span style="min-width:0"><span class="me__name">${u.name}</span><br><span class="me__meta">${u.career || 'Completa tu perfil'}</span></span>`);
    }, signal);
}

function actualizarTitulo(pulse) {
    const pendientes = (pulse.dm_unread_total || 0) + (pulse.notifications_unread || 0);
    document.title = pendientes ? `(${pendientes}) UFG Knowledge Hub` : 'UFG Knowledge Hub';
}

export function setActiveNav(path) {
    document.querySelectorAll('#nav .nav__item[data-path], #tabbar .tabbar__item').forEach((a) => {
        if (path.startsWith(a.dataset.path)) a.setAttribute('aria-current', 'page');
        else a.removeAttribute('aria-current');
    });
}
