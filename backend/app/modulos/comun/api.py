"""Rutas de la edición exclusiva de documentos.
"""
from fastapi import APIRouter

from app.modulos.comun import edicion
from app.web.rutas import Db, User

router = APIRouter()


# Edición exclusiva: una persona edita el documento y las demás lo leen
@router.get("/edicion/{entidad}/{entidad_id}")
def estado_edicion(entidad: str, entidad_id: int, db: Db, user: User):
    return edicion.estado(db, user, entidad, entidad_id)


@router.post("/edicion/{entidad}/{entidad_id}")
def tomar_edicion(entidad: str, entidad_id: int, db: Db, user: User):
    r = edicion.tomar(db, user, entidad, entidad_id)
    db.commit()
    return r


@router.delete("/edicion/{entidad}/{entidad_id}")
def liberar_edicion(entidad: str, entidad_id: int, db: Db, user: User, forzar: bool = False):
    r = edicion.liberar(db, user, entidad, entidad_id, forzar)
    db.commit()
    return r
