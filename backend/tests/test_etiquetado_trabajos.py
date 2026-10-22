"""Trabajos de etiquetado: un solo servicio para todas las entradas (varias
OC, artículos, lista de empaque), borrador que se retoma, concurrencia,
validación por registro con diseños distintos en el mismo trabajo (diseño
normal y excepción por condición), errores que bloquean salvo generación
parcial, reintento de lo que faltó, generación en segundo plano con avance,
ZIP con carpetas y nombres configurables sin colisiones y con resumen,
impresión solo con confirmación, alcance del proveedor, idempotencia y la
migración de las reglas anteriores a usos de diseño."""
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

import pdfplumber
import pytest
from etiquetado_util import aprobada, articulo_de, tipo, uso

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion
from app.modelos.base import ahora
from app.modulos.etiquetado import trabajos

ELEMENTOS = [{"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 3, "w": 70, "h": 8, "estilo": {"tam": 10}},
             {"id": "bc", "tipo": "codigo", "simbologia": "code128", "x": 3, "y": 13, "w": 74, "h": 15, "margen": 1,
              "partes": [{"campo": "articulo.sku"}]}]


def _aprobada(interno, admin, nombre, tipo_id, variables=None):
    return aprobada(interno, admin, nombre, tipo_id, ELEMENTOS, ancho=80, alto=30, variables=variables or [])


@pytest.fixture(scope="module")
def ordenes(interno):
    """Dos OC de TNF con artículos en sus líneas."""
    res = []
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        d = interno.get(f"/ordenes/{o['id']}").json()
        lineas = [x for x in d["posiciones"] if x.get("codigo_articulo")]
        if d["oc"]["proveedor"] == "The North Face" and d["oc"]["estado"] != "BORRADOR" and len(lineas) >= 2:
            res.append({"oc": d["oc"], "lineas": lineas})
        if len(res) == 2:
            return res
    pytest.skip("two TNF POs with items are needed")


@pytest.fixture(scope="module")
def job(interno):
    """El tipo de etiqueta de estas pruebas (una por línea) y el de cantidad manual."""
    return {"linea": tipo(interno, "JOB_LINEA", cantidad="POR_LINEA"), "manual": tipo(interno, "JOB_MANUAL", cantidad="MANUAL")}


@pytest.fixture(scope="module")
def disenos(interno, admin, ordenes, job):
    """Diseño normal de toda la empresa (pide un dato al generar) y una excepción
    por condición: la primera línea de cada OC lleva otro diseño."""
    a = _aprobada(interno, admin, "Job design first lines", job["linea"]["id"])
    b = _aprobada(interno, admin, "Job design other lines", job["linea"]["id"],
                  variables=[{"clave": "lote", "etiqueta": "Batch", "obligatorio": True}])
    normal = uso(interno, job["linea"]["id"], b["id"])
    primeras = [o["lineas"][0]["posicion"] for o in ordenes]
    exc = uso(interno, job["linea"]["id"], a["id"], contexto_tipo="CONDICION", reemplazar=False, motivo="First lines",
              condiciones=[{"campo": "linea.posicion", "op": "en", "valor": primeras}])
    for t in ("manual",):
        uso(interno, job[t]["id"], _aprobada(interno, admin, f"Job design {t}", job[t]["id"])["id"])
    yield a, b, normal, exc
    for u in (exc, normal):
        interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "End of the test"})


@pytest.fixture
def reglas_empresa(admin):
    antes = {r["clave"]: r["valor"] for r in admin.get("/organizacion").json()["reglas"]}
    yield lambda **kw: admin.put("/organizacion", {"reglas": kw})
    admin.put("/organizacion", {"reglas": {k: antes[k] for k in ("ETIQUETAS_GENERACION_PARCIAL", "ETIQUETAS_ASINCRONO_DESDE")}})


def _esperar(interno, tid, segundos=90):
    fin = time.time() + segundos
    while time.time() < fin:
        e = interno.get(f"/etiquetas/trabajos/{tid}/estado").json()
        if e["estado"] != "EN_PROCESO":
            return e
        time.sleep(0.3)
    raise AssertionError("the job did not finish")


