/**
 * Configuración del frontend.
 *
 * Si la página la sirve el propio Flask (http://127.0.0.1:5001), se usan rutas
 * relativas: así no hay que tocar nada al cambiar de puerto ni configurar CORS.
 * Si se abre con Live Server u otro servidor estático, se apunta al backend.
 */
const BACKEND_FALLBACK = 'http://127.0.0.1:5001';

const servedByBackend = window.location.port === '5001';

const config = {
    API_URL: servedByBackend ? '' : BACKEND_FALLBACK
};

export { config };
