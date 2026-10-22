"""Etiquetado: diseños, versiones y aprobación, duplicación, dónde se usa cada
diseño (usos por lugar y excepciones) y cuál gana, vista previa con datos de
ejemplo y reales, e imágenes."""
import io

import pytest
from etiquetado_util import tipo
from PIL import Image

TEXTO = {"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 4, "y": 4, "w": 60, "h": 10, "estilo": {"tam": 12}}


def _tipo(api, sujeto="ARTICULO"):
    return tipo(api, f"PLT_{sujeto}", sujeto=sujeto, cantidad={"ARTICULO": "POR_ARTICULO", "BULTO": "POR_BULTO",
                                                                "DOCUMENTO": "POR_DOCUMENTO"}[sujeto])


def _plantilla(api, nombre, sujeto="ARTICULO", elementos=None, **kw):
    r = api.post("/etiquetas/plantillas", {"nombre": nombre, "tipo_etiqueta_id": _tipo(api, sujeto)["id"], **kw,
                                           "diseno": {"ancho": 80, "alto": 40, "elementos": elementos or [TEXTO]}})
    assert r.status_code == 200, r.text
    return r.json()


def _aprobada(interno, admin, nombre, **kw):
    p = _plantilla(interno, nombre, **kw)
    v = p["versiones"][0]
    assert interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {}).status_code == 200
    r = admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {"comentario": "OK"})
    assert r.status_code == 200, r.text
    return interno.get(f"/etiquetas/plantillas/{p['id']}").json()


