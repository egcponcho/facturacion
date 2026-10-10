"""Rutas de la ficha de la empresa.
"""
from fastapi import APIRouter

from app.modulos.empresa import organizacion
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


# ---- Empresa (organización) -----------------------------------------------------
@router.get("/publico/empresa")
def empresa_publica(db: Db):
    """Nombre, logo y marca para la pantalla de ingreso (sin sesión)."""
    return organizacion.publico(db)


@router.get("/organizacion")
def ver_organizacion(db: Db, user: User):
    """Ficha de la empresa: datos, marca, preferencias, módulos y reglas. Requiere administración."""
    return organizacion.detalle(db, user)


@router.put("/organizacion")
def guardar_organizacion(datos: dict, db: Db, user: User, clave: Clave = None):
    """Guarda datos, marca, preferencias, módulos y reglas de la empresa. Requiere administración."""
    return ejecutar(db, user, clave, lambda: organizacion.actualizar(db, user, datos))
