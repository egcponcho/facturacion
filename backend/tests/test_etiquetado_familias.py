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
    sin = interno.get("/etiquetas/articulos", params={"size": 5}).json()
    assert sin["total"] >= 3
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
    # Se deja como estaba: los artículos vuelven a la familia de su producto o su grupo
    todos = interno.get("/etiquetas/articulos", params={"familia": acc["id"], "size": 200}).json()["items"]
    interno.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [x["id"] for x in todos]})

def test_permisos_y_proveedor(tnf, interno):
    assert tnf.post("/etiquetas/familias", {"codigo": "TNFX", "nombre": "x"}).status_code == 403
    # Un proveedor ve las familias y solo sus artículos
    assert tnf.get("/etiquetas/familias").status_code == 403  # la configuración es del equipo interno
    propios = tnf.get("/etiquetas/articulos", params={"size": 200}).json()
    todos = interno.get("/etiquetas/articulos", params={"size": 200}).json()
    assert 0 < propios["total"] < todos["total"]
    assert tnf.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [todos["items"][0]["id"]]}).status_code == 403


def test_campos_con_origen_y_por_sujeto(interno, tnf):
    r = interno.get("/etiquetas/campos").json()
    claves = {c["clave"]: c for c in r["campos"]}
    assert claves["articulo.talla"]["origen"] == "articulos.talla" and claves["oc.numero"]["origen"] == "ordenes_compra.numero"
    assert claves["organizacion.logo"]["tipo"] == "imagen" and "linea.precio" in claves
    # Lo que puede llevar cada cosa que se etiqueta: el artículo (con su OC si viene de una), el bulto, el documento
    articulo = {c["clave"] for c in interno.get("/etiquetas/campos", params={"sujeto": "ARTICULO"}).json()["campos"]}
    assert {"articulo.sku", "oc.numero", "linea.cantidad"} <= articulo and not any(k.startswith(("bulto.", "pl.")) for k in articulo)
    bulto = {c["clave"] for c in interno.get("/etiquetas/campos", params={"sujeto": "BULTO"}).json()["campos"]}
    assert {"bulto.numero", "bulto.mixto", "pl.numero", "oc.numero"} <= bulto
    doc = {c["clave"] for c in interno.get("/etiquetas/campos", params={"sujeto": "DOCUMENTO"}).json()["campos"]}
    assert "oc.numero" in doc and not any(k.startswith(("articulo.", "bulto.", "linea.")) for k in doc)
    colecciones = {c["clave"] for c in interno.get("/etiquetas/campos", params={"sujeto": "DOCUMENTO"}).json()["colecciones"]}
    assert "oc.lineas" in colecciones and "bulto.lineas" not in colecciones
    # Los atributos de variante propios (no talla ni color, que son columnas) aparecen como campos
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import AtributoVariante

    with SessionLocal() as db, en_organizacion(1):
        propios = [a.codigo for a in db.query(AtributoVariante).filter(AtributoVariante.columna.is_(None), AtributoVariante.activo.is_(True))]
        sistema = [a.codigo for a in db.query(AtributoVariante).filter(AtributoVariante.columna.is_not(None))]
    assert all(f"articulo.atributo.{c}" in claves for c in propios)
    assert not any(f"articulo.atributo.{c}" in claves for c in sistema)


