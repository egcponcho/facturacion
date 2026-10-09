"""Rutas de los tipos de empaque y las plantillas de caja.
"""
from fastapi import APIRouter

from app.esquemas import PlantillaIn, PlantillaPatch
from app.modulos.empaque import plantillas_caja
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/tipos-empaque")
def tipos_empaque(db: Db, user: User):
    """Tipos de empaque activos (para plantillas y el armado del PL)."""
    from app.modulos.empaque import empaques

    return [empaques.tipo_dict(t) for t in empaques.tipos_activos(db)]


@router.get("/plantillas")
def plantillas(db: Db, user: User, proveedor_id: int | None = None, incluir_inactivas: bool = False):
    return plantillas_caja.listar_plantillas(db, user, proveedor_id, incluir_inactivas)


@router.post("/plantillas")
def crear_plantilla(datos: PlantillaIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: plantillas_caja.crear_plantilla(db, user, datos))


@router.patch("/plantillas/{plantilla_id}")
def actualizar_plantilla(plantilla_id: int, datos: PlantillaPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: plantillas_caja.actualizar_plantilla(db, user, plantilla_id, datos))
