"""Etiquetado como un motor de reglas (igual que la clasificación, sin base
oficial): familias → categorías (reconocidas por condiciones o puestas a mano)
→ reglas que deciden qué diseño, si la etiqueta va o no, dónde va (línea,
posición de la OC o de la lista, variante, artículo genérico, OC, lista,
empaque) y cuántas."""
from etiquetado_util import aprobada, articulo_de, oc_con_articulos, tipo, trabajo, uso

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion

TEXTO = [{"id": "t", "tipo": "texto", "contenido": "x", "x": 2, "y": 2, "w": 40, "h": 8}]


def _productos(articulos: list[int]) -> dict:
    from app.modelos import Articulo

    with SessionLocal() as db, en_organizacion(1):
        res = {}
        for i in articulos:
            a = db.get(Articulo, i)
            res[i] = {"producto_id": a.producto_id, "sku": a.sku, "familia_producto": a.producto.familia_etiquetado_id if a.producto else None}
        return res


def _registros(t):
    return [r for r in t["registros"]]


def test_categorias_reglas_no_lleva_y_donde_va(interno, admin):
    caso = oc_con_articulos(interno, 2)
    oc, lineas = caso["oc"], caso["lineas"]
    arts = [articulo_de(x["id"]) for x in lineas]
    info = _productos(arts)
    prods = sorted({v["producto_id"] for v in info.values() if v["producto_id"]})
    antes = {v["producto_id"]: v["familia_producto"] for v in info.values() if v["producto_id"]}
    fam = interno.post("/etiquetas/familias", {"codigo": "MRFAM", "nombre": "Rules family"}).json()
    try:
        assert interno.post("/etiquetas/productos/familia", {"familia_id": fam["id"], "ids": prods}).status_code == 200
        t = tipo(interno, "MR_TAG", cantidad="POR_LINEA")
        d_fam = aprobada(interno, admin, "MR family tag", t["id"], TEXTO)
        d_cat = aprobada(interno, admin, "MR category tag", t["id"], TEXTO)
        uso(interno, t["id"], d_fam["id"], nivel="FAMILIA", destino_id=fam["id"])
        # Categoría reconocida por condiciones (como en la clasificación): primero se prueba sin guardar
        uno = arts[0]
        cond = [{"campo": "articulo.sku", "op": "igual", "valor": info[uno]["sku"]}]
        p = interno.post("/etiquetas/categorias/probar", {"familia_id": fam["id"], "condiciones": cond}).json()
        assert p["entran"] == 1 and p["ejemplos"][0]["sku"] == info[uno]["sku"], p
        cat = interno.post("/etiquetas/categorias", {"familia_id": fam["id"], "codigo": "MRCAT", "nombre": "Rules category",
                                                     "condiciones": cond}).json()
        assert cat["articulos"] == 1, cat
        uso(interno, t["id"], d_cat["id"], nivel="CATEGORIA", destino_id=cat["id"])
        tr = trabajo(interno, "OC", {"oc_ids": [oc["id"]], "tipos": [t["id"]]})
        por_art = {r["articulo_id"]: r for r in _registros(tr)}
        assert por_art[uno]["plantilla_id"] == d_cat["id"] and "Rules category" in por_art[uno]["motivo"], por_art[uno]
        assert all(r["plantilla_id"] == d_fam["id"] for a, r in por_art.items() if a != uno and info[a]["sku"] != info[uno]["sku"])
        # En la matriz, la categoría es una fila debajo de su familia con su propio diseño
        m = interno.get("/etiquetas/matriz").json()
        fila = next(f for f in m["filas"] if f["nivel"] == "CATEGORIA" and f["id"] == cat["id"])
        assert fila["padre_id"] == fam["id"] and fila["celdas"][str(t["id"])]["normal"]["plantilla_id"] == d_cat["id"]
        c = interno.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "CATEGORIA", "destino_id": cat["id"]})
        assert c.status_code == 200 and c.json()["normal"]["plantilla_id"] == d_cat["id"], c.text
        # «No lleva»: la categoría dice que esta etiqueta no va; sus artículos no tienen registro y no es un error
        r = interno.post("/etiquetas/usos", {"tipo_etiqueta_id": t["id"], "accion": "NO_LLEVA", "nivel": "CATEGORIA",
                                             "destino_id": cat["id"], "contexto_tipo": "NINGUNO", "reemplazar": True})
        assert r.status_code == 200 and r.json()["accion"] == "NO_LLEVA" and r.json()["plantilla_id"] is None, r.text
        tr = trabajo(interno, "OC", {"oc_ids": [oc["id"]], "tipos": [t["id"]]})
        assert uno not in {r["articulo_id"] for r in _registros(tr)} and tr["resumen"]["conteo"].get("ERROR", 0) == 0
        el = interno.get("/etiquetas/resolver", params={"articulo_id": uno}).json()["elecciones"]
        e = next(x for x in el if x["tipo_etiqueta_id"] == t["id"])
        assert e["no_lleva"] and e["plantilla_id"] is None
        # Dónde va: la familia dice «artículo genérico, una por unidad»: un registro por producto con sus unidades
        normal = interno.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "FAMILIA", "destino_id": fam["id"]}).json()["normal"]
        r = interno.patch(f"/etiquetas/usos/{normal['id']}", {"alcance": "PRODUCTO", "cantidad": "POR_UNIDAD", "version": normal["version"]})
        assert r.status_code == 200, r.text
        tr = trabajo(interno, "OC", {"oc_ids": [oc["id"]], "tipos": [t["id"]]})
        regs = _registros(tr)
        otros = {info[a]["producto_id"] for a in arts if a != uno and info[a]["sku"] != info[uno]["sku"]}
        assert {r["clave"].split(":")[-1].split("-")[-1] for r in regs} == {f"r{x}" for x in otros}, [r["clave"] for r in regs]
        unidades = {}
        for x in lineas:
            a = articulo_de(x["id"])
            if a != uno and info[a]["sku"] != info[uno]["sku"]:
                unidades[info[a]["producto_id"]] = unidades.get(info[a]["producto_id"], 0) + int(float(x["cantidad"]))
        assert sorted(r["cantidad"] for r in regs) == sorted(unidades.values())
        # Un lugar que el origen no tiene (la línea de la lista de empaque, desde una OC) se avisa
        normal = interno.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "FAMILIA", "destino_id": fam["id"]}).json()["normal"]
        interno.patch(f"/etiquetas/usos/{normal['id']}", {"alcance": "POSICION_PL", "cantidad": None, "version": normal["version"]})
        tr = trabajo(interno, "OC", {"oc_ids": [oc["id"]], "tipos": [t["id"]]})
        assert not _registros(tr) and "alcance_no_aplica" in {x["codigo"] for x in tr["resumen"]["avisos"]}, tr["resumen"]
        # Puesta a mano en el producto: manda sobre las condiciones
        otro_p = next(x for x in interno.get("/etiquetas/productos", params={"size": 200}).json()["items"]
                      if x["id"] != info[uno]["producto_id"])
        antes[otro_p["id"]] = otro_p["familia_propia_id"]
        interno.post("/etiquetas/productos/familia", {"familia_id": fam["id"], "ids": [otro_p["id"]]})
        otro = interno.get("/etiquetas/articulos", params={"producto_id": otro_p["id"]}).json()["items"][0]["id"]
        el = interno.get("/etiquetas/resolver", params={"articulo_id": otro}).json()["elecciones"]
        assert not next(x for x in el if x["tipo_etiqueta_id"] == t["id"])["porque"].get("categoria")
        assert interno.post("/etiquetas/productos/categoria", {"categoria_id": cat["id"], "ids": [otro_p["id"]]}).status_code == 200
        el = interno.get("/etiquetas/resolver", params={"articulo_id": otro}).json()["elecciones"]
        assert next(x for x in el if x["tipo_etiqueta_id"] == t["id"])["porque"].get("categoria") == "Rules category"
        ficha = interno.get(f"/etiquetas/productos/{otro_p['id']}").json()
        assert [(c["nombre"], c["manual"]) for c in ficha["categorias"]] == [("Rules category", True)], ficha["categorias"]
        interno.post("/etiquetas/productos/categoria", {"categoria_id": None, "ids": [otro_p["id"]]})
        # Una categoría en uso no se borra
        assert interno.delete_(f"/etiquetas/categorias/{cat['id']}").status_code == 409
    finally:
        for pid, f in antes.items():
            interno.post("/etiquetas/productos/familia", {"familia_id": f, "ids": [pid]})


