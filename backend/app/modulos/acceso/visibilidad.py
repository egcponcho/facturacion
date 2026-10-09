"""Datos visibles por rol.

Cada rol puede tener grupos de datos ocultos (precios, códigos internos,
fechas internas…). Se configuran en Usuarios y accesos → Rol y se guardan en
`roles.datos_ocultos`.

Ocultar no es solo de la pantalla: el servidor quita esos datos de cada
respuesta de las pantallas de trabajo (órdenes, facturas, listas de empaque,
embarques, seguimiento, productos, tablero, búsqueda) y de los reportes en
Excel/PDF. Los documentos oficiales (factura comercial, lista de empaque)
siempre salen completos porque son documentos legales.

La pantalla usa la misma lista (`/auth/me` → `datos_ocultos`) para quitar las
columnas y los filtros de esos datos.
"""
from contextvars import ContextVar

from app.modelos import Usuario

# Grupo → texto para la pantalla, explicación, campos que el servidor quita de
# las respuestas y columnas de los reportes que se quitan.
GRUPOS: dict[str, dict] = {
    "precios": {
        "etiqueta": "Prices and amounts",
        "descripcion": "Unit prices, PO value, invoice amounts and invoiced value.",
        "claves": {"precio", "precio_oc", "precio_unitario", "importe", "importe_facturado", "motivo_precio",
                   "facturado_mes"},
        "columnas": {"Total", "Amount"},
    },
    "codigos_internos": {
        "etiqueta": "Company, plant and storage location codes",
        "descripcion": "Internal codes of the legal entity, plant, destination plant and storage location.",
        "claves": {"sociedad", "centro", "centro_destino", "almacen", "almacenes"},
        "columnas": {"Co. · plant", "Destination", "Plant", "Storage loc."},
    },
    "fechas_internas": {
        "etiqueta": "In-store dates and risk",
        "descripcion": "Date required in store, estimated arrival in store, margin and late risk.",
        "claves": {"fecha_tienda", "tienda_estimada", "dias_vs_tienda", "dias_tienda", "fecha_requerida_tienda",
                   "riesgo", "holgura"},
        "columnas": {"In store", "Vs. store", "Late to store"},
    },
    "liberaciones": {
        "etiqueta": "Commercial and logistics release details",
        "descripcion": "Release codes and dates. The user still sees whether a PO can be invoiced.",
        "claves": {"liberacion_comercial", "liberacion_logistica", "comercial_txt", "liberacion_txt", "comercial_ok", "logistica_ok", "con_cambios",
                   "fecha_lib_comercial", "fecha_lib_logistica"},
        "columnas": {"Comm. rel.", "Log. rel."},
    },
    "impuestos": {
        "etiqueta": "Duty rates and regulations",
        "descripcion": "Duty rate, taxes and import regulations of each destination country.",
        "claves": {"dai", "impuestos", "regulaciones"},
        "columnas": {"Duty (DAI)"},
    },
    "contactos": {
        "etiqueta": "Internal contacts",
        "descripcion": "Names, emails and phones of the company's people at each plant and legal entity.",
        "claves": {"contactos", "correos"},
        "columnas": set(),
    },
}

# Lo que cada tipo de rol de fábrica no ve al crearse (se puede cambiar)
DEFECTO_POR_TIPO = {"proveedor": ["fechas_internas", "liberaciones", "impuestos"]}

# Pantallas de trabajo cuyas respuestas se filtran. La configuración
# (catálogos, arancel, usuarios) no: ahí se administran esos datos.
RUTAS = ("/api/ordenes", "/api/facturas", "/api/packing-lists", "/api/seguimiento", "/api/embarques",
         "/api/unidades", "/api/dashboard", "/api/buscar", "/api/productos", "/api/alertas", "/api/recoleccion")

# Paneles de la página de inicio que un rol puede ocultar (Usuarios y accesos → Rol)
PANELES_INICIO = {
    "indicadores": "Indicators", "atencion": "Needs your attention", "tareas": "Next steps", "envios": "Shipments",
    "contenedores": "Load units being planned", "alertas": "Import alerts", "periodo": "Performance",
    "proveedores": "By supplier",
}


def paneles_validos(paneles) -> list[str]:
    return [p for p in PANELES_INICIO if p in set(paneles or [])]


_ocultos: ContextVar[frozenset] = ContextVar("datos_ocultos", default=frozenset())


def validos(grupos) -> list[str]:
    return [g for g in GRUPOS if g in set(grupos or [])]


def ocultos_de(user: Usuario | None) -> list[str]:
    if not user or user.rol == "admin" or not user.rol_ref:
        return []
    return validos(user.rol_ref.datos_ocultos)


def usar(user: Usuario | None) -> None:
    """Grupos ocultos de la petición en curso."""
    _ocultos.set(frozenset(ocultos_de(user)))


def oculto(grupo: str) -> bool:
    return grupo in _ocultos.get()


def _claves() -> set[str]:
    return set().union(*(GRUPOS[g]["claves"] for g in _ocultos.get())) if _ocultos.get() else set()


def quitar(datos, claves: set[str] | None = None):
    """Copia de `datos` sin los campos ocultos (en cualquier nivel)."""
    claves = _claves() if claves is None else claves
    if not claves:
        return datos
    if isinstance(datos, dict):
        return {k: quitar(v, claves) for k, v in datos.items() if k not in claves}
    if isinstance(datos, list):
        return [quitar(v, claves) for v in datos]
    return datos


def tabla(columnas: list, filas: list[list]) -> tuple[list, list[list]]:
    """Quita de un reporte las columnas de los grupos ocultos."""
    fuera = set().union(*(GRUPOS[g]["columnas"] for g in _ocultos.get())) if _ocultos.get() else set()
    if not fuera:
        return columnas, filas
    quedan = [i for i, c in enumerate(columnas) if c[0] not in fuera]
    return [columnas[i] for i in quedan], [[f[i] for i in quedan] for f in filas]


def reporte(indicadores: list, columnas: list, filas: list[list], hojas: list[dict] | None = None):
    """Reporte (Excel o PDF) sin las columnas ni los indicadores ocultos."""
    columnas, filas = tabla(columnas, filas)
    indicadores = [i for i in indicadores if tabla([i], [])[0]]
    hojas = [{**h, **dict(zip(("columnas", "filas"), tabla(h["columnas"], h["filas"])))} for h in hojas or []]
    return indicadores, columnas, filas, hojas


def catalogo() -> list[dict]:
    """Grupos para la pantalla de roles."""
    return [{"clave": k, "etiqueta": g["etiqueta"], "descripcion": g["descripcion"]} for k, g in GRUPOS.items()]
