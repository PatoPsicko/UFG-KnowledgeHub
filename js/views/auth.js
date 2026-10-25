/**
 * Pantalla de acceso: iniciar sesión y crear cuenta.
 *
 * Sólo se aceptan correos institucionales (lo comprueba el servidor; aquí se
 * avisa antes de enviar). Los mensajes de error vienen del backend, que nunca
 * revela si un correo tiene cuenta.
 */

import { api } from '../core/api.js';
import { $, html, on, setHtml } from '../core/dom.js';
import { errorBox } from '../ui/components.js';
import { icon } from '../ui/icons.js';

// Lomos de la estantería del panel izquierdo: [ancho, alto %, color, inclinado]
const SHELF = [
    [30, 78, '#0B6FCB'], [22, 64, '#F08A0B'], [34, 88, '#2E7D6B'], [26, 70, '#B5487A'], [20, 56, '#D9822B'],
    [32, 92, '#12325A', true], [28, 74, '#6B4FA3'], [24, 60, '#0B6FCB'], [36, 84, '#C2453A'], [22, 68, '#F08A0B'],
    [30, 90, '#3F7A2E'], [26, 62, '#8A6D1F'], [34, 80, '#1B416F'], [24, 72, '#0B6FCB'],
];

function shelf() {
    return html`<div class="shelf" aria-hidden="true">${SHELF.map(([w, h, c, tilt], i) =>
        html`<i class="${tilt ? 'is-tilt' : ''}" style="--w:${w}px;--h:${h}%;--c:${c};--d:${(0.15 + i * 0.05).toFixed(2)}s"></i>`)}</div>
        <div class="shelf__base"></div>`;
}

function loginForm() {
    return html`<form class="auth__form" id="login-form" novalidate>
        <h2>Inicia sesión</h2>
        <p>Entra con tu correo institucional para ver la biblioteca, el asistente y tus grupos.</p>
        <label class="field"><span class="field__label">Correo</span>
            <input class="input" name="email" type="email" autocomplete="email" inputmode="email" placeholder="nombre.apellido@ufg.edu.sv" required></label>
        <label class="field"><span class="field__label">Contraseña</span>
            <span class="pw"><input class="input" name="password" type="password" autocomplete="current-password" required>
            <button type="button" class="icon-btn icon-btn--sm" data-action="toggle-pw" aria-label="Mostrar contraseña">${icon('eye')}</button></span></label>
        <div class="form-slot"></div>
        <button class="btn btn--primary btn--block" type="submit" style="margin-top:20px;height:44px">Entrar</button>
        <p class="auth__switch">¿Primera vez aquí? <button type="button" data-action="show-register">Crea tu cuenta</button></p>
    </form>`;
}

// Reglas de registro: se piden al servidor; mientras tanto, las de siempre.
const politica = { domains: ['ufg.edu.sv'], domains_label: '@ufg.edu.sv', password_min_length: 8, email_verification: false };

function dominioPermitido(correo) {
    const dominio = (correo.split('@')[1] || '').trim().toLowerCase();
    return politica.domains.some((d) => d === '*' || dominio === d || (d.startsWith('*.') && (dominio === d.slice(2) || dominio.endsWith(d.slice(1)))));
}

function registerForm() {
    const colores = ['#0B6FCB', '#F08A0B', '#2E7D6B', '#B5487A', '#6B4FA3', '#C2453A', '#12325A'];
    return html`<form class="auth__form" id="register-form" novalidate>
        <h2>Crea tu cuenta</h2>
        <p>Comparte material con tu facultad y estudia con el asistente.</p>
        <label class="field"><span class="field__label">Nombre completo</span>
            <input class="input" name="name" autocomplete="name" required maxlength="150"></label>
        <label class="field"><span class="field__label">Correo institucional</span>
            <input class="input" name="email" type="email" autocomplete="email" inputmode="email" placeholder="nombre.apellido@ufg.edu.sv" required>
            <span class="field__hint" data-slot="domain-hint">Sólo correos ${politica.domains_label}.</span></label>
        <label class="field"><span class="field__label">Contraseña</span>
            <span class="pw"><input class="input" name="password" type="password" autocomplete="new-password" minlength="${politica.password_min_length}" required>
            <button type="button" class="icon-btn icon-btn--sm" data-action="toggle-pw" aria-label="Mostrar contraseña">${icon('eye')}</button></span>
            <span class="field__hint">${politica.password_min_length} caracteres o más, con letras y números.</span></label>
        <div class="field"><span class="field__label">Color de tu avatar</span>
            <div class="swatches" role="radiogroup">${colores.map((c, i) => html`<button type="button" class="swatch" role="radio" data-color="${c}" aria-pressed="${i === 0}" aria-label="Color ${c}" style="background:${c}"></button>`)}</div></div>
        <input type="hidden" name="profile_color" value="${colores[0]}">
        <div class="form-slot"></div>
        <button class="btn btn--primary btn--block" type="submit" style="margin-top:20px;height:44px">Crear cuenta</button>
        <p class="auth__switch">¿Ya tienes cuenta? <button type="button" data-action="show-login">Inicia sesión</button></p>
    </form>`;
}

