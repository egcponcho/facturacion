"""Etiquetado: generación desde una OC con datos reales (por línea, por unidad,
manual), combinación de OC y artículo, diseño por familia con dato obligatorio,
advertencias y duplicados, unidades no contables, lotes grandes, alcance del
proveedor, pruebas con versiones sin aprobar y reproducción exacta de un lote
histórico. Todo pasa por los trabajos de etiquetado (el único camino)."""
import io
import time
import zipfile

import pdfplumber
import pytest
from etiquetado_util import (
    aprobada,
    articulo_de,
    cambiar,
    generado,
    generar,
    oc_con_articulos,
    pdf,
    problemas,
    tipo,
    trabajo,
    uso,
)
from PIL import Image

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion

zxingcpp = pytest.importorskip("zxingcpp")

COMBINADA = [
    {"id": "oc", "tipo": "campo", "campo": "oc.numero", "prefijo": "PO ", "x": 3, "y": 3, "w": 50, "h": 7, "estilo": {"tam": 10, "negrita": True}},
    {"id": "prov", "tipo": "campo", "campo": "oc.proveedor", "x": 55, "y": 3, "w": 42, "h": 7, "estilo": {"tam": 8, "alin": "der"}},
    {"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 12, "w": 60, "h": 7, "estilo": {"tam": 11}},
    {"id": "talla", "tipo": "texto", "contenido": "Size {{articulo.talla}}", "x": 65, "y": 12, "w": 32, "h": 7},
    {"id": "n", "tipo": "texto", "contenido": "{{etiqueta.numero}}/{{etiqueta.total}}", "x": 75, "y": 40, "w": 22, "h": 6,
     "estilo": {"tam": 8, "alin": "der"}},
    {"id": "bc", "tipo": "codigo", "simbologia": "code128", "valor": "{{articulo.sku}}", "x": 3, "y": 21, "w": 70, "h": 18,
     "margen": 1},
]


@pytest.fixture(scope="module")
def oc(interno):
    return oc_con_articulos(interno)


@pytest.fixture(scope="module")
def tipos(interno):
    """Tipos de la prueba: uno por línea, uno por unidad y uno manual (ninguno obligatorio)."""
    return {"linea": tipo(interno, "GEN_LINEA", cantidad="POR_LINEA"), "unidad": tipo(interno, "GEN_UNIDAD", cantidad="POR_UNIDAD"),
            "manual": tipo(interno, "GEN_MANUAL", cantidad="MANUAL")}


def test_sin_diseno_aprobado_no_se_genera(interno, oc, tipos):
    """Un tipo opcional sin diseño se omite; uno obligatorio sin diseño es un error que no deja generar."""
    t = trabajo(interno, "OC", {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["linea"]["id"]]})
    assert t["registros"] and all(r["estado"] == "OMITIDO" for r in t["registros"])
    assert generar(interno, t).status_code == 422
    oblig = tipo(interno, "GEN_OBLIG", obligatoria=True)
    try:
        t = trabajo(interno, "OC", {"oc_ids": [oc["oc"]["id"]], "tipos": [oblig["id"]]})
        assert all(r["estado"] == "ERROR" and "sin_plantilla" in problemas(r) for r in t["registros"])
        r = generar(interno, t)
        assert r.status_code == 422 and r.json()["codigo"] == "etiquetas_con_errores"
    finally:
        # Desactivado no cuenta para la cobertura ni para lo que se imprime por defecto
        assert interno.patch(f"/etiquetas/tipos/{oblig['id']}", {"activo": False, "obligatoria": False}).status_code == 200


@pytest.fixture(scope="module")
def combinada(interno, admin, oc, tipos):
    """El mismo diseño (OC + artículo) para los tres tipos de la prueba, en «toda la empresa»."""
    res = {}
    for k, tp in tipos.items():
        p = aprobada(interno, admin, f"Combined PO and item label {k}", tp["id"], COMBINADA)
        uso(interno, tp["id"], p["id"])
        res[k] = p
    return res


