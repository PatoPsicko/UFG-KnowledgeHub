import json
import os
import re
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, JWTManager
from werkzeug.utils import secure_filename
from werkzeug.exceptions import NotFound, RequestEntityTooLarge
from datetime import timedelta
import secrets
from sqlalchemy import text
from datetime import datetime

# Carga las variables del archivo .env si existe (JWT_SECRET_KEY, CORS_ORIGINS,
# DATABASE_PATH, FLASK_DEBUG). Es opcional: sin .env la app arranca igual con
# valores por defecto para desarrollo.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Se importa después de load_dotenv() porque lee OLLAMA_URL, OLLAMA_MODEL...
# al cargarse.
import ai_service

# --- 1. Configuración Inicial ---
app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)

# Modo depuración: sólo activo si se pide explícitamente por variable de entorno.
# Controla si los errores internos se devuelven al cliente (nunca en producción).
DEBUG_MODE = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')

# Configuración de CORS. Los orígenes permitidos se pueden ajustar sin tocar el
# código mediante la variable de entorno CORS_ORIGINS (separados por comas).
_default_origins = [
    "http://127.0.0.1:5500", "http://localhost:5500",
    "http://127.0.0.1:5501", "http://localhost:5501",
    "http://127.0.0.1:5001", "http://localhost:5001",
]
CORS_ORIGINS = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip()] or _default_origins
app.config['CORS_HEADERS'] = 'Content-Type'
CORS(app, origins=CORS_ORIGINS, supports_credentials=True)

# Configuración de la Base de Datos (SQLite).
# DATABASE_PATH permite apuntar a otra base sin tocar el código: útil para
# ejecutar pruebas sin ensuciar la base de datos real.
_db_path = os.environ.get('DATABASE_PATH') or os.path.join(app.instance_path, 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + _db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


def _load_jwt_secret():
    """Devuelve una clave JWT estable entre reinicios.

    Antes se generaba con secrets.token_hex() en cada arranque, lo que invalidaba
    todas las sesiones abiertas cada vez que el servidor se reiniciaba. Ahora se
    toma de JWT_SECRET_KEY y, si no existe, se genera UNA vez y se guarda en
    instance/ (fuera del control de versiones).
    """
    env_secret = os.environ.get('JWT_SECRET_KEY')
    if env_secret:
        return env_secret

    secret_path = os.path.join(app.instance_path, '.jwt_secret')
    if os.path.exists(secret_path):
        with open(secret_path, 'r', encoding='utf-8') as fh:
            saved = fh.read().strip()
            if saved:
                return saved

    generated = secrets.token_urlsafe(48)
    with open(secret_path, 'w', encoding='utf-8') as fh:
        fh.write(generated)
    return generated


# Configuración de JWT (Tokens de Sesión)
app.config['JWT_SECRET_KEY'] = _load_jwt_secret()
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)

# Configuración de la carpeta de subida de archivos
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Límite de tamaño por petición (16 MB) para evitar subidas que agoten el disco.
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Sólo se aceptan estos tipos de archivo. Se excluyen a propósito .html, .htm y
# .svg: al servirse desde el mismo origen podrían ejecutar JavaScript y robar la
# sesión de quien los abra (XSS almacenado).
ALLOWED_EXTENSIONS = {
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
    'txt', 'md', 'csv', 'rtf', 'odt',
    'png', 'jpg', 'jpeg', 'gif', 'webp',
    'zip', 'rar', '7z',
}

# --- 2. Inicialización de Extensiones ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)
migrate = Migrate(app, db)


# --- 2.1 Utilidades compartidas ---
def error_response(message, status=500, exc=None):
    """Respuesta de error uniforme.

    El detalle técnico de la excepción sólo se envía al cliente en modo debug;
    en producción se registra en consola pero no se expone, porque delataba
    rutas internas y estructura de la base de datos.
    """
    payload = {'message': message}
    if exc is not None:
        app.logger.error('%s: %s', message, exc)
        if DEBUG_MODE:
            payload['error'] = str(exc)
    return jsonify(payload), status


def allowed_file(filename):
    """True si la extensión está en la lista blanca."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def build_stored_filename(original_name):
    """Genera un nombre único conservando el nombre original como referencia.

    Antes se guardaba con secure_filename() a secas: si dos estudiantes subían
    'tarea.pdf', el segundo sobrescribía el archivo del primero y al borrar uno
    desaparecía el del otro. El prefijo aleatorio elimina esa colisión.
    """
    safe = secure_filename(original_name) or 'archivo'
    return f"{uuid.uuid4().hex}_{safe}"


def display_filename(stored_name):
    """Recupera el nombre legible a partir del nombre almacenado."""
    if not stored_name:
        return ''
    parts = stored_name.split('_', 1)
    if len(parts) == 2 and len(parts[0]) == 32:
        return parts[1]
    return stored_name


def save_upload(file_storage, subfolder=None):
    """Valida y guarda un archivo subido. Devuelve (nombre_guardado, error).

    Si error no es None, el archivo no se guardó y contiene una respuesta lista
    para devolver al cliente.
    """
    if not file_storage or file_storage.filename == '':
        return None, error_response('No se seleccionó ningún archivo', 400)

    if not allowed_file(file_storage.filename):
        permitidas = ', '.join(sorted(ALLOWED_EXTENSIONS))
        return None, error_response(
            f'Tipo de archivo no permitido. Formatos aceptados: {permitidas}', 400)

    stored_name = build_stored_filename(file_storage.filename)
    destination = app.config['UPLOAD_FOLDER']
    if subfolder:
        destination = os.path.join(destination, subfolder)
        os.makedirs(destination, exist_ok=True)

    file_storage.save(os.path.join(destination, stored_name))
    return stored_name, None


def delete_upload(stored_name, subfolder=None):
    """Borra un archivo subido si existe, ignorando errores de disco."""
    if not stored_name:
        return
    base = app.config['UPLOAD_FOLDER']
    if subfolder:
        base = os.path.join(base, subfolder)
    # secure_filename evita que un nombre manipulado en la base de datos
    # escape del directorio de subidas (../../).
    path = os.path.join(base, secure_filename(stored_name))
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as exc:
        app.logger.warning('No se pudo borrar %s: %s', path, exc)


def get_current_user_id():
    """ID numérico del usuario autenticado."""
    return int(get_jwt_identity())


def are_contacts(user_a, user_b):
    """True si ambos usuarios tienen una relación de contacto aceptada."""
    return Contact.query.filter(
        (((Contact.user_id == user_a) & (Contact.contact_id == user_b)) |
         ((Contact.user_id == user_b) & (Contact.contact_id == user_a))) &
        (Contact.status == 'accepted')
    ).first() is not None

# --- 3. Modelos de la Base de Datos ---
class User(db.Model):
    """Modelo para la tabla de Usuarios"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    career = db.Column(db.String(100))
    semester = db.Column(db.Integer)
    profile_picture = db.Column(db.String(300))
    profile_color = db.Column(db.String(7), default='#3B82F6')
    created_at = db.Column(db.DateTime, default=db.func.now())
    resources = db.relationship('Resource', backref='owner', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True)
    owned_groups = db.relationship('Group', backref='owner', lazy=True)
    group_memberships = db.relationship('GroupMember', backref='user', lazy=True)
    sent_messages = db.relationship('DirectMessage', foreign_keys='DirectMessage.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('DirectMessage', foreign_keys='DirectMessage.receiver_id', backref='receiver', lazy=True)
    contacts_initiated = db.relationship('Contact', foreign_keys='Contact.user_id', backref='user', lazy=True)
    contacts_received = db.relationship('Contact', foreign_keys='Contact.contact_id', backref='contact_user', lazy=True)
    private_resources = db.relationship('PrivateResource', backref='owner', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.email}>'

class Resource(db.Model):
    """Modelo para la tabla de Recursos"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    tags = db.Column(db.String(300))
    filename = db.Column(db.String(300), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())

    def __repr__(self):
        return f'<Resource {self.title}>'

# --- NUEVOS MODELOS PARA LAS FUNCIONALIDADES ---
class ChatMessage(db.Model):
    """Modelo para mensajes del chat global"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())

class Contact(db.Model):
    """Modelo para contactos entre usuarios"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=db.func.now())

class Group(db.Model):
    """Modelo para grupos de trabajo"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    
    members = db.relationship('GroupMember', backref='group', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('GroupMessage', backref='group', lazy=True)
    resources = db.relationship('GroupResource', backref='group', lazy=True)
    tasks = db.relationship('GroupTask', backref='group', lazy=True)

class GroupMember(db.Model):
    """Modelo para miembros de grupos"""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=db.func.now())

class GroupMessage(db.Model):
    """Modelo para mensajes de grupos"""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())

