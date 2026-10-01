"""Escalas de tallas: una base genérica y reutilizable para cualquier tipo de
producto (calzado, ropa, accesorios…) sin depender de una empresa o marca.

Una escala lista sus tallas en orden ("6, 6.5, 7-10, 12" o "S, M, L, XL") y,
si hace falta, el código de alguna ("7=070"). El código de cada talla sale de
ahí o de la regla de la escala:
- MULTIPLICAR: talla numérica × factor, con ceros a la izquierda (7.5 × 10 → 075).
- CONSECUTIVO: 001, 002, 003… en el orden de la escala.
- TALLA: la propia talla sin espacios ni signos (S, M, XL, 32X30).
Si el código ya está usado en el genérico, se toma el siguiente libre.
"""
import re

from .common import ErrorNegocio
from .normalizar import clave

REGLAS = [["MULTIPLICAR", "Size × factor (7.5 × 10 → 075)"], ["CONSECUTIVO", "Consecutive (001, 002…)"],
          ["TALLA", "Same as the size (S, M, XL)"]]


def _rango(a: str, b: str) -> list[str] | None:
    try:
        x, y = float(a), float(b)
    except ValueError:
        return None
    paso = 0.5 if (".5" in a or ".5" in b) else 1
    out, v = [], x
    while v <= y + 1e-9:
        out.append(str(int(v)) if float(v).is_integer() else str(v))
        v += paso
    return out


def tallas_de(texto: str) -> list[tuple[str, str | None]]:
    """[(talla, código escrito o None)] en el orden de la escala."""
    res: list[tuple[str, str | None]] = []
    for parte in re.split(r"[,;\n]+", texto or ""):
        parte = parte.strip()
        if not parte:
            continue
        talla, _, cod = parte.partition("=")
        talla, cod = talla.strip().upper(), (cod.strip().upper() or None)
        m = re.fullmatch(r"(\d+(?:\.5)?)\s*(?:-|TO|A)\s*(\d+(?:\.5)?)", talla)
        lista = _rango(m.group(1), m.group(2)) if m and not cod else None
        for t in (lista or [talla]):
            if t not in {x for x, _ in res}:
                res.append((t, cod if not lista else None))
    return res


def validar(texto: str) -> list[str]:
    errores = []
    tallas = tallas_de(texto)
    if not tallas:
        errores.append("List at least one size.")
    cods = [c for _, c in tallas if c]
    if len(cods) != len(set(cods)):
        errores.append("Two sizes have the same code.")
    if any(not re.fullmatch(r"[A-Z0-9._\-/]{1,20}", c) for c in cods):
        errores.append("Size codes: letters and numbers, up to 20.")
    return errores


def _por_regla(regla: str, talla: str, indice: int, factor: int | None, longitud: int | None) -> str | None:
    largo = longitud or 0
    if regla == "MULTIPLICAR":
        t = talla.replace(",", ".")
        if not re.fullmatch(r"\d+(\.\d+)?", t):
            return None
        n = float(t) * (factor or 1)
        if not float(n).is_integer():
            return None
        return str(int(n)).zfill(largo)
    if regla == "TALLA":
        return clave(talla) or None
    return str(indice + 1).zfill(largo or 3)


def codigo(escala, talla: str, usados: set[str]) -> str:
    """Código de una talla según la escala (o la regla usual si no hay escala),
    evitando los ya usados en el genérico."""
    talla = (talla or "").strip().upper()
    if escala is None:
        regla, factor, longitud, lista = "MULTIPLICAR", 10, 3, []
    else:
        regla, factor, longitud, lista = escala.regla, escala.factor, escala.longitud, tallas_de(escala.tallas)
    escrito = next((c for t, c in lista if t == talla and c), None)
    indice = next((i for i, (t, _) in enumerate(lista) if t == talla), len(lista))
    for propuesta in (escrito, _por_regla(regla, talla, indice, factor, longitud)):
        if propuesta and propuesta not in usados:
            return propuesta
    largo = (longitud or 3) if regla != "TALLA" else 3
    n = 1
    while str(n).zfill(largo) in usados:
        n += 1
        if n >= 10 ** max(largo, 3):
            raise ErrorNegocio("There are no free size codes left.", 422, "sin_codigos")
    return str(n).zfill(largo)


def con_codigos(escala) -> list[dict]:
    usados: set[str] = set()
    res = []
    for t, _ in tallas_de(escala.tallas):
        c = codigo(escala, t, usados)
        usados.add(c)
        res.append({"talla": t, "codigo": c})
    return res