def test_ciclo_de_versiones(interno, admin, tnf):
    p = _plantilla(interno, "Standard footwear label")
    assert p["tipo"] == "Plt_Articulo" and p["sujeto"] == "ARTICULO"
    v1 = p["versiones"][0]
    assert v1["numero"] == 1 and v1["estado"] == "BORRADOR" and p["vigente"] is None
    # Se guarda y se sigue editando
    d = interno.get(f"/etiquetas/versiones/{v1['id']}").json()
    d["diseno"]["elementos"].append({"id": "talla", "tipo": "texto", "contenido": "Size {{articulo.atributo.TALLA}}", "x": 4, "y": 20,
                                     "w": 40, "h": 8})
    r = interno.put(f"/etiquetas/versiones/{v1['id']}/diseno", {"diseno": d["diseno"], "version": d["version"]})
    assert r.status_code == 200, r.text
    # Concurrencia: guardar con la versión vieja se rechaza
    assert interno.put(f"/etiquetas/versiones/{v1['id']}/diseno", {"diseno": d["diseno"], "version": d["version"]}).status_code == 409
    # Un campo que no tiene lo que se etiqueta (un artículo no tiene datos de caja)
    malo = {**d["diseno"], "elementos": [{"id": "b", "tipo": "campo", "campo": "bulto.numero", "x": 1, "y": 1, "w": 10, "h": 5}]}
    assert interno.put(f"/etiquetas/versiones/{v1['id']}/diseno", {"diseno": malo}).status_code == 422
    # Proveedor: no diseña; interno: no aprueba
    assert tnf.post("/etiquetas/plantillas", {"nombre": "x", "tipo_etiqueta_id": _tipo(interno)["id"]}).status_code == 403
    assert interno.post(f"/etiquetas/versiones/{v1['id']}/enviar", {}).json()["estado"] == "PENDIENTE"
    assert interno.put(f"/etiquetas/versiones/{v1['id']}/diseno", {"diseno": d["diseno"]}).status_code == 409
    assert interno.post(f"/etiquetas/versiones/{v1['id']}/aprobar", {}).status_code == 403
    r = admin.post(f"/etiquetas/versiones/{v1['id']}/aprobar", {"comentario": "Fine"})
    assert r.status_code == 200 and r.json()["estado"] == "APROBADA" and r.json()["aprobada_por"]
    p = interno.get(f"/etiquetas/plantillas/{p['id']}").json()
    assert p["vigente"]["numero"] == 1
    # Una aprobada no se modifica: los cambios van en una versión nueva
    assert interno.put(f"/etiquetas/versiones/{v1['id']}/diseno", {"diseno": d["diseno"]}).status_code == 409
    v2 = interno.post(f"/etiquetas/plantillas/{p['id']}/versiones", {}).json()
    assert v2["numero"] == 2 and v2["estado"] == "BORRADOR" and v2["basada_en_id"] == v1["id"]
    assert interno.post(f"/etiquetas/plantillas/{p['id']}/versiones", {}).json()["id"] == v2["id"]  # una sola abierta
    d2 = v2["diseno"]
    d2["ancho"], d2["elementos"] = 90, d2["elementos"][:1]
    v2 = interno.put(f"/etiquetas/versiones/{v2['id']}/diseno", {"diseno": d2}).json()
    assert "size 80×40 → 90×40 mm" in v2["cambios"] and "removed" in v2["cambios"]
    # Mientras v2 no se aprueba, se usa v1
    assert interno.get(f"/etiquetas/plantillas/{p['id']}").json()["vigente"]["numero"] == 1
    interno.post(f"/etiquetas/versiones/{v2['id']}/enviar", {})
    assert admin.post(f"/etiquetas/versiones/{v2['id']}/rechazar", {}).status_code == 422  # el rechazo lleva comentario
    r = admin.post(f"/etiquetas/versiones/{v2['id']}/rechazar", {"comentario": "Logo missing"})
    assert r.json()["estado"] == "RECHAZADA" and r.json()["comentario"] == "Logo missing"
    # Rechazada: se corrige (vuelve a borrador), se envía y se aprueba
    assert interno.put(f"/etiquetas/versiones/{v2['id']}/diseno", {"diseno": d2}).json()["estado"] == "BORRADOR"
    interno.post(f"/etiquetas/versiones/{v2['id']}/enviar", {})
    admin.post(f"/etiquetas/versiones/{v2['id']}/aprobar", {})
    assert interno.get(f"/etiquetas/plantillas/{p['id']}").json()["vigente"]["numero"] == 2
    # Volver a la versión 1 sin borrar la 2; la vigente no se archiva
    assert admin.post(f"/etiquetas/versiones/{v1['id']}/usar", {"comentario": "Back to the old size"}).status_code == 200
    detalle = interno.get(f"/etiquetas/plantillas/{p['id']}").json()
    assert detalle["vigente"]["numero"] == 1 and [v["estado"] for v in detalle["versiones"]] == ["APROBADA", "APROBADA"]
    assert admin.post(f"/etiquetas/versiones/{v1['id']}/archivar", {}).status_code == 409
    assert admin.post(f"/etiquetas/versiones/{v2['id']}/archivar", {}).json()["estado"] == "ARCHIVADA"
    assert admin.post(f"/etiquetas/versiones/{v2['id']}/usar", {}).json()["estado"] == "APROBADA"  # una archivada aprobada vuelve
    # Bitácora con cada acción y su autor
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import Historial

    with SessionLocal() as db, en_organizacion(1):
        acciones = [h.accion for h in db.query(Historial).filter(Historial.entidad == "plantilla_etiqueta",
                                                                 Historial.entidad_id == p["id"]).order_by(Historial.id)]
    assert {"crear", "enviar_aprobacion", "aprobar", "nueva_version", "rechazar", "usar_version", "archivar_version",
            "guardar_diseno"} <= set(acciones)
    # La misma bitácora por la API (la más reciente primero, con autor y motivo)
    bit = interno.get(f"/etiquetas/plantillas/{p['id']}/bitacora").json()
    assert bit[0]["accion"] == "usar_version" and bit[0]["usuario"] and len(bit) == len(acciones)
    assert next(b for b in bit if b["accion"] == "rechazar")["motivo"] == "Logo missing"
    assert tnf.get(f"/etiquetas/plantillas/{p['id']}/bitacora").status_code == 200  # el proveedor ve (etiquetas.ver)


