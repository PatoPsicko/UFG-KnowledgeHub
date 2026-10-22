/**
 * Mensajes: el chat global UFG (fijado arriba), las conversaciones privadas
 * con amigos y la gestión de amistades.
 *
 *   #/mensajes            bandeja
 *   #/mensajes/global     chat global
 *   #/mensajes/dm/:id     conversación con un amigo
 *   #/mensajes/amigos     solicitudes, búsqueda y lista de amigos
 */

import { api } from '../core/api.js';
import { $, debounce, html, on, setHtml, timeAgo } from '../core/dom.js';
import { go } from '../core/router.js';
import { store } from '../core/store.js';
import * as pulse from '../core/pulse.js';
import { avatar, countBadge, empty } from '../ui/components.js';
import { mountChat } from '../ui/chatlog.js';
import { icon } from '../ui/icons.js';
import { toast } from '../ui/overlay.js';
import { friendAction, openUserProfile, relationButtons } from './people.js';

export async function messagesView(root, params, signal) {
    const modo = params.mode || (window.innerWidth > 980 ? 'global' : '');
    const contactId = params.id ? Number(params.id) : null;
    const tab = modo === 'amigos' ? 'amigos' : 'chats';
    const hayHilo = modo === 'global' || modo === 'dm';

    setHtml(root, html`<div class="page page--wide page--flush">
        <div class="messenger ${hayHilo ? 'has-thread' : ''}">
            <aside class="inbox">
                <div class="inbox__head">
                    <h1 style="font-size:22px">Mensajes</h1>
                    <div class="tabs" role="tablist">
                        <button class="tab" role="tab" aria-selected="${tab === 'chats'}" data-tab="chats">Conversaciones</button>
                        <button class="tab" role="tab" aria-selected="${tab === 'amigos'}" data-tab="amigos">Amigos <span data-slot="req-count"></span></button>
                    </div>
                </div>
                <div class="inbox__list" data-slot="list"><div class="loading"><div class="spinner"></div></div></div>
            </aside>
            <section class="conversation" data-slot="thread"></section>
        </div>
    </div>`);

    const lista = $('[data-slot="list"]', root);
    const hilo = $('[data-slot="thread"]', root);
    let conversaciones = [];
    let chat = null;

    on(root, 'click', '[data-tab]', (_e, b) => go(b.dataset.tab === 'amigos' ? '/mensajes/amigos' : '/mensajes'), signal);

    /* --- Bandeja ------------------------------------------------------------- */
    async function cargarBandeja() {
        try {
            conversaciones = (await api.get('/api/conversations')).conversations;
            if (tab === 'chats') pintarBandeja();
        } catch (err) {
            setHtml(lista, empty({ icon: 'alert', title: 'No se pudieron cargar tus conversaciones', text: err.message }));
        }
    }

    function pintarBandeja() {
        const p = store.pulse;
        setHtml(lista, html`
            <a class="thread-item ${p.global_unread ? 'is-unread' : ''}" href="#/mensajes/global" aria-current="${modo === 'global'}">
                <span class="thread-item__global">${icon('globe')}</span>
                <span class="thread-item__body"><span class="thread-item__top"><span class="thread-item__name">Chat global UFG</span>
                    <span class="thread-item__time">${p.online_count || 1} en línea</span></span>
                    <span class="thread-item__last" style="display:block">Toda la comunidad de la universidad</span></span>
                ${countBadge(p.global_unread)}
            </a>
            <div class="section-label">Amigos</div>
            ${conversaciones.length ? conversaciones.map((c) => {
                const unread = p.dm_unread?.[String(c.user.id)] ?? c.unread;
                const ultimo = c.last_message;
                const mio = ultimo && ultimo.sender_id === store.user.id;
                return html`<a class="thread-item ${unread ? 'is-unread' : ''}" href="#/mensajes/dm/${c.user.id}" aria-current="${modo === 'dm' && contactId === c.user.id}">
                    ${avatar({ ...c.user, online: store.isOnline(c.user.id) })}
                    <span class="thread-item__body"><span class="thread-item__top"><span class="thread-item__name">${c.user.name}</span>
                        <span class="thread-item__time">${ultimo ? timeAgo(ultimo.timestamp) : ''}</span></span>
                        <span class="thread-item__last" style="display:block">${ultimo ? `${mio ? 'Tú: ' : ''}${ultimo.message}` : 'Sin mensajes todavía'}</span></span>
                    ${countBadge(unread)}</a>`;
            }) : html`<div class="empty" style="padding:24px 16px">${icon('userPlus')}<p>Agrega amigos para escribirles por privado.</p>
                <a class="btn btn--secondary btn--sm" href="#/mensajes/amigos">Buscar compañeros</a></div>`}`);
    }

    /* --- Amigos -------------------------------------------------------------- */
    async function pintarAmigos(busqueda = '') {
        try {
            const [contactos, recibidas, enviadas, sugerencias, resultados] = await Promise.all([
                api.get('/api/contacts'), api.get('/api/contacts/requests'), api.get('/api/contacts/requests/sent'),
                api.get('/api/contacts/suggestions'),
                busqueda.length >= 2 ? api.get(`/api/contacts/search?q=${encodeURIComponent(busqueda)}`) : Promise.resolve({ users: null }),
            ]);
            const persona = (u, acciones, meta = u.career || '') => html`<div class="person">
                ${avatar(u)}<div class="person__body"><button class="person__name" data-profile="${u.id}">${u.name}</button>
                <div class="person__meta">${meta}</div></div><div class="person__actions">${acciones}</div></div>`;
            const buscador = $('[data-slot="search"]', lista);
            const valor = buscador ? buscador.value : busqueda;
            setHtml(lista, html`
                <div style="padding:12px 14px 4px"><div class="search">${icon('search')}
                    <input class="input" data-slot="search" type="search" value="${valor}" placeholder="Buscar por nombre, correo o carrera" aria-label="Buscar compañeros"></div></div>
                ${resultados.users ? html`<div class="section-label">Resultados</div>
                    ${resultados.users.length ? resultados.users.map((u) => persona(u, relationButtons(u))) : html`<p style="padding:4px 14px;color:var(--ink-3)">Nadie coincide con «${busqueda}».</p>`}` : ''}
                ${recibidas.requests.length ? html`<div class="section-label">Solicitudes recibidas</div>
                    ${recibidas.requests.map((r) => persona(r.user, html`
                        <button class="btn btn--primary btn--sm" data-friend="accept" data-request="${r.id}" data-name="${r.user_name}">Aceptar</button>
                        <button class="icon-btn icon-btn--sm" data-friend="reject" data-request="${r.id}" data-name="${r.user_name}" aria-label="Rechazar">${icon('x')}</button>`, timeAgo(r.created_at)))}` : ''}
                <div class="section-label">Tus amigos (${contactos.contacts.length})</div>
                ${contactos.contacts.length ? contactos.contacts.map((c) => persona(c.user, html`
                    <a class="icon-btn icon-btn--sm" href="#/mensajes/dm/${c.user.id}" aria-label="Escribir a ${c.name}">${icon('chat')}</a>
                    <button class="icon-btn icon-btn--sm" data-friend="remove" data-user="${c.user.id}" data-name="${c.name}" aria-label="Eliminar amigo">${icon('userMinus')}</button>`,
                    c.user.online ? 'En línea' : (c.user.career || ''))) : html`<p style="padding:4px 14px 12px;color:var(--ink-3)">Busca a tus compañeros arriba para agregarlos.</p>`}
                ${enviadas.requests.length ? html`<div class="section-label">Solicitudes enviadas</div>
                    ${enviadas.requests.map((r) => persona(r.user, html`<button class="btn btn--ghost btn--sm" data-friend="cancel" data-request="${r.id}" data-name="${r.user_name}">Cancelar</button>`, 'Esperando respuesta'))}` : ''}
                ${sugerencias.users.length ? html`<div class="section-label">Quizás conozcas</div>
                    ${sugerencias.users.map((u) => persona(u, relationButtons(u)))}` : ''}`);
            const input = $('[data-slot="search"]', lista);
            if (busqueda) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
            setHtml($('[data-slot="req-count"]', root), countBadge(recibidas.requests.length));
        } catch (err) {
            setHtml(lista, empty({ icon: 'alert', title: 'No se pudieron cargar tus amigos', text: err.message }));
        }
    }

    const buscar = debounce((q) => pintarAmigos(q), 300);
    lista.addEventListener('input', (e) => { if (e.target.matches('[data-slot="search"]')) buscar(e.target.value.trim()); }, { signal });
    on(root, 'click', '[data-profile]', (_e, b) => openUserProfile(Number(b.dataset.profile), { onChanged: refrescarTodo }), signal);
    on(root, 'click', '[data-friend]', async (_e, b) => {
        if (b.dataset.friend === 'message') return go(`/mensajes/dm/${b.dataset.user}`);
        try {
            const ok = await friendAction(b.dataset.friend, { userId: Number(b.dataset.user), requestId: b.dataset.request, name: b.dataset.name });
            if (ok !== false) refrescarTodo();
        } catch (err) {
            toast(err.message, 'error');
        }
    }, signal);

    function refrescarTodo() {
        if (tab === 'amigos') pintarAmigos($('[data-slot="search"]', lista)?.value.trim() || '');
        cargarBandeja();
    }

    /* --- Hilo abierto --------------------------------------------------------- */
    function cabecera(contenido) {
        return html`<div class="conversation__head">
            <a class="icon-btn icon-btn--sm" href="#/mensajes" aria-label="Volver a la bandeja" style="${window.innerWidth > 980 ? 'display:none' : ''}">${icon('chevronLeft')}</a>
            ${contenido}</div><div data-slot="chat" style="display:flex;flex-direction:column;flex:1;min-height:0"></div>`;
    }

    async function abrirGlobal() {
        setHtml(hilo, cabecera(html`<span class="thread-item__global">${icon('globe')}</span>
            <div><h2>Chat global UFG</h2><p>Visible para toda la comunidad. Sé respetuoso.</p></div>`));
        chat = mountChat($('[data-slot="chat"]', hilo), {
            signal,
            placeholder: 'Escribe a toda la comunidad UFG',
            load: async (after) => (await api.get(`/api/chat/messages${after ? `?after=${after}` : ''}`)).messages,
            send: async (texto) => (await api.post('/api/chat/messages', { message: texto })).data,
            toMsg: (m) => ({ id: m.id, userId: m.user_id, user: m.user || { name: m.user_name }, text: m.message, time: m.timestamp }),
            canDelete: (m) => m.userId === store.user.id || store.user.is_admin,
            onDelete: (id) => api.del(`/api/chat/messages/${id}`),
        });
        store.on('pulse', ({ pulse: p, previo }) => {
            if (p.global_last_id !== previo?.global_last_id) chat.refresh();
            if (tab === 'chats') pintarBandeja();
        }, signal);
    }

    async function abrirDM(id) {
        let contacto = conversaciones.find((c) => c.user.id === id)?.user;
        setHtml(hilo, cabecera(html`<span data-slot="who" style="display:flex;align-items:center;gap:12px;min-width:0"></span>
            <div class="actions"><button class="icon-btn icon-btn--sm" data-profile="${id}" aria-label="Ver perfil">${icon('user')}</button></div>`));
        const pintarQuien = (u) => setHtml($('[data-slot="who"]', hilo), html`${avatar({ ...u, online: store.isOnline(u.id) })}
            <div style="min-width:0"><h2>${u.name}</h2><p>${store.isOnline(u.id) ? 'En línea' : u.last_seen ? `Visto ${timeAgo(u.last_seen)}` : (u.career || '')}</p></div>`);
        if (contacto) pintarQuien(contacto);
        chat = mountChat($('[data-slot="chat"]', hilo), {
            signal,
            showAuthors: false,
            placeholder: 'Escribe un mensaje',
            emptyText: 'Aún no se han escrito. Empieza la conversación.',
            load: async (after) => {
                const datos = await api.get(`/api/direct-messages/${id}${after ? `?after=${after}` : ''}`);
                if (datos.contact && !contacto) { contacto = datos.contact; pintarQuien(contacto); }
                return datos.messages;
            },
            send: async (texto) => {
                const r = (await api.post('/api/direct-messages', { receiver_id: id, message: texto })).data;
                setTimeout(cargarBandeja, 300);
                return r;
            },
            toMsg: (m) => ({ id: m.id, userId: m.sender_id, user: m.sender_id === id ? contacto : store.user, text: m.message, time: m.timestamp }),
        });
        store.on('pulse', ({ pulse: p }) => {
            chat.refresh();
            if (contacto) pintarQuien(contacto);
            if ((p.dm_unread_total || 0) > 0) cargarBandeja();
            else if (tab === 'chats') pintarBandeja();
        }, signal);
        setTimeout(() => { cargarBandeja(); pulse.now(); }, 600);
    }

    if (tab === 'amigos') {
        pintarAmigos();
        cargarBandeja();
    } else {
        await cargarBandeja();
    }

    if (modo === 'global') abrirGlobal();
    else if (modo === 'dm' && contactId) abrirDM(contactId);
    else setHtml(hilo, html`<div class="empty" style="margin:auto">${icon('chat')}<h3>Elige una conversación</h3>
        <p>El chat global está arriba en la lista. Para escribir por privado, agrega a tus compañeros como amigos.</p></div>`);

    if (!hayHilo) {
        store.on('pulse', () => { if (tab === 'chats') pintarBandeja(); }, signal);
    }
}
