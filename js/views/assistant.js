/**
 * Asistente de estudio («el escritorio»). Se monta en dos sitios:
 *   - Inicio: en la columna derecha, donde antes estaba el chat global.
 *   - #/asistente: a página completa, con el historial de conversaciones.
 * Ambos comparten la conversación en curso.
 */

import { api } from '../core/api.js';
import { $, autoGrow, html, on, raw, setHtml } from '../core/dom.js';
import { renderMarkdown } from '../core/markdown.js';
import { go } from '../core/router.js';
import { store } from '../core/store.js';
import { empty } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { confirmDialog, openDialog, toast } from '../ui/overlay.js';

const sesion = {
    conversationId: null,
    turns: [],          // { role, content, sources, documents, model, error }
    docScope: null,     // { key, title }
    listeners: new Set(),
};

const SUGERENCIAS = [
    '¿Qué material hay sobre bases de datos?',
    'Explícame la tercera forma normal con un ejemplo',
    'Hazme 3 preguntas de repaso de cálculo',
];

const ORIGEN = { public: 'Biblioteca', private_note: 'Tus anotaciones', private_file: 'Tus anotaciones', group: 'Grupo' };

export function askAboutDocument(docKey, title) {
    sesion.docScope = { key: docKey, title };
    sesion.conversationId = null;
    sesion.turns = [];
    go('/asistente');
}

function notificar() {
    sesion.listeners.forEach((fn) => fn());
}

async function estado() {
    if (store.aiStatus && Date.now() - store.aiStatus._t < 60000) return store.aiStatus;
    try {
        store.aiStatus = { ...(await api.get('/api/ai/status')), _t: Date.now() };
    } catch {
        store.aiStatus = { available: false, _t: Date.now() };
    }
    return store.aiStatus;
}

function modelLine(st) {
    if (!st) return html`<span class="dot"></span>Conectando…`;
    if (!st.available) return html`<span class="dot is-off"></span>Sin modelo disponible ahora`;
    return html`<span class="dot"></span>${st.provider_label || st.provider}: ${st.model}`;
}

function turnHtml(t, i) {
    if (t.role === 'user') {
        return html`<div class="turn turn--user"><div class="turn__bubble">${t.content}</div></div>`;
    }
    if (t.error) {
        return html`<div class="turn turn--bot turn--error"><div class="turn__bubble">${icon('alert')} ${t.content}</div></div>`;
    }
    const nums = (t.sources || []).map((s) => s.n);
    const cuerpo = t.pending && !t.content
        ? raw('<span class="typing" aria-label="Escribiendo"><i></i><i></i><i></i></span>')
        : raw(renderMarkdown(t.content, nums));
    const fuentes = t.pending ? [] : (t.sources || []);
    const docs = t.pending ? [] : (t.documents || []);
    return html`<div class="turn turn--bot" data-turn="${i}">
        <div class="turn__bubble md ${t.pending && t.content ? 'caret' : ''}">${cuerpo}</div>
        ${fuentes.length ? html`<div class="sources"><span class="sources__label">Fuentes</span>
            ${fuentes.map((s) => html`<button type="button" class="source" data-turn="${i}" data-n="${s.n}">
                <span class="source__n">${s.n}</span>
                <span style="min-width:0"><span class="source__title">${s.title}</span>
                <span class="source__meta" style="display:block">${s.origin}${s.page ? `, pág. ${s.page}` : ''}</span></span>${icon('chevronRight')}</button>`)}</div>` : ''}
        ${docs.length ? html`<div class="sources"><span class="sources__label">Documentos mencionados</span>
            ${docs.map((d, j) => html`<button type="button" class="source" data-turn="${i}" data-doc="${j}">
                <span class="source__n">${icon('file')}</span>
                <span style="min-width:0"><span class="source__title">${d.title}</span>
                <span class="source__meta" style="display:block">${d.origin}</span></span>${icon('chevronRight')}</button>`)}</div>` : ''}
    </div>`;
}

function intro(compact) {
    const scope = sesion.docScope;
    return html`<div class="desk-intro">
        <h3>${scope ? 'Pregunta lo que quieras sobre este documento' : 'Pregúntale a la biblioteca'}</h3>
        <p>${scope ? 'Puedo resumirlo, explicarte partes o hacerte preguntas de repaso, citando las páginas.'
        : 'Busco en los documentos que puedes ver y te respondo citando de dónde sale cada dato.'}</p>
        ${compact ? '' : html`<p style="margin-top:10px">Si no hay material sobre el tema, te respondo con conocimiento general y te lo aviso.</p>`}
    </div>`;
}

