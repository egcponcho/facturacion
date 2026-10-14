"""Trabajos de etiquetado: un solo servicio para todas las entradas (varias
OC, artículos, lista de empaque), borrador que se retoma, concurrencia,
validación por registro con diseños distintos en el mismo trabajo, errores
que bloquean salvo generación parcial, reintento de lo que faltó, generación
en segundo plano con avance, ZIP con carpetas y nombres configurables sin
colisiones y con resumen, impresión solo con confirmación, alcance del
proveedor, idempotencia y la migración de las asignaciones a reglas."""
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

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion
from app.modulos.etiquetado import trabajos

ELEMENTOS = [{"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 3, "w": 70, "h": 8, "estilo": {"tam": 10}},
             {"id": "bc", "tipo": "codigo", "simbologia": "code128", "x": 3, "y": 13, "w": 74, "h": 15, "margen": 1,
              "partes": [{"campo": "articulo.sku"}]}]


def _aprobada(interno, admin, nombre, modalidad="OC_ARTICULO", variables=None):
    r = interno.post("/etiquetas/plantillas", {"nombre": nombre, "modalidad": modalidad,
                                               "diseno": {"ancho": 80, "alto": 30, "elementos": ELEMENTOS,
                                                          "variables": variables or []}})
    assert r.status_code == 200, r.text
    v = r.json()["versiones"][0]
    assert interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {}).status_code == 200
    assert admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {}).status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def ordenes(interno):
    """Dos OC de TNF con artículos en sus líneas."""
    res = []
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        r = interno.get(f"/etiquetas/oc/{o['id']}").json()
        lineas = [x for x in r["lineas"] if x["articulo_id"] and not x["bloqueada"]]
        if r["oc"]["proveedor"] == "The North Face" and len(lineas) >= 2:
            res.append({**r, "lineas": lineas})
        if len(res) == 2:
            return res
    pytest.skip("two TNF POs with items are needed")


@pytest.fixture(scope="module")
def disenos(interno, admin, ordenes):
    """Dos diseños por regla: la primera línea de cada OC lleva uno; el resto, el otro (que pide un dato al generar)."""
    a = _aprobada(interno, admin, "Job design first lines")
    b = _aprobada(interno, admin, "Job design other lines",
                  variables=[{"clave": "lote", "etiqueta": "Batch", "obligatorio": True}])
    primeras = [o["lineas"][0]["posicion"] for o in ordenes]
    ids = []
    for p, cond, prioridad in ((a, {"campo": "linea.posicion", "op": "en", "valor": primeras}, 7001),
                               (b, {"campo": "contexto.origen", "op": "en", "valor": ["OC", "PACKING"]}, 7000)):
        r = interno.post("/etiquetas/asignaciones", {"plantilla_id": p["id"], "ambito": "REGLA", "prioridad": prioridad,
                                                     "nombre": f"Job rule {p['nombre']}", "condiciones": [cond]})
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
    yield a, b
    for i in ids:
        interno.c.delete(f"/api/etiquetas/asignaciones/{i}", headers=interno.h)


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


def test_trabajo_de_varias_oc_borrador_mezcla_parcial_y_reintento(interno, admin, tnf, ordenes, disenos, reglas_empresa):
    oc_ids = [o["oc"]["id"] for o in ordenes]
    lineas = [x["id"] for o in ordenes for x in o["lineas"][:2]]
    r = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": oc_ids, "posiciones": lineas}}, clave="job-1")
    assert r.status_code == 200, r.text
    t = r.json()
    # Idempotencia: la misma petición no crea otro trabajo
    assert interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": oc_ids}}, clave="job-1").json()["id"] == t["id"]
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
    # Diseños distintos en el mismo trabajo, cada registro con su regla
    assert set(por_diseno) == {"Job design first lines", "Job design other lines"} and all(x["regla_id"] for x in v["registros"])
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