def test_generar_por_linea_unidad_y_manual(interno, oc, tipos, combinada):
    base = {"oc_ids": [oc["oc"]["id"]]}
    lineas = oc["lineas"]
    t = trabajo(interno, "OC", {**base, "tipos": [tipos["linea"]["id"]]})
    assert len(t["registros"]) == len(lineas) and {r["plantilla"] for r in t["registros"]} == {"Combined PO and item label linea"}
    assert all(r["version"] == 1 and r["cantidad"] == 1 for r in t["registros"])
    assert all(r["motivo"] == "Whole company." for r in t["registros"])
    # Por unidad: una etiqueta por cada unidad pedida de cada línea
    dos = [lineas[0]["id"], lineas[1]["id"]]
    t = trabajo(interno, "OC", {**base, "tipos": [tipos["unidad"]["id"]], "posiciones": dos})
    assert [r["cantidad"] for r in t["registros"]] == [int(lineas[0]["cantidad"]), int(lineas[1]["cantidad"])]
    # Manual: sin cantidad es un error; con cantidades distintas por línea, se generan
    t = trabajo(interno, "OC", {**base, "tipos": [tipos["manual"]["id"]], "posiciones": dos})
    assert all("cantidad" in problemas(r) for r in t["registros"])
    t = cambiar(interno, t, {"cantidades": {t["registros"][0]["clave"]: 3, t["registros"][1]["clave"]: 2}})
    assert [r["cantidad"] for r in t["registros"]] == [3, 2] and t["total"] == 5
    t = generado(interno, t)
    gen = t["ejecuciones"][0]
    assert gen["total"] == 5 and gen["estado"] == "GENERADA"
    arch = interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo")
    assert arch.status_code == 200 and arch.headers["x-identico"] == "1"
    paginas = pdf(arch.content)
    assert len(paginas) == 5
    # Datos combinados: la OC y el artículo de cada línea, numeración n/N por registro
    assert all(abs(w - 100 * 72 / 25.4) < 0.01 and abs(h - 50 * 72 / 25.4) < 0.01 for w, h, _ in paginas)
    assert all(f"PO {oc['oc']['numero']}" in x for _, _, x in paginas)
    assert lineas[0]["codigo_articulo"] in paginas[0][2] and "1/3" in paginas[0][2] and "3/3" in paginas[2][2]
    assert lineas[1]["codigo_articulo"] in paginas[3][2] and "2/2" in paginas[4][2]


def test_zip_con_png_y_svg_y_codigo_legible(interno, oc, tipos, combinada):
    linea = oc["lineas"][0]
    t = trabajo(interno, "OC", {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["linea"]["id"]], "posiciones": [linea["id"]]})
    t = generado(interno, t, formato="ZIP")
    z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/generaciones/{t['ejecuciones'][-1]['id']}/archivo").content))
    nombres = z.namelist()
    assert any(n.endswith(".pdf") for n in nombres) and "lote.json" in nombres
    pngs = [n for n in nombres if n.startswith("png/")]
    assert len(pngs) == 1 and len([n for n in nombres if n.startswith("svg/")]) == 1
    with Image.open(io.BytesIO(z.read(pngs[0]))) as im:
        assert im.size == (1181, 591)
        leidos = [x.text for x in zxingcpp.read_barcodes(im.convert("L"))]
    assert linea["codigo_articulo"] in leidos


def test_hoja_que_no_cabe_se_rechaza(interno, oc, tipos, combinada):
    """Varias por hoja: si la etiqueta (100×50) no cabe con esas columnas y
    márgenes, se avisa antes de generar en vez de dibujarla fuera del papel."""
    hoja = {"modo": "hoja", "papel_ancho": 215.9, "papel_alto": 279.4, "columnas": 3, "filas": 2}
    base = {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["linea"]["id"]], "posiciones": [oc["lineas"][0]["id"]], "prueba": True}
    t = trabajo(interno, "OC", {**base, "hoja": hoja})
    r = generar(interno, t, aceptar_advertencias=True)
    assert r.status_code == 422 and r.json()["detalle"][0]["mensaje"] == "100×50 mm", r.text
    t = cambiar(interno, interno.get(f"/etiquetas/trabajos/{t['id']}").json(), {"hoja": {**hoja, "columnas": 2}})
    assert generar(interno, t, aceptar_advertencias=True).status_code == 200


