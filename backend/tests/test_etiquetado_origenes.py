"""Orígenes de un trabajo de etiquetado: las OC de una familia (un PDF por OC,
una etiqueta por artículo distinto aunque se repita en varias líneas),
artículos sueltos (un PDF con una etiqueta por página o PNG en el ZIP),
empaques de una lista de empaque por nivel (tarima, caja…), un diseño de
artículo no puede usar datos de bulto, y campos que se escriben al generar."""
import io
import zipfile

import pdfplumber
import pytest
from etiquetado_util import aprobada, cambiar, generado, tipo, trabajo, uso
from sqlalchemy import inspect, select

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion

MM_PT = 72 / 25.4


def _pdf(contenido):
    with pdfplumber.open(io.BytesIO(contenido)) as doc:
        return [(pg.width, pg.height, pg.extract_text() or "") for pg in doc.pages]


def _con_diseno(interno, admin, codigo, nombre, elementos, sujeto="ARTICULO", cantidad="POR_ARTICULO", **kw):
    t = tipo(interno, codigo, sujeto=sujeto, cantidad=cantidad)
    p = aprobada(interno, admin, nombre, t["id"], elementos, **{"ancho": 80, "alto": 40, **kw})
    uso(interno, t["id"], p["id"])
    return t, p


def _zip(interno, t, **zip_):
    r = interno.patch(f"/etiquetas/trabajos/{t['id']}", {"parametros": {"zip": zip_}})
    assert r.status_code == 200, r.text
    return zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/trabajos/{t['id']}/archivo").content))


