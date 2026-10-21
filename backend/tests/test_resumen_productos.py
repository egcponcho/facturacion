"""Resumen del módulo de productos y filtro del catálogo por familia (con sus
subfamilias): las cifras del resumen abren el catálogo con ese filtro."""
from test_alta_producto import _borrar, _cat


def test_resumen_y_filtro_por_familia(interno, admin, vans):
    base = _cat(interno, "articulos", tipo="SOLIDO")[0]
    fam = admin.post("/grupos-producto", {"codigo": "RES-FAM", "nombre": "Summary family"}).json()
    sub = admin.post("/grupos-producto", {"codigo": "RES-SUB", "nombre": "Summary sub", "padre_id": fam["id"]}).json()
    antes = interno.get("/productos/resumen").json()
    try:
        r = interno.post("/catalogos/genericos", {
            "generico": "RESUM01", "nombre": "Summary product", "marca_id": base["marca_id"], "grupo_id": base["grupo_id"],
            "proveedor_id": base["proveedor_id"], "unidad": "UN", "grupo_producto_id": sub["id"],
            "tallas": [{"valores": {"TALLA": "7"}}, {"valores": {"TALLA": "8"}, "upc": "012345678905"}]})
        assert r.status_code == 200, r.text
        res = interno.get("/productos/resumen").json()
        assert res["total"] == antes["total"] + 1 and res["variantes"] == antes["variantes"] + 2
        assert res["sin_codigo_barras"] == antes["sin_codigo_barras"] + 1
        assert sum(res["por_estado"].values()) == res["total"]
        assert any(f["id"] == sub["id"] and f["productos"] == 1 for f in res["por_familia"])
        assert res["recientes"][0]["codigo"] == "RESUM01" and res["recientes"][0]["familia"] == "Summary sub"
        assert res["configuracion"]["familias"] >= 2
        # La familia de arriba incluye los productos de sus subfamilias
        for f in (fam["id"], sub["id"]):
            items = interno.get("/productos", params={"familia": f}).json()["items"]
            assert [p["codigo_generico"] for p in items] == ["RESUM01"]
        otra = admin.post("/grupos-producto", {"codigo": "RES-OTRA", "nombre": "Other"}).json()
        assert interno.get("/productos", params={"familia": otra["id"]}).json()["items"] == []
        # El proveedor ve el resumen de lo suyo, sin la puesta en marcha
        rv = vans.get("/productos/resumen")
        assert rv.status_code == 200 and rv.json()["configuracion"] is None
    finally:
        _borrar("RESUM01")
