"""Unidades de medida de los artículos (una sola lista para todo el sistema).

Un artículo se mide en la unidad que corresponde a su familia: pares, unidades,
docenas, juegos, kilos, litros, metros… Las cajas de prepack (CJ) solo existen
para los prepacks. Cada unidad tiene sus alias, para leer archivos de clientes
y proveedores (PR, PCS, KGS, LTS…).
"""
from .common import ErrorNegocio

# código, singular, plural, alias
UNIDADES = [
    ("PAR", "pair", "pairs", ("PR", "PRS", "PARES", "PAIR", "PAIRS")),
    ("UN", "unit", "units", ("U", "UND", "UNID", "UNIDAD", "UNIDADES", "EA", "PC", "PCS", "PZA", "PIEZA", "PIEZAS", "UNIT", "UNITS")),
    ("DOC", "dozen", "dozens", ("DOCENA", "DOCENAS", "DZ", "DOZ", "DOZEN")),
    ("JGO", "set", "sets", ("JUEGO", "JUEGOS", "SET", "SETS", "KIT", "KITS")),
    ("KG", "kg", "kg", ("KGS", "KILO", "KILOS", "KILOGRAMO", "KILOGRAMOS")),
    ("G", "g", "g", ("GR", "GRS", "GRAMO", "GRAMOS")),
    ("L", "liter", "liters", ("LT", "LTS", "LITRO", "LITROS", "LITER", "LITERS", "LITRE")),
    ("ML", "ml", "ml", ("MILILITRO", "MILILITROS")),
    ("M", "meter", "meters", ("MT", "MTS", "METRO", "METROS", "METER", "METERS")),
    ("M2", "m²", "m²", ("MT2", "MTS2", "METRO2", "SQM")),
    ("M3", "m³", "m³", ("MT3", "METRO3", "CBM")),
    ("ROL", "roll", "rolls", ("ROLLO", "ROLLOS", "ROLL", "ROLLS")),
    ("CJ", "prepack carton", "prepack cartons", ("CAJA", "CAJAS", "CS", "CTN")),
]
CODIGOS = [u[0] for u in UNIDADES]
DE_ARTICULO = [c for c in CODIGOS if c != "CJ"]  # la caja de prepack no es la unidad de un artículo sólido
_ALIAS = {a: u[0] for u in UNIDADES for a in (u[0], *u[3])}
_TEXTO = {u[0]: (u[1], u[2]) for u in UNIDADES}


def normalizar(v) -> str | None:
    """El código de la unidad escrita (o None si no es una unidad conocida)."""
    return _ALIAS.get(str(v or "").strip().upper().rstrip("."))


def validar(v, articulo: bool = False) -> str:
    u = normalizar(v)
    validas = DE_ARTICULO if articulo else CODIGOS
    if u not in validas:
        raise ErrorNegocio(f"The unit {v or '(empty)'} is not valid ({', '.join(validas)}).", 422, "validacion")
    return u


def texto(unidad: str, cantidad=None) -> str:
    s, p = _TEXTO.get(unidad, ("unit", "units"))
    return s if cantidad == 1 else p


def opciones(articulo: bool = False) -> list[list[str]]:
    return [[c, f"{_TEXTO[c][1].capitalize()} ({c})"] for c in (DE_ARTICULO if articulo else CODIGOS)]
