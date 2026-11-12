"""Contrato del módulo de catálogo: familias, atributos, productos y artículos.
Los demás módulos lo leen por `catalogo/servicio.py`."""
from app.core.modulos import Modulo
from app.modulos.catalogo import api_familias

MODULO = Modulo(
    clave="catalogo", nombre="Catálogo", etiqueta="Datos maestros",
    descripcion="Árbol de familias y categorías del catálogo, con la sección que cada módulo guarda de ellas.",
    rutas=lambda: [api_familias.router],
)
