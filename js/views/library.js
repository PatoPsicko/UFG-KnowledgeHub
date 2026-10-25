/** Biblioteca compartida: buscar, filtrar, previsualizar, guardar y subir documentos. */

import { api } from '../core/api.js';
import { $, debounce, fileSize, html, longDate, on, raw, setHtml, timeAgo } from '../core/dom.js';
import { prefs } from '../core/prefs.js';
import { store } from '../core/store.js';
import { AREAS, PREVIEWABLE, SUGGESTED_TAGS, areaOf, typeLabel } from '../data/categories.js';
import { avatar, empty, scanBadge, skeletonRows } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { closeDrawer, confirmDialog, openDialog, openDrawer, toast } from '../ui/overlay.js';
import { askAboutDocument } from './assistant.js';

/* --- Fila de documento (también la usa Inicio) --------------------------------- */
export function docRow(r) {
    return html`<article class="doc" data-id="${r.id}">
        <span class="doc__type" data-ext="${r.extension}">${typeLabel(r.extension)}</span>
        <div class="doc__main">
            <button class="doc__title" data-action="open" title="${r.title}">${r.title}</button>
            <div class="doc__meta">
                <span>${r.author}</span>
                <span>${r.category}</span>
                <span>${icon('download')}${r.downloads}</span>
                <span>${timeAgo(r.created_at)}</span>
                ${scanBadge(r.scan_status)}
            </div>
            ${r.tags ? html`<div class="doc__tags">${r.tags.split(',').map((t) => t.trim()).filter(Boolean).slice(0, 5).map((t) => html`<span class="tag">${t}</span>`)}</div>` : ''}
        </div>
        <div class="doc__actions">
            <button class="icon-btn icon-btn--sm" data-action="ask" title="Preguntar al asistente sobre este documento" aria-label="Preguntar al asistente">${icon('bulb')}</button>
            <button class="icon-btn icon-btn--sm" data-action="save" aria-pressed="${r.saved}" title="${r.saved ? 'Quitar de guardados' : 'Guardar'}" aria-label="Guardar">${icon(r.saved ? 'bookmarkFill' : 'bookmark')}</button>
            <button class="icon-btn icon-btn--sm" data-action="download" title="Descargar" aria-label="Descargar">${icon('download')}</button>
        </div>
    </article>`;
}

/** Acciones comunes de una fila (biblioteca e inicio). */
export function bindDocActions(root, getResource, signal, onChanged = () => {}) {
    on(root, 'click', '.doc [data-action]', async (_e, btn) => {
        const id = Number(btn.closest('.doc').dataset.id);
        const r = getResource(id);
        if (!r) return;
        const accion = btn.dataset.action;
        try {
            if (accion === 'open') openResource(id, { onChanged });
            if (accion === 'ask') askAboutDocument(r.doc_key, r.title);
            if (accion === 'download') await descargar(r);
            if (accion === 'save') {
                const { saved } = await api.post(`/api/resources/${id}/save`);
                r.saved = saved;
                btn.setAttribute('aria-pressed', String(saved));
                btn.innerHTML = String(icon(saved ? 'bookmarkFill' : 'bookmark'));
                toast(saved ? 'Guardado en tus documentos' : 'Quitado de guardados');
                onChanged();
            }
        } catch (err) {
            toast(err.message, 'error');
        }
    }, signal);
}

async function descargar(r) {
    await api.download(`/api/resources/${r.id}/file?download=1`, r.original_filename);
    r.downloads += r.is_owner ? 0 : 1;
}

