"""Adjuntos: guardar un archivo subido en el almacén y registrar sus datos.

Cada uso (archivo de una factura, foto o documento de un producto) crea su
fila con la llave al adjunto; al quitarlo se borran la fila y el archivo.
"""
import os

from sqlalchemy.orm import Session

from app.core import almacen
from app.modelos import Adjunto, Usuario


def nombre_seguro(nombre: str | None, defecto: str) -> str:
    return "".join(c for c in os.path.basename(nombre or defecto) if c.isalnum() or c in "._- ")[:200] or defecto


def crear(db: Session, user: Usuario, nombre: str, contenido: bytes, carpeta: str, extension: str, tipo_mime: str) -> Adjunto:
    a = Adjunto(nombre=nombre, clave=almacen.guardar(contenido, carpeta, extension), tipo_mime=tipo_mime,
                tamano=len(contenido), sha256=almacen.huella(contenido), subido_por=user.id)
    db.add(a)
    db.flush()
    return a


def quitar(db: Session, uso) -> None:
    """Borra el uso, su adjunto y el archivo del almacén."""
    a = uso.adjunto
    db.delete(uso)
    db.flush()
    db.delete(a)
    db.flush()
    almacen.borrar(a.clave)
