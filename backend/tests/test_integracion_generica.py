"""Integración genérica con artículos y documentos: unidades de cualquier
familia, documentos con las etiquetas del catálogo y aprobación que no exige
líneas nacionales (los documentos usan la subpartida de 6 dígitos)."""


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
