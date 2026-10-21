"""Qué diseño lleva cada cosa: la escalera de resolución (excepción de la OC
primero; después, de lo más específico a lo general, la primera celda que
tiene algo que aplique: sus excepciones en orden centro, país, sociedad,
proveedor, condiciones, y luego su diseño normal), vigencias, la celda que se
guarda entera con su firma, «aplicar también a» (lote), la simulación antes de
guardar, la matriz con su cobertura y la pestaña del producto. Además,
patrones seguros en las condiciones."""
from datetime import date, timedelta

import pytest
from etiquetado_util import aprobada, tipo, uso

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion

TEXTO = [{"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 3, "w": 70, "h": 8, "estilo": {"tam": 10}}]


@pytest.fixture(scope="module")
def caso(interno, admin):
    """Un artículo de una OC (con su centro, país, sociedad y proveedor), una familia propia y siete diseños de un tipo."""
    from app.modelos import Centro, OrdenCompra, PosicionOC

    with SessionLocal() as db, en_organizacion(1):
        p = next(x for x in db.query(PosicionOC).order_by(PosicionOC.id)
                 if x.articulo_id and x.oc.centro_destino and x.oc.estado != "BORRADOR")
        oc: OrdenCompra = p.oc
        centro = db.query(Centro).filter(Centro.codigo == oc.centro_destino).one()
        datos = {"articulo_id": p.articulo_id, "producto_id": p.articulo.producto_id, "oc_id": oc.id, "centro": oc.centro_destino,
                 "pais": centro.pais, "sociedad": oc.sociedad, "proveedor": str(oc.proveedor_id), "posicion_id": p.id}
    fam = interno.post("/etiquetas/familias", {"codigo": "ESCALERA", "nombre": "Ladder family"}).json()
    sub = interno.post("/etiquetas/familias", {"codigo": "ESCALERA-SUB", "nombre": "Ladder subfamily", "padre_id": fam["id"]}).json()
    assert interno.post("/etiquetas/articulos/familia", {"familia_id": sub["id"], "ids": [datos["articulo_id"]]}).status_code == 200
    t = tipo(interno, "ESCALERA")
    d = {k: aprobada(interno, admin, f"Ladder {k}", t["id"], TEXTO, ancho=80, alto=30)
         for k in ("general", "familia", "pais", "sociedad", "centro", "condicion", "producto", "oc")}
    yield {**datos, "familia": fam, "sub": sub, "tipo": t, "d": d}
    interno.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [datos["articulo_id"]]})


def _elige(interno, caso, con_oc=True):
    q = {"sujeto": "ARTICULO", "articulo_id": caso["articulo_id"], **({"oc_id": caso["oc_id"]} if con_oc else {})}
    return next(e for e in interno.get("/etiquetas/resolver", params=q).json()["elecciones"] if e["tipo_etiqueta_id"] == caso["tipo"]["id"])


def _exc(interno, caso, clave, nivel="GENERAL", destino_id=None, **kw):
    return uso(interno, caso["tipo"]["id"], caso["d"][clave]["id"], nivel, destino_id, reemplazar=False,
               motivo=f"Test {clave}", **kw)


