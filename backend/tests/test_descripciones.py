"""Paridad de las descripciones aduanera y comercial con las que armaba motor.js
(tests/paridad/descripciones.json); salen de datos (plantillas y textos de aduana)."""
import json
from pathlib import Path

import pytest

from app.services.descripciones import descripcion_aduana, descripcion_comercial
from app.services.ficha import Catalogo

CAT = Catalogo.desde_json()
CASOS = json.loads((Path(__file__).parent / "paridad/descripciones.json").read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("i", range(len(CASOS)))
def test_paridad_descripciones(i):
    c = CASOS[i]
    e = c["entrada"]
    ficha = {k: v for k, v in e.items() if k not in ("tipo", "comp", "marca") and v is not None}
    ficha["comp"] = e.get("comp") or {}
    s = CAT.hechos_base(ficha, e["tipo"])
    CAT.normalizar(s)
    cobj = CAT.categorias[e["tipo"]]
    assert descripcion_aduana(CAT, s, cobj) == c["aduana"]
    assert descripcion_comercial(CAT, s, cobj, e.get("marca")) == c["comercial"]
