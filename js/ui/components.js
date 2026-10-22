/** Piezas de interfaz reutilizables (devuelven HTML seguro). */

import { html, initials, raw } from '../core/dom.js';
import { store } from '../core/store.js';
import { icon } from './icons.js';

export function avatar(user, size = '') {
    if (!user) return html`<span class="avatar ${size ? `avatar--${size}` : ''}">?</span>`;
    const online = user.online ?? store.isOnline(user.id);
    const color = /^#[0-9a-f]{6}$/i.test(user.profile_color || '') ? user.profile_color : '#0B6FCB';
    const cls = `avatar${size ? ` avatar--${size}` : ''}`;
    const contenido = user.avatar_url
        ? html`<img src="${user.avatar_url}" alt="" loading="lazy">`
        : html`${initials(user.name)}`;
    return html`<span class="${cls}" style="background:${color}" data-online="${online ? 'true' : 'false'}" title="${user.name}">${contenido}</span>`;
}

export function empty({ icon: name = 'folder', title, text = '', action = '' }) {
    return html`<div class="empty">${icon(name)}<h3>${title}</h3>${text ? html`<p>${text}</p>` : ''}${action}</div>`;
}

export function loading() {
    return raw('<div class="loading"><div class="spinner" role="status" aria-label="Cargando"></div></div>');
}

export function skeletonRows(n = 5) {
    return raw(Array.from({ length: n }, () => `
        <div class="doc"><div class="skeleton" style="width:44px;height:52px"></div>
        <div><div class="skeleton" style="height:15px;width:55%"></div>
        <div class="skeleton" style="height:12px;width:35%;margin-top:8px"></div></div><span></span></div>`).join(''));
}

const SCAN = {
    clean: ['clean', 'check', 'Verificado'],
    pending: ['pending', 'clock', 'En revisión'],
    review: ['review', 'alert', 'Pendiente de un admin'],
    blocked: ['blocked', 'lock', 'Bloqueado'],
};

export function scanBadge(status, { onlyIssues = true } = {}) {
    if (onlyIssues && (status === 'clean' || !status)) return '';
    const [cls, ic, label] = SCAN[status] || SCAN.clean;
    return html`<span class="status status--${cls}">${icon(ic)}${label}</span>`;
}

export function countBadge(n) {
    return n > 0 ? html`<span class="nav__count">${n > 99 ? '99+' : n}</span>` : '';
}

export function field({ label, name, type = 'text', value = '', placeholder = '', required = false, hint = '', attrs = '' }) {
    const id = `f-${name}-${Math.random().toString(36).slice(2, 7)}`;
    return html`<label class="field" for="${id}">
        <span class="field__label">${label}</span>
        <input class="input" id="${id}" name="${name}" type="${type}" value="${value}" placeholder="${placeholder}" ${required ? raw('required') : ''} ${raw(attrs)}>
        ${hint ? html`<span class="field__hint">${hint}</span>` : ''}
    </label>`;
}

export function textarea({ label, name, value = '', placeholder = '', rows = 4, max = 2000 }) {
    return html`<label class="field">
        <span class="field__label">${label}</span>
        <textarea class="textarea" name="${name}" rows="${rows}" maxlength="${max}" placeholder="${placeholder}">${value}</textarea>
    </label>`;
}

export function errorBox(err) {
    const findings = err?.details?.findings?.filter((f) => f.severity !== 'info') || [];
    return html`<div class="form-error" role="alert">${icon('alert')}<div>${err?.message || String(err)}
        ${findings.length > 1 ? html`<ul>${findings.map((f) => html`<li>${f.message}</li>`)}</ul>` : ''}</div></div>`;
}
