/**
 * Áreas y categorías de la biblioteca. Cada área tiene su color de «lomo»
 * (variables --spine-* en css/app.css).
 */

export const AREAS = [
    { key: 'tec', name: 'Tecnología y computación', items: ['Programación', 'Base de Datos', 'Inteligencia Artificial', 'Desarrollo Web', 'Redes y Seguridad', 'Sistemas Operativos', 'Ingeniería de Software', 'Machine Learning'] },
    { key: 'cie', name: 'Ciencias básicas', items: ['Matemáticas', 'Física', 'Química', 'Cálculo', 'Estadística', 'Álgebra', 'Geometría'] },
    { key: 'dis', name: 'Diseño y creatividad', items: ['Diseño Gráfico', 'Diseño UX/UI', 'Animación Digital', 'Fotografía', 'Arquitectura', 'Dibujo Técnico'] },
    { key: 'neg', name: 'Negocios y administración', items: ['Administración', 'Contabilidad', 'Marketing', 'Economía', 'Finanzas', 'Emprendimiento'] },
    { key: 'soc', name: 'Derecho y ciencias sociales', items: ['Derecho Civil', 'Derecho Penal', 'Psicología', 'Sociología', 'Comunicación', 'Periodismo'] },
    { key: 'sal', name: 'Ciencias de la salud', items: ['Medicina', 'Enfermería', 'Nutrición', 'Farmacología', 'Anatomía', 'Fisiología'] },
    { key: 'hum', name: 'Idiomas y humanidades', items: ['Inglés', 'Español', 'Literatura', 'Historia', 'Filosofía', 'Lingüística'] },
    { key: 'ing', name: 'Ingenierías', items: ['Ingeniería Civil', 'Ingeniería Industrial', 'Ingeniería Eléctrica', 'Ingeniería Mecánica', 'Ingeniería Química'] },
];

const AREA_BY_CATEGORY = new Map(AREAS.flatMap((a) => a.items.map((c) => [c, a])));

export function areaOf(category) {
    return AREA_BY_CATEGORY.get(category) || { key: 'otro', name: 'Otras', items: [] };
}

export function spineVar(category) {
    return `--spine: var(--spine-${areaOf(category).key})`;
}

export const SUGGESTED_TAGS = ['apuntes', 'guía', 'ejercicios', 'examen', 'resumen', 'laboratorio', 'proyecto', 'tutorial', 'presentación'];

const TYPE_LABEL = {
    pdf: 'PDF', doc: 'DOC', docx: 'DOCX', xls: 'XLS', xlsx: 'XLSX', ppt: 'PPT', pptx: 'PPTX', txt: 'TXT',
    md: 'MD', csv: 'CSV', rtf: 'RTF', odt: 'ODT', odp: 'ODP', ods: 'ODS', png: 'PNG', jpg: 'JPG', jpeg: 'JPG',
    gif: 'GIF', webp: 'WEBP', zip: 'ZIP', rar: 'RAR', '7z': '7Z',
};

export function typeLabel(ext) {
    return TYPE_LABEL[(ext || '').toLowerCase()] || (ext || 'ARCH').toUpperCase().slice(0, 4);
}

export const PREVIEWABLE = new Set(['pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'txt', 'md', 'csv']);
