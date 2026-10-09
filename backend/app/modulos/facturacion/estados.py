"""Estados de los documentos (facturas y listas de empaque) y su texto.
"""


EDITABLE_FACTURA = ("BORRADOR", "EN_CORRECCION")

EDITABLE_PL = ("BORRADOR", "EN_CORRECCION")

ESTADO_TXT = {
    "BORRADOR": "in draft",
    "EN_CORRECCION": "under correction",
    "FINALIZADA": "finalized",
    "FINALIZADO": "finalized",
    "CANCELADA": "cancelled",
    "CANCELADO": "cancelled",
}
