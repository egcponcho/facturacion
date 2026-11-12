"""Contrato del módulo de seguimiento e indicadores."""
from app.core.modulos import Modulo
from app.modulos.seguimiento import api

MODULO = Modulo(
    clave="seguimiento", nombre="Seguimiento e indicadores",
    descripcion="Inicio, búsqueda global, seguimiento, alertas, tableros e indicadores por módulo.",
    rutas=lambda: [api.router],
)
