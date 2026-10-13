"""Estados de los documentos (facturas y listas de empaque) y su texto.

Las transiciones están en core/estados.py (máquinas FACTURA y PL).
"""
from app.core.estados import FACTURA, PL

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