def test_escalera_de_resolucion(interno, caso):
    t, fam, sub = caso["tipo"]["id"], caso["familia"]["id"], caso["sub"]["id"]
    assert _elige(interno, caso)["porque"]["clase"] == "sin_diseno"
    uso(interno, t, caso["d"]["general"]["id"])
    assert _elige(interno, caso)["plantilla"] == "Ladder general"
    # La excepción de toda la empresa aplica mientras no haya algo más específico
    _exc(interno, caso, "pais", contexto_tipo="PAIS_DESTINO", contexto_valores=[caso["pais"]])
    e = _elige(interno, caso)
    assert e["plantilla"] == "Ladder pais" and e["porque"]["clase"] == "excepcion" and e["porque"]["nivel"] == "GENERAL"
    assert _elige(interno, caso, con_oc=False)["plantilla"] == "Ladder general"  # sin OC no hay destino
    # La familia madre (heredada por la subfamilia) gana a toda la empresa, incluso a su excepción
    uso(interno, t, caso["d"]["familia"]["id"], "FAMILIA", fam)
    e = _elige(interno, caso)
    assert (e["plantilla"], e["porque"]["nivel"], e["porque"]["destino"]) == ("Ladder familia", "FAMILIA", "Ladder family")
    # En una celda, las excepciones van antes que su diseño normal: centro > país > sociedad > proveedor > condiciones
    _exc(interno, caso, "condicion", "FAMILIA", fam, contexto_tipo="CONDICION",
         condiciones=[{"campo": "articulo.sku", "op": "existe"}])
    assert _elige(interno, caso)["plantilla"] == "Ladder condicion"
    _exc(interno, caso, "sociedad", "FAMILIA", fam, contexto_tipo="SOCIEDAD", contexto_valores=[caso["sociedad"]])
    assert _elige(interno, caso)["plantilla"] == "Ladder sociedad"
    _exc(interno, caso, "centro", "FAMILIA", fam, contexto_tipo="CENTRO_DESTINO", contexto_valores=[caso["centro"]])
    assert _elige(interno, caso)["plantilla"] == "Ladder centro"
    # Una celda con solo excepciones que no aplican no corta la escalera: la subfamilia sigue a su madre
    otro = "ZZ" if caso["pais"] != "ZZ" else "YY"
    r = interno.post("/etiquetas/usos", {"tipo_etiqueta_id": t, "plantilla_id": caso["d"]["pais"]["id"], "nivel": "FAMILIA",
                                         "destino_id": sub, "contexto_tipo": "PAIS_DESTINO", "contexto_valores": [otro], "motivo": "x"})
    assert r.status_code == 422  # el país tiene que existir
    with SessionLocal() as db, en_organizacion(1):
        from app.modelos import Pais

        otro = db.query(Pais.codigo).filter(Pais.codigo != caso["pais"]).first()[0]
    _exc(interno, caso, "pais", "FAMILIA", sub, contexto_tipo="PAIS_DESTINO", contexto_valores=[otro])
    assert _elige(interno, caso)["plantilla"] == "Ladder centro"
    # El producto (más específico) gana a la familia
    if caso["producto_id"]:
        uso(interno, t, caso["d"]["producto"]["id"], "PRODUCTO", caso["producto_id"])
        assert _elige(interno, caso)["porque"]["nivel"] == "PRODUCTO"
    # Una excepción vencida no aplica
    ayer = (date.today() - timedelta(days=2)).isoformat()
    _exc(interno, caso, "oc", "GENERAL", contexto_tipo="OC", oc_id=caso["oc_id"], vigente_hasta=ayer)
    assert _elige(interno, caso)["plantilla"] != "Ladder oc"
    # La excepción de la OC gana a todo
    # Desde ayer (no se cruza con la vencida; «hoy» del servidor puede ir un día delante del de la empresa)
    desde = (date.today() - timedelta(days=1)).isoformat()
    u = _exc(interno, caso, "oc", "GENERAL", contexto_tipo="OC", oc_id=caso["oc_id"], vigente_desde=desde)
    e = _elige(interno, caso)
    assert (e["plantilla"], e["porque"]["clase"]) == ("Ladder oc", "oc")
    # Dos excepciones iguales en la misma celda no se pueden guardar
    r = interno.post("/etiquetas/usos", {"tipo_etiqueta_id": t, "plantilla_id": caso["d"]["oc"]["id"], "nivel": "GENERAL",
                                         "contexto_tipo": "OC", "oc_id": caso["oc_id"], "motivo": "again"})
    assert r.status_code == 409 and r.json()["codigo"] == "excepcion_repetida"
    # Dar de baja no borra: queda en el historial y deja de aplicar
    assert interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "Done"}).json()["eliminado_en"]
    assert _elige(interno, caso)["plantilla"] != "Ladder oc"
    h = interno.get(f"/etiquetas/usos/{u['id']}/historial").json()
    assert [x["accion"] for x in h][:2] == ["crear", "baja"] or {"crear", "baja"} <= {x["accion"] for x in h}


