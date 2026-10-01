/**
 * Cliente del asistente de IA.
 *
 * El backend (app.py + ai_service.py) implementa estos endpoints con Ollama y
 * búsqueda en los documentos de la plataforma; ver docs/ASISTENTE_IA.md.
 * Si el servidor no los expone (404) o Ollama está apagado (503), este módulo
 * devuelve un estado "no disponible" en lugar de romper la interfaz.
 *
 * CONTRATO CON EL BACKEND
 * -----------------------
 * POST /api/ai/chat           (requiere JWT)
 *   Petición:  { "question": "texto", "conversation_id": "uuid|null" }
 *   Respuesta: {
 *     "answer": "texto de la respuesta",
 *     "conversation_id": "uuid",
 *     "sources": [
 *       { "resource_id": 12, "type": "public", "title": "Apuntes de Cálculo",
 *         "origin": "Biblioteca", "snippet": "fragmento citado", "score": 0.82 }
 *     ]
 *   }
 *
 * POST /api/ai/chat/stream    (requiere JWT) — misma petición, respuesta NDJSON:
 *   {"type":"sources","sources":[...]}  {"type":"token","content":"..."}  ...
 *   {"type":"done","conversation_id":"uuid","sources":[...]}   o   {"type":"error","message":"..."}
 *
 * GET /api/ai/status          (requiere JWT)
 *   Respuesta: { "available": true, "model": "llama3.1:8b",
 *                "search_mode": "hibrido", "indexed_documents": 37 }
 *
 * GET /api/ai/history?conversation_id=uuid   (requiere JWT, opcional)
 *   Respuesta: { "messages": [ {"role":"user|assistant","content":"...","created_at":"..."} ] }
 *
 * El campo `sources` es el que justifica usar RAG en lugar de un modelo suelto:
 * cada respuesta debe poder señalar de qué documento de la plataforma salió,
 * para que el estudiante pueda comprobarlo.
 */

import { config } from './config.js';