def test_trabajo_de_varias_oc_borrador_mezcla_parcial_y_reintento(interno, admin, tnf, ordenes, job, disenos, reglas_empresa):
    oc_ids = [o["oc"]["id"] for o in ordenes]
    lineas = [x["id"] for o in ordenes for x in o["lineas"][:2]]
    tipos = [job["linea"]["id"]]
    r = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": oc_ids, "posiciones": lineas, "tipos": tipos}},
                     clave="job-1")
    assert r.status_code == 200, r.text
    t = r.json()
    # Idempotencia: la misma petición no crea otro trabajo
    assert interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": oc_ids, "tipos": tipos}},
                        clave="job-1").json()["id"] == t["id"]
    assert t["estado"] == "BORRADOR" and t["parametros"]["oc_ids"] == oc_ids
    # Borrador: se guarda el paso y se retoma; con la versión vieja, conflicto
    r = interno.patch(f"/etiquetas/trabajos/{t['id']}", {"paso": 3, "version": t["version"], "parametros": {"formato": "PDF"}})
    assert r.status_code == 200, r.text
    assert interno.get(f"/etiquetas/trabajos/{t['id']}").json()["paso"] == 3
    assert interno.patch(f"/etiquetas/trabajos/{t['id']}", {"paso": 4, "version": t["version"]}).status_code == 409
    assert any(x["id"] == t["id"] for x in interno.get("/etiquetas/trabajos", params={"estado": "BORRADOR"}).json()["items"])
    # Alcance: el proveedor no ve el trabajo de otro
    assert tnf.get(f"/etiquetas/trabajos/{t['id']}").status_code == 404

    v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
    assert v["estado"] == "VALIDADO" and len(v["registros"]) == 4
    por_diseno = {}
    for x in v["registros"]:
        por_diseno.setdefault(x["plantilla"], []).append(x)
    # Diseños distintos en el mismo trabajo, cada registro con el uso de diseño que lo eligió (normal o excepción)
    assert set(por_diseno) == {"Job design first lines", "Job design other lines"}
    assert {x["uso_id"] for x in por_diseno["Job design first lines"]} == {disenos[3]["id"]}
    assert {x["uso_id"] for x in por_diseno["Job design other lines"]} == {disenos[2]["id"]}
    assert all(x["motivo"].startswith("Whole company, exception") for x in por_diseno["Job design first lines"])
    assert {d["plantilla"] for d in v["resumen"]["disenos"]} == set(por_diseno)
    # Los de un diseño piden un dato obligatorio: error clasificado
    otros = por_diseno["Job design other lines"]
    assert all(x["estado"] == "ERROR" and any(p["categoria"] == "dato_obligatorio" for p in x["problemas"]) for x in otros)
    assert v["resumen"]["conteo"]["ERROR"] == 2
    # Vista previa de un registro con sus datos reales
    pv = interno.get(f"/etiquetas/trabajos/{t['id']}/registros/{por_diseno['Job design first lines'][0]['id']}/vista-previa").json()
    assert pv["svg"].startswith("<svg") and pv["plantilla"] == "Job design first lines" and pv["valores"]["articulo.sku"]

    # Con errores no se genera; la generación parcial solo si la empresa la permite
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True}).status_code == 422
    reglas_empresa(ETIQUETAS_GENERACION_PARCIAL=False)
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True, "parcial": True}).status_code == 422
    reglas_empresa(ETIQUETAS_GENERACION_PARCIAL=True)
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True, "parcial": True})
    assert g.status_code == 200, g.text
    g = g.json()
    assert g["estado"] == "PARCIAL" and len(g["ejecuciones"]) == 2  # una por OC
    hechos = [x for x in g["registros"] if x["estado"] == "GENERADO"]
    assert {x["plantilla"] for x in hechos} == {"Job design first lines"} and all(x["generacion_id"] for x in hechos)
    # Reintento: con el dato escrito se generan solo los que faltaban
    interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"manuales": {"lote": "B-77"}}})
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True}).json()
    assert g["estado"] == "GENERADO" and len(g["ejecuciones"]) == 4
    assert all(x["estado"] == "GENERADO" for x in g["registros"])
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {}).status_code == 409  # ya está todo

    # ZIP con carpetas por OC y diseño, nombres configurados, sin colisiones y con resumen
    interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"zip": {"carpetas": ["oc", "plantilla"], "nombre": "{sku}",
                                                                              "contenido": "PNG"}}})
    assert interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"zip": {"nombre": "{nope}"}}}).status_code == 422
    z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/trabajos/{t['id']}/archivo").content))
    nombres = z.namelist()
    pngs = [n for n in nombres if n.endswith(".png")]
    assert len(pngs) == 4 and len(set(pngs)) == 4
    assert {n.split("/")[0] for n in pngs} == {o["oc"]["numero"] for o in ordenes}
    assert {n.split("/")[1] for n in pngs} == {"Job design first lines", "Job design other lines"}
    resumen = json.loads(z.read("summary.json"))
    assert resumen["etiquetas"] == 4 and len(resumen["registros"]) == 4 and "summary.csv" in nombres
    # Mismo nombre para todas: se numeran sin pisarse
    interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"zip": {"nombre": "label", "contenido": "SVG"}}})
    z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/trabajos/{t['id']}/archivo").content))
    assert sorted(n for n in z.namelist() if n.endswith(".svg")) == ["label-2.svg", "label-3.svg", "label-4.svg", "label.svg"]

    # PDF: el usuario elige cómo se reparten las etiquetas en archivos; sin mezclar diseños salvo que lo pida
    def pdfs(zip_):
        r = interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"zip": zip_}})
        assert r.status_code == 200, r.text
        z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/trabajos/{t['id']}/archivo").content))
        return {n: len(pdfplumber.open(io.BytesIO(z.read(n))).pages) for n in z.namelist() if n.endswith(".pdf")}

    v1 = {d: f"{d}-v{por_diseno[d][0]['version']}.pdf" for d in por_diseno}
    assert pdfs({"contenido": "PDF", "agrupar": "plantilla"}) == {v1[d]: len(por_diseno[d]) for d in por_diseno}
    assert pdfs({"contenido": "PDF", "agrupar": "unico"}) == {f"{trabajos._seguro(t['nombre'])}.pdf": 4}
    por_etiqueta = pdfs({"contenido": "PDF", "agrupar": "etiqueta", "carpetas": ["oc"], "nombre": "{sku}-{n}"})
    assert len(por_etiqueta) == 4 and set(por_etiqueta.values()) == {1}
    assert {n.split("/")[0] for n in por_etiqueta} == {o["oc"]["numero"] for o in ordenes}
    # Por carpeta (OC): si una carpeta tiene dos diseños, un PDF por diseño dentro de ella
    por_carpeta = pdfs({"contenido": "PDF", "agrupar": "carpeta", "carpetas": ["oc"]})
    assert sum(por_carpeta.values()) == 4
    for ruta in por_carpeta:
        carpeta, archivo = ruta.split("/")
        oc_id = next(o["oc"]["id"] for o in ordenes if o["oc"]["numero"] == carpeta)
        disenos = {x["plantilla"] for x in v["registros"] if x["oc_id"] == oc_id}
        assert archivo == (f"{carpeta}.pdf" if len(disenos) == 1 else next(f"{carpeta}-{v1[d]}" for d in disenos if archivo.endswith(v1[d])))
    # Combinaciones sin sentido: 422 con el motivo
    for malo in ({"contenido": "PNG", "agrupar": "plantilla"}, {"contenido": "PDF", "agrupar": "carpeta"},
                 {"contenido": "PDF", "agrupar": "unico", "carpetas": ["oc"]}, {"contenido": "PDF", "agrupar": "todo"}):
        assert interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"zip": malo}}).status_code == 422, malo
    # Trabajos anteriores sin agrupación elegida: un PDF por plantilla y versión (antes iba todo en un PDF mezclado)
    with SessionLocal() as db, en_organizacion(1):
        from app.modelos import TrabajoEtiquetas

        tr = db.get(TrabajoEtiquetas, t["id"])
        tr.parametros = {**tr.parametros, "zip": {"carpetas": [], "nombre": "", "contenido": "PDF"}}
        db.commit()
    z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/trabajos/{t['id']}/archivo").content))
    assert sorted(n for n in z.namelist() if n.endswith(".pdf")) == sorted(v1.values())

    # Generado ≠ descargado ≠ impreso: impreso solo con confirmación expresa
    e = interno.get(f"/etiquetas/trabajos/{t['id']}").json()["ejecuciones"][0]
    assert e["situacion"] == "DESCARGADA" and e["descargas"] >= 1
    assert interno.post(f"/etiquetas/generaciones/{e['id']}/impresion", {"cantidad": e["total"]}).status_code == 422
    if e["total"] > 1:
        assert interno.post(f"/etiquetas/generaciones/{e['id']}/impresion",
                            {"confirmo": True, "cantidad": e["total"] - 1}).status_code == 422
    r = interno.post(f"/etiquetas/generaciones/{e['id']}/impresion", {"confirmo": True, "cantidad": e["total"], "impresora": "Zebra 1"})
    assert r.status_code == 200, r.text
    assert r.json()["situacion"] == "IMPRESA" and r.json()["impresion"]["impresora"] == "Zebra 1"


