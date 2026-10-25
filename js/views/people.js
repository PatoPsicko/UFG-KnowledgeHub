/** Perfil de otra persona (se abre desde los miembros de un grupo). */

import { api } from '../core/api.js';
import { html, longDate } from '../core/dom.js';
import { avatar } from '../ui/components.js';
import { openDialog, toast } from '../ui/overlay.js';

export async function openUserProfile(userId) {
    let u;
    try {
        u = (await api.get(`/api/users/${userId}/profile`)).user;
    } catch (err) {
        return toast(err.message, 'error');
    }
    return openDialog({
        title: u.name,
        footer: false,
        body: html`<div style="display:flex;gap:16px;align-items:center">
                ${avatar(u, 'lg')}
                <p style="font-weight:600">${u.career || 'Carrera sin indicar'}${u.semester ? `, ciclo ${u.semester}` : ''}</p>
            </div>
            ${u.bio ? html`<p style="margin-top:14px;color:var(--ink-2)">${u.bio}</p>` : ''}
            <dl class="kv">
                <dt>Aportes</dt><dd>${u.resources_count} ${u.resources_count === 1 ? 'documento' : 'documentos'} en la biblioteca</dd>
                <dt>Grupos en común</dt><dd>${u.groups_in_common}</dd>
                <dt>En la UFG Hub desde</dt><dd>${longDate(u.created_at)}</dd>
            </dl>`,
    });
}
