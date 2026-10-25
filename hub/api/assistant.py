"""Rutas del asistente de IA (RAG sobre los documentos de la plataforma).

Contrato:

POST /api/ai/chat          {"question", "conversation_id"?, "doc_key"?}
    -> {"answer", "conversation_id", "sources": [...], "documents": [...], "model", "search_mode"}
POST /api/ai/chat/stream   misma petición; respuesta NDJSON, un objeto por línea:
    {"type":"sources", ...}  {"type":"token","content":"..."}  ...
    {"type":"done","conversation_id","sources","documents","model"} | {"type":"error","message"}
GET  /api/ai/status        estado de los modelos y documentos indexados
GET  /api/ai/conversations historial de conversaciones del usuario
GET  /api/ai/history?conversation_id=...   mensajes de una conversación
DELETE /api/ai/conversations/<id>
"""

from __future__ import annotations

import json
import time

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from ..ai import assistant, index, llm
from ..errors import ApiError
from ..extensions import db
from ..models import AIConversation, AIMessage, iso_utc
from ..utils import current_user, json_body, login_required, user_group_ids

bp = Blueprint('assistant', __name__, url_prefix='/api/ai')


def _conversation(user_id: int, conversation_id) -> AIConversation | None:
    """Una conversación ajena o inexistente no da error: se empieza una nueva."""
    if not conversation_id:
        return None
    conv = db.session.get(AIConversation, str(conversation_id))
    return conv if conv and conv.user_id == user_id else None


def _preparar() -> tuple[assistant.Contexto, AIConversation | None, int]:
    viewer = current_user()
    data = json_body()
    conv = _conversation(viewer.id, data.get('conversation_id'))
    historial = [(m.role, m.content) for m in conv.messages[-assistant.AI_HISTORY_TURNS:]] if conv else []
    doc_key = (data.get('doc_key') or '').strip() or None
    ctx = assistant.preparar(viewer.id, user_group_ids(viewer.id), data.get('question') or '', historial, doc_key)
    return ctx, conv, viewer.id


def _guardar(user_id: int, conv: AIConversation | None, ctx: assistant.Contexto, respuesta: str,
             sources: list[dict], documents: list[dict], modelo: str | None) -> str:
    if conv is None:
        conv = AIConversation(user_id=user_id, title=ctx.question[:120])
        db.session.add(conv)
        db.session.flush()
    db.session.add(AIMessage(conversation_id=conv.id, role='user', content=ctx.question))
    db.session.add(AIMessage(conversation_id=conv.id, role='assistant', content=respuesta, model=modelo,
                             sources=json.dumps({'sources': sources, 'documents': documents}, ensure_ascii=False)))
    db.session.commit()
    return conv.id


@bp.get('/status')
@login_required
def status():
    viewer = current_user()
    estado = llm.router().status()
    idx = index.indice()
    primario = estado['primary']
    payload = {
        'available': estado['available'],
        'model': primario['model'] if primario else None,
        'provider': primario['provider'] if primario else None,
        'provider_label': primario['label'] if primario else None,
        'security_model': estado['security'],
        'embeddings': estado['embeddings'],
        'search_mode': 'hibrido' if idx.coleccion() is not None else 'lexico',
        'indexed_documents': idx.contar_accesibles(viewer.id, user_group_ids(viewer.id)),
    }
    if viewer.is_admin:
        payload['providers'] = estado['providers']
        payload['index'] = idx.estadisticas()
    return jsonify(payload), 200


@bp.post('/chat')
@login_required
def chat():
    ctx, conv, user_id = _preparar()
    t0 = time.perf_counter()
    respuesta, meta = assistant.generar(ctx)
    sources, documents = assistant.fuentes_citadas(ctx, respuesta)
    modelo = f"{meta['provider']}/{meta['model']}" if meta.get('provider') else None
    conv_id = _guardar(user_id, conv, ctx, respuesta, sources, documents, modelo)
    tiempos = {**ctx.info.get('tiempos_ms', {}), 'generacion': round((time.perf_counter() - t0) * 1000)}
    current_app.logger.info('Asistente: modo=%s modelo=%s tiempos=%s', ctx.info.get('modo'), modelo, tiempos)
    return jsonify({'answer': respuesta, 'conversation_id': conv_id, 'sources': sources, 'documents': documents,
                    'model': modelo, 'search_mode': ctx.info.get('modo'), 'timings_ms': tiempos}), 200


