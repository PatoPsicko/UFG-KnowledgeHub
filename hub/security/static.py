"""Análisis estático de archivos: la primera barrera del vigilante.

Se ejecuta en el momento de la subida (milisegundos) y decide si el archivo
se rechaza de inmediato. No ejecuta ni abre el archivo con programas externos:
sólo lee bytes y, en los formatos ZIP (docx, pptx, xlsx, odt, zip), la lista
de entradas.

Cada hallazgo tiene una severidad:
    block   el archivo se rechaza (ejecutable disfrazado, macros, JavaScript en PDF...)
    review  se publica sólo después de que un administrador lo revise
    info    dato informativo para el informe
"""

from __future__ import annotations

import hashlib
import os
import re
import zipfile
from dataclasses import dataclass, field

from ..storage import extension

# Firmas (magic bytes) esperadas para cada extensión.
_OLE = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
_ZIP = (b'PK\x03\x04', b'PK\x05\x06')
MAGIC = {
    'pdf': (b'%PDF-',),
    'png': (b'\x89PNG\r\n\x1a\n',),
    'jpg': (b'\xff\xd8\xff',),
    'jpeg': (b'\xff\xd8\xff',),
    'gif': (b'GIF87a', b'GIF89a'),
    'webp': (b'RIFF',),
    'zip': _ZIP,
    'docx': _ZIP, 'xlsx': _ZIP, 'pptx': _ZIP, 'odt': _ZIP, 'odp': _ZIP, 'ods': _ZIP,
    'doc': (_OLE,), 'xls': (_OLE,), 'ppt': (_OLE,),
    'rar': (b'Rar!\x1a\x07',),
    '7z': (b"7z\xbc\xaf'\x1c",),
    'rtf': (b'{\\rtf',),
}
TEXT_EXTENSIONS = {'txt', 'md', 'csv'}

# Firmas de ejecutables y scripts que nunca deberían estar en un documento.
EXECUTABLE_SIGNATURES = {
    b'MZ': 'ejecutable de Windows (.exe/.dll)',
    b'\x7fELF': 'ejecutable de Linux',
    b'\xca\xfe\xba\xbe': 'ejecutable de macOS o clase Java',
    b'\xcf\xfa\xed\xfe': 'ejecutable de macOS',
    b'#!': 'script ejecutable',
    b'L\x00\x00\x00\x01\x14\x02\x00': 'acceso directo de Windows (.lnk)',
}

DANGEROUS_EXTENSIONS = {
    'exe', 'dll', 'scr', 'com', 'bat', 'cmd', 'ps1', 'psm1', 'vbs', 'vbe', 'js', 'jse', 'wsf', 'wsh',
    'hta', 'msi', 'msp', 'jar', 'lnk', 'reg', 'sh', 'apk', 'app', 'iso', 'img', 'cpl', 'pif', 'gadget',
    'docm', 'xlsm', 'pptm', 'dotm', 'xlam', 'html', 'htm', 'svg', 'xhtml', 'php', 'py', 'chm',
}

# Huella del archivo de prueba antivirus EICAR (68 bytes). Se compara por hash
# para no guardar la cadena en el código: el propio antivirus marcaría este archivo.
EICAR_SHA256 = '275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f'

MAX_UNCOMPRESSED = 300 * 1024 * 1024     # 300 MB descomprimidos como máximo
MAX_RATIO = 120                          # proporción de compresión sospechosa (zip bomb)
MAX_ZIP_ENTRIES = 5000


@dataclass
class Finding:
    severity: str  # block | review | info
    code: str
    message: str

    def to_dict(self) -> dict:
        return {'severity': self.severity, 'code': self.code, 'message': self.message}


@dataclass
class StaticReport:
    sha256: str
    size: int
    detected_type: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        severidades = {f.severity for f in self.findings}
        if 'block' in severidades:
            return 'block'
        if 'review' in severidades:
            return 'review'
        return 'ok'

    def add(self, severity: str, code: str, message: str) -> None:
        self.findings.append(Finding(severity, code, message))

    def to_dict(self) -> dict:
        return {
            'verdict': self.verdict, 'sha256': self.sha256, 'size': self.size,
            'detected_type': self.detected_type, 'findings': [f.to_dict() for f in self.findings],
        }

    def reasons(self, severity: str = 'block') -> list[str]:
        return [f.message for f in self.findings if f.severity == severity]


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for bloque in iter(lambda: fh.read(1 << 16), b''):
            h.update(bloque)
    return h.hexdigest()


def _detect_type(head: bytes) -> str:
    if head.startswith(b'%PDF-'):
        return 'pdf'
    if head.startswith(_OLE):
        return 'ole'
    if head.startswith(_ZIP):
        return 'zip'
    for ext in ('png', 'jpg', 'gif', 'rar', '7z', 'rtf'):
        if any(head.startswith(m) for m in MAGIC[ext]):
            return ext
    if head.startswith(b'RIFF') and head[8:12] == b'WEBP':
        return 'webp'
    # Un ejecutable real trae bytes nulos; un texto que empieza por "MZ" no.
    # (Los .txt UTF-16 de Windows sí traen nulos, pero empiezan con su BOM.)
    if head.startswith((b'\xff\xfe', b'\xfe\xff')):
        return 'texto'
    if b'\x00' not in head[:4096]:
        return 'script' if head.startswith(b'#!') else 'texto'
    for firma in EXECUTABLE_SIGNATURES:
        if head.startswith(firma):
            return 'ejecutable'
    return 'binario'


