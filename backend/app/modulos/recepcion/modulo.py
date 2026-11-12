"""Contrato del módulo de recepción e inventario."""
from app.core.modulos import Modulo
from app.modulos.recepcion import api

MODULO = Modulo(
    clave="recepcion", nombre="Recepción e inventario",
    descripcion="Recepción en bodega por contenedor (conteos, ajustes, cierre) y existencias por bodega.",
    rutas=lambda: [api.router],
)