/* --- Panel de detalle con vista previa -------------------------------------------- */
export async function openResource(id, { onChanged = () => {} } = {}) {
    const drawer = openDrawer(html`<div class="drawer__head"><div style="flex:1"><div class="skeleton" style="height:20px;width:60%"></div></div>
        <button class="icon-btn" data-close aria-label="Cerrar">${icon('x')}</button></div><div class="drawer__body"><div class="loading"><div class="spinner"></div></div></div>`);
    let r;
    try {
        r = (await api.get(`/api/resources/${id}`)).resource;
    } catch (err) {
        closeDrawer();
        return toast(err.message, 'error');
    }
    const area = areaOf(r.category);
    const puedePrevisualizar = PREVIEWABLE.has(r.extension) && r.scan_status !== 'blocked';
    setHtml(drawer, html`<div class="drawer__head">
            <span class="doc__type" data-ext="${r.extension}">${typeLabel(r.extension)}</span>
            <div style="flex:1;min-width:0"><h2 style="font-size:20px">${r.title}</h2>
                <p style="color:var(--ink-3);font-size:14px;margin-top:2px">${area.name}</p></div>
            <button class="icon-btn" data-close aria-label="Cerrar">${icon('x')}</button>
        </div>
        <div class="drawer__body">
            <div style="display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn btn--primary" data-act="download">${icon('download')}Descargar</button>
                <button class="btn btn--accent" data-act="ask">${icon('bulb')}Preguntar al asistente</button>
                <button class="btn btn--secondary" data-act="save" aria-pressed="${r.saved}">${icon(r.saved ? 'bookmarkFill' : 'bookmark')}${r.saved ? 'Guardado' : 'Guardar'}</button>
                ${r.is_owner || store.user.is_admin ? html`
                    <button class="icon-btn" data-act="edit" title="Editar" aria-label="Editar">${icon('edit')}</button>
                    <button class="icon-btn" data-act="delete" title="Eliminar" aria-label="Eliminar">${icon('trash')}</button>` : ''}
            </div>
            ${r.scan_status !== 'clean' ? html`<div style="margin-top:14px">${scanBadge(r.scan_status)}
                <span style="font-size:13.5px;color:var(--ink-2);margin-left:6px">${r.scan_status === 'pending' ? 'Sólo tú lo ves hasta que termine la revisión de seguridad.'
                    : r.scan_status === 'review' ? 'Un administrador lo revisará antes de publicarlo.' : 'No se publicó por motivos de seguridad.'}</span></div>` : ''}
            ${r.description ? html`<p style="margin-top:16px;color:var(--ink-2)">${r.description}</p>` : ''}
            <dl class="kv">
                <dt>Autor</dt><dd>${r.author}</dd>
                <dt>Categoría</dt><dd>${r.category}</dd>
                <dt>Subido por</dt><dd style="display:flex;align-items:center;gap:8px">${avatar(r.owner, 'sm')}${r.owner?.name || r.owner_name}</dd>
                <dt>Fecha</dt><dd>${longDate(r.created_at)}</dd>
                <dt>Archivo</dt><dd style="word-break:break-all">${r.original_filename} ${r.file_size ? html`<span style="color:var(--ink-3)">(${fileSize(r.file_size)})</span>` : ''}</dd>
                <dt>Descargas</dt><dd>${r.downloads}</dd>
                ${r.tags ? html`<dt>Etiquetas</dt><dd class="doc__tags" style="margin:0">${r.tags.split(',').filter((t) => t.trim()).map((t) => html`<span class="tag">${t.trim()}</span>`)}</dd>` : ''}
            </dl>
            <h3 style="font-size:15px;margin-bottom:8px">Vista previa</h3>
            <div class="preview" data-slot="preview">${puedePrevisualizar ? raw('<div class="spinner"></div>')
                : html`<div class="empty" style="padding:20px">${icon('file')}<p>Este formato no se puede previsualizar. Descárgalo para abrirlo.</p></div>`}</div>
        </div>`);
    drawer.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', closeDrawer));

    let objectUrl = null;
    // Los navegadores del celular (y las web views) no muestran un PDF dentro
    // de un iframe: se abre con un enlace firmado en el visor del teléfono.
    const pdfEnCelular = r.extension === 'pdf' && matchMedia('(max-width: 980px), (pointer: coarse)').matches;
    if (puedePrevisualizar && pdfEnCelular) {
        try {
            const url = await api.link(`/api/resources/${r.id}/file`);
            setHtml(drawer.querySelector('[data-slot="preview"]'), html`<div class="empty" style="padding:20px">${icon('file')}
                <p>El PDF se abre en el visor de tu teléfono.</p>
                <a class="btn btn--primary" href="${url}" target="_blank" rel="noopener">${icon('eye')}Abrir PDF</a></div>`);
        } catch (err) {
            setHtml(drawer.querySelector('[data-slot="preview"]'), html`<div class="empty" style="padding:20px"><p>${err.message}</p></div>`);
        }
    } else if (puedePrevisualizar) {
        try {
            const blob = await api.blob(`/api/resources/${r.id}/file`);
            const slot = drawer.querySelector('[data-slot="preview"]');
            if (!slot) return;
            if (['txt', 'md', 'csv'].includes(r.extension)) {
                const texto = (await blob.text()).slice(0, 20000);
                setHtml(slot, html`<pre>${texto}</pre>`);
            } else {
                objectUrl = URL.createObjectURL(blob);
                setHtml(slot, r.extension === 'pdf'
                    ? html`<iframe src="${objectUrl}" title="Vista previa de ${r.title}"></iframe>`
                    : html`<img src="${objectUrl}" alt="Vista previa de ${r.title}">`);
            }
        } catch (err) {
            setHtml(drawer.querySelector('[data-slot="preview"]'), html`<div class="empty" style="padding:20px"><p>${err.message}</p></div>`);
        }
    }
    const limpiar = () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };

    drawer.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-act]');
        if (!b) return;
        try {
            if (b.dataset.act === 'download') await descargar(r);
            if (b.dataset.act === 'ask') { closeDrawer(); limpiar(); askAboutDocument(r.doc_key, r.title); }
            if (b.dataset.act === 'save') {
                const { saved } = await api.post(`/api/resources/${r.id}/save`);
                r.saved = saved;
                setHtml(b, html`${icon(saved ? 'bookmarkFill' : 'bookmark')}${saved ? 'Guardado' : 'Guardar'}`);
                onChanged();
            }
            if (b.dataset.act === 'edit') { closeDrawer(); limpiar(); uploadDialog(r, onChanged); }
            if (b.dataset.act === 'delete') {
                if (!await confirmDialog({ title: 'Eliminar documento', text: `«${r.title}» se borrará de la biblioteca para todos.`, confirmLabel: 'Eliminar' })) return;
                await api.del(`/api/resources/${r.id}`);
                toast('Documento eliminado');
                closeDrawer();
                limpiar();
                onChanged();
            }
        } catch (err) {
            toast(err.message, 'error');
        }
    });
}

