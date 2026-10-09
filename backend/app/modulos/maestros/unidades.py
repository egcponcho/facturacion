"""Unidades de medida de los artículos (una sola lista para todo el sistema).

Un artículo se mide en la unidad que corresponde a su familia: pares, unidades,
docenas, juegos, kilos, litros, metros… Las cajas de prepack (CJ) solo existen
para los prepacks. Cada unidad tiene sus alias, para leer archivos de clientes
y proveedores (PR, PCS, KGS, LTS…).
"""
from app.core import listas
from app.core.errores import ErrorNegocio

# La caja de prepack: unidad de sistema, solo para prepacks (no para un sólido)
PREPACK = "CJ"


def codigos() -> list[str]:
    return listas.codigos("unidad")


def de_articulo() -> list[str]:
    """Unidades de un artículo sólido."""
    return [c for c in codigos() if c != PREPACK]


def _alias() -> dict[str, str]:
    return {a.strip().upper(): u["codigo"] for u in listas.valores("unidad")
            for a in (u["codigo"], *(u.get("alias") or "").split(",")) if a.strip()}


def normalizar(v) -> str | None:
    """El código de la unidad escrita (o None si no es una unidad conocida)."""
    return _alias().get(str(v or "").strip().upper().rstrip("."))


def validar(v, articulo: bool = False) -> str:
    u = normalizar(v)
    validas = de_articulo() if articulo else codigos()
    if u not in validas:
        raise ErrorNegocio(f"The unit {v or '(empty)'} is not valid ({', '.join(validas)}).", 422, "validacion")
    return u


def texto(unidad: str, cantidad=None) -> str:
    u = listas.valor("unidad", unidad)
    if not u:
        return "unit" if cantidad == 1 else "units"
    return u["nombre"] if cantidad == 1 else (u.get("nombre_plural") or u["nombre"])


def opciones(articulo: bool = False) -> list[list[str]]:
    return [[c, f"{texto(c, 2).capitalize()} ({c})"] for c in (de_articulo() if articulo else codigos())]


def contable(unidad: str | None) -> bool:
    """Lo que se cuenta va en enteros; lo que se mide admite hasta 3 decimales."""
    u = listas.valor("unidad", unidad or "UN")
    return bool(u.get("contable")) if u else True


def error_cantidad(cantidad, unidad: str | None) -> str | None:
    """Por qué la cantidad no vale para la unidad (o None si vale)."""
    if cantidad is None:
        return None
    if float(cantidad) <= 0:
        return "The quantity must be greater than zero."
    if contable(unidad) and float(cantidad) != int(float(cantidad)):
        return f"{texto(unidad or 'UN', 2).capitalize()} are counted in whole numbers: {cantidad} is not valid."
    if round(float(cantidad), 3) != float(cantidad):
        return f"At most 3 decimals: {cantidad}."
    return None


def exigir_cantidad(cantidad, unidad: str | None) -> None:
    msg = error_cantidad(cantidad, unidad)
    if msg:
        raise ErrorNegocio(msg, 422, "validacion")