def test_entradas_articulos_y_lista_de_empaque_usan_el_mismo_servicio(interno, admin, ordenes, job, disenos):
    # Artículos: el mismo artículo sin OC; su diseño es el normal de toda la empresa (la excepción mira la línea de OC)
    articulos = [{"articulo_id": articulo_de(x["id"]), "cantidad": 2} for x in ordenes[0]["lineas"][:2]]
    t = interno.post("/etiquetas/trabajos", {"origen": "ARTICULOS", "parametros": {"articulos": articulos, "tipos": [job["linea"]["id"]]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
    # Una por artículo (el tipo es «una por línea»); la cantidad escrita vale para los tipos por unidad o manuales
    assert len(v["registros"]) == 2 and all(x["cantidad"] == 1 for x in v["registros"])
    assert {x["plantilla"] for x in v["registros"]} == {"Job design other lines"}
    m = interno.post("/etiquetas/trabajos", {"origen": "ARTICULOS", "parametros": {"articulos": articulos, "tipos": [job["manual"]["id"]]}}).json()
    m = interno.post(f"/etiquetas/trabajos/{m['id']}/validar").json()
    assert [x["cantidad"] for x in m["registros"]] == [2, 2]
    # Elegido por el usuario para este trabajo (sin cambiar los usos)
    interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"elegidas": {x["clave"]: disenos[0]["id"] for x in v["registros"]}},
                                                    "version": v["version"]})
    v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
    assert {x["plantilla"] for x in v["registros"]} == {"Job design first lines"}
    assert all(x["motivo"] == "Chosen by the user for this job." for x in v["registros"])
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True, "version": v["version"]})
    assert g.status_code == 200, g.text
    assert g.json()["estado"] == "GENERADO"
    # Un tipo de caja no se imprime desde artículos sueltos
    caja = tipo(interno, "JOB_CAJA", sujeto="BULTO", cantidad="POR_BULTO")
    r = interno.post("/etiquetas/trabajos", {"origen": "ARTICULOS", "parametros": {"articulos": articulos, "tipos": [caja["id"]]}})
    assert r.status_code == 422
    # Lista de empaque: un registro por bulto superior, cada uno con su lista de empaque
    pls = interno.get("/etiquetas/packing").json()
    con = [x for x in pls if interno.get(f"/etiquetas/packing/{x['id']}").json()["superiores"] and x["etiquetas_reales"]]
    if not con:
        pytest.skip("no packing lists with packages")
    pl = con[0]
    uso(interno, caja["id"], aprobada(interno, admin, "Job carton", caja["id"], [
        {"id": "b", "tipo": "texto", "contenido": "{{bulto.numero}}/{{bulto.total}}", "x": 3, "y": 3, "w": 60, "h": 8}])["id"])
    t = interno.post("/etiquetas/trabajos", {"origen": "PACKING", "parametros": {"pl_id": pl["id"], "tipos": [caja["id"]]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
    superiores = interno.get(f"/etiquetas/packing/{pl['id']}").json()["superiores"]
    assert len(v["registros"]) == superiores and all(x["pl_id"] == pl["id"] for x in v["registros"])
    assert {x["plantilla"] for x in v["registros"]} == {"Job carton"} and all(x["cantidad"] == 1 for x in v["registros"])
    # La clave de cada bulto lleva su lista de empaque (dos listas de la misma OC no chocan: E1)
    assert all(f"-pl{pl['id']}-" in x["clave"] for x in v["registros"])
    # Cancelar un borrador
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/cancelar").json()["estado"] == "CANCELADO"
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/validar").status_code == 409


def test_generacion_en_segundo_plano_con_avance(interno, ordenes, job, disenos, reglas_empresa):
    o = ordenes[0]
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {
        "oc_ids": [o["oc"]["id"]], "posiciones": [o["lineas"][0]["id"]], "tipos": [job["manual"]["id"]]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
    v = interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"cantidades": {v["registros"][0]["clave"]: 6}},
                                                        "version": v["version"]}).json()
    reglas_empresa(ETIQUETAS_ASINCRONO_DESDE=5)
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True})
    assert g.status_code == 200, g.text
    assert g.json()["asincrono"] is True and g.json()["estado"] in ("EN_PROCESO", "GENERADO")
    fin = _esperar(interno, t["id"])
    assert fin["estado"] == "GENERADO" and fin["progreso"] == 6 and fin["error"] is None
    d = interno.get(f"/etiquetas/trabajos/{t['id']}").json()
    assert sum(e["total"] for e in d["ejecuciones"]) == 6


