"""Modelos de la base de datos (SQLite vía SQLAlchemy).

Los nombres de tabla son los de la versión anterior para que la base ya
existente siga funcionando. Las columnas nuevas las añade schema.py al
arrancar, sin herramientas externas.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from .extensions import db


def utcnow() -> datetime:
    """Hora UTC sin zona (así guarda SQLite CURRENT_TIMESTAMP)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(dt: datetime | None) -> str | None:
    """Fecha en ISO 8601 marcada como UTC.

    SQLite guarda las fechas sin zona horaria; enviadas así el navegador las
    leía como hora local y el chat mostraba la hora desplazada.
    """
    return dt.isoformat() + 'Z' if dt else None


def display_filename(stored_name: str | None) -> str:
    """Nombre legible a partir del guardado (<uuid32>_<nombre>)."""
    if not stored_name:
        return ''
    partes = stored_name.split('_', 1)
    if len(partes) == 2 and len(partes[0]) == 32:
        return partes[1]
    return stored_name


# Estados del escáner de seguridad. NULL = archivo anterior al escáner (se
# revisa en segundo plano al arrancar y mientras tanto se trata como limpio).
SCAN_PENDING = 'pending'
SCAN_CLEAN = 'clean'
SCAN_REVIEW = 'review'
SCAN_BLOCKED = 'blocked'
VISIBLE_STATUSES = (SCAN_CLEAN, None)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    career = db.Column(db.String(100))
    semester = db.Column(db.Integer)
    bio = db.Column(db.String(280))
    profile_picture = db.Column(db.String(300))
    profile_color = db.Column(db.String(7), default='#0A6CC2')
    role = db.Column(db.String(20), default='student')  # student | admin
    # True para las cuentas anteriores a la verificación por correo; las nuevas
    # empiezan en False sólo si EMAIL_VERIFICATION está activo.
    email_verified = db.Column(db.Boolean, default=True)
    # Preferencias de la interfaz en JSON (tema, animaciones, orden de la biblioteca...).
    preferences = db.Column(db.Text)
    last_seen = db.Column(db.DateTime)
    # Último mensaje del chat global que el usuario vio (para contar no leídos).
    chat_last_read_id = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=db.func.now())

    resources = db.relationship('Resource', backref='owner', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True)
    owned_groups = db.relationship('Group', backref='owner', lazy=True)
    group_memberships = db.relationship('GroupMember', backref='user', lazy=True)
    sent_messages = db.relationship('DirectMessage', foreign_keys='DirectMessage.sender_id',
                                    backref='sender', lazy=True)
    received_messages = db.relationship('DirectMessage', foreign_keys='DirectMessage.receiver_id',
                                        backref='receiver', lazy=True)
    contacts_initiated = db.relationship('Contact', foreign_keys='Contact.user_id', backref='user', lazy=True)
    contacts_received = db.relationship('Contact', foreign_keys='Contact.contact_id',
                                        backref='contact_user', lazy=True)
    private_resources = db.relationship('PrivateResource', backref='owner', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    def prefs(self) -> dict:
        try:
            datos = json.loads(self.preferences) if self.preferences else {}
        except ValueError:
            datos = {}
        return datos if isinstance(datos, dict) else {}

    def public_dict(self) -> dict:
        """Datos que cualquier usuario autenticado puede ver."""
        return {
            'id': self.id,
            'name': self.name,
            'career': self.career,
            'profile_color': self.profile_color or '#0A6CC2',
            'avatar_url': f'/api/avatars/{self.profile_picture}' if self.profile_picture else None,
            'last_seen': iso_utc(self.last_seen),
        }

    def private_dict(self) -> dict:
        """Datos de la propia cuenta."""
        return {
            **self.public_dict(),
            'email': self.email,
            'semester': self.semester,
            'bio': self.bio,
            'role': self.role or 'student',
            'is_admin': self.is_admin,
            'email_verified': self.email_verified is not False,
            'preferences': self.prefs(),
            'created_at': iso_utc(self.created_at),
        }

    def __repr__(self) -> str:
        return f'<User {self.email}>'


class Resource(db.Model):
    """Documento de la biblioteca compartida."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    tags = db.Column(db.String(300))
    description = db.Column(db.Text)
    filename = db.Column(db.String(300), nullable=False)
    file_size = db.Column(db.Integer)
    downloads = db.Column(db.Integer, default=0)
    scan_status = db.Column(db.String(20))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())

    def __repr__(self) -> str:
        return f'<Resource {self.title}>'


class SavedResource(db.Model):
    """Documentos que un estudiante guarda para tenerlos a mano."""
    __table_args__ = (db.UniqueConstraint('user_id', 'resource_id', name='uq_saved_resource'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())


class ChatMessage(db.Model):
    """Mensaje del chat global."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())


class Contact(db.Model):
    """Relación de amistad. user_id envía la solicitud, contact_id la recibe."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    contact_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending')  # pending | accepted
    created_at = db.Column(db.DateTime, default=db.func.now())


class Group(db.Model):
    """Grupo de trabajo."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    subject = db.Column(db.String(120))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())

    members = db.relationship('GroupMember', backref='group', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('GroupMessage', backref='group', lazy=True, cascade='all, delete-orphan')
    resources = db.relationship('GroupResource', backref='group', lazy=True, cascade='all, delete-orphan')
    tasks = db.relationship('GroupTask', backref='group', lazy=True, cascade='all, delete-orphan')


class GroupMember(db.Model):
    __table_args__ = (db.UniqueConstraint('group_id', 'user_id', name='uq_group_member'),)
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    last_read_message_id = db.Column(db.Integer, default=0)
    joined_at = db.Column(db.DateTime, default=db.func.now())


class GroupMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())

    author = db.relationship('User', lazy='joined')


class GroupResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    file_size = db.Column(db.Integer)
    scan_status = db.Column(db.String(20))
    uploaded_at = db.Column(db.DateTime, default=db.func.now())

    uploader = db.relationship('User', lazy='joined')


class GroupTask(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='pending')  # pending | in_progress | completed
    due_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=db.func.now())

    creator = db.relationship('User', foreign_keys=[created_by], lazy='joined')
    assignee = db.relationship('User', foreign_keys=[assigned_to], lazy='joined')


