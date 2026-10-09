"""Integración genérica con artículos y documentos: unidades de cualquier
familia, documentos con las etiquetas del catálogo y aprobación que no exige
líneas nacionales (los documentos usan la subpartida de 6 dígitos)."""
import re

from test_oficial import RAIZ


def test_units_are_one_list_in_server_and_screens():
    from app.modulos.maestros.unidades import CODIGOS, DE_ARTICULO, normalizar

    js = (RAIZ.parent / "frontend" / "src" / "unidades.js").read_text(encoding="utf-8")
    bloque = js[js.index("export const UNIDADES = {"):js.index("}\n", js.index("export const UNIDADES = {"))]
    assert re.findall(r"^\s+(\w+):", bloque, re.M) == CODIGOS
    assert "CJ" not in DE_ARTICULO and {"KG", "L", "M", "DOC"} <= set(DE_ARTICULO)
    assert normalizar("pcs") == "UN" and normalizar("Kgs") == "KG" and normalizar("LTS") == "L" and normalizar("xyz") is None


def test_items_accept_units_of_any_family(interno):
    m = {x["codigo"]: x["id"] for x in interno.get("/catalogos/marcas", params={"size": 100}).json()["items"]}
    g = {x["codigo"]: x["id"] for x in interno.get("/catalogos/grupos").json()["items"]}
    pv = {x["codigo"]: x["id"] for x in interno.get("/catalogos/proveedores").json()["items"]}
    base = {"estilo": "CHEMKG01", "color": "Clear", "marca_id": m["VANS"], "grupo_id": next(iter(g.values())), "proveedor_id": pv["VANS"],
            "nombre": "Citric acid 25 kg bag", "tallas": [{"talla": "25"}]}
    r = interno.post("/catalogos/genericos", {**base, "generico": "30077801", "unidad": "XX"})
    assert r.status_code == 422 and "unit" in r.text.lower()
    r = interno.post("/catalogos/genericos", {**base, "generico": "30077801", "unidad": "KG"})
    assert r.status_code == 200, r.text


def test_sheet_documents_use_catalog_labels():
    from app.modulos.documentos.documentos import secciones_ficha

    d = {"ficha": {"comp": {"cuerpo": "100% porcelain"}, "foo_attr": "a", "flag_x": True}, "tipo": "taza",
         "etiquetas": {"partes": {"cuerpo": "Body"}, "campos": {"foo_attr": "Foo", "flag_x": "Has a lid"},
                       "valores": {"foo_attr": {"a": "Alpha"}}, "tipos": {"taza": "Mug"}, "paises": ["PA", "GT"]},
         "partidas": {"GT": {"codigo": "6912000000", "estado": "ok"}, "PA": {"codigo": "691200000000", "estado": "historial"}}}
    x = secciones_ficha(d)
    assert x["composicion"] == [["Body", "100% porcelain"]]
    assert ("Foo", "Alpha") in x["datos"] and ("Has a lid", "Yes") in x["datos"] and ("Product type", "Mug") in x["datos"]
    assert [p[0] for p in x["partidas"]] == ["PA", "GT"]  # el orden de los países configurado
    assert x["partidas"][0][3] == "Suggested by history"
