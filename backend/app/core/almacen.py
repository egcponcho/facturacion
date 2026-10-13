"""Almacén de archivos: el contenido vive fuera de la base.

La base guarda solo la clave (ruta relativa dentro de UPLOAD_DIR), el tamaño y
la huella SHA-256; el archivo, en el disco (o en un volumen montado). Así la
base no crece con PDFs, fotos ni hojas de cálculo y sus respaldos son
livianos. Las rutas absolutas que guardaban las versiones anteriores siguen
sirviendo tal cual.
"""
import hashlib
import json
import os
import uuid

from app.core.config import settings


def ruta(clave: str) -> str:
    """Ruta en el disco de una clave (las antiguas ya eran absolutas)."""
    return clave if os.path.isabs(clave) else os.path.join(settings.UPLOAD_DIR, clave)


def guardar(contenido: bytes, carpeta: str, extension: str = "") -> str:
    """Escribe el contenido con un nombre imposible de adivinar y devuelve su clave."""
    destino = os.path.join(settings.UPLOAD_DIR, carpeta)
    os.makedirs(destino, exist_ok=True)
    clave = os.path.join(carpeta, uuid.uuid4().hex + extension)
    with open(ruta(clave), "wb") as fh:
        fh.write(contenido)
    return clave


def leer(clave: str) -> bytes:
    with open(ruta(clave), "rb") as fh:
        return fh.read()


def borrar(clave: str | None) -> None:
    if not clave:
        return
    try:
        os.remove(ruta(clave))
    except OSError:
        pass


def huella(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def guardar_json(datos, carpeta: str) -> str:
    return guardar(json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8"), carpeta, ".json")


def leer_json(clave: str | None, defecto=None):
    if not clave:
        return defecto
    try:
        return json.loads(leer(clave).decode("utf-8"))
    except (OSError, ValueError):
        return defecto