const ai = {
    baseURL: config.API_URL,

    /** Identificador de la conversación en curso; lo asigna el backend. */
    conversationId: null,

    /** Cache del estado para no consultarlo en cada apertura del widget. */
    _estado: null,

    getHeaders() {
        const headers = { 'Content-Type': 'application/json' };
        const token = localStorage.getItem('token');
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    },

    /**
     * Consulta si el asistente está operativo.
     * Devuelve siempre un objeto; nunca lanza, para que el widget pueda
     * renderizarse aunque el backend no responda.
     */
    async consultarEstado({ forzar = false } = {}) {
        if (this._estado && !forzar) return this._estado;

        try {
            const response = await fetch(`${this.baseURL}/api/ai/status`, {
                headers: this.getHeaders()
            });

            if (response.status === 404) {
                this._estado = {
                    disponible: false,
                    motivo: 'no_implementado',
                    mensaje: 'El asistente todavía no está conectado en el servidor.'
                };
                return this._estado;
            }

            if (!response.ok) {
                this._estado = {
                    disponible: false,
                    motivo: 'error',
                    mensaje: `El servidor respondió ${response.status}.`
                };
                return this._estado;
            }

            const datos = await response.json();
            this._estado = {
                disponible: !!datos.available,
                modelo: datos.model || null,
                documentosIndexados: datos.indexed_documents ?? null,
                mensaje: datos.available
                    ? 'Asistente disponible.'
                    : 'El asistente está configurado pero no responde en este momento.'
            };
            return this._estado;

        } catch (error) {
            this._estado = {
                disponible: false,
                motivo: 'sin_conexion',
                mensaje: 'No se pudo contactar con el servidor.'
            };
            return this._estado;
        }
    },

    /**
     * Envía una pregunta al asistente.
     *
     * Devuelve { ok: true, answer, sources } o { ok: false, motivo, mensaje }.
     * No lanza excepciones: el widget muestra el mensaje tal cual lo reciba.
     */
    async enviarPregunta(pregunta) {
        const texto = (pregunta || '').trim();
        if (!texto) {
            return { ok: false, motivo: 'vacio', mensaje: 'Escribe una pregunta.' };
        }

        try {
            const response = await fetch(`${this.baseURL}/api/ai/chat`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({
                    question: texto,
                    conversation_id: this.conversationId
                })
            });

            // El endpoint aún no existe: se avisa con claridad en vez de
            // mostrar un error genérico de red.
            if (response.status === 404) {
                return {
                    ok: false,
                    motivo: 'no_implementado',
                    mensaje: 'El asistente de IA todavía no está disponible. '
                        + 'La interfaz ya está lista; falta activarlo en el servidor.'
                };
            }

            if (response.status === 401 || response.status === 422) {
                return {
                    ok: false,
                    motivo: 'sesion',
                    mensaje: 'Tu sesión expiró. Inicia sesión de nuevo para usar el asistente.'
                };
            }

            if (!response.ok) {
                return this._errorDeRespuesta(response);
            }

            const datos = await response.json();
            if (datos.conversation_id) {
                this.conversationId = datos.conversation_id;
            }

            return {
                ok: true,
                answer: datos.answer || '',
                sources: Array.isArray(datos.sources) ? datos.sources : []
            };

        } catch (error) {
            return {
                ok: false,
                motivo: 'sin_conexion',
                mensaje: 'No se pudo contactar con el servidor. Comprueba que esté en marcha.'
            };
        }
    },

    /**
     * Igual que enviarPregunta, pero el texto llega conforme el modelo lo
     * escribe (POST /api/ai/chat/stream, NDJSON). Así el estudiante ve la
     * respuesta empezar en un par de segundos aunque tarde en terminar.
     *
     * `alRecibir({ texto, sources })` se llama con el texto acumulado cada vez
     * que llega un trozo. Devuelve lo mismo que enviarPregunta. Si el servidor
     * no tiene la ruta de streaming, recurre a enviarPregunta.
     */
    async enviarPreguntaStream(pregunta, alRecibir = () => {}) {
        const texto = (pregunta || '').trim();
        if (!texto) {
            return { ok: false, motivo: 'vacio', mensaje: 'Escribe una pregunta.' };
        }

        let response;
        try {
            response = await fetch(`${this.baseURL}/api/ai/chat/stream`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify({ question: texto, conversation_id: this.conversationId })
            });
        } catch (error) {
            return {
                ok: false,
                motivo: 'sin_conexion',
                mensaje: 'No se pudo contactar con el servidor. Comprueba que esté en marcha.'
            };
        }

        if (response.status === 404 || !response.body) {
            return this.enviarPregunta(texto);
        }
        if (!response.ok) {
            return this._errorDeRespuesta(response);
        }

        const lector = response.body.getReader();
        const decodificador = new TextDecoder();
        let pendiente = '';
        let acumulado = '';
        let sources = [];

        const procesarLinea = (linea) => {
            if (!linea.trim()) return null;
            const evento = JSON.parse(linea);
            if (evento.type === 'sources') {
                sources = Array.isArray(evento.sources) ? evento.sources : [];
            } else if (evento.type === 'token') {
                acumulado += evento.content || '';
                alRecibir({ texto: acumulado, sources });
            } else if (evento.type === 'done') {
                if (evento.conversation_id) this.conversationId = evento.conversation_id;
                // Al terminar, el servidor manda sólo las fuentes que la respuesta cita.
                if (Array.isArray(evento.sources)) sources = evento.sources;
                return { ok: true, answer: acumulado, sources };
            } else if (evento.type === 'error') {
                return { ok: false, motivo: 'modelo_caido', mensaje: evento.message };
            }
            return null;
        };

        try {
            while (true) {
                const { value, done } = await lector.read();
                if (done) break;
                pendiente += decodificador.decode(value, { stream: true });
                const lineas = pendiente.split('\n');
                pendiente = lineas.pop();
                for (const linea of lineas) {
                    const final = procesarLinea(linea);
                    if (final) return final;
                }
            }
            const final = procesarLinea(pendiente);
            if (final) return final;
        } catch (error) {
            return {
                ok: false,
                motivo: 'sin_conexion',
                mensaje: 'Se cortó la conexión mientras llegaba la respuesta.'
            };
        }

        // El flujo terminó sin "done": se devuelve lo que haya llegado.
        return acumulado
            ? { ok: true, answer: acumulado, sources }
            : { ok: false, motivo: 'error', mensaje: 'El servidor cerró la respuesta sin contenido.' };
    },

    /** Traduce una respuesta HTTP de error al formato { ok:false, motivo, mensaje }. */
    async _errorDeRespuesta(response) {
        let mensaje = null;
        try {
            const datos = await response.json();
            mensaje = datos.message || null;
        } catch (_) { /* la respuesta no era JSON */ }

        if (response.status === 401 || response.status === 422) {
            return {
                ok: false,
                motivo: 'sesion',
                mensaje: 'Tu sesión expiró. Inicia sesión de nuevo para usar el asistente.'
            };
        }
        if (response.status === 429) {
            return { ok: false, motivo: 'limite', mensaje: mensaje || 'Demasiadas preguntas seguidas. Espera un minuto.' };
        }
        if (response.status === 503) {
            return {
                ok: false,
                motivo: 'modelo_caido',
                mensaje: mensaje || 'El modelo de IA no está respondiendo en el servidor. Inténtalo más tarde.'
            };
        }
        return { ok: false, motivo: 'error', mensaje: mensaje || `El servidor respondió ${response.status}.` };
    },

    /** Empieza una conversación nueva (olvida el hilo anterior). */
    reiniciarConversacion() {
        this.conversationId = null;
    }
};

export { ai };
