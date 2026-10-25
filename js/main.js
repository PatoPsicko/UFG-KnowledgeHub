/**
 * Punto de entrada del frontend.
 *
 *   core/   cliente de la API, plantillas seguras, enrutador, estado y sondeo
 *   ui/     iconos, componentes, diálogos y conversación reutilizable
 *   views/  una vista por sección (inicio, biblioteca, asistente, mensajes...)
 */

import { api } from './core/api.js';
import { html, setHtml } from './core/dom.js';
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

// Tema guardado (o el del sistema) antes de pintar nada.
try {
    const tema = localStorage.getItem('theme')
        || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.dataset.theme = tema;
} catch { /* sin almacenamiento */ }

router.route('/inicio', homeView, { title: 'Inicio' });
router.route('/biblioteca', libraryView, { title: 'Biblioteca' });
router.route('/asistente', assistantView, { title: 'Asistente' });
router.route('/grupos', groupsView, { title: 'Grupos' });
router.route('/grupos/:id', groupsView, { title: 'Grupo' });
router.route('/anotaciones', notesView, { title: 'Mi espacio' });
router.route('/perfil', profileView, { title: 'Mi perfil' });
router.route('/seguridad', securityView, { title: 'Seguridad' });

let arrancado = false;

function entrar(user) {
    store.setUser(user);
    renderShell(root, { onLogout: salir });
    router.onRouteChange((_meta, path) => setActiveNav(path));
    if (!arrancado) {
        router.start();
        arrancado = true;
    } else {
        router.resolve();
    }
    pulse.start();
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
    if (!api.hasToken()) return renderAuth(root, { onLogin: entrar });
    try {
        const { user } = await api.get('/api/me');
        entrar(user);
    } catch (err) {
        if (err.status === 401) return;  // salir() ya mostró el acceso
        setHtml(root, html`<div class="boot"><div class="empty"><h3>No se pudo conectar con el servidor</h3>
            <p>${err.message}</p><button class="btn btn--primary" id="retry">Reintentar</button></div></div>`);
        document.getElementById('retry').addEventListener('click', () => location.reload());
    }
}

boot();
