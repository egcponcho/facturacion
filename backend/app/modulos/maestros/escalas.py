"""Escalas de valores: los valores de un atributo de variante en orden (una
serie de medidas, presentaciones, concentraciones…), reutilizables entre
productos y sin depender de un rubro.

Una escala lista sus valores ("6, 6.5, 7-10, 12", "S, M, L, XL" o
"250 ML, 500 ML, 1 L") y, si hace falta, el código de alguno ("7=070"). El
código de cada valor (la parte de la variante en su código) sale de ahí o de
la regla de la escala:
- MULTIPLICAR: valor numérico × factor, con ceros a la izquierda (7.5 × 10 → 075).
- CONSECUTIVO: 001, 002, 003… en el orden de la escala.
- VALOR: el propio valor sin espacios ni signos (S, M, XL, 32X30).
Si el código ya está usado en el producto, se toma el siguiente libre.
"""
import re

from app.core.errores import ErrorNegocio
from app.modulos.comun.normalizar import clave

REGLAS = [["MULTIPLICAR", "Value × factor (7.5 × 10 → 075)"], ["CONSECUTIVO", "Consecutive (001, 002…)"],
          ["VALOR", "Same as the value (S, M, XL)"]]


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


def valores_de(texto: str) -> list[tuple[str, str | None]]:
    """[(valor, código escrito o None)] en el orden de la escala."""
    res: list[tuple[str, str | None]] = []
    for parte in re.split(r"[,;\n]+", texto or ""):
        parte = parte.strip()
        if not parte:
            continue
        valor, _, cod = parte.partition("=")
        valor, cod = valor.strip().upper(), (cod.strip().upper() or None)
        m = re.fullmatch(r"(\d+(?:\.5)?)\s*(?:-|TO|A)\s*(\d+(?:\.5)?)", valor)
        lista = _rango(m.group(1), m.group(2)) if m and not cod else None
        for t in (lista or [valor]):
            if t not in {x for x, _ in res}:
                res.append((t, cod if not lista else None))
    return res


def validar(texto: str) -> list[str]:
    errores = []
    valores = valores_de(texto)
    if not valores:
        errores.append("List at least one value.")
    cods = [c for _, c in valores if c]
    if len(cods) != len(set(cods)):
        errores.append("Two values have the same code.")
    if any(not re.fullmatch(r"[A-Z0-9._\-/]{1,20}", c) for c in cods):
        errores.append("Value codes: letters and numbers, up to 20.")
    return errores


def _por_regla(regla: str, valor: str, indice: int, factor: int | None, longitud: int | None) -> str | None:
    largo = longitud or 0
    if regla == "MULTIPLICAR":
        t = valor.replace(",", ".")
        if not re.fullmatch(r"\d+(\.\d+)?", t):
            return None
        n = float(t) * (factor or 1)
        if not float(n).is_integer():
            return None
        return str(int(n)).zfill(largo)
    if regla == "VALOR":
        return clave(valor) or None
    return str(indice + 1).zfill(largo or 3)


def codigo(escala, valor: str, usados: set[str]) -> str:
    """Código de un valor según la escala (o la regla usual si no hay escala),
    evitando los ya usados en el producto."""
    valor = (valor or "").strip().upper()
    if escala is None:
        regla, factor, longitud, lista = "MULTIPLICAR", 10, 3, []
    else:
        regla, factor, longitud, lista = escala.regla, escala.factor, escala.longitud, valores_de(escala.valores)
    escrito = next((c for t, c in lista if t == valor and c), None)
    indice = next((i for i, (t, _) in enumerate(lista) if t == valor), len(lista))
    for propuesta in (escrito, _por_regla(regla, valor, indice, factor, longitud)):
        if propuesta and propuesta not in usados:
            return propuesta
    largo = (longitud or 3) if regla != "VALOR" else 3
    n = 1
    while str(n).zfill(largo) in usados:
        n += 1
        if n >= 10 ** max(largo, 3):
            raise ErrorNegocio("There are no free variant codes left.", 422, "sin_codigos")
    return str(n).zfill(largo)


def con_codigos(escala) -> list[dict]:
    usados: set[str] = set()
    res = []
    for v, _ in valores_de(escala.valores):
        c = codigo(escala, v, usados)
        usados.add(c)
        res.append({"valor": v, "codigo": c})
    return res
