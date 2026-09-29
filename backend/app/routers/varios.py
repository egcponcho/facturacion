from fastapi import APIRouter, Query

from ..schemas import PlantillaIn, PlantillaPatch
from ..services import dashboard as tablero
from ..services import seguimiento as seg
from ..services import varios as svc
from .base import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/dashboard")
def dashboard(db: Db, user: User, proveedor_id: int | None = None):
    return tablero.dashboard(db, user, proveedor_id)


@router.get("/seguimiento")
def seguimiento(db: Db, user: User, proveedor_id: int | None = None, q: str | None = None, marca: str | None = None,
                estilo: str | None = None, color: str | None = None, talla: str | None = None,
                etapa: str | None = None, riesgo: str | None = None, embarque_id: int | None = None,
                orden: str | None = None, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    return seg.seguimiento(db, user, proveedor_id, q, marca, estilo, color, talla, etapa, riesgo, embarque_id,
                           orden, page, size)


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
