"""Etiquetado: plantillas, versiones y aprobación, duplicación, asignaciones
con su prioridad, vista previa con datos de ejemplo y reales, e imágenes."""
import io

import pytest
from PIL import Image

TEXTO = {"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 4, "y": 4, "w": 60, "h": 10, "estilo": {"tam": 12}}


def _plantilla(api, nombre, modalidad="ARTICULO", elementos=None, **kw):
    r = api.post("/etiquetas/plantillas", {"nombre": nombre, "modalidad": modalidad, **kw,
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
    p = _plantilla(interno, "Standard footwear label", familia_id=None)
    v1 = p["versiones"][0]
    assert v1["numero"] == 1 and v1["estado"] == "BORRADOR" and p["vigente"] is None
    # Se guarda y se sigue editando
    d = interno.get(f"/etiquetas/versiones/{v1['id']}").json()
    d["diseno"]["elementos"].append({"id": "talla", "tipo": "texto", "contenido": "Size {{articulo.talla}}", "x": 4, "y": 20,
                                     "w": 40, "h": 8})
    r = interno.put(f"/etiquetas/versiones/{v1['id']}/diseno", {"diseno": d["diseno"], "version": d["version"]})
    assert r.status_code == 200, r.text
    # Concurrencia: guardar con la versión vieja se rechaza
    assert interno.put(f"/etiquetas/versiones/{v1['id']}/diseno", {"diseno": d["diseno"], "version": d["version"]}).status_code == 409
    # Un campo que la modalidad no tiene (artículo sin OC)
    malo = {**d["diseno"], "elementos": [{"id": "oc", "tipo": "campo", "campo": "oc.numero", "x": 1, "y": 1, "w": 10, "h": 5}]}
    assert interno.put(f"/etiquetas/versiones/{v1['id']}/diseno", {"diseno": malo}).status_code == 422
    # Proveedor: no diseña; interno: no aprueba
    assert tnf.post("/etiquetas/plantillas", {"nombre": "x", "modalidad": "ARTICULO"}).status_code == 403
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
    """Artículos, una familia y diseños aprobados para probar la prioridad."""
    fam = interno.post("/etiquetas/familias", {"codigo": "PRIO", "nombre": "Priority test"}).json()
    arts = interno.get("/etiquetas/articulos", params={"size": 6}).json()["items"]
    x, y, z = arts[0], arts[1], arts[2]
    interno.post("/etiquetas/articulos/familia", {"familia_id": fam["id"], "ids": [x["id"], y["id"]]})
    interno.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [z["id"]]})
    p = {k: _aprobada(interno, admin, f"Priority {k}") for k in ("general", "familia", "articulo")}
    oc = interno.get("/ordenes", params={"solo_disponible": False, "size": 1}).json()["items"][0]
    p["oc"] = _aprobada(interno, admin, "Priority PO", modalidad="OC", elementos=[
        {"id": "n", "tipo": "campo", "campo": "oc.numero", "x": 4, "y": 4, "w": 60, "h": 10}])
    p["oc_general"] = _aprobada(interno, admin, "Priority PO general", modalidad="OC", elementos=[
        {"id": "n", "tipo": "campo", "campo": "oc.numero", "x": 4, "y": 4, "w": 60, "h": 10}])
    return {"familia": fam, "x": x, "y": y, "z": z, "p": p, "oc": oc}


def test_prioridad_de_plantillas(interno, admin, mundo):
    p, x, y, z = mundo["p"], mundo["x"], mundo["y"], mundo["z"]
    asignar = lambda **d: interno.post("/etiquetas/asignaciones", d)  # noqa: E731
    assert asignar(plantilla_id=p["general"]["id"], ambito="GENERAL").status_code == 200
    assert asignar(plantilla_id=p["familia"]["id"], ambito="FAMILIA", familia_id=mundo["familia"]["id"]).status_code == 200
    assert asignar(plantilla_id=p["articulo"]["id"], ambito="ARTICULO", articulo_id=x["id"]).status_code == 200
    assert asignar(plantilla_id=p["articulo"]["id"], ambito="ARTICULO", articulo_id=x["id"]).status_code == 409  # repetida
    # Una plantilla de OC no se asigna a un artículo; la excepción de una OC exige motivo
    assert asignar(plantilla_id=p["oc"]["id"], ambito="ARTICULO", articulo_id=x["id"]).status_code == 422
    assert asignar(plantilla_id=p["oc"]["id"], ambito="OC", oc_id=mundo["oc"]["id"]).status_code == 422
    res = lambda **q: interno.get("/etiquetas/resolver", params=q).json()  # noqa: E731
    r = res(modalidad="ARTICULO", articulo_id=x["id"])
    assert (r["plantilla"], r["nivel"], r["version"]) == ("Priority articulo", "ARTICULO", 1) and x["sku"] in r["motivo"]
    r = res(modalidad="ARTICULO", articulo_id=y["id"])
    assert (r["plantilla"], r["nivel"]) == ("Priority familia", "FAMILIA") and "Priority test" in r["motivo"]
    r = res(modalidad="ARTICULO", articulo_id=z["id"])
    assert (r["plantilla"], r["nivel"]) == ("Priority general", "GENERAL") and "The item has no labeling family." in r["avisos"]
    # Dos generales sin predeterminada: el usuario elige; con predeterminada, se resuelve
    otra = interno.post(f"/etiquetas/plantillas/{p['general']['id']}/duplicar", {"nombre": "Priority general 2"}).json()
    asignar(plantilla_id=otra["id"], ambito="GENERAL")
    r = res(modalidad="ARTICULO", articulo_id=z["id"])
    assert r["plantilla"] == "Priority general" and r["sin_aprobar"] == [{"plantilla_id": otra["id"], "plantilla": "Priority general 2"}]
    copia_aprobada = interno.post(f"/etiquetas/plantillas/{p['general']['id']}/duplicar", {"nombre": "Priority general 3"}).json()
    _aprobar_existente(interno, admin, copia_aprobada)
    asignar(plantilla_id=copia_aprobada["id"], ambito="GENERAL")
    r = res(modalidad="ARTICULO", articulo_id=z["id"])
    assert r["ambigua"] and {c["plantilla"] for c in r["candidatas"]} == {"Priority general", "Priority general 3"}
    a = next(a for a in interno.get("/etiquetas/asignaciones", params={"plantilla_id": copia_aprobada["id"]}).json())
    interno.patch(f"/etiquetas/asignaciones/{a['id']}", {"predeterminada": True})
    r = res(modalidad="ARTICULO", articulo_id=z["id"])
    assert r["plantilla"] == "Priority general 3" and "default among several" in r["motivo"]
    # Archivada: deja de elegirse (la de familia cae a la general)
    interno.post(f"/etiquetas/plantillas/{p['familia']['id']}/archivar", {})
    assert res(modalidad="ARTICULO", articulo_id=y["id"])["nivel"] == "GENERAL"
    interno.post(f"/etiquetas/plantillas/{p['familia']['id']}/reactivar", {})
    # Modalidad OC: la excepción de la OC gana a la general
    oc = mundo["oc"]
    asignar(plantilla_id=p["oc_general"]["id"], ambito="GENERAL")
    assert res(modalidad="OC", oc_id=oc["id"])["plantilla"] == "Priority PO general"
    assert asignar(plantilla_id=p["oc"]["id"], ambito="OC", oc_id=oc["id"], motivo="Customer asked for a special label").status_code == 200
    r = res(modalidad="OC", oc_id=oc["id"])
    assert (r["plantilla"], r["nivel"]) == ("Priority PO", "OC") and oc["numero"] in r["motivo"]


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
    # Un diseño sin guardar (editor) con su modalidad
    sin_guardar = interno.post("/etiquetas/vista-previa", {"modalidad": "ARTICULO", "diseno": {"ancho": 50, "alto": 30, "elementos": [
        {"id": "t", "tipo": "texto", "contenido": "{{articulo.marca}}", "x": 2, "y": 2, "w": 40, "h": 8}]}}).json()
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
