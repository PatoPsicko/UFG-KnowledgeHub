/** Mi perfil: datos, foto, color, contraseña, acceso (sesiones y verificación en dos pasos) y aportes. */

import { api } from '../core/api.js';
import { $, fileSize, html, longDate, on, setHtml, timeAgo } from '../core/dom.js';
import { prefs } from '../core/prefs.js';
import { store } from '../core/store.js';
import { avatar, errorBox, loading, meter, segmented } from '../ui/components.js';
import { icon } from '../ui/icons.js';
import { confirmDialog, toast } from '../ui/overlay.js';
import { careerFields, fillCareer } from '../ui/pickers.js';
import { openDisableTwoFactor, openNewRecoveryCodes, openTwoFactorSetup } from '../ui/twofactor.js';

const COLORES = ['#0B6FCB', '#F08A0B', '#2E7D6B', '#B5487A', '#6B4FA3', '#C2453A', '#12325A', '#8A6D1F'];
const esCelular = (device) => /Android|iPhone|iPad/.test(device);

function dosPasos(st) {
    if (!st) return '';
    const texto = st.enabled
        ? `Activa: al entrar se pide un código de tu celular. Te quedan ${st.recovery_left} códigos de respaldo.`
        : st.required
            ? 'Los administradores la necesitan para entrar al panel de Seguridad.'
            : 'Además de la contraseña, pide un código que cambia cada 30 segundos en tu celular.';
    return html`<div class="access-row">
        <span class="access-row__icon ${st.enabled ? 'is-on' : ''}">${icon('shield')}</span>
        <div class="access-row__text"><strong>Verificación en dos pasos</strong><p>${texto}</p></div>
        <div class="access-row__actions">${st.enabled
            ? html`<button type="button" class="btn btn--secondary btn--sm" data-action="2fa-codes">Códigos nuevos</button>
                ${st.required ? '' : html`<button type="button" class="btn btn--ghost btn--sm" data-action="2fa-off">Desactivar</button>`}`
            : html`<button type="button" class="btn btn--primary btn--sm" data-action="2fa-on">${icon('shield')}Activar</button>`}</div>
    </div>`;
}

function sesiones(lista) {
    const otras = lista.filter((s) => !s.current).length;
    return html`<h3 class="access__sub">Dónde tienes la sesión abierta</h3>
        <ul class="sessions">${lista.map((s) => html`<li class="session">
            <span class="session__icon">${icon(esCelular(s.device) ? 'phone' : 'monitor')}</span>
            <div class="session__text">
                <strong>${s.device}</strong>${s.current ? html`<span class="tag">Este dispositivo</span>` : ''}
                <span>${s.current ? 'Activa ahora' : `Activa ${timeAgo(s.last_seen_at)}`}${s.ip ? ` · IP ${s.ip}` : ''} · desde ${longDate(s.created_at)}</span>
            </div>
            ${s.current ? '' : html`<button type="button" class="btn btn--ghost btn--sm" data-session="${s.id}">Cerrar</button>`}
        </li>`)}</ul>
        ${otras ? html`<button type="button" class="btn btn--secondary btn--sm" data-action="revoke-others">${icon('logout')}${otras === 1 ? 'Cerrar la otra sesión' : `Cerrar las otras ${otras} sesiones`}</button>` : ''}
        <p class="field__hint" style="margin-top:10px">Una sesión se cierra sola tras 14 días sin usarla. Si no reconoces un dispositivo, ciérralo y cambia tu contraseña.</p>`;
}

