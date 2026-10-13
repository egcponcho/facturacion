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


def ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