export function renderAuth(root, { onLogin }) {
    const controller = new AbortController();
    const { signal } = controller;
    setHtml(root, html`<div class="auth">
        <section class="auth__side">
            <div class="auth__brand"><img src="img/logo_hub.png" alt="UFG Knowledge Hub"></div>
            <div>
                <h1>Apuntes, guías y proyectos de toda la UFG, en un solo lugar.</h1>
                <p>Una biblioteca que arman los propios estudiantes, con grupos de trabajo y un asistente que responde citando los documentos.</p>
                ${shelf()}
                <div class="auth__facts">
                    <span>${icon('shield')}Cada archivo pasa por un vigilante de seguridad</span>
                    <span>${icon('bulb')}El asistente cita de qué documento sale cada dato</span>
                </div>
            </div>
            <div style="font-size:13px;color:#7F95B1">Proyecto académico de la Universidad Francisco Gavidia</div>
        </section>
        <main class="auth__main" id="auth-main">${loginForm()}</main>
    </div>`);

    const main = $('#auth-main', root);
    api.get('/api/auth/policy').then((p) => Object.assign(politica, p)).catch(() => {});

    on(main, 'click', '[data-action="show-register"]', () => { setHtml(main, registerForm()); $('[name="name"]', main).focus(); }, signal);
    on(main, 'click', '[data-action="show-login"]', () => { setHtml(main, loginForm()); $('[name="email"]', main).focus(); }, signal);
    on(main, 'click', '[data-action="toggle-pw"]', (_e, btn) => {
        const input = btn.parentElement.querySelector('input');
        input.type = input.type === 'password' ? 'text' : 'password';
        btn.setAttribute('aria-label', input.type === 'password' ? 'Mostrar contraseña' : 'Ocultar contraseña');
    }, signal);
    on(main, 'click', '.swatch', (_e, btn) => {
        main.querySelectorAll('.swatch').forEach((s) => s.setAttribute('aria-pressed', String(s === btn)));
        main.querySelector('[name="profile_color"]').value = btn.dataset.color;
    }, signal);

    main.addEventListener('submit', async (e) => {
        e.preventDefault();
        const form = e.target;
        const slot = $('.form-slot', form);
        const boton = form.querySelector('[type="submit"]');
        const datos = Object.fromEntries(new FormData(form));
        setHtml(slot, '');
        boton.disabled = true;
        try {
            if (form.id === 'register-form') {
                if (!dominioPermitido(datos.email)) {
                    throw new Error(`Usa tu correo institucional (${politica.domains_label}).`);
                }
                const reg = await api.post('/api/register', datos);
                if (reg.verification_required) {
                    setHtml(main, loginForm());
                    setHtml($('.form-slot', main), html`<div class="notice">${icon('check')}<span>${reg.message}</span></div>`);
                    $('[name="email"]', main).value = datos.email;
                    return;
                }
            }
            const r = await api.post('/api/login', { email: datos.email, password: datos.password });
            api.setToken(r.token);
            controller.abort();
            onLogin(r.user);
        } catch (err) {
            setHtml(slot, html`${errorBox(err)}${err.code === 'email_unverified'
                ? html`<button type="button" class="btn btn--ghost btn--sm" data-action="resend" style="margin-top:8px">Enviar el enlace otra vez</button>` : ''}`);
            boton.disabled = false;
        }
    }, { signal });

    on(main, 'click', '[data-action="resend"]', async (_e, b) => {
        b.disabled = true;
        const { message } = await api.post('/api/resend-verification', { email: $('[name="email"]', main).value }).catch((e) => e);
        b.textContent = message;
    }, signal);

    $('[name="email"]', main)?.focus();
}
