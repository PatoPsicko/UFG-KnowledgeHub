/**
 * Cliente HTTP de la API (mismo origen: Flask sirve frontend y API).
 *
 * Todas las respuestas de error del backend tienen la forma
 * { message, code?, details? }; aquí se convierten en ApiError para que las
 * vistas muestren el mensaje tal cual.
 *
 * Sesión: el token de acceso dura unos 30 minutos. Cuando está por caducar (o
 * el servidor responde 401) se pide otro a /api/auth/refresh, que usa la
 * cookie HttpOnly de renovación: el estudiante no nota nada mientras la sesión
 * siga abierta en ese dispositivo.
 */

const TOKEN_KEY = 'token';

export class ApiError extends Error {
    constructor(message, status, code, details) {
        super(message);
        this.status = status;
        this.code = code;
        this.details = details;
    }
}

let onUnauthorized = () => {};
// Copia en memoria por si el navegador no deja usar localStorage (algunas web
// views de WhatsApp o Instagram, o el modo privado de Safari).
let tokenEnMemoria = null;

function token() {
    try { return localStorage.getItem(TOKEN_KEY) || tokenEnMemoria; } catch { return tokenEnMemoria; }
}

// Rutas que no deben intentar renovar la sesión (o se entraría en un bucle).
const SIN_RENOVAR = new Set(['/api/login', '/api/login/2fa', '/api/register', '/api/auth/refresh', '/api/auth/logout']);

function guardar(t) {
    tokenEnMemoria = t;
    try { localStorage.setItem(TOKEN_KEY, t); } catch { /* modo privado */ }
}

/** Segundos que le quedan al token de acceso (Infinity si no se puede leer). */
function restante(t) {
    try {
        const datos = JSON.parse(atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
        return datos.exp - Date.now() / 1000;
    } catch { return Infinity; }
}

// Una sola renovación a la vez aunque varias peticiones caduquen juntas.
let renovando = null;
function renovar() {
    renovando ??= fetch('/api/auth/refresh', { method: 'POST', headers: { 'X-Requested-With': 'fetch' } })
        .then(async (r) => {
            if (!r.ok) return false;
            guardar((await r.json()).token);
            return true;
        })
        .catch(() => false)
        .finally(() => { renovando = null; });
    return renovando;
}

/** fetch con el token; si caducó, renueva una vez y repite la petición. */
async function fetchAuth(path, init = {}) {
    const ruta = path.split('?')[0];
    const renovable = !SIN_RENOVAR.has(ruta);
    const t = token();
    if (renovable && t && restante(t) < 30) await renovar();
    const enviar = () => fetch(path, { ...init, headers: headers(init.headers) });
    let response = await enviar();
    if (response.status === 401 && renovable && await renovar()) response = await enviar();
    return response;
}

function headers(extra = {}) {
    const h = { ...extra };
    const t = token();
    if (t) h.Authorization = `Bearer ${t}`;
    return h;
}

async function parse(response) {
    const type = response.headers.get('content-type') || '';
    if (type.includes('application/json')) return response.json();
    const text = await response.text();
    return { message: text.slice(0, 200) || `Error ${response.status}` };
}

async function request(path, { method = 'GET', body, form } = {}) {
    const options = { method, headers: {} };
    if (form) {
        options.body = form;
    } else if (body !== undefined) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(body);
    }
    let response;
    try {
        response = await fetchAuth(path, options);
    } catch {
        throw new ApiError('No hay conexión con el servidor. Revisa tu internet o que el servidor esté encendido.', 0, 'network');
    }
    const data = await parse(response);
    if (!response.ok) {
        if (response.status === 401 && token() && !SIN_RENOVAR.has(path)) onUnauthorized(data.message);
        throw new ApiError(data.message || `Error ${response.status}`, response.status, data.code, data.details);
    }
    return data;
}

export const api = {
    ApiError,
    setUnauthorizedHandler(fn) { onUnauthorized = fn; },
    hasToken: () => !!token(),
    setToken: guardar,
    clearToken() { tokenEnMemoria = null; try { localStorage.removeItem(TOKEN_KEY); } catch { /* modo privado */ } },
    /** Recupera la sesión con la cookie de renovación (p. ej. si el navegador borró localStorage). */
    refresh: renovar,
    /** Cierra la sesión de este dispositivo en el servidor y olvida el token. */
    logout() {
        const h = headers();
        this.clearToken();
        return fetch('/api/auth/logout', { method: 'POST', headers: h, keepalive: true }).catch(() => {});
    },
    authHeaders: () => headers(),

    get: (path) => request(path),
    post: (path, body) => request(path, { method: 'POST', body: body ?? {} }),
    put: (path, body) => request(path, { method: 'PUT', body: body ?? {} }),
    del: (path, body) => request(path, { method: 'DELETE', body }),
    upload: (path, formData, method = 'POST') => request(path, { method, form: formData }),

    /** Descarga un archivo protegido (las <a href> no pueden enviar el token). */
    async blob(path) {
        let response;
        try {
            response = await fetchAuth(path);
        } catch {
            throw new ApiError('No hay conexión con el servidor.', 0, 'network');
        }
        if (!response.ok) {
            const data = await parse(response);
            throw new ApiError(data.message || `Error ${response.status}`, response.status, data.code);
        }
        return response.blob();
    },

    /** Enlace firmado de unos minutos para abrir o bajar un archivo sin cabeceras (ver hub/api/files.py). */
    async link(path) {
        return (await request('/api/files/link', { method: 'POST', body: { path } })).url;
    },

    /**
     * Descarga con un enlace normal en vez de un «blob»: así funciona también
     * dentro de las web views del celular, que pasan el archivo al gestor de
     * descargas del teléfono.
     */
    async download(path, filename) {
        const url = await this.link(path.includes('?') ? path : `${path}?download=1`);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || '';
        a.rel = 'noopener';
        document.body.appendChild(a);
        a.click();
        a.remove();
    },

    /** POST con respuesta NDJSON (streaming del asistente). */
    async stream(path, body, onEvent, signal) {
        const response = await fetchAuth(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal,
        });
        if (!response.ok || !response.body) {
            const data = await parse(response);
            if (response.status === 401 && token()) onUnauthorized(data.message);
            throw new ApiError(data.message || `Error ${response.status}`, response.status, data.code);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();
            for (const line of lines) {
                if (line.trim()) onEvent(JSON.parse(line));
            }
        }
        if (buffer.trim()) onEvent(JSON.parse(buffer));
    },
};
