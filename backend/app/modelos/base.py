"""Tipos y funciones comunes del modelo: cantidades y fecha actual.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Numeric,
    TypeDecorator,
)


def cant(v):
    """Una cantidad tal como se muestra y se compara: entera si es exacta
    (pares, unidades, cajas…) y con hasta 3 decimales si se mide (kg, litros,
    metros…)."""
    if v is None:
        return None
    x = round(float(v), 3)
    return int(x) if x == int(x) else x


class Cantidad(TypeDecorator):
    """Columna de cantidad: NUMERIC(14,3) que se lee con cant()."""

    impl = Numeric(14, 3)
    cache_ok = True

    def process_bind_param(self, v, _dialecto):
        return None if v is None else Decimal(str(round(float(v), 3)))

    def process_result_value(self, v, _dialecto):
        return cant(v)


def exacto(v, escala: int):
    """Un número tal como se guarda en una columna NUMERIC de esa escala."""
    if v is None:
        return None
    return Decimal(str(v)).quantize(Decimal(1).scaleb(-escala))


class _Numero(TypeDecorator):
    """NUMERIC exacto que se lee como número de Python (entero si es exacto):
    la base guarda el valor sin errores de coma flotante y las operaciones
    con dinero se hacen en Decimal (core/dinero.py)."""

    impl = Numeric(18, 6)
    cache_ok = True
    escala = 6

    def process_bind_param(self, v, _dialecto):
        return exacto(v, self.escala)

    def process_result_value(self, v, _dialecto):
        if v is None:
            return None
        x = float(exacto(v, self.escala))
        return int(x) if x == int(x) and abs(x) < 2**53 else x


class Precio(_Numero):
    """Precio unitario: NUMERIC(18,6) (admite precios de fracciones de centavo)."""

    impl = Numeric(18, 6)
    cache_ok = True
    escala = 6


class Importe(_Numero):
    """Importe o umbral en una moneda: NUMERIC(18,4); se redondea a los
    decimales de la moneda al calcular (core/dinero.py)."""

    impl = Numeric(18, 4)
    cache_ok = True
    escala = 4


class Tasa(_Numero):
    """Tasa o porcentaje: NUMERIC(12,6)."""

    impl = Numeric(12, 6)
    cache_ok = True
    escala = 6


def ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