def analyze(path: str, original_name: str) -> StaticReport:
    """Analiza el archivo guardado en `path` (con el nombre que puso el usuario)."""
    size = os.path.getsize(path)
    with open(path, 'rb') as fh:
        head = fh.read(8192)
    report = StaticReport(sha256=sha256_of(path), size=size, detected_type=_detect_type(head))
    ext = extension(original_name)

    if size == 0:
        report.add('block', 'empty', 'El archivo está vacío.')
        return report

    if report.sha256 == EICAR_SHA256 or (size < 200 and hashlib.sha256(head[:68]).hexdigest() == EICAR_SHA256):
        report.add('block', 'eicar', 'Archivo de prueba antivirus (EICAR) detectado.')
        return report

    # Doble extensión engañosa: "tarea.pdf.exe" ya lo frena la lista blanca,
    # pero "virus.exe.pdf" pasa la lista y conviene señalarlo.
    partes = original_name.lower().split('.')
    if len(partes) > 2 and any(p in DANGEROUS_EXTENSIONS for p in partes[1:-1]):
        report.add('review', 'double_extension', f'El nombre tiene una doble extensión sospechosa ({original_name}).')

    # En un .txt un texto que empieza por "MZ" o "#!" es sólo texto: se exige
    # que haya bytes binarios para considerarlo un ejecutable.
    es_texto = ext in TEXT_EXTENSIONS and b'\x00' not in head
    for firma, nombre in EXECUTABLE_SIGNATURES.items():
        if head.startswith(firma) and not es_texto:
            report.add('block', 'executable', f'El contenido real es un {nombre}, no un documento.')
            return report

    esperado = MAGIC.get(ext)
    if esperado and not any(head.startswith(m) for m in esperado):
        report.add('block', 'type_mismatch',
                   f'El contenido no corresponde a un archivo .{ext} (parece {report.detected_type}).')
        return report
    if ext == 'webp' and head[8:12] != b'WEBP':
        report.add('block', 'type_mismatch', 'El contenido no corresponde a una imagen WEBP.')
        return report
    if ext in TEXT_EXTENSIONS and report.detected_type not in ('texto', 'script'):
        report.add('block', 'type_mismatch', f'El archivo .{ext} contiene datos binarios, no texto.')
        return report

    if ext == 'pdf':
        _check_pdf(path, report)
    elif esperado == _ZIP:
        _check_zip(path, report, ext)
    elif ext in ('doc', 'xls', 'ppt'):
        _check_ole(path, report)
    elif ext == 'rtf':
        _check_rtf(path, report)
    elif ext in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
        _check_image(path, report)
    elif ext in ('rar', '7z'):
        report.add('info', 'opaque_archive',
                   f'Los .{ext} no se pueden inspeccionar por dentro; se confía en el antivirus.')
    return report


def _read_all(path: str, limite: int = 40 * 1024 * 1024) -> bytes:
    with open(path, 'rb') as fh:
        return fh.read(limite)


def _check_pdf(path: str, report: StaticReport) -> None:
    datos = _read_all(path)
    # Los nombres PDF pueden ir con escapes hexadecimales (/J#61vaScript).
    normal = re.sub(rb'#([0-9a-fA-F]{2})', lambda m: bytes([int(m.group(1), 16)]), datos)
    if re.search(rb'/(JavaScript|JS)\b', normal):
        report.add('block', 'pdf_javascript', 'El PDF contiene código JavaScript.')
    if re.search(rb'/Launch\b', normal):
        report.add('block', 'pdf_launch', 'El PDF intenta abrir programas externos (/Launch).')
    if re.search(rb'/EmbeddedFile\b', normal):
        report.add('review', 'pdf_embedded', 'El PDF trae archivos incrustados.')
    if re.search(rb'/(RichMedia|XFA)\b', normal):
        report.add('review', 'pdf_active', 'El PDF tiene contenido activo (Flash o formularios XFA).')
    if re.search(rb'/(AA|OpenAction)\b', normal) and re.search(rb'/URI\s*\(', normal):
        report.add('review', 'pdf_autoaction', 'El PDF abre un enlace automáticamente al abrirse.')
    if b'%%EOF' not in datos[-2048:] and b'%%EOF' not in datos:
        report.add('info', 'pdf_truncated', 'El PDF no termina como un PDF normal (puede estar dañado).')


