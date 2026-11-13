from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.modulos.pagos import pagos as svc
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


class ProgramarIn(BaseModel):
    factura_ids: list[int] = Field(min_length=1, max_length=500)
    fecha: date


class PagarIn(BaseModel):
    fecha: date
    referencia: str | None = Field(default=None, max_length=80)


class VenceIn(BaseModel):
    vence: date | None = None


@router.get("/pagos/facturas")
def facturas(db: Db, user: User, vista: str = "por_pagar", proveedor_id: int | None = None):
    """Facturas finalizadas por pagar (vista=por_pagar), con diferencias en el cuadre (diferencias), pagadas
    (pagadas) o todas: importe, vencimiento, pagado, saldo, estado de pago y cuadre OC/factura/recepción."""
    return svc.lista(db, user, vista, proveedor_id)


@router.get("/pagos/facturas/{factura_id}")
def factura(factura_id: int, db: Db, user: User):
    """Una factura con el cuadre línea por línea (precio OC contra factura, facturado contra recibido) y sus pagos."""
    return svc.detalle(db, user, factura_id)


@router.get("/pagos/resumen")
def resumen(db: Db, user: User, proveedor_id: int | None = None):
    """Pagos de las próximas semanas (programado y sin programar) y antigüedad del saldo, en la moneda de la empresa."""
    return svc.resumen(db, user, proveedor_id)


@router.post("/pagos/programar")
def programar(datos: ProgramarIn, db: Db, user: User, clave: Clave = None):
    """Programa para la fecha el pago del saldo sin programar de cada factura."""
    return ejecutar(db, user, clave, lambda: svc.programar(db, user, datos.factura_ids, datos.fecha))


@router.post("/pagos/{pago_id}/pagar")
def pagar(pago_id: int, datos: PagarIn, db: Db, user: User, clave: Clave = None):
    """Marca pagado un pago programado, con la fecha real y la referencia."""
    return ejecutar(db, user, clave, lambda: svc.pagar(db, user, pago_id, datos.fecha, datos.referencia))


@router.post("/pagos/{pago_id}/anular")
def anular(pago_id: int, db: Db, user: User, clave: Clave = None):
    """Anula un pago programado."""
    return ejecutar(db, user, clave, lambda: svc.anular(db, user, pago_id))


@router.put("/pagos/facturas/{factura_id}/vence")
def vence(factura_id: int, datos: VenceIn, db: Db, user: User, clave: Clave = None):
    """Pone el vencimiento de la factura (vacío: vuelve al plazo de la condición de pago de su OC)."""
    return ejecutar(db, user, clave, lambda: svc.cambiar_vence(db, user, factura_id, datos.vence))
