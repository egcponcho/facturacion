from fastapi import APIRouter

from ..schemas import PlantillaIn, PlantillaPatch
from ..services import dashboard as tablero
from ..services import varios as svc
from .base import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/dashboard")
def dashboard(db: Db, user: User, proveedor_id: int | None = None):
    return tablero.dashboard(db, user, proveedor_id)


@router.get("/alertas")
def alertas(db: Db, user: User, proveedor_id: int | None = None):
    return svc.listar_alertas(db, user, proveedor_id)


@router.post("/alertas/{alerta_id}/resolver")
def resolver(alerta_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.resolver_alerta(db, user, alerta_id))


@router.get("/plantillas")
def plantillas(db: Db, user: User, proveedor_id: int | None = None, incluir_inactivas: bool = False):
    return svc.listar_plantillas(db, user, proveedor_id, incluir_inactivas)


@router.post("/plantillas")
def crear_plantilla(datos: PlantillaIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.crear_plantilla(db, user, datos))


@router.patch("/plantillas/{plantilla_id}")
def actualizar_plantilla(plantilla_id: int, datos: PlantillaPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.actualizar_plantilla(db, user, plantilla_id, datos))
