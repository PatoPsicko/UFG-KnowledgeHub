/**
 * Inicio: un librero de madera visto de frente. Cada libro es un módulo; al
 * pasar el ratón el libro sobresale y al tocarlo se «saca» y abre su sección.
 * En la computadora es una sola repisa; en el celular, dos (3 arriba y 2 abajo).
 */

import { html, on, setHtml } from '../core/dom.js';
import { prefs } from '../core/prefs.js';
import { go } from '../core/router.js';
import { store } from '../core/store.js';
import { SECTIONS } from '../data/sections.js';
import { icon } from '../ui/icons.js';

// Alto (en % de la repisa) y ancho relativo de cada libro: no todos iguales,
// como en un librero de verdad. El último va inclinado.
const FORMA = [
    { h: 90, w: 1.05 }, { h: 97, w: 1.1 }, { h: 93, w: 1.2 }, { h: 86, w: 1 }, { h: 91, w: 1.05, lean: true },
];

function bookHtml(s, i, pulse) {
    const f = FORMA[i];
    const n = s.badge ? s.badge(pulse) : 0;
    return html`<a class="book ${f.lean ? 'book--lean' : ''}" href="#${s.path}" data-path="${s.path}"
        style="--book:${s.color};--h:${f.h}%;--w:${f.w};--i:${i}" aria-label="${s.label}: ${s.blurb}">
        <span class="book__body">
            <span class="book__cap">${icon(s.icon)}</span>
            <span class="book__title">${s.label}</span>
            <span class="book__foot">UFG</span>
        </span>
        ${n > 0 ? html`<span class="book__ribbon" title="${n} sin leer">${n > 99 ? '99+' : n}</span>` : ''}
    </a>`;
}

function shelfHtml(libros, desde, pulse) {
    return html`<div class="bookcase__shelf">
        <div class="bookcase__books">${libros.map((s, k) => bookHtml(s, desde + k, pulse))}</div>
        <div class="bookcase__plank"></div>
    </div>`;
}

const celular = matchMedia('(max-width: 720px)');

export async function shelfView(root, _params, signal) {
    const nombre = store.user.name.split(' ')[0];

    const pintar = () => {
        const repisas = celular.matches
            ? html`${shelfHtml(SECTIONS.slice(0, 3), 0, store.pulse)}${shelfHtml(SECTIONS.slice(3), 3, store.pulse)}`
            : shelfHtml(SECTIONS, 0, store.pulse);
        setHtml(root, html`<div class="lobby">
            <header class="lobby__head">
                <img class="lobby__logo" src="img/logo_hub.png" alt="UFG">
                <span class="lobby__product">Knowledge Hub</span>
                <p class="lobby__hello">Hola, ${nombre}. Toma un libro para empezar.</p>
            </header>
            <div class="bookcase">${repisas}</div>
        </div>`);
    };
    pintar();
    celular.addEventListener('change', pintar, { signal });
    store.on('pulse', ({ pulse, previo }) => {
        if (pulse.groups_unread_total !== previo?.groups_unread_total) pintar();
    }, signal);

    // Al tocar, el libro sale de la repisa y luego se abre el módulo.
    on(root, 'click', '.book', (e, libro) => {
        e.preventDefault();
        if (prefs.reducedMotion()) return go(libro.dataset.path);
        libro.classList.add('is-taken');
        root.querySelector('.bookcase')?.classList.add('is-leaving');
        setTimeout(() => go(libro.dataset.path), 320);
    }, signal);
}
