/**
 * Verificación en dos pasos: activar (contraseña → QR → código), confirmar la
 * sesión con un código y mostrar los códigos de respaldo.
 *
 * Funciona con cualquier app de códigos: Google Authenticator, Microsoft
 * Authenticator, Authy, el llavero de iPhone...
 */

import { api } from '../core/api.js';
import { $, html } from '../core/dom.js';
import { icon } from './icons.js';
import { openDialog, toast } from './overlay.js';

const campoCodigo = (label = 'Código de 6 dígitos') => html`<label class="field"><span class="field__label">${label}</span>
    <input class="input input--code" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="9"
        placeholder="000000" required></label>`;

const campoClave = () => html`<label class="field"><span class="field__label">Tu contraseña</span>
    <input class="input" name="password" type="password" autocomplete="current-password" required></label>`;

function svgComoImagen(svg) {
    const datos = btoa(svg);  // el SVG del QR es sólo ASCII
    return html`<img class="qr" src="data:image/svg+xml;base64,${datos}" alt="Código QR para la app de verificación">`;
}

/** Muestra los códigos de respaldo (sólo se ven esta vez). */
export function showRecoveryCodes(codigos, { onClose } = {}) {
    const dlg = openDialog({
        title: 'Guarda tus códigos de respaldo',
        description: 'Si pierdes el celular, cada código sirve una vez para entrar. Es la única vez que se muestran.',
        body: html`<ol class="recovery">${codigos.map((c) => html`<li><code>${c}</code></li>`)}</ol>
            <button type="button" class="btn btn--secondary btn--sm" data-action="copy">${icon('copy')}Copiar todos</button>
            <p class="field__hint" style="margin-top:12px">Guárdalos en un lugar seguro (no en el mismo celular): una nota en la compu, papel o tu gestor de contraseñas.</p>`,
        submitLabel: 'Ya los guardé',
        cancelLabel: 'Cerrar',
        onSubmit: () => true,
    });
    $('[data-action="copy"]', dlg).addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(`UFG Knowledge Hub - códigos de respaldo\n${codigos.join('\n')}`);
            toast('Códigos copiados');
        } catch { toast('No se pudo copiar: selecciónalos a mano', 'error'); }
    });
    dlg.addEventListener('close', () => onClose?.());
}

/** Activa la verificación en dos pasos. `onDone(status)` al terminar. */
export function openTwoFactorSetup({ onDone } = {}) {
    openDialog({
        title: 'Activar verificación en dos pasos',
        description: 'Además de la contraseña, al entrar se pedirá un código que cambia cada 30 segundos en tu celular.',
        body: html`<ol class="steps-mini">
                <li>Instala una app de códigos: Google Authenticator, Microsoft Authenticator o Authy.</li>
                <li>Confirma tu contraseña para ver el código QR.</li>
            </ol>${campoClave()}`,
        submitLabel: 'Continuar',
        onSubmit: async (form) => {
            const datos = await api.post('/api/auth/2fa/setup', { password: form.password.value });
            setTimeout(() => pasoQr(datos, onDone));
        },
        onOpen: (_dlg, form) => form.password.focus(),
    });
}

function pasoQr({ secret, qr_svg: svg }, onDone) {
    const agrupado = secret.match(/.{1,4}/g).join(' ');
    openDialog({
        title: 'Escanea el código',
        description: 'En la app toca «Agregar» y escanea este código. Luego escribe el número que aparece.',
        body: html`<div class="qr-box">${svgComoImagen(svg)}
                <details><summary>¿No puedes escanear? Escribe la clave a mano</summary>
                    <code class="secret">${agrupado}</code></details></div>
            ${campoCodigo()}`,
        submitLabel: 'Activar',
        onSubmit: async (form) => {
            const r = await api.post('/api/auth/2fa/enable', { code: form.code.value });
            toast('Verificación en dos pasos activada');
            setTimeout(() => showRecoveryCodes(r.recovery_codes, { onClose: () => onDone?.(r.status) }));
        },
        onOpen: (_dlg, form) => form.code.focus(),
    });
}

/** Confirma esta sesión con un código (para entrar al panel de Seguridad). */
export function openStepUp({ onDone } = {}) {
    openDialog({
        title: 'Confirma que eres tú',
        description: 'Escribe el código de tu app de verificación (o uno de respaldo).',
        body: campoCodigo('Código'),
        submitLabel: 'Confirmar',
        onSubmit: async (form) => {
            const r = await api.post('/api/auth/2fa/step-up', { code: form.code.value });
            setTimeout(() => onDone?.(r.status));
        },
        onOpen: (_dlg, form) => form.code.focus(),
    });
}

/** Códigos de respaldo nuevos (los anteriores dejan de valer). */
export function openNewRecoveryCodes({ onDone } = {}) {
    openDialog({
        title: 'Códigos de respaldo nuevos',
        description: 'Los códigos anteriores dejarán de servir.',
        body: campoClave(),
        submitLabel: 'Generar',
        onSubmit: async (form) => {
            const r = await api.post('/api/auth/2fa/recovery-codes', { password: form.password.value });
            setTimeout(() => showRecoveryCodes(r.recovery_codes, { onClose: () => onDone?.(r.status) }));
        },
        onOpen: (_dlg, form) => form.password.focus(),
    });
}

/** Desactivar: pide contraseña y un código. */
export function openDisableTwoFactor({ onDone } = {}) {
    openDialog({
        title: 'Desactivar verificación en dos pasos',
        description: 'Tu cuenta quedará protegida sólo con la contraseña.',
        body: html`${campoClave()}${campoCodigo('Código de la app o de respaldo')}`,
        submitLabel: 'Desactivar',
        danger: true,
        onSubmit: async (form) => {
            const r = await api.post('/api/auth/2fa/disable', { password: form.password.value, code: form.code.value });
            toast('Verificación en dos pasos desactivada');
            setTimeout(() => onDone?.(r.status));
        },
    });
}