def test_familia_con_dato_obligatorio_y_diseno_de_familia(interno, admin, oc, tipos, combinada):
    linea = oc["lineas"][0]
    articulo_id = articulo_de(linea["id"])
    fam = interno.post("/etiquetas/familias", {"codigo": "GENFAM", "nombre": "Generation family",
                                               "campos": [{"campo": "articulo.extra.no_existe_aun", "obligatorio": True}]})
    assert fam.status_code == 422  # un campo que no existe no se acepta
    fam = interno.post("/etiquetas/familias", {"codigo": "GENFAM", "nombre": "Generation family",
                                               "campos": [{"campo": "producto.uso", "obligatorio": True}]}).json()
    assert interno.post("/etiquetas/articulos/familia", {"familia_id": fam["id"], "ids": [articulo_id]}).status_code == 200
    de_familia = aprobada(interno, admin, "Generation family label", tipos["linea"]["id"], [c for c in COMBINADA if c["id"] != "talla"])
    uso(interno, tipos["linea"]["id"], de_familia["id"], "FAMILIA", fam["id"])
    try:
        with SessionLocal() as db, en_organizacion(1):
            from app.modelos import Articulo

            a = db.get(Articulo, articulo_id)
            valor = (a.producto.ficha or {}).get("uso") if a.producto else None
        t = trabajo(interno, "OC", {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["linea"]["id"]],
                                    "posiciones": [linea["id"], oc["lineas"][1]["id"]]})
        r0, r1 = t["registros"]
        assert r0["plantilla"] == "Generation family label" and r0["motivo"] == "Labeling family Generation family."
        assert r1["plantilla"] == "Combined PO and item label linea" or articulo_de(oc["lineas"][1]["id"]) == articulo_id
        if not valor:
            assert "dato_familia" in problemas(r0)
    finally:
        # Se deja todo como estaba para las demás pruebas
        interno.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [articulo_id]})


def test_advertencias_y_duplicados_piden_confirmar(interno, oc, tipos, combinada):
    pedido = {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["linea"]["id"]], "posiciones": [oc["lineas"][-1]["id"]]}
    generado(interno, trabajo(interno, "OC", pedido))
    t = trabajo(interno, "OC", pedido)
    assert "ya_generada" in problemas(t["registros"][0]) and t["registros"][0]["estado"] == "ADVERTENCIA"
    sin_aceptar = generar(interno, t)
    assert sin_aceptar.status_code == 409 and sin_aceptar.json()["codigo"] == "confirmar_advertencias"
    assert generar(interno, t, aceptar_advertencias=True).status_code == 200


def _por_unidad(interno, oc, tipos, linea, unidad, cantidad=None):
    """El registro «una por unidad» de la línea en otra unidad de medida."""
    from app.modelos import PosicionOC

    with SessionLocal() as db, en_organizacion(1):
        p = db.get(PosicionOC, linea["id"])
        antes = p.unidad, p.cantidad
        p.unidad = unidad
        if cantidad is not None:
            p.cantidad = cantidad
        db.commit()
    try:
        t = trabajo(interno, "OC", {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["unidad"]["id"]], "posiciones": [linea["id"]]})
        r = t["registros"][0]
        return r, {x["codigo"]: x["mensaje"] for x in r["problemas"]}
    finally:
        with SessionLocal() as db, en_organizacion(1):
            p = db.get(PosicionOC, linea["id"])
            p.unidad, p.cantidad = antes
            db.commit()


def test_unidad_no_contable(interno, oc, tipos, combinada):
    """Decide el catálogo de unidades de medida, no una lista fija en el código."""
    linea = oc["lineas"][0]
    _, prob = _por_unidad(interno, oc, tipos, linea, "KG", 12)
    assert "unidad_no_contable" in prob and "measured" in prob["unidad_no_contable"]
    _, prob = _por_unidad(interno, oc, tipos, linea, "PAR", 2.5)
    assert "unidad_no_contable" in prob and "fractional" in prob["unidad_no_contable"]
    r, prob = _por_unidad(interno, oc, tipos, linea, "PAR", 3)
    assert "unidad_no_contable" not in prob and r["cantidad"] == 3


