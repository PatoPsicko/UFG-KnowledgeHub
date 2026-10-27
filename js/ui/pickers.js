/**
 * Desplegables en cascada: primero el grupo y luego lo de ese grupo, para no
 * mostrar el catálogo entero de golpe.
 *   - Carrera: área → carrera. Las carreras se piden una vez al servidor
 *     (GET /api/resources/careers, con caché) y se guardan en memoria.
 *   - Categoría: área de estudio → materia (datos locales de categories.js).
 */

import { api } from '../core/api.js';
import { html, raw, setHtml } from '../core/dom.js';
import { AREAS } from '../data/categories.js';

let carreras = null;

export function careerGroups() {
    carreras ??= api.get('/api/resources/careers').then((r) => r.groups).catch((err) => { carreras = null; throw err; });
    return carreras;
}

const opt = (value, label, selected = false) => html`<option value="${value}" ${selected ? raw('selected') : ''}>${label}</option>`;

function cascada(grupo, final, grupos, value, { placeholderGrupo, placeholderFinal, actual }) {
    const legado = value && !grupos.some((g) => g.items.includes(value));
    const inicial = legado ? '__actual' : (grupos.find((g) => g.items.includes(value))?.key || '');
    setHtml(grupo, html`${opt('', placeholderGrupo, !inicial)}${legado ? opt('__actual', actual, true) : ''}
        ${grupos.map((g) => opt(g.key, g.name, g.key === inicial))}`);
    const pintar = () => {
        if (grupo.value === '__actual') {
            setHtml(final, opt(value, value, true));
            final.disabled = false;
            return;
        }
        const g = grupos.find((x) => x.key === grupo.value);
        setHtml(final, g ? html`${opt('', placeholderFinal)}${g.items.map((it) => opt(it, it, it === value))}` : opt('', 'Primero elige el área'));
        final.disabled = !g;
    };
    grupo.addEventListener('change', pintar);
    pintar();
}

export function careerFields(name = 'career') {
    return html`<div class="row cascade">
        <label class="field"><span class="field__label">Área</span><select class="select" data-level="career-group"><option>Cargando…</option></select></label>
        <label class="field"><span class="field__label">Carrera</span><select class="select" name="${name}" disabled></select></label>
    </div>`;
}

export async function fillCareer(container, value, name = 'career') {
    const grupos = (await careerGroups()).map((g) => ({ key: g.name, name: g.name, items: g.careers }));
    cascada(container.querySelector('[data-level="career-group"]'), container.querySelector(`[name="${name}"]`), grupos, value,
        { placeholderGrupo: 'Elige un área', placeholderFinal: 'Elige la carrera', actual: 'Carrera actual' });
}

export function categoryFields(name = 'category') {
    return html`<div class="row cascade">
        <label class="field"><span class="field__label">Categoría</span><select class="select" data-level="category-group"></select></label>
        <label class="field"><span class="field__label">Materia</span><select class="select" name="${name}" required disabled></select></label>
    </div>`;
}

export function fillCategory(container, value, name = 'category') {
    cascada(container.querySelector('[data-level="category-group"]'), container.querySelector(`[name="${name}"]`), AREAS, value,
        { placeholderGrupo: 'Elige una categoría', placeholderFinal: 'Elige la materia', actual: 'Categoría actual' });
}
