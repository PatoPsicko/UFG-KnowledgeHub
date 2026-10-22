/**
 * Conversación reutilizable (chat global, mensajes privados y chat de grupo).
 *
 *   const chat = mountChat(el, { load, send, toMsg, canDelete, onDelete, placeholder, signal });
 *   chat.refresh()   pide sólo los mensajes nuevos (after=<último id>)
 *
 * `load(afterId)` devuelve la lista de mensajes del backend; `toMsg` los
 * convierte a { id, userId, user, text, time }.
 */

import { $, autoGrow, clock, dayLabel, html, on, setHtml } from '../core/dom.js';
import { store } from '../core/store.js';
import { avatar } from './components.js';
import { icon } from './icons.js';
import { toast } from './overlay.js';

const AGRUPAR_MS = 5 * 60 * 1000;

function bubbles(msgs, { showAuthors, canDelete }) {
    const yo = store.user.id;
    const partes = [];
    let previo = null;
    for (const m of msgs) {
        const fecha = new Date(m.time);
        if (!previo || new Date(previo.time).toDateString() !== fecha.toDateString()) {
            partes.push(html`<div class="day-sep">${dayLabel(m.time)}</div>`);
            previo = null;
        }
        const mio = m.userId === yo;
        const continua = previo && previo.userId === m.userId && fecha - new Date(previo.time) < AGRUPAR_MS;
        partes.push(html`<div class="msg ${mio ? 'msg--mine' : ''} ${continua ? 'msg--cont' : ''}" data-id="${m.id}">
            <span class="avatar-slot">${!mio && !continua ? avatar(m.user, 'sm') : ''}</span>
            <div class="msg__col">
                ${showAuthors && !mio && !continua ? html`<span class="msg__author">${m.user?.name || 'Usuario eliminado'}</span>` : ''}
                <div class="msg__bubble">${m.text}</div>
                <span class="msg__time">${clock(m.time)}${canDelete(m) ? html` <button class="icon-btn icon-btn--sm msg-del" data-del="${m.id}" aria-label="Borrar mensaje" style="width:22px;height:22px;vertical-align:middle">${icon('trash')}</button>` : ''}</span>
            </div>
        </div>`);
        previo = m;
    }
    return html`${partes}`;
}

export function mountChat(container, { load, send, toMsg, canDelete = () => false, onDelete, placeholder = 'Escribe un mensaje',
                                         showAuthors = true, emptyText = 'Todavía no hay mensajes. Escribe el primero.', signal, disabled = false }) {
    setHtml(container, html`<div class="conversation__log" data-slot="log" aria-live="polite"><div class="loading"><div class="spinner"></div></div></div>
        <form class="composer" data-slot="form">
            <label class="sr-only" for="composer-input">${placeholder}</label>
            <textarea class="textarea" id="composer-input" name="text" rows="1" maxlength="2000" placeholder="${placeholder}" ${disabled ? 'disabled' : ''}></textarea>
            <button class="btn btn--primary" type="submit" ${disabled ? 'disabled' : ''}>${icon('send')}<span class="sr-only">Enviar</span></button>
        </form>`);
    const log = $('[data-slot="log"]', container);
    const form = $('[data-slot="form"]', container);
    const input = form.text;
    let mensajes = [];
    let cargando = false;

    const pintar = (forzarAbajo = false) => {
        const cerca = log.scrollHeight - log.scrollTop - log.clientHeight < 120;
        setHtml(log, mensajes.length ? bubbles(mensajes, { showAuthors, canDelete })
            : html`<div class="empty">${icon('chat')}<p>${emptyText}</p></div>`);
        if (forzarAbajo || cerca) log.scrollTop = log.scrollHeight;
    };

    async function inicial() {
        try {
            mensajes = (await load(0)).map(toMsg);
            pintar(true);
        } catch (err) {
            setHtml(log, html`<div class="empty">${icon('alert')}<p>${err.message}</p></div>`);
        }
    }

    async function refresh() {
        if (cargando || signal?.aborted) return;
        cargando = true;
        try {
            const ultimo = mensajes.length ? mensajes[mensajes.length - 1].id : 0;
            const nuevos = (await load(ultimo)).map(toMsg).filter((m) => !mensajes.some((x) => x.id === m.id));
            if (nuevos.length) {
                mensajes = [...mensajes, ...nuevos];
                pintar();
            }
        } catch { /* se reintentará en el próximo pulso */ } finally {
            cargando = false;
        }
    }

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const texto = input.value.trim();
        if (!texto) return;
        const boton = form.querySelector('button');
        boton.disabled = true;
        try {
            const enviado = toMsg(await send(texto));
            input.value = '';
            autoGrow(input, 140);
            if (!mensajes.some((m) => m.id === enviado.id)) mensajes.push(enviado);
            pintar(true);
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            boton.disabled = false;
            input.focus();
        }
    }, { signal });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
    }, { signal });
    input.addEventListener('input', () => autoGrow(input, 140), { signal });

    on(log, 'click', '[data-del]', async (_e, b) => {
        const id = Number(b.dataset.del);
        try {
            await onDelete(id);
            mensajes = mensajes.filter((m) => m.id !== id);
            pintar();
        } catch (err) {
            toast(err.message, 'error');
        }
    }, signal);

    inicial();
    return { refresh, focus: () => input.focus() };
}