def test_familia_por_grupos_de_articulos_y_prioridad_del_articulo(interno, tnf):
    """Una familia toma grupos de artículos completos (varios a la vez); el
    artículo con familia propia la conserva."""
    textil = _familia(interno, "TEXTIL", "Textiles")
    otra = _familia(interno, "ESPECIAL", "Special")
    grupos = interno.get("/etiquetas/grupos-articulos").json()
    antes = {g["id"]: g["familia_id"] for g in grupos}
    con_articulos = sorted((g for g in grupos if g["articulos"] > 0), key=lambda g: g["con_familia_propia"] - g["articulos"])
    assert len(con_articulos) >= 2
    elegidos = con_articulos[:2]
    ids = [g["id"] for g in elegidos]
    assert tnf.post("/etiquetas/grupos-articulos/familia", {"familia_id": textil["id"], "grupo_ids": ids}).status_code == 403
    r = interno.post("/etiquetas/grupos-articulos/familia", {"familia_id": textil["id"], "grupo_ids": ids})
    assert r.status_code == 200 and r.json()["elegidos"] == 2, r.text
    assert {g["id"] for g in interno.get("/etiquetas/grupos-articulos", params={"familia": textil["id"]}).json()} == set(ids)
    # Sus artículos la heredan del grupo
    del_grupo = interno.get("/etiquetas/articulos", params={"grupo_id": ids[0], "size": 200}).json()["items"]
    assert del_grupo and all(a["familia_id"] == textil["id"] and a["familia_origen"] == "GRUPO" for a in del_grupo
                             if not a["familia_propia_id"])
    total = sum(g["articulos"] - g["con_familia_propia"] for g in elegidos)
    en_familia = interno.get("/etiquetas/articulos", params={"familia": textil["id"], "size": 1}).json()["total"]
    assert en_familia == total
    # Un artículo con familia propia la conserva aunque su grupo tenga otra
    propio = next(a for a in del_grupo if not a["familia_propia_id"])
    interno.post("/etiquetas/articulos/familia", {"familia_id": otra["id"], "ids": [propio["id"]]})
    a = interno.get("/etiquetas/articulos", params={"ids": str(propio["id"])}).json()["items"][0]
    assert a["familia_id"] == otra["id"] and a["familia_origen"] == "ARTICULO"
    assert interno.get("/etiquetas/articulos", params={"familia": textil["id"], "size": 1}).json()["total"] == en_familia - 1
    eleccion = interno.get("/etiquetas/resolver", params={"sujeto": "ARTICULO", "articulo_id": propio["id"]}).json()
    assert eleccion["elecciones"] and all(e["porque"].get("destino") != "Textiles" for e in eleccion["elecciones"])
    f = next(x for x in interno.get("/etiquetas/familias").json() if x["id"] == textil["id"])
    assert f["grupos"] == 2 and f["articulos"] == en_familia - 1
    # Una familia con grupos está en uso: no se borra
    assert interno.delete_(f"/etiquetas/familias/{textil['id']}").status_code == 409
    # Quitar la familia de un grupo
    r = interno.post("/etiquetas/grupos-articulos/familia", {"familia_id": None, "grupo_ids": [ids[1]]})
    assert r.json()["cambiados"] == 1
    assert next(x for x in interno.get("/etiquetas/familias").json() if x["id"] == textil["id"])["grupos"] == 1
    # Dejar todo como estaba para las demás pruebas
    for gid in ids:
        interno.post("/etiquetas/grupos-articulos/familia", {"familia_id": antes[gid], "grupo_ids": [gid]})
    interno.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [propio["id"]]})


def test_familia_del_producto_la_heredan_sus_tallas(interno, tnf):
    """La familia se pone al producto (estilo-color): sus tallas la heredan salvo
    las que tienen la suya; un producto con familia propia no se borra de ella."""
    fam = _familia(interno, "PRODFAM", "Product family")
    prods = interno.get("/etiquetas/productos", params={"size": 200}).json()["items"]
    p = next(x for x in prods if x["tallas"] >= 2)
    assert tnf.post("/etiquetas/productos/familia", {"familia_id": fam["id"], "ids": [p["id"]]}).status_code == 403
    r = interno.post("/etiquetas/productos/familia", {"familia_id": fam["id"], "ids": [p["id"]]})
    assert r.status_code == 200, r.text
    tallas = interno.get("/etiquetas/articulos", params={"producto_id": p["id"], "size": 200}).json()["items"]
    assert tallas and all(a["familia_id"] == fam["id"] and a["familia_origen"] == "PRODUCTO" for a in tallas if not a["familia_propia_id"])
    x = next(y for y in interno.get("/etiquetas/productos", params={"familia": fam["id"]}).json()["items"] if y["id"] == p["id"])
    assert x["familia_propia_id"] == fam["id"]
    assert interno.delete_(f"/etiquetas/familias/{fam['id']}").status_code == 409
    interno.post("/etiquetas/productos/familia", {"familia_id": p["familia_propia_id"], "ids": [p["id"]]})