def _check_zip(path: str, report: StaticReport, ext: str) -> None:
    try:
        with zipfile.ZipFile(path) as z:
            entradas = z.infolist()
    except zipfile.BadZipFile:
        report.add('block', 'bad_zip', 'El archivo comprimido está dañado o no es lo que dice ser.')
        return

    if len(entradas) > MAX_ZIP_ENTRIES:
        report.add('block', 'zip_entries', f'Contiene demasiados archivos ({len(entradas)}).')
        return
    total = sum(e.file_size for e in entradas)
    comprimido = sum(e.compress_size for e in entradas) or 1
    if total > MAX_UNCOMPRESSED or (total / comprimido > MAX_RATIO and total > 20 * 1024 * 1024):
        report.add('block', 'zip_bomb', 'El archivo se descomprime a un tamaño desproporcionado (posible zip bomb).')
        return

    nombres = [e.filename for e in entradas]
    office = ext in ('docx', 'xlsx', 'pptx')
    if office and not any(n == '[Content_Types].xml' for n in nombres):
        report.add('block', 'type_mismatch', f'No es un documento .{ext} válido.')
        return
    if ext in ('odt', 'odp', 'ods') and 'mimetype' not in nombres:
        report.add('block', 'type_mismatch', f'No es un documento .{ext} válido.')
        return

    for e in entradas:
        nombre = e.filename.lower()
        base = nombre.rsplit('/', 1)[-1]
        if '..' in nombre.split('/') or nombre.startswith('/'):
            report.add('block', 'zip_traversal', 'Contiene rutas que intentan salir de la carpeta (../).')
            return
        if e.flag_bits & 0x1:
            report.add('review', 'zip_encrypted', 'Contiene archivos protegidos con contraseña que no se pueden revisar.')
        if 'vbaproject.bin' in base or (nombre.endswith('.bin') and 'vba' in nombre):
            report.add('block', 'macros', 'El documento contiene macros (código VBA).')
        if office and ('activex' in nombre):
            report.add('review', 'activex', 'El documento contiene controles ActiveX.')
        if office and '/embeddings/' in nombre and base.startswith('oleobject'):
            report.add('review', 'ole_object', 'El documento trae objetos incrustados (OLE).')
        sub_ext = base.rsplit('.', 1)[-1] if '.' in base else ''
        if ext == 'zip' and sub_ext in DANGEROUS_EXTENSIONS:
            report.add('block', 'zip_executable', f'El comprimido contiene un archivo peligroso: {e.filename}')
            return

    if office:
        _check_office_relationships(path, report)
    if ext == 'zip':
        report.add('info', 'zip_listing', f'{len(entradas)} archivos dentro del comprimido.')


def _check_office_relationships(path: str, report: StaticReport) -> None:
    """Plantillas y objetos remotos (técnica de ataques tipo Follina)."""
    with zipfile.ZipFile(path) as z:
        for nombre in z.namelist():
            if not nombre.endswith('.rels'):
                continue
            try:
                xml = z.read(nombre)[:2_000_000]
            except Exception:
                continue
            for m in re.finditer(rb'<Relationship [^>]*>', xml):
                rel = m.group(0)
                if b'TargetMode="External"' not in rel:
                    continue
                destino = re.search(rb'Target="([^"]+)"', rel)
                destino_txt = destino.group(1).decode('utf-8', 'replace') if destino else ''
                tipo = re.search(rb'Type="[^"]*/([^"/]+)"', rel)
                tipo_txt = tipo.group(1).decode() if tipo else ''
                if tipo_txt in ('attachedTemplate', 'oleObject', 'frame', 'subDocument') or \
                        destino_txt.lower().startswith(('mhtml:', 'ms-msdt:', 'file:', '\\\\')):
                    report.add('block', 'remote_template',
                               f'El documento carga contenido remoto al abrirse ({tipo_txt or destino_txt[:60]}).')
                    return


def _check_ole(path: str, report: StaticReport) -> None:
    datos = _read_all(path)
    if b'_VBA_PROJECT' in datos or (b'V\x00B\x00A\x00' in datos and b'Macros' in datos):
        report.add('block', 'macros', 'El documento contiene macros (código VBA).')
    if b'Equation.3' in datos or (b'Package' in datos and b'Ole10Native' in datos):
        report.add('review', 'ole_object', 'El documento trae objetos incrustados (OLE).')


def _check_rtf(path: str, report: StaticReport) -> None:
    datos = _read_all(path, 10 * 1024 * 1024).lower()
    if b'\\objupdate' in datos or b'\\objautlink' in datos:
        report.add('block', 'rtf_autoobject', 'El RTF ejecuta objetos incrustados automáticamente.')
    elif b'\\object' in datos or b'\\objdata' in datos:
        report.add('review', 'rtf_object', 'El RTF trae objetos incrustados.')


def _check_image(path: str, report: StaticReport) -> None:
    """Imágenes políglota: válidas como imagen pero con código adentro."""
    datos = _read_all(path, 20 * 1024 * 1024)
    cola = datos[-65536:]
    for patron, desc in ((rb'<script', 'código JavaScript'), (rb'<\?php', 'código PHP'),
                         (rb'<html', 'una página HTML')):
        if re.search(patron, datos[:65536], re.IGNORECASE) or re.search(patron, cola, re.IGNORECASE):
            report.add('block', 'polyglot', f'La imagen esconde {desc}.')
            return
    if b'PK\x03\x04' in cola:
        report.add('review', 'appended_zip', 'La imagen tiene un archivo comprimido pegado al final.')