class PrivateResource(db.Model):
    """Anotación privada: nota de texto o archivo personal."""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    filename = db.Column(db.String(300))
    file_size = db.Column(db.Integer)
    type = db.Column(db.String(20), default='note')  # note | file
    scan_status = db.Column(db.String(20))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())


class DirectMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    read = db.Column(db.Boolean, default=False)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    # contact_request | contact_accepted | message | group_invite | group_task | scan_result ...
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    related_id = db.Column(db.Integer)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.now())

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'message': self.message,
            'related_id': self.related_id,
            'read': bool(self.read),
            'created_at': iso_utc(self.created_at),
        }


class AIConversation(db.Model):
    """Conversación con el asistente. Pertenece a un único usuario."""
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=db.func.now())

    messages = db.relationship('AIMessage', backref='conversation', lazy=True,
                               cascade='all, delete-orphan', order_by='AIMessage.id')


class AIMessage(db.Model):
    """Un turno de la conversación. `sources` guarda en JSON las fuentes citadas."""
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(36), db.ForeignKey('ai_conversation.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user | assistant
    content = db.Column(db.Text, nullable=False)
    sources = db.Column(db.Text)
    model = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=db.func.now())


class FileScan(db.Model):
    """Resultado del escáner de seguridad para un archivo subido."""
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)  # public | group | private | avatar
    resource_id = db.Column(db.Integer, index=True)
    group_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    original_name = db.Column(db.String(300))
    stored_name = db.Column(db.String(300))
    sha256 = db.Column(db.String(64), index=True)
    size = db.Column(db.Integer)
    detected_type = db.Column(db.String(40))
    status = db.Column(db.String(20), default=SCAN_PENDING)
    summary = db.Column(db.String(500))
    static_report = db.Column(db.Text)  # JSON
    antivirus_report = db.Column(db.Text)  # JSON
    ai_report = db.Column(db.Text)  # JSON
    reviewed_by = db.Column(db.Integer)
    # Reintentos de la revisión con IA cuando no hubo cuota o red.
    ai_attempts = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=db.func.now())
    finished_at = db.Column(db.DateTime)

    uploader = db.relationship('User', lazy='joined')

    def to_dict(self) -> dict:
        def carga(texto):
            try:
                return json.loads(texto) if texto else None
            except ValueError:
                return None
        return {
            'id': self.id,
            'kind': self.kind,
            'resource_id': self.resource_id,
            'group_id': self.group_id,
            'user': self.uploader.public_dict() if self.uploader else None,
            'original_name': self.original_name,
            'sha256': self.sha256,
            'size': self.size,
            'detected_type': self.detected_type,
            'status': self.status,
            'summary': self.summary,
            'static': carga(self.static_report),
            'antivirus': carga(self.antivirus_report),
            'ai': carga(self.ai_report),
            'ai_attempts': self.ai_attempts or 0,
            'reviewed_by': self.reviewed_by,
            'created_at': iso_utc(self.created_at),
            'finished_at': iso_utc(self.finished_at),
        }


class LoginThrottle(db.Model):
    """Intentos fallidos de inicio de sesión por correo (exista o no la cuenta).

    Vive en la base de datos para que el bloqueo sobreviva a un reinicio del
    servidor. Se borra la fila al entrar con éxito.
    """
    email = db.Column(db.String(190), primary_key=True)
    failures = db.Column(db.Integer, default=0)
    first_failure_at = db.Column(db.DateTime)
    locked_until = db.Column(db.DateTime)


class BlockedHash(db.Model):
    """Huellas SHA-256 de archivos bloqueados: no se pueden volver a subir."""
    sha256 = db.Column(db.String(64), primary_key=True)
    reason = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=db.func.now())
