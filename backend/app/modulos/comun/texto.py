"""Búsqueda de texto en las listas: varios términos, sin distinguir acentos ni
mayúsculas.
"""
import re

from sqlalchemy import and_, func, or_
from sqlalchemy.sql import operators

from app.core.db import ES_SQLITE, plano

SEPARADORES = re.compile(r"[\s,;|]+")


def terminos(q: str | None) -> list[str]:
    """Términos de una búsqueda: se separan por espacios, comas, punto y coma,
    barras o saltos de línea (p. ej. una lista de OCs pegada desde Excel)."""
    return list(dict.fromkeys(t for t in SEPARADORES.split(str(q or "").strip()) if t))


ACENTOS = "áéíóúàèìòùäëïöüâêîôûãõñçÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÂÊÎÔÛÃÕÑÇ"

SIN_ACENTOS = "aeiouaeiouaeiouaeiouaoncAEIOUAEIOUAEIOUAEIOUAONC"


def plano_sql(col):
    """La columna sin acentos y en minúsculas (SQLite: función registrada en la conexión)."""
    if ES_SQLITE:
        return func.plano(col)
    return func.lower(func.translate(col, ACENTOS, SIN_ACENTOS))


def _sin_acentos(condicion, termino: str):
    """Una comparación `columna.ilike(patrón)` pasa a compararse sin acentos ni
    mayúsculas en los dos lados; otras condiciones quedan igual."""
    if getattr(condicion, "operator", None) is operators.ilike_op:
        return plano_sql(condicion.left).like(f"%{plano(termino)}%")
    return condicion


def filtro_texto(q: str | None, condiciones):
    """Condición SQL para una búsqueda inteligente de uno o varios términos.
    `condiciones(patron)` devuelve las columnas comparadas con ese patrón.
    Cada término puede estar en cualquiera de las columnas y en cualquier orden;
    se ignoran acentos y mayúsculas. Varios códigos (términos con números) se
    buscan cualquiera de ellos; varias palabras deben estar todas
    (vietnam cat = vietnam y cat)."""
    ts = terminos(q)
    if not ts:
        return None
    por_termino = [or_(*[_sin_acentos(c, t) for c in condiciones(f"%{t}%")]) for t in ts]
    if len(ts) == 1:
        return por_termino[0]
    return or_(*por_termino) if all(re.search(r"\d", t) for t in ts) else and_(*por_termino)
