"""Reglas de negocio de la empresa.

Las reglas que cambian de una empresa a otra se guardan en la base de datos
(Configuración → Empresa) y se leen con `regla(nombre)`. Si la empresa no
definió una, se usa el valor de fábrica de `settings` (config.py), que solo
sirve como valor inicial de una instalación nueva.

En cada petición, `deps.usuario_actual` carga la configuración de la empresa
una sola vez con `usar_configuracion`; fuera de una petición (arranque,
semilla, pruebas de servicios) se usan los valores de fábrica.
"""
from contextvars import ContextVar

from app.core.config import settings

_config: ContextVar[dict] = ContextVar("config_empresa", default={})

# Reglas configurables (nombre en settings → descripción para la pantalla)
REGLAS = {
    "PROVEEDOR_PUEDE_FINALIZAR": "Suppliers can finalize their invoices and packing lists",
    "POSICION_EN_VARIAS_FACTURAS": "A PO line can be split across several active invoices",
    "FACTURA_EN_UNA_SOLA_UNIDAD": "All packing lists of an invoice must travel in the same load unit",
    "REQUERIR_DATOS_ADUANA": "Country of origin and HS code are required per line to finalize",
    "DIAS_ALERTA_BORRADOR": "Days before warning about drafts that still reserve quantities",
    "DIAS_MARGEN_RIESGO": "Minimum margin (days) before the required date to be on time",
    "DIAS_AVISO_TIENDA": "Days before the in-store date at which a PO is highlighted",
    "PAIS_BASE_CLASIF": "Country whose national code completes the suggested HS code",
    "COMPATIBILIDAD_BLOQUEANTE": "PO data that cannot be mixed in one invoice",
    "COMPATIBILIDAD_ADVERTENCIA": "PO data that only warns when mixed in one invoice",
}
# Datos de la OC que pueden ser parte de las reglas de compatibilidad
CAMPOS_COMPATIBILIDAD = ("sociedad", "centro", "centro_destino", "moneda", "incoterm", "puerto_despacho", "pais_origen")


def usar_configuracion(config: dict | None) -> None:
    """Configuración de la empresa para la petición en curso."""
    _config.set(config or {})


def configuracion_actual() -> dict:
    return _config.get() or {}


def regla(nombre: str):
    valor = (_config.get() or {}).get("reglas", {}).get(nombre)
    return getattr(settings, nombre) if valor is None else valor