async function abrirFuente(item) {
    const tipo = item.type;
    const destino = () => {
        if (tipo === 'public') {
            import('./library.js').then((m) => m.openResource(item.resource_id));
        } else if (tipo === 'private_note' || tipo === 'private_file') {
            go(`/anotaciones?id=${item.resource_id}`);
        } else {
            go('/grupos');
        }
    };
    if (!item.snippet) return destino();
    openDialog({
        title: item.title,
        description: `${ORIGEN[tipo] || item.origin}${item.page ? `, página ${item.page}` : ''}`,
        body: html`<p style="color:var(--ink-2);border-left:3px solid var(--ufg-orange);padding-left:12px">${item.snippet}</p>`,
        submitLabel: 'Abrir documento',
        cancelLabel: 'Cerrar',
        onSubmit: () => { destino(); },
    });
}

/**
 * Monta el asistente dentro de `container`. Devuelve una función para
 * empezar de nuevo desde fuera (la usa la página completa).
 */
export function mountAssistant(container, { compact = false, signal, onChange } = {}) {
    setHtml(container, html`<section class="desk" aria-label="Asistente de estudio">
        <div class="desk__head">
            <span class="desk__mark">${icon('bulb')}</span>
            <div style="min-width:0;flex:1"><div class="desk__title">Asistente de estudio</div>
                <div class="desk__model" data-slot="model">${modelLine(null)}</div></div>
            <button class="icon-btn icon-btn--sm" data-action="new" title="Nueva conversación" aria-label="Nueva conversación">${icon('plus')}</button>
            ${compact ? html`<a class="icon-btn icon-btn--sm" href="#/asistente" title="Abrir a pantalla completa" aria-label="Abrir a pantalla completa">${icon('chevronRight')}</a>` : ''}
        </div>
        <div data-slot="scope"></div>
        <div class="desk__log" data-slot="log" aria-live="polite"></div>
        <div class="desk__suggest" data-slot="suggest"></div>
        <form class="desk__form" data-slot="form">
            <label class="sr-only" for="ai-input">Escribe tu pregunta</label>
            <textarea class="desk__input" id="ai-input" name="q" rows="1" maxlength="2000"
                placeholder="Pregunta sobre tus materias…"></textarea>
            <button class="desk__send" type="submit" aria-label="Enviar pregunta">${icon('send')}</button>
        </form>
        <p class="desk__note">Las respuestas pueden tener errores: revisa las fuentes antes de usarlas en un trabajo.</p>
    </section>`);

    const log = $('[data-slot="log"]', container);
    const form = $('[data-slot="form"]', container);
    const input = form.q;
    let enCurso = null;

    function pintar({ scroll = true } = {}) {
        const scope = sesion.docScope;
        setHtml($('[data-slot="scope"]', container), scope ? html`<div class="desk__scope">${icon('file')}
            <span>Preguntando sobre <strong>${scope.title}</strong></span>
            <button class="icon-btn icon-btn--sm" data-action="clear-scope" aria-label="Preguntar sobre toda la biblioteca">${icon('x')}</button></div>` : '');
        setHtml(log, sesion.turns.length ? html`${sesion.turns.map(turnHtml)}` : intro(compact));
        setHtml($('[data-slot="suggest"]', container), !sesion.turns.length && !sesion.docScope
            ? html`${SUGERENCIAS.slice(0, compact ? 2 : 3).map((s) => html`<button type="button" data-suggest="${s}">${s}</button>`)}` : '');
        if (scroll) log.scrollTop = log.scrollHeight;
    }

    function pintarUltimo() {
        const i = sesion.turns.length - 1;
        const nodo = log.querySelector(`[data-turn="${i}"]`);
        if (!nodo) return pintar();
        const cerca = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
        nodo.outerHTML = String(turnHtml(sesion.turns[i], i));
        if (cerca) log.scrollTop = log.scrollHeight;
    }

    async function preguntar(pregunta) {
        pregunta = pregunta.trim();
        if (!pregunta || enCurso) return;
        input.value = '';
        autoGrow(input);
        sesion.turns.push({ role: 'user', content: pregunta });
        const turno = { role: 'assistant', content: '', pending: true, sources: [], documents: [] };
        sesion.turns.push(turno);
        pintar();
        form.querySelector('button').disabled = true;
        enCurso = new AbortController();
        let pendientePintar = false;
        const programar = () => {
            if (pendientePintar) return;
            pendientePintar = true;
            requestAnimationFrame(() => { pendientePintar = false; pintarUltimo(); });
        };
        try {
            await api.stream('/api/ai/chat/stream', {
                question: pregunta, conversation_id: sesion.conversationId, doc_key: sesion.docScope?.key,
            }, (ev) => {
                if (ev.type === 'token') { turno.content += ev.content; programar(); }
                else if (ev.type === 'model') { turno.model = ev.model; }
                else if (ev.type === 'done') {
                    turno.pending = false;
                    turno.sources = ev.sources || [];
                    turno.documents = ev.documents || [];
                    sesion.conversationId = ev.conversation_id || sesion.conversationId;
                } else if (ev.type === 'error') {
                    turno.pending = false;
                    turno.error = true;
                    turno.content = ev.message;
                }
            }, enCurso.signal);
            if (turno.pending) { turno.pending = false; if (!turno.content) { turno.error = true; turno.content = 'El servidor cerró la respuesta sin contenido.'; } }
        } catch (err) {
            if (err.name === 'AbortError') return;
            turno.pending = false;
            turno.error = true;
            turno.content = err.message;
        } finally {
            enCurso = null;
            form.querySelector('button').disabled = false;
            pintarUltimo();
            onChange?.();
            notificar();
        }
    }

    form.addEventListener('submit', (e) => { e.preventDefault(); preguntar(input.value); }, { signal });
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); preguntar(input.value); }
    }, { signal });
    input.addEventListener('input', () => autoGrow(input), { signal });

    on(container, 'click', '[data-suggest]', (_e, b) => preguntar(b.dataset.suggest), signal);
    on(container, 'click', '[data-action="new"]', () => reiniciar(), signal);
    on(container, 'click', '[data-action="clear-scope"]', () => { sesion.docScope = null; reiniciar(); }, signal);
    on(container, 'click', '.cite', (_e, b) => {
        const turno = sesion.turns[Number(b.closest('[data-turn]').dataset.turn)];
        const fuente = turno?.sources?.find((s) => s.n === Number(b.dataset.cite));
        if (fuente) abrirFuente(fuente);
    }, signal);
    on(container, 'click', '.source', (_e, b) => {
        const turno = sesion.turns[Number(b.dataset.turn)];
        const item = b.dataset.n ? turno.sources.find((s) => s.n === Number(b.dataset.n)) : turno.documents[Number(b.dataset.doc)];
        if (item) abrirFuente(b.dataset.n ? item : { ...item, snippet: null, type: item.type });
    }, signal);

    function reiniciar() {
        enCurso?.abort();
        sesion.conversationId = null;
        sesion.turns = [];
        pintar();
        onChange?.();
        input.focus();
    }

    const alNotificar = () => { if (!enCurso) pintar({ scroll: true }); };
    sesion.listeners.add(alNotificar);
    signal?.addEventListener('abort', () => { sesion.listeners.delete(alNotificar); enCurso?.abort(); });

    estado().then((st) => setHtml($('[data-slot="model"]', container), modelLine(st)));
    pintar();
    if (!compact) input.focus();
    return { reiniciar, preguntar, pintar };
}

