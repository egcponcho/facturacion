"""Listas de valores configurables (unidades de medida, monedas, incoterms,
modos y modalidades de transporte, tipos de centro, almacén, contacto,
impuesto y documento técnico).

La empresa las mantiene en Datos maestros → Listas de valores y se guardan en
`valores_lista`. En cada petición, `web.dependencias` las carga una sola vez
con `usar_listas`; fuera de una petición (arranque, semilla, pruebas de
servicios) se usan los valores de fábrica de este archivo, que son los mismos
que la migración 0040 deja en una instalación nueva.

Cada lista declara los atributos que usa (columnas de `valores_lista`) y sus
códigos de sistema: valores de los que depende el código (p. ej. la caja de
prepack CJ). Esos se pueden renombrar, pero no borrar, desactivar ni cambiar
de código.
"""
from contextvars import ContextVar

# lista → etiqueta, ayuda, atributos que usa y códigos de sistema
LISTAS: dict[str, dict] = {
    "unidad": {
        "etiqueta": "Units of measure",
        "ayuda": "Units in which items are counted or measured. Counted units only take whole quantities.",
        "atributos": ["nombre_plural", "alias", "contable"],
        "sistema": ["CJ"],
    },
    "moneda": {
        "etiqueta": "Currencies",
        "ayuda": "Currencies of POs and invoices: symbol, decimals and the amount in words of the documents.",
        "atributos": ["simbolo", "decimales", "letras_en", "letras_es"],
        "sistema": [],
    },
    "incoterm": {
        "etiqueta": "Incoterms",
        "ayuda": "Delivery terms of POs and invoices.",
        "atributos": [],
        "sistema": [],
    },
    "modo_transporte": {
        "etiqueta": "Transport modes",
        "ayuda": "How goods travel. The calculation decides how load units are suggested: by volume (full and "
                 "consolidated units) or by chargeable weight (actual weight vs. volume × factor).",
        "atributos": ["calculo", "factor", "icono", "documento", "etiqueta_puerto", "etiqueta_transportista",
                      "etiqueta_unidad"],
        "sistema": [],
    },
    "modalidad_transporte": {
        "etiqueta": "Transport modalities",
        "ayuda": "Kinds of load unit of each mode. A consolidated modality shares space with other cargo (LCL, LTL).",
        "atributos": ["padre", "consolidado"],
        "sistema": [],
    },
    "tipo_centro": {"etiqueta": "Plant types", "ayuda": "", "atributos": [], "sistema": []},
    "tipo_almacen": {"etiqueta": "Storage location types", "ayuda": "", "atributos": [], "sistema": []},
    "tipo_contacto": {"etiqueta": "Contact types", "ayuda": "", "atributos": [], "sistema": []},
    "tipo_impuesto": {"etiqueta": "Tax types", "ayuda": "Taxes of the national tariff rules.", "atributos": [],
                      "sistema": []},
    "tipo_documento": {"etiqueta": "Technical document types",
                       "ayuda": "Technical evidence attached to a product (safety and technical data sheets, "
                                "certificates…).", "atributos": [], "sistema": []},
}
# Atributos de cada valor (columnas de valores_lista): etiqueta, tipo y largo máximo de los textos
ATRIBUTOS = {
    "nombre_plural": ("Plural name", "texto", 120),
    "alias": ("Other names in files (comma-separated)", "texto", 300),
    "contable": ("Counted in whole numbers", "bool"),
    "simbolo": ("Symbol", "texto", 5),
    "decimales": ("Decimals", "entero"),
    "letras_en": ("Amount in words, English (singular|plural)", "texto", 120),
    "letras_es": ("Amount in words, Spanish (singular|plural)", "texto", 120),
    "calculo": ("Load unit calculation", "opcion"),
    "factor": ("Volumetric factor (kg per m³)", "numero"),
    "icono": ("Icon", "opcion"),
    "documento": ("Transport document (e.g. B/L, AWB)", "texto", 40),
    "etiqueta_puerto": ("Name of its ports (e.g. Airport)", "texto", 40),
    "etiqueta_transportista": ("Name of its carriers (e.g. Airline)", "texto", 40),
    "etiqueta_unidad": ("Name of its load units (singular|plural)", "texto", 80),
    "padre": ("Transport mode", "lista:modo_transporte"),
    "consolidado": ("Consolidated", "bool"),
}
CALCULOS = [["VOLUMEN", "By volume (full and consolidated units)"],
            ["PESO_COBRABLE", "By chargeable weight (air)"]]
