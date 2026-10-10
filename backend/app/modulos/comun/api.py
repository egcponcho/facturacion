"""Rutas comunes: edición exclusiva de documentos y bitácora general.
"""
from datetime import date

from fastapi import APIRouter, Query

from app.modulos.comun import auditoria as bitacora
from app.modulos.comun import edicion
from app.web.rutas import Db, User

router = APIRouter()


# Edición exclusiva: una persona edita el documento y las demás lo leen
@router.get("/edicion/{entidad}/{entidad_id}")
def estado_edicion(entidad: str, entidad_id: int, db: Db, user: User):
    """Quién edita el documento en este momento, si alguien lo hace, y si es el propio usuario."""
    return edicion.estado(db, user, entidad, entidad_id)


@router.post("/edicion/{entidad}/{entidad_id}")
def tomar_edicion(entidad: str, entidad_id: int, db: Db, user: User):
    """Toma o renueva la edición exclusiva del documento (vence a los 2 min); 423 si otro lo edita."""
    r = edicion.tomar(db, user, entidad, entidad_id)
    db.commit()
    return r


@router.delete("/edicion/{entidad}/{entidad_id}")
def liberar_edicion(entidad: str, entidad_id: int, db: Db, user: User, forzar: bool = False):
    """Suelta la edición del documento; con forzar, un administrador libera la de otra persona."""
    r = edicion.liberar(db, user, entidad, entidad_id, forzar)
    db.commit()
    return r


# Bitácora general (administración)
@router.get("/auditoria")
def auditoria(
    db: Db,
    user: User,
    entidad: str | None = None,
    entidad_id: int | None = None,
    usuario_id: int | None = None,
    accion: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    """Bitácora general (quién hizo qué y cuándo) con filtros y paginación. Requiere administración."""
    return bitacora.consultar(db, user, entidad, entidad_id, usuario_id, accion, desde, hasta, page, size)


@router.get("/auditoria/opciones")
def auditoria_opciones(db: Db, user: User):
    """Entidades y usuarios que aparecen en la bitácora, para sus filtros. Requiere administración."""
    return bitacora.opciones(db, user)
