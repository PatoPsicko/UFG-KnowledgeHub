"""Qué documentos existen y cómo se describen ante el índice del asistente.

Sólo se indexan los archivos que el escáner de seguridad dejó pasar: un
documento en revisión o bloqueado nunca llega a las respuestas del asistente
(evita, por ejemplo, que un PDF con instrucciones ocultas manipule al modelo).
"""

from __future__ import annotations

from typing import Iterator

from flask import current_app

from ..extensions import db
from ..models import VISIBLE_STATUSES, Group, GroupResource, PrivateResource, Resource
from ..storage import path_for
from . import index


def spec_resource(r: Resource) -> index.DocSpec:
    return index.DocSpec(
        kind='public', resource_id=r.id, title=r.title, owner_id=r.owner_id, origin='Biblioteca',
        header=(f'Autor: {r.author}. Categoría: {r.category or "-"}. Etiquetas: {r.tags or "-"}. '
                f'{r.description or ""}').strip(),
        path=path_for('public', r.filename))


def spec_private(p: PrivateResource) -> index.DocSpec:
    if p.type == 'file':
        return index.DocSpec(kind='private_file', resource_id=p.id, title=p.title, owner_id=p.owner_id,
                             origin='Mi espacio', path=path_for('private', p.filename, p.owner_id))
    return index.DocSpec(kind='private_note', resource_id=p.id, title=p.title, owner_id=p.owner_id,
                         origin='Mi espacio', text=f'{p.title}\n{p.content or ""}')


def spec_group_resource(g: GroupResource, group_name: str | None = None) -> index.DocSpec:
    if group_name is None:
        grupo = db.session.get(Group, g.group_id)
        group_name = grupo.name if grupo else ''
    return index.DocSpec(
        kind='group', resource_id=g.id, title=g.title, owner_id=g.user_id, group_id=g.group_id,
        origin=f'Grupo {group_name}'.strip(), header=f'Descripción: {g.description or "-"}.',
        path=path_for('group', g.filename, g.group_id))


def all_specs() -> Iterator[index.DocSpec]:
    for r in Resource.query.all():
        if r.scan_status in VISIBLE_STATUSES:
            yield spec_resource(r)
    for p in PrivateResource.query.all():
        if p.type == 'note' or p.scan_status in VISIBLE_STATUSES:
            yield spec_private(p)
    nombres = {g.id: g.name for g in Group.query.all()}
    for g in GroupResource.query.all():
        if g.scan_status in VISIBLE_STATUSES:
            yield spec_group_resource(g, nombres.get(g.group_id, ''))


def reindex(spec: index.DocSpec) -> None:
    """Encola el (re)indexado; nunca hace fallar la operación que lo pide."""
    try:
        index.encolar_indexado(spec)
    except Exception as exc:
        current_app.logger.warning('No se pudo encolar el indexado de %s: %s', spec.key, exc)


def unindex(kind: str, resource_id: int) -> None:
    try:
        index.encolar_borrado(f'{kind}:{resource_id}')
    except Exception as exc:
        current_app.logger.warning('No se pudo quitar %s:%s del índice: %s', kind, resource_id, exc)
