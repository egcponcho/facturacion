"""Archivos que se suben: un solo límite de tamaño para todo el sistema
(MAX_SUBIDA_MB). El servidor ya rechaza las peticiones más grandes antes de
leerlas; esto cubre las que llegan sin indicar su tamaño."""
from app.core.config import settings
from app.core.errores import ErrorNegocio


def exigir_tamano(contenido: bytes) -> None:
    if len(contenido) > settings.MAX_SUBIDA_MB * 1024 * 1024:
        raise ErrorNegocio(f"The file is too large (maximum {settings.MAX_SUBIDA_MB} MB).", 413, "archivo_grande")
