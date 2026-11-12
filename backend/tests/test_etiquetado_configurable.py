"""Lo que cada empresa configura sin tocar el código: el nombre que le da a cada
campo y los que oculta al diseñar, y completar desde el trabajo el dato del
artículo que falta (en su maestro, con sus validaciones e historial)."""
from etiquetado_util import aprobada, articulo_de, oc_con_articulos, problemas, tipo, trabajo, uso

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion


def test_nombres_propios_y_campos_ocultos(interno, tnf):
    base = {c["clave"]: c for c in interno.get("/etiquetas/campos").json()["campos"]}
    assert base["articulo.codigo_barras"]["etiqueta"] == base["articulo.codigo_barras"]["etiqueta_original"] and not base["articulo.codigo_barras"]["oculto"]
    r = interno.put("/etiquetas/campos/propios", {"campos": {"articulo.codigo_barras": {"nombre": "Código de barras"},
                                                             "oc.incoterm": {"oculto": True}}})
    assert r.status_code == 200, r.text
    try:
        campos = {c["clave"]: c for c in interno.get("/etiquetas/campos").json()["campos"]}
        upc = campos["articulo.codigo_barras"]
        assert (upc["etiqueta"], upc["etiqueta_original"], upc["propio"]) == ("Código de barras", base["articulo.codigo_barras"]["etiqueta"], True)
        assert campos["oc.incoterm"]["oculto"] and not campos["oc.incoterm"]["propio"]
        # Un campo que no existe, un nombre demasiado largo y un proveedor: no
        assert interno.put("/etiquetas/campos/propios", {"campos": {"no.existe": {"nombre": "x"}}}).status_code == 422
        assert interno.put("/etiquetas/campos/propios", {"campos": {"articulo.codigo_barras": {"nombre": "x" * 61}}}).status_code == 422
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
        antes = db.get(Articulo, aid).codigo_proveedor
    assert interno.patch(f"/catalogos/articulos/{aid}", {"codigo_proveedor": None}).status_code == 200
    t_ = tipo(interno, "COMPLETAR")
    d = aprobada(interno, admin, "Supplier SKU required", t_["id"],
                 [{"id": "s", "tipo": "campo", "campo": "articulo.codigo_proveedor", "si_vacio": "error", "x": 3, "y": 3, "w": 60, "h": 8}])
    u = uso(interno, t_["id"], d["id"])
    try:
        tr = trabajo(interno, "OC", {"oc_ids": [datos["oc"]["id"]], "posiciones": [linea["id"]], "tipos": [t_["id"]]})
        reg = next(r for r in tr["registros"] if r["tipo_etiqueta_id"] == t_["id"])
        assert reg["estado"] == "ERROR" and "campo_obligatorio" in problemas(reg)
        assert any(p.get("campo") == "articulo.codigo_proveedor" for p in reg["problemas"])
        # Solo datos del artículo que no lo identifican, solo artículos a los que les falta, y con permiso
        assert interno.post(f"/etiquetas/trabajos/{tr['id']}/completar",
                            {"campo": "articulo.sku", "valores": {str(aid): "X"}}).status_code == 422
        assert interno.post(f"/etiquetas/trabajos/{tr['id']}/completar",
                            {"campo": "articulo.codigo_proveedor", "valores": {"999999": "X"}}).status_code == 422
        assert tnf.post(f"/etiquetas/trabajos/{tr['id']}/completar",
                        {"campo": "articulo.codigo_proveedor", "valores": {str(aid): "X"}}).status_code in (403, 404)
        r = interno.post(f"/etiquetas/trabajos/{tr['id']}/completar", {"campo": "articulo.codigo_proveedor", "valores": {str(aid): "PROV-777"}})
        assert r.status_code == 200, r.text
        reg = next(x for x in r.json()["registros"] if x["tipo_etiqueta_id"] == t_["id"])
        assert reg["estado"] != "ERROR" and "campo_obligatorio" not in problemas(reg)
        with SessionLocal() as db, en_organizacion(1):
            assert db.get(Articulo, aid).codigo_proveedor == "PROV-777"
        h = interno.get(f"/catalogos/articulos/{aid}/historial").json()
        assert any(x.get("accion") == "editar" for x in (h if isinstance(h, list) else h.get("items", [])))
    finally:
        interno.patch(f"/catalogos/articulos/{aid}", {"codigo_proveedor": antes})
        interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "Test done"})
        version = next(x for x in interno.get("/etiquetas/tipos", params={"todos": True}).json() if x["id"] == t_["id"])["version"]
        interno.patch(f"/etiquetas/tipos/{t_['id']}", {"activo": False, "version": version})


