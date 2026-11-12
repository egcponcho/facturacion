"""Contrato del módulo de clasificación arancelaria (complemento de comercio
exterior: la empresa lo apaga en Configuración → Empresa → Módulos)."""
from app.core.modulos import Modulo
from app.modulos.clasificacion import api, api_conocimiento

MODULO = Modulo(
    clave="clasificacion", nombre="Clasificación arancelaria",
    descripcion="Arancel oficial, motor de clasificación (familias, atributos, reglas) y conocimiento de la empresa.",
    rutas=lambda: [api.router, api_conocimiento.router],
)
