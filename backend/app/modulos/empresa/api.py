"""Rutas de la ficha de la empresa.
"""
from fastapi import APIRouter

from app.core.api import Clave, Db, User, ejecutar
from app.modulos.empresa import organizacion

router = APIRouter()


# ---- Empresa (organización) -----------------------------------------------------
@router.get("/organizacion")
def ver_organizacion(db: Db, user: User):
    return organizacion.detalle(db, user)


@router.put("/organizacion")
def guardar_organizacion(datos: dict, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: organizacion.actualizar(db, user, datos))
