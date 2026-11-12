"""Contrato del módulo de plataforma: las organizaciones de la instalación."""
from app.core.modulos import Modulo
from app.modulos.plataforma import api

MODULO = Modulo(
    clave="plataforma", nombre="Plataforma",
    descripcion="Organizaciones (empresas cliente) de la instalación; solo la administración de la plataforma.",
    rutas=lambda: [api.router],
)