def test_celda_con_firma_simulacion_y_lote(interno, admin, tnf, caso):
    """La celda se lee con su firma y se guarda entera; si otro la cambió, 409.
    «Qué cambia» no guarda nada. «Aplicar también a» copia la excepción."""
    t = tipo(interno, "CELDA")
    d1 = aprobada(interno, admin, "Cell A", t["id"], TEXTO, ancho=80, alto=30)
    d2 = aprobada(interno, admin, "Cell B", t["id"], TEXTO, ancho=80, alto=30)
    fam = caso["familia"]["id"]
    c = interno.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "FAMILIA", "destino_id": fam}).json()
    assert c["normal"] is None and c["hereda"] is None and c["articulos"] >= 1
    # Simular: cuántos artículos cambian, sin guardar
    sim = interno.post("/etiquetas/usos/simular", {"tipo_etiqueta_id": t["id"], "nivel": "FAMILIA", "destino_id": fam,
                                                    "normal": {"plantilla_id": d1["id"]}}).json()
    assert sim["cambian"] == c["articulos"] and sim["sin_diseno"] == 0
    assert interno.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "FAMILIA", "destino_id": fam}).json()["normal"] is None
    # Guardar con la firma leída
    r = interno.put("/etiquetas/usos/celda", {"tipo_etiqueta_id": t["id"], "nivel": "FAMILIA", "destino_id": fam, "firma": c["firma"],
                                              "normal": {"plantilla_id": d1["id"]},
                                              "excepciones": [{"contexto_tipo": "SOCIEDAD", "contexto_valores": [caso["sociedad"]],
                                                               "plantilla_id": d2["id"], "motivo": "Company"}]})
    assert r.status_code == 200, r.text
    c2 = r.json()
    assert c2["normal"]["plantilla"] == "Cell A" and len(c2["excepciones"]) == 1 and c2["firma"] != c["firma"]
    # Con la firma vieja: alguien más la cambió
    r = interno.put("/etiquetas/usos/celda", {"tipo_etiqueta_id": t["id"], "nivel": "FAMILIA", "destino_id": fam, "firma": c["firma"],
                                              "normal": {"plantilla_id": d2["id"]}})
    assert r.status_code == 409 and r.json()["codigo"] == "conflicto_version"
    # Quitar la excepción y volver a heredar (sin diseño propio) en una sola operación
    r = interno.put("/etiquetas/usos/celda", {"tipo_etiqueta_id": t["id"], "nivel": "FAMILIA", "destino_id": fam, "firma": c2["firma"],
                                              "normal": None, "quitar": [c2["excepciones"][0]["id"]]})
    assert r.status_code == 200 and r.json()["normal"] is None and r.json()["excepciones"] == []
    # La misma excepción en varias celdas de la columna
    sub = caso["sub"]["id"]
    r = interno.post("/etiquetas/usos/lote", {"tipo_etiqueta_id": t["id"], "celdas": [{"nivel": "FAMILIA", "destino_id": fam},
                                                                                      {"nivel": "FAMILIA", "destino_id": sub}],
                                              "excepcion": {"contexto_tipo": "PROVEEDOR", "contexto_valores": [caso["proveedor"]],
                                                            "plantilla_id": d2["id"], "motivo": "Supplier"}})
    assert r.status_code == 200, r.text
    assert {u["destino_id"] for u in r.json()["creados"]} == {fam, sub}
    # Un lugar que no existe para ese tipo: 422
    assert interno.put("/etiquetas/usos/celda", {"tipo_etiqueta_id": t["id"], "nivel": "TIPO_EMPAQUE", "destino_id": 1,
                                                 "normal": {"plantilla_id": d1["id"]}}).status_code == 422
    # Un proveedor no configura
    assert tnf.put("/etiquetas/usos/celda", {"tipo_etiqueta_id": t["id"], "nivel": "GENERAL", "destino_id": None,
                                             "normal": {"plantilla_id": d1["id"]}}).status_code == 403


def test_matriz_cobertura_y_producto(interno, tnf, caso):
    m = interno.get("/etiquetas/matriz", params={"sujeto": "ARTICULO"}).json()
    assert m["filas"][0]["nivel"] == "GENERAL" and m["filas"][-1]["nivel"] == "SIN_FAMILIA"
    ids = [f["id"] for f in m["filas"] if f["nivel"] == "FAMILIA"]
    assert ids.index(caso["familia"]["id"]) < ids.index(caso["sub"]["id"])  # la subfamilia debajo de su madre
    fila = next(f for f in m["filas"] if f["id"] == caso["sub"]["id"])
    celda = fila["celdas"][str(caso["tipo"]["id"])]
    assert celda["normal"] is None and celda["hereda"]["destino"] == "Ladder family" and celda["excepciones"] >= 1
    assert m["cobertura"]["total"] >= 1
    assert {t["id"] for t in m["tipos"]} >= {caso["tipo"]["id"]}
    # Cajas: filas por tipo de empaque
    b = interno.get("/etiquetas/matriz", params={"sujeto": "BULTO"}).json()
    assert b["filas"][0]["nivel"] == "GENERAL" and all(f["nivel"] == "TIPO_EMPAQUE" for f in b["filas"][1:])
    # El producto: su familia y el diseño de cada tipo con el porqué
    if caso["producto_id"]:
        p = interno.get(f"/etiquetas/productos/{caso['producto_id']}").json()
        x = next(t for t in p["tipos"] if t["tipo"]["id"] == caso["tipo"]["id"])
        assert x["eleccion"]["plantilla"] and x["propio"] and x["propio"]["nivel"] == "PRODUCTO"
    # Lo que se imprimiría desde la OC, por tipo
    r = interno.get("/etiquetas/resumen", params={"origen": "OC", "id": caso["oc_id"]}).json()
    assert r["total"] >= 1 and any(t["tipo"]["id"] == caso["tipo"]["id"] for t in r["tipos"])
    # Un proveedor ve pero no cambia
    assert tnf.get("/etiquetas/matriz").status_code == 403
    assert tnf.post("/etiquetas/usos", {"tipo_etiqueta_id": caso["tipo"]["id"], "plantilla_id": caso["d"]["general"]["id"],
                                        "nivel": "GENERAL"}).status_code == 403


