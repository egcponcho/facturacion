"""Rutas de las solicitudes de compra (compras/solicitudes.py)."""
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.modulos.compras import solicitudes as svc
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


class LineaSolicitud(BaseModel):
    codigo_articulo: str | None = Field(default=None, max_length=40)
    descripcion: str | None = Field(default=None, max_length=300)
    cantidad: float | None = None
    unidad: str | None = Field(default=None, max_length=5)
    precio_estimado: float | None = Field(default=None, ge=0)


class SolicitudIn(BaseModel):
    area: str = Field(default="", max_length=80)
    centro: str | None = Field(default=None, max_length=10)
    prioridad: str = "NORMAL"
    fecha_requerida: date | None = None
    proveedor_id: int | None = None
    moneda: str | None = Field(default=None, max_length=3)
    motivo: str | None = Field(default=None, max_length=500)
    lineas: list[LineaSolicitud] = Field(default_factory=list, max_length=200)


class Revision(BaseModel):
    comentario: str | None = Field(default=None, max_length=500)


class Convertir(BaseModel):
    solicitud_ids: list[int] = Field(min_length=1, max_length=100)
    proveedor_id: int
    oc: str = Field(min_length=1, max_length=40)


@router.get("/solicitudes")
def lista(db: Db, user: User, vista: str = "por_aprobar"):
    """Solicitudes por aprobar (vista=por_aprobar), aprobadas (aprobadas) o todas, con cuántas hay en cada vista."""
    return svc.lista(db, user, vista)


@router.get("/solicitudes/{solicitud_id}")
def detalle(solicitud_id: int, db: Db, user: User):
    """Una solicitud con sus líneas y qué acciones se pueden hacer."""
    return svc.detalle(db, user, solicitud_id)


@router.post("/solicitudes")
def crear(datos: SolicitudIn, db: Db, user: User, clave: Clave = None):
    """Crea una solicitud, pendiente de aprobación."""
    return ejecutar(db, user, clave, lambda: svc.crear(db, user, datos.model_dump()))


@router.put("/solicitudes/{solicitud_id}")
def editar(solicitud_id: int, datos: SolicitudIn, db: Db, user: User, clave: Clave = None):
    """Corrige una solicitud pendiente o rechazada (la rechazada vuelve a pendiente)."""
    return ejecutar(db, user, clave, lambda: svc.editar(db, user, solicitud_id, datos.model_dump()))


@router.post("/solicitudes/{solicitud_id}/aprobar")
def aprobar(solicitud_id: int, datos: Revision, db: Db, user: User, clave: Clave = None):
    """Aprueba una solicitud pendiente, con un comentario opcional."""
    return ejecutar(db, user, clave, lambda: svc.aprobar(db, user, solicitud_id, datos.comentario))


@router.post("/solicitudes/{solicitud_id}/rechazar")
def rechazar(solicitud_id: int, datos: Revision, db: Db, user: User, clave: Clave = None):
    """Rechaza una solicitud pendiente; el comentario es obligatorio."""
    return ejecutar(db, user, clave, lambda: svc.rechazar(db, user, solicitud_id, datos.comentario))


@router.post("/solicitudes/{solicitud_id}/cancelar")
def cancelar(solicitud_id: int, db: Db, user: User, clave: Clave = None):
    """Cancela una solicitud pendiente, rechazada o aprobada (quien aprueba o quien la pidió)."""
    return ejecutar(db, user, clave, lambda: svc.cancelar(db, user, solicitud_id))


@router.post("/solicitudes/convertir")
def convertir(datos: Convertir, db: Db, user: User, clave: Clave = None):
    """Convierte solicitudes aprobadas en una OC en borrador del proveedor; devuelve la OC para seguir en el asistente."""
    return ejecutar(db, user, clave, lambda: svc.convertir(db, user, datos.solicitud_ids, datos.proveedor_id, datos.oc))