class GroupResource(db.Model):
    """Modelo para recursos de grupos"""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    uploaded_at = db.Column(db.DateTime, default=db.func.now())

class GroupTask(db.Model):
    """Modelo para tareas de grupos"""
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    assigned_to = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='pending')  # pending, in_progress, completed
    due_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=db.func.now())

class PrivateResource(db.Model):
    """Modelo para recursos privados (anotaciones)"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    filename = db.Column(db.String(300))
    type = db.Column(db.String(20), default='note')  # 'note' o 'file'
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

class DirectMessage(db.Model):
    """Modelo para mensajes directos entre contactos"""
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    read = db.Column(db.Boolean, default=False)

class Notification(db.Model):
    """Modelo para notificaciones"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'contact_request', 'message', 'group_invite', etc.
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    related_id = db.Column(db.Integer)  # ID del recurso relacionado
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=db.func.now())

class AIConversation(db.Model):
    """Conversación con el asistente de IA. Pertenece a un único usuario."""
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())

    messages = db.relationship('AIMessage', backref='conversation', lazy=True,
                               cascade='all, delete-orphan', order_by='AIMessage.id')

class AIMessage(db.Model):
    """Un turno de la conversación. `sources` guarda en JSON las fuentes citadas."""
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(36), db.ForeignKey('ai_conversation.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' o 'assistant'
    content = db.Column(db.Text, nullable=False)
    sources = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=db.func.now())

# --- 4. Rutas de la API EXISTENTES ---
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'message': 'No se recibieron datos JSON'}), 400

        email = (data.get('email') or '').strip().lower()
        name = (data.get('name') or '').strip()
        password = data.get('password') or ''
        profile_color = data.get('profile_color', '#3B82F6')

        if not email or not name or not password:
            return jsonify({'message': 'Faltan datos (nombre, email o contraseña)'}), 400

        if '@' not in email or '.' not in email.split('@')[-1]:
            return jsonify({'message': 'El correo electrónico no es válido'}), 400

        # Longitud mínima: antes se aceptaba cualquier contraseña, incluso de un carácter.
        if len(password) < 6:
            return jsonify({'message': 'La contraseña debe tener al menos 6 caracteres'}), 400

        existing_user = User.query.filter(db.func.lower(User.email) == email).first()
        if existing_user:
            return jsonify({'message': 'El correo ya existe'}), 409

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        new_user = User(
            name=name, 
            email=email, 
            password=hashed_password,
            profile_color=profile_color 
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({'message': 'Usuario registrado exitosamente'}), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Error al registrar el usuario', 'error': str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'message': 'No se recibieron datos JSON'}), 400

        email = (data.get('email') or '').strip().lower()
        password = data.get('password')

        if not email or not password:
            return jsonify({'message': 'Faltan email o contraseña'}), 400

        # Comparación insensible a mayúsculas: las cuentas ya existentes se
        # guardaron con distinta capitalización y si no, no podrían entrar.
        user = User.query.filter(db.func.lower(User.email) == email).first()

        # Se responde el mismo mensaje tanto si el correo no existe como si la
        # contraseña es incorrecta, para no revelar qué correos están registrados.
        if not user or not bcrypt.check_password_hash(user.password, password):
            return jsonify({'message': 'Credenciales inválidas'}), 401

        access_token = create_access_token(identity=str(user.id))

        return jsonify({
            'message': 'Inicio de sesión exitoso',
            'token': access_token,
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'career': user.career,
                'semester': user.semester,
                'profile_color': user.profile_color
            }
        }), 200

    except Exception as e:
        return error_response('Error interno del servidor', 500, e)

@app.route('/api/resources', methods=['GET'])
@jwt_required()
def get_resources():
    try:
        current_user_id = get_jwt_identity()

        user = User.query.get(int(current_user_id))

        if not user:
            return jsonify({'message': 'Usuario no encontrado'}), 404

        resources = Resource.query.order_by(Resource.created_at.desc()).all()
        
        resources_list = []
        for resource in resources:
            owner_name = 'Usuario Eliminado'
            if resource.owner and resource.owner.name:
                owner_name = resource.owner.name

            resources_list.append({
                'id': resource.id,
                'title': resource.title or 'Sin Título',
                'author': resource.author or 'Sin Autor',
                'category': resource.category or 'Sin Categoría',
                'tags': resource.tags or '',
                'filename': resource.filename or '',
                # Nombre legible: en disco los archivos llevan un prefijo único
                # para que dos usuarios no se pisen el mismo nombre.
                'original_filename': display_filename(resource.filename),
                'owner_id': resource.owner_id,
                'owner_name': owner_name,
                'created_at': resource.created_at.isoformat()
            })

        return jsonify({
            'resources': resources_list,
            'user_id': int(current_user_id),
            'user_name': user.name 
        }), 200
        
    except Exception as e:
        print(f"❌ Error en get_resources: {str(e)}")
        return jsonify({'message': 'Error interno del servidor', 'error': str(e)}), 500

@app.route('/api/resources', methods=['POST'])
@jwt_required()
def create_resource():
    try:
        user_id = get_current_user_id()

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'message': 'Usuario no válido'}), 401

        title = (request.form.get('title') or '').strip()
        author = (request.form.get('author') or '').strip()
        category = request.form.get('category')
        tags = request.form.get('tags')

        if 'file' not in request.files:
            return jsonify({'message': 'No se encontró el archivo'}), 400

        if not title or not author:
            return jsonify({'message': 'Faltan título o autor'}), 400

        stored_name, upload_error = save_upload(request.files['file'])
        if upload_error:
            return upload_error

        new_resource = Resource(
            title=title,
            author=author,
            category=category,
            tags=tags,
            filename=stored_name,
            owner_id=user_id
        )

        db.session.add(new_resource)
        db.session.commit()

        return jsonify({'message': 'Recurso creado exitosamente', 'id': new_resource.id}), 201

    except Exception as e:
        db.session.rollback()
        return error_response('Error al guardar en la base de datos', 500, e)

@app.route('/api/resources/<int:id>', methods=['PUT'])
@jwt_required()
def update_resource(id):
    try:
        user_id = get_current_user_id()
        resource = db.session.get(Resource, id)

        if not resource:
            return jsonify({'message': 'Recurso no encontrado'}), 404

        if resource.owner_id != user_id:
            return jsonify({'message': 'No autorizado para editar este recurso'}), 403

        resource.title = request.form.get('title', resource.title)
        resource.author = request.form.get('author', resource.author)
        resource.category = request.form.get('category', resource.category)
        resource.tags = request.form.get('tags', resource.tags)

        if 'file' in request.files and request.files['file'].filename != '':
            stored_name, upload_error = save_upload(request.files['file'])
            if upload_error:
                return upload_error
            # El archivo anterior se borra sólo después de guardar el nuevo,
            # para no dejar el recurso sin fichero si la subida falla.
            old_filename = resource.filename
            resource.filename = stored_name
            delete_upload(old_filename)

        db.session.commit()
        return jsonify({'message': 'Recurso actualizado exitosamente'}), 200

    except Exception as e:
        db.session.rollback()
        return error_response('Error al actualizar en la base de datos', 500, e)

