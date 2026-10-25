/**
 * Punto de entrada del frontend.
 *
 *   core/   cliente de la API, plantillas seguras, enrutador, estado, sondeo y preferencias
 *   ui/     iconos, componentes, diálogos y conversación reutilizable
 *   views/  una vista por sección (inicio, biblioteca, asistente, grupos...)
 */

import { api } from './core/api.js';
import { html, setHtml } from './core/dom.js';
import { applyPrefs, prefs } from './core/prefs.js';
import * as pulse from './core/pulse.js';
import * as router from './core/router.js';
import { store } from './core/store.js';
import { toast } from './ui/overlay.js';
import { assistantView } from './views/assistant.js';
import { renderAuth } from './views/auth.js';
import { groupsView } from './views/groups.js';
import { homeView } from './views/home.js';
import { libraryView } from './views/library.js';
import { notesView } from './views/notes.js';
import { profileView } from './views/profile.js';
import { securityView } from './views/security.js';
import { renderShell, setActiveNav } from './views/shell.js';

const root = document.getElementById('app-root');

// Tema y animaciones guardados (o los del sistema) antes de pintar nada.
applyPrefs();

router.route('/inicio', homeView, { title: 'Inicio' });
router.route('/biblioteca', libraryView, { title: 'Biblioteca' });
router.route('/asistente', assistantView, { title: 'Asistente' });
router.route('/grupos', groupsView, { title: 'Grupos' });
router.route('/grupos/:id', groupsView, { title: 'Grupo' });
router.route('/anotaciones', notesView, { title: 'Mi espacio' });
router.route('/perfil', profileView, { title: 'Mi perfil' });
router.route('/seguridad', securityView, { title: 'Seguridad' });

/* --- Pantalla de entrada ---------------------------------------------------------
   El logo con su línea de luz se pinta desde index.html antes de que cargue el
   JavaScript. Se retira cuando la app ya tiene algo que mostrar; la primera
   vez de cada sesión se deja ver al menos ~0,7 s para que no sea un parpadeo. */
function hideSplash() {
    const splash = document.getElementById('splash');
    if (!splash || splash.classList.contains('is-leaving')) return;
    let primeraVez = true;
    try {
        primeraVez = !sessionStorage.getItem('splash');
        sessionStorage.setItem('splash', '1');
    } catch { /* sin almacenamiento */ }
    const minimo = primeraVez && !prefs.reducedMotion() ? 700 : 0;
    const espera = Math.max(0, minimo - performance.now());
    setTimeout(() => {
        splash.classList.add('is-leaving');
        setTimeout(() => splash.remove(), 500);
    }, espera);
}

/* --- App instalable (PWA) ------------------------------------------------------- */
if ('serviceWorker' in navigator && (location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname))) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
}
// Chrome y Edge avisan cuando la app se puede instalar; el botón «Instalar app»
// del menú usa este evento (en iPhone se instala desde Compartir → «Agregar a inicio»).
window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    store.installPrompt = e;
    store.emit('install', true);
});
window.addEventListener('appinstalled', () => {
    store.installPrompt = null;
    store.emit('install', false);
    toast('App instalada. Ábrela desde tu pantalla de inicio.');
});

/* --- Aviso tras abrir el enlace de verificación del correo ----------------------- */
function avisoVerificacion() {
    const estado = new URLSearchParams(location.search).get('verificacion');
    if (!estado) return;
    history.replaceState(null, '', location.pathname + location.hash);
    const textos = {
        ok: ['Correo confirmado. Ya puedes iniciar sesión.', 'success'],
        caducada: ['El enlace caducó. Inicia sesión para pedir otro.', 'error'],
        invalida: ['El enlace de verificación no es válido.', 'error'],
    };
    const [texto, tipo] = textos[estado] || textos.invalida;
    toast(texto, tipo, 6000);
}

let arrancado = false;

function entrar(user) {
    store.setUser(user);
    prefs.fromUser(user);
    renderShell(root, { onLogout: salir });
    router.onRouteChange((_meta, path) => setActiveNav(path));
    if (!arrancado) {
        router.start();
        arrancado = true;
    } else {
        router.resolve();
    }
    pulse.start();
    hideSplash();
}

function salir(motivo) {
    pulse.stop();
    api.clearToken();
    store.setUser(null);
    if (motivo) toast(motivo, 'info');
    location.hash = '';
    renderAuth(root, { onLogin: entrar });
}

api.setUnauthorizedHandler((mensaje) => salir(mensaje || 'Tu sesión expiró. Inicia sesión de nuevo.'));

async function boot() {
    avisoVerificacion();
    if (!api.hasToken()) {
        renderAuth(root, { onLogin: entrar });
        return hideSplash();
    }
    try {
        const { user } = await api.get('/api/me');
        entrar(user);
    } catch (err) {
        hideSplash();
        if (err.status === 401) return;  // salir() ya mostró el acceso
        setHtml(root, html`<div class="boot"><div class="empty"><h3>No se pudo conectar con el servidor</h3>
            <p>${err.message}</p><button class="btn btn--primary" id="retry">Reintentar</button></div></div>`);
        document.getElementById('retry').addEventListener('click', () => location.reload());
    }
}

boot();