def test_proveedor_solo_con_sus_ordenes(vans, ordenes, job):
    # Una OC de otro proveedor no se puede poner en un trabajo
    r = vans.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [ordenes[0]["oc"]["id"]], "tipos": [job["linea"]["id"]]}})
    assert r.status_code == 404


# Reglas de la versión anterior (0075) de cada ámbito, con lo que cada una debe dar en usos de diseño
_REGLAS = [  # id, plantilla, ambito, familia, articulo, oc, prioridad, activa, condiciones, contexto, desde, hasta
    (1, 1, "GENERAL", None, None, None, 100, 1, [], {}, None, None),
    (2, 2, "GENERAL", None, None, None, 100, 1, [], {}, None, None),  # mismo tipo y lugar que 1: queda de baja
    (3, 1, "FAMILIA", 1, None, None, 200, 1, [], {}, None, None),
    (4, 3, "OC", None, None, 7, 500, 1, [], {}, None, None),
    (5, 1, "REGLA", None, None, None, 250, 1, [{"campo": "producto.dato.MARCA", "op": "igual", "valor": "TNF"}], {}, None, None),
    (6, 4, "FAMILIA", 1, None, None, 200, 1, [], {}, None, None),  # caja por familia: de baja
    (7, 5, "GENERAL", None, None, None, 100, 0, [], {}, None, None),  # inactiva: de baja
    (8, 4, "GENERAL", None, None, None, 100, 1, [], {"tipos_empaque": ["MASTER", "NOEXISTE"]}, None, None),
    (9, 1, "ARTICULO", None, 33, None, 400, 1, [], {}, "2026-01-01", "2026-12-31"),  # vigencia → excepción por condición
]