def test_asistente_de_familia_se_termina_de_una_vez_o_no_cambia_nada(interno, admin, tnf):
    """El asistente guarda borradores personales sin tocar la configuración;
    al terminar crea la familia, le pone productos/grupos/artículos y su diseño
    por tipo en una sola operación (si algo falla, no queda nada a medias)."""
    from tests.etiquetado_util import aprobada, tipo

    t = tipo(interno, "ASIS_TAG")
    p = aprobada(interno, admin, "Wizard tag", t["id"], [{"id": "t1", "tipo": "texto", "x": 2, "y": 2, "w": 40, "h": 8, "contenido": "x"}])
    prods = interno.get("/etiquetas/productos", params={"size": 200}).json()["items"]
    prod = prods[0]
    # Borrador: personal, no cambia nada
    borr = {"titulo": "Wizard", "datos": {"paso": 2, "familia": {"codigo": "WIZ", "nombre": "Wizard"}, "productos": [prod["id"]]}}
    r = interno.put("/perfil/borradores/etiquetas.familia.nueva", borr)
    assert r.status_code == 200 and r.json()["datos"]["paso"] == 2, r.text
    assert "WIZ" not in {f["codigo"] for f in interno.get("/etiquetas/familias").json()}
    assert [b["clave"] for b in interno.get("/perfil/borradores", params={"prefijo": "etiquetas."}).json()] == ["etiquetas.familia.nueva"]
    assert tnf.get("/perfil/borradores").json() == []
    assert "borradores" not in interno.get("/auth/me").json()["preferencias"]
    assert interno.put("/perfil/borradores/Mal Nombre", borr).status_code == 422
    # Si algo falla (un producto que no existe) no se crea la familia
    malo = {"familia": {"codigo": "WIZ", "nombre": "Wizard"}, "productos": [prod["id"], 999999],
            "disenos": [{"tipo_etiqueta_id": t["id"], "plantilla_id": p["id"]}]}
    assert interno.post("/etiquetas/familias/configurar", malo).status_code == 404
    assert "WIZ" not in {f["codigo"] for f in interno.get("/etiquetas/familias").json()}
    # Sin permiso de configurar etiquetas, nada
    assert tnf.post("/etiquetas/familias/configurar", {**malo, "productos": [prod["id"]]}).status_code == 403
    # Bien: familia, producto y diseño de una vez
    r = interno.post("/etiquetas/familias/configurar", {**malo, "productos": [prod["id"]]})
    assert r.status_code == 200, r.text
    fam = r.json()["familia"]
    assert fam["codigo"] == "WIZ" and r.json()["hecho"]["productos"] == 1 and r.json()["hecho"]["disenos"] == 1
    # La familia cuenta su producto (el conteo recorre los productos, no una sola fila)
    assert fam["productos"] == 1
    assert next(f for f in interno.get("/etiquetas/familias").json() if f["id"] == fam["id"])["productos"] == 1
    celda = interno.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "FAMILIA", "destino_id": fam["id"]}).json()
    assert celda["normal"]["plantilla_id"] == p["id"]
    # Volver a terminar con lo mismo no repite cambios; dejar el diseño vacío lo hereda
    r = interno.post("/etiquetas/familias/configurar", {"familia": {"id": fam["id"], "nombre": "Wizard 2"},
                                                        "disenos": [{"tipo_etiqueta_id": t["id"], "plantilla_id": p["id"]}]})
    assert r.status_code == 200 and r.json()["hecho"]["disenos"] == 0 and r.json()["familia"]["nombre"] == "Wizard 2"
    r = interno.post("/etiquetas/familias/configurar", {"familia": {"id": fam["id"]},
                                                        "disenos": [{"tipo_etiqueta_id": t["id"], "plantilla_id": None}]})
    assert r.status_code == 200 and r.json()["hecho"]["disenos"] == 1
    assert interno.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "FAMILIA", "destino_id": fam["id"]}).json()["normal"] is None
    # El borrador se descarta
    assert interno.delete_("/perfil/borradores/etiquetas.familia.nueva").status_code == 200
    assert interno.get("/perfil/borradores").json() == []
    interno.post("/etiquetas/productos/familia", {"familia_id": prod["familia_propia_id"], "ids": [prod["id"]]})