SKU = {"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 3, "w": 70, "h": 8, "estilo": {"tam": 10}}
OC = {"id": "oc", "tipo": "campo", "campo": "oc.numero", "prefijo": "PO ", "x": 3, "y": 14, "w": 70, "h": 8, "estilo": {"tam": 9}}


@pytest.fixture(scope="module")
def familia(interno):
    """Una familia con el grupo de artículos que más líneas de OC tiene."""
    r = interno.post("/etiquetas/familias", {"codigo": "MASIVO", "nombre": "Bulk family"})
    assert r.status_code == 200, r.text
    f = r.json()
    grupos = sorted(interno.get("/etiquetas/grupos-articulos").json(), key=lambda g: -g["articulos"])
    ids = [g["id"] for g in grupos[:3] if g["articulos"]]
    assert interno.post("/etiquetas/grupos-articulos/familia", {"familia_id": f["id"], "grupo_ids": ids}).status_code == 200
    yield f
    for g in grupos[:3]:
        interno.post("/etiquetas/grupos-articulos/familia", {"familia_id": g["familia_id"], "grupo_ids": [g["id"]]})


def test_ordenes_de_una_familia_un_pdf_por_oc_y_cada_articulo_una_vez(interno, admin, tnf, familia):
    ordenes = interno.get("/etiquetas/ordenes", params={"familia_id": familia["id"]}).json()
    assert ordenes["total"] >= 1, "the family must have POs"
    elegidas = ordenes["items"][:3]
    assert all(o["articulos"] >= 1 and o["lineas"] >= o["articulos"] for o in elegidas)
    todas = interno.get("/etiquetas/ordenes", params={"familia_id": familia["id"], "solo_ids": True}).json()["ids"]
    assert {o["id"] for o in ordenes["items"]} <= set(todas)
    # El proveedor solo ve sus OC
    propias = tnf.get("/etiquetas/ordenes", params={"familia_id": familia["id"]}).json()["items"]
    assert all(o["proveedor"] == "The North Face" for o in propias)

    # Un artículo repetido en dos líneas de la primera OC lleva una sola etiqueta (una por artículo distinto)
    from app.modelos import PosicionOC

    primera = elegidas[0]
    with SessionLocal() as db, en_organizacion(1):
        base = db.scalars(select(PosicionOC).where(PosicionOC.oc_id == primera["id"], PosicionOC.articulo_id.is_not(None))
                          .order_by(PosicionOC.id)).first()
        cols = {c.key: getattr(base, c.key) for c in inspect(PosicionOC).mapper.column_attrs if c.key not in ("id",)}
        ultima = max((p.posicion for p in db.scalars(select(PosicionOC).where(PosicionOC.oc_id == primera["id"]))), key=int)
        cols["posicion"] = str(int(ultima) + 990).zfill(len(ultima))
        copia = PosicionOC(**cols)
        db.add(copia)
        db.commit()
        copia_id = copia.id
    try:
        t_, _ = _con_diseno(interno, admin, "ORIG_ARTICULO", "Bulk PO item label", [SKU, OC])
        t = trabajo(interno, "OC", {"oc_ids": [o["id"] for o in elegidas], "familia_id": familia["id"], "tipos": [t_["id"]]})
        for o in elegidas:
            de_oc = [r for r in t["registros"] if r["oc_id"] == o["id"]]
            assert len(de_oc) == o["articulos"], de_oc  # artículos distintos de la familia, no líneas
            assert len({r["articulo_id"] for r in de_oc}) == len(de_oc)
        t = generado(interno, t)
        assert len(t["ejecuciones"]) == len(elegidas) and sum(e["total"] for e in t["ejecuciones"]) == sum(o["articulos"] for o in elegidas)
        # Todo junto: un ZIP con un PDF por OC, una etiqueta por página con la medida del diseño
        z = _zip(interno, t, contenido="PDF", agrupar="carpeta", carpetas=["oc"])
        assert sorted(z.namelist()) == sorted([*(f"{o['numero']}/{o['numero']}.pdf" for o in elegidas), "summary.json", "summary.csv"])
        for o in elegidas:
            paginas = _pdf(z.read(f"{o['numero']}/{o['numero']}.pdf"))
            assert len(paginas) == o["articulos"]
            assert abs(paginas[0][0] - 80 * MM_PT) < 0.5 and abs(paginas[0][1] - 40 * MM_PT) < 0.5
            assert all(f"PO {o['numero']}" in pg[2] for pg in paginas)
        # Cada OC queda en el historial como su propia ejecución, unidas por el lote del trabajo
        detalles = [interno.get(f"/etiquetas/generaciones/{e['id']}").json() for e in t["ejecuciones"]]
        assert len({d["lote"] for d in detalles}) == 1 and all(d["tipos"] == ["Orig_Articulo"] for d in detalles)
        png = _zip(interno, t, contenido="PNG", agrupar="etiqueta")
        assert len([n for n in png.namelist() if n.endswith(".png")]) == sum(o["articulos"] for o in elegidas)
    finally:
        with SessionLocal() as db, en_organizacion(1):
            db.delete(db.get(PosicionOC, copia_id))
            db.commit()


def test_articulos_de_una_familia_en_un_pdf_y_en_imagenes(interno, admin, familia):
    ids = interno.get("/etiquetas/articulos", params={"familia": familia["id"], "solo_ids": True}).json()["ids"]
    assert len(ids) >= 2
    ids = ids[:6]
    t_, _ = _con_diseno(interno, admin, "ORIG_SUELTO", "Bulk item label", [SKU], cantidad="POR_UNIDAD", ancho=50, alto=30)
    t = trabajo(interno, "ARTICULOS", {"articulos": [{"articulo_id": i, "cantidad": 1} for i in ids], "tipos": [t_["id"]]})
    assert len(t["registros"]) == len(ids)
    t = generado(interno, t)
    z = _zip(interno, t, contenido="PDF", agrupar="unico")
    pdfs = [n for n in z.namelist() if n.endswith(".pdf")]
    assert len(pdfs) == 1  # un solo PDF
    paginas = _pdf(z.read(pdfs[0]))
    assert len(paginas) == len(ids) and abs(paginas[0][0] - 50 * MM_PT) < 0.5 and abs(paginas[0][1] - 30 * MM_PT) < 0.5
    t = generado(interno, trabajo(interno, "ARTICULOS", {"articulos": [{"articulo_id": i, "cantidad": 2} for i in ids], "tipos": [t_["id"]]}))
    z = _zip(interno, t, contenido="PNG", agrupar="etiqueta")
    assert len([n for n in z.namelist() if n.endswith(".png")]) == 2 * len(ids)


def test_lista_de_empaque_por_nivel_con_tarimas_y_cajas(interno, admin):
    from app.modelos import GrupoCajas, PackingList, TipoEmpaque

    pls = interno.get("/etiquetas/packing").json()
    con = [x for x in pls if x["etiquetas_reales"] and interno.get(f"/etiquetas/packing/{x['id']}").json()["superiores"]]
    if not con:
        pytest.skip("no packing lists with packages")
    pl_id = con[0]["id"]
    # Las cajas de primer nivel van sobre una tarima (y se deshace al final)
    with SessionLocal() as db, en_organizacion(1):
        pl = db.get(PackingList, pl_id)
        cajas = [g for g in pl.grupos if g.padre_id is None]
        n_cajas = sum(g.num_cajas for g in cajas)
        tarima_tipo = TipoEmpaque(codigo="PALLET-T", nombre="Pallet", nivel=9, prefijo="P", cuenta_como="SOPORTE")
        db.add(tarima_tipo)
        db.flush()
        tarima = GrupoCajas(pl_id=pl.id, num_cajas=1, tipo_empaque_id=tarima_tipo.id, peso_bruto_caja=100)
        db.add(tarima)
        db.flush()
        for g in cajas:
            g.padre_id = tarima.id
        db.commit()
        ids_cajas, tarima_id, tipo_id = [g.id for g in cajas], tarima.id, tarima_tipo.id
        tipos_cajas = {g.tipo_empaque_id for g in cajas}
        from app.modulos.etiquetado import campos as svc_campos

        db.refresh(pl)
        articulos_pl = set().union(*(set(u.articulos) for u in svc_campos.unidades_pl(pl, superiores=True)))
    try:
        info = interno.get(f"/etiquetas/packing/{pl_id}").json()
        niveles = {n["tipo_empaque_id"]: n for n in info["niveles"]}
        assert niveles[tipo_id]["unidades"] == 1 and niveles[tipo_id]["superior"] and info["niveles"][0]["tipo_empaque_id"] == tipo_id
        t_, _ = _con_diseno(interno, admin, "ORIG_BULTO", "Bulk package label", [
            OC, {"id": "b", "tipo": "texto", "contenido": "{{bulto.tipo}} {{bulto.codigo}} in {{bulto.contenedor}} · {{bulto.numero}}/{{bulto.total}}",
                 "x": 3, "y": 24, "w": 74, "h": 7, "estilo": {"tam": 7}},
            {"id": "u", "tipo": "texto", "contenido": "Units {{bulto.unidades}}", "x": 3, "y": 32, "w": 74, "h": 6, "estilo": {"tam": 7}},
            {"id": "s", "tipo": "texto", "contenido": "{{articulo.sku}} mixed {{bulto.mixto}}", "x": 3, "y": 3, "w": 74, "h": 6,
             "estilo": {"tam": 7}}],
            sujeto="BULTO", cantidad="POR_BULTO")
        # La tarima: una etiqueta con todo su contenido (el de las cajas que lleva)
        t = trabajo(interno, "PACKING", {"pl_id": pl_id, "tipo_empaque_id": tipo_id, "tipos": [t_["id"]]})
        assert len(t["registros"]) == 1, t["registros"]
        # E5: si lleva varios artículos, los datos del artículo quedan vacíos con un aviso (no se toma el primero)
        mixto = "contenido_mixto" in {p["codigo"] for p in t["registros"][0]["problemas"]}
        assert mixto == (len(articulos_pl) > 1), (articulos_pl, t["registros"][0]["problemas"])
        t = generado(interno, t)
        texto = _pdf(interno.get(f"/etiquetas/generaciones/{t['ejecuciones'][0]['id']}/archivo").content)[0][2]
        assert "Pallet P1" in texto and "Units" in texto
        if len(articulos_pl) > 1:
            assert "mixed Yes" in texto
        # Las cajas: una por unidad, con la tarima que las contiene
        if len(tipos_cajas) == 1:
            tipo_caja = next(iter(tipos_cajas))
            t = trabajo(interno, "PACKING", {"pl_id": pl_id, "tipo_empaque_id": tipo_caja, "tipos": [t_["id"]]})
            assert len(t["registros"]) == n_cajas
            t = generado(interno, t)
            gen = t["ejecuciones"][0]
            paginas = _pdf(interno.get(f"/etiquetas/generaciones/{gen['id']}/archivo").content)
            assert len(paginas) == n_cajas and "in P1" in paginas[0][2] and f"1/{n_cajas}" in paginas[0][2]
            assert interno.get(f"/etiquetas/generaciones/{gen['id']}").json()["pl_id"] == pl_id
            # Varios niveles en un mismo trabajo: la tarima y sus cajas, cada unidad una vez
            t = trabajo(interno, "PACKING", {"pl_id": pl_id, "niveles": [tipo_id, tipo_caja, tipo_id], "tipos": [t_["id"]]})
            assert len(t["registros"]) == n_cajas + 1 and t["parametros"]["niveles"] == [tipo_id, tipo_caja]
            # Los exteriores (0) son la tarima: pedirla dos veces no la repite
            t = trabajo(interno, "PACKING", {"pl_id": pl_id, "niveles": [0, tipo_id], "tipos": [t_["id"]]})
            assert len(t["registros"]) == 1
            assert interno.post("/etiquetas/trabajos", {"origen": "PACKING", "parametros": {"pl_id": pl_id, "niveles": ["x"]}}).status_code == 422
            # «Se aplica a»: una etiqueta solo de pallet no sale en las cajas aunque se elijan las dos
            tp, pp = _con_diseno(interno, admin, "ORIG_SOLO_PALLET", "Pallet only", [OC], sujeto="BULTO", cantidad="POR_BULTO")
            assert tp["empaques"] == []
            # Con un diseño puesto en las cajas, no se puede dejar de aplicar a las cajas
            u = uso(interno, tp["id"], pp["id"], nivel="TIPO_EMPAQUE", destino_id=tipo_caja)
            v = interno.get("/etiquetas/tipos", params={"todos": True}).json()
            version = next(x for x in v if x["id"] == tp["id"])["version"]
            r = interno.patch(f"/etiquetas/tipos/{tp['id']}", {"empaques": [tipo_id], "version": version})
            assert r.status_code == 422 and "empaques" in r.text, r.text
            assert interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "test"}).status_code == 200
            r = interno.patch(f"/etiquetas/tipos/{tp['id']}", {"empaques": [tipo_id], "version": version})
            assert r.status_code == 200 and r.json()["empaques"] == [tipo_id], r.text
            t = trabajo(interno, "PACKING", {"pl_id": pl_id, "niveles": [tipo_id, tipo_caja], "tipos": [tp["id"], t_["id"]]})
            de = [x["tipo_etiqueta_id"] for x in t["registros"]]
            assert de.count(tp["id"]) == 1 and de.count(t_["id"]) == n_cajas + 1
            # En la matriz de bultos la celda de las cajas no aplica (ni hereda ni falta) y no admite diseño
            m = interno.get("/etiquetas/matriz", params={"sujeto": "BULTO"}).json()
            celdas = {f["id"]: f["celdas"][str(tp["id"])] for f in m["filas"] if f["nivel"] == "TIPO_EMPAQUE"}
            assert celdas[tipo_caja]["no_aplica"] and not celdas[tipo_caja]["falta"] and not celdas[tipo_id].get("no_aplica")
            r = interno.post("/etiquetas/usos", {"tipo_etiqueta_id": tp["id"], "plantilla_id": pp["id"], "nivel": "TIPO_EMPAQUE",
                                                 "destino_id": tipo_caja, "contexto_tipo": "NINGUNO"})
            assert r.status_code == 422, r.text
            el = interno.get("/etiquetas/resolver", params={"sujeto": "BULTO", "tipo_empaque_id": tipo_caja}).json()["elecciones"]
            assert tp["id"] not in {e["tipo_etiqueta_id"] for e in el} and t_["id"] in {e["tipo_etiqueta_id"] for e in el}
            # Solo los tipos de bulto se limitan por empaque
            ta = tipo(interno, "ORIG_ART_EMP")
            assert interno.patch(f"/etiquetas/tipos/{ta['id']}", {"empaques": [tipo_id]}).status_code == 422
    finally:
        with SessionLocal() as db, en_organizacion(1):
            for g in db.scalars(select(GrupoCajas).where(GrupoCajas.id.in_(ids_cajas))):
                g.padre_id = None
            db.flush()
            db.delete(db.get(GrupoCajas, tarima_id))
            from app.modelos import TipoEtiquetaEmpaque
            for x in db.scalars(select(TipoEtiquetaEmpaque).where(TipoEtiquetaEmpaque.tipo_empaque_id == tipo_id)):
                db.delete(x)
            db.flush()
            db.delete(db.get(TipoEmpaque, tipo_id))
            db.commit()


