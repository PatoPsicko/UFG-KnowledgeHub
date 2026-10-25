/** Mi espacio: notas tipo post-it y archivos personales. */

import { api } from '../core/api.js';
import { $, fileSize, html, on, setHtml, timeAgo } from '../core/dom.js';
import { typeLabel } from '../data/categories.js';
import { bindFilter, empty, loading, scanBadge, searchToggle } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { confirmDialog, openDialog, toast } from '../ui/overlay.js';
import { askAboutDocument } from './assistant.js';

export async function notesView(root, { query = {} }, signal) {
    let items = [];
    let tab = query.tab === 'archivos' ? 'archivos' : 'notas';
    let actual = query.id ? Number(query.id) : null;

    setHtml(root, html`<div class="page page--wide">
        <div class="page-head">
            <div><h1>Mi espacio</h1><p>Tus notas y archivos: sólo tú los ves. El asistente también puede consultarlas cuando le preguntas.</p></div>
            <div class="page-head__actions">
                <button class="btn btn--secondary" data-action="upload">${icon('paperclip')}Subir archivo</button>
                <button class="btn btn--primary" data-action="new">${icon('plus')}Nueva nota</button>
            </div>
        </div>
        <div class="tabs" role="tablist">
            <button class="tab" role="tab" data-tab="notas" aria-selected="${tab === 'notas'}">${icon('note')}Mis notas</button>
            <button class="tab" role="tab" data-tab="archivos" aria-selected="${tab === 'archivos'}">${icon('paperclip')}Mis archivos</button>
            <span style="margin-left:auto;align-self:center">${searchToggle('Buscar en mi espacio')}</span>
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
        setHtml(cuerpo, html`<div class="stickies">
            <button class="sticky sticky--new" data-action="new">${icon('plus')}Nueva nota</button>
            ${notas.map((n) => html`<button class="sticky" data-note="${n.id}">
                <div class="sticky__title">${n.title}</div>
                <div class="sticky__text">${n.content || 'Sin contenido'}</div>
                <span class="sticky__time">${timeAgo(n.updated_at)}</span></button>`)}
        </div>`);
        if (actual && notas.some((n) => n.id === actual)) {
            const id = actual;
            actual = null;
            abrirNota(id);
        }
    }

    function abrirNota(id) {
        const nota = items.find((i) => i.id === id);
        if (!nota) return;
        const dlg = openDialog({
            title: 'Nota',
            submitLabel: 'Guardar',
            body: html`<input class="input" name="title" maxlength="200" value="${nota.title}" aria-label="Título" style="font-weight:600;margin-bottom:10px">
                <textarea class="textarea sticky-editor" name="content" maxlength="50000" placeholder="Escribe aquí tus ideas, resúmenes o pendientes…" aria-label="Contenido">${nota.content}</textarea>
                <div style="display:flex;gap:6px;margin-top:10px">
                    <button type="button" class="btn btn--ghost btn--sm" data-note-act="ask">${icon('bulb')}Preguntar al asistente</button>
                    <button type="button" class="btn btn--ghost btn--sm" data-note-act="delete" style="margin-left:auto;color:var(--danger)">${icon('trash')}Eliminar</button>
                </div>`,
            onOpen: (_d, form) => form.content.focus(),
            onSubmit: async (form) => {
                const { resource } = await api.put(`/api/private-resources/${id}`, {
                    title: form.title.value.trim() || 'Sin título', content: form.content.value });
                items = items.map((i) => (i.id === id ? resource : i));
                pintar();
                toast('Nota guardada');
            },
        });
        dlg.addEventListener('click', async (e) => {
            const b = e.target.closest('[data-note-act]');
            if (!b) return;
            if (b.dataset.noteAct === 'ask') { dlg.close(); askAboutDocument(nota.doc_key, nota.title); return; }
            dlg.close();
            if (!await confirmDialog({ title: 'Eliminar nota', text: `«${nota.title}» se borrará para siempre.`, confirmLabel: 'Eliminar' })) return;
            await api.del(`/api/private-resources/${id}`);
            items = items.filter((i) => i.id !== id);
            pintar();
            toast('Nota eliminada');
        });
    }

    function pintarArchivos() {
        const archivos = items.filter((i) => i.type === 'file');
        setHtml(cuerpo, html`<section class="panel doc-list">${archivos.length ? archivos.map((f) => html`
            <article class="doc" data-file="${f.id}">
                <span class="doc__type" data-ext="${f.extension}">${typeLabel(f.extension)}</span>
                <div class="doc__main"><span class="doc__title" style="cursor:default">${f.title}</span>
                    <div class="doc__meta"><span>${f.original_filename}</span>${f.file_size ? html`<span>${fileSize(f.file_size)}</span>` : ''}<span>${timeAgo(f.created_at)}</span>${scanBadge(f.scan_status)}</div></div>
                <div class="doc__actions">
                    <button class="icon-btn icon-btn--sm" data-file-act="ask" aria-label="Preguntar al asistente" title="Preguntar al asistente">${icon('bulb')}</button>
                    <button class="icon-btn icon-btn--sm" data-file-act="download" aria-label="Descargar" title="Descargar">${icon('download')}</button>
                    <button class="icon-btn icon-btn--sm" data-file-act="delete" aria-label="Eliminar" title="Eliminar">${icon('trash')}</button>
                </div>
            </article>`) : empty({ icon: 'paperclip', title: 'Sin archivos personales', text: 'Guarda aquí documentos que sólo quieres para ti.' })}</section>`);
    }

    bindFilter(root, '[data-slot="body"]', '.sticky:not(.sticky--new), .doc', signal);
    on(root, 'click', '[data-tab]', (_e, b) => {
        tab = b.dataset.tab;
        root.querySelectorAll('[data-tab]').forEach((t) => t.setAttribute('aria-selected', String(t === b)));
        actual = null;
        pintar();
    }, signal);
    on(root, 'click', '[data-note]', (_e, b) => abrirNota(Number(b.dataset.note)), signal);
    on(root, 'click', '[data-action="new"]', async () => {
        try {
            const { resource } = await api.post('/api/private-resources', { title: 'Nota sin título', content: '' });
            items.unshift(resource);
            tab = 'notas';
            root.querySelectorAll('[data-tab]').forEach((t) => t.setAttribute('aria-selected', String(t.dataset.tab === 'notas')));
            pintar();
            abrirNota(resource.id);
        } catch (err) { toast(err.message, 'error'); }
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
