"""Ayudas comunes de las pruebas de etiquetado: tipos de etiqueta propios de
cada prueba (no obligatorios, para no cambiar lo que imprime la demostración),
diseños aprobados, usos de diseño y trabajos (el único camino de generación)."""
import io

import pdfplumber
import pytest

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion


def tipo(api, codigo, sujeto="ARTICULO", cantidad="POR_LINEA", obligatoria=False, nombre=None):
    """Un tipo de etiqueta de la prueba (se crea una sola vez por código)."""
    for t in api.get("/etiquetas/tipos", params={"todos": True}).json():
        if t["codigo"] == codigo:
            return t
    r = api.post("/etiquetas/tipos", {"codigo": codigo, "nombre": nombre or codigo.title(), "sujeto": sujeto, "cantidad": cantidad,
                                      "obligatoria": obligatoria})
    assert r.status_code == 200, r.text
    return r.json()


def aprobada(interno, admin, nombre, tipo_id, elementos, ancho=100, alto=50, **diseno):
    """Diseño nuevo con su versión 1 aprobada."""
    r = interno.post("/etiquetas/plantillas", {"nombre": nombre, "tipo_etiqueta_id": tipo_id,
                                               "diseno": {"ancho": ancho, "alto": alto, "elementos": elementos, **diseno}})
    assert r.status_code == 200, r.text
    p = r.json()
    v = p["versiones"][0]
    assert interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {}).status_code == 200
    assert admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {}).status_code == 200
    return interno.get(f"/etiquetas/plantillas/{p['id']}").json()


def uso(api, tipo_id, plantilla_id, nivel="GENERAL", destino_id=None, **kw):
    """El diseño normal de un lugar (lo reemplaza si ya había uno) o una excepción (con contexto_tipo)."""
    datos = {"tipo_etiqueta_id": tipo_id, "plantilla_id": plantilla_id, "nivel": nivel, "destino_id": destino_id,
             "contexto_tipo": "NINGUNO", "reemplazar": True, **kw}
    r = api.post("/etiquetas/usos", datos)
    assert r.status_code == 200, r.text
    return r.json()


def trabajo(api, origen, parametros, validar=True, esperado=200):
    """Crea el trabajo y lo revisa en el servidor; devuelve su detalle."""
    r = api.post("/etiquetas/trabajos", {"origen": origen, "parametros": parametros})
    assert r.status_code == esperado, r.text
    if r.status_code != 200 or not validar:
        return r.json()
    v = api.post(f"/etiquetas/trabajos/{r.json()['id']}/validar")
    assert v.status_code == 200, v.text
    return v.json()


def cambiar(api, t, parametros, validar=True):
    """Cambia parámetros del borrador y vuelve a revisarlo."""
    r = api.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": parametros, "version": t["version"]})
    assert r.status_code == 200, r.text
    if not validar:
        return r.json()
    v = api.post(f"/etiquetas/trabajos/{t['id']}/validar")
    assert v.status_code == 200, v.text
    return v.json()


def generar(api, t, **opciones):
    """Genera lo pendiente del trabajo (la respuesta, para revisar el código de estado)."""
    return api.post(f"/etiquetas/trabajos/{t['id']}/generar", {"formato": "PDF", **opciones, "version": t["version"]})


def generado(api, t, **opciones):
    r = generar(api, t, aceptar_advertencias=True, **opciones)
    assert r.status_code == 200, r.text
    return r.json()


def problemas(registro):
    return {p["codigo"] for p in registro["problemas"]}


def pdf(contenido):
    with pdfplumber.open(io.BytesIO(contenido)) as doc:
        return [(pg.width, pg.height, pg.extract_text()) for pg in doc.pages]


def oc_con_articulos(api, minimo=2):
    """Una OC aprobada con artículo en todas sus líneas (con sus posiciones)."""
    for o in api.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        d = api.get(f"/ordenes/{o['id']}").json()
        lineas = d["posiciones"]
        if o["estado"] != "BORRADOR" and len(lineas) >= minimo and all(x.get("codigo_articulo") for x in lineas):
            return {"oc": d["oc"], "lineas": lineas}
    pytest.skip("no PO with items")


def articulo_de(posicion_id):
    from app.modelos import PosicionOC

    with SessionLocal() as db, en_organizacion(1):
        return db.get(PosicionOC, posicion_id).articulo_id
