from datetime import date

from fastapi import APIRouter, Query, Request

from ..schemas import PlantillaIn, PlantillaPatch
from ..services import dashboard as tablero
from ..services import seguimiento as seg
from ..services import varios as svc
from .base import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/dashboard")
def dashboard(db: Db, user: User, proveedor_id: int | None = None):
    return tablero.dashboard(db, user, proveedor_id)


# Los tres tableros de mercancía comparten los mismos filtros
FILTROS_Q = ("q", "marca", "estilo", "color", "talla", "almacen", "grupo", "sku", "contenedor", "documento",
             "etapa", "riesgo", "embarque_id", "estado", "liberacion_comercial", "liberacion_logistica",
             "sociedad", "centro", "proveedor", "xf_vencida", "eta_desde", "eta_hasta", "fecha_xf_desde",
             "fecha_xf_hasta", "fecha_tienda_desde", "fecha_tienda_hasta")


def _filtros_de(request: Request) -> dict:
    f = {k: v for k, v in request.query_params.items() if k in FILTROS_Q and v != ""}
    for k in list(f):
        if k.endswith("_desde") or k.endswith("_hasta"):
            f[k] = date.fromisoformat(f[k])
        elif k == "embarque_id":
            f[k] = int(f[k])
    return f


@router.get("/seguimiento")
def seguimiento(request: Request, db: Db, user: User, proveedor_id: int | None = None, orden: str | None = None,
                page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    return seg.seguimiento(db, user, proveedor_id, _filtros_de(request), orden, page, size)


@router.get("/seguimiento/contenedores")
def seguimiento_contenedores(request: Request, db: Db, user: User, proveedor_id: int | None = None,
                             orden: str | None = None, page: int = Query(1, ge=1),
                             size: int = Query(25, ge=1, le=200)):
    return seg.contenedores(db, user, proveedor_id, _filtros_de(request), orden, page, size)


@router.get("/seguimiento/contenedores/{embarque_id}/explosion")
def seguimiento_explosion(embarque_id: int, contenedor: str, db: Db, user: User, proveedor_id: int | None = None):
    return seg.explosion_contenedor(db, user, embarque_id, contenedor, proveedor_id)


@router.get("/seguimiento/ordenes")
def seguimiento_ordenes(request: Request, db: Db, user: User, proveedor_id: int | None = None,
                        orden: str | None = None, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    return seg.ordenes(db, user, proveedor_id, _filtros_de(request), orden, page, size)


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
