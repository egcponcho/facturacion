"""Etiquetado masivo: órdenes de compra de una familia (un PDF por OC, una
etiqueta por artículo distinto aunque se repita en varias líneas), artículos
sueltos (un PDF con una etiqueta por página o PNG en ZIP), empaques de una
lista de empaque por nivel (tarima, caja…), aviso cuando el diseño usa datos
de la lista de empaque que no hay, y campos que se escriben al generar."""
import io
import zipfile

import pdfplumber
import pytest
from sqlalchemy import inspect, select

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion

MM_PT = 72 / 25.4


def _aprobada(interno, admin, nombre, modalidad, elementos, ancho=80, alto=40, variables=None):
    r = interno.post("/etiquetas/plantillas", {"nombre": nombre, "modalidad": modalidad,
                                               "diseno": {"ancho": ancho, "alto": alto, "elementos": elementos,
                                                          "variables": variables or []}})
    assert r.status_code == 200, r.text
    v = r.json()["versiones"][0]
    assert interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {}).status_code == 200
    assert admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {}).status_code == 200
    return r.json()


def _pdf(contenido):
    with pdfplumber.open(io.BytesIO(contenido)) as doc:
        return [(pg.width, pg.height, pg.extract_text() or "") for pg in doc.pages]


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
    interno.post("/etiquetas/grupos-articulos/familia", {"familia_id": None, "grupo_ids": ids})


def test_ordenes_de_una_familia_un_pdf_por_oc_y_cada_articulo_una_vez(interno, admin, tnf, familia):
    ordenes = interno.get("/etiquetas/masivo/ordenes", params={"familia_id": familia["id"]}).json()
    assert ordenes["total"] >= 1, "the family must have POs"
    elegidas = ordenes["items"][:3]
    assert all(o["articulos"] >= 1 and o["lineas"] >= o["articulos"] for o in elegidas)
    todas = interno.get("/etiquetas/masivo/ordenes", params={"familia_id": familia["id"], "solo_ids": True}).json()["ids"]
    assert {o["id"] for o in ordenes["items"]} <= set(todas)
    # El proveedor solo ve sus OC
    propias = tnf.get("/etiquetas/masivo/ordenes", params={"familia_id": familia["id"]}).json()["items"]
    assert all(o["proveedor"] == "The North Face" for o in propias)

    # Un artículo repetido en dos líneas de la primera OC lleva una sola etiqueta
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
        p = _aprobada(interno, admin, "Bulk PO item label", "OC_ARTICULO", [SKU, OC])
        pedido = {"tipo": "ordenes", "oc_ids": [o["id"] for o in elegidas], "familia_id": familia["id"], "plantilla_id": p["id"]}
        plan = interno.post("/etiquetas/masivo/plan", pedido).json()
        assert plan["plantilla"]["nombre"] == "Bulk PO item label" and len(plan["partes"]) == len(elegidas)
        for parte, o in zip(plan["partes"], elegidas, strict=True):
            assert parte["total"] == o["articulos"], parte  # artículos distintos de la familia, no líneas
            assert len({g["articulo_id"] for g in parte["grupos"]}) == parte["total"]
        # Un diseño de artículo no sirve para órdenes de compra
        solo_art = _aprobada(interno, admin, "Bulk item only", "ARTICULO", [SKU])
        assert interno.post("/etiquetas/masivo/plan", {**pedido, "plantilla_id": solo_art["id"]}).status_code == 422
        r = interno.post("/etiquetas/masivo", {**pedido, "formato": "PDF", "aceptar_advertencias": True})
        assert r.status_code == 200, r.text
        res = r.json()
        assert len(res["generaciones"]) == len(elegidas) and res["total"] == sum(o["articulos"] for o in elegidas)
        # Todo junto: un ZIP con un PDF por OC, una etiqueta por página con la medida del diseño
        z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/masivo/{res['lote']}/archivo").content))
        assert sorted(z.namelist()) == sorted(f"{o['numero']}.pdf" for o in elegidas)
        for o in elegidas:
            paginas = _pdf(z.read(f"{o['numero']}.pdf"))
            assert len(paginas) == o["articulos"]
            assert abs(paginas[0][0] - 80 * MM_PT) < 0.5 and abs(paginas[0][1] - 40 * MM_PT) < 0.5
            assert all(f"PO {o['numero']}" in pg[2] for pg in paginas)
        # Cada OC queda en el historial como su propio lote, unidos por el código de la generación
        detalle = interno.get(f"/etiquetas/generaciones/{res['generaciones'][0]['id']}").json()
        assert detalle["lote"] == res["lote"] and detalle["unidad"] == "ARTICULO"
        png = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/masivo/{res['lote']}/archivo", params={"formato": "PNG"}).content))
        assert len([n for n in png.namelist() if n.endswith(".png")]) == res["total"]
    finally:
        with SessionLocal() as db, en_organizacion(1):
            db.delete(db.get(PosicionOC, copia_id))
            db.commit()


