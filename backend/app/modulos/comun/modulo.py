"""Contrato del módulo común: piezas que comparten todos los módulos
(edición exclusiva, historial, adjuntos, tablas, formato). Publica registros
en los que los demás se inscriben; no conoce a ningún módulo de negocio."""
from app.core.modulos import Modulo
from app.modulos.comun import api

MODULO = Modulo(
    clave="comun", nombre="Común",
    descripcion="Edición exclusiva de un registro y bitácora de auditoría.",
    rutas=lambda: [api.router],
)
