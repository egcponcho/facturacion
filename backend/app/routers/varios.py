from datetime import date

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
                almacen: str | None = None, grupo: str | None = None, sku: str | None = None,
                contenedor: str | None = None, documento: str | None = None, etapa: str | None = None,
                riesgo: str | None = None, embarque_id: int | None = None,
                eta_desde: date | None = None, eta_hasta: date | None = None,
                fecha_xf_desde: date | None = None, fecha_xf_hasta: date | None = None,
                fecha_tienda_desde: date | None = None, fecha_tienda_hasta: date | None = None,
                orden: str | None = None, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    filtros = {k: v for k, v in locals().items()
               if k not in ("db", "user", "proveedor_id", "orden", "page", "size")}
    return seg.seguimiento(db, user, proveedor_id, filtros, orden, page, size)


@router.get("/seguimiento/documentos")
def seguimiento_documentos(db: Db, user: User, proveedor_id: int | None = None, q: str | None = None,
                           etapa: str | None = None, estado_factura: str | None = None, estado_pl: str | None = None,
                           sociedad: str | None = None, centro: str | None = None, embarque_id: int | None = None,
                           proveedor: str | None = None, con_pendientes: bool = False, orden: str | None = None,
                           page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    filtros = {k: v for k, v in locals().items()
               if k not in ("db", "user", "proveedor_id", "orden", "page", "size")}
    return seg.seguimiento_documentos(db, user, proveedor_id, filtros, orden, page, size)


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
