/**
 * Preferencias de la interfaz: tema, animaciones y orden de la biblioteca.
 *
 * Se aplican al instante con lo guardado en este navegador y, con la sesión
 * iniciada, también se guardan en el servidor (PUT /api/profile/preferences)
 * para que te sigan al celular o a otra computadora.
 *
 *   theme         system | light | dark
 *   motion        system | reduced | full   (system = lo que diga el sistema operativo)
 *   library_sort  recent | popular | title
 */

import { api } from './api.js';
import { store } from './store.js';

const CLAVE = 'prefs';
const DEFECTO = { theme: 'system', motion: 'system', library_sort: 'recent' };
const oscuroSistema = matchMedia('(prefers-color-scheme: dark)');
const quietoSistema = matchMedia('(prefers-reduced-motion: reduce)');

function leerLocal() {
    try {
        const datos = JSON.parse(localStorage.getItem(CLAVE) || '{}');
        // Versión anterior: sólo se guardaba el tema, con su propia clave.
        const tema = localStorage.getItem('theme');
        if (tema && !datos.theme) datos.theme = tema;
        return datos && typeof datos === 'object' ? datos : {};
    } catch {
        return {};
    }
}

let actuales = { ...DEFECTO, ...leerLocal() };

function guardarLocal() {
    try { localStorage.setItem(CLAVE, JSON.stringify(actuales)); } catch { /* sin almacenamiento */ }
}

/** Pone data-theme y data-motion en <html>; el CSS hace el resto. */
export function applyPrefs() {
    const raiz = document.documentElement;
    const oscuro = actuales.theme === 'dark' || (actuales.theme === 'system' && oscuroSistema.matches);
    raiz.dataset.theme = oscuro ? 'dark' : 'light';
    const quieto = actuales.motion === 'reduced' || (actuales.motion === 'system' && quietoSistema.matches);
    raiz.dataset.motion = quieto ? 'reduced' : 'full';
    store.emit('prefs', { ...actuales });
}

oscuroSistema.addEventListener?.('change', applyPrefs);
quietoSistema.addEventListener?.('change', applyPrefs);

export const prefs = {
    get: (clave) => actuales[clave],
    all: () => ({ ...actuales }),
    isDark: () => document.documentElement.dataset.theme === 'dark',
    reducedMotion: () => document.documentElement.dataset.motion === 'reduced',

    /** Al iniciar sesión: lo guardado en el servidor manda sobre lo local. */
    fromUser(user) {
        const remotas = user?.preferences || {};
        const locales = { ...actuales };
        actuales = { ...DEFECTO, ...actuales, ...remotas };
        guardarLocal();
        applyPrefs();
        // Si el servidor aún no tenía nada, se sube lo que había en este navegador.
        const subir = Object.fromEntries(Object.entries(locales).filter(([k, v]) => !(k in remotas) && v !== DEFECTO[k]));
        if (Object.keys(subir).length) api.put('/api/profile/preferences', subir).catch(() => {});
    },

    async set(cambios) {
        actuales = { ...actuales, ...cambios };
        guardarLocal();
        applyPrefs();
        if (api.hasToken()) {
            try { await api.put('/api/profile/preferences', cambios); } catch { /* se queda local */ }
        }
    },
};