def test_entradas_articulos_y_lista_de_empaque_usan_el_mismo_servicio(interno, admin, ordenes, disenos):
    # Artículos: un trabajo con la modalidad de artículo (sin regla para ella, se dice por qué)
    articulos = [{"articulo_id": x["articulo_id"], "cantidad": 2} for x in ordenes[0]["lineas"][:2]]
    t = interno.post("/etiquetas/trabajos", {"origen": "ARTICULOS", "parametros": {"articulos": articulos}}).json()
    v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
    assert len(v["registros"]) == 2 and all(x["cantidad"] == 2 for x in v["registros"])
    p = _aprobada(interno, admin, "Job item design", modalidad="ARTICULO")
    regla = interno.post("/etiquetas/asignaciones", {"plantilla_id": p["id"], "ambito": "REGLA", "prioridad": 7002,
                                                     "condiciones": [{"campo": "contexto.origen", "op": "igual", "valor": "ARTICULOS"}]}).json()
    try:
        v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
        assert {x["plantilla"] for x in v["registros"]} == {"Job item design"} and all(x["regla_id"] == regla["id"] for x in v["registros"])
        g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True})
        assert g.status_code == 200, g.text
        assert g.json()["estado"] == "GENERADO"
    finally:
        interno.c.delete(f"/api/etiquetas/asignaciones/{regla['id']}", headers=interno.h)
    # Lista de empaque: un registro por bulto, con el diseño de su regla (la del contexto PACKING)
    pls = interno.get("/etiquetas/masivo/packing").json()
    con = [x for x in pls if interno.get(f"/etiquetas/masivo/packing/{x['id']}").json()["superiores"]]
    if not con:
        pytest.skip("no packing lists with packages")
    t = interno.post("/etiquetas/trabajos", {"origen": "PACKING", "parametros": {"pl_id": con[0]["id"]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{t['id']}/validar").json()
    assert v["registros"] and all(x["pl_id"] == con[0]["id"] for x in v["registros"])
    assert {x["plantilla"] for x in v["registros"] if x["plantilla"]} <= {"Job design first lines", "Job design other lines"}
    # Cancelar un borrador
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/cancelar").json()["estado"] == "CANCELADO"
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/validar").status_code == 409


def test_generacion_en_segundo_plano_con_avance(interno, ordenes, disenos, reglas_empresa):
    o = ordenes[0]
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {
        "oc_ids": [o["oc"]["id"]], "posiciones": [o["lineas"][0]["id"]], "unidad": "MANUAL",
        "cantidades": {str(o["lineas"][0]["id"]): 6}}}).json()
    reglas_empresa(ETIQUETAS_ASINCRONO_DESDE=5)
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True})
    assert g.status_code == 200, g.text
    assert g.json()["asincrono"] is True and g.json()["estado"] in ("EN_PROCESO", "GENERADO")
    fin = _esperar(interno, t["id"])
    assert fin["estado"] == "GENERADO" and fin["progreso"] == 6 and fin["error"] is None
    d = interno.get(f"/etiquetas/trabajos/{t['id']}").json()
    assert sum(e["total"] for e in d["ejecuciones"]) == 6


def test_proveedor_solo_con_sus_ordenes(vans, ordenes):
    # Una OC de otro proveedor no se puede poner en un trabajo
    r = vans.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [ordenes[0]["oc"]["id"]]}})
    assert r.status_code == 404


def test_migracion_convierte_asignaciones_en_reglas_equivalentes():
    from test_oficial import RAIZ

    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        r = subprocess.run(alembic + ["upgrade", "0072"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        con.execute("INSERT INTO familias_etiquetado (id, codigo, nombre, campos, orden, activa, creada_en, organizacion_id)"
                    " VALUES (1, 'F', 'Fam', '[]', 0, 1, CURRENT_TIMESTAMP, 1)")
        con.execute("INSERT INTO plantillas_etiqueta (id, nombre, modalidad, unidad, estado, creada_en, actualizada_en, organizacion_id)"
                    " VALUES (1, 'Old design', 'OC_ARTICULO', 'LINEA', 'ACTIVA', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)")
        con.execute("INSERT INTO asignaciones_etiqueta (plantilla_id, ambito, predeterminada, activa, creada_en, organizacion_id)"
                    " VALUES (1, 'GENERAL', 1, 1, CURRENT_TIMESTAMP, 1)")
        con.execute("INSERT INTO asignaciones_etiqueta (plantilla_id, ambito, familia_id, predeterminada, activa, creada_en, organizacion_id)"
                    " VALUES (1, 'FAMILIA', 1, 0, 1, CURRENT_TIMESTAMP, 1)")
        con.commit()
        con.close()
        r = subprocess.run(alembic + ["upgrade", "head"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        filas = con.execute("SELECT ambito, prioridad, nombre, condiciones, contexto, predeterminada, version FROM asignaciones_etiqueta"
                            " ORDER BY id").fetchall()
        assert filas == [("GENERAL", 100, "General · Old design", "[]", "{}", 1, 1),
                         ("FAMILIA", 200, "Familia · Old design", "[]", "{}", 0, 1)]
        assert con.execute("SELECT padre_id FROM familias_etiquetado").fetchall() == [(None,)]
        # Una regla sin destino ya se puede guardar; al revertir se quita (antes no existía)
        con.execute("INSERT INTO asignaciones_etiqueta (plantilla_id, ambito, predeterminada, activa, creada_en, organizacion_id,"
                    " prioridad, condiciones, contexto, version) VALUES (1, 'REGLA', 0, 1, CURRENT_TIMESTAMP, 1, 250, '[]', '{}', 1)")
        con.commit()
        con.close()
        r = subprocess.run(alembic + ["downgrade", "0072"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        assert [x[0] for x in con.execute("SELECT ambito FROM asignaciones_etiqueta ORDER BY id")] == ["GENERAL", "FAMILIA"]
        con.close()


def test_generacion_interrumpida_se_puede_retomar(interno, ordenes, disenos):
    """Si el proceso que generaba en segundo plano se detuvo (reinicio), el
    trabajo no queda «generando» para siempre: se retoma lo pendiente."""
    from datetime import datetime, timedelta

    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import TrabajoEtiquetas

    o = ordenes[1]
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [o["oc"]["id"]], "posiciones": [o["lineas"][0]["id"]]}}).json()
    interno.post(f"/etiquetas/trabajos/{t['id']}/validar")
    with SessionLocal() as db, en_organizacion(1):
        x = db.get(TrabajoEtiquetas, t["id"])
        x.estado, x.actualizado_en = "EN_PROCESO", datetime.now()
        db.commit()
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True}).status_code == 409
    with SessionLocal() as db, en_organizacion(1):
        db.get(TrabajoEtiquetas, t["id"]).actualizado_en = datetime.now() - timedelta(minutes=30)
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
