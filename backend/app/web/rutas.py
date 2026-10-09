"""Piezas comunes de las rutas: sesión de base de datos, usuario, clave de
idempotencia, descargas (PDF/Excel) y ejecución con confirmación.
"""
from typing import Annotated

from fastapi import Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modelos import Usuario
from app.modulos.comun.historial import idempotente
from app.web.dependencias import usuario_con_preferencias

Db = Annotated[Session, Depends(get_db)]
User = Annotated[Usuario, Depends(usuario_con_preferencias)]
Clave = Annotated[str | None, Header(alias="Idempotency-Key")]

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF = "application/pdf"
Formato = Annotated[str, Query(pattern="^(pdf|xlsx)$")]


def descarga(contenido: bytes, nombre: str, formato: str) -> Response:
    """Archivo para descargar; `nombre` sin extensión."""
    nombre = nombre.replace("/", "-").replace('"', "")
    return Response(contenido, media_type=PDF if formato == "pdf" else XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.{formato}"'})


def plantilla_o_vista(contenido: bytes, nombre: str, vista: bool):
    """Plantilla Excel para descargar o, con ?vista=1, su vista previa en JSON."""
    if vista:
        from app.modulos.documentos.plantillas import vista as vista_plantilla
        return vista_plantilla(contenido)
    return descarga(contenido, nombre, "xlsx")


def ejecutar(db: Session, user: Usuario, clave: str | None, fn):
    """Ejecuta una operación en una sola transacción (todo o nada) y la
    protege contra duplicados con la clave de idempotencia."""
    resultado = idempotente(db, user, clave, fn)
    db.commit()
    return resultado