def test_un_diseno_con_errores_no_se_envia_ni_se_aprueba(interno):
    p = _plantilla(interno, "Broken EAN label", elementos=[
        {"id": "ean", "tipo": "codigo", "simbologia": "ean13", "valor": "{{articulo.sku}}", "x": 5, "y": 5, "w": 60, "h": 25}])
    r = interno.post(f"/etiquetas/versiones/{p['versiones'][0]['id']}/enviar", {})
    assert r.status_code == 422 and r.json()["codigo"] == "diseno_con_errores"


def test_cuatro_ojos(interno, admin):
    try:
        assert admin.put("/organizacion", {"reglas": {"ETIQUETAS_CUATRO_OJOS": True}}).status_code == 200
        p = _plantilla(admin, "Four eyes label")
        v = p["versiones"][0]
        admin.post(f"/etiquetas/versiones/{v['id']}/enviar", {})
        r = admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {})
        assert r.status_code == 409 and r.json()["codigo"] == "cuatro_ojos"
    finally:
        admin.put("/organizacion", {"reglas": {"ETIQUETAS_CUATRO_OJOS": False}})


def test_duplicar_es_independiente(interno, admin):
    original = _aprobada(interno, admin, "Apparel label by size and color")
    copia = interno.post(f"/etiquetas/plantillas/{original['id']}/duplicar", {"nombre": "Apparel label for outlet"}).json()
    assert copia["origen_id"] == original["id"] and copia["versiones"][0]["estado"] == "BORRADOR"
    v = interno.get(f"/etiquetas/versiones/{copia['versiones'][0]['id']}").json()
    v["diseno"]["fondo"] = "#ffeecc"
    interno.put(f"/etiquetas/versiones/{v['id']}/diseno", {"diseno": v["diseno"]})
    vo = interno.get(f"/etiquetas/versiones/{original['vigente']['id']}").json()
    assert vo["diseno"]["fondo"] == "#ffffff" and vo["estado"] == "APROBADA"
    assert interno.post(f"/etiquetas/plantillas/{original['id']}/duplicar", {"nombre": "Apparel label for outlet"}).status_code == 422


@pytest.fixture(scope="module")
def mundo(interno, admin):
    """Artículos, una familia y diseños aprobados para ver cuál gana."""
    fam = interno.post("/etiquetas/familias", {"codigo": "PRIO", "nombre": "Priority test"}).json()
    arts = interno.get("/etiquetas/articulos", params={"size": 200}).json()["items"]
    # x e y, variantes de un producto que toma la familia; z, de otro producto
    # (el primero de un producto con más de una variante: otras pruebas crean productos de una sola)
    x = next(a for a in arts if sum(1 for o in arts if o["producto_id"] == a["producto_id"]) > 1)
    y = next(a for a in arts if a["producto_id"] == x["producto_id"] and a["id"] != x["id"])
    z = next(a for a in arts if a["producto_id"] != x["producto_id"])
    antes = next(p for p in interno.get("/etiquetas/productos", params={"size": 200}).json()["items"]
                 if p["id"] == x["producto_id"])["familia_id"]
    interno.post("/etiquetas/productos/familia", {"familia_id": fam["id"], "ids": [x["producto_id"]]})
    p = {k: _aprobada(interno, admin, f"Priority {k}") for k in ("general", "familia", "articulo", "oc_especial")}
    oc = interno.get("/ordenes", params={"solo_disponible": False, "size": 1}).json()["items"][0]
    doc = {"id": "n", "tipo": "campo", "campo": "oc.numero", "x": 4, "y": 4, "w": 60, "h": 10}
    p["oc"] = _aprobada(interno, admin, "Priority PO", sujeto="DOCUMENTO", elementos=[doc])
    p["oc_general"] = _aprobada(interno, admin, "Priority PO general", sujeto="DOCUMENTO", elementos=[doc])
    yield {"familia": fam, "x": x, "y": y, "z": z, "p": p, "oc": oc}
    interno.post("/etiquetas/productos/familia", {"familia_id": antes, "ids": [x["producto_id"]]})


