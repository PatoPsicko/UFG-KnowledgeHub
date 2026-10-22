/**
 * Sondeo del «pulso»: cada 4 s con la pestaña visible, cada 25 s en segundo
 * plano, y con espera creciente si el servidor no responde. Una sola petición
 * ligera mantiene al día los contadores de mensajes, grupos y notificaciones.
 */

import { api } from './api.js';
import { store } from './store.js';

const VISIBLE_MS = 4000;
const HIDDEN_MS = 25000;
let timer = null;
let fallos = 0;
let activo = false;

async function tick() {
    if (!activo) return;
    try {
        store.setPulse(await api.get('/api/pulse'));
        fallos = 0;
    } catch (err) {
        fallos += 1;
        if (err.status === 401) return stop();
    }
    programar();
}

function programar() {
    clearTimeout(timer);
    if (!activo) return;
    const base = document.hidden ? HIDDEN_MS : VISIBLE_MS;
    timer = setTimeout(tick, Math.min(base * 2 ** Math.min(fallos, 3), 60000));
}

function alCambiarVisibilidad() {
    if (!document.hidden && activo) {
        clearTimeout(timer);
        tick();
    }
}

export function start() {
    if (activo) return;
    activo = true;
    document.addEventListener('visibilitychange', alCambiarVisibilidad);
    tick();
}

export function stop() {
    activo = false;
    clearTimeout(timer);
    document.removeEventListener('visibilitychange', alCambiarVisibilidad);
}

/** Pide un pulso inmediato (después de enviar un mensaje, por ejemplo). */
export function now() {
    if (activo) {
        clearTimeout(timer);
        tick();
    }
}