@app.route('/api/resources/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_resource(id):
    try:
        user_id = get_current_user_id()
        resource = db.session.get(Resource, id)

        if not resource:
            return jsonify({'message': 'Recurso no encontrado'}), 404

        if resource.owner_id != user_id:
            return jsonify({'message': 'No autorizado para eliminar este recurso'}), 403

        filename = resource.filename
        db.session.delete(resource)
        db.session.commit()

        # El fichero se borra tras confirmar el borrado en base de datos: si el
        # commit fallara, el recurso seguiría existiendo pero sin archivo.
        delete_upload(filename)

        return jsonify({'message': 'Recurso eliminado exitosamente'}), 200

    except Exception as e:
        db.session.rollback()
        return error_response('Error al eliminar de la base de datos', 500, e)

@app.route('/api/uploads/<filename>')
def get_file(filename):
    """Sirve únicamente los recursos PÚBLICOS de la biblioteca.

    Antes esta ruta usaba <path:filename>, lo que permitía descargar también
    uploads/private/... y uploads/groups/... sin ningún token: cualquiera con la
    URL accedía a documentos privados de otros usuarios. Ahora no acepta
    subcarpetas y los archivos privados y de grupo tienen rutas autenticadas
    propias (más abajo).
    """
    if '/' in filename or '\\' in filename:
        return jsonify({'message': 'Ruta no válida'}), 400
    try:
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=False)
    except (FileNotFoundError, NotFound):
        return jsonify({'message': 'Archivo no encontrado'}), 404


@app.route('/api/private-resources/<int:id>/download', methods=['GET'])
@jwt_required()
def download_private_resource(id):
    """Descarga de un archivo privado, sólo para su dueño."""
    user_id = get_current_user_id()
    resource = db.session.get(PrivateResource, id)

    if not resource or resource.type != 'file' or not resource.filename:
        return jsonify({'message': 'Archivo no encontrado'}), 404

    if resource.owner_id != user_id:
        return jsonify({'message': 'No autorizado para acceder a este archivo'}), 403

    try:
        return send_from_directory(
            os.path.join(app.config['UPLOAD_FOLDER'], 'private'),
            resource.filename,
            as_attachment=True,
            download_name=display_filename(resource.filename)
        )
    except (FileNotFoundError, NotFound):
        return jsonify({'message': 'Archivo no encontrado'}), 404


@app.route('/api/groups/<int:group_id>/resources/<int:resource_id>/download', methods=['GET'])
@jwt_required()
def download_group_resource(group_id, resource_id):
    """Descarga de un recurso de grupo, sólo para miembros del grupo."""
    user_id = get_current_user_id()

    if not GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first():
        return jsonify({'message': 'No eres miembro de este grupo'}), 403

    resource = db.session.get(GroupResource, resource_id)
    if not resource or resource.group_id != group_id:
        return jsonify({'message': 'Archivo no encontrado'}), 404

    try:
        return send_from_directory(
            os.path.join(app.config['UPLOAD_FOLDER'], 'groups', str(group_id)),
            resource.filename,
            as_attachment=True,
            download_name=display_filename(resource.filename)
        )
    except (FileNotFoundError, NotFound):
        return jsonify({'message': 'Archivo no encontrado'}), 404

@app.route('/api/verify-token', methods=['GET'])
@jwt_required()
def verify_token():
    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))
    
    if not user:
        return jsonify({'valid': False}), 401
        
    return jsonify({
        'valid': True,
        'user': {
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'profile_color': user.profile_color
        }
    }), 200

# --- NUEVAS RUTAS PARA LAS FUNCIONALIDADES ---

# --- Chat Global ---
@app.route('/api/chat/messages', methods=['GET'])
@jwt_required()
def get_chat_messages():
    try:
        # Se piden los 50 MÁS RECIENTES (desc + limit) y luego se invierten para
        # mostrarlos en orden cronológico. Con asc + limit(50) el chat se quedaba
        # anclado a los 50 primeros mensajes de la historia y los nuevos nunca
        # llegaban a verse.
        #
        # El desempate por id es necesario: la marca de tiempo de SQLite tiene
        # precisión de segundo, así que varios mensajes enviados seguidos quedan
        # empatados y sin este criterio salían desordenados entre sí.
        messages = (ChatMessage.query
                    .order_by(ChatMessage.timestamp.desc(), ChatMessage.id.desc())
                    .limit(50).all())
        messages.reverse()

        messages_list = []
        for msg in messages:
            messages_list.append({
                'id': msg.id,
                'user_id': msg.user_id,
                'user_name': msg.user.name if msg.user else 'Usuario eliminado',
                'message': msg.message,
                'timestamp': msg.timestamp.isoformat()
            })

        return jsonify({'messages': messages_list}), 200
    except Exception as e:
        return error_response('Error al obtener mensajes', 500, e)

@app.route('/api/chat/messages', methods=['POST'])
@jwt_required()
def send_chat_message():
    try:
        user_id = get_current_user_id()
        data = request.get_json(silent=True) or {}

        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({'message': 'El mensaje no puede estar vacío'}), 400
        if len(message) > 2000:
            return jsonify({'message': 'El mensaje no puede superar los 2000 caracteres'}), 400

        new_message = ChatMessage(user_id=user_id, message=message)

        db.session.add(new_message)
        db.session.commit()

        return jsonify({'message': 'Mensaje enviado exitosamente'}), 201
    except Exception as e:
        db.session.rollback()
        return error_response('Error al enviar mensaje', 500, e)

# --- Contactos ---
@app.route('/api/contacts', methods=['GET'])
@jwt_required()
def get_contacts():
    try:
        current_user_id = get_jwt_identity()
        
        contacts = Contact.query.filter(
            ((Contact.user_id == int(current_user_id)) | (Contact.contact_id == int(current_user_id))) &
            (Contact.status == 'accepted')
        ).all()
        
        contacts_list = []
        for contact in contacts:
            if contact.user_id == int(current_user_id):
                contact_user = contact.contact_user
            else:
                contact_user = contact.user
            
            contacts_list.append({
                'id': contact.id,
                'user_id': contact_user.id,
                'name': contact_user.name,
                'email': contact_user.email,
                'status': contact.status
            })
        
        return jsonify({'contacts': contacts_list}), 200
    except Exception as e:
        return jsonify({'message': 'Error al obtener contactos', 'error': str(e)}), 500

@app.route('/api/contacts/search', methods=['GET'])
@jwt_required()
def search_users():
    try:
        current_user_id = get_jwt_identity()
        query = request.args.get('q', '')
        
        if not query:
            return jsonify({'users': []}), 200
        
        users = User.query.filter(
            User.id != int(current_user_id),
            (User.name.ilike(f'%{query}%') | User.email.ilike(f'%{query}%'))
        ).limit(10).all()
        
        users_list = []
        for user in users:
            existing_contact = Contact.query.filter(
                ((Contact.user_id == int(current_user_id)) & (Contact.contact_id == user.id)) |
                ((Contact.user_id == user.id) & (Contact.contact_id == int(current_user_id)))
            ).first()
            
            users_list.append({
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'is_contact': existing_contact is not None,
                'contact_status': existing_contact.status if existing_contact else None
            })
        
        return jsonify({'users': users_list}), 200
    except Exception as e:
        return jsonify({'message': 'Error al buscar usuarios', 'error': str(e)}), 500

@app.route('/api/contacts/request', methods=['POST'])
@jwt_required()
def send_contact_request():
    try:
        user_id = get_current_user_id()
        data = request.get_json(silent=True) or {}

        if not data.get('contact_id'):
            return jsonify({'message': 'ID de contacto requerido'}), 400

        try:
            contact_id = int(data.get('contact_id'))
        except (TypeError, ValueError):
            return jsonify({'message': 'ID de contacto no válido'}), 400

        # Antes no se comprobaba nada de esto: se podía enviar una solicitud a
        # uno mismo o a un usuario inexistente, creando filas huérfanas.
        if contact_id == user_id:
            return jsonify({'message': 'No puedes agregarte a ti mismo como contacto'}), 400

        target_user = db.session.get(User, contact_id)
        if not target_user:
            return jsonify({'message': 'Usuario no encontrado'}), 404

        existing_request = Contact.query.filter(
            ((Contact.user_id == user_id) & (Contact.contact_id == contact_id)) |
            ((Contact.user_id == contact_id) & (Contact.contact_id == user_id))
        ).first()

        if existing_request:
            return jsonify({'message': 'Ya existe una solicitud de contacto'}), 409

        sender = db.session.get(User, user_id)

        new_contact = Contact(
            user_id=user_id,
            contact_id=contact_id,
            status='pending'
        )
        db.session.add(new_contact)
        # flush() asigna el id antes de usarlo. Sin esto related_id se guardaba
        # siempre como None y la notificación no sabía a qué solicitud apuntaba.
        db.session.flush()

        notification = Notification(
            user_id=contact_id,
            type='contact_request',
            title='Nueva solicitud de contacto',
            message=f'{sender.name} te ha enviado una solicitud de contacto',
            related_id=new_contact.id
        )
        db.session.add(notification)
        db.session.commit()

        return jsonify({'message': 'Solicitud de contacto enviada'}), 201
    except Exception as e:
        db.session.rollback()
        return error_response('Error al enviar solicitud', 500, e)

