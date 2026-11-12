"""Contrato del módulo de integraciones con sistemas externos (ERP u otros)."""
from app.core.modulos import Modulo
from app.modulos.integraciones import api

MODULO = Modulo(
    clave="integraciones", nombre="Integraciones",
    descripcion="Sistemas externos (ERP u otros): adaptadores de formato, mapeos versionados, entrada de OCs, salida de "
                "facturas, bitácora y referencias externas.",
    rutas=lambda: [api.router],
)
