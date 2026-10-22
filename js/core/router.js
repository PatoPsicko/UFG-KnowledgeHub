/**
 * Enrutador por hash: #/biblioteca, #/grupos/12, #/mensajes/global ...
 * Cada vista recibe (root, params, signal); el AbortSignal se dispara al salir
 * de la vista para que limpie sus escuchadores y temporizadores.
 */

const routes = [];
let controller = null;
let onChange = () => {};

export function route(pattern, view, meta = {}) {
    const keys = [];
    const regex = new RegExp('^' + pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/]+)'; }) + '/?$');
    routes.push({ regex, keys, view, meta, pattern });
}

export function current() {
    return location.hash.replace(/^#/, '') || '/inicio';
}

export function go(path) {
    if (current() === path) {
        resolve();
    } else {
        location.hash = path;
    }
}

export function onRouteChange(fn) {
    onChange = fn;
}

export async function resolve() {
    const path = current().split('?')[0];
    const match = routes.find((r) => r.regex.test(path)) || routes.find((r) => r.pattern === '/inicio');
    const values = path.match(match.regex)?.slice(1) || [];
    const params = Object.fromEntries(match.keys.map((k, i) => [k, decodeURIComponent(values[i] || '')]));
    const query = Object.fromEntries(new URLSearchParams(current().split('?')[1] || ''));

    controller?.abort();
    controller = new AbortController();
    const root = document.getElementById('view');
    if (!root) return;
    onChange(match.meta, path);
    root.scrollTop = 0;
    window.scrollTo(0, 0);
    try {
        await match.view(root, { ...params, query }, controller.signal);
    } catch (err) {
        if (err.name === 'AbortError') return;
        console.error(err);
        root.innerHTML = `<div class="page"><div class="empty"><h3>No se pudo cargar esta sección</h3>
            <p>${String(err.message || err).replace(/[<>&]/g, '')}</p></div></div>`;
    }
}

export function start() {
    window.addEventListener('hashchange', resolve);
    resolve();
}
