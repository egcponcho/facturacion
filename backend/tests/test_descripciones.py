"""Paridad de las descripciones aduanera y comercial con las que armaba el antiguo clasificador del navegador
(tests/paridad/descripciones.json); salen de datos (plantillas y textos de aduana)."""
import json
from pathlib import Path

import pytest

from app.services.descripciones import descripcion_aduana, descripcion_comercial
from app.services.ficha import Catalogo

# El catálogo del motor más el conocimiento de la empresa de ejemplo: los nombres
# de sus modelos («old skool» es un tenis) son palabras clave de la empresa, no
# patrones del motor
_PALABRAS = [{"frase": x["frase"], "tipo": x["tipo"], "marca": x.get("marca"), **x["atributos"]}
             for x in json.loads((Path(__file__).parents[1] / "app/data/demo/palabras_empresa_demo.json").read_text(encoding="utf-8"))]
_BASE = Catalogo.desde_json()
CAT = Catalogo(_BASE.atributos, list(_BASE.categorias.values()), palabras=_PALABRAS, clases=_BASE.clases)
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