def test_cual_diseno_gana(interno, admin, mundo):
    """Cada lugar tiene un solo diseño normal; gana el más específico (talla,
    producto, familia, toda la empresa) y la excepción de una OC antes que todo."""
    p, x, y, z = mundo["p"], mundo["x"], mundo["y"], mundo["z"]
    art, doc = _tipo(interno)["id"], _tipo(interno, "DOCUMENTO")["id"]

    def usar(**d):
        return interno.post("/etiquetas/usos", {"tipo_etiqueta_id": art, "contexto_tipo": "NINGUNO", **d})

    assert usar(plantilla_id=p["general"]["id"], nivel="GENERAL").status_code == 200
    assert usar(plantilla_id=p["familia"]["id"], nivel="FAMILIA", destino_id=mundo["familia"]["id"]).status_code == 200
    assert usar(plantilla_id=p["articulo"]["id"], nivel="SKU", destino_id=x["id"]).status_code == 200
    r = usar(plantilla_id=p["general"]["id"], nivel="SKU", destino_id=x["id"])
    assert r.status_code == 409 and r.json()["codigo"] == "celda_ocupada"  # un lugar, un diseño normal
    # Un diseño de otro tipo no se usa aquí; una excepción exige el motivo
    assert usar(plantilla_id=p["oc"]["id"], nivel="SKU", destino_id=z["id"]).status_code == 422
    assert usar(plantilla_id=p["oc_especial"]["id"], nivel="GENERAL", contexto_tipo="OC", oc_id=mundo["oc"]["id"]).status_code == 422
    # Un documento no tiene familia: solo se le pone diseño en toda la empresa
    assert interno.post("/etiquetas/usos", {"tipo_etiqueta_id": doc, "plantilla_id": p["oc"]["id"], "nivel": "FAMILIA",
                                            "destino_id": mundo["familia"]["id"]}).status_code == 422

    def res(tipo_id=art, **q):
        return next(e for e in interno.get("/etiquetas/resolver", params=q).json()["elecciones"] if e["tipo_etiqueta_id"] == tipo_id)

    r = res(sujeto="ARTICULO", articulo_id=x["id"])
    assert (r["plantilla"], r["porque"]["nivel"], r["porque"]["clase"]) == ("Priority articulo", "SKU", "normal") and x["sku"] in r["motivo"]
    r = res(sujeto="ARTICULO", articulo_id=y["id"])
    assert (r["plantilla"], r["porque"]["nivel"]) == ("Priority familia", "FAMILIA") and "Priority test" in r["motivo"]
    r = res(sujeto="ARTICULO", articulo_id=z["id"])
    assert (r["plantilla"], r["porque"]["nivel"]) == ("Priority general", "GENERAL")
    # La excepción de una OC gana aunque el artículo tenga diseño propio
    assert usar(plantilla_id=p["oc_especial"]["id"], nivel="GENERAL", contexto_tipo="OC", oc_id=mundo["oc"]["id"],
                motivo="Customer asked for a special label").status_code == 200
    r = res(sujeto="ARTICULO", articulo_id=x["id"], oc_id=mundo["oc"]["id"])
    assert (r["plantilla"], r["porque"]["clase"]) == ("Priority oc_especial", "oc") and mundo["oc"]["numero"] in r["motivo"]
    assert res(sujeto="ARTICULO", articulo_id=x["id"])["plantilla"] == "Priority articulo"  # sin esa OC, no aplica
    # Archivado: deja de elegirse (la familia cae a toda la empresa)
    interno.post(f"/etiquetas/plantillas/{p['familia']['id']}/archivar", {})
    assert res(sujeto="ARTICULO", articulo_id=y["id"])["porque"]["nivel"] == "GENERAL"
    interno.post(f"/etiquetas/plantillas/{p['familia']['id']}/reactivar", {})
    # Sin aprobar: se elige igual pero se marca (solo imprime en prueba)
    otra = interno.post(f"/etiquetas/plantillas/{p['general']['id']}/duplicar", {"nombre": "Priority general 2"}).json()
    assert usar(plantilla_id=otra["id"], nivel="GENERAL", reemplazar=True).status_code == 200
    r = res(sujeto="ARTICULO", articulo_id=z["id"])
    assert r["plantilla"] == "Priority general 2" and r["aprobada"] is False
    # Dónde se usa cada diseño
    lista = {d["id"]: d for d in interno.get("/etiquetas/plantillas", params={"tipo_etiqueta_id": art, "size": 200}).json()["items"]}
    assert {u["nivel"] for u in lista[p["articulo"]["id"]]["se_usa_en"]} == {"SKU"}
    assert lista[p["oc_especial"]["id"]]["se_usa_en"][0]["excepcion"] is True
    # Documento: la excepción de la OC gana a toda la empresa
    oc = mundo["oc"]
    interno.post("/etiquetas/usos", {"tipo_etiqueta_id": doc, "plantilla_id": p["oc_general"]["id"], "nivel": "GENERAL", "reemplazar": True})
    assert res(doc, sujeto="DOCUMENTO", oc_id=oc["id"])["plantilla"] == "Priority PO general"
    assert interno.post("/etiquetas/usos", {"tipo_etiqueta_id": doc, "plantilla_id": p["oc"]["id"], "nivel": "GENERAL", "contexto_tipo": "OC",
                                            "oc_id": oc["id"], "motivo": "Customer asked for a special label"}).status_code == 200
    r = res(doc, sujeto="DOCUMENTO", oc_id=oc["id"])
    assert (r["plantilla"], r["porque"]["clase"]) == ("Priority PO", "oc")