def test_un_diseno_de_articulo_no_usa_datos_de_bulto(interno):
    """Lo que puede llevar una etiqueta depende de qué se etiqueta: un diseño de
    artículo no tiene datos de caja (esos van en el tipo de etiqueta de caja)."""
    t_ = tipo(interno, "ORIG_ART_SIN_BULTO", cantidad="POR_ARTICULO")
    r = interno.post("/etiquetas/plantillas", {"nombre": "Item with package data", "tipo_etiqueta_id": t_["id"], "diseno": {
        "ancho": 80, "alto": 40, "elementos": [SKU, {"id": "peso", "tipo": "campo", "campo": "bulto.peso_bruto", "sufijo": " kg",
                                                      "x": 3, "y": 24, "w": 40, "h": 7}]}})
    assert r.status_code == 422, r.text


def test_campos_que_se_escriben_al_generar(interno, admin, familia):
    lote = {"id": "lote", "tipo": "texto", "contenido": "Lot {{manual.lote}} · {{manual.temporada}}", "x": 3, "y": 24, "w": 74, "h": 7}
    t_ = tipo(interno, "ORIG_MANUAL", cantidad="POR_ARTICULO")
    # Un campo manual sin declarar no se acepta
    malo = interno.post("/etiquetas/plantillas", {"nombre": "Bad manual", "tipo_etiqueta_id": t_["id"],
                                                  "diseno": {"ancho": 80, "alto": 40, "elementos": [lote]}})
    assert malo.status_code == 422
    p = aprobada(interno, admin, "Bulk with manual fields", t_["id"], [SKU, lote], ancho=80, alto=40,
                 variables=[{"clave": "lote", "etiqueta": "Lot", "obligatorio": True},
                            {"clave": "temporada", "etiqueta": "Season", "defecto": "FW26"}])
    uso(interno, t_["id"], p["id"])
    previa = interno.post("/etiquetas/vista-previa", {"version_id": p["versiones"][0]["id"]}).json()
    assert previa["valores"]["manual.lote"] == "[Lot]" and previa["valores"]["manual.temporada"] == "FW26"
    ids = interno.get("/etiquetas/articulos", params={"familia": familia["id"], "solo_ids": True}).json()["ids"][:2]
    t = trabajo(interno, "ARTICULOS", {"articulos": [{"articulo_id": i} for i in ids], "tipos": [t_["id"]]})
    assert all(r["estado"] == "ERROR" and any("Lot" in q["mensaje"] for q in r["problemas"]) for r in t["registros"])
    assert [v["clave"] for v in t["resumen"]["variables"]] == ["lote", "temporada"]
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True, "version": t["version"]}).status_code == 422
    t = generado(interno, cambiar(interno, t, {"manuales": {"lote": "L-77"}}))
    texto = _pdf(interno.get(f"/etiquetas/generaciones/{t['ejecuciones'][0]['id']}/archivo").content)[0][2]
    assert "Lot L-77 · FW26" in texto