/* --- Subir / editar ------------------------------------------------------------- */
function categoryOptions(selected) {
    return html`<option value="">Elige una categoría</option>${AREAS.map((a) => html`<optgroup label="${a.name}">
        ${a.items.map((c) => html`<option value="${c}" ${c === selected ? raw('selected') : ''}>${c}</option>`)}</optgroup>`)}`;
}

export function uploadDialog(resource = null, onDone = () => {}) {
    const editando = !!resource;
    openDialog({
        title: editando ? 'Editar documento' : 'Subir documento',
        description: editando ? '' : 'Lo verá toda la comunidad UFG después de pasar la revisión de seguridad.',
        submitLabel: editando ? 'Guardar cambios' : 'Subir',
        body: html`
            <label class="dropzone" data-slot="drop">
                ${icon('upload')}
                <span><strong>${editando ? 'Reemplazar archivo (opcional)' : 'Elige un archivo'}</strong> o arrástralo aquí</span>
                <span class="field__hint">PDF, Word, Excel, PowerPoint, imágenes, texto o ZIP, hasta 25 MB</span>
                <span class="dropzone__file" data-slot="filename">${editando ? resource.original_filename : ''}</span>
                <input type="file" name="file" ${editando ? '' : raw('required')}
                    accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.csv,.rtf,.odt,.odp,.ods,.png,.jpg,.jpeg,.gif,.webp,.zip,.rar,.7z">
            </label>
            <label class="field" style="margin-top:16px"><span class="field__label">Título</span>
                <input class="input" name="title" required maxlength="200" value="${resource?.title || ''}" placeholder="Ej. Guía de normalización con ejercicios"></label>
            <div class="row">
                <label class="field"><span class="field__label">Autor</span>
                    <input class="input" name="author" required maxlength="200" value="${resource?.author || store.user.name}"></label>
                <label class="field"><span class="field__label">Categoría</span>
                    <select class="select" name="category" required>${categoryOptions(resource?.category)}</select></label>
            </div>
            <label class="field"><span class="field__label">Etiquetas</span>
                <input class="input" name="tags" maxlength="300" value="${resource?.tags || ''}" placeholder="Separadas por comas">
                <span class="chips" style="margin-top:4px">${SUGGESTED_TAGS.map((t) => html`<button type="button" class="chip" data-tag="${t}">${t}</button>`)}</span></label>
            <label class="field"><span class="field__label">Descripción</span>
                <textarea class="textarea" name="description" rows="3" maxlength="2000" placeholder="¿De qué materia es? ¿Qué incluye?">${resource?.description || ''}</textarea></label>`,
        onOpen: (dlg, form) => {
            const drop = dlg.querySelector('[data-slot="drop"]');
            const input = form.file;
            const nombre = dlg.querySelector('[data-slot="filename"]');
            const mostrar = () => {
                const f = input.files[0];
                if (!f) return;
                nombre.textContent = `${f.name} (${fileSize(f.size)})`;
                if (!form.title.value) form.title.value = f.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ');
            };
            input.addEventListener('change', mostrar);
            drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('is-over'); });
            drop.addEventListener('dragleave', () => drop.classList.remove('is-over'));
            drop.addEventListener('drop', (e) => {
                e.preventDefault();
                drop.classList.remove('is-over');
                if (e.dataTransfer.files.length) { input.files = e.dataTransfer.files; mostrar(); }
            });
            dlg.querySelectorAll('[data-tag]').forEach((b) => b.addEventListener('click', () => {
                const actuales = form.tags.value.split(',').map((t) => t.trim()).filter(Boolean);
                if (!actuales.includes(b.dataset.tag)) actuales.push(b.dataset.tag);
                form.tags.value = actuales.join(', ');
            }));
        },
        onSubmit: async (form) => {
            if (!editando && !form.file.files.length) throw new Error('Elige el archivo que quieres compartir.');
            if (!form.title.value.trim() || !form.author.value.trim()) throw new Error('El título y el autor son obligatorios.');
            if (!form.category.value) throw new Error('Elige una categoría para que otros lo encuentren.');
            const datos = new FormData(form);
            if (!form.file.files.length) datos.delete('file');
            const r = editando
                ? await api.upload(`/api/resources/${resource.id}`, datos, 'PUT')
                : await api.upload('/api/resources', datos);
            toast(editando ? 'Cambios guardados' : r.message, 'success', 5000);
            onDone(r.resource);
        },
    });
}

