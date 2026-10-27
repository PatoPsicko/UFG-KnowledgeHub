/**
 * Los cinco módulos de la app: la barra lateral (lomos), la barra inferior del
 * celular y la paleta «Ir a…». Idea para más adelante: un librero en Inicio
 * con un libro por módulo (boceto en views/shelf.js, hoy sin ruta).
 */

export const SECTIONS = [
    { path: '/inicio', label: 'Inicio', icon: 'home', color: '#0B6FCB', blurb: 'Lo nuevo de tu carrera' },
    { path: '/francis', label: 'Francis', icon: 'robot', color: '#E07E05', blurb: 'Pregúntale a Francis' },
    { path: '/biblioteca', label: 'Biblioteca', icon: 'library', color: '#1F4F86', blurb: 'Material de toda la UFG' },
    { path: '/grupos', label: 'Grupos', icon: 'users', color: '#2E7D6B', blurb: 'Tareas, archivos y chat', badge: (p) => p.groups_unread_total },
    { path: '/anotaciones', label: 'Mi espacio', icon: 'note', color: '#6B4FA3', blurb: 'Tus notas y archivos' },
];

