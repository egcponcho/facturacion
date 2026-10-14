"""Etiquetado: generación desde una OC con datos reales (línea, unidad,
bulto, cantidad manual), combinación de OC y artículo, plantillas por
familia, errores y advertencias, duplicados, lotes grandes, alcance del
proveedor, pruebas con versiones sin aprobar y reproducción exacta de un
lote histórico."""
import io
import time
import zipfile

import pdfplumber
import pytest
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


def _aprobada(interno, admin, nombre, modalidad, elementos, **kw):
    r = interno.post("/etiquetas/plantillas", {"nombre": nombre, "modalidad": modalidad, **kw,
                                               "diseno": {"ancho": 100, "alto": 50, "elementos": elementos}})
    assert r.status_code == 200, r.text
    p = r.json()
    v = p["versiones"][0]
    assert interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {}).status_code == 200
    assert admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {}).status_code == 200
    return interno.get(f"/etiquetas/plantillas/{p['id']}").json()


@pytest.fixture(scope="module")
def oc(interno):
    """Una OC de TNF con artículos en todas sus líneas."""
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        r = interno.get(f"/etiquetas/oc/{o['id']}").json()
        if o.get("proveedor_codigo", o.get("proveedor")) and r["lineas"] and all(x["articulo_id"] for x in r["lineas"]) \
                and len(r["lineas"]) >= 2:
            return r
    pytest.skip("no PO with items")


