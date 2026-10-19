"""Anular una ejecución y reimprimir, siempre con motivo y con su rastro: anular deja los
registros pendientes para generarlos de nuevo (la ejecución anulada ya no se descarga, no se
confirma como impresa ni entra en el ZIP del trabajo); reimprimir da copias idénticas de todo
el lote o de algunos grupos y rangos, y queda en el historial del lote."""
from etiquetado_util import aprobada, generado, oc_con_articulos, pdf, tipo, trabajo, uso

NUMERO = [{"id": "n", "tipo": "texto", "contenido": "{{articulo.sku}} {{etiqueta.numero}}/{{etiqueta.total}}",
           "x": 3, "y": 3, "w": 90, "h": 10}]


def _preparar(interno, admin, codigo):
    datos = oc_con_articulos(interno)
    t_ = tipo(interno, codigo, cantidad="MANUAL")
    d = aprobada(interno, admin, f"Numbered {codigo}", t_["id"], NUMERO)
    u = uso(interno, t_["id"], d["id"])
    lineas = datos["lineas"][:2]
    tr = trabajo(interno, "OC", {"oc_ids": [datos["oc"]["id"]], "posiciones": [x["id"] for x in lineas], "tipos": [t_["id"]]})
    cantidades = {r["clave"]: 3 for r in tr["registros"] if r["tipo_etiqueta_id"] == t_["id"]}
    assert interno.patch(f"/etiquetas/trabajos/{tr['id']}", {"parametros": {"cantidades": cantidades},
                                                             "version": tr["version"]}).status_code == 200
    tr = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    return t_, u, tr


def _limpiar(interno, t_, u):
    interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "Test done"})
    version = next(x for x in interno.get("/etiquetas/tipos", params={"todos": True}).json() if x["id"] == t_["id"])["version"]
    interno.patch(f"/etiquetas/tipos/{t_['id']}", {"activo": False, "version": version})


def test_anular_deja_los_registros_pendientes_y_se_genera_de_nuevo(interno, admin, tnf):
    t_, u, tr = _preparar(interno, admin, "ANULAR")
    try:
        tr = generado(interno, tr)
        assert tr["estado"] == "GENERADO" and len(tr["ejecuciones"]) == 1
        g = tr["ejecuciones"][0]
        assert g["total"] == 6 and {x["cantidad"] for x in g["grupos"]} == {3}
        # Sin motivo, o un proveedor: no
        assert interno.post(f"/etiquetas/generaciones/{g['id']}/anular", {"motivo": " "}).status_code == 422
        assert tnf.post(f"/etiquetas/generaciones/{g['id']}/anular", {"motivo": "Wrong data"}).status_code in (403, 404)
        r = interno.post(f"/etiquetas/generaciones/{g['id']}/anular", {"motivo": "Wrong supplier SKU"})
        assert r.status_code == 200, r.text
        assert r.json()["situacion"] == "ANULADA" and r.json()["motivo_anulacion"] == "Wrong supplier SKU"
        assert interno.post(f"/etiquetas/generaciones/{g['id']}/anular", {"motivo": "Again"}).status_code == 409
        # Ya no se descarga, no se confirma como impresa ni se reimprime
        assert interno.get(f"/etiquetas/generaciones/{g['id']}/archivo").status_code == 409
        assert interno.post(f"/etiquetas/generaciones/{g['id']}/impresion",
                            {"confirmo": True, "cantidad": 6}).status_code == 409
        assert interno.post(f"/etiquetas/generaciones/{g['id']}/reimprimir", {"motivo": "Damaged"}).status_code == 409
        # Los registros vuelven a estar pendientes y el trabajo se genera de nuevo, en otra ejecución
        tr = interno.get(f"/etiquetas/trabajos/{tr['id']}").json()
        assert tr["estado"] in ("VALIDADO", "PARCIAL") and all(r["estado"] != "GENERADO" for r in tr["registros"])
        tr = generado(interno, tr)
        assert tr["estado"] == "GENERADO" and [e["situacion"] for e in tr["ejecuciones"]] == ["ANULADA", "GENERADA"]
        assert tr["ejecuciones"][1]["total"] == 6
        # El ZIP del trabajo solo lleva la vigente
        z = interno.get(f"/etiquetas/trabajos/{tr['id']}/archivo")
        assert z.status_code == 200
        import io
        import json
        import zipfile
        with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
            resumen = json.loads(next(zf.read(n) for n in zf.namelist() if n.endswith(".json")))
        assert [e["id"] for e in resumen["ejecuciones"]] == [tr["ejecuciones"][1]["id"]]
        # En el historial queda anulada, con su motivo
        h = interno.get(f"/etiquetas/generaciones/{g['id']}").json()
        assert h["anulada_en"] and h["motivo_anulacion"] == "Wrong supplier SKU"
    finally:
        _limpiar(interno, t_, u)