def test_unidad_nueva_del_catalogo(interno, oc, tipos, combinada):
    """Una unidad que la empresa agrega al catálogo (botella, contable) se
    etiqueta por unidad sin tocar código; otra medible (galón) no."""
    nuevas = []
    for codigo, nombre, contable in (("BTL", "bottle", True), ("GLN", "gallon", False)):
        r = interno.post("/catalogos/unidades", {"codigo": codigo, "nombre": nombre, "contable": contable})
        assert r.status_code == 200, r.text
        nuevas.append(r.json()["id"])
    try:
        linea = oc["lineas"][0]
        r, prob = _por_unidad(interno, oc, tipos, linea, "BTL", 4)
        assert "unidad_no_contable" not in prob and r["cantidad"] == 4
        _, prob = _por_unidad(interno, oc, tipos, linea, "GLN", 4)
        assert "unidad_no_contable" in prob
    finally:
        for i in nuevas:
            interno.delete_(f"/catalogos/unidades/{i}")


def test_reproducir_un_lote_historico_sin_cambiar_version_ni_datos(interno, admin, oc, tipos, combinada):
    linea = oc["lineas"][0]
    articulo_id = articulo_de(linea["id"])
    pedido = {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["linea"]["id"]], "posiciones": [linea["id"]]}
    gen = generado(interno, trabajo(interno, "OC", pedido))["ejecuciones"][0]
    original = interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo").content
    # Cambia el diseño (versión 2 aprobada) y cambian los datos del artículo
    disenio = combinada["linea"]
    v2 = interno.post(f"/etiquetas/plantillas/{disenio['id']}/versiones", {}).json()
    v2["diseno"]["fondo"] = "#fff3e0"
    v2["diseno"]["elementos"][0]["prefijo"] = "ORDER "
    assert interno.put(f"/etiquetas/versiones/{v2['id']}/diseno", {"diseno": v2["diseno"]}).status_code == 200
    interno.post(f"/etiquetas/versiones/{v2['id']}/enviar", {})
    admin.post(f"/etiquetas/versiones/{v2['id']}/aprobar", {})
    with SessionLocal() as db, en_organizacion(1):
        from app.modelos import Articulo

        a = db.get(Articulo, articulo_id)
        talla_antes, a.talla = a.talla, "ZZ"
        db.commit()
    try:
        r = interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo")
        assert r.headers["x-identico"] == "1" and r.content == original
        texto = pdf(r.content)[0][2]
        assert f"PO {oc['oc']['numero']}" in texto and "ORDER" not in texto and "ZZ" not in texto
        detalle = interno.get(f"/etiquetas/generaciones/{gen['id']}").json()
        assert detalle["versiones"][0]["version"] == 1 and detalle["items"][0]["valores"]["articulo.talla"] == talla_antes
        # Un trabajo nuevo usa la versión 2 y los datos actuales
        nueva = generado(interno, trabajo(interno, "OC", pedido))["ejecuciones"][0]
        assert interno.get(f"/etiquetas/generaciones/{nueva['id']}").json()["versiones"][0]["version"] == 2
        texto = pdf(interno.get(f"/etiquetas/generaciones/{nueva['id']}/archivo").content)[0][2]
        assert "ORDER" in texto and "Size ZZ" in texto
    finally:
        with SessionLocal() as db, en_organizacion(1):
            db.get(Articulo, articulo_id).talla = talla_antes
            db.commit()
    # Historial con filtros
    h = interno.get("/etiquetas/generaciones", params={"oc_id": oc["oc"]["id"], "version_id": disenio["vigente"]["id"]}).json()
    assert gen["id"] in {x["id"] for x in h["items"]}
    assert interno.get("/etiquetas/generaciones", params={"articulo_id": articulo_id}).json()["total"] >= 2


