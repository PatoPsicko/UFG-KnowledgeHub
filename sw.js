/**
 * Service worker de UFG Knowledge Hub (app instalable).
 *
 * Estrategia «primero la red»: siempre se pide la versión actual al servidor
 * (así nadie se queda con JavaScript viejo) y la copia guardada sólo se usa
 * si no hay conexión, para que la app al menos abra y diga qué pasa.
 * La API (/api/...) nunca se guarda: son datos privados de cada estudiante.
 */

const CACHE = 'ufg-hub-v2';
const BASICO = ['/', '/css/app.css', '/js/main.js', '/img/logo_hub.png', '/img/icons/icon-192.png'];

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE).then((c) => c.addAll(BASICO)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(caches.keys()
        .then((claves) => Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
        .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    const url = new URL(req.url);
    if (req.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
    event.respondWith(
        fetch(req).then((resp) => {
            if (resp.ok && resp.type === 'basic') {
                const copia = resp.clone();
                caches.open(CACHE).then((c) => c.put(req, copia));
            }
            return resp;
        }).catch(async () => {
            const guardada = await caches.match(req);
            if (guardada) return guardada;
            if (req.mode === 'navigate') return caches.match('/');
            return Response.error();
        }),
    );
});
