"""Contrato del módulo de datos maestros: catálogos, listas de valores y cargas masivas."""
from app.core.modulos import Modulo
from app.modulos.comun import auditoria
from app.modulos.maestros import api, api_listas
from app.modulos.maestros.definiciones import CATALOGOS


def _al_cargar() -> None:
    # La bitácora muestra cada catálogo con su título
    auditoria.registrar_entidades({clave: c["titulo"] for clave, c in CATALOGOS.items() if c.get("titulo")})


MODULO = Modulo(
    clave="maestros", nombre="Datos maestros",
    descripcion="Catálogos, listas de valores, genéricos y escalas, cargas masivas y su gobierno (responsables, "
                "obligatorios, historial).",
    rutas=lambda: [api.router, api_listas.router],
    al_cargar=_al_cargar,
)
