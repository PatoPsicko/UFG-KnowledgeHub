/**
 * Cliente del asistente de IA.
 *
 * ESTADO ACTUAL: el backend todavía NO expone estos endpoints. Este módulo está
 * escrito contra el contrato que se implementará más adelante (ver README y el
 * documento de trabajo futuro). Mientras el backend no exista, `enviarPregunta`
 * detecta el 404 y devuelve un estado "no disponible" en lugar de romper la
 * interfaz: el widget se ve, se puede abrir y avisa de que el asistente aún no
 * está conectado.
 *
 * CONTRATO QUE DEBERÁ IMPLEMENTAR EL BACKEND
 * ------------------------------------------
 * POST /api/ai/chat           (requiere JWT)
 *   Petición:  { "question": "texto", "conversation_id": "uuid|null" }
 *   Respuesta: {
 *     "answer": "texto de la respuesta",
 *     "conversation_id": "uuid",
 *     "sources": [
 *       { "resource_id": 12, "title": "Apuntes de Cálculo",
 *         "snippet": "fragmento citado", "score": 0.82 }
 *     ]
 *   }
 *
 * GET /api/ai/status          (requiere JWT)
 *   Respuesta: { "available": true, "model": "llama3.1:8b", "indexed_documents": 37 }
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

            if (response.status === 503) {
                return {
                    ok: false,
                    motivo: 'modelo_caido',
                    mensaje: 'El modelo de IA no está respondiendo en el servidor. Inténtalo más tarde.'
                };
            }

            if (!response.ok) {
                let mensaje = `El servidor respondió ${response.status}.`;
                try {
                    const datos = await response.json();
                    if (datos.message) mensaje = datos.message;
                } catch (_) { /* la respuesta no era JSON */ }
                return { ok: false, motivo: 'error', mensaje };
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

    /** Empieza una conversación nueva (olvida el hilo anterior). */
    reiniciarConversacion() {
        this.conversationId = null;
    }
};

export { ai };
