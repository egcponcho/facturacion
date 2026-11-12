"""Estados de los documentos (facturas y listas de empaque) y su texto.

Las transiciones están en core/estados.py (máquinas FACTURA y PL).
"""
from sqlalchemy import func

from app.core.estados import FACTURA, PL
from app.modelos import Factura

EDITABLE_FACTURA = FACTURA.acciones["editar"][0]

EDITABLE_PL = PL.acciones["editar"][0]

ESTADO_TXT = {
    "BORRADOR": "in draft",
    "EN_CORRECCION": "under correction",
    "FINALIZADA": "finalized",
    "FINALIZADO": "finalized",
    "CANCELADA": "cancelled",
    "CANCELADO": "cancelled",
}


def fecha_devengo():
    """Fecha en que una factura cuenta como facturada: su fecha de documento o,
    si no tiene, el día en que se finalizó (la usan la lista de facturas,
    Inicio e Indicadores)."""
    return func.coalesce(Factura.fecha, func.date(Factura.finalizado_en))