def test_reimprimir_todo_o_algunos_rangos_con_motivo(interno, admin, tnf):
    t_, u, tr = _preparar(interno, admin, "REIMPRIMIR")
    try:
        tr = generado(interno, tr)
        g = tr["ejecuciones"][0]
        uno, dos = g["grupos"]
        original = pdf(interno.get(f"/etiquetas/generaciones/{g['id']}/archivo").content)
        assert len(original) == 6
        assert interno.post(f"/etiquetas/generaciones/{g['id']}/reimprimir", {}).status_code == 422
        # Todo el lote: las mismas etiquetas
        r = interno.post(f"/etiquetas/generaciones/{g['id']}/reimprimir", {"motivo": "Printer jam"})
        assert r.status_code == 200, r.text
        assert "reprint1" in r.headers["content-disposition"]
        assert [x[2] for x in pdf(r.content)] == [x[2] for x in original]
        # La etiqueta 2 y 3 del segundo grupo: con sus mismos números
        r = interno.post(f"/etiquetas/generaciones/{g['id']}/reimprimir",
                         {"motivo": "Two labels damaged", "seleccion": [{"item_id": dos["id"], "desde": 2, "hasta": 3}]})
        assert r.status_code == 200, r.text
        paginas = [x[2] for x in pdf(r.content)]
        assert paginas == [x[2] for x in original[4:6]] and paginas[0].strip().endswith("2/3")
        # Un rango fuera del grupo o un grupo de otro lote: no; un proveedor: no
        malo = interno.post(f"/etiquetas/generaciones/{g['id']}/reimprimir",
                            {"motivo": "x" * 5, "seleccion": [{"item_id": uno["id"], "desde": 2, "hasta": 4}]})
        assert malo.status_code == 422
        assert interno.post(f"/etiquetas/generaciones/{g['id']}/reimprimir",
                            {"motivo": "x" * 5, "seleccion": [{"item_id": 999999}]}).status_code == 422
        # Reimprimir pide lo mismo que descargar (el proveedor de la OC también puede), y cuenta igual
        puede = tnf.get(f"/etiquetas/generaciones/{g['id']}/archivo").status_code == 200
        assert (tnf.post(f"/etiquetas/generaciones/{g['id']}/reimprimir", {"motivo": "Damaged"}).status_code == 200) == puede
        # Queda en el historial del lote (quién, cuándo, cuántas, por qué), sin cambiar el lote
        e = interno.get(f"/etiquetas/trabajos/{tr['id']}").json()["ejecuciones"][0]
        assert [(x["n"], x["total"], x["motivo"]) for x in e["reimpresiones"]][:2] == [(1, 6, "Printer jam"), (2, 2, "Two labels damaged")]
        assert e["reimpresiones"][1]["seleccion"] == [{"item_id": dos["id"], "desde": 2, "hasta": 3}] and e["reimpresiones"][0]["por"]
        assert e["total"] == 6 and e["situacion"] in ("GENERADA", "DESCARGADA")
        assert interno.get(f"/etiquetas/generaciones/{g['id']}").json()["reimpresiones"] == 2 + puede
    finally:
        _limpiar(interno, t_, u)
