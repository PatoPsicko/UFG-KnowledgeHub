/** Mi perfil: datos, foto, color, contraseña y aportes. */

import { api } from '../core/api.js';
import { $, html, longDate, on, setHtml } from '../core/dom.js';
import { store } from '../core/store.js';
import { avatar, errorBox, loading } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { toast } from '../ui/overlay.js';

const COLORES = ['#0B6FCB', '#F08A0B', '#2E7D6B', '#B5487A', '#6B4FA3', '#C2453A', '#12325A', '#8A6D1F'];

export async function profileView(root, _params, signal) {
    setHtml(root, html`<div class="page">${loading()}</div>`);
    let stats = {};
    try { stats = await api.get('/api/user/stats'); } catch { /* opcional */ }

    function pintar() {
        const u = store.user;
        setHtml(root, html`<div class="page">
            <div class="page-head"><div><h1>Mi perfil</h1><p>Así te ven tus compañeros en grupos, mensajes y la biblioteca.</p></div></div>
            <div class="profile">
                <section class="panel profile-card">
                    ${avatar({ ...u, online: true }, 'xl')}
                    <h2>${u.name}</h2>
                    <p>${u.career || 'Carrera sin indicar'}${u.semester ? `, ciclo ${u.semester}` : ''}</p>
                    <p>${u.email}</p>
                    <div style="display:flex;gap:6px;justify-content:center;margin-top:12px">
                        <label class="btn btn--secondary btn--sm">${icon('image')}Cambiar foto<input type="file" accept="image/png,image/jpeg,image/gif,image/webp" data-action="photo" hidden></label>
                        ${u.avatar_url ? html`<button class="btn btn--ghost btn--sm" data-action="remove-photo">Quitar</button>` : ''}
                    </div>
                    <div class="profile-stats">
                        <div><strong>${stats.resources_count ?? 0}</strong><span>aportes</span></div>
                        <div><strong>${stats.downloads_received ?? 0}</strong><span>descargas</span></div>
                        <div><strong>${stats.contacts_count ?? 0}</strong><span>amigos</span></div>
                    </div>
                    <p style="margin-top:14px;font-size:13px">En la plataforma desde ${longDate(u.created_at)}</p>
                </section>
                <div style="display:flex;flex-direction:column;gap:18px">
                    <form class="panel" data-form="profile">
                        <div class="panel__head"><h2>Datos personales</h2></div>
                        <div class="panel__body">
                            <label class="field"><span class="field__label">Nombre</span><input class="input" name="name" required maxlength="150" value="${u.name}"></label>
                            <div class="row">
                                <label class="field"><span class="field__label">Carrera</span><input class="input" name="career" maxlength="100" value="${u.career || ''}" placeholder="Ej. Ingeniería en Ciencias de la Computación"></label>
                                <label class="field"><span class="field__label">Ciclo</span><input class="input" name="semester" type="number" min="1" max="12" value="${u.semester || ''}"></label>
                            </div>
                            <label class="field"><span class="field__label">Presentación</span>
                                <textarea class="textarea" name="bio" rows="2" maxlength="280" placeholder="Qué estudias, en qué puedes ayudar...">${u.bio || ''}</textarea></label>
                            <div class="field"><span class="field__label">Color del avatar</span>
                                <div class="swatches">${COLORES.map((c) => html`<button type="button" class="swatch" data-color="${c}" aria-pressed="${c.toLowerCase() === (u.profile_color || '').toLowerCase()}" aria-label="Color ${c}" style="background:${c}"></button>`)}</div></div>
                            <input type="hidden" name="profile_color" value="${u.profile_color}">
                            <div data-slot="error"></div>
                        </div>
                        <div class="panel__foot" style="display:flex;justify-content:flex-end"><button class="btn btn--primary" type="submit">Guardar cambios</button></div>
                    </form>
                    <form class="panel" data-form="password">
                        <div class="panel__head"><h2>Contraseña</h2></div>
                        <div class="panel__body">
                            <div class="row">
                                <label class="field"><span class="field__label">Contraseña actual</span><input class="input" name="current_password" type="password" autocomplete="current-password" required></label>
                                <label class="field"><span class="field__label">Nueva contraseña</span><input class="input" name="new_password" type="password" autocomplete="new-password" minlength="8" required></label>
                            </div>
                            <div data-slot="error"></div>
                        </div>
                        <div class="panel__foot" style="display:flex;justify-content:flex-end"><button class="btn btn--secondary" type="submit">${icon('key')}Cambiar contraseña</button></div>
                    </form>
                </div>
            </div>
        </div>`);
    }

    on(root, 'click', '.swatch', (_e, b) => {
        root.querySelectorAll('.swatch').forEach((s) => s.setAttribute('aria-pressed', String(s === b)));
        $('[name="profile_color"]', root).value = b.dataset.color;
    }, signal);

    root.addEventListener('submit', async (e) => {
        e.preventDefault();
        const form = e.target;
        const slot = $('[data-slot="error"]', form);
        setHtml(slot, '');
        const boton = form.querySelector('[type="submit"]');
        boton.disabled = true;
        try {
            const datos = Object.fromEntries(new FormData(form));
            if (form.dataset.form === 'profile') {
                const { user } = await api.put('/api/profile', datos);
                store.setUser(user);
                toast('Perfil actualizado');
                pintar();
            } else {
                await api.post('/api/profile/password', datos);
                form.reset();
                toast('Contraseña actualizada');
            }
        } catch (err) {
            setHtml(slot, errorBox(err));
        } finally {
            boton.disabled = false;
        }
    }, { signal });

    root.addEventListener('change', async (e) => {
        if (!e.target.matches('[data-action="photo"]') || !e.target.files.length) return;
        const fd = new FormData();
        fd.append('file', e.target.files[0]);
        try {
            const { user } = await api.upload('/api/profile/picture', fd);
            store.setUser(user);
            toast('Foto actualizada');
            pintar();
        } catch (err) { toast(err.message, 'error'); }
    }, { signal });

    on(root, 'click', '[data-action="remove-photo"]', async () => {
        try {
            const { user } = await api.del('/api/profile/picture');
            store.setUser(user);
            pintar();
        } catch (err) { toast(err.message, 'error'); }
    }, signal);

    pintar();
}