@app.route('/api/contacts/requests', methods=['GET'])
@jwt_required()
def get_contact_requests():
    try:
        current_user_id = get_jwt_identity()
        
        requests = Contact.query.filter(
            Contact.contact_id == int(current_user_id),
            Contact.status == 'pending'
        ).all()
        
        requests_list = []
        for req in requests:
            requests_list.append({
                'id': req.id,
                'user_id': req.user_id,
                'user_name': req.user.name,
                'user_email': req.user.email,
                'created_at': req.created_at.isoformat()
            })
        
        return jsonify({'requests': requests_list}), 200
    except Exception as e:
        return jsonify({'message': 'Error al obtener solicitudes', 'error': str(e)}), 500

@app.route('/api/contacts/requests/<int:request_id>/accept', methods=['PUT'])
@jwt_required()
def accept_contact_request(request_id):
    try:
        user_id = get_current_user_id()

        contact_request = db.session.get(Contact, request_id)

        if not contact_request or contact_request.contact_id != user_id:
            return jsonify({'message': 'Solicitud no encontrada'}), 404

        if contact_request.status == 'accepted':
            return jsonify({'message': 'La solicitud ya estaba aceptada'}), 200

        contact_request.status = 'accepted'

        # El remitente no se enteraba de que le habían aceptado: faltaba avisarle.
        accepter = db.session.get(User, user_id)
        db.session.add(Notification(
            user_id=contact_request.user_id,
            type='contact_accepted',
            title='Solicitud aceptada',
            message=f'{accepter.name} aceptó tu solicitud de contacto',
            related_id=contact_request.id
        ))

        db.session.commit()

        return jsonify({'message': 'Solicitud de contacto aceptada'}), 200
    except Exception as e:
        db.session.rollback()
        return error_response('Error al aceptar solicitud', 500, e)

@app.route('/api/contacts/requests/<int:request_id>/reject', methods=['DELETE'])
@jwt_required()
def reject_contact_request(request_id):
    try:
        user_id = get_current_user_id()

        contact_request = db.session.get(Contact, request_id)

        if not contact_request or contact_request.contact_id != user_id:
            return jsonify({'message': 'Solicitud no encontrada'}), 404

        db.session.delete(contact_request)
        db.session.commit()

        return jsonify({'message': 'Solicitud de contacto rechazada'}), 200
    except Exception as e:
        db.session.rollback()
        return error_response('Error al rechazar solicitud', 500, e)

# --- Mensajes Directos ---
@app.route('/api/direct-messages/<int:contact_id>', methods=['GET'])
@jwt_required()
def get_direct_messages(contact_id):
    try:
        user_id = get_current_user_id()

        if not are_contacts(user_id, contact_id):
            return jsonify({'message': 'No tienes una conversación con este usuario'}), 403

        messages = DirectMessage.query.filter(
            ((DirectMessage.sender_id == user_id) & (DirectMessage.receiver_id == contact_id)) |
            ((DirectMessage.sender_id == contact_id) & (DirectMessage.receiver_id == user_id))
        ).order_by(DirectMessage.timestamp.asc(), DirectMessage.id.asc()).all()

        messages_list = []
        unread_ids = []
        for msg in messages:
            messages_list.append({
                'id': msg.id,
                'sender_id': msg.sender_id,
                'sender_name': msg.sender.name if msg.sender else 'Usuario eliminado',
                'receiver_id': msg.receiver_id,
                'receiver_name': msg.receiver.name if msg.receiver else 'Usuario eliminado',
                'message': msg.message,
                'timestamp': msg.timestamp.isoformat(),
                'read': msg.read
            })
            # El campo 'read' existía en el modelo pero nunca se actualizaba.
            if msg.receiver_id == user_id and not msg.read:
                unread_ids.append(msg.id)

        if unread_ids:
            DirectMessage.query.filter(DirectMessage.id.in_(unread_ids)).update(
                {'read': True}, synchronize_session=False)
            db.session.commit()

        return jsonify({'messages': messages_list}), 200
    except Exception as e:
        db.session.rollback()
        return error_response('Error al obtener mensajes', 500, e)

@app.route('/api/direct-messages', methods=['POST'])
@jwt_required()
def send_direct_message():
    try:
        user_id = get_current_user_id()
        data = request.get_json(silent=True) or {}

        if not data.get('receiver_id') or not (data.get('message') or '').strip():
            return jsonify({'message': 'Datos incompletos'}), 400

        try:
            receiver_id = int(data.get('receiver_id'))
        except (TypeError, ValueError):
            return jsonify({'message': 'Destinatario no válido'}), 400

        message = data.get('message').strip()
        if len(message) > 2000:
            return jsonify({'message': 'El mensaje no puede superar los 2000 caracteres'}), 400

        # Comprobación que faltaba por completo: sin ella cualquier usuario podía
        # escribir por privado a cualquier otro sin ser contactos.
        if not are_contacts(user_id, receiver_id):
            return jsonify({'message': 'Sólo puedes enviar mensajes a tus contactos'}), 403

        new_message = DirectMessage(
            sender_id=user_id,
            receiver_id=receiver_id,
            message=message
        )
        db.session.add(new_message)

        sender = db.session.get(User, user_id)
        db.session.add(Notification(
            user_id=receiver_id,
            type='message',
            title='Nuevo mensaje directo',
            message=f'{sender.name} te ha enviado un mensaje',
            related_id=user_id
        ))

        db.session.commit()

        return jsonify({'message': 'Mensaje enviado exitosamente'}), 201
    except Exception as e:
        db.session.rollback()
        return error_response('Error al enviar mensaje', 500, e)

# --- Grupos de Trabajo ---
@app.route('/api/groups', methods=['GET'])
@jwt_required()
def get_groups():
    try:
        current_user_id = get_jwt_identity()
        
        user_groups = GroupMember.query.filter_by(user_id=int(current_user_id)).all()
        
        groups_list = []
        for membership in user_groups:
            group = membership.group
            groups_list.append({
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'owner_id': group.owner_id,
                'owner_name': group.owner.name,
                'member_count': len(group.members),
                'created_at': group.created_at.isoformat()
            })
        
        return jsonify({'groups': groups_list}), 200
    except Exception as e:
        return jsonify({'message': 'Error al obtener grupos', 'error': str(e)}), 500

