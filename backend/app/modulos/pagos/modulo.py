"""Contrato del módulo de pagos a proveedores (cuentas por pagar)."""
from app.core.modulos import Modulo
from app.modulos.pagos import api

MODULO = Modulo(
    clave="pagos", nombre="Pagos a proveedores",
    descripcion="Facturas por pagar con el cuadre de tres vías (OC, factura, recepción), vencimientos y pagos programados y pagados.",
    rutas=lambda: [api.router],
)
