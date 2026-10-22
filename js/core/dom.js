/**
 * Plantillas HTML seguras y utilidades de DOM.
 *
 *   html`<p>${texto}</p>`   escapa automáticamente cada valor interpolado.
 *   raw(cadena)             marca HTML de confianza (iconos, plantillas propias).
 *
 * Así ningún texto escrito por un estudiante (títulos, mensajes, nombres) puede
 * inyectar HTML o JavaScript en la página de otro (XSS).
 */

class SafeHtml {
    constructor(value) { this.value = value; }
    toString() { return this.value; }
}

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' };

export function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"'`]/g, (c) => ESCAPES[c]);
}

export function raw(value) {
    return new SafeHtml(String(value ?? ''));
}

function render(value) {
    if (value instanceof SafeHtml) return value.value;
    if (Array.isArray(value)) return value.map(render).join('');
    if (value === null || value === undefined || value === false) return '';
    return escapeHtml(value);
}

export function html(strings, ...values) {
    let out = strings[0];
    for (let i = 0; i < values.length; i++) {
        out += render(values[i]) + strings[i + 1];
    }
    return new SafeHtml(out);
}

export function setHtml(el, content) {
    el.innerHTML = String(content);
    return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

/**
 * Delegación de eventos: on(root, 'click', '[data-action="x"]', fn, signal).
 * El AbortSignal de la vista quita todos los escuchadores al cambiar de página.
 */
export function on(root, type, selector, handler, signal) {
    root.addEventListener(type, (event) => {
        const target = event.target.closest(selector);
        if (target && root.contains(target)) handler(event, target);
    }, { signal });
}

export function debounce(fn, ms = 300) {
    let t;
    return (...args) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
    };
}

/* --- Formato --------------------------------------------------------------- */
const rtf = new Intl.RelativeTimeFormat('es', { numeric: 'auto' });
const fechaCorta = new Intl.DateTimeFormat('es-SV', { day: 'numeric', month: 'short' });
const fechaLarga = new Intl.DateTimeFormat('es-SV', { day: 'numeric', month: 'long', year: 'numeric' });
const hora = new Intl.DateTimeFormat('es-SV', { hour: 'numeric', minute: '2-digit' });

export function timeAgo(iso) {
    if (!iso) return '';
    const fecha = new Date(iso);
    const seg = (fecha.getTime() - Date.now()) / 1000;
    const abs = Math.abs(seg);
    if (abs < 45) return 'ahora';
    if (abs < 3600) return rtf.format(Math.round(seg / 60), 'minute');
    if (abs < 86400) return rtf.format(Math.round(seg / 3600), 'hour');
    if (abs < 86400 * 6) return rtf.format(Math.round(seg / 86400), 'day');
    return fechaCorta.format(fecha);
}

export function clock(iso) {
    return iso ? hora.format(new Date(iso)) : '';
}

export function longDate(iso) {
    return iso ? fechaLarga.format(new Date(iso)) : '';
}

export function dayLabel(iso) {
    const d = new Date(iso);
    const hoy = new Date();
    const ayer = new Date(Date.now() - 86400000);
    if (d.toDateString() === hoy.toDateString()) return 'Hoy';
    if (d.toDateString() === ayer.toDateString()) return 'Ayer';
    return fechaLarga.format(d);
}

export function fileSize(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1).replace('.0', '')} MB`;
}

export function initials(name = '') {
    const partes = name.trim().split(/\s+/).filter(Boolean);
    return ((partes[0]?.[0] || '') + (partes.length > 1 ? partes[partes.length - 1][0] : '')).toUpperCase() || '?';
}

export function plural(n, singular, pluralForm = `${singular}s`) {
    return `${n} ${n === 1 ? singular : pluralForm}`;
}

/** Ajusta la altura de un textarea a su contenido. */
export function autoGrow(textarea, max = 160) {
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, max)}px`;
}
