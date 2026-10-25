/**
 * Cliente HTTP de la API (mismo origen: Flask sirve frontend y API).
 *
 * Todas las respuestas de error del backend tienen la forma
 * { message, code?, details? }; aquí se convierten en ApiError para que las
 * vistas muestren el mensaje tal cual.
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
    const options = { method, headers: headers() };
    if (form) {
        options.body = form;
    } else if (body !== undefined) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(body);
    }
    let response;
    try {
        response = await fetch(path, options);
    } catch {
        throw new ApiError('No hay conexión con el servidor. Revisa tu internet o que el servidor esté encendido.', 0, 'network');
    }
    const data = await parse(response);
    if (!response.ok) {
        if (response.status === 401 && token()) onUnauthorized(data.message);
        throw new ApiError(data.message || `Error ${response.status}`, response.status, data.code, data.details);
    }
    return data;
}

export const api = {
    ApiError,
    setUnauthorizedHandler(fn) { onUnauthorized = fn; },
    hasToken: () => !!token(),
    setToken(t) { tokenEnMemoria = t; try { localStorage.setItem(TOKEN_KEY, t); } catch { /* modo privado */ } },
    clearToken() { tokenEnMemoria = null; try { localStorage.removeItem(TOKEN_KEY); } catch { /* modo privado */ } },
    authHeaders: () => headers(),

    get: (path) => request(path),
    post: (path, body) => request(path, { method: 'POST', body: body ?? {} }),
    put: (path, body) => request(path, { method: 'PUT', body: body ?? {} }),
    del: (path) => request(path, { method: 'DELETE' }),
    upload: (path, formData, method = 'POST') => request(path, { method, form: formData }),

    /** Descarga un archivo protegido (las <a href> no pueden enviar el token). */
    async blob(path) {
        let response;
        try {
            response = await fetch(path, { headers: headers() });
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
        const response = await fetch(path, {
            method: 'POST',
            headers: headers({ 'Content-Type': 'application/json' }),
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
