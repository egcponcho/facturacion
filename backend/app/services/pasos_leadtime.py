"""Pasos de un plan de lead time: validación y formato de texto.

Cada paso: {codigo, nombre, tramo, dias, habiles, depende, modo}.
- tramo: entre qué hitos medidos cae (ver leadtimes.TRAMOS).
- habiles: cuenta solo lunes a viernes.
- depende: código de un paso anterior del mismo tramo del que arranca;
  vacío = el paso anterior; INICIO = en paralelo desde el inicio del tramo.
- modo: solo aplica a ese modo de transporte (vacío = todos).

En Excel se escriben en una celda, uno por línea o separados por «;»:
    transito: Ocean transit = 35d [MARITIMO]
    puerto: Customs clearance = 2bd
    puerto: Inspection = 1d (||)             -> en paralelo (también «(start)»)
    puerto: Trucking = 1d (> CUSTOMS)        -> después de ese paso (también «(after CUSTOMS)»)
"""
import json
import re

from .normalizar import clave
from .normalizar import texto as limpiar

TRAMOS = ["liberacion", "transito", "puerto", "ingreso", "tienda"]
MODOS = ["MARITIMO", "AEREO", "TERRESTRE"]
LINEA = re.compile(r"^\s*(\w+)\s*:\s*(.+?)\s*=\s*(\d+)\s*(bd|d)?\s*(?:\[(\w+)\])?\s*(?:\((\|\||start|(?:>|after)\s*\w+)\))?\s*$", re.I)


def cargar(v) -> list[dict]:
    try:
        r = json.loads(v or "[]")
        return r if isinstance(r, list) else []
    except (TypeError, ValueError):
        return []


def texto(pasos: list[dict]) -> str:
    partes = []
    for p in pasos:
        t = f"{p['tramo']}: {p['nombre']} = {p['dias']}{'bd' if p.get('habiles') else 'd'}"
        if p.get("modo"):
            t += f" [{p['modo']}]"
        if p.get("depende") == "INICIO":
            t += " (||)"
        elif p.get("depende"):
            t += f" (> {p['depende']})"
        partes.append(t)
    return "; ".join(partes)


def _de_texto(v: str) -> tuple[list[dict], list[str]]:
    pasos, errores = [], []
    for linea in [x for x in re.split(r"[;\n]+", v) if x.strip()]:
        m = LINEA.match(linea)
        if not m:
            errores.append(f"Step not understood: {limpiar(linea)}. Use stage: name = days(d|bd).")
            continue
        tramo, nombre, dias, unidad, modo, dep = m.groups()
        p = {"tramo": tramo.lower(), "nombre": nombre, "dias": int(dias), "habiles": (unidad or "").lower() == "bd",
             "modo": (modo or "").upper()}
        if dep:
            p["depende"] = "INICIO" if dep.lower() in ("start", "||") else re.sub(r"^(>|after)\s*", "", dep, flags=re.I)
        pasos.append(p)
    return pasos, errores


def validar(v) -> tuple[list[dict], list[str]]:
    """Normaliza la lista (JSON, lista o texto) y devuelve (pasos, errores)."""
    if isinstance(v, str):
        v = v.strip()
        if v.startswith("["):
            v = cargar(v)
        else:
            v, errores = _de_texto(v)
            if errores:
                return [], errores
    if not isinstance(v, list):
        return [], ["Steps: invalid value."]
    pasos, errores, codigos = [], [], []
    for i, p in enumerate(v, 1):
        if not isinstance(p, dict):
            errores.append(f"Step {i}: invalid value.")
            continue
        nombre = limpiar(p.get("nombre"))
        cod = clave(p.get("codigo") or nombre)[:12]
        if not nombre:
            errores.append(f"Step {i}: enter the name.")
            continue
        if cod in codigos:
            cod = f"{cod[:10]}{i}"
        tramo = str(p.get("tramo") or "").lower()
        if tramo not in TRAMOS:
            errores.append(f"Step {i} ({nombre}): choose the stage.")
        try:
            dias = int(p.get("dias"))
            if dias < 0 or dias > 365:
                raise ValueError
        except (TypeError, ValueError):
            errores.append(f"Step {i} ({nombre}): days between 0 and 365.")
            dias = 0
        modo = str(p.get("modo") or "").upper()
        if modo and modo not in MODOS:
            errores.append(f"Step {i} ({nombre}): invalid transport mode.")
        dep = str(p.get("depende") or "").upper()
        if dep and dep != "INICIO":
            dep = clave(dep)
            previos = [q["codigo"] for q in pasos if q["tramo"] == tramo]
            if dep not in previos:
                errores.append(f"Step {i} ({nombre}): it can only start after an earlier step of the same stage.")
        pasos.append({"codigo": cod, "nombre": nombre, "tramo": tramo, "dias": dias,
                      "habiles": bool(p.get("habiles")), "depende": dep, "modo": modo})
        codigos.append(cod)
    return pasos, errores
