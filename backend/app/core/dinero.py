"""Dinero exacto.

Los precios, importes y tasas se guardan en columnas NUMERIC (modelos/base.py:
Precio, Importe, Tasa) y se calculan aquí en Decimal, nunca en coma flotante.

Política de redondeo: cada importe de línea (cantidad × precio) se redondea a
los decimales de su moneda (lista de monedas; 2 si no se conoce) con
redondeo comercial (mitad hacia arriba) y el total del documento es la suma
de esas líneas. Así el total de la pantalla, el PDF, el Excel y lo que se
exporta coinciden al centavo.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CERO = Decimal(0)


def decimal(v) -> Decimal:
    """Cualquier número (int, float, Decimal o texto) como Decimal exacto de
    su representación decimal (0.1 → Decimal('0.1'), no 0.1000000000000000055…)."""
    if v is None or v == "":
        return CERO
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def decimales(moneda: str | None) -> int:
    """Decimales de la moneda según la lista de monedas de la empresa."""
    from app.core import listas

    v = listas.valor("moneda", (moneda or "").upper()) or {}
    d = v.get("decimales")
    return 2 if d is None else int(d)


def redondear(v, moneda: str | None = None, decimales_: int | None = None) -> Decimal:
    d = decimales(moneda) if decimales_ is None else decimales_
    return decimal(v).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)


def importe(cantidad, precio, moneda: str | None = None) -> Decimal:
    """Importe de una línea: cantidad × precio redondeado a la moneda."""
    return redondear(decimal(cantidad) * decimal(precio), moneda)


def total(lineas, moneda: str | None = None) -> Decimal:
    """Suma de importes de línea [(cantidad, precio)], cada uno ya redondeado."""
    return sum((importe(c, p, moneda) for c, p in lineas), CERO)


def numero(v: Decimal | None):
    """Decimal → número para JSON (entero si es exacto)."""
    if v is None:
        return None
    x = float(v)
    return int(x) if x == int(x) and abs(x) < 2**53 else x


def iguales(a, b) -> bool:
    """¿Dos precios o importes son el mismo valor exacto?"""
    if a is None or b is None:
        return a is b
    return decimal(a) == decimal(b)


def importe_sql(cantidad, precio, decimales_: int = 2):
    """Importe de línea en SQL, redondeado como importe(): las sumas de las
    listas y tableros coinciden con el detalle de cada documento."""
    from sqlalchemy import Numeric, cast, func

    return func.round(cast(cantidad * precio, Numeric(24, 6)), decimales_)


def porcentaje(v) -> Decimal | None:
    """Un porcentaje escrito («15», «15 %», «7,5») como número; None si está
    vacío. ValueError si no es un número."""
    if v is None:
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    t = str(v).replace("%", "").replace(" ", "").strip()
    if not t:
        return None
    if t.count(",") == 1 and "." not in t:
        t = t.replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation as e:
        raise ValueError(f"{v} is not a percentage.") from e


def porcentaje_o_nota(v) -> tuple[Decimal | None, str | None]:
    """El porcentaje, o el texto tal cual si no es un número (p. ej. «Parte II»)."""
    try:
        return porcentaje(v), None
    except ValueError:
        return None, str(v).strip()[:20] or None