/* --- Página completa ---------------------------------------------------------- */
export async function assistantView(root, _params, signal) {
    setHtml(root, html`<div class="page page--wide page--flush">
        <div class="assistant-page">
            <aside class="history">
                <button class="btn btn--secondary btn--block" data-action="new-conv">${icon('plus')}Nueva conversación</button>
                <div class="history__list" data-slot="history"></div>
            </aside>
            <div data-slot="desk" style="min-height:0"></div>
        </div>
    </div>`);

    const lista = $('[data-slot="history"]', root);
    async function cargarHistorial() {
        try {
            const { conversations } = await api.get('/api/ai/conversations');
            setHtml(lista, conversations.length ? html`${conversations.map((c) => html`
                <button class="history__item" data-id="${c.id}" aria-current="${c.id === sesion.conversationId}">
                    ${icon('history')}<span title="${c.title}">${c.title}</span>
                    <span class="icon-btn icon-btn--sm" role="button" data-delete="${c.id}" aria-label="Eliminar conversación">${icon('trash')}</span>
                </button>`)}` : html`<p style="color:var(--ink-3);font-size:14px;padding:10px">Tus conversaciones aparecerán aquí.</p>`);
        } catch {
            setHtml(lista, empty({ icon: 'history', title: 'No se pudo cargar el historial' }));
        }
    }

    const desk = mountAssistant($('[data-slot="desk"]', root), { signal, onChange: cargarHistorial });

    on(root, 'click', '[data-action="new-conv"]', () => { sesion.docScope = null; desk.reiniciar(); }, signal);
    on(lista, 'click', '[data-delete]', async (e, b) => {
        e.stopPropagation();
        if (!await confirmDialog({ title: 'Eliminar conversación', text: 'Se borrará esta conversación del historial.', confirmLabel: 'Eliminar' })) return;
        await api.del(`/api/ai/conversations/${b.dataset.delete}`);
        if (sesion.conversationId === b.dataset.delete) desk.reiniciar();
        cargarHistorial();
    }, signal);
    on(lista, 'click', '.history__item', async (_e, b) => {
        try {
            const { messages, conversation_id: id } = await api.get(`/api/ai/history?conversation_id=${encodeURIComponent(b.dataset.id)}`);
            sesion.conversationId = id;
            sesion.docScope = null;
            sesion.turns = messages.map((m) => ({ role: m.role, content: m.content, sources: m.sources || [], documents: m.documents || [], model: m.model }));
            desk.pintar();
            cargarHistorial();
        } catch (err) {
            toast(err.message, 'error');
        }
    }, signal);

    cargarHistorial();
}