ICONOS = [["barco", "Ship"], ["avion", "Plane"], ["camion", "Truck"], ["tren", "Train"], ["caja", "Box"]]


def _v(codigo, nombre, **datos):
    return {"codigo": codigo, "nombre": nombre, **datos}


# Valores de fábrica (los mismos que siembra la migración 0040)
FABRICA: dict[str, list[dict]] = {
    "unidad": [
        _v("PAR", "pair", nombre_plural="pairs", alias="PR,PRS,PARES,PAIR,PAIRS", contable=True),
        _v("UN", "unit", nombre_plural="units",
           alias="U,UND,UNID,UNIDAD,UNIDADES,EA,PC,PCS,PZA,PIEZA,PIEZAS,UNIT,UNITS", contable=True),
        _v("DOC", "dozen", nombre_plural="dozens", alias="DOCENA,DOCENAS,DZ,DOZ,DOZEN", contable=True),
        _v("JGO", "set", nombre_plural="sets", alias="JUEGO,JUEGOS,SET,SETS,KIT,KITS", contable=True),
        _v("KG", "kg", nombre_plural="kg", alias="KGS,KILO,KILOS,KILOGRAMO,KILOGRAMOS", contable=False),
        _v("G", "g", nombre_plural="g", alias="GR,GRS,GRAMO,GRAMOS", contable=False),
        _v("L", "liter", nombre_plural="liters", alias="LT,LTS,LITRO,LITROS,LITER,LITERS,LITRE", contable=False),
        _v("ML", "ml", nombre_plural="ml", alias="MILILITRO,MILILITROS", contable=False),
        _v("M", "meter", nombre_plural="meters", alias="MT,MTS,METRO,METROS,METER,METERS", contable=False),
        _v("M2", "m²", nombre_plural="m²", alias="MT2,MTS2,METRO2,SQM", contable=False),
        _v("M3", "m³", nombre_plural="m³", alias="MT3,METRO3,CBM", contable=False),
        _v("ROL", "roll", nombre_plural="rolls", alias="ROLLO,ROLLOS,ROLL,ROLLS", contable=True),
        _v("CJ", "prepack carton", nombre_plural="prepack cartons", alias="CAJA,CAJAS,CS,CTN", contable=True),
    ],
    "moneda": [
        _v("USD", "US dollar", simbolo="$", decimales=2, letras_en="US DOLLAR|US DOLLARS", letras_es="DÓLAR|DÓLARES"),
        _v("EUR", "Euro", simbolo="€", decimales=2, letras_en="EURO|EUROS", letras_es="EURO|EUROS"),
        _v("GTQ", "Quetzal", simbolo="Q", decimales=2, letras_en="QUETZAL|QUETZALES", letras_es="QUETZAL|QUETZALES"),
        _v("CRC", "Colón", simbolo="₡", decimales=2, letras_en="COLON|COLONES", letras_es="COLÓN|COLONES"),
        _v("HNL", "Lempira", simbolo="L", decimales=2, letras_en="LEMPIRA|LEMPIRAS", letras_es="LEMPIRA|LEMPIRAS"),
        _v("NIO", "Córdoba", simbolo="C$", decimales=2, letras_en="CORDOBA|CORDOBAS", letras_es="CÓRDOBA|CÓRDOBAS"),
        _v("PAB", "Balboa", simbolo="B/.", decimales=2, letras_en="BALBOA|BALBOAS", letras_es="BALBOA|BALBOAS"),
        _v("MXN", "Mexican peso", simbolo="$", decimales=2, letras_en="MEXICAN PESO|MEXICAN PESOS",
           letras_es="PESO MEXICANO|PESOS MEXICANOS"),
    ],
    "incoterm": [_v(c, n) for c, n in (
        ("EXW", "Ex works"), ("FCA", "Free carrier"), ("FAS", "Free alongside ship"), ("FOB", "Free on board"),
        ("CFR", "Cost and freight"), ("CIF", "Cost, insurance and freight"), ("CPT", "Carriage paid to"),
        ("CIP", "Carriage and insurance paid to"), ("DAP", "Delivered at place"),
        ("DPU", "Delivered at place unloaded"), ("DDP", "Delivered duty paid"))],
    "modo_transporte": [
        _v("MARITIMO", "Ocean", calculo="VOLUMEN", icono="barco", documento="B/L", etiqueta_puerto="Port",
           etiqueta_transportista="Shipping line", etiqueta_unidad="Container|Containers"),
        _v("AEREO", "Air", calculo="PESO_COBRABLE", factor=167, icono="avion", documento="AWB",
           etiqueta_puerto="Airport", etiqueta_transportista="Airline", etiqueta_unidad="Air waybill|Air waybills"),
        _v("TERRESTRE", "Road", calculo="VOLUMEN", icono="camion", documento="Waybill",
           etiqueta_puerto="Customs post", etiqueta_transportista="Carrier", etiqueta_unidad="Truck|Trucks"),
    ],
    "modalidad_transporte": [
        _v("FCL", "FCL · full container", padre="MARITIMO", consolidado=False),
        _v("LCL", "LCL · consolidated cargo", padre="MARITIMO", consolidado=True),
        _v("AEREO", "Air cargo", padre="AEREO", consolidado=False),
        _v("FTL", "FTL · full truck", padre="TERRESTRE", consolidado=False),
        _v("LTL", "LTL · partial load", padre="TERRESTRE", consolidado=True),
    ],
    "tipo_centro": [_v("BODEGA_FISCAL", "Bonded warehouse"), _v("ZONA_FRANCA", "Free trade zone"),
                    _v("LOCAL", "Local warehouse"), _v("TIENDA", "Store / DC")],
    "tipo_almacen": [_v("VIRTUAL", "Virtual"), _v("DETALLE", "Retail"), _v("MAYOREO", "Wholesale")],
    "tipo_contacto": [_v("FACTURACION", "Billing"), _v("NOTIFY", "Notify party"), _v("LOGISTICA", "Logistics")],
    "tipo_impuesto": [_v(c, c) for c in ("DAI", "IVA", "ITBMS", "ISV", "ISC", "SELECTIVO")] + [_v("OTRO", "Other")],
    "tipo_documento": [_v("SDS", "SDS · safety data sheet"), _v("TDS", "TDS · technical data sheet"),
                       _v("COA", "COA · certificate of analysis")],
}

_actual: ContextVar[dict | None] = ContextVar("listas", default=None)


def usar_listas(listas: dict | None) -> None:
    """Listas de la empresa para la petición en curso ({lista: [valores activos]})."""
    _actual.set(listas)


def valores(lista: str) -> list[dict]:
    """Valores activos de una lista, en su orden."""
    actual = _actual.get()
    return (actual if actual is not None else FABRICA).get(lista, [])


def codigos(lista: str) -> list[str]:
    return [v["codigo"] for v in valores(lista)]


def valor(lista: str, codigo: str | None) -> dict | None:
    return next((v for v in valores(lista) if v["codigo"] == codigo), None) if codigo else None


def nombre(lista: str, codigo: str | None) -> str | None:
    v = valor(lista, codigo)
    return v["nombre"] if v else codigo


def opciones(lista: str) -> list[list[str]]:
    """[[código, nombre]] para los campos de opción de los catálogos."""
    return [[v["codigo"], v["nombre"]] for v in valores(lista)]