def test_articulos_de_una_familia_en_un_pdf_y_en_imagenes(interno, admin, familia):
    ids = interno.get("/etiquetas/articulos", params={"familia": familia["id"], "solo_ids": True}).json()["ids"]
    assert len(ids) >= 2
    ids = ids[:6]
    p = _aprobada(interno, admin, "Bulk item label", "ARTICULO", [SKU], ancho=50, alto=30)
    pedido = {"tipo": "articulos", "articulo_ids": ids, "plantilla_id": p["id"], "cantidad": 1, "aceptar_advertencias": True}
    plan = interno.post("/etiquetas/masivo/plan", pedido).json()
    assert plan["total"] == len(ids) and len(plan["partes"]) == 1
    res = interno.post("/etiquetas/masivo", {**pedido, "formato": "PDF"}).json()
    contenido = interno.get(f"/etiquetas/masivo/{res['lote']}/archivo").content
    assert contenido[:4] == b"%PDF"  # un solo PDF, no un ZIP
    paginas = _pdf(contenido)
    assert len(paginas) == len(ids) and abs(paginas[0][0] - 50 * MM_PT) < 0.5 and abs(paginas[0][1] - 30 * MM_PT) < 0.5
    res = interno.post("/etiquetas/masivo", {**pedido, "formato": "PNG", "cantidad": 2}).json()
    z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/masivo/{res['lote']}/archivo").content))
    assert len([n for n in z.namelist() if n.endswith(".png")]) == 2 * len(ids)


def test_lista_de_empaque_por_nivel_con_tarimas_y_cajas(interno, admin):
    from app.modelos import GrupoCajas, PackingList, TipoEmpaque

    pls = interno.get("/etiquetas/masivo/packing").json()
    con = [x for x in pls if interno.get(f"/etiquetas/masivo/packing/{x['id']}").json()["superiores"]]
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
    try:
        info = interno.get(f"/etiquetas/masivo/packing/{pl_id}").json()
        niveles = {n["tipo_empaque_id"]: n for n in info["niveles"]}
        assert niveles[tipo_id]["unidades"] == 1 and niveles[tipo_id]["superior"] and info["niveles"][0]["tipo_empaque_id"] == tipo_id
        p = _aprobada(interno, admin, "Bulk package label", "OC", [
            OC, {"id": "b", "tipo": "texto", "contenido": "{{bulto.tipo}} {{bulto.codigo}} in {{bulto.contenedor}} · {{bulto.numero}}/{{bulto.total}}",
                 "x": 3, "y": 24, "w": 74, "h": 7, "estilo": {"tam": 7}},
            {"id": "u", "tipo": "texto", "contenido": "Units {{bulto.unidades}}", "x": 3, "y": 32, "w": 74, "h": 6, "estilo": {"tam": 7}}])
        # La tarima: una etiqueta con todo su contenido (el de las cajas que lleva)
        plan = interno.post("/etiquetas/masivo/plan", {"tipo": "packing", "pl_id": pl_id, "tipo_empaque_id": tipo_id,
                                                        "plantilla_id": p["id"]}).json()
        assert plan["total"] == 1, plan
        res = interno.post("/etiquetas/masivo", {"tipo": "packing", "pl_id": pl_id, "tipo_empaque_id": tipo_id, "plantilla_id": p["id"],
                                                 "formato": "PDF", "aceptar_advertencias": True}).json()
        texto = _pdf(interno.get(f"/etiquetas/masivo/{res['lote']}/archivo").content)[0][2]
        assert "Pallet P1" in texto and "Units" in texto
        # Las cajas: una por unidad, con la tarima que las contiene
        if len(tipos_cajas) == 1:
            tipo_caja = next(iter(tipos_cajas))
            r = interno.post("/etiquetas/masivo/plan", {"tipo": "packing", "pl_id": pl_id, "tipo_empaque_id": tipo_caja,
                                                         "plantilla_id": p["id"]}).json()
            assert r["total"] == n_cajas
            gen = interno.post("/etiquetas/masivo", {"tipo": "packing", "pl_id": pl_id, "tipo_empaque_id": tipo_caja,
                                                     "plantilla_id": p["id"], "formato": "PDF", "aceptar_advertencias": True}).json()
            paginas = _pdf(interno.get(f"/etiquetas/masivo/{gen['lote']}/archivo").content)
            assert len(paginas) == n_cajas and "in P1" in paginas[0][2] and f"1/{n_cajas}" in paginas[0][2]
            assert interno.get(f"/etiquetas/generaciones/{gen['generaciones'][0]['id']}").json()["pl_id"] == pl_id
    finally:
        with SessionLocal() as db, en_organizacion(1):
            for g in db.scalars(select(GrupoCajas).where(GrupoCajas.id.in_(ids_cajas))):
                g.padre_id = None
            db.flush()
            db.delete(db.get(GrupoCajas, tarima_id))
            db.delete(db.get(TipoEmpaque, tipo_id))
            db.commit()


