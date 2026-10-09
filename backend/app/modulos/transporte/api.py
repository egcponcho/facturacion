from fastapi import APIRouter, Query

from app.esquemas import (
    AsignarPL,
    ConMotivo,
    EmbarqueIn,
    EmbarquePatch,
    EventoIn,
    PLIds,
    Recoleccion,
    UnidadIn,
    UnidadPatch,
)
from app.modulos.transporte import transporte as svc
from app.modulos.transporte.sugerencias import sugerir_unidades
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/sugerencia-unidades")
def sugerencia_unidades(db: Db, user: User, cbm: float = Query(0, ge=0), kg: float = Query(0, ge=0),
                        modo: str | None = Query(None, max_length=20)):
    """Qué unidades de carga convienen para ese volumen y peso."""
    return sugerir_unidades(db, cbm, kg, modo)


@router.get("/embarques")
def listar(db: Db, user: User, estado: str | None = None, q: str | None = None):
    return svc.listar_embarques(db, user, estado, q)


@router.post("/embarques")
def crear(datos: EmbarqueIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.crear_embarque(db, user, datos))


@router.get("/embarques/{embarque_id}")
def detalle(embarque_id: int, db: Db, user: User):
    return svc.detalle_embarque(db, user, embarque_id)


@router.patch("/embarques/{embarque_id}")
def actualizar(embarque_id: int, datos: EmbarquePatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.actualizar_embarque(db, user, embarque_id, datos))


@router.post("/embarques/{embarque_id}/eventos")
def evento(embarque_id: int, datos: EventoIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.registrar_evento(db, user, embarque_id, datos))


@router.post("/embarques/{embarque_id}/cancelar")
def cancelar(embarque_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    """Anula un embarque planificado: su carga vuelve a estar disponible."""
    return ejecutar(db, user, clave, lambda: svc.cancelar(db, user, embarque_id, datos.motivo))


@router.post("/embarques/{embarque_id}/unidades")
def agregar_unidad(embarque_id: int, datos: UnidadIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.agregar_unidad(db, user, embarque_id, datos))


@router.get("/unidades/{unidad_id}")
def unidad(unidad_id: int, db: Db, user: User):
    return svc.detalle_unidad(db, user, unidad_id)


@router.patch("/unidades/{unidad_id}")
def actualizar_unidad(unidad_id: int, datos: UnidadPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.actualizar_unidad(db, user, unidad_id, datos))


@router.delete("/unidades/{unidad_id}")
def eliminar_unidad(unidad_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.eliminar_unidad(db, user, unidad_id))


@router.get("/unidades/{unidad_id}/disponibles")
def disponibles(unidad_id: int, db: Db, user: User, proveedor_id: int | None = None,
                q: str | None = None, solo_listos: bool = False):
    return svc.disponibles(db, user, unidad_id, proveedor_id, q, solo_listos)


@router.post("/unidades/{unidad_id}/asignar")
def asignar(unidad_id: int, datos: AsignarPL, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.asignar(db, user, unidad_id, datos))




@router.post("/unidades/{unidad_id}/desasignar")
def desasignar(unidad_id: int, datos: PLIds, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.desasignar(db, user, unidad_id, datos))


@router.post("/recoleccion")
def recoleccion(datos: Recoleccion, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.recoleccion(db, user, datos))
