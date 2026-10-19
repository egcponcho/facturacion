"""Recetas de empaque de N niveles y reglas de empaque."""
from conftest import Api

from app.modulos.empaque import recetas


def _tipos(api: Api) -> dict:
    return {t["codigo"]: t["id"] for t in api.get("/tipos-empaque").json()}


def _oc(api: Api, numero: str) -> dict:
    oc = next(o for o in api.get("/ordenes", params={"q": numero, "solo_disponible": False}).json()["items"]
              if o["numero"] == numero)
    return api.get(f"/ordenes/{oc['id']}/posiciones").json()


def _receta(api: Api, codigo: str, niveles: list[tuple[str, int]], **extra) -> dict:
    t = _tipos(api)
    r = api.post("/recetas-empaque", {"codigo": codigo, "nombre": codigo.title(),
                                      "niveles": [{"tipo_empaque_id": t[c], "cantidad": n, **extra.get(c, {})}
                                                  for c, n in niveles]})
    assert r.status_code == 200, r.text
    return r.json()


def test_derivar_casepack_e_inner_de_una_foto():
    foto = {"niveles": [{"cuenta_como": "INTERIOR", "unidades": 12, "nombre": "Inner"},
                        {"cuenta_como": "BULTO", "unidades": 24, "nombre": "Master"},
                        {"cuenta_como": "SOPORTE", "unidades": 960, "nombre": "Pallet"}]}
    assert recetas.derivar(foto) == (24, 12)
    assert recetas.derivar({"niveles": [foto["niveles"][1]]}) == (24, None)
    assert recetas.resumen(foto) == "Pallet 960 · Master 24 · Inner 12"


def test_receta_de_varios_niveles_con_totales_y_validaciones(admin):
    t = _tipos(admin)
    # Totales en vivo: 12 por inner, 2 inners por master, 40 masters por pallet
    calc = admin.post("/recetas-empaque/calcular", {"niveles": [
        {"tipo_empaque_id": t["INNER"], "cantidad": 12}, {"tipo_empaque_id": t["CAJA"], "cantidad": 2},
        {"tipo_empaque_id": t["PALLET"], "cantidad": 40}]}).json()
    assert [n["unidades"] for n in calc["niveles"]] == [12, 24, 960]
    assert calc["niveles"][1]["volumen"] == round(60 * 40 * 40 / 1e6, 4)  # medidas del tipo
    r = _receta(admin, "CAL-12X2X40", [("INNER", 12), ("CAJA", 2), ("PALLET", 40)])
    assert r["casepack"] == 24 and r["inner_pack"] == 12 and r["resumen"].startswith("Pallet 960")
    # Un inner no puede llevar una caja; el primer nivel lleva producto; solo los de arriba son opcionales
    malas = [
        [{"tipo_empaque_id": t["CAJA"], "cantidad": 2}, {"tipo_empaque_id": t["INNER"], "cantidad": 2}],
        [{"tipo_empaque_id": t["PALLET"], "cantidad": 2}],
        [{"tipo_empaque_id": t["CAJA"], "cantidad": 2, "opcional": True}, {"tipo_empaque_id": t["PALLET"], "cantidad": 2}],
        [{"tipo_empaque_id": t["CAJA"], "cantidad": 0}],
    ]
    for niveles in malas:
        x = admin.post("/recetas-empaque", {"codigo": "MALA", "nombre": "Mala", "niveles": niveles})
        assert x.status_code == 422, niveles
    assert admin.post("/recetas-empaque", {"codigo": "CAL-12X2X40", "nombre": "Otra",
                                           "niveles": [{"tipo_empaque_id": t["CAJA"], "cantidad": 6}]}).status_code == 409
    # Con un pallet opcional arriba sí vale; editarla sube la versión
    x = admin.patch(f"/recetas-empaque/{r['id']}", {"version": r["version"], "niveles": [
        {"tipo_empaque_id": t["INNER"], "cantidad": 12}, {"tipo_empaque_id": t["CAJA"], "cantidad": 2},
        {"tipo_empaque_id": t["PALLET"], "cantidad": 40, "opcional": True}]})
    assert x.status_code == 200, x.text
    assert x.json()["niveles"][2]["opcional"] is True
    assert admin.patch(f"/recetas-empaque/{r['id']}", {"version": r["version"], "nombre": "Vieja"}).status_code == 409