def test_validacion_de_las_reglas(interno, admin):
    t = tipo(interno, "MR_VAL", cantidad="POR_UNIDAD")
    d = aprobada(interno, admin, "MR val", t["id"], TEXTO)
    base = {"tipo_etiqueta_id": t["id"], "plantilla_id": d["id"], "nivel": "GENERAL", "contexto_tipo": "CONDICION",
            "motivo": "test", "condiciones": [{"campo": "articulo.sku", "op": "existe"}]}
    # Una etiqueta de artículo no va en un empaque; «usar» necesita diseño; la prioridad tiene límites
    assert interno.post("/etiquetas/usos", {**base, "alcance": "EMPAQUE"}).status_code == 422
    assert interno.post("/etiquetas/usos", {**base, "plantilla_id": None}).status_code == 422
    assert interno.post("/etiquetas/usos", {**base, "prioridad": 5000}).status_code == 422
    caja = tipo(interno, "MR_VAL_BULTO", sujeto="BULTO", cantidad="POR_BULTO")
    dc = aprobada(interno, admin, "MR val box", caja["id"], TEXTO)
    assert interno.post("/etiquetas/usos", {**base, "tipo_etiqueta_id": caja["id"], "plantilla_id": dc["id"],
                                            "cantidad": "POR_UNIDAD", "condiciones": []}).status_code == 422
    # Prioridad: de dos excepciones del mismo lugar que aplican, gana la de mayor prioridad (sin aviso de empate)
    d2 = aprobada(interno, admin, "MR val high", t["id"], TEXTO)
    a = interno.post("/etiquetas/usos", {**base, "prioridad": 1}).json()
    b = interno.post("/etiquetas/usos", {**base, "plantilla_id": d2["id"], "prioridad": 9,
                                         "condiciones": [{"campo": "articulo.descripcion", "op": "existe"}]})
    assert b.status_code == 200, b.text
    caso = oc_con_articulos(interno, 1)
    tr = trabajo(interno, "OC", {"oc_ids": [caso["oc"]["id"]], "tipos": [t["id"]]})
    r = _registros(tr)[0]
    assert r["plantilla_id"] == d2["id"] and "excepciones_empatadas" not in {p["codigo"] for p in r["problemas"]}
    for u in (a["id"], b.json()["id"]):
        interno.post(f"/etiquetas/usos/{u}/baja", {"motivo": "test"})


