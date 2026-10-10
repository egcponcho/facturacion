"""Filtros por columna de las tablas (TablaDatos; docs/API.md).

Una lista del servidor acepta `f`, un JSON con {columna: [valores]}: cada
columna filtra por «es alguno de estos valores» (el valor `__vacio__` es el
dato vacío) y las columnas se combinan con «y». Cada lista declara qué
expresión SQL corresponde a cada columna que se puede filtrar; una columna
que no declara se ignora.

La ruta `<lista>/valores?columna=…` devuelve los valores únicos de esa columna
con cuántas filas tienen cada uno, bajo los demás filtros (como el filtro de
Excel): así el filtro de la tabla muestra solo lo que tiene sentido elegir.
"""
import json

from sqlalchemy import Boolean, String, cast, func, or_

from app.core.db import plano
from app.core.errores import ErrorNegocio
from app.modulos.comun.texto import plano_sql

VACIO = "__vacio__"
MAX_VALORES = 201  # uno más que lo que muestra el filtro: así sabe que hay más


def leer(f: str | None) -> dict[str, list[str]]:
    """El parámetro `f` como {columna: [valores en texto]}."""
    if not f:
        return {}
    try:
        datos = json.loads(f)
    except ValueError as e:
        raise ErrorNegocio("Invalid column filters.", 422, "datos_invalidos") from e
    if not isinstance(datos, dict):
        raise ErrorNegocio("Invalid column filters.", 422, "datos_invalidos")
    res = {}
    for k, v in list(datos.items())[:40]:
        vals = v if isinstance(v, list) else [v]
        vals = [str(x)[:200] for x in vals if x is not None and x != ""][:500]
        if vals:
            res[str(k)[:40]] = vals
    return res


def _texto(expr):
    return cast(expr, String)


def condicion(expr, valores: list[str]):
    """«La columna es alguno de estos valores» (incluido el vacío)."""
    vacio = VACIO in valores
    otros = [v for v in valores if v != VACIO]
    partes = []
    if isinstance(getattr(expr, "type", None), Boolean):
        verdad = {"true": True, "1": True, "false": False, "0": False}
        bools = {verdad[v.lower()] for v in otros if v.lower() in verdad}
        partes += [expr.is_(b) for b in bools]
    elif otros:
        partes.append(_texto(expr).in_(otros))
    if vacio:
        partes.append(expr.is_(None))
        if not isinstance(getattr(expr, "type", None), Boolean):
            partes.append(_texto(expr) == "")
    return or_(*partes) if partes else expr.is_(None) & expr.isnot(None)


def aplicar(consulta, columnas: dict, filtros: dict[str, list[str]], excepto: str | None = None):
    """La consulta con los filtros por columna (menos el de `excepto`)."""
    for k, vals in filtros.items():
        if k == excepto or k not in columnas:
            continue
        consulta = consulta.where(condicion(columnas[k], vals))
    return consulta


def valores(db, consulta, expr, q: str | None = None, contar=None) -> list[dict]:
    """Valores únicos de `expr` en la consulta, con cuántas filas tienen cada uno.
    `contar` es lo que se cuenta (por defecto, las filas); `q` busca dentro de
    los valores sin acentos ni mayúsculas."""
    n = func.count(func.distinct(contar)) if contar is not None else func.count()
    c = consulta.order_by(None).with_only_columns(expr, n).group_by(expr)
    if q and q.strip():
        c = c.where(plano_sql(_texto(expr)).like(f"%{plano(q.strip())}%"))
    c = c.order_by(expr.is_(None).desc(), expr.asc()).limit(MAX_VALORES)
    return [{"valor": v, "n": cuenta} for v, cuenta in db.execute(c)]


def columna_valida(columnas: dict, columna: str):
    if columna not in columnas:
        raise ErrorNegocio("This column cannot be filtered.", 422, "datos_invalidos")
    return columnas[columna]