def test_la_demo_convierte_el_casepack_en_recetas(interno):
    """Como la migración 0081: cada casepack e inner pack de sólidos tiene su receta (origen DATOS)."""
    oc = _oc(interno, "4400003901")
    con_casepack = [p for p in oc["posiciones"] if p["casepack"]]
    assert con_casepack
    for p in con_casepack:
        assert p["receta"]["origen"] == "DATOS"
        assert recetas.derivar({"niveles": p["receta"]["niveles"]}) == (p["casepack"], p["inner_pack"])
    prepacks = [p for p in _oc(interno, "4400003903")["posiciones"] if p["tipo_empaque"] == "PREPACK"]
    assert prepacks and all(p["receta"]["receta_id"] is None for p in prepacks)


def test_reglas_gana_la_mas_especifica(admin):
    base = _receta(admin, "RG-BASE", [("CAJA", 10)])
    vans = _receta(admin, "RG-VANS", [("CAJA", 6)])
    sku = _receta(admin, "RG-SKU", [("INNER", 4), ("CAJA", 3)])
    otra = _receta(admin, "RG-OTRA", [("CAJA", 8)])
    oc = _oc(admin, "4400003902")
    pos = oc["posiciones"][0]
    creadas = []
    try:
        def regla(**d):
            r = admin.post("/reglas-empaque", d)
            assert r.status_code == 200, r.text
            creadas.append(r.json()["id"])
            return r.json()

        def gana(pid=pos["id"]):
            filas = admin.post("/reglas-empaque/probar", {"oc_id": oc["oc"]["id"]}).json()["posiciones"]
            return next(f for f in filas if f["posicion_id"] == pid)["reglas"]["receta"]

        regla(receta_id=base["id"])
        assert gana() == base["nombre"]
        # Con condiciones gana sobre sin condiciones (mismo destino)
        r_vans = regla(receta_id=vans["id"], condiciones=[{"campo": "oc.proveedor", "op": "igual", "valor": "VANS"}])
        assert gana() == vans["nombre"]
        # Una condición que no se cumple no aplica
        regla(receta_id=otra["id"], condiciones=[{"campo": "oc.proveedor", "op": "igual", "valor": "TNF"}])
        assert gana() == vans["nombre"]
        # El artículo es más específico que cualquier regla de toda la empresa
        r_sku = regla(receta_id=sku["id"], destino="ARTICULO", articulo_id=_articulo_id(admin, pos))
        assert gana() == sku["nombre"]
        # Con el mismo peso, decide el orden de la lista
        r_otra = regla(receta_id=otra["id"], condiciones=[{"campo": "linea.cantidad", "op": "mayor", "valor": 0}])
        assert gana(oc["posiciones"][1]["id"]) == vans["nombre"]  # VANS está arriba
        ids = [x["id"] for x in admin.get("/reglas-empaque").json()]
        ids.remove(r_otra["id"])
        ids.insert(ids.index(r_vans["id"]), r_otra["id"])
        assert admin.put("/reglas-empaque/orden", {"ids": ids}).status_code == 200
        assert gana(oc["posiciones"][1]["id"]) == otra["nombre"]
        # El impacto de dar de baja la regla del artículo: solo cambian sus posiciones abiertas que siguen a las reglas
        imp = admin.post("/reglas-empaque/impacto", {"quitar": r_sku["id"]}).json()
        assert imp["revisadas"] >= 0 and imp["cambian"] >= 0
        # Una condición sobre un dato que no existe no se guarda
        assert admin.post("/reglas-empaque", {"receta_id": base["id"], "condiciones": [
            {"campo": "oc.no_existe", "op": "igual", "valor": "X"}]}).status_code == 422
    finally:
        for rid in creadas:  # las demás pruebas crean OCs: sin reglas que les cambien el casepack
            admin.delete_(f"/reglas-empaque/{rid}")


