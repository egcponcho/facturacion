"""Seguridad del etiquetado: un proveedor no ve la configuración ni lo ajeno,
las imágenes son solo las de los diseños, los parámetros mal escritos dan 422
(nunca 500) y lo que el rol no ve se oculta en pantalla pero se imprime."""
import io

import pytest
from etiquetado_util import aprobada, tipo, uso
from PIL import Image

from app.core.db import SessionLocal
from app.modulos.acceso import visibilidad

ELEM = [{"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 3, "w": 70, "h": 8, "estilo": {"tam": 10}}]


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "#123456").save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def oc_tnf(interno):
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        d = interno.get(f"/ordenes/{o['id']}").json()
        lineas = [x for x in d["posiciones"] if x.get("codigo_articulo")]
        if d["oc"]["proveedor"] == "The North Face" and d["oc"]["estado"] != "BORRADOR" and lineas:
            return {"oc": d["oc"], "lineas": lineas}
    raise AssertionError("La demo no tiene una OC de The North Face con líneas")


@pytest.fixture(scope="module")
def t_seg(interno, admin):
    t = tipo(interno, "SEG_L", cantidad="POR_LINEA")
    p = aprobada(interno, admin, "SEG design", t["id"], ELEM, ancho=80, alto=30)
    uso(interno, t["id"], p["id"])
    return t, p


def test_imagenes_solo_las_de_los_disenos(interno, vans, tnf):
    from app.modelos import ProductoFoto

    r = interno.c.post("/api/etiquetas/imagenes", files={"archivo": ("logo.png", _png(), "image/png")}, headers=interno.h)
    assert r.status_code == 200, r.text
    assert tnf.get(f"/etiquetas/imagenes/{r.json()['id']}").status_code == 200
    # Una foto de producto de otro proveedor no se lee por la ruta de las imágenes de etiquetas
    p = next(x for x in vans.get("/productos", params={"size": 5}).json()["items"])
    f = vans.c.post(f"/api/productos/{p['id']}/fotos", headers=vans.h, files={"archivo": ("f.png", _png(), "image/png")})
    assert f.status_code == 200, f.text
    with SessionLocal() as db:
        adjunto = db.get(ProductoFoto, f.json()["id"]).adjunto_id
    assert tnf.get(f"/etiquetas/imagenes/{adjunto}").status_code == 404
    assert interno.get(f"/etiquetas/imagenes/{adjunto}").status_code == 404
    # Tampoco se puede poner en un diseño
    r = interno.post("/etiquetas/plantillas", {"nombre": "Photo design", "tipo_etiqueta_id": tipo(interno, "SEG_IMG")["id"],
                                               "diseno": {"ancho": 50, "alto": 30, "elementos": [
                                                   {"id": "i", "tipo": "imagen", "fuente_imagen": "adjunto", "adjunto_id": adjunto,
                                                    "x": 1, "y": 1, "w": 10, "h": 10}]}})
    assert r.status_code == 422


def test_proveedor_no_ve_la_configuracion(tnf, t_seg):
    t, _ = t_seg
    for r in (tnf.get("/etiquetas/usos/valores", params={"contexto": "PROVEEDOR"}), tnf.get("/etiquetas/usos"),
              tnf.post("/etiquetas/usos/simular", {"tipo_etiqueta_id": t["id"], "nivel": "GENERAL", "normal": {"accion": "NO_LLEVA"}}),
              tnf.get("/etiquetas/matriz"), tnf.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "GENERAL"}),
              tnf.get("/etiquetas/familias"), tnf.get("/etiquetas/categorias"), tnf.get("/etiquetas/campos-logicos")):
        assert r.status_code == 403, r.request.url
    # Lo que necesita para imprimir sigue abierto: los tipos y sus propios artículos
    assert tnf.get("/etiquetas/tipos").status_code == 200
    assert tnf.get("/etiquetas/articulos", params={"size": 5}).status_code == 200


@pytest.mark.parametrize("parametros", [
    {"origen": "OC", "parametros": {"oc_ids": ["abc"]}},
    {"origen": "ARTICULOS", "parametros": {"articulos": [{}]}},
    {"origen": "ARTICULOS", "parametros": {"articulos": [{"articulo_id": "x"}]}},
    {"origen": "OC", "parametros": {"oc_ids": [], "dpi": "abc"}},
    {"origen": "OC", "parametros": {"oc_ids": [], "dpi": 5000}},
    {"origen": "OC", "parametros": {"oc_ids": [], "hoja": {"modo": "hoja", "columnas": 0}}},
    {"origen": "OC", "parametros": {"oc_ids": [], "elegidas": {"x": "abc"}}},
    {"origen": "OC", "parametros": {"oc_ids": [], "cantidades": {"x": "muchas"}}},
    {"origen": "PACKING", "parametros": {"pl_id": "abc"}},
])
def test_parametros_mal_escritos_dan_422(interno, parametros):
    assert interno.post("/etiquetas/trabajos", parametros).status_code == 422


def test_proveedor_no_cambia_el_diseno_de_las_reglas(tnf, interno, admin, oc_tnf, t_seg):
    t, p = t_seg
    otra = aprobada(interno, admin, "SEG design B", t["id"], ELEM, ancho=80, alto=30)
    tr = tnf.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc_tnf["oc"]["id"]], "tipos": [t["id"]]}})
    assert tr.status_code == 200, tr.text
    v = tnf.post(f"/etiquetas/trabajos/{tr.json()['id']}/validar").json()
    clave = v["registros"][0]["clave"]
    tnf.patch(f"/etiquetas/trabajos/{tr.json()['id']}", {"version": v["version"], "parametros": {"elegidas": {clave: otra["id"]}}})
    v = tnf.post(f"/etiquetas/trabajos/{tr.json()['id']}/validar").json()
    reg = next(x for x in v["registros"] if x["clave"] == clave)
    assert reg["plantilla"] == p["nombre"]
    assert any(x["codigo"] == "elegida_ignorada" for x in reg["problemas"])


def test_lo_reservado_se_oculta_en_pantalla_por_su_prefijo():
    """Las instantáneas llevan las claves con prefijo («linea.precio»): también se quitan."""
    datos = {"valores": {"linea.precio": 10.5, "oc.fecha_tienda": "2026-01-01", "articulo.sku": "X"}, "precio": 3}
    assert visibilidad.quitar(datos, {"precio", "fecha_tienda"}) == {"valores": {"articulo.sku": "X"}}
    # Dentro de lo que se imprime, el grupo oculto se lee completo
    token = visibilidad._ocultos.set(frozenset({"precios"}))
    try:
        assert visibilidad.oculto("precios")
        with visibilidad.completo():
            assert not visibilidad.oculto("precios")
        assert visibilidad.oculto("precios")
    finally:
        visibilidad._ocultos.reset(token)
