"""Contrato del módulo de reportes."""
from app.core.modulos import Modulo
from app.modulos.reportes import api

MODULO = Modulo(
    clave="reportes", nombre="Reportes",
    descripcion="Generador de reportes: fuentes permitidas, vista previa, exportación y reportes guardados.",
    rutas=lambda: [api.router],
)
