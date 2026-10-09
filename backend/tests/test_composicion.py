"""Paridad de la lectura de composiciones: app/modulos/clasificacion/composicion.py frente a
lo que devolvía el antiguo clasificador del navegador (tests/paridad/composicion.json,
casos fijados al retirarlo: son la referencia de regresión)."""
import json
from pathlib import Path

import pytest

from app.modulos.clasificacion.composicion import Lector

DATOS = json.loads((Path(__file__).parent / "paridad/composicion.json").read_text(encoding="utf-8"))
L = Lector(DATOS["sinonimos"])


def _igual(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_igual(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_igual(x, y) for x, y in zip(a, b, strict=False))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) < 1e-9
    return a == b


@pytest.mark.parametrize("caso", DATOS["casos"], ids=lambda c: c["txt"][:40] or "vacio")
def test_paridad_lectura(caso):
    txt = caso["txt"]
    pr = L.prep(txt)
    assert _igual({k: pr[k] for k in ("s", "cambios", "desconocidas", "ambiguas")}, caso["prep"])
    pc = L.parse_comp(txt)
    esperado = caso["comp"]
    if esperado:
        esperado = {**esperado, "pred": {("mezcla_mm" if k == "mezclaMM" else k): v for k, v in esperado["pred"].items()}}
    assert _igual(pc, esperado)
    for modo in ("corte", "suela"):
        pm = L.parse_mat(txt, modo)
        assert _igual(pm and {"pesos": pm["pesos"], "pred": pm["pred"], "mixto": bool(pm.get("mixto")), "grupos": pm.get("grupos")}, caso[modo]), modo
    cm = L.clase_mat(txt)
    assert _igual(cm and {k: cm[k] for k in ("pred", "corrugado", "aluminio")}, caso["clase"])
    ct = L.clase_texto(txt)
    assert (ct and ct["clase"]) == caso["clase_texto"]
    assert L.filas(txt) == caso["filas"]
