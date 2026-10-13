"""Rutas del ciclo de vida de la OC: borrador del asistente, envío, aprobación,
cancelación, cierre, detalle e historial (docs/FLUJOS.md §1)."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.modulos.compras import flujo_oc as svc
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


class Borrador(BaseModel):
    cabecera: dict = Field(default_factory=dict)


class Guardar(BaseModel):
    version: int | None = None
    cabecera: dict | None = None
    lineas: list[dict] | None = Field(default=None, max_length=500)


class Validar(BaseModel):
    cabecera: dict = Field(default_factory=dict)
    lineas: list[dict] = Field(default_factory=list, max_length=500)
    paso: str = "revision"


class Version(BaseModel):
    version: int | None = None


class Comentario(BaseModel):
    comentario: str | None = Field(default=None, max_length=500)


class Motivo(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)


@router.get("/ordenes/pendientes-aprobacion")
def pendientes(db: Db, user: User):
    """OCs que esperan la aprobación del rol del usuario."""
    return svc.pendientes_de_aprobar(db, user)


@router.post("/ordenes/borrador")
def crear_borrador(datos: Borrador, db: Db, user: User, clave: Clave = None):
    """Primer paso del asistente: crea el borrador con los datos generales."""
    return ejecutar(db, user, clave, lambda: svc.crear_borrador(db, user, datos.cabecera))


@router.post("/ordenes/validar")
def validar(datos: Validar, db: Db, user: User, oc_id: int | None = None):
    """Errores de un paso del asistente (sin guardar)."""
    pasos = [p for p, _ in svc.PASOS]
    paso = datos.paso if datos.paso in pasos else "revision"
    return {"paso": paso, "errores": svc.validar_paso(db, user, {"cabecera": datos.cabecera, "lineas": datos.lineas}, paso, oc_id)}


@router.get("/ordenes/{oc_id}")
def detalle(oc_id: int, db: Db, user: User):
    """Detalle de la OC: posiciones, avance, pasos de aprobación y acciones que el usuario puede hacer."""
    return svc.detalle(db, user, oc_id)


@router.patch("/ordenes/{oc_id}")
def guardar(oc_id: int, datos: Guardar, db: Db, user: User, clave: Clave = None):
    """Guarda el borrador (aunque le falten datos)."""
    return ejecutar(db, user, clave, lambda: svc.guardar_borrador(db, user, oc_id, datos.model_dump(exclude_unset=True)))


@router.delete("/ordenes/{oc_id}")
def eliminar(oc_id: int, db: Db, user: User):
    """Elimina un borrador de OC que nunca se envió."""
    svc.eliminar(db, user, oc_id)
    db.commit()
    return {"ok": True}


@router.get("/ordenes/{oc_id}/historial")
def historial(oc_id: int, db: Db, user: User):
    """Historial de cambios de la OC, del más reciente al más antiguo."""
    return svc.historial(db, user, oc_id)


@router.post("/ordenes/{oc_id}/enviar")
def enviar(oc_id: int, datos: Version, db: Db, user: User, clave: Clave = None):
    """Envía el borrador (o la OC rechazada) a aprobación; si ninguna regla aplica, queda aprobada."""
    return ejecutar(db, user, clave, lambda: svc.enviar(db, user, oc_id, datos.version))


@router.post("/ordenes/{oc_id}/aprobar")
def aprobar(oc_id: int, datos: Comentario, db: Db, user: User, clave: Clave = None):
    """Aprueba el paso pendiente según el rol; con el último paso la OC queda aprobada y liberada."""
    return ejecutar(db, user, clave, lambda: svc.aprobar(db, user, oc_id, datos.comentario))


@router.post("/ordenes/{oc_id}/rechazar")
def rechazar(oc_id: int, datos: Motivo, db: Db, user: User, clave: Clave = None):
    """Rechaza el paso pendiente con motivo; la OC queda rechazada y se puede corregir y reenviar."""
    return ejecutar(db, user, clave, lambda: svc.rechazar(db, user, oc_id, datos.motivo))


@router.post("/ordenes/{oc_id}/cancelar")
def cancelar(oc_id: int, datos: Motivo, db: Db, user: User, clave: Clave = None):
    """Cancela la OC con motivo; si está en facturas activas, hay que cancelarlas antes o cerrar la OC."""
    return ejecutar(db, user, clave, lambda: svc.cancelar(db, user, oc_id, datos.motivo))


@router.post("/ordenes/{oc_id}/cerrar")
def cerrar(oc_id: int, datos: Motivo, db: Db, user: User, clave: Clave = None):
    """Cierra una OC aprobada con motivo: lo que falta por facturar deja de estar disponible."""
    return ejecutar(db, user, clave, lambda: svc.cerrar(db, user, oc_id, datos.motivo))


@router.post("/ordenes/{oc_id}/reabrir")
def reabrir(oc_id: int, datos: Motivo, db: Db, user: User, clave: Clave = None):
    """Reabre una OC cerrada con motivo: vuelve a quedar aprobada."""
    return ejecutar(db, user, clave, lambda: svc.reabrir(db, user, oc_id, datos.motivo))
