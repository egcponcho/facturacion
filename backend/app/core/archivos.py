"""Archivos que se suben: tamaño, tipo real y hojas de cálculo seguras.

- Un solo límite de tamaño para todo el sistema (MAX_SUBIDA_MB). El servidor
  rechaza antes de leerlas las peticiones que declaran un tamaño mayor; la
  lectura por partes (`web.rutas.leer_subida`) cubre las que no lo declaran.
- El tipo se decide por el contenido (sus primeros bytes), no por la
  extensión ni por lo que dice el navegador.
- Un Excel es un ZIP: antes de abrirlo se revisa que no se expanda a un tamaño
  desmedido (bomba de descompresión). openpyxl usa defusedxml para leer el XML.
"""
import base64
import binascii
import io
import os
import re
import zipfile

from app.core.config import settings
from app.core.errores import ErrorNegocio

# Tipo → extensiones aceptadas y prueba sobre los primeros bytes
TIPOS = {
    "pdf": ((".pdf",), lambda b: b.startswith(b"%PDF-")),
    "png": ((".png",), lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "jpeg": ((".jpg", ".jpeg"), lambda b: b.startswith(b"\xff\xd8\xff")),
    "webp": ((".webp",), lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
    # Formatos de Office modernos (ZIP) y antiguos (OLE)
    "xlsx": ((".xlsx",), lambda b: b.startswith(b"PK\x03\x04")),
    "docx": ((".docx",), lambda b: b.startswith(b"PK\x03\x04")),
    "xls": ((".xls",), lambda b: b.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")),
    "doc": ((".doc",), lambda b: b.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")),
    "csv": ((".csv",), lambda b: _es_texto(b)),
    "txt": ((".txt",), lambda b: _es_texto(b)),
}
MIME = {"pdf": "application/pdf", "png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}
IMAGENES = {"png", "jpeg", "webp"}
DOCUMENTOS = {"pdf", "png", "jpeg", "webp", "xlsx", "xls", "docx", "doc", "csv", "txt"}
HOJAS = {"xlsx", "csv"}

# Un Excel legítimo de este sistema no pasa de unos cientos de MB descomprimido
MAX_DESCOMPRIMIDO = 300 * 1024 * 1024
MAX_PARTES_ZIP = 2000


def _es_texto(b: bytes) -> bool:
    muestra = b[:4096]
    if b"\x00" in muestra:
        return False
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            muestra.decode(codificacion)
            return True
        except UnicodeDecodeError:
            continue
    return False


def limite_bytes() -> int:
    return settings.MAX_SUBIDA_MB * 1024 * 1024


def muy_grande() -> ErrorNegocio:
    return ErrorNegocio(f"The file is too large (maximum {settings.MAX_SUBIDA_MB} MB).", 413, "archivo_grande")


def exigir_tamano(contenido: bytes) -> None:
    if len(contenido) > limite_bytes():
        raise muy_grande()


def tipo_de(nombre: str, contenido: bytes, permitidos: set[str]) -> str:
    """El tipo del archivo si su extensión y su contenido coinciden con uno de
    los permitidos; si no, un error que dice qué se acepta."""
    ext = os.path.splitext(nombre or "")[1].lower()
    for tipo in sorted(permitidos):
        extensiones, prueba = TIPOS[tipo]
        if ext in extensiones and prueba(contenido):
            return tipo
    aceptados = ", ".join(sorted({e for t in permitidos for e in TIPOS[t][0]}))
    raise ErrorNegocio(f"This kind of file is not accepted (accepted: {aceptados}).", 415, "tipo_archivo")


def tipo_imagen(contenido: bytes) -> str | None:
    """png | jpeg | webp según el contenido (None si no es una de ellas)."""
    return next((t for t in ("png", "jpeg", "webp") if TIPOS[t][1](contenido)), None)


def imagen_data_url(valor: str, max_bytes: int) -> str:
    """Una imagen en `data:` (logo, foto de perfil) que de verdad es PNG, JPEG o WebP."""
    m = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", valor or "")
    if not m:
        raise ErrorNegocio("Use a PNG, JPEG or WebP image.", 422, "validacion")
    try:
        datos = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise ErrorNegocio("Use a PNG, JPEG or WebP image.", 422, "validacion") from None
    if len(datos) > max_bytes:
        raise ErrorNegocio(f"The image is too large (maximum {max_bytes // 1024} KB).", 422, "validacion")
    if tipo_imagen(datos) != m.group(1):
        raise ErrorNegocio("Use a PNG, JPEG or WebP image.", 422, "validacion")
    return valor


def exigir_zip_seguro(contenido: bytes) -> None:
    """Un ZIP (xlsx) que no se expande a un tamaño desmedido."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            partes = z.infolist()
    except zipfile.BadZipFile:
        raise ErrorNegocio("The Excel file is damaged or is not an .xlsx file.", 422, "archivo_invalido") from None
    if len(partes) > MAX_PARTES_ZIP or sum(p.file_size for p in partes) > MAX_DESCOMPRIMIDO:
        raise ErrorNegocio("The Excel file is too large once uncompressed.", 413, "archivo_grande")


def abrir_libro(contenido: bytes, **opciones):
    """Abre un Excel subido después de revisar que sea seguro."""
    from openpyxl import load_workbook

    exigir_tamano(contenido)
    exigir_zip_seguro(contenido)
    return load_workbook(io.BytesIO(contenido), **opciones)


def celda_texto(celda):
    """Un dato que empieza con «=» queda como texto en el Excel que se
    descarga: nunca se ejecuta como fórmula al abrirlo (inyección de fórmulas)."""
    if celda.data_type == "f":
        celda.data_type = "s"
    return celda