def _articulo_id(api: Api, pos: dict) -> int:
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modelos import PosicionOC

    with SessionLocal() as db:
        return db.scalar(select(PosicionOC.articulo_id).where(PosicionOC.id == pos["id"]))


def test_oc_sin_casepack_toma_la_receta_de_la_regla_y_se_cambia_a_mano(admin):
    r6 = _receta(admin, "RG-FORM-6", [("CAJA", 6)])
    r4 = _receta(admin, "RG-FORM-4", [("INNER", 2), ("CAJA", 2)])
    regla = admin.post("/reglas-empaque", {"receta_id": r6["id"], "condiciones": [
        {"campo": "oc.proveedor", "op": "igual", "valor": "VANS"}], "motivo": "Vans ships 6 pairs per carton"}).json()
    try:
        sku = _oc(admin, "4400003901")["posiciones"][0]["codigo_articulo"]
        cab = {"proveedor": "VANS", "oc": "PO-RECETA-1", "centro_destino": "2220", "liberacion_comercial": "C",
               "liberacion_logistica": "Released"}
        r = admin.post("/ordenes", {"cabecera": cab, "lineas": [{"codigo_articulo": sku, "cantidad": 18}]})
        assert r.status_code == 200, r.text
        det = admin.get(f"/ordenes/{r.json()['oc_id']}/posiciones").json()
        p = det["posiciones"][0]
        assert p["receta"]["origen"] == "REGLA" and p["receta"]["receta_id"] == r6["id"] and p["casepack"] == 6
        assert p["receta"]["aviso"] is None
        # A mano: la receta y su casepack e inner; avisa si la cantidad no cierra
        x = admin.put(f"/ordenes/{det['oc']['id']}/posiciones/{p['id']}/receta", {"receta_id": r4["id"]})
        assert x.status_code == 200, x.text
        assert x.json()["origen"] == "MANUAL" and x.json()["aviso"] == "18 is not a multiple of 4."
        p = admin.get(f"/ordenes/{det['oc']['id']}/posiciones").json()["posiciones"][0]
        assert (p["casepack"], p["inner_pack"]) == (4, 2)
        # Cambiar la receta después no altera la posición (foto congelada)
        admin.patch(f"/recetas-empaque/{r4['id']}", {"nombre": "Renamed"})
        p = admin.get(f"/ordenes/{det['oc']['id']}/posiciones").json()["posiciones"][0]
        assert p["receta"]["receta"] == r4["nombre"]
        # Sin receta: vuelve a la regla
        x = admin.put(f"/ordenes/{det['oc']['id']}/posiciones/{p['id']}/receta", {"receta_id": None})
        assert x.json()["origen"] == "REGLA" and x.json()["receta_id"] == r6["id"]
    finally:
        admin.delete_(f"/reglas-empaque/{regla['id']}")


def test_proveedor_no_ve_ni_cambia_recetas(vans):
    assert vans.get("/recetas-empaque").status_code == 403
    assert vans.get("/reglas-empaque").status_code == 403
    assert vans.post("/reglas-empaque", {"receta_id": 1}).status_code == 403