def test_tipo_dice_donde_va_por_defecto_y_documento_por_oc(interno, admin):
    t = tipo(interno, "MR_VAR", cantidad="POR_LINEA")
    d = aprobada(interno, admin, "MR variant", t["id"], TEXTO)
    uso(interno, t["id"], d["id"])
    r = interno.patch(f"/etiquetas/tipos/{t['id']}", {"alcance": "ARTICULO", "version": t["version"]})
    assert r.status_code == 200 and r.json()["alcance_efectivo"] == "ARTICULO", r.text
    assert interno.patch(f"/etiquetas/tipos/{t['id']}", {"alcance": "OC", "version": r.json()["version"]}).status_code == 422
    caso = oc_con_articulos(interno, 2)
    tr = trabajo(interno, "OC", {"oc_ids": [caso["oc"]["id"]], "tipos": [t["id"]]})
    skus = {x["codigo_articulo"] for x in caso["lineas"]}
    assert len(_registros(tr)) == len(skus) and all(r["cantidad"] == 1 for r in _registros(tr))
    # Un documento «por OC» desde una lista de empaque: una etiqueta por cada OC que trae la lista
    doc = tipo(interno, "MR_DOC", sujeto="DOCUMENTO", cantidad="POR_DOCUMENTO")
    dd = aprobada(interno, admin, "MR doc", doc["id"], TEXTO)
    uso(interno, doc["id"], dd["id"])
    interno.patch(f"/etiquetas/tipos/{doc['id']}", {"alcance": "OC", "version": doc["version"]})
    pls = [x for x in interno.get("/etiquetas/packing").json() if x["etiquetas_reales"]]
    from app.modelos import PackingList

    with SessionLocal() as db, en_organizacion(1):
        pl = db.get(PackingList, pls[0]["id"])
        ocs = {x.factura_linea.posicion_oc.oc_id for x in pl.lineas}
    tr = trabajo(interno, "PACKING", {"pl_id": pls[0]["id"], "tipos": [doc["id"]]})
    assert {r["oc_id"] for r in _registros(tr)} == ocs and all(r["clave"].split("-")[-1].startswith("oc") for r in _registros(tr))