def test_tipos_de_etiqueta(interno, tnf):
    sug = interno.get("/etiquetas/catalogos").json()["sugeridos"]
    assert {s["codigo"] for s in sug} >= {"COLGANTE", "CAJA"}
    r = interno.post("/etiquetas/tipos", {"codigo": "x y", "nombre": "Bad", "sujeto": "ARTICULO", "cantidad": "POR_UNIDAD"})
    assert r.status_code == 422
    r = interno.post("/etiquetas/tipos", {"codigo": "TT_DOC", "nombre": "Doc", "sujeto": "DOCUMENTO", "cantidad": "POR_UNIDAD"})
    assert r.status_code == 422  # un documento no sale «una por unidad»
    t = interno.post("/etiquetas/tipos", {"codigo": "TT_DOC", "nombre": "Doc", "sujeto": "DOCUMENTO", "cantidad": "POR_DOCUMENTO"}).json()
    r = interno.patch(f"/etiquetas/tipos/{t['id']}", {"nombre": "Document", "version": t["version"]})
    assert r.status_code == 200 and r.json()["nombre"] == "Document"
    assert interno.patch(f"/etiquetas/tipos/{t['id']}", {"nombre": "Again", "version": t["version"]}).status_code == 409
    r = interno.patch(f"/etiquetas/tipos/{t['id']}", {"activo": False})
    assert r.status_code == 200 and t["id"] not in {x["id"] for x in interno.get("/etiquetas/tipos").json()}
    assert t["id"] in {x["id"] for x in interno.get("/etiquetas/tipos", params={"todos": True}).json()}
    assert tnf.post("/etiquetas/tipos", {"codigo": "TT_P", "nombre": "P", "sujeto": "ARTICULO", "cantidad": "POR_UNIDAD"}).status_code == 403


def test_patrones_seguros_y_acotados(interno):
    """«coincide» no puede dejar al servidor calculando: se rechazan las
    repeticiones anidadas al guardar una excepción o un diseño, y un patrón
    peligroso guardado antes (o un texto enorme) no se evalúa."""
    import time

    from app.modulos.etiquetado import reglas, render

    assert reglas.validar_patron(r"^[A-Z]{3}-\d{4}$") is None and reglas.validar_patron("NIKE.*") is None
    c = {"campo": "articulo.sku", "op": "coincide", "valor": "(a+)+$"}
    inicio = time.perf_counter()
    assert reglas.cumple_condicion(c, {"articulo.sku": "a" * 40 + "!"}) is False
    assert render.cumple(c, {"articulo.sku": "a" * 40 + "!"}) is False
    assert time.perf_counter() - inicio < 0.5
    assert reglas.cumple_condicion({**c, "valor": "A.*"}, {"articulo.sku": "A" * 5000}) is False  # texto fuera del tope
    assert reglas.cumple_condicion({**c, "valor": "a[0-9]+"}, {"articulo.sku": "A123"}) is True
    # La condición de visibilidad de un elemento del diseño usa la misma validación
    t = tipo(interno, "PATRON")
    r = interno.post("/etiquetas/plantillas", {"nombre": "Unsafe pattern", "tipo_etiqueta_id": t["id"], "diseno": {
        "ancho": 50, "alto": 20, "elementos": [{"id": "t", "tipo": "texto", "contenido": "x", "x": 1, "y": 1, "w": 20, "h": 5,
                                                "condicion": {"campo": "articulo.sku", "op": "coincide", "valor": "(\\w+\\s?)*$"}}]}})
    assert r.status_code == 422 and "repeat" in r.text, r.text
