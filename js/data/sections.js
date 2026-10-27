/**
 * Los cinco módulos de la app: son los libros del librero de Inicio, la barra
 * inferior del celular y los destinos de la paleta «Ir a…».
 */

export const SECTIONS = [
    { path: '/dashboard', label: 'Dashboard', icon: 'dashboard', color: '#0B6FCB', blurb: 'Lo nuevo de tu carrera' },
    { path: '/francis', label: 'Francis', icon: 'robot', color: '#E07E05', blurb: 'Pregúntale a Francis' },
    { path: '/biblioteca', label: 'Biblioteca', icon: 'library', color: '#1F4F86', blurb: 'Material de toda la UFG' },
    { path: '/grupos', label: 'Grupos', icon: 'users', color: '#2E7D6B', blurb: 'Tareas, archivos y chat', badge: (p) => p.groups_unread_total },
    { path: '/anotaciones', label: 'Mi espacio', icon: 'note', color: '#6B4FA3', blurb: 'Tus notas y archivos' },
];

const OTRAS = { '/perfil': 'Mi perfil', '/seguridad': 'Seguridad' };

/** Nombre de la sección para la barra superior. */
export function sectionTitle(path) {
    const s = SECTIONS.find((it) => path.startsWith(it.path));
    if (s) return s.label;
    if (path.startsWith('/asistente')) return 'Francis';
    return Object.entries(OTRAS).find(([p]) => path.startsWith(p))?.[1] || '';
}