def test_sin_plantilla_aprobada_no_se_genera(interno, oc):
    p = interno.post("/etiquetas/plan", {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA"}).json()
    assert not p["puede_generar"] and all(g["problemas"][0]["codigo"] == "sin_plantilla" for g in p["grupos"])
    r = interno.post("/etiquetas/generaciones", {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA"})
    assert r.status_code == 422 and r.json()["codigo"] == "etiquetas_con_errores"


@pytest.fixture(scope="module")
def combinada(interno, admin, oc):
    p = _aprobada(interno, admin, "Combined PO and item label", "OC_ARTICULO", COMBINADA)
    assert interno.post("/etiquetas/asignaciones", {"plantilla_id": p["id"], "ambito": "GENERAL"}).status_code == 200
    return p


def _pdf(contenido):
    with pdfplumber.open(io.BytesIO(contenido)) as doc:
        return [(pg.width, pg.height, pg.extract_text()) for pg in doc.pages]


def test_generar_por_linea_unidad_y_manual(interno, oc, combinada):
    base = {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO"}
    lineas = [x for x in oc["lineas"] if not x["bloqueada"]]
    plan = interno.post("/etiquetas/plan", {**base, "unidad": "LINEA"}).json()
    assert plan["puede_generar"], plan
    assert plan["total"] == len(lineas) and {g["plantilla"] for g in plan["grupos"]} == {"Combined PO and item label"}
    assert all(g["version"] == 1 and g["nivel"] == "GENERAL" for g in plan["grupos"])
    # Por unidad: una etiqueta por cada unidad pedida de cada línea
    unidad = interno.post("/etiquetas/plan", {**base, "unidad": "UNIDAD", "posiciones": [lineas[0]["id"], lineas[1]["id"]]}).json()
    assert [g["cantidad"] for g in unidad["grupos"]] == [int(lineas[0]["cantidad"]), int(lineas[1]["cantidad"])]
    assert unidad["total"] == int(lineas[0]["cantidad"]) + int(lineas[1]["cantidad"])
    # Manual: cantidades distintas por línea
    manual = {"unidad": "MANUAL", "posiciones": [lineas[0]["id"], lineas[1]["id"]],
              "cantidades": {str(lineas[0]["id"]): 3, str(lineas[1]["id"]): 2}}
    plan = interno.post("/etiquetas/plan", {**base, **manual}).json()
    assert plan["total"] == 5
    # Los artículos sin familia de etiquetado dan una advertencia que hay que aceptar expresamente
    assert interno.post("/etiquetas/generaciones", {**base, **manual, "formato": "PDF"}).status_code == 409
    r = interno.post("/etiquetas/generaciones", {**base, **manual, "formato": "PDF", "aceptar_advertencias": True})
    assert r.status_code == 200, r.text
    gen = r.json()
    assert gen["total"] == 5 and gen["versiones"][0]["version"] == 1 and gen["estado"] == "GENERADA"
    arch = interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo")
    assert arch.status_code == 200 and arch.headers["x-identico"] == "1"
    paginas = _pdf(arch.content)
    assert len(paginas) == 5
    # Datos combinados: la OC y el artículo de cada línea, numeración n/N por grupo
    assert all(abs(w - 100 * 72 / 25.4) < 0.01 and abs(h - 50 * 72 / 25.4) < 0.01 for w, h, _ in paginas)
    assert all(f"PO {oc['oc']['numero']}" in t for _, _, t in paginas)
    assert lineas[0]["codigo"] in paginas[0][2] and "1/3" in paginas[0][2] and "3/3" in paginas[2][2]
    assert lineas[1]["codigo"] in paginas[3][2] and "2/2" in paginas[4][2]


def test_zip_con_png_y_svg_y_codigo_legible(interno, oc, combinada):
    linea = oc["lineas"][0]
    r = interno.post("/etiquetas/generaciones", {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA",
                                                 "posiciones": [linea["id"]], "formato": "ZIP", "aceptar_advertencias": True})
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/generaciones/{r.json()['id']}/archivo").content))
    nombres = z.namelist()
    assert any(n.endswith(".pdf") for n in nombres) and "lote.json" in nombres
    pngs = [n for n in nombres if n.startswith("png/")]
    assert len(pngs) == 1 and len([n for n in nombres if n.startswith("svg/")]) == 1
    with Image.open(io.BytesIO(z.read(pngs[0]))) as im:
        assert im.size == (1181, 591)
        leidos = [x.text for x in zxingcpp.read_barcodes(im.convert("L"))]
    with SessionLocal() as db, en_organizacion(1):
        from app.modelos import PosicionOC

        sku = db.get(PosicionOC, linea["id"]).articulo.sku
    assert sku in leidos


def test_familia_con_dato_obligatorio_y_plantilla_de_familia(interno, admin, oc, combinada):
    linea = oc["lineas"][0]
    fam = interno.post("/etiquetas/familias", {"codigo": "GENFAM", "nombre": "Generation family",
                                               "campos": [{"campo": "articulo.extra.no_existe_aun", "obligatorio": True}]})
    assert fam.status_code == 422  # un campo que no existe no se acepta
    fam = interno.post("/etiquetas/familias", {"codigo": "GENFAM", "nombre": "Generation family",
                                               "campos": [{"campo": "producto.uso", "obligatorio": True}]}).json()
    interno.post("/etiquetas/articulos/familia", {"familia_id": fam["id"], "ids": [linea["articulo_id"]]})
    de_familia = _aprobada(interno, admin, "Generation family label", "OC_ARTICULO",
                           [c for c in COMBINADA if c["id"] != "talla"], familia_id=fam["id"])
    interno.post("/etiquetas/asignaciones", {"plantilla_id": de_familia["id"], "ambito": "FAMILIA", "familia_id": fam["id"]})
    with SessionLocal() as db, en_organizacion(1):
        from app.modelos import Articulo

        a = db.get(Articulo, linea["articulo_id"])
        uso = (a.producto.ficha or {}).get("uso") if a.producto else None
    plan = interno.post("/etiquetas/plan", {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA",
                                            "posiciones": [linea["id"], oc["lineas"][1]["id"]]}).json()
    g0, g1 = plan["grupos"]
    assert g0["plantilla"] == "Generation family label" and g0["nivel"] == "FAMILIA" and g0["familia"] == "Generation family"
    assert g1["plantilla"] == "Combined PO and item label" or oc["lineas"][1]["articulo_id"] == linea["articulo_id"]
    if not uso:
        assert {p["codigo"] for p in g0["problemas"] if p["nivel"] == "error"} == {"dato_obligatorio"}
    # Se deja la familia como estaba para las demás pruebas
    interno.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [linea["articulo_id"]]})


def test_advertencias_y_duplicados_piden_confirmar(interno, oc, combinada):
    linea = oc["lineas"][-1]
    pedido = {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA", "posiciones": [linea["id"]],
              "formato": "PDF", "aceptar_advertencias": True}
    assert interno.post("/etiquetas/generaciones", pedido).status_code == 200
    plan = interno.post("/etiquetas/plan", pedido).json()
    assert "ya_generada" in {p["codigo"] for p in plan["grupos"][0]["problemas"]} and plan["puede_generar"]
    sin_aceptar = interno.post("/etiquetas/generaciones", {**pedido, "aceptar_advertencias": False})
    assert sin_aceptar.status_code == 409 and sin_aceptar.json()["codigo"] == "confirmar_advertencias"
    assert interno.post("/etiquetas/generaciones", pedido).status_code == 200


def test_unidad_no_contable(interno, oc, combinada):
    linea = oc["lineas"][0]
    with SessionLocal() as db, en_organizacion(1):
        from app.modelos import PosicionOC

        p = db.get(PosicionOC, linea["id"])
        antes = p.unidad
        p.unidad = "KG"
        db.commit()
    try:
        plan = interno.post("/etiquetas/plan", {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "UNIDAD",
                                                "posiciones": [linea["id"]]}).json()
        assert "unidad_no_contable" in {x["codigo"] for x in plan["grupos"][0]["problemas"]} and not plan["puede_generar"]
    finally:
        with SessionLocal() as db, en_organizacion(1):
            db.get(PosicionOC, linea["id"]).unidad = antes
            db.commit()


def test_reproducir_un_lote_historico_sin_cambiar_version_ni_datos(interno, admin, oc, combinada):
    linea = oc["lineas"][0]
    pedido = {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA", "posiciones": [linea["id"]],
              "formato": "PDF", "aceptar_advertencias": True}
    gen = interno.post("/etiquetas/generaciones", pedido).json()
    original = interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo").content
    # Cambia el diseño (versión 2 aprobada) y cambian los datos del artículo
    v2 = interno.post(f"/etiquetas/plantillas/{combinada['id']}/versiones", {}).json()
    v2["diseno"]["fondo"] = "#fff3e0"
    v2["diseno"]["elementos"][0]["prefijo"] = "ORDER "
    interno.put(f"/etiquetas/versiones/{v2['id']}/diseno", {"diseno": v2["diseno"]})
    interno.post(f"/etiquetas/versiones/{v2['id']}/enviar", {})
    admin.post(f"/etiquetas/versiones/{v2['id']}/aprobar", {})
    with SessionLocal() as db, en_organizacion(1):
        from app.modelos import Articulo

        a = db.get(Articulo, linea["articulo_id"])
        talla_antes, a.talla = a.talla, "ZZ"
        db.commit()
    try:
        r = interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo")
        assert r.headers["x-identico"] == "1" and r.content == original
        texto = _pdf(r.content)[0][2]
        assert f"PO {oc['oc']['numero']}" in texto and "ORDER" not in texto and "ZZ" not in texto
        detalle = interno.get(f"/etiquetas/generaciones/{gen['id']}").json()
        assert detalle["versiones"][0]["version"] == 1 and detalle["items"][0]["valores"]["articulo.talla"] == talla_antes
        # Una generación nueva usa la versión 2 y los datos actuales
        nueva = interno.post("/etiquetas/generaciones", pedido).json()
        assert nueva["versiones"][0]["version"] == 2
        texto = _pdf(interno.get(f"/etiquetas/generaciones/{nueva['id']}/archivo").content)[0][2]
        assert "ORDER" in texto and "Size ZZ" in texto
    finally:
        with SessionLocal() as db, en_organizacion(1):
            db.get(Articulo, linea["articulo_id"]).talla = talla_antes
            db.commit()
    # Historial con filtros
    h = interno.get("/etiquetas/generaciones", params={"oc_id": oc["oc"]["id"], "version_id": combinada["vigente"]["id"]}).json()
    assert gen["id"] in {x["id"] for x in h["items"]}
    assert interno.get("/etiquetas/generaciones", params={"articulo_id": linea["articulo_id"]}).json()["total"] >= 2


def test_prueba_con_version_sin_aprobar(interno, tnf, oc):
    p = interno.post("/etiquetas/plantillas", {"nombre": "Draft PO label", "modalidad": "OC", "diseno": {
        "ancho": 60, "alto": 30, "elementos": [{"id": "n", "tipo": "campo", "campo": "oc.numero", "x": 3, "y": 3, "w": 50, "h": 8}]}}).json()
    pedido = {"oc_id": oc["oc"]["id"], "modalidad": "OC", "unidad": "ORDEN", "plantilla_id": p["id"], "formato": "PDF"}
    assert interno.post("/etiquetas/plan", pedido).json()["grupos"][0]["problemas"][0]["codigo"] == "sin_plantilla"
    r = interno.post("/etiquetas/generaciones", {**pedido, "prueba": True, "aceptar_advertencias": True})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "PRUEBA"
    with pdfplumber.open(io.BytesIO(interno.get(f"/etiquetas/generaciones/{r.json()['id']}/archivo").content)) as doc:
        letras = "".join(c["text"] for c in doc.pages[0].chars)
    assert "TEST·NOTAPPROVED" in letras.replace(" ", "") and oc["oc"]["numero"] in letras
    # Un proveedor no prueba versiones sin aprobar
    assert tnf.post("/etiquetas/plan", {**pedido, "prueba": True}).status_code == 403


def test_por_bulto_desde_las_listas_de_empaque(interno, admin):
    con_bultos = None
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        r = interno.get(f"/etiquetas/oc/{o['id']}").json()
        if r["bultos"]:
            con_bultos = r
            break
    if not con_bultos:
        pytest.skip("no packing lists with packages")
    p = _aprobada(interno, admin, "Package label", "OC", [
        {"id": "oc", "tipo": "campo", "campo": "oc.numero", "x": 3, "y": 3, "w": 60, "h": 8},
        {"id": "b", "tipo": "texto", "contenido": "Package {{bulto.numero}} of {{bulto.total}} · {{bulto.packing_list}}",
         "x": 3, "y": 14, "w": 90, "h": 8},
        {"id": "c", "tipo": "campo", "campo": "bulto.contenido", "x": 3, "y": 24, "w": 90, "h": 20,
         "estilo": {"tam": 7, "multilinea": True}}])
    pedido = {"oc_id": con_bultos["oc"]["id"], "modalidad": "OC", "unidad": "BULTO", "plantilla_id": p["id"], "formato": "PDF",
              "aceptar_advertencias": True}
    plan = interno.post("/etiquetas/plan", pedido).json()
    assert plan["total"] == con_bultos["bultos"] and plan["puede_generar"]
    gen = interno.post("/etiquetas/generaciones", pedido).json()
    paginas = _pdf(interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo").content)
    assert len(paginas) == con_bultos["bultos"] and "Package 1 of" in paginas[0][2]


def test_lote_grande_y_tope(interno, oc, combinada, monkeypatch):
    linea = oc["lineas"][0]
    pedido = {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "MANUAL", "posiciones": [linea["id"]],
              "cantidades": {str(linea["id"]): 2000}, "formato": "PDF", "aceptar_advertencias": True}
    inicio = time.monotonic()
    gen = interno.post("/etiquetas/generaciones", pedido)
    assert gen.status_code == 200, gen.text
    assert gen.json()["total"] == 2000 and time.monotonic() - inicio < 120
    from app.core.config import settings

    monkeypatch.setattr(settings, "ETIQUETAS_MAXIMO_LOTE", 100)
    r = interno.post("/etiquetas/plan", pedido).json()
    assert not r["puede_generar"] and r["problemas"][0]["codigo"] == "lote_grande"


def test_alcance_del_proveedor(interno, tnf, vans, oc, combinada):
    propia = oc["oc"]
    if propia["proveedor"] != "The North Face":
        cliente, otro = vans, tnf
    else:
        cliente, otro = tnf, vans
    pedido = {"oc_id": propia["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA", "formato": "PDF", "aceptar_advertencias": True}
    r = cliente.post("/etiquetas/generaciones", pedido)
    assert r.status_code == 200, r.text
    assert otro.post("/etiquetas/plan", pedido).status_code == 404
    assert otro.get(f"/etiquetas/generaciones/{r.json()['id']}").status_code == 404
    assert all(g["oc_id"] == propia["id"] or g["creada_por"] for g in cliente.get("/etiquetas/generaciones").json()["items"])
    assert otro.get("/etiquetas/generaciones", params={"oc_id": propia["id"]}).json()["total"] == 0
