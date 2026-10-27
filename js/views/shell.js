/**
 * Marco de la aplicación. Inicio es el librero (views/shelf.js): cada libro es
 * un módulo. Dentro de un módulo la barra superior tiene «atrás» y la casita
 * para volver al librero; en el celular, además, la barra inferior.
 */

import { api } from '../core/api.js';
import { $, html, on, raw, setHtml, timeAgo } from '../core/dom.js';
import { prefs } from '../core/prefs.js';
import { go } from '../core/router.js';
import { store } from '../core/store.js';
import { SECTIONS, sectionTitle } from '../data/sections.js';
import { avatar, countBadge, empty } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { openDialog, openMenu, toast } from '../ui/overlay.js';

/** Barra inferior del celular: los cinco módulos, al alcance del pulgar. */
function tabbarHtml(pulse, activePath) {
    return html`${SECTIONS.map((it) => html`<a class="tabbar__item" href="#${it.path}" data-path="${it.path}"
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

let shellController = null;

export function renderShell(root, { onLogout }) {
    // Al volver a entrar tras cerrar sesión se descartan los escuchadores anteriores.
    shellController?.abort();
    shellController = new AbortController();
    const { signal } = shellController;
    const user = store.user;
    setHtml(root, html`<div class="app" id="app" data-home="true">
        <div class="main">
            <header class="topbar" id="topbar">
                <div class="topbar__nav">
                    <button class="icon-btn" data-action="back" type="button" aria-label="Atrás" title="Atrás">${icon('arrowLeft')}</button>
                    <a class="icon-btn" href="#/inicio" aria-label="Volver al librero" title="Volver al librero">${icon('home')}</a>
                </div>
                <a class="topbar__brand" href="#/inicio" aria-label="Volver al librero"><img src="img/logo_hub.png" alt="UFG Knowledge Hub"></a>
                <h1 class="topbar__title" id="topbar-title"></h1>
                <div class="topbar__actions">
                    <button class="topbar__search only-desktop" data-action="palette" type="button" title="Ir a… (Ctrl+K)">${icon('search')}<span>Ir a…</span><kbd>Ctrl K</kbd></button>
                    <button class="icon-btn only-desktop" data-action="share" type="button" aria-label="Compartir la app (QR)" title="Compartir la app (QR)">${icon('globe')}</button>
                    <button class="icon-btn only-desktop" data-action="install" type="button" aria-label="Instalar app" title="Instalar app" hidden>${icon('download')}</button>
                    <button class="icon-btn" data-action="theme" type="button" role="switch" aria-checked="false" aria-label="Modo oscuro" title="Modo oscuro">${icon('moon')}</button>
                    <button class="icon-btn" data-action="toggle-notifs" data-bell aria-label="Notificaciones" aria-haspopup="true" title="Notificaciones">${icon('bell')}</button>
                    <button class="topbar__me" data-action="me" type="button" id="me" aria-haspopup="menu" aria-label="Tu cuenta">${avatar({ ...user, online: true }, 'sm')}</button>
                </div>
            </header>
            <div id="view"></div>
        </div>
        <nav class="tabbar" id="tabbar" aria-label="Módulos">${tabbarHtml(store.pulse, '/inicio')}</nav>
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
        sw.title = oscuro ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
        setHtml(sw, icon(oscuro ? 'sun' : 'moon'));
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
    // «Compartir»: link de la app y su QR para que entren escaneándolo.
    on(app, 'click', '[data-action="share"]', async () => {
        try {
            const { url, svg, fixed } = await api.get('/api/share');
            const dlg = openDialog({
                title: 'Comparte la app',
                description: fixed ? 'Este link es fijo: sirve hoy y la próxima vez.' : 'Este link cambia cada vez que se enciende el servidor.',
                body: html`<div class="share-qr">${raw(svg)}</div><p class="share-url">${url}</p>`,
                submitLabel: 'Copiar link',
                cancelLabel: 'Cerrar',
                onSubmit: async () => {
                    try { await navigator.clipboard.writeText(url); toast('Link copiado'); } catch { toast(url, 'info', 8000); }
                },
            });
            dlg.querySelector('.share-qr svg')?.setAttribute('role', 'img');
        } catch (err) { toast(err.message, 'error'); }
    });

    // Menú de la cuenta (avatar): perfil, seguridad para admins y salir.
    on(app, 'click', '[data-action="me"]', (_e, b) => {
        openMenu(b, [
            { label: 'Mi perfil', icon: 'user', onSelect: () => go('/perfil') },
            ...(store.user.is_admin ? [{ label: 'Seguridad', icon: 'shield', onSelect: () => go('/seguridad') }] : []),
            { label: 'Cerrar sesión', icon: 'logout', danger: true, onSelect: () => onLogout() },
        ]);
    });

    // Atrás: vuelve por donde se vino dentro de la app; si se entró directo a un
    // módulo (link compartido), lleva al librero.
    const recorrido = [];
    navegacion = (path) => {
        if (recorrido.length > 1 && recorrido[recorrido.length - 2] === path) recorrido.pop();
        else if (recorrido[recorrido.length - 1] !== path) recorrido.push(path);
        const enCasa = path === '/inicio';
        app.dataset.home = String(enCasa);
        document.documentElement.classList.toggle('en-librero', enCasa);
        setHtml($('#topbar-title', root), sectionTitle(path));
    };
    on(app, 'click', '[data-action="back"]', () => {
        if (recorrido.length > 1) history.back(); else go('/inicio');
    });

    // Paleta «Ir a…»: salta a una sección o busca en la biblioteca escribiendo.
    function abrirPaleta() {
        if (document.querySelector('.palette')) return;
        const destinos = [{ path: '/inicio', label: 'Librero (inicio)', icon: 'home' }, ...SECTIONS, ...(store.user.is_admin ? [{ path: '/seguridad', label: 'Seguridad', icon: 'shield' }] : []),
            { path: '/perfil', label: 'Mi perfil', icon: 'user' }];
        const capa = document.createElement('div');
        capa.className = 'palette';
        setHtml(capa, html`<div class="palette__box" role="dialog" aria-label="Ir a">
            <div class="palette__input">${icon('search')}<input type="text" placeholder="Ir a una sección o buscar documentos…" aria-label="Ir a"></div>
            <div class="palette__list" role="listbox"></div></div>`);
        document.body.appendChild(capa);
        const input = capa.querySelector('input');
        const lista = capa.querySelector('.palette__list');
        let sel = 0;
        let items = [];
        const pintar = () => {
            const q = input.value.trim().toLowerCase();
            items = destinos.filter((d) => !q || d.label.toLowerCase().includes(q)).map((d) => ({ ...d, go: d.path }));
            if (q) items.push({ label: `Buscar «${input.value.trim()}» en la biblioteca`, icon: 'library', go: `/biblioteca?q=${encodeURIComponent(input.value.trim())}` });
            sel = Math.min(sel, items.length - 1);
            setHtml(lista, html`${items.map((it, i) => html`<button type="button" class="palette__item" role="option" aria-selected="${i === sel}" data-i="${i}">${icon(it.icon)}<span>${it.label}</span></button>`)}`);
        };
        const cerrar = () => capa.remove();
        const ir = (i) => { const it = items[i]; cerrar(); if (it) go(it.go); };
        input.addEventListener('input', () => { sel = 0; pintar(); });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') { sel = (sel + 1) % items.length; pintar(); e.preventDefault(); }
            else if (e.key === 'ArrowUp') { sel = (sel - 1 + items.length) % items.length; pintar(); e.preventDefault(); }
            else if (e.key === 'Enter') ir(sel);
            else if (e.key === 'Escape') cerrar();
        });
        capa.addEventListener('click', (e) => {
            const b = e.target.closest('.palette__item');
            if (b) ir(Number(b.dataset.i));
            else if (!e.target.closest('.palette__box')) cerrar();
        });
        pintar();
        input.focus();
    }
    on(app, 'click', '[data-action="palette"]', abrirPaleta);
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); abrirPaleta(); }
    }, { signal });

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
        const activo = $('#tabbar [aria-current="page"]', root)?.dataset.path || '';
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
        setHtml($('#me', root), avatar({ ...u, online: true }, 'sm'));
    }, signal);
}

function actualizarTitulo(pulse) {
    const pendientes = (pulse.dm_unread_total || 0) + (pulse.notifications_unread || 0);
    document.title = pendientes ? `(${pendientes}) UFG Knowledge Hub` : 'UFG Knowledge Hub';
}

let navegacion = () => {};

export function setActiveNav(path) {
    navegacion(path);
    document.querySelectorAll('#tabbar .tabbar__item').forEach((a) => {
        if (path.startsWith(a.dataset.path)) a.setAttribute('aria-current', 'page');
        else a.removeAttribute('aria-current');
    });
}
