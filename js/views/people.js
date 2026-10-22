/** Perfil de otra persona y acciones de amistad (se usa desde Mensajes y Grupos). */

import { api } from '../core/api.js';
import { html, longDate } from '../core/dom.js';
import { go } from '../core/router.js';
import { avatar } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { confirmDialog, openDialog, toast } from '../ui/overlay.js';

export async function friendAction(action, { userId, requestId, name }) {
    if (action === 'add') {
        const r = await api.post('/api/contacts/request', { contact_id: userId });
        toast(r.message);
    } else if (action === 'accept') {
        await api.put(`/api/contacts/requests/${requestId}/accept`);
        toast(`Ahora tú y ${name} son amigos`);
    } else if (action === 'reject' || action === 'cancel') {
        await api.del(`/api/contacts/requests/${requestId}`);
        toast(action === 'reject' ? 'Solicitud rechazada' : 'Solicitud cancelada');
    } else if (action === 'remove') {
        if (!await confirmDialog({ title: 'Eliminar amigo', text: `${name} dejará de estar en tus amigos y no podrán escribirse por privado.`, confirmLabel: 'Eliminar' })) return false;
        await api.del(`/api/contacts/${userId}`);
        toast('Amigo eliminado');
    }
    return true;
}

export function relationButtons(u) {
    switch (u.relation) {
    case 'accepted':
        return html`<button class="btn btn--primary btn--sm" data-friend="message" data-user="${u.id}">${icon('chat')}Escribir</button>`;
    case 'pending_sent':
        return html`<button class="btn btn--secondary btn--sm" data-friend="cancel" data-user="${u.id}" data-request="${u.request_id}" data-name="${u.name}">Cancelar solicitud</button>`;
    case 'pending_received':
        return html`<button class="btn btn--primary btn--sm" data-friend="accept" data-user="${u.id}" data-request="${u.request_id}" data-name="${u.name}">${icon('check')}Aceptar</button>`;
    case 'self':
        return '';
    default:
        return html`<button class="btn btn--secondary btn--sm" data-friend="add" data-user="${u.id}" data-name="${u.name}">${icon('userPlus')}Agregar</button>`;
    }
}

export async function openUserProfile(userId, { onChanged = () => {} } = {}) {
    let u;
    try {
        u = (await api.get(`/api/users/${userId}/profile`)).user;
    } catch (err) {
        return toast(err.message, 'error');
    }
    const dlg = openDialog({
        title: u.name,
        footer: false,
        body: html`<div style="display:flex;gap:16px;align-items:center">
                ${avatar(u, 'lg')}
                <div style="min-width:0">
                    <p style="font-weight:600">${u.career || 'Carrera sin indicar'}${u.semester ? `, ciclo ${u.semester}` : ''}</p>
                    <p style="color:var(--ink-3);font-size:14px">${u.online ? 'En línea ahora' : 'Desconectado'}</p>
                    ${u.email ? html`<p style="color:var(--ink-3);font-size:14px">${u.email}</p>` : ''}
                </div>
            </div>
            ${u.bio ? html`<p style="margin-top:14px;color:var(--ink-2)">${u.bio}</p>` : ''}
            <dl class="kv">
                <dt>Aportes</dt><dd>${u.resources_count} ${u.resources_count === 1 ? 'documento' : 'documentos'} en la biblioteca</dd>
                <dt>Grupos en común</dt><dd>${u.groups_in_common}</dd>
                <dt>En la UFG Hub desde</dt><dd>${longDate(u.created_at)}</dd>
            </dl>
            <div style="display:flex;gap:8px;flex-wrap:wrap" data-slot="actions">
                ${relationButtons(u)}
                ${u.relation === 'pending_received' ? html`<button class="btn btn--ghost btn--sm" data-friend="reject" data-request="${u.request_id}" data-name="${u.name}">Rechazar</button>` : ''}
                ${u.relation === 'accepted' ? html`<button class="btn btn--ghost btn--sm" data-friend="remove" data-user="${u.id}" data-name="${u.name}">${icon('userMinus')}Eliminar amigo</button>` : ''}
            </div>`,
    });
    dlg.addEventListener('click', async (e) => {
        const b = e.target.closest('[data-friend]');
        if (!b) return;
        if (b.dataset.friend === 'message') {
            dlg.close();
            return go(`/mensajes/dm/${u.id}`);
        }
        try {
            const hecho = await friendAction(b.dataset.friend, {
                userId: Number(b.dataset.user || u.id), requestId: b.dataset.request, name: b.dataset.name || u.name,
            });
            if (hecho !== false) { dlg.close(); onChanged(); }
        } catch (err) {
            toast(err.message, 'error');
        }
    });
    return dlg;
}

