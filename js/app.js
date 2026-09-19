import { config } from './config.js';
import { api } from './api.js';
import { ai } from './ai.js';
import { templates } from './ui.js';

/**
 * Aplicación Principal - MEJORADO CON SISTEMA DE AVATARES POR COLOR Y PERFILES DE CONTACTOS
 */
const App = {
    /**
     * State: Almacena el estado de la aplicación
     */
    state: {
        user: {
            name: null,
            id: null,
            token: null,
            email: null,
            career: null,
            semester: null,
            profile_color: null
        },
        currentView: 'home',
        resources: [],
        contacts: [],
        groups: [],
        privateResources: [],
        chatMessages: [],
        directMessages: {},
        selectedContact: null,
        notifications: [],
        currentGroup: null,

        /**
         * Conversación con el asistente de IA. Vive sólo en memoria: cuando el
         * backend implemente /api/ai/history se podrá rehidratar desde ahí.
         */
        aiMessages: [],
        aiPanelAbierto: false,
        aiEnviando: false,

        setUser(userData) {
            this.user.name = userData.name;
            this.user.id = userData.id;
            this.user.token = userData.token;
            this.user.email = userData.email;
            this.user.career = userData.career;
            this.user.semester = userData.semester;
            this.user.profile_color = userData.profile_color;
        },
        
        clearUser() {
            this.user.name = null;
            this.user.id = null;
            this.user.token = null;
            this.user.email = null;
            this.user.career = null;
            this.user.semester = null;
            this.user.profile_color = null;
            localStorage.removeItem('token');
        },

        setResources(resources) {
            this.resources = resources;
        },

        setContacts(contacts) {
            this.contacts = contacts;
        },

        setGroups(groups) {
            this.groups = groups;
        },

        setPrivateResources(resources) {
            this.privateResources = resources;
        },

        setChatMessages(messages) {
            this.chatMessages = messages;
        }
    },

    /**
     * View: Métodos para renderizar la UI
     */
    view: {
        render: (selector, html) => {
             const element = document.getElementById(selector);
             if (element) {
                 element.innerHTML = html;
             }
         },

        renderTableRows(resources, currentUserId) {
            const tableBody = document.getElementById('resource-table-body');
            if (tableBody) {
                tableBody.innerHTML = templates.resourceTableRows(resources, currentUserId);
            }
        },

        toggleModal(show = false, resource = null, currentUserName = '', isPrivate = false) {
            const modalOverlay = document.getElementById('resource-modal-overlay');
            
            if (show) {
                modalOverlay.innerHTML = templates.resourceModal(resource, currentUserName, isPrivate);
                modalOverlay.classList.remove('hidden');
                modalOverlay.classList.add('flex');
                
                modalOverlay.onclick = (e) => {
                    if (e.target === modalOverlay) {
                        this.toggleModal(false);
                    }
                };
                
                setTimeout(() => {
                    templates.addTagSuggestionsListeners();
                }, 100);
            } else {
                modalOverlay.innerHTML = '';
                modalOverlay.classList.add('hidden');
                modalOverlay.classList.remove('flex');
                modalOverlay.onclick = null;
            }
        },

        toggleGroupModal(show = false) {
            const modal = document.getElementById('create-group-modal');
            if (show) {
                modal.classList.remove('hidden');
                modal.classList.add('flex');
            } else {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        },

        toggleNoteModal(show = false, note = null) {
            const modal = document.getElementById('note-modal');
            if (show) {
                if (note) {
                    document.getElementById('note-modal-title').textContent = 'Editar Nota';
                    document.getElementById('note-id').value = note.id;
                    document.getElementById('note-title').value = note.title;
                    document.getElementById('note-content').value = note.content || '';
                } else {
                    document.getElementById('note-modal-title').textContent = 'Nueva Nota';
                    document.getElementById('note-id').value = '';
                    document.getElementById('note-title').value = '';
                    document.getElementById('note-content').value = '';
                }
                modal.classList.remove('hidden');
                modal.classList.add('flex');
            } else {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        },

        toggleGroupDetailModal(show = false, group = null) {
            const modal = document.getElementById('group-detail-modal');
            if (show && group) {
                modal.innerHTML = templates.groupDetailModal(group);
                modal.classList.remove('hidden');
                modal.classList.add('flex');
            } else {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        }
    },

    /**
     * Controller: Lógica de negocio y manejo de eventos
     */
    controller: {
        /**
         * Inicializa la aplicación
         */
        init() {
            App.controller.addEventListeners();
            App.controller.checkAuth();
        },

        /**
         * Comprueba si el usuario ya está autenticado
         */
        async checkAuth() {
            const token = localStorage.getItem('token');
            console.log("🔐 Verificando autenticación, token existe:", !!token);
            
            if (token) {
                try {
                    const verification = await api.verifyToken();
                    if (verification.valid) {
                        console.log("✅ Token válido, mostrando dashboard");
                        App.state.setUser(verification.user);
                        await this.showDashboard();
                    } else {
                        throw new Error('Token inválido');
                    }
                } catch (error) {
                    console.error("❌ Fallo en checkAuth:", error);
                    this.showLogin();
                }
            } else {
                console.log("🔐 No hay token, mostrando login");
                this.showLogin();
            }
        },

        /**
         * Muestra la pantalla de Inicio de Sesión
         */
        showLogin() {
            App.view.render('app-root', templates.loginScreen());
        },

        /**
         * Muestra la pantalla de Registro
         */
        showRegister() {
            App.view.render('app-root', templates.registerScreen());
        },

        async showDashboard() {
            const initialUserName = App.state.user.name || 'Usuario';
            App.view.render('app-root', templates.dashboardScreen(initialUserName, ''));
            
            // RECUPERAR la vista anterior de localStorage, o usar 'home' por defecto
            const savedView = localStorage.getItem('currentView') || 'home';
            App.state.currentView = savedView;
            
            const sidebarUl = document.querySelector('#app-sidebar ul');
            if (sidebarUl) {
                sidebarUl.innerHTML = templates.sidebarLinks(savedView);
            }
            
            await this.loadViewContent(savedView);
            this.startPolling();
        },

        /**
         * Inicia el polling para actualizaciones en tiempo real
         */
        /**
         * Temporizadores activos. Se guardan para poder cancelarlos: antes cada
         * llamada a showDashboard() creaba dos setInterval nuevos sin limpiar los
         * anteriores, así que tras varios inicios de sesión la app consultaba al
         * servidor una vez por cada sesión abierta en la pestaña.
         */
        pollingTimers: [],

        startPolling() {
            this.stopPolling();

            this.pollingTimers.push(setInterval(async () => {
                if (App.state.user.id) {
                    await this.loadNotifications();
                }
            }, 30000));

            this.pollingTimers.push(setInterval(async () => {
                if (App.state.currentView === 'home' && App.state.user.id) {
                    await this.loadChatMessages();
                }
            }, 10000));
        },

        stopPolling() {
            this.pollingTimers.forEach(clearInterval);
            this.pollingTimers = [];
        },

        /**
         * Carga el contenido de la vista seleccionada y guarda en localStorage
         */
        async loadViewContent(viewId) {
            // GUARDAR la vista actual en localStorage
            localStorage.setItem('currentView', viewId);
            App.state.currentView = viewId;
            
            const contentEl = document.getElementById('dashboard-content');
            if (!contentEl) return;
            
            contentEl.innerHTML = '<div class="text-center p-8 text-gray-500">Cargando...</div>';

            try {
                switch (viewId) {
                    case 'home':
                        await this.loadHomeContent();
                        break;
                    case 'library':
                        await this.loadLibraryContent();
                        break;
                    case 'groups':
                        await this.loadGroupsContent();
                        break;
                    case 'profile':
                        await this.loadProfileContent();
                        break;
                    case 'contacts':
                        await this.loadContactsContent();
                        break;
                    case 'notes':
                        await this.loadNotesContent();
                        break;
                    default:
                        App.view.render('dashboard-content', templates.placeholderContent('Vista no encontrada'));
                }
            } catch (error) {
                console.error(`Error cargando la vista ${viewId}:`, error);
                this.handleApiError(error);
            }
        },

        /**
         * Carga el contenido del Home
         */
        async loadHomeContent() {
            try {
                const [resourcesResponse, chatResponse, statsResponse] = await Promise.all([
                    api.getResources(),
                    api.getChatMessages(),
                    api.getUserStats()
                ]);

                App.state.setResources(resourcesResponse.resources || []);
                App.state.setChatMessages(chatResponse.messages || []);
                
                App.view.render('dashboard-content', 
                    templates.homeContent(
                        resourcesResponse.resources || [], 
                        chatResponse.messages || [],
                        statsResponse || {}
                    )
                );
            } catch (error) {
                throw error;
            }
        },

        /**
         * Carga el contenido de la Biblioteca
         */
        async loadLibraryContent() {
            try {
                const resourcesResponse = await api.getResources();
                App.state.setResources(resourcesResponse.resources || []);
                
                App.view.render('dashboard-content', 
                    templates.libraryContent(
                        resourcesResponse.resources || [], 
                        App.state.user.id
                    )
                );
            } catch (error) {
                throw error;
            }
        },

        /**
         * Carga el contenido de Grupos
         */
        async loadGroupsContent() {
            try {
                const groupsResponse = await api.getGroups();
                App.state.setGroups(groupsResponse.groups || []);
                
                App.view.render('dashboard-content', 
                    templates.groupsContent(groupsResponse.groups || [])
                );
            } catch (error) {
                throw error;
            }
        },

        /**
         * Carga el contenido de Contactos con datos reales
         */
        async loadContactsContent(searchResults = [], contactRequests = []) {
            try {
                const contactsResponse = await api.getContacts();
                const requestsResponse = await api.getContactRequests();
                
                App.state.setContacts(contactsResponse.contacts || []);
                const contactRequestsData = requestsResponse.requests || [];
                
                App.view.render('dashboard-content', 
                    templates.contactsContent(
                        contactsResponse.contacts || [], 
                        searchResults,
                        contactRequestsData
                    )
                );
            } catch (error) {
                console.error('Error cargando contactos:', error);
                throw error;
            }
        },

        /**
         * Carga el contenido de Anotaciones
         */
        async loadNotesContent() {
            try {
                const privateResponse = await api.getPrivateResources();
                App.state.setPrivateResources(privateResponse.resources || []);
                
                App.view.render('dashboard-content', 
                    templates.notesContent(privateResponse.resources || [])
                );
            } catch (error) {
                throw error;
            }
        },

        /**
         * Carga el contenido del Perfil
         */
        async loadProfileContent() {
            try {
                const statsResponse = await api.getUserStats();
                
                App.view.render('dashboard-content', 
                    templates.profileContent(App.state.user, statsResponse || {})
                );
            } catch (error) {
                throw error;
            }
        },

        /**
         * Carga las notificaciones
         */
        async loadNotifications() {
            try {
                const notificationsResponse = await api.getNotifications();
                App.state.notifications = notificationsResponse.notifications || [];
                
                const unreadCount = App.state.notifications.filter(n => !n.read).length;
                const badge = document.getElementById('notification-badge');
                if (badge) {
                    if (unreadCount > 0) {
                        badge.textContent = unreadCount;
                        badge.classList.remove('hidden');
                    } else {
                        badge.classList.add('hidden');
                    }
                }
            } catch (error) {
                console.error('Error cargando notificaciones:', error);
            }
        },

        /**
         * Carga los mensajes del chat
         */
        async loadChatMessages() {
            try {
                const chatResponse = await api.getChatMessages();
                App.state.setChatMessages(chatResponse.messages || []);
                
                if (App.state.currentView === 'home') {
                    const chatMessagesEl = document.getElementById('chat-messages');
                    if (chatMessagesEl) {
                        chatMessagesEl.innerHTML = templates.chatMessages(chatResponse.messages || []);
                        chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
                    }
                }
            } catch (error) {
                console.error('Error cargando mensajes del chat:', error);
            }
        },

        /**
         * Selecciona un contacto para chatear
         */
        async selectContact(contactId) {
            try {
                App.state.selectedContact = contactId;
                
                const contact = App.state.contacts.find(c => (c.user_id || c.id) == contactId);
                if (contact) {
                    // Actualizar la interfaz de chat
                    const chatArea = document.getElementById('chat-area');
                    if (chatArea) {
                        chatArea.innerHTML = templates.chatArea(contact, []);
                    }
                    
                    // Habilitar el formulario de mensajes
                    const messageInput = document.getElementById('direct-message-input');
                    const messageButton = document.querySelector('#direct-message-form button');
                    if (messageInput && messageButton) {
                        messageInput.disabled = false;
                        messageButton.disabled = false;
                        messageInput.focus();
                    }
                    
                    // Cargar mensajes existentes
                    await this.loadDirectMessages(contactId);
                }
            } catch (error) {
                console.error('Error seleccionando contacto:', error);
                alert('Error al cargar el chat con el contacto.');
            }
        },

        /**
         * Carga mensajes directos con un contacto
         */
        async loadDirectMessages(contactId) {
            try {
                const messagesResponse = await api.getDirectMessages(contactId);
                const messages = messagesResponse.messages || [];
                
                const messagesEl = document.getElementById('direct-messages');
                if (messagesEl) {
                    messagesEl.innerHTML = templates.directMessages(messages);
                    messagesEl.scrollTop = messagesEl.scrollHeight;
                }
                
                // Guardar mensajes en el estado
                if (!App.state.directMessages) {
                    App.state.directMessages = {};
                }
                App.state.directMessages[contactId] = messages;
                
            } catch (error) {
                console.error('Error cargando mensajes directos:', error);
                // Mostrar mensaje de error en la interfaz
                const messagesEl = document.getElementById('direct-messages');
                if (messagesEl) {
                    messagesEl.innerHTML = `
                        <div class="text-center py-8 text-red-500">
                            <p>Error al cargar los mensajes</p>
                        </div>
                    `;
                }
            }
        },

        /**
         * Envía un mensaje directo
         */
        async sendDirectMessage(contactId, message) {
            try {
                await api.sendDirectMessage(contactId, message);
                
                // Recargar mensajes para mostrar el nuevo
                await this.loadDirectMessages(contactId);
                
                // Limpiar el input
                const messageInput = document.getElementById('direct-message-input');
                if (messageInput) {
                    messageInput.value = '';
                    messageInput.focus();
                }
                
            } catch (error) {
                console.error('Error enviando mensaje directo:', error);
                alert('Error al enviar el mensaje: ' + error.message);
            }
        },

        /**
         * Acepta una solicitud de contacto
         */
        async acceptContactRequest(requestId) {
            try {
                await api.acceptContactRequest(requestId);
                
                // Recargar la vista de contactos
                await this.loadContactsContent();
                
                // Mostrar notificación
                this.showNotification('Solicitud de contacto aceptada', 'success');
                
            } catch (error) {
                console.error('Error aceptando solicitud:', error);
                alert('Error al aceptar la solicitud: ' + error.message);
            }
        },

        /**
         * Rechaza una solicitud de contacto
         */
        async rejectContactRequest(requestId) {
            try {
                await api.rejectContactRequest(requestId);
                
                // Recargar la vista de contactos
                await this.loadContactsContent();
                
                // Mostrar notificación
                this.showNotification('Solicitud de contacto rechazada', 'info');
                
            } catch (error) {
                console.error('Error rechazando solicitud:', error);
                alert('Error al rechazar la solicitud: ' + error.message);
            }
        },

        /**
         * Busca usuarios
         */
        async searchUsers(query) {
            try {
                const searchResponse = await api.searchUsers(query);
                await this.loadContactsContent(searchResponse.users || []);
                
            } catch (error) {
                console.error('Error buscando usuarios:', error);
                // Ocultar resultados si hay error
                const resultsContainer = document.getElementById('search-results');
                if (resultsContainer) {
                    resultsContainer.classList.add('hidden');
                }
            }
        },

        /**
         * Muestra el perfil de un contacto
         */
        async viewContactProfile(contactId) {
            try {
                console.log(`🔍 Cargando perfil del contacto ID: ${contactId}`);
                
                // Mostrar loading
                this.showNotification('Cargando perfil...', 'info');
                
                const profileResponse = await api.getUserProfile(contactId);
                console.log("✅ Perfil recibido:", profileResponse);
                
                if (profileResponse && profileResponse.user) {
                    // Mostrar modal con el perfil del contacto
                    this.showContactProfileModal(profileResponse.user);
                } else {
                    throw new Error('No se pudo cargar el perfil');
                }
                
            } catch (error) {
                console.error('❌ Error cargando perfil de contacto:', error);
                
                let errorMessage = 'Error al cargar el perfil';
                if (error.message.includes('403')) {
                    errorMessage = 'No puedes ver el perfil de este usuario. No son contactos.';
                } else if (error.message.includes('404')) {
                    errorMessage = 'Usuario no encontrado.';
                } else {
                    errorMessage = error.message || 'Error al cargar el perfil';
                }
                
                alert('❌ ' + errorMessage);
            }
        },

        /**
         * Muestra el modal con el perfil del contacto
         */
        showContactProfileModal(contactUser) {
            const modalHtml = templates.contactProfileModal(contactUser);
            
            // Crear o actualizar el modal
            let modal = document.getElementById('contact-profile-modal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = 'contact-profile-modal';
                modal.className = 'hidden fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4 backdrop-blur-sm';
                document.body.appendChild(modal);
            }
            
            modal.innerHTML = modalHtml;
            modal.classList.remove('hidden');
            modal.classList.add('flex');
            
            // Cerrar modal al hacer clic fuera
            modal.onclick = (e) => {
                if (e.target === modal) {
                    this.closeContactProfileModal();
                }
            };
        },

        // --- Asistente de IA -------------------------------------------------
        // La interfaz está completa; el backend todavía no expone /api/ai/*.
        // Mientras tanto ai.js devuelve un estado "no disponible" y el panel lo
        // muestra como aviso, sin romper nada.

        /** Abre o cierra el panel del asistente. */
        async toggleAiPanel(forzarAbierto = null) {
            const panel = document.getElementById('ai-panel');
            if (!panel) return;

            const abrir = forzarAbierto === null ? !App.state.aiPanelAbierto : forzarAbierto;
            App.state.aiPanelAbierto = abrir;

            if (!abrir) {
                panel.classList.add('hidden');
                return;
            }

            panel.classList.remove('hidden');
            await this.renderAiPanel();

            const input = document.getElementById('ai-input');
            const estado = await ai.consultarEstado();
            if (input && estado.disponible) input.focus();
        },

        /** Vuelve a dibujar el panel con el estado y los mensajes actuales. */
        async renderAiPanel() {
            const panel = document.getElementById('ai-panel');
            if (!panel || !App.state.aiPanelAbierto) return;

            const estado = await ai.consultarEstado();
            panel.innerHTML = templates.aiPanel(App.state.aiMessages, estado);

            // Mientras el asistente no esté operativo el formulario se deshabilita
            // para no dar la impresión de que la pregunta se envió a algún sitio.
            const input = document.getElementById('ai-input');
            const boton = document.getElementById('ai-send-button');
            const bloqueado = !estado.disponible || App.state.aiEnviando;
            if (input) input.disabled = bloqueado;
            if (boton) boton.disabled = bloqueado;

            this.scrollAiToBottom();
        },

        scrollAiToBottom() {
            const lista = document.getElementById('ai-messages');
            if (lista) lista.scrollTop = lista.scrollHeight;
        },

        /** Envía la pregunta del usuario al asistente. */
        async enviarPreguntaAi(pregunta) {
            const texto = (pregunta || '').trim();
            if (!texto || App.state.aiEnviando) return;

            App.state.aiMessages.push({ rol: 'user', texto });
            App.state.aiMessages.push({ rol: 'assistant', texto: '', pendiente: true });
            App.state.aiEnviando = true;
            await this.renderAiPanel();

            const respuesta = await ai.enviarPregunta(texto);

            // Se quita el marcador "Pensando..." antes de insertar el resultado.
            App.state.aiMessages = App.state.aiMessages.filter(m => !m.pendiente);

            if (respuesta.ok) {
                App.state.aiMessages.push({
                    rol: 'assistant',
                    texto: respuesta.answer,
                    fuentes: respuesta.sources
                });
            } else {
                App.state.aiMessages.push({ rol: 'error', texto: respuesta.mensaje });
                if (respuesta.motivo === 'sesion') this.logout();
            }

            App.state.aiEnviando = false;
            await this.renderAiPanel();
        },

        /** Descarta el hilo actual y empieza de cero. */
        async reiniciarAi() {
            ai.reiniciarConversacion();
            App.state.aiMessages = [];
            await this.renderAiPanel();
        },

        /**
         * Cierra el panel de notificaciones
         */
        closeNotifications() {
            const modal = document.getElementById('notifications-modal');
            if (modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
                modal.onclick = null;
            }
        },

        /**
         * Cierra el modal de perfil de contacto
         */
        closeContactProfileModal() {
            const modal = document.getElementById('contact-profile-modal');
            if (modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        },

        /**
         * Muestra una notificación temporal
         */
        showNotification(message, type = 'info') {
            // Crear elemento de notificación
            const notification = document.createElement('div');
            notification.className = `fixed top-4 right-4 p-4 rounded-lg shadow-lg z-50 transform transition-all duration-300 ${
                type === 'success' ? 'bg-green-500 text-white' :
                type === 'error' ? 'bg-red-500 text-white' :
                'bg-blue-500 text-white'
            }`;
            notification.innerHTML = `
                <div class="flex items-center gap-2">
                    <span>${message}</span>
                </div>
            `;
            
            document.body.appendChild(notification);
            
            // Remover después de 3 segundos
            setTimeout(() => {
                notification.remove();
            }, 3000);
        },

        /**
         * Cierra la sesión del usuario
         */
        logout() {
            this.stopPolling();
            // La conversación con el asistente no debe sobrevivir al cierre de
            // sesión: puede contener preguntas sobre documentos del usuario.
            ai.reiniciarConversacion();
            App.state.aiMessages = [];
            App.state.aiPanelAbierto = false;
            App.state.clearUser();
            api.setToken(null);
            localStorage.removeItem('currentView');
            this.showLogin();
        },
        
        /**
         * Maneja los errores de API
         */
        handleApiError(error) {   
            console.log("🕵️‍♂️ DEBUG - Error completo:", error);
            console.log("🕵️‍♂️ DEBUG - Error message:", error.message);
            console.log("🕵️‍♂️ DEBUG - Error string:", error.toString())
            
            const errorStr = error.toString();
            
            // Solo hacer logout si es error de autenticación EXPLÍCITO
            if (errorStr.includes('401') || errorStr.includes('token') || errorStr.includes('autenticación')) {
                console.warn("🔐 Error de autenticación, redirigiendo al login");
                this.logout();
            } else {
                // Para otros errores, solo mostrar alerta
                console.error("Error no crítico:", error);
                const userMessage = error.message || 'Error en la operación. Intenta nuevamente.';
                alert(userMessage);
            }
        },

        /**
         * Añade todos los event listeners de la aplicación
         */
        addEventListeners() {
            const body = document.body;

            // Listener para cambio de color en tiempo real
            body.addEventListener('change', (event) => {
                if (event.target.name === 'profile_color_edit') {
                    const selectedColor = event.target.value;
                    const preview = document.getElementById('color-preview');
                    const avatarPreview = document.getElementById('profile-avatar-preview');
                    
                    if (preview) {
                        preview.style.backgroundColor = selectedColor;
                    }
                    if (avatarPreview) {
                        avatarPreview.style.backgroundColor = selectedColor;
                    }
                }
            });

            // --- Listener Principal para Clics ---
            body.addEventListener('click', async (event) => {
                const target = event.target;

                // --- Autenticación y Navegación Básica ---
                if (target.id === 'show-register') {
                    event.preventDefault();
                    this.showRegister();
                }

                if (target.id === 'show-login') {
                    event.preventDefault();
                    this.showLogin();
                }
                
                // --- CERRAR SESIÓN ---
                if (target.id === 'logout-button' || target.closest('#logout-button')) {
                    event.preventDefault();
                    event.stopPropagation();
                    console.log("🎯 Logout clickeado - Ejecutando confirmación!");
                    
                    const userConfirmed = confirm('¿Estás seguro de que quieres cerrar sesión?');
                    console.log("Usuario confirmó logout:", userConfirmed);
                    
                    if (userConfirmed) {
                        console.log("🔐 Ejecutando logout completo...");
                        localStorage.removeItem('token');
                        sessionStorage.clear();
                        window.location.href = window.location.origin + window.location.pathname;
                        return;
                    }
                    return;
                }

                // --- Navegación del Dashboard ---
                const navLink = target.closest('a[data-view]');
                if (navLink) {
                    event.preventDefault();
                    const viewId = navLink.dataset.view;
                    
                    await this.loadViewContent(viewId);
                    
                    const sidebarUl = document.querySelector('#app-sidebar ul');
                    if (sidebarUl) {
                        sidebarUl.innerHTML = templates.sidebarLinks(viewId);
                    }
                }

                // --- Contactos ---
                const contactItem = target.closest('.contact-item');
                if (contactItem) {
                    event.preventDefault();
                    const contactId = contactItem.dataset.contactId;
                    await this.selectContact(contactId);
                }

                const acceptRequestBtn = target.closest('.accept-request-btn');
                if (acceptRequestBtn) {
                    event.preventDefault();
                    const requestId = acceptRequestBtn.dataset.requestId;
                    await this.acceptContactRequest(requestId);
                }

                const rejectRequestBtn = target.closest('.reject-request-btn');
                if (rejectRequestBtn) {
                    event.preventDefault();
                    const requestId = rejectRequestBtn.dataset.requestId;
                    await this.rejectContactRequest(requestId);
                }

                // --- VER PERFIL DE CONTACTO ---
                const viewProfileBtn = target.closest('.view-profile-btn');
                if (viewProfileBtn) {
                    event.preventDefault();
                    const contactId = viewProfileBtn.dataset.contactId;
                    console.log(`👤 Solicitando ver perfil del contacto: ${contactId}`);
                    await this.viewContactProfile(contactId);
                }

                // --- CERRAR MODAL DE PERFIL DE CONTACTO ---
                const closeContactProfileBtn = target.closest('.close-contact-profile-modal');
                if (closeContactProfileBtn) {
                    event.preventDefault();
                    this.closeContactProfileModal();
                }

                // --- Acciones del Modal de Recursos ---
                if (target.id === 'add-resource-btn') {
                    App.view.toggleModal(true, null, App.state.user.name, false);
                }
                if (target.id === 'close-modal-btn' || target.id === 'cancel-modal-btn' || target.id === 'resource-modal-overlay') {
                    if (target.id === 'resource-modal-overlay' && event.target.closest('#resource-form')) return; 
                    App.view.toggleModal(false);
                }

                // --- Acciones de la Biblioteca ---
                const deleteResourceBtn = target.closest('.delete-resource-btn');
                if (deleteResourceBtn) {
                    const id = deleteResourceBtn.dataset.id;
                    if (confirm('¿Estás seguro de que quieres eliminar este recurso?')) {
                        try {
                            await api.deleteResource(id);
                            await this.loadViewContent('library');
                        } catch (error) {
                            console.error('Error al eliminar recurso:', error);
                            alert('Error al eliminar el recurso.');
                            this.handleApiError(error);
                        }
                    }
                }

                const editResourceBtn = target.closest('.edit-resource-btn');
                if (editResourceBtn) {
                    const id = editResourceBtn.dataset.id;
                    const resource = App.state.resources.find(r => r.id == id);
                    if(resource) {
                       App.view.toggleModal(true, resource, App.state.user.name, false);
                    } else {
                        alert("No se encontró el recurso para editar.");
                    }
                }

                // --- Grupos de Trabajo ---
                if (target.id === 'create-group-btn' || target.id === 'create-group-placeholder') {
                    App.view.toggleGroupModal(true);
                }

                if (target.id === 'close-group-modal' || target.id === 'cancel-group-modal') {
                    App.view.toggleGroupModal(false);
                }

                const accessGroupBtn = target.closest('.access-group-btn');
                if (accessGroupBtn) {
                    // Antes se abría el modal con el objeto de la LISTA de grupos,
                    // que sólo trae id/nombre/descripción. Como no incluye members,
                    // resources ni tasks, las tres pestañas salían siempre vacías.
                    // Ahora se piden los detalles completos al backend.
                    await this.loadGroupDetails(accessGroupBtn.dataset.groupId);
                }

                // --- Asistente de IA ---
                if (target.closest('#ai-toggle-button')) {
                    event.preventDefault();
                    await this.toggleAiPanel();
                }

                if (target.closest('#ai-close-button')) {
                    event.preventDefault();
                    await this.toggleAiPanel(false);
                }

                if (target.closest('#ai-reset-button')) {
                    event.preventDefault();
                    await this.reiniciarAi();
                }

                // --- Notificaciones ---
                if (target.closest('#notifications-button')) {
                    event.preventDefault();
                    await this.loadNotifications();
                    const modal = document.getElementById('notifications-modal');
                    if (modal) {
                        modal.innerHTML = templates.notificationsPanel(App.state.notifications);
                        modal.classList.remove('hidden');
                        modal.classList.add('flex');
                        modal.onclick = (e) => {
                            if (e.target === modal) this.closeNotifications();
                        };
                    }
                }

                if (target.closest('#close-notifications-modal')) {
                    event.preventDefault();
                    this.closeNotifications();
                }

                const markReadBtn = target.closest('.mark-read-btn');
                if (markReadBtn) {
                    event.preventDefault();
                    try {
                        await api.markNotificationAsRead(markReadBtn.dataset.notificationId);
                        await this.loadNotifications();
                        const modal = document.getElementById('notifications-modal');
                        if (modal && !modal.classList.contains('hidden')) {
                            modal.innerHTML = templates.notificationsPanel(App.state.notifications);
                        }
                    } catch (error) {
                        console.error('Error marcando notificación:', error);
                    }
                }

                // --- Descargas protegidas (privadas y de grupo) ---
                const downloadBtn = target.closest('.download-protected-btn');
                if (downloadBtn) {
                    event.preventDefault();
                    const { privateId, groupId, resourceId, filename } = downloadBtn.dataset;
                    try {
                        if (privateId) {
                            await api.downloadPrivateResource(privateId, filename);
                        } else if (groupId && resourceId) {
                            await api.downloadGroupResource(groupId, resourceId, filename);
                        }
                    } catch (error) {
                        console.error('Error descargando archivo:', error);
                        alert('No se pudo descargar el archivo: ' + error.message);
                    }
                }

                const closeGroupDetailBtn = target.closest('#close-group-detail-modal, #cancel-group-detail-modal');
                if (closeGroupDetailBtn) {
                    App.view.toggleGroupDetailModal(false);
                }

                // --- Anotaciones ---
                if (target.id === 'create-note-btn' || target.id === 'create-note-placeholder') {
                    App.view.toggleNoteModal(true);
                }

                if (target.id === 'upload-private-file-btn') {
                    App.view.toggleModal(true, null, App.state.user.name, true);
                }

                if (target.id === 'close-note-modal' || target.id === 'cancel-note-modal') {
                    App.view.toggleNoteModal(false);
                }

                const editNoteBtn = target.closest('.edit-note-btn');
                if (editNoteBtn) {
                    const noteId = editNoteBtn.dataset.noteId;
                    const note = App.state.privateResources.find(n => n.id == noteId && n.type === 'note');
                    if (note) {
                        App.view.toggleNoteModal(true, note);
                    }
                }

                const deleteNoteBtn = target.closest('.delete-note-btn');
                if (deleteNoteBtn) {
                    const noteId = deleteNoteBtn.dataset.noteId;
                    if (confirm('¿Estás seguro de que quieres eliminar esta nota?')) {
                        try {
                            await api.deletePrivateResource(noteId);
                            await this.loadViewContent('notes');
                        } catch (error) {
                            console.error('Error al eliminar nota:', error);
                            alert('Error al eliminar la nota.');
                        }
                    }
                }

                const deleteFileBtn = target.closest('.delete-file-btn');
                if (deleteFileBtn) {
                    const fileId = deleteFileBtn.dataset.fileId;
                    if (confirm('¿Estás seguro de que quieres eliminar este archivo?')) {
                        try {
                            await api.deletePrivateResource(fileId);
                            await this.loadViewContent('notes');
                        } catch (error) {
                            console.error('Error al eliminar archivo:', error);
                            alert('Error al eliminar el archivo.');
                        }
                    }
                }

                // --- Contactos (funcionalidades existentes) ---
                const addContactBtn = target.closest('.add-contact-btn');
                if (addContactBtn) {
                    const userId = addContactBtn.dataset.userId;
                    if (addContactBtn.textContent === 'Agregar') {
                        try {
                            await api.sendContactRequest(userId);
                            addContactBtn.textContent = 'Pendiente';
                            addContactBtn.classList.remove('bg-purple-600', 'hover:bg-purple-700');
                            addContactBtn.classList.add('bg-yellow-500', 'hover:bg-yellow-600');
                            alert('Solicitud de contacto enviada');
                        } catch (error) {
                            console.error('Error enviando solicitud de contacto:', error);
                            alert(error.message || 'Error al enviar solicitud de contacto.');
                        }
                    }
                }

                const messageContactBtn = target.closest('.message-contact-btn');
                if (messageContactBtn) {
                    const contactId = messageContactBtn.dataset.contactId;
                    this.selectContact(contactId);
                }

                // --- GUARDAR PERFIL - VERSIÓN CORREGIDA ---
                if (target.id === 'save-profile-btn') {
                    event.preventDefault();
                    event.stopPropagation();
                    console.log("💾 Iniciando guardado de perfil...");
                    
                    // Obtener valores del formulario
                    const name = document.getElementById('profile-name').value;
                    const career = document.getElementById('profile-career').value;
                    const semester = document.getElementById('profile-semester').value;
                    
                    // Obtener color seleccionado
                    const colorRadio = document.querySelector('input[name="profile_color_edit"]:checked');
                    const profileColor = colorRadio ? colorRadio.value : '#3B82F6';
                    
                    console.log("📝 Datos a guardar:", { name, career, semester, profileColor });
                    
                    // Validaciones básicas
                    if (!name.trim()) {
                        alert('❌ El nombre es obligatorio');
                        return false;
                    }
                    
                    if (semester && (semester < 1 || semester > 12)) {
                        alert('❌ El semestre debe estar entre 1 y 12');
                        return false;
                    }

                    try {
                        console.log("📤 Enviando datos al servidor...");
                        
                        const profileData = { 
                            name: name.trim(), 
                            career: career || null, 
                            semester: semester ? parseInt(semester) : null, 
                            profile_color: profileColor 
                        };
                        
                        // Mostrar loading
                        const saveBtn = document.getElementById('save-profile-btn');
                        const originalText = saveBtn.innerHTML;
                        saveBtn.innerHTML = '⏳ Guardando...';
                        saveBtn.disabled = true;
                        
                        console.log("🔄 Enviando datos:", profileData);
                        const response = await api.updateProfile(profileData);
                        console.log("✅ Respuesta del servidor:", response);
                        
                        if (response && response.user) {
                            // ACTUALIZAR ESTADO GLOBAL con los datos del servidor
                            App.state.user.name = response.user.name;
                            App.state.user.career = response.user.career;
                            App.state.user.semester = response.user.semester;
                            App.state.user.profile_color = response.user.profile_color;
                            
                            // Actualizar también en localStorage mediante verificación de token
                            try {
                                const verification = await api.verifyToken();
                                if (verification.valid) {
                                    App.state.setUser(verification.user);
                                    console.log("🔄 Estado actualizado con datos del servidor");
                                }
                            } catch (verifyError) {
                                console.warn("⚠️ No se pudo verificar token, pero perfil guardado");
                            }
                            
                            // Mostrar confirmación
                            saveBtn.innerHTML = '✅ Guardado!';
                            
                            // Esperar un momento y recargar la vista
                            setTimeout(async () => {
                                await App.controller.loadViewContent('profile');
                                this.showNotification('Perfil actualizado exitosamente', 'success');
                            }, 1000);
                            
                        } else {
                            throw new Error('Respuesta inválida del servidor');
                        }
                        
                    } catch (error) {
                        console.error('❌ Error actualizando perfil:', error);
                        
                        // Restaurar botón
                        const saveBtn = document.getElementById('save-profile-btn');
                        saveBtn.innerHTML = '💾 Guardar Cambios';
                        saveBtn.disabled = false;
                        
                        // Mostrar error específico
                        let errorMessage = 'Error al guardar el perfil';
                        if (error.message.includes('401') || error.message.includes('token')) {
                            errorMessage = 'Sesión expirada. Por favor, inicia sesión nuevamente.';
                            this.logout();
                        } else if (error.message.includes('500')) {
                            errorMessage = 'Error del servidor. Intenta más tarde.';
                        } else {
                            errorMessage = error.message || 'Error al guardar el perfil';
                        }
                        
                        alert('❌ ' + errorMessage);
                    }
                    
                    return false;
                }

                // --- Cancelar perfil ---
                if (target.id === 'cancel-profile-btn') {
                    event.preventDefault();
                    event.stopPropagation();
                    console.log("❌ Cancelando edición de perfil");
                    return false;
                }

                if (target.id === 'quick-upload') {
                    App.state.currentView = 'library';
                    const sidebarUl = document.querySelector('#app-sidebar ul');
                    if (sidebarUl) {
                         sidebarUl.innerHTML = templates.sidebarLinks('library');
                    }
                    await this.loadViewContent('library');
                    setTimeout(() => {
                        const addBtn = document.getElementById('add-resource-btn');
                        if (addBtn) addBtn.click();
                    }, 500);
                }

                if (target.id === 'quick-group') {
                    App.state.currentView = 'groups';
                    const sidebarUl = document.querySelector('#app-sidebar ul');
                    if (sidebarUl) {
                         sidebarUl.innerHTML = templates.sidebarLinks('groups');
                    }
                    await this.loadViewContent('groups');
                    setTimeout(() => {
                        const createBtn = document.getElementById('create-group-btn');
                        if (createBtn) createBtn.click();
                    }, 500);
                }

                if (target.id === 'quick-contact') {
                    App.state.currentView = 'contacts';
                    const sidebarUl = document.querySelector('#app-sidebar ul');
                    if (sidebarUl) {
                         sidebarUl.innerHTML = templates.sidebarLinks('contacts');
                    }
                    await this.loadViewContent('contacts');
                }

                // --- Pestañas ---
                const groupDetailTab = target.closest('.group-detail-tab');
                if (groupDetailTab) {
                    const tabName = groupDetailTab.dataset.tab;
                    App.controller.switchGroupDetailTab(tabName);
                }

                const notesTab = target.closest('.notes-tab');
                if (notesTab) {
                    const tabName = notesTab.dataset.tab;
                    App.controller.switchNotesTab(tabName);
                }
            });

            // --- Listeners de Formularios (Submit) ---
            body.addEventListener('submit', async (event) => {
                event.preventDefault();

                // --- Formulario de Login ---
                if (event.target.id === 'login-form') {
                    const email = document.getElementById('login-email').value;
                    const password = document.getElementById('login-password').value;
                    try {
                        const data = await api.login(email, password);
                        localStorage.setItem('token', data.token);
                        App.state.setUser(data.user);
                        await this.showDashboard();
                    } catch (error) {
                        console.error('Error de inicio de sesión:', error);
                        alert(error.message || 'Error al iniciar sesión.');
                    }
                }

                // --- Formulario de Registro ---
                if (event.target.id === 'register-form') {
                    const name = document.getElementById('register-name').value;
                    const email = document.getElementById('register-email').value;
                    const password = document.getElementById('register-password').value;
                    
                    // Obtener el color seleccionado
                    const profileColor = document.querySelector('input[name="profile_color"]:checked').value;
                    
                    try {
                        await api.register(name, email, password, profileColor);
                        alert('¡Registro exitoso! Por favor, inicia sesión.');
                        this.showLogin();
                    } catch (error) {
                        console.error('Error de registro:', error);
                        alert(error.message || 'Error al registrarse.');
                    }
                }
                
                // --- Formulario de Recursos (Públicos y Privados) ---
                if (event.target.id === 'resource-form') {
                    const form = event.target;
                    const resourceId = form.dataset.id;
                    const isEdit = !!resourceId;
                    const isPrivate = form.dataset.private === 'true';

                    const formData = new FormData();
                    
                    if (!isPrivate) {
                        formData.append('title', document.getElementById('res-title').value);
                        formData.append('author', document.getElementById('res-author').value);
                        formData.append('category', document.getElementById('res-category').value);
                        formData.append('tags', document.getElementById('res-tags').value);
                    } else {
                        formData.append('title', document.getElementById('res-title').value);
                    }
                    
                    const fileInput = document.getElementById('res-file');
                    if (fileInput.files.length > 0) {
                        formData.append('file', fileInput.files[0]);
                    } else if (!isEdit) {
                        alert("Se requiere un archivo para crear un nuevo recurso.");
                        return;
                    }

                    try {
                        if (isPrivate) {
                            if (isEdit) {
                                await api.updatePrivateResource(resourceId, formData);
                            } else {
                                await api.createPrivateFile(formData);
                            }
                            App.view.toggleModal(false);
                            await this.loadViewContent('notes');
                            alert('Archivo privado subido exitosamente');
                        } else {
                            if (isEdit) {
                                await api.updateResource(resourceId, formData);
                            } else {
                                await api.createResource(formData);
                            }
                            App.view.toggleModal(false);
                            await this.loadViewContent('library');
                            alert('Recurso compartido exitosamente');
                        }
                    } catch (error) {
                        console.error('Error al guardar recurso:', error);
                        alert(error.message || 'Error al guardar el recurso.');
                    }
                }

                // --- Formulario del Asistente de IA ---
                if (event.target.id === 'ai-form') {
                    const input = document.getElementById('ai-input');
                    const pregunta = input ? input.value.trim() : '';
                    if (pregunta) {
                        if (input) input.value = '';
                        await this.enviarPreguntaAi(pregunta);
                    }
                    return false;
                }

                // --- Formulario de Chat Global ---
                if (event.target.id === 'chat-form') {
                    const input = document.getElementById('chat-input');
                    const message = input.value.trim();
                    
                    if (message) {
                        try {
                            await api.sendChatMessage(message);
                            input.value = '';
                            await this.loadChatMessages();
                            input.focus();
                        } catch (error) {
                            console.error('Error enviando mensaje:', error);
                            alert('Error al enviar el mensaje.');
                        }
                    }
                    
                    event.preventDefault();
                    return false;
                }

                // --- Formulario de Mensaje Directo ---
                if (event.target.id === 'direct-message-form') {
                    const input = document.getElementById('direct-message-input');
                    const message = input.value.trim();
                    
                    if (message && App.state.selectedContact) {
                        try {
                            await this.sendDirectMessage(App.state.selectedContact, message);
                        } catch (error) {
                            console.error('Error enviando mensaje directo:', error);
                            alert('Error al enviar el mensaje.');
                        }
                    }
                }

                // --- Formulario de Crear Grupo ---
                if (event.target.id === 'create-group-form') {
                    const name = document.getElementById('group-name').value;
                    const description = document.getElementById('group-description').value;
                    
                    try {
                        await api.createGroup(name, description);
                        App.view.toggleGroupModal(false);
                        await this.loadViewContent('groups');
                        alert('Grupo creado exitosamente');
                    } catch (error) {
                        console.error('Error creando grupo:', error);
                        alert(error.message || 'Error al crear el grupo.');
                    }
                }

                // --- Formulario de Nota ---
                if (event.target.id === 'note-form') {
                    const noteId = document.getElementById('note-id').value;
                    const title = document.getElementById('note-title').value;
                    const content = document.getElementById('note-content').value;
                    const isEdit = !!noteId;
                    
                    try {
                        if (isEdit) {
                            await api.updatePrivateResource(noteId, { title, content });
                        } else {
                            await api.createPrivateNote(title, content);
                        }
                        App.view.toggleNoteModal(false);
                        await this.loadViewContent('notes');
                        alert('Nota guardada exitosamente');
                    } catch (error) {
                        console.error('Error guardando nota:', error);
                        alert(error.message || 'Error al guardar la nota.');
                    }
                }
            });

            // --- Listeners de Input ---
            body.addEventListener('input', (event) => {
                // Búsqueda en biblioteca
                if (event.target.id === 'search-bar') {
                    const searchTerm = event.target.value.toLowerCase();
                    const filteredResources = App.state.resources.filter(r => 
                        (r.title || '').toLowerCase().includes(searchTerm) ||
                        (r.author || '').toLowerCase().includes(searchTerm) ||
                        (r.tags || '').toLowerCase().includes(searchTerm)
                    );
                    App.view.renderTableRows(filteredResources, App.state.user.id);
                }

                // Búsqueda de contactos
                if (event.target.id === 'search-contacts') {
                    const searchTerm = event.target.value.trim();
                    if (searchTerm.length >= 2) {
                        clearTimeout(this.searchTimeout);
                        this.searchTimeout = setTimeout(() => {
                            this.searchUsers(searchTerm);
                        }, 500);
                    } else {
                        const resultsContainer = document.getElementById('search-results');
                        if (resultsContainer) {
                            resultsContainer.classList.add('hidden');
                        }
                    }
                }
            });
        },

        /**
         * Cambia entre pestañas en el detalle del grupo
         */
        switchGroupDetailTab(tabName) {
            document.querySelectorAll('.group-detail-content').forEach(content => {
                content.classList.add('hidden');
            });
            
            const selectedTab = document.getElementById(`group-${tabName}-tab`);
            if (selectedTab) {
                selectedTab.classList.remove('hidden');
            }
            
            document.querySelectorAll('.group-detail-tab').forEach(tab => {
                if (tab.dataset.tab === tabName) {
                    tab.classList.add('border-green-500', 'text-green-600');
                    tab.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                } else {
                    tab.classList.remove('border-green-500', 'text-green-600');
                    tab.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                }
            });
        },

        /**
         * Cambia entre pestañas en anotaciones
         */
        switchNotesTab(tabName) {
            document.querySelectorAll('.notes-tab-content').forEach(content => {
                content.classList.add('hidden');
            });
            
            const selectedTab = document.getElementById(`${tabName}-tab-content`);
            if (selectedTab) {
                selectedTab.classList.remove('hidden');
            }
            
            document.querySelectorAll('.notes-tab').forEach(tab => {
                if (tab.dataset.tab === tabName) {
                    tab.classList.add('border-orange-500', 'text-orange-600');
                    tab.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                } else {
                    tab.classList.remove('border-orange-500', 'text-orange-600');
                    tab.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                }
            });
        },

        /**
         * Carga los detalles completos de un grupo
         */
        async loadGroupDetails(groupId) {
            try {
                const details = await api.getGroupDetails(groupId);

                // El backend responde {group, members, resources, tasks}, pero la
                // plantilla espera un único objeto plano con esas listas dentro.
                // Sin este aplanado el modal mostraba el nombre del grupo vacío.
                const group = {
                    ...details.group,
                    members: details.members || [],
                    resources: details.resources || [],
                    tasks: details.tasks || []
                };

                App.state.currentGroup = group;
                App.view.toggleGroupDetailModal(true, group);
            } catch (error) {
                console.error('Error cargando detalles del grupo:', error);
                alert('Error al cargar los detalles del grupo: ' + error.message);
            }
        }
    }
};

/**
 * Inicialización
 */
document.addEventListener('DOMContentLoaded', App.controller.init);

// Exportar para acceso global (debugging)
window.App = App;