"""Etiquetado: familias propias de la empresa (independientes de la
clasificación arancelaria), su asignación a los artículos y el catálogo de
campos dinámicos con su origen."""


def _familia(api, codigo, nombre, **kw):
    r = api.post("/etiquetas/familias", {"codigo": codigo, "nombre": nombre, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_crear_modificar_desactivar_y_ordenar(interno):
    calzado = _familia(interno, "calzado", "Footwear", campos=[{"campo": "articulo.talla", "obligatorio": True},
                                                               {"campo": "articulo.estilo"}])
    assert calzado["codigo"] == "CALZADO" and calzado["activa"] and calzado["campos"] == [
        {"campo": "articulo.talla", "obligatorio": True}, {"campo": "articulo.estilo", "obligatorio": False}]
    quim = _familia(interno, "QUIMICOS", "Chemicals", descripcion="Cleaning products")
    # Código único, campos que existan y solo del artículo o producto
    assert interno.post("/etiquetas/familias", {"codigo": "CALZADO", "nombre": "x"}).status_code == 422
    assert interno.post("/etiquetas/familias", {"codigo": "X1", "nombre": "x", "campos": [{"campo": "articulo.inventado"}]}).status_code == 422
    assert interno.post("/etiquetas/familias", {"codigo": "X2", "nombre": "x", "campos": [{"campo": "oc.numero"}]}).status_code == 422
    r = interno.patch(f"/etiquetas/familias/{quim['id']}", {"nombre": "Chemical products", "activa": False})
    assert r.status_code == 200 and r.json()["nombre"] == "Chemical products" and not r.json()["activa"]
    todas = interno.get("/etiquetas/familias").json()
    ids = [f["id"] for f in todas]
    r = interno.put("/etiquetas/familias/orden", {"ids": list(reversed(ids))})
    assert r.status_code == 200 and [f["id"] for f in r.json()] == list(reversed(ids))
    assert quim["id"] not in {f["id"] for f in interno.get("/etiquetas/familias", params={"activas": True}).json()}
    # El cambio queda en la bitácora
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import Historial

    with SessionLocal() as db, en_organizacion(1):
        acciones = {h.accion for h in db.query(Historial).filter(Historial.entidad == "familia_etiquetado", Historial.entidad_id == quim["id"])}
    assert {"crear", "editar"} <= acciones


def test_asignar_familia_a_articulos_sin_tocar_la_clasificacion(interno):
    ropa = _familia(interno, "ROPA", "Apparel")
    sin = interno.get("/etiquetas/articulos", params={"familia": "sin", "size": 5}).json()
    assert sin["total"] > 0
    elegidos = [a["id"] for a in sin["items"][:3]]
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import Articulo

    with SessionLocal() as db, en_organizacion(1):
        p = db.get(Articulo, elegidos[0]).producto
        clasif = p.codigo if p else None
    r = interno.post("/etiquetas/articulos/familia", {"familia_id": ropa["id"], "ids": elegidos})
    assert r.status_code == 200 and r.json()["cambiados"] == 3
    con = interno.get("/etiquetas/articulos", params={"familia": ropa["id"]}).json()
    assert {a["id"] for a in con["items"]} == set(elegidos) and all(a["familia"] == "Apparel" for a in con["items"])
    solo = interno.get("/etiquetas/articulos", params={"ids": ",".join(map(str, elegidos[:2]))}).json()
    assert {a["id"] for a in solo["items"]} == set(elegidos[:2])
    assert interno.get("/etiquetas/articulos", params={"ids": "1;DROP"}).status_code == 422
    assert next(f for f in interno.get("/etiquetas/familias").json() if f["id"] == ropa["id"])["articulos"] == 3
    # En uso no se borra: se desactiva
    assert interno.delete_(f"/etiquetas/familias/{ropa['id']}").status_code == 409
    # Quitarla (familia vacía) y luego sí se puede borrar
    assert interno.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": elegidos}).json()["cambiados"] == 3
    assert interno.delete_(f"/etiquetas/familias/{ropa['id']}").status_code == 200
    # Por filtro: todos los de un estilo
    acc = _familia(interno, "ACCESORIOS", "Accessories")
    estilo = sin["items"][0]["estilo"]
    r = interno.post("/etiquetas/articulos/familia", {"familia_id": acc["id"], "filtro": {"q": estilo}})
    assert r.status_code == 200 and r.json()["cambiados"] >= 1
    # La clasificación arancelaria del producto no cambia ni se usa
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import Articulo

    with SessionLocal() as db, en_organizacion(1):
        a = db.get(Articulo, elegidos[0])
        assert a.familia_etiquetado_id == acc["id"] and (a.producto is None or a.producto.codigo == clasif)

def test_permisos_y_proveedor(tnf, interno):
    assert tnf.post("/etiquetas/familias", {"codigo": "TNFX", "nombre": "x"}).status_code == 403
    # Un proveedor ve las familias y solo sus artículos
    assert tnf.get("/etiquetas/familias").status_code == 200
    propios = tnf.get("/etiquetas/articulos", params={"size": 200}).json()
    todos = interno.get("/etiquetas/articulos", params={"size": 200}).json()
    assert 0 < propios["total"] < todos["total"]
    assert tnf.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [todos["items"][0]["id"]]}).status_code == 403


def test_campos_con_origen_y_por_modalidad(interno, tnf):
    r = interno.get("/etiquetas/campos").json()
    claves = {c["clave"]: c for c in r["campos"]}
    assert claves["articulo.talla"]["origen"] == "articulos.talla" and claves["oc.numero"]["origen"] == "ordenes_compra.numero"
    assert claves["organizacion.logo"]["tipo"] == "imagen" and "linea.precio" in claves
    articulo = {c["clave"] for c in interno.get("/etiquetas/campos", params={"modalidad": "ARTICULO"}).json()["campos"]}
    assert "articulo.sku" in articulo and not any(k.startswith(("oc.", "linea.", "bulto.")) for k in articulo)
    oc = {c["clave"] for c in interno.get("/etiquetas/campos", params={"modalidad": "OC"}).json()["campos"]}
    assert "oc.numero" in oc and "bulto.numero" in oc and not any(k.startswith("articulo.") for k in oc)
    # Los atributos de variante propios (no talla ni color, que son columnas) aparecen como campos
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import AtributoVariante

    with SessionLocal() as db, en_organizacion(1):
        propios = [a.codigo for a in db.query(AtributoVariante).filter(AtributoVariante.columna.is_(None), AtributoVariante.activo.is_(True))]
        sistema = [a.codigo for a in db.query(AtributoVariante).filter(AtributoVariante.columna.is_not(None))]
    assert all(f"articulo.atributo.{c}" in claves for c in propios)
    assert not any(f"articulo.atributo.{c}" in claves for c in sistema)
