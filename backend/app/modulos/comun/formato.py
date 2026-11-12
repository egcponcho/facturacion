"""Cantidades con su unidad de medida, en texto.

El nombre de cada unidad sale de la lista «unidad» de la empresa
(core/listas.py, que se mantiene en Datos maestros)."""
from app.core import listas


def unidad_txt(unidad: str, cantidad: int | None = None) -> str:
    """«par» o «pares» según la cantidad; una unidad que no está en la lista se lee «unit(s)»."""
    u = listas.valor("unidad", unidad)
    if not u:
        return "unit" if cantidad == 1 else "units"
    return u["nombre"] if cantidad == 1 else (u.get("nombre_plural") or u["nombre"])


def cant_txt(cantidad: int, unidad: str) -> str:
    return f"{cantidad:,} {unidad_txt(unidad, cantidad)}"