def test_celda_guarda_la_regla_completa_y_prioridad_permite_cruces(interno, admin):
    t = tipo(interno, "MR_CELDA", cantidad="POR_LINEA")
    d = aprobada(interno, admin, "MR cell", t["id"], TEXTO)
    d2 = aprobada(interno, admin, "MR cell 2", t["id"], TEXTO)
    fam = interno.post("/etiquetas/familias", {"codigo": "MRCEL", "nombre": "Cell family"}).json()
    base = {"tipo_etiqueta_id": t["id"], "nivel": "FAMILIA", "destino_id": fam["id"]}
    # La regla normal de la celda: un diseño con dónde va y cuántas
    c = interno.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "FAMILIA", "destino_id": fam["id"]}).json()
    r = interno.put("/etiquetas/usos/celda", {**base, "firma": c["firma"],
                                               "normal": {"plantilla_id": d["id"], "alcance": "PRODUCTO", "cantidad": "UNA"}})
    assert r.status_code == 200 and r.json()["normal"]["alcance"] == "PRODUCTO" and r.json()["normal"]["cantidad"] == "UNA", r.text
    # Simular «no lleva» no guarda nada; guardarlo deja la regla sin diseño
    s = interno.post("/etiquetas/usos/simular", {**base, "normal": {"accion": "NO_LLEVA"}})
    assert s.status_code == 200 and "no_lleva" in s.json(), s.text
    r = interno.put("/etiquetas/usos/celda", {**base, "firma": r.json()["firma"], "normal": {"accion": "NO_LLEVA"}})
    assert r.status_code == 200 and r.json()["normal"]["accion"] == "NO_LLEVA" and r.json()["normal"]["plantilla_id"] is None, r.text
    # Dos excepciones iguales del mismo lugar: con la misma prioridad chocan; con otra, la prioridad decide
    exc = {"contexto_tipo": "CONDICION", "condiciones": [{"campo": "articulo.sku", "op": "existe"}], "motivo": "test",
           "plantilla_id": d["id"]}
    r = interno.put("/etiquetas/usos/celda", {**base, "firma": r.json()["firma"], "excepciones": [exc]})
    assert r.status_code == 200, r.text
    choque = interno.put("/etiquetas/usos/celda", {**base, "firma": r.json()["firma"], "excepciones": [{**exc, "plantilla_id": d2["id"]}]})
    assert choque.status_code == 409, choque.text
    r = interno.put("/etiquetas/usos/celda", {**base, "firma": r.json()["firma"],
                                               "excepciones": [{**exc, "plantilla_id": d2["id"], "prioridad": 5}]})
    assert r.status_code == 200 and sorted(x["prioridad"] for x in r.json()["excepciones"]) == [0, 5], r.text
    # Heredar otra vez (normal null) y el catálogo dice dónde puede ir cada etiqueta
    r = interno.put("/etiquetas/usos/celda", {**base, "firma": r.json()["firma"], "normal": None,
                                               "quitar": [x["id"] for x in r.json()["excepciones"]]})
    assert r.status_code == 200 and r.json()["normal"] is None and not r.json()["excepciones"], r.text
    cat = interno.get("/etiquetas/catalogos").json()
    assert "PRODUCTO" in cat["alcances"]["ARTICULO"] and cat["cantidades_regla"]["BULTO"] == ["UNA", "MANUAL"]
    # La lista de productos dice la categoría de cada uno (o ninguna)
    p = interno.get("/etiquetas/productos", params={"size": 5}).json()["items"][0]
    assert {"categoria", "categoria_id", "categoria_origen"} <= set(p)
