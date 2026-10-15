"""Lo que cada empresa configura sin tocar el código: el nombre que le da a cada
campo y los que oculta al diseñar, y completar desde el trabajo el dato del
artículo que falta (en su maestro, con sus validaciones e historial)."""
from etiquetado_util import aprobada, articulo_de, oc_con_articulos, problemas, tipo, trabajo, uso

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion


def test_nombres_propios_y_campos_ocultos(interno, tnf):
    base = {c["clave"]: c for c in interno.get("/etiquetas/campos").json()["campos"]}
    assert base["articulo.upc"]["etiqueta"] == base["articulo.upc"]["etiqueta_original"] and not base["articulo.upc"]["oculto"]
    r = interno.put("/etiquetas/campos/propios", {"campos": {"articulo.upc": {"nombre": "Código de barras"},
                                                             "oc.incoterm": {"oculto": True}}})
    assert r.status_code == 200, r.text
    try:
        campos = {c["clave"]: c for c in interno.get("/etiquetas/campos").json()["campos"]}
        upc = campos["articulo.upc"]
        assert (upc["etiqueta"], upc["etiqueta_original"], upc["propio"]) == ("Código de barras", base["articulo.upc"]["etiqueta"], True)
        assert campos["oc.incoterm"]["oculto"] and not campos["oc.incoterm"]["propio"]
        # Un campo que no existe, un nombre demasiado largo y un proveedor: no
        assert interno.put("/etiquetas/campos/propios", {"campos": {"no.existe": {"nombre": "x"}}}).status_code == 422
        assert interno.put("/etiquetas/campos/propios", {"campos": {"articulo.upc": {"nombre": "x" * 61}}}).status_code == 422
        assert tnf.put("/etiquetas/campos/propios", {"campos": {}}).status_code == 403
    finally:
        assert interno.put("/etiquetas/campos/propios", {"campos": {}}).status_code == 200
    assert interno.get("/etiquetas/campos").json()["campos"][0]["propio"] is False


def test_completar_desde_el_trabajo_el_dato_del_articulo(interno, admin, tnf):
    """El diseño exige el SKU del proveedor y un artículo no lo tiene: se completa desde
    el trabajo, queda en su maestro (con historial) y el registro deja de tener el error."""
    from app.modelos import Articulo

    datos = oc_con_articulos(interno)
    linea = datos["lineas"][0]
    aid = articulo_de(linea["id"])
    with SessionLocal() as db, en_organizacion(1):
        antes = db.get(Articulo, aid).sku_proveedor
    assert interno.patch(f"/catalogos/articulos/{aid}", {"sku_proveedor": None}).status_code == 200
    t_ = tipo(interno, "COMPLETAR")
    d = aprobada(interno, admin, "Supplier SKU required", t_["id"],
                 [{"id": "s", "tipo": "campo", "campo": "articulo.sku_proveedor", "si_vacio": "error", "x": 3, "y": 3, "w": 60, "h": 8}])
    u = uso(interno, t_["id"], d["id"])
    try:
        tr = trabajo(interno, "OC", {"oc_ids": [datos["oc"]["id"]], "posiciones": [linea["id"]], "tipos": [t_["id"]]})
        reg = next(r for r in tr["registros"] if r["tipo_etiqueta_id"] == t_["id"])
        assert reg["estado"] == "ERROR" and "campo_obligatorio" in problemas(reg)
        assert any(p.get("campo") == "articulo.sku_proveedor" for p in reg["problemas"])
        # Solo datos del artículo que no lo identifican, solo artículos a los que les falta, y con permiso
        assert interno.post(f"/etiquetas/trabajos/{tr['id']}/completar",
                            {"campo": "articulo.sku", "valores": {str(aid): "X"}}).status_code == 422
        assert interno.post(f"/etiquetas/trabajos/{tr['id']}/completar",
                            {"campo": "articulo.sku_proveedor", "valores": {"999999": "X"}}).status_code == 422
        assert tnf.post(f"/etiquetas/trabajos/{tr['id']}/completar",
                        {"campo": "articulo.sku_proveedor", "valores": {str(aid): "X"}}).status_code in (403, 404)
        r = interno.post(f"/etiquetas/trabajos/{tr['id']}/completar", {"campo": "articulo.sku_proveedor", "valores": {str(aid): "PROV-777"}})
        assert r.status_code == 200, r.text
        reg = next(x for x in r.json()["registros"] if x["tipo_etiqueta_id"] == t_["id"])
        assert reg["estado"] != "ERROR" and "campo_obligatorio" not in problemas(reg)
        with SessionLocal() as db, en_organizacion(1):
            assert db.get(Articulo, aid).sku_proveedor == "PROV-777"
        h = interno.get(f"/catalogos/articulos/{aid}/historial").json()
        assert any(x.get("accion") == "editar" for x in (h if isinstance(h, list) else h.get("items", [])))
    finally:
        interno.patch(f"/catalogos/articulos/{aid}", {"sku_proveedor": antes})
        interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "Test done"})
        version = next(x for x in interno.get("/etiquetas/tipos", params={"todos": True}).json() if x["id"] == t_["id"])["version"]
        interno.patch(f"/etiquetas/tipos/{t_['id']}", {"activo": False, "version": version})