@app.route('/api/groups', methods=['POST'])
@jwt_required()
def create_group():
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json()
        
        if not data or not data.get('name'):
            return jsonify({'message': 'El nombre del grupo es requerido'}), 400
        
        new_group = Group(
            name=data.get('name'),
            description=data.get('description', ''),
            owner_id=int(current_user_id)
        )
        
        db.session.add(new_group)
        db.session.flush()
        
        group_member = GroupMember(
            group_id=new_group.id,
            user_id=int(current_user_id)
        )
        db.session.add(group_member)
        
        db.session.commit()
        
        return jsonify({'message': 'Grupo creado exitosamente', 'group_id': new_group.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Error al crear grupo', 'error': str(e)}), 500

@app.route('/api/groups/<int:group_id>', methods=['GET'])
@jwt_required()
def get_group_details(group_id):
    try:
        current_user_id = get_jwt_identity()
        
        group = Group.query.get(group_id)
        if not group:
            return jsonify({'message': 'Grupo no encontrado'}), 404
        
        is_member = GroupMember.query.filter_by(group_id=group_id, user_id=int(current_user_id)).first()
        if not is_member:
            return jsonify({'message': 'No eres miembro de este grupo'}), 403
        
        members = GroupMember.query.filter_by(group_id=group_id).all()
        resources = GroupResource.query.filter_by(group_id=group_id).all()
        tasks = GroupTask.query.filter_by(group_id=group_id).all()
        
        members_list = []
        for member in members:
            members_list.append({
                'id': member.user.id,
                'name': member.user.name,
                'email': member.user.email,
                'is_owner': member.user.id == group.owner_id,
                'joined_at': member.joined_at.isoformat()
            })
        
        # GroupResource no declara relación con User, así que resource.user
        # lanzaba AttributeError y la vista de grupo devolvía 500 en cuanto el
        # grupo tenía algún recurso. Se resuelven los nombres en una consulta.
        uploaders = {u.id: u.name for u in User.query.filter(
            User.id.in_({r.user_id for r in resources})).all()} if resources else {}

        resources_list = []
        for resource in resources:
            resources_list.append({
                'id': resource.id,
                'title': resource.title,
                'filename': resource.filename,
                'original_filename': display_filename(resource.filename),
                'download_url': f'/api/groups/{group_id}/resources/{resource.id}/download',
                'description': resource.description,
                'uploaded_by': uploaders.get(resource.user_id, 'Usuario eliminado'),
                'uploaded_at': resource.uploaded_at.isoformat()
            })
        
        tasks_list = []
        for task in tasks:
            assigned_user = db.session.get(User, task.assigned_to) if task.assigned_to else None
            creator = db.session.get(User, task.created_by)
            tasks_list.append({
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'assigned_to': assigned_user.name if assigned_user else None,
                # Si el creador fue eliminado, User.query.get(...).name reventaba
                # con AttributeError y tumbaba toda la vista del grupo.
                'created_by': creator.name if creator else 'Usuario eliminado',
                'created_at': task.created_at.isoformat()
            })
        
        return jsonify({
            'group': {
                'id': group.id,
                'name': group.name,
                'description': group.description,
                'owner_id': group.owner_id,
                'owner_name': group.owner.name,
                'created_at': group.created_at.isoformat()
            },
            'members': members_list,
            'resources': resources_list,
            'tasks': tasks_list
        }), 200
    except Exception as e:
        return jsonify({'message': 'Error al obtener detalles del grupo', 'error': str(e)}), 500

@app.route('/api/groups/<int:group_id>/resources', methods=['POST'])
@jwt_required()
def upload_group_resource(group_id):
    try:
        current_user_id = get_jwt_identity()
        
        is_member = GroupMember.query.filter_by(group_id=group_id, user_id=int(current_user_id)).first()
        if not is_member:
            return jsonify({'message': 'No eres miembro de este grupo'}), 403
        
        title = (request.form.get('title') or '').strip()
        description = request.form.get('description', '')

        if 'file' not in request.files:
            return jsonify({'message': 'No se encontró el archivo'}), 400

        if not title:
            return jsonify({'message': 'El título es requerido'}), 400

        stored_name, upload_error = save_upload(
            request.files['file'], subfolder=os.path.join('groups', str(group_id)))
        if upload_error:
            return upload_error

        new_resource = GroupResource(
            group_id=group_id,
            user_id=int(current_user_id),
            title=title,
            filename=stored_name,
            description=description
        )

        db.session.add(new_resource)
        db.session.commit()

        return jsonify({'message': 'Recurso subido exitosamente', 'id': new_resource.id}), 201

    except Exception as e:
        db.session.rollback()
        return error_response('Error al subir recurso', 500, e)

@app.route('/api/groups/<int:group_id>/tasks', methods=['POST'])
@jwt_required()
def add_group_task(group_id):
    try:
        current_user_id = get_jwt_identity()
        
        group = Group.query.get(group_id)
        if not group:
            return jsonify({'message': 'Grupo no encontrado'}), 404
        
        if group.owner_id != int(current_user_id):
            return jsonify({'message': 'Solo el líder del grupo puede agregar tareas'}), 403
        
        data = request.get_json()
        if not data or not data.get('title'):
            return jsonify({'message': 'El título de la tarea es requerido'}), 400
        
        due_date = None
        if data.get('due_date'):
            due_date = datetime.fromisoformat(data.get('due_date').replace('Z', '+00:00'))
        
        new_task = GroupTask(
            group_id=group_id,
            created_by=int(current_user_id),
            title=data.get('title'),
            description=data.get('description', ''),
            assigned_to=data.get('assigned_to'),
            status='pending',
            due_date=due_date
        )
        
        db.session.add(new_task)
        db.session.commit()
        
        return jsonify({'message': 'Tarea agregada exitosamente'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Error al agregar tarea', 'error': str(e)}), 500

# --- Recursos Privados (Anotaciones) ---
@app.route('/api/private-resources', methods=['GET'])
@jwt_required()
def get_private_resources():
    try:
        current_user_id = get_jwt_identity()
        
        resources = PrivateResource.query.filter_by(owner_id=int(current_user_id)).order_by(PrivateResource.updated_at.desc()).all()
        
        resources_list = []
        for resource in resources:
            resources_list.append({
                'id': resource.id,
                'title': resource.title,
                'content': resource.content,
                'filename': resource.filename,
                'original_filename': display_filename(resource.filename),
                # URL autenticada: los privados ya no se sirven desde /api/uploads/.
                'download_url': f'/api/private-resources/{resource.id}/download' if resource.type == 'file' else None,
                'type': resource.type,
                'created_at': resource.created_at.isoformat(),
                'updated_at': resource.updated_at.isoformat()
            })
        
        return jsonify({'resources': resources_list}), 200
    except Exception as e:
        return jsonify({'message': 'Error al obtener recursos privados', 'error': str(e)}), 500

@app.route('/api/private-resources', methods=['POST'])
@jwt_required()
def create_private_resource():
    try:
        current_user_id = get_jwt_identity()
        
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            title = (request.form.get('title') or file.filename).strip()

            stored_name, upload_error = save_upload(file, subfolder='private')
            if upload_error:
                return upload_error

            new_resource = PrivateResource(
                title=title,
                filename=stored_name,
                type='file',
                owner_id=int(current_user_id)
            )
        else:
            data = request.get_json(silent=True) or {}
            title = (data.get('title') or '').strip()
            if not title:
                return jsonify({'message': 'El título es requerido'}), 400

            new_resource = PrivateResource(
                title=title,
                content=data.get('content', ''),
                type='note',
                owner_id=int(current_user_id)
            )

        db.session.add(new_resource)
        db.session.commit()

        return jsonify({'message': 'Recurso privado creado exitosamente', 'id': new_resource.id}), 201
    except Exception as e:
        db.session.rollback()
        return error_response('Error al crear recurso privado', 500, e)

@app.route('/api/private-resources/<int:id>', methods=['PUT'])
@jwt_required()
def update_private_resource(id):
    try:
        current_user_id = get_jwt_identity()
        resource = PrivateResource.query.get(id)

        if not resource:
            return jsonify({'message': 'Recurso no encontrado'}), 404

        if resource.owner_id != int(current_user_id):
            return jsonify({'message': 'No autorizado para editar este recurso'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'message': 'No JSON data provided'}), 400

        resource.title = data.get('title', resource.title)
        resource.content = data.get('content', resource.content)
        resource.updated_at = db.func.now()
                
        db.session.commit()
        return jsonify({'message': 'Recurso actualizado exitosamente'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'message': 'Error al actualizar recurso', 'error': str(e)}), 500

@app.route('/api/private-resources/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_private_resource(id):
    try:
        current_user_id = get_jwt_identity()
        resource = PrivateResource.query.get(id)

        if not resource:
            return jsonify({'message': 'Recurso no encontrado'}), 404

        if resource.owner_id != int(current_user_id):
            return jsonify({'message': 'No autorizado para eliminar este recurso'}), 403

        filename = resource.filename if resource.type == 'file' else None

        db.session.delete(resource)
        db.session.commit()

        delete_upload(filename, subfolder='private')

        return jsonify({'message': 'Recurso eliminado exitosamente'}), 200

    except Exception as e:
        db.session.rollback()
        return error_response('Error al eliminar recurso', 500, e)

# --- Perfil y Estadísticas ---
@app.route('/api/user/stats', methods=['GET'])
@jwt_required()
def get_user_stats():
    try:
        current_user_id = get_jwt_identity()
        
        resources_count = Resource.query.filter_by(owner_id=int(current_user_id)).count()
        groups_count = GroupMember.query.filter_by(user_id=int(current_user_id)).count()
        contacts_count = Contact.query.filter(
            ((Contact.user_id == int(current_user_id)) | (Contact.contact_id == int(current_user_id))) &
            (Contact.status == 'accepted')
        ).count()
        notes_count = PrivateResource.query.filter_by(owner_id=int(current_user_id), type='note').count()
        files_count = PrivateResource.query.filter_by(owner_id=int(current_user_id), type='file').count()
        
        return jsonify({
            'resources_count': resources_count,
            'groups_count': groups_count,
            'contacts_count': contacts_count,
            'notes_count': notes_count,
            'files_count': files_count,
            # Antes se devolvía 'online_users': 24 fijo, un dato inventado que la
            # interfaz mostraba como real. Sin WebSockets no hay forma de saber
            # quién está conectado, así que se informa el total de usuarios
            # registrados, que sí es un número verdadero.
            'registered_users': User.query.count()
        }), 200
    except Exception as e:
        return error_response('Error al obtener estadísticas', 500, e)

@app.route('/api/profile', methods=['POST'])
@jwt_required()
def update_profile():
    try:
        current_user_id = get_jwt_identity()
        
        user = User.query.get(int(current_user_id))
        if not user:
            return jsonify({'message': 'Usuario no encontrado'}), 404
        
        # Acepta tanto JSON como form-data. Antes, con form-data el semestre se
        # guardaba como cadena ("5") en una columna Integer y el color no se
        # validaba, así que cualquier texto acababa en la base de datos.
        source = request.get_json(silent=True) or {} if request.is_json else request.form

        name = (source.get('name') or user.name or '').strip()
        if not name:
            return jsonify({'message': 'El nombre es obligatorio'}), 400
        if len(name) > 150:
            return jsonify({'message': 'El nombre no puede superar los 150 caracteres'}), 400
        user.name = name

        career = source.get('career', user.career)
        user.career = career.strip() if isinstance(career, str) else career

        semester = source.get('semester', user.semester)
        if semester in ('', None):
            user.semester = None
        else:
            try:
                semester = int(semester)
            except (TypeError, ValueError):
                return jsonify({'message': 'El semestre debe ser un número'}), 400
            if not 1 <= semester <= 12:
                return jsonify({'message': 'El semestre debe estar entre 1 y 12'}), 400
            user.semester = semester

        color = source.get('profile_color', user.profile_color)
        if isinstance(color, str) and re.fullmatch(r'#[0-9A-Fa-f]{6}', color.strip()):
            user.profile_color = color.strip()
        elif color != user.profile_color:
            return jsonify({'message': 'El color debe tener formato hexadecimal (#RRGGBB)'}), 400

        db.session.commit()
        
        return jsonify({
            'message': 'Perfil actualizado exitosamente',
            'user': {
                'id': user.id,
                'name': user.name,
                'email': user.email,
                'career': user.career,
                'semester': user.semester,
                'profile_color': user.profile_color
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error actualizando perfil: {str(e)}")
        return jsonify({'message': 'Error al actualizar perfil', 'error': str(e)}), 500
    
# --- Notificaciones ---
@app.route('/api/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    try:
        current_user_id = get_jwt_identity()
        
        notifications = Notification.query.filter_by(user_id=int(current_user_id)).order_by(Notification.created_at.desc()).limit(10).all()
        
        notifications_list = []
        for notification in notifications:
            notifications_list.append({
                'id': notification.id,
                'type': notification.type,
                'title': notification.title,
                'message': notification.message,
                # Se guardaba en la base pero no se enviaba al cliente, así que
                # la interfaz no podía saber a qué solicitud o grupo se refería.
                'related_id': notification.related_id,
                'read': notification.read,
                'created_at': notification.created_at.isoformat()
            })
        
        return jsonify({'notifications': notifications_list}), 200
    except Exception as e:
        return jsonify({'message': 'Error al obtener notificaciones', 'error': str(e)}), 500

# --- Rutas que el frontend ya consumía pero que no existían en el backend ---
# js/api.js llamaba a todas ellas; sin implementación devolvían 404 y las
# secciones de grupos, notificaciones y perfil de contacto quedaban a medias.

def is_group_member(group_id, user_id):
    """True si el usuario pertenece al grupo."""
    return GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first() is not None


@app.route('/api/groups/<int:group_id>/members', methods=['GET'])
@jwt_required()
def get_group_members(group_id):
    try:
        user_id = get_current_user_id()
        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({'message': 'Grupo no encontrado'}), 404
        if not is_group_member(group_id, user_id):
            return jsonify({'message': 'No eres miembro de este grupo'}), 403

        members = GroupMember.query.filter_by(group_id=group_id).all()
        return jsonify({'members': [{
            'id': m.user.id,
            'name': m.user.name,
            'email': m.user.email,
            'profile_color': m.user.profile_color,
            'is_owner': m.user.id == group.owner_id,
            'joined_at': m.joined_at.isoformat()
        } for m in members if m.user]}), 200
    except Exception as e:
        return error_response('Error al obtener miembros', 500, e)


@app.route('/api/groups/<int:group_id>/messages', methods=['GET'])
@jwt_required()
def get_group_messages(group_id):
    """El modelo GroupMessage existía desde el principio pero no tenía ninguna
    ruta: el chat de grupo era inalcanzable."""
    try:
        user_id = get_current_user_id()
        if not is_group_member(group_id, user_id):
            return jsonify({'message': 'No eres miembro de este grupo'}), 403

        messages = (GroupMessage.query.filter_by(group_id=group_id)
                    .order_by(GroupMessage.timestamp.desc(), GroupMessage.id.desc())
                    .limit(50).all())
        messages.reverse()

        authors = {u.id: u.name for u in User.query.filter(
            User.id.in_({m.user_id for m in messages})).all()} if messages else {}

        return jsonify({'messages': [{
            'id': m.id,
            'user_id': m.user_id,
            'user_name': authors.get(m.user_id, 'Usuario eliminado'),
            'message': m.message,
            'timestamp': m.timestamp.isoformat()
        } for m in messages]}), 200
    except Exception as e:
        return error_response('Error al obtener mensajes del grupo', 500, e)


@app.route('/api/groups/<int:group_id>/messages', methods=['POST'])
@jwt_required()
def send_group_message(group_id):
    try:
        user_id = get_current_user_id()
        if not is_group_member(group_id, user_id):
            return jsonify({'message': 'No eres miembro de este grupo'}), 403

        data = request.get_json(silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({'message': 'El mensaje no puede estar vacío'}), 400
        if len(message) > 2000:
            return jsonify({'message': 'El mensaje no puede superar los 2000 caracteres'}), 400

        db.session.add(GroupMessage(group_id=group_id, user_id=user_id, message=message))
        db.session.commit()
        return jsonify({'message': 'Mensaje enviado exitosamente'}), 201
    except Exception as e:
        db.session.rollback()
        return error_response('Error al enviar mensaje al grupo', 500, e)


@app.route('/api/groups/<int:group_id>/invite', methods=['POST'])
@jwt_required()
def invite_to_group(group_id):
    try:
        user_id = get_current_user_id()
        group = db.session.get(Group, group_id)
        if not group:
            return jsonify({'message': 'Grupo no encontrado'}), 404
        if group.owner_id != user_id:
            return jsonify({'message': 'Sólo el líder del grupo puede invitar miembros'}), 403

        data = request.get_json(silent=True) or {}
        try:
            invited_id = int(data.get('user_id'))
        except (TypeError, ValueError):
            return jsonify({'message': 'Usuario no válido'}), 400

        invited = db.session.get(User, invited_id)
        if not invited:
            return jsonify({'message': 'Usuario no encontrado'}), 404
        if is_group_member(group_id, invited_id):
            return jsonify({'message': 'El usuario ya es miembro del grupo'}), 409

        db.session.add(GroupMember(group_id=group_id, user_id=invited_id))
        db.session.add(Notification(
            user_id=invited_id,
            type='group_invite',
            title='Te agregaron a un grupo',
            message=f'Ahora formas parte del grupo "{group.name}"',
            related_id=group_id
        ))
        db.session.commit()
        return jsonify({'message': 'Miembro agregado exitosamente'}), 201
    except Exception as e:
        db.session.rollback()
        return error_response('Error al invitar al grupo', 500, e)


@app.route('/api/groups/<int:group_id>/tasks', methods=['GET'])
@jwt_required()
def get_group_tasks(group_id):
    try:
        user_id = get_current_user_id()
        if not is_group_member(group_id, user_id):
            return jsonify({'message': 'No eres miembro de este grupo'}), 403

        tasks = GroupTask.query.filter_by(group_id=group_id).order_by(GroupTask.created_at.desc()).all()
        result = []
        for task in tasks:
            assigned = db.session.get(User, task.assigned_to) if task.assigned_to else None
            creator = db.session.get(User, task.created_by)
            result.append({
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'due_date': task.due_date.isoformat() if task.due_date else None,
                'assigned_to': assigned.name if assigned else None,
                'created_by': creator.name if creator else 'Usuario eliminado',
                'created_at': task.created_at.isoformat()
            })
        return jsonify({'tasks': result}), 200
    except Exception as e:
        return error_response('Error al obtener tareas', 500, e)


@app.route('/api/groups/<int:group_id>/resources', methods=['GET'])
@jwt_required()
def get_group_resources(group_id):
    try:
        user_id = get_current_user_id()
        if not is_group_member(group_id, user_id):
            return jsonify({'message': 'No eres miembro de este grupo'}), 403

        resources = GroupResource.query.filter_by(group_id=group_id).order_by(
            GroupResource.uploaded_at.desc()).all()
        uploaders = {u.id: u.name for u in User.query.filter(
            User.id.in_({r.user_id for r in resources})).all()} if resources else {}

        return jsonify({'resources': [{
            'id': r.id,
            'title': r.title,
            'filename': r.filename,
            'original_filename': display_filename(r.filename),
            'download_url': f'/api/groups/{group_id}/resources/{r.id}/download',
            'description': r.description,
            'uploaded_by': uploaders.get(r.user_id, 'Usuario eliminado'),
            'uploaded_at': r.uploaded_at.isoformat()
        } for r in resources]}), 200
    except Exception as e:
        return error_response('Error al obtener recursos del grupo', 500, e)


@app.route('/api/notifications/<int:notification_id>/read', methods=['PUT'])
@jwt_required()
def mark_notification_read(notification_id):
    try:
        user_id = get_current_user_id()
        notification = db.session.get(Notification, notification_id)
        if not notification or notification.user_id != user_id:
            return jsonify({'message': 'Notificación no encontrada'}), 404

        notification.read = True
        db.session.commit()
        return jsonify({'message': 'Notificación marcada como leída'}), 200
    except Exception as e:
        db.session.rollback()
        return error_response('Error al marcar la notificación', 500, e)


@app.route('/api/users/<int:user_id>/profile', methods=['GET'])
@jwt_required()
def get_user_profile(user_id):
    """Perfil público de un contacto. app.js ya lo pedía vía api.getUserProfile(),
    que tampoco existía en el cliente."""
    try:
        viewer_id = get_current_user_id()
        target = db.session.get(User, user_id)
        if not target:
            return jsonify({'message': 'Usuario no encontrado'}), 404

        # Sólo se muestra el perfil completo a uno mismo o a contactos aceptados.
        if viewer_id != user_id and not are_contacts(viewer_id, user_id):
            return jsonify({'message': 'No puedes ver el perfil de este usuario'}), 403

        return jsonify({'user': {
            'id': target.id,
            'name': target.name,
            'email': target.email,
            'career': target.career,
            'semester': target.semester,
            'profile_color': target.profile_color,
            'created_at': target.created_at.isoformat() if target.created_at else None,
            'resources_count': Resource.query.filter_by(owner_id=target.id).count()
        }}), 200
    except Exception as e:
        return error_response('Error al obtener el perfil', 500, e)


@app.route('/api/profile/picture', methods=['POST'])
@jwt_required()
def upload_profile_picture():
    try:
        user_id = get_current_user_id()
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'message': 'Usuario no encontrado'}), 404

        if 'file' not in request.files:
            return jsonify({'message': 'No se encontró el archivo'}), 400

        file = request.files['file']
        extension = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if extension not in {'png', 'jpg', 'jpeg', 'gif', 'webp'}:
            return jsonify({'message': 'La foto debe ser PNG, JPG, GIF o WEBP'}), 400

        stored_name, upload_error = save_upload(file, subfolder='profile')
        if upload_error:
            return upload_error

        old_picture = user.profile_picture
        user.profile_picture = stored_name
        db.session.commit()
        delete_upload(old_picture, subfolder='profile')

        return jsonify({
            'message': 'Foto de perfil actualizada',
            'profile_picture': stored_name
        }), 200
    except Exception as e:
        db.session.rollback()
        return error_response('Error al subir la foto de perfil', 500, e)


@app.route('/api/uploads/profile/<filename>', methods=['GET'])
@jwt_required()
def get_profile_picture(filename):
    """Las fotos de perfil requieren sesión, igual que el resto de subidas."""
    if '/' in filename or '\\' in filename:
        return jsonify({'message': 'Ruta no válida'}), 400
    try:
        return send_from_directory(
            os.path.join(app.config['UPLOAD_FOLDER'], 'profile'), filename)
    except (FileNotFoundError, NotFound):
        return jsonify({'message': 'Archivo no encontrado'}), 404


# --- Asistente de IA (RAG con Ollama) ---
# La lógica de búsqueda y la conexión con el modelo están en ai_service.py.
# Aquí sólo se decide QUÉ documentos puede consultar cada usuario y se guardan
# las conversaciones.

AI_HISTORY_TURNS = 6          # mensajes previos que se envían al modelo
AI_MAX_QUESTION_LENGTH = 2000


def collect_ai_documents(user_id):
    """Documentos que `user_id` tiene permiso de ver, listos para buscar.

    El filtro por permisos se aplica AQUÍ, antes de la búsqueda y antes de
    construir el prompt. Si se filtrara después, el modelo ya habría leído
    la nota privada de otro estudiante y podría citarla en su respuesta.

    - Biblioteca: todos los recursos públicos.
    - Anotaciones: sólo las del propio usuario (notas y archivos).
    - Grupos: sólo los recursos de grupos a los que pertenece.
    """
    upload_dir = app.config['UPLOAD_FOLDER']
    documentos = []

    for r in Resource.query.all():
        metadatos = (f'Título: {r.title}. Autor: {r.author}. '
                     f'Categoría: {r.category or "-"}. Etiquetas: {r.tags or "-"}.')
        contenido = ai_service.extract_text(
            os.path.join(upload_dir, secure_filename(r.filename or '')))
        documentos.append(ai_service.Documento(
            kind='public', id=r.id, title=r.title, origin='Biblioteca',
            text=f'{metadatos}\n{contenido}'))

    for p in PrivateResource.query.filter_by(owner_id=user_id).all():
        if p.type == 'file':
            contenido = ai_service.extract_text(
                os.path.join(upload_dir, 'private', secure_filename(p.filename or '')))
            kind = 'private_file'
        else:
            contenido = p.content or ''
            kind = 'private_note'
        documentos.append(ai_service.Documento(
            kind=kind, id=p.id, title=p.title, origin='Tus anotaciones',
            text=f'Título: {p.title}.\n{contenido}'))

    group_ids = [m.group_id for m in GroupMember.query.filter_by(user_id=user_id).all()]
    if group_ids:
        nombres = {g.id: g.name for g in Group.query.filter(Group.id.in_(group_ids)).all()}
        for g in GroupResource.query.filter(GroupResource.group_id.in_(group_ids)).all():
            contenido = ai_service.extract_text(os.path.join(
                upload_dir, 'groups', str(g.group_id), secure_filename(g.filename or '')))
            documentos.append(ai_service.Documento(
                kind='group', id=g.id, title=g.title,
                origin=f'Grupo {nombres.get(g.group_id, "")}'.strip(),
                text=f'Título: {g.title}. Descripción: {g.description or "-"}.\n{contenido}'))

    return documentos


def count_ai_documents(user_id):
    """Cuántos documentos puede consultar el usuario, sin leer los archivos."""
    group_ids = [m.group_id for m in GroupMember.query.filter_by(user_id=user_id).all()]
    total = Resource.query.count() + PrivateResource.query.filter_by(owner_id=user_id).count()
    if group_ids:
        total += GroupResource.query.filter(GroupResource.group_id.in_(group_ids)).count()
    return total


@app.route('/api/ai/status', methods=['GET'])
@jwt_required()
def ai_status():
    try:
        user_id = get_current_user_id()
        disponible, detalle = ai_service.model_status()
        if not disponible:
            app.logger.warning('Asistente de IA no disponible: %s', detalle)

        payload = {
            'available': disponible,
            'model': ai_service.OLLAMA_MODEL,
            'indexed_documents': count_ai_documents(user_id),
        }
        # El detalle incluye la URL interna de Ollama: sólo se expone en debug.
        if not disponible and DEBUG_MODE:
            payload['detail'] = detalle
        return jsonify(payload), 200
    except Exception as e:
        return error_response('Error al consultar el asistente', 500, e)


@app.route('/api/ai/chat', methods=['POST'])
@jwt_required()
def ai_chat():
    try:
        user_id = get_current_user_id()
        data = request.get_json(silent=True) or {}

        question = (data.get('question') or '').strip()
        if not question:
            return jsonify({'message': 'Escribe una pregunta'}), 400
        if len(question) > AI_MAX_QUESTION_LENGTH:
            return jsonify({'message': f'La pregunta no puede superar los {AI_MAX_QUESTION_LENGTH} caracteres'}), 400

        # Una conversación ajena o inexistente no da error: se empieza una
        # nueva. (Un 404 aquí lo interpretaría el frontend como "asistente no
        # implementado".)
        conversation = None
        conversation_id = data.get('conversation_id')
        if conversation_id:
            conversation = db.session.get(AIConversation, str(conversation_id))
            if conversation and conversation.user_id != user_id:
                conversation = None

        historial = []
        if conversation:
            previos = conversation.messages[-AI_HISTORY_TURNS:]
            historial = [(m.role, m.content) for m in previos]

        fragmentos = ai_service.search(collect_ai_documents(user_id), question)
        try:
            respuesta = ai_service.answer(question, fragmentos, historial)
        except ai_service.OllamaError as exc:
            return error_response('El modelo de IA no está respondiendo en este momento', 503, exc)

        sources = [{
            'resource_id': f.documento.id,
            'type': f.documento.kind,
            'title': f.documento.title,
            'origin': f.documento.origin,
            'snippet': ai_service.snippet(f.texto),
            'score': f.score,
        } for f in fragmentos]

        if not conversation:
            conversation = AIConversation(user_id=user_id)
            db.session.add(conversation)
            db.session.flush()

        db.session.add(AIMessage(conversation_id=conversation.id, role='user', content=question))
        db.session.add(AIMessage(conversation_id=conversation.id, role='assistant',
                                 content=respuesta, sources=json.dumps(sources, ensure_ascii=False)))
        db.session.commit()

        return jsonify({
            'answer': respuesta,
            'conversation_id': conversation.id,
            'sources': sources,
        }), 200
    except Exception as e:
        db.session.rollback()
        return error_response('Error al procesar la pregunta', 500, e)


@app.route('/api/ai/history', methods=['GET'])
@jwt_required()
def ai_history():
    try:
        user_id = get_current_user_id()
        conversation_id = request.args.get('conversation_id', '')
        conversation = db.session.get(AIConversation, conversation_id) if conversation_id else None
        if not conversation or conversation.user_id != user_id:
            return jsonify({'message': 'Conversación no encontrada'}), 404

        return jsonify({'messages': [{
            'role': m.role,
            'content': m.content,
            'sources': json.loads(m.sources) if m.sources else [],
            'created_at': m.created_at.isoformat() if m.created_at else None,
        } for m in conversation.messages]}), 200
    except Exception as e:
        return error_response('Error al obtener el historial', 500, e)


# Ruta de salud
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'OK', 'message': 'UFG Knowledge Hub API is running'}), 200


@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_e):
    """Sin este manejador, superar MAX_CONTENT_LENGTH devolvía HTML y el
    frontend mostraba 'Expected JSON' en lugar de un mensaje entendible."""
    limite = app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)
    return jsonify({'message': f'El archivo supera el límite de {limite} MB'}), 413

# --- FUNCIÓN DE ACTUALIZACIÓN DE BASE DE DATOS ---
def check_and_update_db():
    """Verifica y añade las columnas que falten en la tabla user.

    La versión anterior tenía dos bloques `except` para un solo `try`: el segundo
    era código inalcanzable, y las columnas career/semester/profile_picture/
    created_at sólo se intentaban añadir DENTRO del manejador de errores, es
    decir, únicamente si fallaba la de profile_color. En la práctica nunca se
    creaban. Además `columns` se leía en el except, donde podía no existir.
    """
    expected_columns = [
        ('profile_color', 'VARCHAR(7) DEFAULT "#3B82F6"'),
        ('career', 'VARCHAR(100)'),
        ('semester', 'INTEGER'),
        ('profile_picture', 'VARCHAR(300)'),
        ('created_at', 'DATETIME'),
    ]

    with app.app_context():
        try:
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if 'user' not in inspector.get_table_names():
                return

            existing = {col['name'] for col in inspector.get_columns('user')}

            added = []
            for column_name, column_type in expected_columns:
                if column_name not in existing:
                    # Cada ALTER va en su propia transacción: si una columna
                    # falla, las demás siguen aplicándose.
                    try:
                        db.session.execute(
                            text(f'ALTER TABLE user ADD COLUMN {column_name} {column_type}'))
                        db.session.commit()
                        added.append(column_name)
                    except Exception as exc:
                        db.session.rollback()
                        print(f"No se pudo agregar la columna '{column_name}': {exc}")

            if added:
                print(f"Base de datos actualizada. Columnas agregadas: {', '.join(added)}")

        except Exception as exc:
            db.session.rollback()
            print(f"Error verificando la base de datos: {exc}")


# --- 5. Servir el frontend desde el propio Flask ---
# Antes index.html había que abrirlo aparte (Live Server en el puerto 5500), lo
# que obligaba a mantener la lista de orígenes CORS sincronizada a mano. Ahora
# con `python app.py` se sirven API y frontend en el mismo puerto.
FRONTEND_FILES = {'index.html'}
FRONTEND_DIRS = ('js', 'css', 'img')


@app.route('/')
def serve_index():
    return send_from_directory(app.root_path, 'index.html')


@app.route('/<path:filename>')
def serve_frontend(filename):
    """Sirve js/, css/, img/ e index.html. Cualquier otra ruta da 404 para no
    exponer el resto del proyecto (app.py, instance/, uploads/...)."""
    first_segment = filename.split('/')[0]
    if filename not in FRONTEND_FILES and first_segment not in FRONTEND_DIRS:
        return jsonify({'message': 'Recurso no encontrado'}), 404
    try:
        return send_from_directory(app.root_path, filename)
    except (FileNotFoundError, NotFound):
        return jsonify({'message': 'Recurso no encontrado'}), 404


# --- 6. Punto de entrada (main) ---
if __name__ == '__main__':
    os.makedirs(app.instance_path, exist_ok=True)

    with app.app_context():
        db.create_all()

    # Esta función existía pero nunca se llamaba, así que las columnas que
    # faltaban en bases de datos antiguas jamás se añadían.
    check_and_update_db()

    # En local se escucha sólo en 127.0.0.1. En un servidor se puede cambiar con
    # APP_HOST/APP_PORT, aunque para producción conviene usar wsgi.py con
    # waitress o gunicorn (ver docs/ASISTENTE_IA.md).
    host = os.environ.get('APP_HOST', '').strip() or '127.0.0.1'
    port = int(os.environ.get('APP_PORT') or 5001)

    print("=" * 52)
    print("  UFG Knowledge Hub")
    print(f"  Abre la app en:  http://{host}:{port}")
    print(f"  Modo debug:      {'SÍ' if DEBUG_MODE else 'no'}")
    print(f"  Asistente IA:    {ai_service.OLLAMA_MODEL} en {ai_service.OLLAMA_URL}")
    print("=" * 52)

    # debug estaba fijado a True. El depurador de Werkzeug permite ejecutar
    # código desde el navegador ante cualquier error, así que ahora sólo se
    # activa si se pide con FLASK_DEBUG=1.
    app.run(debug=DEBUG_MODE, port=port, host=host)