def _sembrar_0075(ruta):
    c = sqlite3.connect(ruta)
    c.execute("PRAGMA foreign_keys=OFF")
    q = c.execute
    q("INSERT OR IGNORE INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en) VALUES (1, 'O1', 'Org', '{}', 1, '2026-01-01')")
    q("INSERT INTO familias_etiquetado (id, organizacion_id, codigo, nombre, campos, orden, activa, creada_en)"
      " VALUES (1, 1, 'CALZ', 'Calzado', '[]', 0, 1, '2026-01-01')")
    q("INSERT INTO tipos_empaque (id, organizacion_id, codigo, nombre, nivel, cuenta_como, contiene_productos, mezcla_productos,"
      " mezcla_tallas, mezcla_oc, activo) VALUES (901, 1, 'MASTER', 'Master', 2, 'BULTO', 1, 1, 1, 1, 1)")
    for i, n, m, u in ((1, "Hang", "ARTICULO", "UNIDAD"), (2, "Hang PO", "OC_ARTICULO", "UNIDAD"), (3, "Line", "OC_ARTICULO", "LINEA"),
                       (4, "Carton", "OC_ARTICULO", "BULTO"), (5, "Content", "OC", "ORDEN")):
        q("INSERT INTO plantillas_etiqueta (id, organizacion_id, nombre, modalidad, unidad, estado, creada_en, actualizada_en)"
          " VALUES (?, 1, ?, ?, ?, 'ACTIVA', '2026-01-01', '2026-01-01')", (i, n, m, u))
    for r in _REGLAS:
        q("INSERT INTO asignaciones_etiqueta (id, organizacion_id, plantilla_id, ambito, familia_id, articulo_id, oc_id, prioridad,"
          " predeterminada, activa, condiciones, contexto, vigente_desde, vigente_hasta, creada_en, nombre, version)"
          " VALUES (?, 1, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, '2026-01-01', ?, 1)",
          (*r[:8], json.dumps(r[8]), json.dumps(r[9]), r[10], r[11], f"Rule {r[0]}"))
    q("INSERT INTO roles (id, organizacion_id, nombre, tipo, permisos, sistema, activo, datos_ocultos, inicio_oculto)"
      " VALUES (999, 1, 'AdminX', 'admin', ?, 1, 1, '[]', '[]')", (json.dumps(["etiquetas.asignar", "etiquetas.ver"]),))
    q("INSERT INTO proveedores (id, organizacion_id, codigo, nombre, activo, extra) VALUES (901, 1, 'P1', 'Prov', 1, '{}')")
    q("INSERT INTO ordenes_compra (id, organizacion_id, proveedor_id, numero, liberacion_comercial, liberacion_logistica, liberada,"
      " actualizado_en, extra, estado, origen, version) VALUES (7, 1, 901, '4500', 'L', 'L', 1, '2026-01-01', '{}', 'APROBADA', 'ERP', 1)")
    q("INSERT INTO marcas (id, organizacion_id, codigo, nombre, activa, extra) VALUES (901, 1, 'M1', 'Marca', 1, '{}')")
    cat = c.execute("SELECT codigo FROM categorias_articulo LIMIT 1").fetchone()
    if cat is None:
        q("INSERT INTO categorias_articulo (organizacion_id, codigo, nombre, activo) VALUES (1, 'CAT', 'Cat', 1)")
        cat = ("CAT",)
    q("INSERT INTO grupos_articulos (id, organizacion_id, codigo, nombre, categoria, activo) VALUES (901, 1, 'G1', 'Grupo', ?, 1)", cat)
    q("INSERT INTO articulos (id, organizacion_id, sku, estilo, marca_id, grupo_id, unidad, tipo, activo, extra)"
      " VALUES (33, 1, 'SKU1', 'E1', 901, 901, 'UN', 'SOLIDO', 1, '{}')")
    c.commit()
    c.close()