def test_trabajo_desactualizado_avisa_antes_de_generar(interno, admin):
    """Si lo que se va a imprimir cambia entre la revisión y la generación (aquí, el SKU del
    proveedor del artículo), generar responde 409 con qué cambió en vez de imprimir algo
    distinto de lo revisado; un cambio en un dato que el diseño no imprime no frena nada.
    Revisar de nuevo (o aceptar los cambios) permite generar."""
    from app.modelos import Articulo

    datos = oc_con_articulos(interno)
    linea = datos["lineas"][0]
    aid = articulo_de(linea["id"])
    with SessionLocal() as db, en_organizacion(1):
        a = db.get(Articulo, aid)
        antes_sku, antes_peso = a.codigo_proveedor, a.peso_unitario
    assert interno.patch(f"/catalogos/articulos/{aid}", {"codigo_proveedor": "REV-1"}).status_code == 200
    t_ = tipo(interno, "DESACTUALIZADO")
    d = aprobada(interno, admin, "Supplier SKU printed", t_["id"],
                 [{"id": "s", "tipo": "campo", "campo": "articulo.codigo_proveedor", "x": 3, "y": 3, "w": 60, "h": 8}])
    u = uso(interno, t_["id"], d["id"])
    try:
        tr = trabajo(interno, "OC", {"oc_ids": [datos["oc"]["id"]], "posiciones": [linea["id"]], "tipos": [t_["id"]]})
        # Un dato que el diseño no imprime: no frena
        assert interno.patch(f"/catalogos/articulos/{aid}", {"peso_unitario": (antes_peso or 0) + 1}).status_code == 200
        # El que imprime: 409 con antes y después
        assert interno.patch(f"/catalogos/articulos/{aid}", {"codigo_proveedor": "REV-2"}).status_code == 200
        r = interno.post(f"/etiquetas/trabajos/{tr['id']}/generar", {"formato": "PDF", "version": tr["version"], "aceptar_advertencias": True})
        assert r.status_code == 409 and r.json()["codigo"] == "datos_cambiaron", r.text
        assert "articulo.codigo_proveedor: REV-1 → REV-2" in r.json()["detalle"][0]["mensaje"]
        # El 409 no cambia el trabajo: sigue con lo revisado hasta revisarlo de nuevo
        tr = interno.get(f"/etiquetas/trabajos/{tr['id']}").json()
        r = interno.post(f"/etiquetas/trabajos/{tr['id']}/generar", {"formato": "PDF", "version": tr["version"], "aceptar_advertencias": True})
        assert r.status_code == 409
        # Aceptar los cambios genera con los datos nuevos
        r = interno.post(f"/etiquetas/trabajos/{tr['id']}/generar", {"formato": "PDF", "version": tr["version"], "aceptar_advertencias": True,
                                                                     "aceptar_cambios": True})
        assert r.status_code == 200, r.text
        # Otro trabajo: revisar de nuevo también deja generar sin aceptar nada
        tr = trabajo(interno, "OC", {"oc_ids": [datos["oc"]["id"]], "posiciones": [linea["id"]], "tipos": [t_["id"]]})
        assert interno.patch(f"/catalogos/articulos/{aid}", {"codigo_proveedor": "REV-3"}).status_code == 200
        tr = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
        r = interno.post(f"/etiquetas/trabajos/{tr['id']}/generar", {"formato": "PDF", "version": tr["version"], "aceptar_advertencias": True})
        assert r.status_code in (200, 409) and r.json().get("codigo") != "datos_cambiaron", r.text
    finally:
        interno.patch(f"/catalogos/articulos/{aid}", {"codigo_proveedor": antes_sku, "peso_unitario": antes_peso})
        interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "Test done"})
        version = next(x for x in interno.get("/etiquetas/tipos", params={"todos": True}).json() if x["id"] == t_["id"])["version"]
        interno.patch(f"/etiquetas/tipos/{t_['id']}", {"activo": False, "version": version})