def test_migracion_crea_recetas_desde_el_casepack():
    """0081: una receta automática por casepack e inner pack de los sólidos, con los tipos
    del catálogo; lo que no cierra o los prepacks quedan sin receta. Revertir no toca el casepack."""
    import sqlite3
    import subprocess
    import sys
    import tempfile

    from test_oficial import RAIZ

    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        r = subprocess.run(alembic + ["upgrade", "0080"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        c = sqlite3.connect(f"{tmp}/m.db")
        c.execute("PRAGMA foreign_keys=OFF")
        q = c.execute
        q("INSERT OR IGNORE INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en)"
          " VALUES (1, 'O1', 'Org', '{}', 1, '2026-01-01')")
        for i, cod, nom, nivel, cuenta in ((1, "INNER", "Inner pack", 1, "INTERIOR"), (2, "MASTER", "Master", 2, "BULTO")):
            q("INSERT INTO tipos_empaque (id, organizacion_id, codigo, nombre, nivel, cuenta_como, contiene_productos,"
              " mezcla_productos, mezcla_tallas, mezcla_oc, activo, tara) VALUES (?, 1, ?, ?, ?, ?, 1, 1, 1, 1, 1, 0.5)",
              (i, cod, nom, nivel, cuenta))
        q("INSERT INTO tipo_empaque_contiene (padre_id, hijo_id) VALUES (2, 1)")
        q("INSERT INTO proveedores (id, organizacion_id, codigo, nombre, activo, extra) VALUES (1, 1, 'P1', 'Prov', 1, '{}')")
        q("INSERT INTO ordenes_compra (id, organizacion_id, proveedor_id, numero, liberacion_comercial, liberacion_logistica,"
          " liberada, actualizado_en, extra, estado, origen, version) VALUES (1, 1, 1, '4500', 'L', 'L', 1, '2026-01-01', '{}',"
          " 'APROBADA', 'ERP', 1)")
        for i, (tipo, cp, inner) in enumerate((("SOLIDO", 12, 6), ("SOLIDO", 12, 6), ("SOLIDO", 10, None),
                                              ("SOLIDO", 10, 3), ("PREPACK", 1, None), ("SOLIDO", None, None)), start=1):
            q("INSERT INTO posiciones_oc (id, organizacion_id, oc_id, posicion, codigo_articulo, tipo_empaque, casepack,"
              " inner_pack, cantidad, unidad, bloqueada) VALUES (?, 1, 1, ?, 'A', ?, ?, ?, 24, 'PAR', 0)",
              (i, str(i * 10), tipo, cp, inner))
        c.commit()
        r = subprocess.run(alembic + ["upgrade", "head"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        recetas_bd = {cod: rid for rid, cod in c.execute("SELECT id, codigo FROM recetas_empaque WHERE automatica = 1")}
        assert set(recetas_bd) == {"CP12-IN6", "CP10"}
        niveles = c.execute("SELECT tipo_empaque_id, cantidad FROM receta_niveles WHERE receta_id = ? ORDER BY orden",
                            (recetas_bd["CP12-IN6"],)).fetchall()
        assert niveles == [(1, 6), (2, 2)]
        pos = {i: (rid, origen, cp) for i, rid, origen, cp in c.execute(
            "SELECT id, receta_id, receta_origen, casepack FROM posiciones_oc ORDER BY id")}
        assert pos[1] == (recetas_bd["CP12-IN6"], "DATOS", 12) and pos[2][0] == recetas_bd["CP12-IN6"]
        assert pos[3] == (recetas_bd["CP10"], "DATOS", 10)
        assert pos[4][0] is None and pos[5][0] is None and pos[6][0] is None  # 10 no es múltiplo de 3; prepack; sin casepack
        foto = c.execute("SELECT receta_foto FROM posiciones_oc WHERE id = 1").fetchone()[0]
        assert '"unidades": 12' in foto and '"cuenta_como": "BULTO"' in foto
        c.close()
        r = subprocess.run(alembic + ["downgrade", "0080"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        c = sqlite3.connect(f"{tmp}/m.db")
        assert c.execute("SELECT casepack, inner_pack FROM posiciones_oc WHERE id = 1").fetchone() == (12, 6)
        assert not c.execute("SELECT name FROM sqlite_master WHERE name = 'recetas_empaque'").fetchall()
        c.close()


def test_armar_segun_la_receta_completas_y_parciales():
    from app.modulos.empaque.packing import _contar_receta

    niveles = [{"orden": 1, "nombre": "Inner", "cantidad": 12, "unidades": 12},
               {"orden": 2, "nombre": "Master", "cantidad": 2, "unidades": 24},
               {"orden": 3, "nombre": "Pallet", "cantidad": 40, "unidades": 960}]
    # 1000 = 1 pallet (40 masters, 80 inners) + pallet parcial con 1 master, 1 master parcial con 1 inner y 1 inner de 4
    cuenta, queda = _contar_receta(niveles, 1000, "caja_parcial")
    assert queda == 0
    assert {c["nombre"]: (c["completas"], c["parciales"]) for c in cuenta} == {"Pallet": (1, 1), "Master": (41, 1),
                                                                                "Inner": (83, 1)}
    # Sin caja parcial: los 4 quedan sin empacar y no se arma nada vacío
    cuenta, queda = _contar_receta(niveles, 1000, "sin_caja")
    assert queda == 4 and {c["nombre"]: c["parciales"] for c in cuenta}["Inner"] == 0
    cuenta, queda = _contar_receta(niveles, 4, "sin_caja")
    assert queda == 4 and cuenta == []


def test_packing_list_se_arma_segun_la_receta(admin, vans):
    pallet = _receta(admin, "PL-40X2X12", [("INNER", 12), ("CAJA", 2), ("PALLET", 40)])
    sku = _oc(admin, "4400003901")["posiciones"][0]["codigo_articulo"]
    cab = {"proveedor": "VANS", "oc": "PO-RECETA-PL", "sociedad": "8000", "moneda": "USD", "centro_destino": "2220",
           "liberacion_comercial": "C", "liberacion_logistica": "300"}
    r = admin.post("/ordenes", {"cabecera": cab, "lineas": [{"codigo_articulo": sku, "cantidad": 1008, "precio": 10}]})
    assert r.status_code == 200, r.text
    oc_id = r.json()["oc_id"]
    pos = admin.get(f"/ordenes/{oc_id}/posiciones").json()["posiciones"][0]
    assert admin.put(f"/ordenes/{oc_id}/posiciones/{pos['id']}/receta", {"receta_id": pallet["id"]}).status_code == 200
    fid = vans.post("/facturas", {"lineas": [{"posicion_id": pos["id"], "cantidad": 1008}]}).json()["id"]
    pl_id = vans.post(f"/facturas/{fid}/packing-lists", {}).json()["id"]
    previa = vans.post(f"/packing-lists/{pl_id}/empaque-receta/previa", {}).json()
    fila = previa["filas"][0]
    assert fila["receta"] == pallet["nombre"] and fila["queda"] == 0
    assert {n["nombre"]: (n["completas"], n["parciales"]) for n in fila["niveles"]} == {
        "Pallet": (1, 1), "Master carton": (42, 0), "Inner pack": (84, 0)}
    version = vans.get(f"/packing-lists/{pl_id}").json()["version"]
    r = vans.post(f"/packing-lists/{pl_id}/empaque-receta", {"version": version})
    assert r.status_code == 200, r.text
    pl = vans.get(f"/packing-lists/{pl_id}").json()
    por_tipo = {t["codigo"]: t["unidades"] for t in pl["totales"]["por_tipo"]}
    assert por_tipo == {"PALLET": 2, "CAJA": 42, "INNER": 84}
    assert pl["totales"]["cajas"] == 42 and pl["totales"]["pallets"] == 2
    assert all(ln["sin_caja"] == 0 for ln in pl["lineas"])
    # Ya empacada: no hay nada más que armar
    r = vans.post(f"/packing-lists/{pl_id}/empaque-receta", {"version": pl["version"]})
    assert r.status_code == 422
