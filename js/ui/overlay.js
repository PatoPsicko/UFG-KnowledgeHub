/** Avisos (toasts), diálogos nativos <dialog>, paneles laterales y menús. */

import { $, html, setHtml } from '../core/dom.js';
import { icon } from './icons.js';

/* --- Avisos ----------------------------------------------------------------- */
export function toast(message, type = 'success', ms = 3800) {
    let box = $('.toasts');
    if (!box) {
        box = document.createElement('div');
        box.className = 'toasts';
        box.setAttribute('aria-live', 'polite');
        document.body.appendChild(box);
    }
    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    setHtml(el, html`${icon(type === 'error' ? 'alert' : type === 'info' ? 'info' : 'check')}<span>${message}</span>`);
    box.appendChild(el);
    setTimeout(() => {
        el.classList.add('is-leaving');
        setTimeout(() => el.remove(), 220);
    }, ms);
}

/* --- Diálogos ----------------------------------------------------------------- */
/**
 * Abre un <dialog>. `body` es HTML seguro; `onSubmit(form, dialog)` recibe el
 * formulario y puede devolver false para no cerrar. Devuelve el elemento.
 */
export function openDialog({ title, description = '', body = '', submitLabel = 'Guardar', cancelLabel = 'Cancelar',
                             danger = false, wide = false, onSubmit = null, onOpen = null, footer = true }) {
    const dlg = document.createElement('dialog');
    dlg.className = `dialog${wide ? ' dialog--wide' : ''}`;
    setHtml(dlg, html`<form method="dialog" novalidate>
        <div class="dialog__head">
            <div><h2>${title}</h2>${description ? html`<p>${description}</p>` : ''}</div>
            <button type="button" class="icon-btn icon-btn--sm" data-close aria-label="Cerrar">${icon('x')}</button>
        </div>
        <div class="dialog__body">${body}<div class="dialog__error"></div></div>
        ${footer ? html`<div class="dialog__foot">
            <button type="button" class="btn btn--secondary" data-close>${cancelLabel}</button>
            ${onSubmit ? html`<button type="submit" class="btn ${danger ? 'btn--danger' : 'btn--primary'}">${submitLabel}</button>` : ''}
        </div>` : ''}
    </form>`);
    document.body.appendChild(dlg);
    const form = dlg.querySelector('form');
    const cerrar = () => dlg.close();
    dlg.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', cerrar));
    dlg.addEventListener('close', () => dlg.remove());
    dlg.addEventListener('click', (e) => { if (e.target === dlg) cerrar(); });
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!onSubmit) return cerrar();
        const boton = form.querySelector('[type="submit"]');
        const error = dlg.querySelector('.dialog__error');
        setHtml(error, '');
        boton.disabled = true;
        const texto = boton.innerHTML;
        boton.innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px"></span>';
        try {
            const resultado = await onSubmit(form, dlg);
            if (resultado !== false) cerrar();
        } catch (err) {
            const { errorBox } = await import('./components.js');
            setHtml(error, errorBox(err));
        } finally {
            boton.disabled = false;
            boton.innerHTML = texto;
        }
    });
    dlg.showModal();
    onOpen?.(dlg, form);
    return dlg;
}

export function confirmDialog({ title, text, confirmLabel = 'Confirmar', danger = true }) {
    return new Promise((resolve) => {
        let ok = false;
        const dlg = openDialog({
            title, body: html`<p>${text}</p>`, submitLabel: confirmLabel, danger,
            onSubmit: () => { ok = true; },
        });
        dlg.addEventListener('close', () => resolve(ok));
    });
}

/* --- Panel lateral -------------------------------------------------------------- */
export function openDrawer(content, { onClose } = {}) {
    closeDrawer();
    const backdrop = document.createElement('div');
    backdrop.className = 'drawer-backdrop';
    const drawer = document.createElement('aside');
    drawer.className = 'drawer';
    drawer.setAttribute('role', 'dialog');
    drawer.setAttribute('aria-modal', 'true');
    setHtml(drawer, content);
    document.body.append(backdrop, drawer);
    requestAnimationFrame(() => { backdrop.classList.add('is-open'); drawer.classList.add('is-open'); });
    const cerrar = () => closeDrawer();
    backdrop.addEventListener('click', cerrar);
    drawer.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', cerrar));
    const alTeclado = (e) => { if (e.key === 'Escape') cerrar(); };
    document.addEventListener('keydown', alTeclado);
    drawer._cleanup = () => { document.removeEventListener('keydown', alTeclado); onClose?.(); };
    drawer.querySelector('[data-close]')?.focus();
    return drawer;
}

export function closeDrawer() {
    document.querySelectorAll('.drawer').forEach((d) => {
        d._cleanup?.();
        d.classList.remove('is-open');
        setTimeout(() => d.remove(), 260);
    });
    document.querySelectorAll('.drawer-backdrop').forEach((b) => {
        b.classList.remove('is-open');
        setTimeout(() => b.remove(), 220);
    });
}

/* --- Menú contextual ------------------------------------------------------------ */
export function openMenu(anchor, items) {
    closeMenu();
    const menu = document.createElement('div');
    menu.className = 'menu';
    menu.setAttribute('role', 'menu');
    setHtml(menu, html`${items.map((it, i) => html`<button type="button" role="menuitem" data-i="${i}" class="${it.danger ? 'is-danger' : ''}">${icon(it.icon || 'chevronRight')}${it.label}</button>`)}`);
    document.body.appendChild(menu);
    const r = anchor.getBoundingClientRect();
    const ancho = 200;
    menu.style.top = `${r.bottom + window.scrollY + 4}px`;
    menu.style.left = `${Math.max(8, Math.min(r.right - ancho, window.innerWidth - ancho - 8)) + window.scrollX}px`;
    menu.addEventListener('click', (e) => {
        const b = e.target.closest('button[data-i]');
        if (!b) return;
        closeMenu();
        items[Number(b.dataset.i)].onSelect();
    });
    setTimeout(() => document.addEventListener('click', closeMenu, { once: true }), 0);
    menu.querySelector('button')?.focus();
}

export function closeMenu() {
    document.querySelectorAll('.menu').forEach((m) => m.remove());
}
