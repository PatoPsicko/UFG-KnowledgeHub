/** Reportar un documento y aviso de privacidad (Fase 3C). */

import { api } from '../core/api.js';
import { html } from '../core/dom.js';
import { openDialog, toast } from './overlay.js';

export const REPORT_REASONS = [
    ['malicious', 'Archivo peligroso o sospechoso'],
    ['inappropriate', 'Contenido inapropiado u ofensivo'],
    ['personal_data', 'Expone datos personales'],
    ['copyright', 'Derechos de autor (libro o material completo)'],
    ['spam', 'Spam o publicidad'],
    ['wrong', 'No es material de estudio o está mal clasificado'],
    ['other', 'Otro motivo'],
];

/** Abre el diálogo para reportar un documento. kind: public | group. */
export function reportDialog({ kind, resourceId, title, onDone = () => {} }) {
    openDialog({
        title: 'Reportar documento',
        description: `«${title}». Un administrador lo revisará; quien lo subió no sabrá quién lo reportó.`,
        submitLabel: 'Enviar reporte',
        body: html`<fieldset class="field report-reasons"><legend class="field__label">¿Qué pasa con este documento?</legend>
                ${REPORT_REASONS.map(([k, l], i) => html`<label class="radio"><input type="radio" name="reason" value="${k}" ${i === 0 ? 'required' : ''}><span>${l}</span></label>`)}
            </fieldset>
            <label class="field"><span class="field__label">Detalle (opcional)</span>
                <textarea class="textarea" name="comment" rows="3" maxlength="500" placeholder="Ej. En la página 3 aparecen los DUI de varios estudiantes."></textarea></label>`,
        onSubmit: async (form) => {
            const motivo = form.querySelector('input[name="reason"]:checked')?.value;
            if (!motivo) throw new Error('Elige un motivo.');
            const r = await api.post('/api/reports', { kind, resource_id: resourceId, reason: motivo, comment: form.comment.value.trim() });
            toast(r.message, 'success', 5000);
            onDone(r);
        },
    });
}

export function privacyNotice() {
    openDialog({
        title: 'Aviso de privacidad',
        wide: true,
        footer: false,
        body: html`<div class="privacy">
            <p><strong>UFG Knowledge Hub</strong> es un proyecto académico de la Universidad Francisco Gavidia. Este aviso explica qué datos guardamos y para qué.</p>
            <h3>Qué guardamos</h3>
            <ul>
                <li>Tu nombre, correo @ufg.edu.sv, carrera, ciclo, foto y preferencias.</li>
                <li>Los documentos y notas que subes, los grupos en los que participas, sus mensajes y tareas.</li>
                <li>Tus conversaciones con Francis, para que puedas retomarlas.</li>
                <li>Una bitácora de seguridad: inicios de sesión, dispositivo, dirección IP y acciones de administración, durante 180 días.</li>
            </ul>
            <h3>Para qué</h3>
            <ul>
                <li>Darte acceso a la biblioteca, tus grupos y tu espacio.</li>
                <li>Revisar que los archivos sean seguros: un vigilante automático y, en caso de duda, un administrador.</li>
                <li>Proteger tu cuenta (sesiones, verificación en dos pasos y detección de accesos sospechosos).</li>
            </ul>
            <h3>Con quién se comparte</h3>
            <ul>
                <li>Lo que publicas en la biblioteca lo ve la comunidad UFG; lo de un grupo, sólo sus miembros; Mi espacio, sólo tú.</li>
                <li>Para responder, Francis envía tu pregunta y fragmentos de los documentos que puedes ver a un proveedor de IA (Groq o Google). No se envía tu correo ni tu contraseña.</li>
                <li>No vendemos ni compartimos tus datos con terceros con fines comerciales.</li>
            </ul>
            <h3>Tus derechos</h3>
            <ul>
                <li>Descargar todos tus datos y archivos desde <em>Mi perfil → Privacidad</em>.</li>
                <li>Corregir tu perfil en cualquier momento.</li>
                <li>Borrar tu cuenta: se eliminan tu perfil, tus documentos, notas, mensajes de grupo y conversaciones.</li>
            </ul>
            <p class="muted">Dudas o solicitudes: escribe a la coordinación del proyecto.</p>
        </div>`,
    });
}