export async function profileView(root, _params, signal) {
    setHtml(root, html`<div class="page">${loading()}</div>`);
    let stats = {};
    let uso = null;
    [stats, uso] = await Promise.all([
        api.get('/api/user/stats').catch(() => ({})),
        api.get('/api/files/usage').catch(() => null),
    ]);

    function pintar() {
        const u = store.user;
        setHtml(root, html`<div class="page">
            <div class="page-head"><div><h1>Mi perfil</h1><p>Así te ven tus compañeros en los grupos y la biblioteca.</p></div></div>
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
                    </div>
                    <p style="margin-top:14px;font-size:13px">En la plataforma desde ${longDate(u.created_at)}</p>
                </section>
                <div style="display:flex;flex-direction:column;gap:18px">
                    <section class="panel">
                        <div class="panel__head"><h2>Preferencias</h2></div>
                        <div class="panel__body prefs">
                            <div class="field"><span class="field__label">Tema</span>
                                ${segmented('theme', [['system', 'Automático'], ['light', 'Claro'], ['dark', 'Oscuro']], prefs.get('theme'))}</div>
                            <div class="field"><span class="field__label">Animaciones</span>
                                ${segmented('motion', [['system', 'Automáticas'], ['reduced', 'Reducidas'], ['full', 'Completas']], prefs.get('motion'))}
                                <span class="field__hint">Las luces de Francis y la pantalla de entrada. «Reducidas» las deja quietas.</span></div>
                            <div class="field"><span class="field__label">Orden de la biblioteca</span>
                                ${segmented('library_sort', [['recent', 'Recientes'], ['popular', 'Populares'], ['title', 'Por título']], prefs.get('library_sort'))}</div>
                            <p class="field__hint">Se guardan en tu cuenta: te siguen al celular y a otras computadoras.</p>
                        </div>
                    </section>
                    ${uso ? html`<section class="panel">
                        <div class="panel__head"><h2>Tus archivos</h2></div>
                        <div class="panel__body" style="display:grid;gap:16px">
                            ${meter({ label: 'Espacio usado', value: uso.bytes, max: uso.quota_bytes, text: `${fileSize(uso.bytes) || '0 B'} de ${fileSize(uso.quota_bytes)}` })}
                            ${meter({ label: 'Subidas en las últimas 24 h', value: uso.uploads_24h, max: uso.uploads_per_day, text: `${uso.uploads_24h} de ${uso.uploads_per_day}` })}
                        </div>
                    </section>` : ''}
                    <form class="panel" data-form="profile">
                        <div class="panel__head"><h2>Datos personales</h2></div>
                        <div class="panel__body">
                            <label class="field"><span class="field__label">Nombre</span><input class="input" name="name" required maxlength="150" value="${u.name}"></label>
                            <div class="field"><span class="field__label">Tu carrera</span>
                                <span class="field__hint">Tus documentos la llevan y el dashboard te recomienda material de ella.</span></div>
                            ${careerFields()}
                            <label class="field" style="max-width:160px"><span class="field__label">Ciclo</span><input class="input" name="semester" type="number" min="1" max="12" value="${u.semester || ''}"></label>
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
                                <label class="field"><span class="field__label">Nueva contraseña</span><input class="input" name="new_password" type="password" autocomplete="new-password" minlength="8" required>
                                    <span class="field__hint">8 caracteres o más, con letras y números.</span></label>
                            </div>
                            <div data-slot="error"></div>
                        </div>
                        <div class="panel__foot" style="display:flex;justify-content:flex-end"><button class="btn btn--secondary" type="submit">${icon('key')}Cambiar contraseña</button></div>
                    </form>
                    <section class="panel" id="acceso">
                        <div class="panel__head"><h2>Acceso y sesiones</h2></div>
                        <div class="panel__body" data-slot="access">${loading()}</div>
                    </section>
                </div>
            </div>
        </div>`);
        fillCareer($('[data-form="profile"]', root), u.career).catch((err) => toast(err.message, 'error'));
        acceso();
    }

    async function acceso() {
        const slot = $('[data-slot="access"]', root);
        try {
            const [st, { sessions: lista }] = await Promise.all([api.get('/api/auth/2fa'), api.get('/api/auth/sessions')]);
            if (!slot.isConnected) return;
            if (st.enabled !== store.user.two_factor_enabled) store.setUser({ ...store.user, two_factor_enabled: st.enabled });
            setHtml(slot, html`${dosPasos(st)}${sesiones(lista)}`);
        } catch (err) {
            setHtml(slot, errorBox(err));
        }
    }

    on(root, 'click', '[data-action="2fa-on"]', () => openTwoFactorSetup({ onDone: acceso }), signal);
    on(root, 'click', '[data-action="2fa-codes"]', () => openNewRecoveryCodes({ onDone: acceso }), signal);
    on(root, 'click', '[data-action="2fa-off"]', () => openDisableTwoFactor({ onDone: acceso }), signal);
    on(root, 'click', '[data-session]', async (_e, b) => {
        b.disabled = true;
        try {
            await api.del(`/api/auth/sessions/${b.dataset.session}`);
            toast('Sesión cerrada en ese dispositivo');
            acceso();
        } catch (err) { toast(err.message, 'error'); b.disabled = false; }
    }, signal);
    on(root, 'click', '[data-action="revoke-others"]', async () => {
        if (!await confirmDialog({ title: 'Cerrar las otras sesiones', text: 'Se cerrará tu cuenta en todos los demás celulares y computadoras. Esta queda abierta.', confirmLabel: 'Cerrar sesiones' })) return;
        try {
            const r = await api.post('/api/auth/sessions/revoke-others');
            toast(r.closed === 1 ? 'Se cerró 1 sesión' : `Se cerraron ${r.closed} sesiones`);
            acceso();
        } catch (err) { toast(err.message, 'error'); }
    }, signal);

    on(root, 'click', '[data-pref] [data-value]', async (_e, b) => {
        const grupo = b.closest('[data-pref]');
        grupo.querySelectorAll('[data-value]').forEach((x) => x.setAttribute('aria-checked', String(x === b)));
        await prefs.set({ [grupo.dataset.pref]: b.dataset.value });
        toast('Preferencia guardada');
    }, signal);

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
                const r = await api.post('/api/profile/password', datos);
                form.reset();
                toast(r.closed_sessions ? `Contraseña actualizada. Se cerró tu sesión en ${r.closed_sessions === 1 ? 'otro dispositivo' : `otros ${r.closed_sessions} dispositivos`}.` : 'Contraseña actualizada');
                acceso();
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
