"""Empresa (organización) de la petición en curso.

Varias empresas comparten una instalación sin mezclar datos:

- Cada tabla de negocio lleva `organizacion_id` (mixin `DeOrganizacion` en
  models.py). Al crear un registro toma la empresa de la petición.
- Toda consulta del ORM se filtra por la empresa de la petición (evento
  `do_orm_execute` en services/organizacion.py), también las cargas de
  relaciones: un id de otra empresa simplemente "no existe".
- Sin empresa en el contexto (arranque, semilla, migraciones, pruebas de
  servicios) no se filtra.

Las reglas de negocio que antes eran variables de entorno se leen con
`regla(nombre)`: valor de la empresa si lo definió, si no el de settings.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from .config import settings

_org: ContextVar[int | None] = ContextVar("organizacion", default=None)
_config: ContextVar[dict] = ContextVar("config_organizacion", default={})

# Reglas configurables por empresa (nombre de settings → descripción)
REGLAS = {
    "PROVEEDOR_PUEDE_FINALIZAR": "Suppliers can finalize their invoices and packing lists",
    "POSICION_EN_VARIAS_FACTURAS": "A PO line can be split across several active invoices",
    "FACTURA_EN_UNA_SOLA_UNIDAD": "All packing lists of an invoice must travel in the same load unit",
    "REQUERIR_DATOS_ADUANA": "Country of origin and HS code are required per line to finalize",
    "DIAS_ALERTA_BORRADOR": "Days before warning about drafts that still reserve quantities",
    "DIAS_MARGEN_RIESGO": "Minimum margin (days) before the required date to be on time",
    "PAIS_BASE_CLASIF": "Country whose national code completes the suggested HS code",
}


def org_actual() -> int | None:
    return _org.get()


def usar_organizacion(organizacion_id: int | None, config: dict | None = None) -> None:
    _org.set(organizacion_id)
    _config.set(config or {})


@contextmanager
def en_organizacion(organizacion_id: int):
    """Trabaja temporalmente dentro de otra empresa (crearla, sembrarla)."""
    t1, t2 = _org.set(organizacion_id), _config.set({})
    try:
        yield
    finally:
        _org.reset(t1)
        _config.reset(t2)


def org_por_defecto() -> int:
    """Empresa de un registro nuevo: la de la petición o la principal."""
    return _org.get() or 1


def regla(nombre: str):
    valor = (_config.get() or {}).get("reglas", {}).get(nombre)
    return getattr(settings, nombre) if valor is None else valor