def _aprobar_existente(interno, admin, plantilla):
    v = plantilla["versiones"][0]
    interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {})
    assert admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {}).status_code == 200


def test_vista_previa_ejemplo_y_reales(interno, mundo):
    p = mundo["p"]["articulo"]
    r = interno.post("/etiquetas/vista-previa", {"version_id": p["vigente"]["id"]})
    assert r.status_code == 200 and r.json()["datos"] == "ejemplo" and r.json()["svg"].startswith("<svg")
    real = interno.post("/etiquetas/vista-previa", {"version_id": p["vigente"]["id"], "articulo_id": mundo["x"]["id"]}).json()
    assert real["datos"] == "reales" and real["valores"]["articulo.sku"] == mundo["x"]["sku"]
    # Un diseño sin guardar (editor) con su tipo de etiqueta
    sin_guardar = interno.post("/etiquetas/vista-previa", {"tipo_etiqueta_id": _tipo(interno)["id"], "diseno": {"ancho": 50, "alto": 30, "elementos": [
        {"id": "t", "tipo": "texto", "contenido": "{{producto.marca}}", "x": 2, "y": 2, "w": 40, "h": 8}]}}).json()
    assert 'width="50mm"' in sin_guardar["svg"]
    assert interno.get(f"/etiquetas/versiones/{p['vigente']['id']}/miniatura.svg").headers["content-type"].startswith("image/svg")


def test_imagenes_del_diseno(interno):
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "#2e7d32").save(buf, "PNG")
    r = interno.c.post("/api/etiquetas/imagenes", files={"archivo": ("logo.png", buf.getvalue(), "image/png")},
                            headers=interno.h)
    assert r.status_code == 200, r.text
    img = r.json()
    assert (img["ancho_px"], img["alto_px"]) == (40, 20)
    assert interno.c.post("/api/etiquetas/imagenes", files={"archivo": ("x.txt", b"hola", "text/plain")},
                               headers=interno.h).status_code == 422
    p = _plantilla(interno, "Label with logo", elementos=[
        {"id": "logo", "tipo": "imagen", "fuente_imagen": "adjunto", "adjunto_id": img["id"], "x": 2, "y": 2, "w": 20, "h": 10}])
    prev = interno.post("/etiquetas/vista-previa", {"version_id": p["versiones"][0]["id"]}).json()
    assert "<image" in prev["svg"] and not prev["problemas"]
    assert interno.get(f"/etiquetas/imagenes/{img['id']}").content == buf.getvalue()
    assert interno.get("/etiquetas/fuentes/LiberationSans-Regular.ttf").status_code == 200
    assert interno.get("/etiquetas/fuentes/..%2Fx.ttf").status_code == 404
