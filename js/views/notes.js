/** Anotaciones privadas: notas con guardado automático y archivos personales. */

import { api } from '../core/api.js';
import { $, debounce, fileSize, html, on, setHtml, timeAgo } from '../core/dom.js';
import { typeLabel } from '../data/categories.js';
import { empty, loading, scanBadge } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { confirmDialog, openDialog, toast } from '../ui/overlay.js';
import { askAboutDocument } from './assistant.js';

export async function notesView(root, { query = {} }, signal) {
    let items = [];
    let tab = query.tab === 'archivos' ? 'archivos' : 'notas';
    let actual = query.id ? Number(query.id) : null;

    setHtml(root, html`<div class="page page--wide">
        <div class="page-head">
            <div><h1>Anotaciones</h1><p>Sólo tú las ves. El asistente también puede consultarlas cuando le preguntas.</p></div>
            <div class="page-head__actions">
                <button class="btn btn--secondary" data-action="upload">${icon('paperclip')}Subir archivo</button>
                <button class="btn btn--primary" data-action="new">${icon('plus')}Nueva nota</button>
            </div>
        </div>
        <div class="tabs" role="tablist">
            <button class="tab" role="tab" data-tab="notas" aria-selected="${tab === 'notas'}">${icon('note')}Notas</button>
            <button class="tab" role="tab" data-tab="archivos" aria-selected="${tab === 'archivos'}">${icon('paperclip')}Archivos</button>
        </div>
        <div data-slot="body">${loading()}</div>
    </div>`);
    const cuerpo = $('[data-slot="body"]', root);

    async function cargar() {
        items = (await api.get('/api/private-resources')).resources;
        if (actual && !items.some((i) => i.id === actual)) actual = null;
        const elegido = items.find((i) => i.id === actual);
        if (elegido) tab = elegido.type === 'file' ? 'archivos' : 'notas';
        root.querySelectorAll('[data-tab]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === tab)));
        pintar();
    }

    function pintar() {
        if (tab === 'archivos') return pintarArchivos();
        const notas = items.filter((i) => i.type === 'note');
        if (!actual && notas.length && window.innerWidth > 980) actual = notas[0].id;
        const nota = notas.find((n) => n.id === actual);
        setHtml(cuerpo, notas.length ? html`<div class="panel notes ${nota ? 'has-note' : ''}">
            <div class="notes__list">${notas.map((n) => html`<button class="note-item" data-note="${n.id}" aria-current="${n.id === actual}">
                <div class="note-item__title">${n.title}</div>
                <div class="note-item__preview">${n.content || 'Sin contenido'}</div>
                <div class="note-item__time">${timeAgo(n.updated_at)}</div></button>`)}</div>
            <div class="editor" data-slot="editor">${nota ? html`
                <div class="editor__bar">
                    <button class="icon-btn icon-btn--sm" data-action="back" aria-label="Volver a la lista" style="${window.innerWidth > 980 ? 'display:none' : ''}">${icon('chevronLeft')}</button>
                    <span class="editor__state" data-slot="state">Guardado</span>
                    <button class="btn btn--ghost btn--sm" data-action="ask">${icon('bulb')}Preguntar al asistente</button>
                    <button class="icon-btn icon-btn--sm" data-action="delete" aria-label="Eliminar nota">${icon('trash')}</button>
                </div>
                <input class="editor__title" data-field="title" value="${nota.title}" maxlength="200" aria-label="Título de la nota">
                <textarea class="editor__content" data-field="content" placeholder="Escribe aquí tus ideas, resúmenes o pendientes…" aria-label="Contenido de la nota">${nota.content}</textarea>` : ''}</div>
        </div>` : html`<div class="panel">${empty({ icon: 'note', title: 'Tu cuaderno está vacío', text: 'Escribe resúmenes, ideas para proyectos o pendientes. Se guardan solos.',
            action: html`<button class="btn btn--primary" data-action="new">${icon('plus')}Nueva nota</button>` })}</div>`);
    }

    function pintarArchivos() {
        const archivos = items.filter((i) => i.type === 'file');
        setHtml(cuerpo, html`<section class="panel doc-list">${archivos.length ? archivos.map((f) => html`
            <article class="doc" style="--spine: var(--ufg-orange)" data-file="${f.id}">
                <span class="doc__type">${typeLabel(f.extension)}</span>
                <div class="doc__main"><span class="doc__title" style="cursor:default">${f.title}</span>
                    <div class="doc__meta"><span>${f.original_filename}</span>${f.file_size ? html`<span>${fileSize(f.file_size)}</span>` : ''}<span>${timeAgo(f.created_at)}</span>${scanBadge(f.scan_status)}</div></div>
                <div class="doc__actions">
                    <button class="icon-btn icon-btn--sm" data-file-act="ask" aria-label="Preguntar al asistente" title="Preguntar al asistente">${icon('bulb')}</button>
                    <button class="icon-btn icon-btn--sm" data-file-act="download" aria-label="Descargar" title="Descargar">${icon('download')}</button>
                    <button class="icon-btn icon-btn--sm" data-file-act="delete" aria-label="Eliminar" title="Eliminar">${icon('trash')}</button>
                </div>
            </article>`) : empty({ icon: 'paperclip', title: 'Sin archivos personales', text: 'Guarda aquí documentos que sólo quieres para ti.' })}</section>`);
    }

    // Lo que falta por guardar se captura al escribir: si cambias de nota antes
    // de que pase el retardo, se guarda igualmente en la nota correcta.
    let pendiente = null;
    async function guardarAhora() {
        if (!pendiente) return;
        const { id, datos } = pendiente;
        pendiente = null;
        const estado = $('[data-slot="state"]', cuerpo);
        try {
            const { resource } = await api.put(`/api/private-resources/${id}`, datos);
            const i = items.findIndex((x) => x.id === id);
            if (i >= 0) items[i] = resource;
            if (estado && id === actual) estado.textContent = 'Guardado';
            const fila = cuerpo.querySelector(`[data-note="${id}"]`);
            if (fila) {
                fila.querySelector('.note-item__title').textContent = resource.title;
                fila.querySelector('.note-item__preview').textContent = resource.content || 'Sin contenido';
                fila.querySelector('.note-item__time').textContent = 'ahora';
            }
        } catch (err) {
            if (estado) estado.textContent = 'No se pudo guardar';
            toast(err.message, 'error');
        }
    }
    const guardar = debounce(guardarAhora, 700);

    cuerpo.addEventListener('input', (e) => {
        if (!e.target.matches('[data-field]') || !actual) return;
        pendiente = { id: actual, datos: {
            title: $('[data-field="title"]', cuerpo).value.trim() || 'Sin título',
            content: $('[data-field="content"]', cuerpo).value,
        } };
        const estado = $('[data-slot="state"]', cuerpo);
        if (estado) estado.textContent = 'Guardando…';
        guardar();
    }, { signal });
    signal.addEventListener('abort', () => guardarAhora());

    on(root, 'click', '[data-tab]', (_e, b) => {
        tab = b.dataset.tab;
        root.querySelectorAll('[data-tab]').forEach((t) => t.setAttribute('aria-selected', String(t === b)));
        actual = null;
        pintar();
    }, signal);
    on(root, 'click', '[data-note]', (_e, b) => { guardarAhora(); actual = Number(b.dataset.note); pintar(); $('[data-field="content"]', cuerpo)?.focus(); }, signal);
    on(root, 'click', '[data-action="back"]', () => { guardarAhora(); actual = null; pintar(); }, signal);
    on(root, 'click', '[data-action="new"]', async () => {
        try {
            const { resource } = await api.post('/api/private-resources', { title: 'Nota sin título', content: '' });
            items.unshift(resource);
            tab = 'notas';
            actual = resource.id;
            root.querySelectorAll('[data-tab]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === 'notas')));
            pintar();
            const titulo = $('[data-field="title"]', cuerpo);
            titulo?.select();
        } catch (err) { toast(err.message, 'error'); }
    }, signal);
    on(root, 'click', '[data-action="delete"]', async () => {
        const nota = items.find((i) => i.id === actual);
        if (!nota || !await confirmDialog({ title: 'Eliminar nota', text: `«${nota.title}» se borrará para siempre.`, confirmLabel: 'Eliminar' })) return;
        await api.del(`/api/private-resources/${nota.id}`);
        items = items.filter((i) => i.id !== nota.id);
        actual = null;
        pintar();
        toast('Nota eliminada');
    }, signal);
    on(root, 'click', '[data-action="ask"]', () => {
        const nota = items.find((i) => i.id === actual);
        if (nota) askAboutDocument(nota.doc_key, nota.title);
    }, signal);
    on(root, 'click', '[data-file-act]', async (_e, b) => {
        const f = items.find((i) => i.id === Number(b.closest('[data-file]').dataset.file));
        try {
            if (b.dataset.fileAct === 'download') await api.download(f.download_url, f.original_filename);
            if (b.dataset.fileAct === 'ask') askAboutDocument(f.doc_key, f.title);
            if (b.dataset.fileAct === 'delete') {
                if (!await confirmDialog({ title: 'Eliminar archivo', text: `«${f.title}» se borrará para siempre.`, confirmLabel: 'Eliminar' })) return;
                await api.del(`/api/private-resources/${f.id}`);
                items = items.filter((i) => i.id !== f.id);
                pintar();
                toast('Archivo eliminado');
            }
        } catch (err) { toast(err.message, 'error'); }
    }, signal);
    on(root, 'click', '[data-action="upload"]', () => openDialog({
        title: 'Subir archivo personal',
        description: 'Sólo tú lo verás. Igualmente pasa por el análisis de seguridad.',
        submitLabel: 'Subir',
        body: html`<label class="dropzone">${icon('upload')}<span><strong>Elige un archivo</strong></span>
                <span class="dropzone__file" data-slot="fn"></span><input type="file" name="file" required></label>
            <label class="field" style="margin-top:14px"><span class="field__label">Título</span><input class="input" name="title" maxlength="200"></label>`,
        onOpen: (dlg, form) => form.file.addEventListener('change', () => {
            const f = form.file.files[0];
            dlg.querySelector('[data-slot="fn"]').textContent = f ? `${f.name} (${fileSize(f.size)})` : '';
            if (f && !form.title.value) form.title.value = f.name.replace(/\.[^.]+$/, '');
        }),
        onSubmit: async (form) => {
            if (!form.file.files.length) throw new Error('Elige un archivo.');
            await api.upload('/api/private-resources', new FormData(form));
            toast('Archivo guardado');
            tab = 'archivos';
            actual = null;
            await cargar();
        },
    }), signal);

    try {
        await cargar();
    } catch (err) {
        setHtml(cuerpo, empty({ icon: 'alert', title: 'No se pudieron cargar tus anotaciones', text: err.message }));
    }
}