def test_migracion_convierte_las_reglas_en_tipos_y_usos_de_diseno():
    """0076: un tipo por cada (qué se etiqueta, cuántas) de los diseños; cada regla pasa a su lugar
    (o a excepción) sin perder nada: lo que ya no tiene lugar queda de baja con el motivo, y
    cada conversión queda en el historial. Revertir devuelve las reglas."""
    from test_oficial import RAIZ

    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        r = subprocess.run(alembic + ["upgrade", "0075"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _sembrar_0075(f"{tmp}/m.db")
        # Hasta 0091: 0092 deja la familia solo en el producto y quita usos_diseno.familia_id
        r = subprocess.run(alembic + ["upgrade", "0091"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        tipos = {t: (s, c) for t, s, c in con.execute("SELECT id, sujeto, cantidad FROM tipos_etiqueta")}
        assert sorted(tipos.values()) == [("ARTICULO", "POR_LINEA"), ("ARTICULO", "POR_UNIDAD"), ("BULTO", "POR_BULTO"),
                                          ("DOCUMENTO", "POR_DOCUMENTO")]
        usos = con.execute("SELECT plantilla_id, nivel, familia_id, articulo_id, tipo_empaque_id, contexto_tipo, oc_id,"
                           " eliminado_en IS NOT NULL FROM usos_diseno ORDER BY id").fetchall()
        vivos = {(u[0], u[1], u[5]) for u in usos if not u[7]}
        de_baja = {(u[0], u[1], u[5]) for u in usos if u[7]}
        # Los diseños 1 y 2 son del mismo tipo (una por unidad): en el mismo lugar queda el de la regla más antigua
        assert (1, "GENERAL", "NINGUNO") in vivos and (2, "GENERAL", "NINGUNO") in de_baja
        assert (1, "FAMILIA", "NINGUNO") in vivos and (3, "GENERAL", "OC") in vivos
        assert (1, "GENERAL", "CONDICION") in vivos and (1, "SKU", "CONDICION") in vivos
        assert (4, "TIPO_EMPAQUE", "NINGUNO") in vivos  # la caja MASTER
        assert (4, "FAMILIA", "NINGUNO") in de_baja and (5, "GENERAL", "NINGUNO") in de_baja
        assert any(u[0] == 4 and u[1] == "GENERAL" and u[7] for u in usos)  # tipo de empaque que no existe
        # Una sola fila normal viva por lugar
        celdas = [c for c, n in con.execute("SELECT celda, COUNT(*) FROM usos_diseno WHERE contexto_tipo = 'NINGUNO'"
                                            " AND eliminado_en IS NULL GROUP BY celda") if n > 1]
        assert celdas == []
        assert con.execute("SELECT COUNT(*) FROM historial WHERE entidad = 'uso_diseno' AND accion = 'migrar'").fetchone()[0] == len(usos)
        assert con.execute("SELECT permisos FROM roles WHERE id = 999").fetchone()[0].count("etiquetas.configurar") == 1
        assert not con.execute("SELECT name FROM sqlite_master WHERE name = 'asignaciones_etiqueta'").fetchall()
        con.close()
        r = subprocess.run(alembic + ["downgrade", "0075"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        assert con.execute("SELECT COUNT(*) FROM asignaciones_etiqueta WHERE activa = 1").fetchone()[0] >= 6
        assert con.execute("SELECT permisos FROM roles WHERE id = 999").fetchone()[0].count("etiquetas.asignar") == 1
        con.close()
        r = subprocess.run(alembic + ["upgrade", "0091"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


def test_generacion_interrumpida_se_puede_retomar(interno, ordenes, job, disenos):
    """Si el proceso que generaba en segundo plano se detuvo (reinicio), el
    trabajo no queda «generando» para siempre: se retoma lo pendiente."""
    from datetime import timedelta

    from app.modelos import TrabajoEtiquetas

    o = ordenes[1]
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [o["oc"]["id"]], "posiciones": [o["lineas"][0]["id"]],
                                                                           "tipos": [job["linea"]["id"]]}}).json()
    interno.post(f"/etiquetas/trabajos/{t['id']}/validar")
    with SessionLocal() as db, en_organizacion(1):
        x = db.get(TrabajoEtiquetas, t["id"])
        x.estado, x.actualizado_en = "EN_PROCESO", ahora()
        db.commit()
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True}).status_code == 409
    with SessionLocal() as db, en_organizacion(1):
        db.get(TrabajoEtiquetas, t["id"]).actualizado_en = ahora() - timedelta(minutes=30)
        db.commit()
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True})
    assert g.status_code == 200, g.text
    assert g.json()["estado"] == "GENERADO"


def _lienzo(ancho, alto):
    from app.modulos.etiquetado import render

    return render.componer({"ancho": ancho, "alto": alto, "margen": 1, "fondo": "#ffffff", "elementos": []}, {})


def test_un_solo_pdf_no_mezcla_medidas():
    """El PDF único se pide expresamente y exige que todas midan lo mismo."""
    from app.core.errores import ErrorNegocio

    etiquetas = [("", "a", _lienzo(80, 30), "A-v1"), ("", "b", _lienzo(50, 20), "B-v1")]
    with pytest.raises(ErrorNegocio) as e:
        trabajos._archivos_pdf(etiquetas, "unico", "job")
    assert e.value.status == 422 and "50×20 mm" in e.value.detalle[0]["mensaje"]
    assert [r for r, _ in trabajos._archivos_pdf(etiquetas, "plantilla", "job")] == ["A-v1.pdf", "B-v1.pdf"]


def test_hoja_con_etiquetas_de_medidas_distintas():
    """Varias por hoja: cada medida empieza su hoja (antes todas tomaban la
    celda de la primera y se encimaban) y la que no cabe no se dibuja."""
    from app.modulos.etiquetado import salidas

    hoja = {"modo": "hoja", "papel_ancho": 200, "papel_alto": 100, "columnas": 2, "filas": 1, "margen_sup": 5, "margen_izq": 5,
            "espacio_h": 2, "espacio_v": 2}
    assert len(pdfplumber.open(io.BytesIO(salidas.pdf([_lienzo(80, 30), _lienzo(50, 20)], hoja))).pages) == 2
    assert len(pdfplumber.open(io.BytesIO(salidas.pdf([_lienzo(50, 20), _lienzo(50, 20)], hoja))).pages) == 1
    with pytest.raises(ValueError):
        salidas.pdf([_lienzo(120, 30)], hoja)
