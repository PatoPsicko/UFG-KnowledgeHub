/**
 * Estado compartido mínimo: el usuario y el último «pulso» del servidor.
 * Las vistas se suscriben con store.on('pulse', fn, signal).
 */

const listeners = new Map();

export const store = {
    user: null,
    pulse: {
        notifications_unread: 0, dm_unread: {}, dm_unread_total: 0, global_last_id: 0, global_unread: 0,
        groups_unread: {}, groups_unread_total: 0, online_count: 0, friends_online: [],
    },
    aiStatus: null,

    on(event, fn, signal) {
        if (!listeners.has(event)) listeners.set(event, new Set());
        listeners.get(event).add(fn);
        signal?.addEventListener('abort', () => listeners.get(event)?.delete(fn));
    },

    emit(event, data) {
        listeners.get(event)?.forEach((fn) => {
            try { fn(data); } catch (err) { console.error(err); }
        });
    },

    setUser(user) {
        this.user = user;
        this.emit('user', user);
    },

    setPulse(pulse) {
        const previo = this.pulse;
        this.pulse = pulse;
        this.emit('pulse', { pulse, previo });
    },

    isOnline(userId) {
        return this.pulse.friends_online?.includes(userId);
    },
};