def test_bultos_de_listas_distintas_no_se_confunden_y_borrador_solo_prueba(interno, admin):
    """E1: el «ya impreso» de un bulto va por su identidad (lista, grupo, número), no por
    su texto: el bulto 1 de otra lista de empaque no sale como ya impreso. E6: una lista
    en borrador solo da etiquetas de prueba."""
    pls = interno.get("/etiquetas/packing").json()
    reales = [x for x in pls if x["etiquetas_reales"] and interno.get(f"/etiquetas/packing/{x['id']}").json()["superiores"]]
    if len(reales) < 2:
        pytest.skip("two packing lists with packages are needed")
    t_, _ = _con_diseno(interno, admin, "ORIG_IDENT", "Package identity", [
        {"id": "b", "tipo": "texto", "contenido": "{{bulto.numero}}/{{bulto.total}}", "x": 3, "y": 3, "w": 60, "h": 8}],
        sujeto="BULTO", cantidad="POR_BULTO")
    a, b = reales[0]["id"], reales[1]["id"]
    generado(interno, trabajo(interno, "PACKING", {"pl_id": a, "tipos": [t_["id"]]}))

    def ya(pl_id):
        t = trabajo(interno, "PACKING", {"pl_id": pl_id, "tipos": [t_["id"]]})
        regs = [r for r in t["registros"] if r["tipo_etiqueta_id"] == t_["id"]]
        return regs, [r for r in regs if "ya_generada" in {p["codigo"] for p in r["problemas"]}]

    regs_a, ya_a = ya(a)
    assert regs_a and len(ya_a) == len(regs_a)  # la misma lista: todos ya impresos
    regs_b, ya_b = ya(b)
    assert regs_b and not ya_b  # otra lista con bultos 1, 2…: ninguno
    # Borrador (la lista b vuelve a borrador un momento): en real, error de lista sin finalizar; en prueba, se puede
    from app.modelos import PackingList

    with SessionLocal() as db, en_organizacion(1):
        pl = db.get(PackingList, b)
        estado, pl.estado = pl.estado, "BORRADOR"
        db.commit()
    try:
        r = interno.post("/etiquetas/trabajos", {"origen": "PACKING", "parametros": {"pl_id": b, "tipos": [t_["id"]]}})
        t = interno.post(f"/etiquetas/trabajos/{r.json()['id']}/validar").json()
        assert "pl_sin_finalizar" in {p.get("codigo") for p in t["resumen"]["problemas"]}, t["resumen"]
        t = trabajo(interno, "PACKING", {"pl_id": b, "tipos": [t_["id"]], "prueba": True})
        assert "pl_sin_finalizar" not in {p.get("codigo") for p in t["resumen"]["problemas"]}
    finally:
        with SessionLocal() as db, en_organizacion(1):
            db.get(PackingList, b).estado = estado
            db.commit()
