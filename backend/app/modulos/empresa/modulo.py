"""Contrato del módulo de empresa: ficha, marca, documentos y reglas de la organización."""
from app.core.modulos import Modulo
from app.modulos.empresa import api

MODULO = Modulo(
    clave="empresa", nombre="Empresa",
    descripcion="Ficha, marca, documentos y reglas de la organización.",
    rutas=lambda: [api.router],
)