def test_diseno_con_datos_de_empaque_sin_lista_avisa_y_deja_seguir(interno, admin, familia):
    o = interno.get("/etiquetas/masivo/ordenes", params={"familia_id": familia["id"]}).json()["items"][0]
    p = _aprobada(interno, admin, "Bulk needs packing list", "OC_ARTICULO", [
        SKU, {"id": "peso", "tipo": "campo", "campo": "bulto.peso_bruto", "sufijo": " kg", "x": 3, "y": 24, "w": 40, "h": 7}])
    pedido = {"tipo": "ordenes", "oc_ids": [o["id"]], "familia_id": familia["id"], "plantilla_id": p["id"], "formato": "PDF"}
    plan = interno.post("/etiquetas/masivo/plan", pedido).json()
    avisos = [q["mensaje"] for q in plan["partes"][0]["problemas"]]
    assert any("packing list data (bulto.peso_bruto)" in a for a in avisos) and plan["puede_generar"]
    r = interno.post("/etiquetas/masivo", pedido)
    assert r.status_code == 409 and r.json()["codigo"] == "confirmar_advertencias"
    r = interno.post("/etiquetas/masivo", {**pedido, "aceptar_advertencias": True})
    assert r.status_code == 200 and r.json()["total"] == o["articulos"]


def test_campos_que_se_escriben_al_generar(interno, admin, familia):
    lote = {"id": "lote", "tipo": "texto", "contenido": "Lot {{manual.lote}} · {{manual.temporada}}", "x": 3, "y": 24, "w": 74, "h": 7}
    # Un campo manual sin declarar no se acepta
    malo = interno.post("/etiquetas/plantillas", {"nombre": "Bad manual", "modalidad": "ARTICULO",
                                                  "diseno": {"ancho": 80, "alto": 40, "elementos": [lote]}})
    assert malo.status_code == 422
    p = _aprobada(interno, admin, "Bulk with manual fields", "ARTICULO", [SKU, lote],
                  variables=[{"clave": "lote", "etiqueta": "Lot", "obligatorio": True},
                             {"clave": "temporada", "etiqueta": "Season", "defecto": "FW26"}])
    previa = interno.post("/etiquetas/vista-previa", {"version_id": p["versiones"][0]["id"]}).json()
    assert previa["valores"]["manual.lote"] == "[Lot]" and previa["valores"]["manual.temporada"] == "FW26"
    ids = interno.get("/etiquetas/articulos", params={"familia": familia["id"], "solo_ids": True}).json()["ids"][:2]
    pedido = {"tipo": "articulos", "articulo_ids": ids, "plantilla_id": p["id"], "formato": "PDF", "aceptar_advertencias": True}
    plan = interno.post("/etiquetas/masivo/plan", pedido).json()
    assert plan["errores"] and any("Lot" in q["mensaje"] for q in plan["partes"][0]["problemas"])
    assert [v["clave"] for v in plan["plantilla"]["variables"]] == ["lote", "temporada"]
    assert interno.post("/etiquetas/masivo", pedido).status_code == 422
    res = interno.post("/etiquetas/masivo", {**pedido, "manuales": {"lote": "L-77"}}).json()
    texto = _pdf(interno.get(f"/etiquetas/masivo/{res['lote']}/archivo").content)[0][2]
    assert "Lot L-77 · FW26" in texto
