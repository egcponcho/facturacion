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
from datetime import date, datetime, timezone

from app.core.config import settings

_config: ContextVar[dict | None] = ContextVar("config_empresa", default=None)

# Reglas configurables (nombre en settings → descripción para la pantalla)
REGLAS = {
    "PROVEEDOR_PUEDE_FINALIZAR": "Suppliers can finalize their invoices and packing lists",
    "POSICION_EN_VARIAS_FACTURAS": "A PO line can be split across several active invoices",
    "FACTURA_EN_UNA_SOLA_UNIDAD": "All packing lists of an invoice must travel in the same load unit",
    "REQUERIR_DATOS_ADUANA": "Country of origin and HS code are required per line to finalize",
    "DIAS_ALERTA_BORRADOR": "Days before warning about drafts that still reserve quantities",
    "DIAS_MARGEN_RIESGO": "Minimum margin (days) before the required date to be on time",
    "DIAS_AVISO_TIENDA": "Days before the in-store date at which a PO is highlighted",
    "DIAS_TOLERANCIA_ARRIBO": "Days after the committed ETA that still count as an on-time arrival",
    "DIAS_TOLERANCIA_XF": "Days after the original XF that still count as an on-time pickup",
    "META_LIBERACION_A_TIEMPO": "Target (%) of logistics releases on time",
    "ETIQUETAS_CUATRO_OJOS": "A label design version must be approved by someone other than its author",
    "ETIQUETAS_GENERACION_PARCIAL": "A labeling job can generate its ready records and leave the ones with errors for later",
    "ETIQUETAS_ASINCRONO_DESDE": "Labels from which a labeling job is generated in the background",
    "ETIQUETAS_MAXIMO_TRABAJO": "Most labels in one labeling job",
    "ETIQUETAS_PL_SIN_FINALIZAR": "Real labels can be generated from packing lists that are not finalized (tests always can)",
    "ETIQUETAS_VALIDAR_EMPAQUE": "Warn when a packing list differs from the casepack and inner pack of the PO",
    "PAIS_BASE_CLASIF": "Country whose national code completes the suggested HS code",
    "COMPATIBILIDAD_BLOQUEANTE": "PO data that cannot be mixed in one invoice",
    "COMPATIBILIDAD_ADVERTENCIA": "PO data that only warns when mixed in one invoice",
    "APROBACION_CUATRO_OJOS": "Whoever creates or sends a PO cannot approve it",
    "APROBAR_OC_IMPORTADAS": "POs loaded from the ERP also go through the approval rules",
    "EXIGIR_LIBERACION_ANTES_ENTREGA": "A load unit is delivered to the warehouse only after its customs release",
}
# Datos de la OC que pueden ser parte de las reglas de compatibilidad
CAMPOS_COMPATIBILIDAD = ("sociedad", "centro", "centro_destino", "moneda", "incoterm", "puerto_despacho", "pais_origen")


def zona_horaria() -> str:
    return ((configuracion_actual().get("preferencias") or {}).get("zona_horaria")) or "UTC"


def hoy() -> date:
    """La fecha de hoy donde está la empresa (su zona horaria), no la del servidor:
    lo que se imprime en una etiqueta y la vigencia de una regla dependen de ella."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return datetime.now(ZoneInfo(zona_horaria())).date()
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(timezone.utc).date()


def usar_configuracion(config: dict | None) -> None:
    """Configuración de la empresa para la petición en curso."""
    _config.set(config or {})


def configuracion_actual() -> dict:
    return _config.get() or {}


def regla(nombre: str):
    valor = (_config.get() or {}).get("reglas", {}).get(nombre)
    return getattr(settings, nombre) if valor is None else valor