@bp.post('/chat/stream')
@login_required
def chat_stream():
    ctx, conv, user_id = _preparar()
    conv_id_inicial = conv.id if conv else None
    app = current_app._get_current_object()

    def linea(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False) + '\n'

    def generar():
        yield linea({'type': 'sources', 'sources': ctx.sources, 'documents': ctx.documents,
                     'search_mode': ctx.info.get('modo')})
        t0 = time.perf_counter()
        partes: list[str] = []
        meta: dict = {}
        if ctx.respuesta_directa:
            partes.append(ctx.respuesta_directa)
            yield linea({'type': 'token', 'content': ctx.respuesta_directa})
        else:
            if not assistant.cola_modelo.acquire(timeout=assistant.AI_QUEUE_TIMEOUT):
                yield linea({'type': 'error', 'message': 'El asistente está atendiendo muchas preguntas. '
                                                         'Inténtalo en un momento.'})
                return
            try:
                # Los primeros caracteres se retienen para detectar el marcador de
                # «fuera de tema» antes de mostrar nada al estudiante.
                general = not ctx.fragmentos and not ctx.catalogo
                retenido = ''
                decidido = False
                modelo_avisado = False
                for trozo in llm.router().chat_stream(assistant.build_messages(ctx), temperature=0.2, meta=meta):
                    if not modelo_avisado and meta:
                        modelo_avisado = True
                        yield linea({'type': 'model', 'model': meta.get('model'), 'provider': meta.get('provider'),
                                     'label': meta.get('label')})
                    if decidido:
                        partes.append(trozo)
                        yield linea({'type': 'token', 'content': trozo})
                        continue
                    retenido += trozo
                    if assistant.MARCADOR_FUERA in retenido:
                        break
                    if len(retenido) < len(assistant.MARCADOR_FUERA) + 4:
                        continue
                    decidido = True
                    if general and not retenido.lstrip().startswith(assistant.AVISO_GENERAL[:12]):
                        retenido = f'{assistant.AVISO_GENERAL}\n\n{retenido}'
                    partes.append(retenido)
                    yield linea({'type': 'token', 'content': retenido})
                if not decidido:
                    texto = assistant.fuera_de_tema() if assistant.MARCADOR_FUERA in retenido else retenido
                    partes.append(texto)
                    yield linea({'type': 'token', 'content': texto})
            except llm.LLMError as exc:
                app.logger.error('Asistente (stream): %s', exc)
                yield linea({'type': 'error', 'message': 'El modelo de IA no está respondiendo en este momento. '
                                                         'Inténtalo más tarde.'})
                return
            finally:
                assistant.cola_modelo.release()

        respuesta = ''.join(partes).strip()
        # Si el modelo repitió el aviso, no se muestra dos veces.
        aviso = assistant.AVISO_GENERAL
        if respuesta.count(aviso) > 1:
            respuesta = aviso + respuesta.split(aviso, 2)[-1]
        sources, documents = assistant.fuentes_citadas(ctx, respuesta)
        modelo = f"{meta['provider']}/{meta['model']}" if meta.get('provider') else None
        try:
            conv_actual = db.session.get(AIConversation, conv_id_inicial) if conv_id_inicial else None
            conv_id = _guardar(user_id, conv_actual, ctx, respuesta, sources, documents, modelo)
        except Exception as exc:
            db.session.rollback()
            app.logger.error('No se pudo guardar la conversación: %s', exc)
            conv_id = conv_id_inicial
        yield linea({'type': 'done', 'conversation_id': conv_id, 'sources': sources, 'documents': documents,
                     'model': modelo, 'timings_ms': {**ctx.info.get('tiempos_ms', {}),
                                                     'generacion': round((time.perf_counter() - t0) * 1000)}})

    return Response(stream_with_context(generar()), mimetype='application/x-ndjson',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@bp.get('/conversations')
@login_required
def conversations():
    viewer = current_user()
    filas = (AIConversation.query.filter_by(user_id=viewer.id)
             .order_by(AIConversation.created_at.desc()).limit(30).all())
    return jsonify({'conversations': [{
        'id': c.id,
        'title': c.title or (c.messages[0].content[:120] if c.messages else 'Conversación'),
        'created_at': iso_utc(c.created_at),
        'messages': len(c.messages),
    } for c in filas]}), 200


@bp.get('/history')
@login_required
def history():
    viewer = current_user()
    conv = _conversation(viewer.id, request.args.get('conversation_id'))
    if conv is None:
        raise ApiError('Conversación no encontrada.', 404)

    def fuentes(m: AIMessage) -> tuple[list, list]:
        if not m.sources:
            return [], []
        data = json.loads(m.sources)
        if isinstance(data, list):  # formato anterior: sólo la lista de fuentes
            return data, []
        return data.get('sources', []), data.get('documents', [])

    mensajes = []
    for m in conv.messages:
        s, d = fuentes(m)
        mensajes.append({'role': m.role, 'content': m.content, 'sources': s, 'documents': d, 'model': m.model,
                         'created_at': iso_utc(m.created_at)})
    return jsonify({'conversation_id': conv.id, 'messages': mensajes}), 200


@bp.delete('/conversations/<conversation_id>')
@login_required
def delete_conversation(conversation_id: str):
    conv = _conversation(current_user().id, conversation_id)
    if conv is None:
        raise ApiError('Conversación no encontrada.', 404)
    db.session.delete(conv)
    db.session.commit()
    return jsonify({'message': 'Conversación eliminada.'}), 200