def test_prueba_con_version_sin_aprobar(interno, tnf, admin, oc):
    """Un diseño sin aprobar solo imprime en prueba (marca TEST); nunca usa una versión rechazada."""
    doc = tipo(interno, "GEN_DOC", sujeto="DOCUMENTO", cantidad="POR_DOCUMENTO")
    p = interno.post("/etiquetas/plantillas", {"nombre": "Draft PO label", "tipo_etiqueta_id": doc["id"], "diseno": {
        "ancho": 60, "alto": 30, "elementos": [{"id": "n", "tipo": "campo", "campo": "oc.numero", "x": 3, "y": 3, "w": 50, "h": 8}]}}).json()
    uso(interno, doc["id"], p["id"])
    base = {"oc_ids": [oc["oc"]["id"]], "tipos": [doc["id"]]}
    t = trabajo(interno, "OC", base)
    assert "sin_plantilla" in problemas(t["registros"][0])
    t = trabajo(interno, "OC", {**base, "prueba": True})
    t = generado(interno, t)
    gen = t["ejecuciones"][0]
    assert gen["estado"] == "PRUEBA"
    with pdfplumber.open(io.BytesIO(interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo").content)) as d:
        letras = "".join(c["text"] for c in d.pages[0].chars)
    assert "TEST·NOTAPPROVED" in letras.replace(" ", "") and oc["oc"]["numero"] in letras
    # Una versión rechazada no se usa ni en prueba (E2)
    v = p["versiones"][0]
    interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {})
    assert admin.post(f"/etiquetas/versiones/{v['id']}/rechazar", {"comentario": "No"}).status_code == 200
    t = trabajo(interno, "OC", {**base, "prueba": True})
    assert "sin_plantilla" in problemas(t["registros"][0])
    # Un proveedor prueba solo con versiones aprobadas (las sin aprobar son de quien diseña)
    p2 = interno.post("/etiquetas/plantillas", {"nombre": "Draft PO label 2", "tipo_etiqueta_id": doc["id"], "diseno": {
        "ancho": 60, "alto": 30, "elementos": [{"id": "n", "tipo": "campo", "campo": "oc.numero", "x": 3, "y": 3, "w": 50, "h": 8}]}}).json()
    uso(interno, doc["id"], p2["id"])
    if oc["oc"]["proveedor"] == "The North Face":
        t = trabajo(tnf, "OC", {**base, "prueba": True})
        assert "sin_plantilla" in problemas(t["registros"][0])


def test_lote_grande_y_tope(interno, oc, tipos, combinada, monkeypatch):
    linea = oc["lineas"][0]
    t = trabajo(interno, "OC", {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["manual"]["id"]], "posiciones": [linea["id"]]})
    t = cambiar(interno, t, {"cantidades": {t["registros"][0]["clave"]: 2000}})
    inicio = time.monotonic()
    r = generar(interno, t, aceptar_advertencias=True)
    # Desde cierto tamaño se genera en segundo plano
    assert r.status_code == 200 and r.json()["estado"] in ("GENERADO", "EN_PROCESO"), r.text
    assert time.monotonic() - inicio < 120
    from app.core.config import settings

    monkeypatch.setattr(settings, "ETIQUETAS_MAXIMO_TRABAJO", 100)
    t = trabajo(interno, "OC", {"oc_ids": [oc["oc"]["id"]], "tipos": [tipos["manual"]["id"]], "posiciones": [linea["id"]]})
    t = cambiar(interno, t, {"cantidades": {t["registros"][0]["clave"]: 200}})
    assert "lote_grande" in {p["codigo"] for p in t["resumen"]["problemas"]}


def test_alcance_del_proveedor(interno, tnf, vans, oc, tipos, combinada):
    propia = oc["oc"]
    cliente, otro = (vans, tnf) if propia["proveedor"] != "The North Face" else (tnf, vans)
    pedido = {"oc_ids": [propia["id"]], "tipos": [tipos["linea"]["id"]]}
    t = generado(cliente, trabajo(cliente, "OC", pedido))
    gen = t["ejecuciones"][0]
    assert otro.post("/etiquetas/trabajos", {"origen": "OC", "parametros": pedido}).status_code == 404
    assert otro.get(f"/etiquetas/generaciones/{gen['id']}").status_code == 404
    assert otro.get(f"/etiquetas/trabajos/{t['id']}").status_code == 404
    assert otro.get("/etiquetas/generaciones", params={"oc_id": propia["id"]}).json()["total"] == 0
