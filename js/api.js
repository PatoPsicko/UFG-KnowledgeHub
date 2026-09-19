import { config } from './config.js';

const api = {
    baseURL: config.API_URL,
    
    /**
     * Realiza una solicitud fetch al backend.
     */
    async request(endpoint, method = 'GET', body = null, isFormData = false) {
        const url = `${this.baseURL}${endpoint}`;
        const options = {
            method: method,
            headers: {},
        };

        if (!isFormData && body) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        } else if (isFormData && body) {
            options.body = body;
        }

        const currentToken = localStorage.getItem('token');
        
        if (currentToken) {
            options.headers['Authorization'] = `Bearer ${currentToken}`;
        }

        try {
            const response = await fetch(url, options);

            if (response.status === 204) {
                return {};
            }

            let data;
            const contentType = response.headers.get('content-type');
            
            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                const text = await response.text();
                data = { 
                    message: text || `Error ${response.status}`,
                    error: `Expected JSON but got ${contentType || 'unknown'}`
                };
            }

            if (!response.ok) {
                const errorMessage = data.message || data.error || `Error ${response.status} en la solicitud`;
                let userMessage = errorMessage;
                if (response.status === 401) {
                    userMessage = 'No autorizado. Por favor, inicia sesión nuevamente.';
                } else if (response.status === 422) {
                    userMessage = 'Token inválido o expirado. Por favor, inicia sesión nuevamente.';
                } else if (response.status === 500) {
                    userMessage = 'Error interno del servidor. Intenta más tarde.';
                }
                
                throw new Error(`${userMessage} (${response.status})`);
            }

            return data;
            
        } catch (error) {
            if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
                throw new Error('Error de conexión. Verifica que el servidor esté ejecutándose.');
            }
            
            throw error;
        }
    },

    /**
     * Obtener headers para las solicitudes
     */
    getHeaders() {
        const headers = {};
        const token = localStorage.getItem('token');
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    },

    /**
     * Manejar respuesta de la API
     */
    async handleResponse(response) {
        if (!response.ok) {
            const error = await response.json().catch(() => ({ message: 'Error desconocido' }));
            throw new Error(error.message || `Error ${response.status}`);
        }
        return response.json();
    },

    // --- Autenticación ---
    async login(email, password) {
        const loginData = await this.request('/api/login', 'POST', { email, password });
        
        if (loginData.token) {
            localStorage.setItem('token', loginData.token);
        } else {
            throw new Error('Error en el servidor: no se recibió token de autenticación');
        }
        
        return loginData;
    },

   async register(name, email, password, profileColor = '#3B82F6') {  // 🆕 NUEVO parámetro
    return this.request('/api/register', 'POST', { 
        name, 
        email, 
        password,
        profile_color: profileColor  // 🆕 NUEVO: enviar color al backend
    });
},

    async verifyToken() {
        return this.request('/api/verify-token', 'GET');
    },

    async healthCheck() {
        return this.request('/api/health', 'GET');
    },

    // --- Recursos Públicos ---
    async getResources() {
        return this.request('/api/resources', 'GET');
    },

    async createResource(formData) {
        return this.request('/api/resources', 'POST', formData, true);
    },

    async deleteResource(id) {
        return this.request(`/api/resources/${id}`, 'DELETE');
    },

    async updateResource(id, formData) {
        return this.request(`/api/resources/${id}`, 'PUT', formData, true);
    },

    // --- Chat Global ---
    async getChatMessages() {
        return this.request('/api/chat/messages', 'GET');
    },

    async sendChatMessage(message) {
        return this.request('/api/chat/messages', 'POST', { message });
    },

    // --- Contactos ---
    async getContacts() {
        return this.request('/api/contacts', 'GET');
    },

    async searchUsers(query) {
        return this.request(`/api/contacts/search?q=${encodeURIComponent(query)}`, 'GET');
    },

    async sendContactRequest(contactId) {
        return this.request('/api/contacts/request', 'POST', { contact_id: contactId });
    },

    async getContactRequests() {
        return this.request('/api/contacts/requests', 'GET');
    },

    async acceptContactRequest(requestId) {
        // El backend espera 'PUT' para aceptar (actualizar el estado)
        return this.request(`/api/contacts/requests/${requestId}/accept`, 'PUT');
    },

    async rejectContactRequest(requestId) {
        // El backend espera 'DELETE' para rechazar (borrar la solicitud)
        return this.request(`/api/contacts/requests/${requestId}/reject`, 'DELETE');
    },

    // --- Mensajes Directos ---
    async getDirectMessages(contactId) {
        return this.request(`/api/direct-messages/${contactId}`, 'GET');
    },

    async sendDirectMessage(contactId, message) {
        return this.request('/api/direct-messages', 'POST', { 
            receiver_id: contactId, 
            message: message 
        });
    },

    // --- Grupos de Trabajo ---
    async getGroups() {
        return this.request('/api/groups', 'GET');
    },

    async createGroup(name, description = '') {
        return this.request('/api/groups', 'POST', { name, description });
    },

    async getGroupDetails(groupId) {
        return this.request(`/api/groups/${groupId}`, 'GET');
    },

    async getGroupMembers(groupId) {
        return this.request(`/api/groups/${groupId}/members`, 'GET');
    },

    async getGroupMessages(groupId) {
        return this.request(`/api/groups/${groupId}/messages`, 'GET');
    },

    async sendGroupMessage(groupId, message) {
        return this.request(`/api/groups/${groupId}/messages`, 'POST', { message });
    },

    async inviteToGroup(groupId, userId) {
        return this.request(`/api/groups/${groupId}/invite`, 'POST', { user_id: userId });
    },

    async addGroupTask(groupId, taskData) {
        return this.request(`/api/groups/${groupId}/tasks`, 'POST', taskData);
    },

    async getGroupTasks(groupId) {
        return this.request(`/api/groups/${groupId}/tasks`, 'GET');
    },

    async uploadGroupResource(groupId, formData) {
        return this.request(`/api/groups/${groupId}/resources`, 'POST', formData, true);
    },

    async getGroupResources(groupId) {
        return this.request(`/api/groups/${groupId}/resources`, 'GET');
    },

    // --- Recursos Privados (Anotaciones) ---
    async getPrivateResources() {
        return this.request('/api/private-resources', 'GET');
    },

    async createPrivateNote(title, content) {
        return this.request('/api/private-resources', 'POST', { 
            title, 
            content,
            type: 'note'
        });
    },

    async createPrivateFile(formData) {
        return this.request('/api/private-resources', 'POST', formData, true);
    },

    async updatePrivateResource(id, data) {
        // El backend espera JSON en este endpoint. Si llega un FormData (como
        // hacía el formulario de archivos privados), JSON.stringify lo convertía
        // en "{}" y la edición se guardaba vacía. Se normaliza aquí.
        if (data instanceof FormData) {
            data = Object.fromEntries(
                Array.from(data.entries()).filter(([, value]) => !(value instanceof File))
            );
        }
        return this.request(`/api/private-resources/${id}`, 'PUT', data);
    },

    async deletePrivateResource(id) {
        return this.request(`/api/private-resources/${id}`, 'DELETE');
    },

    async updateProfile(profileData) {
        return this.request('/api/profile', 'POST', profileData);
    },

    /**
     * Perfil público de otro usuario.
     * app.js ya la invocaba desde viewContactProfile(), pero no estaba definida:
     * el botón "Ver perfil" fallaba siempre con "api.getUserProfile is not a function".
     */
    async getUserProfile(userId) {
        return this.request(`/api/users/${userId}/profile`, 'GET');
    },

    async getUserStats() {
        return this.request('/api/user/stats', 'GET');
    },

    async uploadProfilePicture(formData) {
        return this.request('/api/profile/picture', 'POST', formData, true);
    },

    // --- Notificaciones ---
    async getNotifications() {
        return this.request('/api/notifications', 'GET');
    },

    async markNotificationAsRead(notificationId) {
        return this.request(`/api/notifications/${notificationId}/read`, 'PUT');
    },

    // --- Utilidades ---
    getFileUrl(filename) {
        if (!filename) return '';
        return `${this.baseURL}/api/uploads/${encodeURIComponent(filename)}`;
    },

    /**
     * Descarga un archivo protegido por token.
     *
     * Una etiqueta <a href> no puede enviar la cabecera Authorization, así que
     * los archivos privados y de grupo se piden por fetch y se entregan al
     * navegador como blob. Antes se enlazaban directamente a /api/uploads/...,
     * que no pedía autenticación: cualquiera con la URL los descargaba.
     */
    async downloadProtectedFile(path, suggestedName = 'archivo') {
        const response = await fetch(`${this.baseURL}${path}`, {
            headers: this.getHeaders()
        });

        if (!response.ok) {
            let message = `Error ${response.status}`;
            try {
                const data = await response.json();
                message = data.message || message;
            } catch (_) { /* la respuesta no era JSON */ }
            throw new Error(message);
        }

        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = suggestedName;
        document.body.appendChild(link);
        link.click();
        link.remove();
        // Se libera la memoria del blob tras dar tiempo al navegador a iniciar
        // la descarga.
        setTimeout(() => URL.revokeObjectURL(objectUrl), 10000);
    },

    async downloadPrivateResource(id, suggestedName) {
        return this.downloadProtectedFile(`/api/private-resources/${id}/download`, suggestedName);
    },

    async downloadGroupResource(groupId, resourceId, suggestedName) {
        return this.downloadProtectedFile(
            `/api/groups/${groupId}/resources/${resourceId}/download`, suggestedName);
    },

    getProfilePictureUrl(filename) {
        if (!filename) return '';
        return `${this.baseURL}/api/uploads/profile/${encodeURIComponent(filename)}`;
    },

    setToken(token) {
        if (token) {
            localStorage.setItem('token', token);
        } else {
            localStorage.removeItem('token');
        }
    },

    clearToken() {
        localStorage.removeItem('token');
    },

    hasToken() {
        return !!localStorage.getItem('token');
    }
};

export { api };