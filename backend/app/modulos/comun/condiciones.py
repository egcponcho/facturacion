"""Condiciones declarativas de las reglas ({campo, op, valor}), compartidas por
los módulos que deciden algo con reglas (etiquetado, empaque…).

Los operadores son de una lista cerrada: nunca se evalúa código escrito por un
usuario. Cada módulo dice qué campos admite y con qué valores evalúa.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from app.core.errores import ErrorNegocio

OPERADORES = ("existe", "vacio", "igual", "distinto", "en", "no_en", "contiene", "no_contiene", "empieza", "termina",
              "mayor", "mayor_igual", "menor", "menor_igual", "entre", "en_familia", "coincide")
# Los que la interfaz ofrece a primera vista (los demás quedan en «Avanzado»)
OPERADORES_SIMPLES = ("igual", "distinto", "en", "no_en", "contiene", "vacio", "existe", "mayor", "menor")
SIN_VALOR = {"existe", "vacio"}
NUMERICOS = {"mayor", "mayor_igual", "menor", "menor_igual", "entre"}
LISTAS = {"en", "no_en"}
MAX_CONDICIONES = 20
MAX_VALORES = 200
# Patrones («coincide»): cortos, sin construcciones que hacen que el motor de
# expresiones regulares retroceda sin fin (repeticiones anidadas, alternativas
# repetidas, referencias atrás, búsquedas hacia delante o atrás) y contra un
# texto acotado. Así ninguna regla puede dejar el servidor calculando (ReDoS).
MAX_PATRON = 100
MAX_TEXTO_PATRON = 200


# ---- Validación -------------------------------------------------------------------------------
def limpiar(condiciones, validos: set[str], extra: Callable[[str, str, object], str | None] | None = None,
            operadores=OPERADORES) -> list[dict]:
    """Las condiciones limpias o 422: campo de `validos`, operador de la lista y
    un valor del tipo que el operador necesita. `extra(campo, op, valor)`
    devuelve un motivo para rechazar una condición que solo el módulo conoce."""
    if condiciones in (None, ""):
        return []
    if not isinstance(condiciones, list) or len(condiciones) > MAX_CONDICIONES:
        raise ErrorNegocio(f"Up to {MAX_CONDICIONES} conditions per rule.", 422, "validacion")
    errores, limpio = [], []
    for i, c in enumerate(condiciones):
        donde = f"condiciones.{i}"
        if not isinstance(c, dict):
            errores.append({"campo": donde, "mensaje": "Each condition needs a field, an operator and a value."})
            continue
        campo, op, valor = c.get("campo"), c.get("op"), c.get("valor")
        if campo not in validos:
            errores.append({"campo": donde, "mensaje": f"Unknown field: {campo}."})
            continue
        if op not in operadores:
            errores.append({"campo": donde, "mensaje": f"Unknown operator: {op}."})
            continue
        if op in SIN_VALOR:
            valor = None
        elif op in LISTAS:
            if isinstance(valor, str):
                valor = [x.strip() for x in valor.split(",") if x.strip()]
            if not isinstance(valor, list) or not valor or len(valor) > MAX_VALORES:
                errores.append({"campo": donde, "mensaje": f"Write between 1 and {MAX_VALORES} values."})
                continue
            valor = [str(x)[:100] for x in valor]
        elif op == "entre":
            if not isinstance(valor, list) or len(valor) != 2 or not all(_numero(x) is not None for x in valor):
                errores.append({"campo": donde, "mensaje": "Write the two numbers of the range."})
                continue
            valor = sorted(_numero(x) for x in valor)
        elif op in NUMERICOS:
            if _numero(valor) is None:
                errores.append({"campo": donde, "mensaje": "Write a number."})
                continue
            valor = _numero(valor)
        else:
            if valor in (None, "") or isinstance(valor, (list, dict)):
                errores.append({"campo": donde, "mensaje": "Write the value to compare."})
                continue
            valor = str(valor)[:200]
            if op == "coincide":
                motivo = validar_patron(valor)
                if motivo:
                    errores.append({"campo": donde, "mensaje": motivo})
                    continue
        if extra is not None and (motivo := extra(campo, op, valor)):
            errores.append({"campo": donde, "mensaje": motivo})
            continue
        limpio.append({"campo": campo, "op": op, "valor": valor})
    if errores:
        raise ErrorNegocio("Check the rule conditions.", 422, "validacion", errores)
    return limpio


def validar_patron(patron: str) -> str | None:
    """Por qué el patrón no se acepta (o None si es seguro)."""
    try:
        from re import _constants as k
        from re import _parser as analizador
    except ImportError:  # Python < 3.11
        import sre_constants as k
        import sre_parse as analizador
    if len(patron) > MAX_PATRON:
        return f"The pattern is too long (at most {MAX_PATRON} characters)."
    try:
        arbol = analizador.parse(patron)
    except (re.error, RecursionError, OverflowError):
        return "The pattern is not valid."
    prohibidos = {k.GROUPREF, k.GROUPREF_EXISTS, k.ASSERT, k.ASSERT_NOT}
    repeticiones = {k.MAX_REPEAT, k.MIN_REPEAT, getattr(k, "POSSESSIVE_REPEAT", k.MAX_REPEAT)}

    def hijos(op, av):
        if op in repeticiones:
            return [av[2]]
        if op == k.SUBPATTERN:
            return [av[-1]]
        if op == k.BRANCH:
            return list(av[1])
        if op == getattr(k, "ATOMIC_GROUP", None):
            return [av]
        return []

    def revisar(sub, dentro_de_repeticion: bool) -> str | None:
        for op, av in sub:
            if op in prohibidos:
                return "The pattern cannot use back-references or look-ahead/look-behind."
            if op in repeticiones and dentro_de_repeticion:
                return "The pattern cannot repeat a group that already repeats, like (a+)+: use a single repetition."
            if op == k.BRANCH and dentro_de_repeticion:
                return "The pattern cannot repeat alternatives, like (a|b)+: use a character class, like [ab]+."
            repite = op in repeticiones and av[1] > 1
            for h in hijos(op, av):
                motivo = revisar(h, dentro_de_repeticion or repite)
                if motivo:
                    return motivo
        return None

    return revisar(arbol, False)


def _patron_cumple(patron: str, texto: str) -> bool:
    """«coincide» acotado: un patrón inseguro guardado antes de esta validación
    no se evalúa, y el texto se mira solo hasta MAX_TEXTO_PATRON caracteres."""
    if len(texto) > MAX_TEXTO_PATRON or validar_patron(patron):
        return False
    try:
        return re.fullmatch(patron, texto, flags=re.IGNORECASE) is not None
    except re.error:
        return False


# ---- Evaluación -------------------------------------------------------------------------------
def _numero(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _vacio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v)


def _texto(v) -> str:
    return "" if v is None else str(v).strip().lower()


def cumple_condicion(c: dict, valores: dict) -> bool:
    v = valores.get(c["campo"])
    op, esperado = c["op"], c.get("valor")
    if op == "existe":
        return not _vacio(v)
    if op == "vacio":
        return _vacio(v)
    if op in NUMERICOS:
        n = _numero(v)
        if n is None:
            return False
        if op == "entre":
            return esperado[0] <= n <= esperado[1]
        return {"mayor": n > esperado, "mayor_igual": n >= esperado, "menor": n < esperado, "menor_igual": n <= esperado}[op]
    if op == "en_familia":
        return _texto(esperado) in [x.strip().lower() for x in str(v or "").split("/")]
    if isinstance(v, list):  # una colección: contiene / en sobre sus valores
        textos = {_texto(x) for x in v}
        if op in ("contiene", "igual"):
            return _texto(esperado) in textos
        if op in ("no_contiene", "distinto"):
            return _texto(esperado) not in textos
        if op == "en":
            return bool(textos & {_texto(x) for x in esperado})
        if op == "no_en":
            return not textos & {_texto(x) for x in esperado}
        return False
    s = _texto(v)
    if op == "igual":
        n, m = _numero(v), _numero(esperado)
        return (n == m) if n is not None and m is not None else s == _texto(esperado)
    if op == "distinto":
        return not cumple_condicion({**c, "op": "igual"}, valores)
    if op == "en":
        return s in {_texto(x) for x in esperado}
    if op == "no_en":
        return s not in {_texto(x) for x in esperado}
    if op == "contiene":
        return _texto(esperado) in s
    if op == "no_contiene":
        return _texto(esperado) not in s
    if op == "empieza":
        return s.startswith(_texto(esperado))
    if op == "termina":
        return s.endswith(_texto(esperado))
    if op == "coincide":
        return _patron_cumple(str(esperado), "" if v is None else str(v))
    return False


def cumple(condiciones: list[dict] | None, valores: dict) -> bool:
    return all(cumple_condicion(c, valores) for c in condiciones or [])


def detalle(condiciones: list[dict] | None, valores: dict) -> list[dict]:
    """Cada condición con el valor real y si se cumple (para explicar una decisión)."""
    return [{"campo": c["campo"], "op": c["op"], "valor": c.get("valor"), "real": valores.get(c["campo"]),
             "cumple": cumple_condicion(c, valores)} for c in condiciones or []]