/* --- Vista -------------------------------------------------------------------- */
export async function libraryView(root, { query = {} }, signal) {
    const estado = {
        q: query.q || '', category: query.category || '', scope: query.scope || 'all', sort: query.sort || prefs.get('library_sort'),
        resources: [], total: 0, categories: [],
    };

    setHtml(root, html`<div class="page">
        <div class="page-head">
            <div><h1>Biblioteca</h1><p>Material que comparten estudiantes de todas las facultades. Cada archivo pasa por el vigilante de seguridad antes de publicarse.</p></div>
            <div class="page-head__actions"><button class="btn btn--primary" data-action="upload">${icon('upload')}Subir documento</button></div>
        </div>
        <div class="library-layout">
            <aside class="facets" data-slot="facets"></aside>
            <section>
                <div class="toolbar">
                    <div class="search">${icon('search')}<input class="input" type="search" name="q" value="${estado.q}" placeholder="Buscar por título, autor, etiqueta o tema" aria-label="Buscar documentos"></div>
                    <select class="select" name="sort" aria-label="Ordenar">
                        <option value="recent">Más recientes</option><option value="popular">Más descargados</option><option value="title">Por título</option>
                    </select>
                </div>
                <div class="chips" style="margin-bottom:14px" data-slot="scope">
                    ${[['all', 'Todos'], ['saved', 'Guardados'], ['mine', 'Subidos por mí']].map(([k, l]) => html`<button class="chip" data-scope="${k}" aria-pressed="${estado.scope === k}">${l}</button>`)}
                </div>
                <p class="result-count" data-slot="count"></p>
                <div class="panel doc-list" data-slot="list">${skeletonRows(6)}</div>
            </section>
        </div>
    </div>`);

    const lista = $('[data-slot="list"]', root);
    $('[name="sort"]', root).value = estado.sort;

    // Áreas plegables: con ~40 categorías, una lista plana era difícil de recorrer.
    const abiertas = new Set(estado.category ? [areaOf(estado.category).key] : []);
    function pintarFacetas() {
        const porArea = new Map();
        for (const c of estado.categories) {
            const a = areaOf(c.name);
            if (!porArea.has(a.key)) porArea.set(a.key, { area: a, cats: [], total: 0 });
            porArea.get(a.key).cats.push(c);
            porArea.get(a.key).total += c.count;
        }
        const orden = [...porArea.values()].sort((x, y) => y.total - x.total);
        setHtml($('[data-slot="facets"]', root), html`<div class="facet">
            <h3>Áreas de estudio</h3>
            <button class="facet__item" data-category="" aria-pressed="${!estado.category}">Todas<span class="facet__n">${estado.categories.reduce((s, c) => s + c.count, 0)}</span></button>
            ${orden.map(({ area, cats, total }) => html`
                <button class="facet__item" data-area="${area.key}" aria-expanded="${abiertas.has(area.key)}" style="--spine: var(--spine-${area.key})">
                    <span class="facet__swatch"></span>${area.name}<span class="facet__n">${total}</span></button>
                ${abiertas.has(area.key) ? cats.map((c) => html`<button class="facet__item facet__item--sub" data-category="${c.name}" aria-pressed="${estado.category === c.name}">
                    ${c.name}<span class="facet__n">${c.count}</span></button>`) : ''}`)}
        </div>`);
    }

    async function cargar() {
        const params = new URLSearchParams({ sort: estado.sort, scope: estado.scope, limit: 120 });
        if (estado.q) params.set('q', estado.q);
        if (estado.category) params.set('category', estado.category);
        try {
            const datos = await api.get(`/api/resources?${params}`);
            if (signal.aborted) return;
            estado.resources = datos.resources;
            estado.total = datos.total;
            pintarLista();
        } catch (err) {
            setHtml(lista, empty({ icon: 'alert', title: 'No se pudo cargar la biblioteca', text: err.message }));
        }
    }

    function pintarLista() {
        const filtros = [estado.q && `«${estado.q}»`, estado.category].filter(Boolean).join(' en ');
        $('[data-slot="count"]', root).textContent = `${estado.total} ${estado.total === 1 ? 'documento' : 'documentos'}${filtros ? ` para ${filtros}` : ''}`;
        if (!estado.resources.length) {
            setHtml(lista, empty(estado.scope === 'saved'
                ? { icon: 'bookmark', title: 'Aún no guardas documentos', text: 'Usa el marcador de cada documento para tenerlo a mano aquí.' }
                : estado.q || estado.category
                    ? { icon: 'search', title: 'Sin resultados', text: 'Prueba con otras palabras o pregúntale al asistente: busca también dentro del contenido de los archivos.' }
                    : { icon: 'library', title: 'La biblioteca está vacía', text: 'Sé la primera persona en compartir material con tu facultad.', action: html`<button class="btn btn--primary" data-action="upload">${icon('upload')}Subir documento</button>` }));
            return;
        }
        setHtml(lista, html`${estado.resources.map(docRow)}`);
    }

    async function cargarCategorias() {
        try {
            estado.categories = (await api.get('/api/resources/categories')).categories;
            pintarFacetas();
        } catch { /* las facetas son opcionales */ }
    }

    const recargar = () => { cargar(); cargarCategorias(); };
    bindDocActions(root, (id) => estado.resources.find((r) => r.id === id), signal, recargar);

    on(root, 'click', '[data-action="upload"]', () => uploadDialog(null, recargar), signal);
    on(root, 'click', '[data-category]', (_e, b) => { estado.category = b.dataset.category; pintarFacetas(); cargar(); }, signal);
    on(root, 'click', '[data-area]', (_e, b) => {
        const k = b.dataset.area;
        if (abiertas.has(k)) abiertas.delete(k); else abiertas.add(k);
        pintarFacetas();
    }, signal);
    on(root, 'click', '[data-scope]', (_e, b) => {
        estado.scope = b.dataset.scope;
        root.querySelectorAll('[data-scope]').forEach((c) => c.setAttribute('aria-pressed', String(c === b)));
        cargar();
    }, signal);
    $('[name="q"]', root).addEventListener('input', debounce((e) => { estado.q = e.target.value.trim(); cargar(); }, 300), { signal });
    $('[name="sort"]', root).addEventListener('change', (e) => {
        estado.sort = e.target.value;
        prefs.set({ library_sort: estado.sort });  // se recuerda para la próxima vez
        cargar();
    }, { signal });

    // Los documentos propios en revisión cambian de estado solos: se refresca de vez en cuando.
    store.on('pulse', ({ pulse, previo }) => {
        if (pulse.notifications_unread > (previo?.notifications_unread || 0)) cargar();
    }, signal);

    cargar();
    cargarCategorias();
}
