"""Recorre el flujo completo OC -> factura -> PL -> cajas -> unidad de carga -> salida."""


def _oc(api, numero):
    oc = next(o for o in api.get("/ordenes", params={"solo_disponible": False}).json()["items"] if o["numero"] == numero)
    return api.get(f"/ordenes/{oc['id']}/posiciones").json()


def _pos(det, talla, estilo=None):
    return next(p for p in det["posiciones"] if p["talla"] == talla and (estilo is None or p["estilo"] == estilo))


estado = {}


def test_alcance_por_proveedor(tnf, vans):
    ocs_tnf = {o["numero"] for o in tnf.get("/ordenes", params={"solo_disponible": False}).json()["items"]}
    ocs_vans = {o["numero"] for o in vans.get("/ordenes", params={"solo_disponible": False}).json()["items"]}
    assert "4500012345" in ocs_tnf and "4500020001" not in ocs_tnf
    assert ocs_tnf.isdisjoint(ocs_vans)
    oc_tnf = next(o for o in tnf.get("/ordenes").json()["items"] if o["numero"] == "4500012345")
    assert vans.get(f"/ordenes/{oc_tnf['id']}/posiciones").status_code == 404


def test_factura_parcial_y_reglas(tnf):
    det = _oc(tnf, "4500012345")
    s, m, xl = _pos(det, "S"), _pos(det, "M"), _pos(det, "XL")
    zap10 = _pos(det, "10", "NF0A7W4G")
    # Factura con cantidad parcial de S y completa de XL (27) y calzado talla 10
    r = tnf.post("/facturas", {"lineas": [
        {"posicion_id": s["id"], "cantidad": 25},
        {"posicion_id": xl["id"], "cantidad": 27},
        {"posicion_id": zap10["id"], "cantidad": 50},
    ]}, clave="crear-1")
    assert r.status_code == 200, r.text
    fid = r.json()["id"]
    estado["fid"] = fid
    # Idempotencia: la misma clave no crea otra factura
    r2 = tnf.post("/facturas", {"lineas": [{"posicion_id": m["id"], "cantidad": 1}]}, clave="crear-1")
    assert r2.json()["id"] == fid
    assert _pos(_oc(tnf, "4500012345"), "S")["disponible"] == 15

    # Exceso sobre lo disponible
    f = tnf.get(f"/facturas/{fid}").json()
    r = tnf.post(f"/facturas/{fid}/lineas", {"version": f["version"], "lineas": [{"posicion_id": s["id"], "cantidad": 99}]})
    assert r.status_code == 422

    # Regla: el saldo de S no puede ir a otra factura mientras esta siga activa
    r = tnf.post("/facturas", {"lineas": [{"posicion_id": s["id"], "cantidad": 5}]})
    assert r.status_code == 422 and "ya está en" in r.json()["detalle"][0]["mensaje"]

    # Pero sí se agrega a la misma factura (suma a la línea existente)
    r = tnf.post(f"/facturas/{fid}/lineas", {"version": f["version"], "lineas": [
        {"posicion_id": s["id"], "cantidad": 15}, {"posicion_id": m["id"], "cantidad": 60}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"agregadas": 1, "aumentadas": 1, "advertencias": []}

    # Compatibilidad: no se mezclan centros (PA10 con PA20)
    pa20 = _oc(tnf, "4500012350")["posiciones"][0]
    f = tnf.get(f"/facturas/{fid}").json()
    r = tnf.post(f"/facturas/{fid}/lineas", {"version": f["version"], "lineas": [{"posicion_id": pa20["id"], "cantidad": 1}]})
    assert r.status_code == 422 and "centros" in r.json()["detalle"][0]["mensaje"]


def test_version_conflicto(tnf):
    fid = estado["fid"]
    r = tnf.patch(f"/facturas/{fid}", {"version": 1, "observaciones": "x"})
    assert r.status_code == 409 and r.json()["codigo"] == "conflicto_version"


def test_precio_requiere_motivo(tnf):
    fid = estado["fid"]
    f = tnf.get(f"/facturas/{fid}").json()
    linea = f["lineas"][0]
    r = tnf.patch(f"/facturas/{fid}/lineas", {"version": f["version"], "cambios": [
        {"linea_id": linea["id"], "precio_unitario": linea["precio_oc"] + 1}]})
    assert r.status_code == 422 and r.json()["detalle"][0]["codigo"] == "motivo_precio"
    r = tnf.patch(f"/facturas/{fid}/lineas", {"version": f["version"], "cambios": [
        {"linea_id": linea["id"], "precio_unitario": linea["precio_oc"] + 1, "motivo_precio": "Ajuste acordado"}]})
    assert r.status_code == 200, r.text


def _empacar(api, pl_id, version, filas, sobrante="caja_parcial"):
    """filas: [(pl_linea_id, plantilla_id)]"""
    return api.post(f"/packing-lists/{pl_id}/empaque/aplicar", {
        "version": version, "sobrante": sobrante,
        "filas": [{"pl_linea_id": l, "plantilla_id": t} for l, t in filas]})


def test_packing_list_pendientes_mover(tnf):
    fid = estado["fid"]
    r = tnf.post(f"/facturas/{fid}/packing-lists", {})
    assert r.status_code == 200, r.text
    pl_id = r.json()["id"]
    estado["pl"] = pl_id
    # Sin saldo: segundo PL con pendientes explica dónde está todo
    r = tnf.post(f"/facturas/{fid}/packing-lists", {})
    assert r.status_code == 409 and r.json()["codigo"] == "sin_saldo"

    pl = tnf.get(f"/packing-lists/{pl_id}").json()
    assert pl["plantillas"] and all(t["proveedor_id"] if "proveedor_id" in t else True for t in pl["plantillas"])
    zap = next(l for l in pl["lineas"] if l["unidad"] == "PAR")
    # Mover solo 14 de los 50 pares a un PL nuevo (sin dividir antes)
    r = tnf.post(f"/packing-lists/{pl_id}/mover", {"version": pl["version"],
                 "movimientos": [{"pl_linea_id": zap["id"], "cantidad": 14}], "destino_pl_id": None})
    assert r.status_code == 200, r.text
    estado["pl2"] = r.json()["destino_id"]
    assert r.json()["destino_numero"] == "PL-002"
    pl = tnf.get(f"/packing-lists/{pl_id}").json()
    assert next(l for l in pl["lineas"] if l["unidad"] == "PAR")["cantidad"] == 36


def test_plantilla_con_sobrante(tnf):
    pl_id = estado["pl"]
    pl = tnf.get(f"/packing-lists/{pl_id}").json()
    plantillas = tnf.get("/plantillas").json()
    chaqueta = next(t for t in plantillas if t["nombre"] == "Caja chaqueta 10 un")
    xl = next(l for l in pl["lineas"] if l["talla"] == "XL")
    assert xl["cantidad"] == 27
    previa = tnf.post(f"/packing-lists/{pl_id}/empaque/previa",
                      {"filas": [{"pl_linea_id": xl["id"], "plantilla_id": chaqueta["id"]}]}).json()
    assert previa["resumen"]["cajas_completas"] == 2 and previa["resumen"]["sobrante_total"] == 7
    # Una plantilla de pares no aplica a una fila en unidades: se omite, no falla
    calzado = next(t for t in plantillas if t["nombre"] == "Caja calzado 12 pares")
    previa = tnf.post(f"/packing-lists/{pl_id}/empaque/previa",
                      {"filas": [{"pl_linea_id": xl["id"], "plantilla_id": calzado["id"]}]}).json()
    assert previa["resumen"]["filas"] == 0 and previa["filas"][0]["omitida"]
    r = _empacar(tnf, pl_id, pl["version"], [(xl["id"], chaqueta["id"])])
    assert r.status_code == 200, r.text
    pl = tnf.get(f"/packing-lists/{pl_id}").json()
    grupos = [g for g in pl["grupos"] if g["items"][0]["pl_linea_id"] == xl["id"]]
    assert [(g["num_cajas"], g["items"][0]["cantidad_por_caja"], g["es_parcial"]) for g in grupos] == [(2, 10, False), (1, 7, True)]
    parcial = grupos[1]
    assert parcial["peso_estimado"] and parcial["peso_neto_caja"] == 6.3 and parcial["peso_bruto_caja"] == 7.5
    assert next(l for l in pl["lineas"] if l["id"] == xl["id"])["sin_caja"] == 0


def test_reducir_factura_con_pl(tnf):
    fid = estado["fid"]
    f = tnf.get(f"/facturas/{fid}").json()
    m = next(l for l in f["lineas"] if l["talla"] == "M")
    r = tnf.patch(f"/facturas/{fid}/lineas", {"version": f["version"], "cambios": [{"linea_id": m["id"], "cantidad": 50}]})
    assert r.status_code == 409 and r.json()["codigo"] == "requiere_ajuste_pl"
    assert r.json()["detalle"][0]["hay_que_liberar"] == 10
    r = tnf.patch(f"/facturas/{fid}/lineas", {"version": f["version"], "ajuste_pl": "automatico",
                  "cambios": [{"linea_id": m["id"], "cantidad": 50}]})
    assert r.status_code == 200, r.text
    # Lo empacado no se libera automáticamente
    xl = next(l for l in f["lineas"] if l["talla"] == "XL")
    f = tnf.get(f"/facturas/{fid}").json()
    r = tnf.patch(f"/facturas/{fid}/lineas", {"version": f["version"], "ajuste_pl": "automatico",
                  "cambios": [{"linea_id": xl["id"], "cantidad": 20}]})
    assert r.status_code == 409 and r.json()["codigo"] == "ajuste_insuficiente"


def test_empacar_todo_y_finalizar(tnf):
    pl_id = estado["pl"]
    plantillas = {t["nombre"]: t for t in tnf.get("/plantillas").json()}
    pl = tnf.get(f"/packing-lists/{pl_id}").json()
    # Todo en un solo paso: cada fila con la plantilla de su unidad
    por_unidad = {"UN": plantillas["Caja chaqueta 10 un"]["id"], "PAR": plantillas["Caja calzado 12 pares"]["id"]}
    filas = [(l["id"], por_unidad[l["unidad"]]) for l in pl["lineas"] if l["sin_caja"]]
    r = _empacar(tnf, pl_id, pl["version"], filas)
    assert r.status_code == 200, r.text
    v = r.json()["version"]
    # 36 pares / 12 = 3 cajas exactas, sin sobrante; pesos parciales pendientes de confirmar
    r = tnf.post(f"/packing-lists/{pl_id}/finalizar", {"version": v})
    assert r.status_code == 422 and any(e.get("codigo") == "peso_estimado" for e in r.json()["detalle"])
    pl = tnf.get(f"/packing-lists/{pl_id}").json()
    estimadas = [g["id"] for g in pl["grupos"] if g["peso_estimado"]]
    r = tnf.patch(f"/packing-lists/{pl_id}/cajas", {"version": pl["version"], "grupo_ids": estimadas, "confirmar_pesos": True})
    assert r.status_code == 200, r.text
    r = tnf.post(f"/packing-lists/{pl_id}/finalizar", {"version": r.json()["version"]})
    assert r.status_code == 200, r.text

    # PL-002: 14 pares -> 1 caja de 12 + caja parcial de 2. La plantilla se
    # sugiere sola porque el mismo estilo ya se empacó con ella en PL-001.
    pl2 = tnf.get(f"/packing-lists/{estado['pl2']}").json()
    fila = pl2["lineas"][0]
    assert fila["plantilla_sugerida_id"] == plantillas["Caja calzado 12 pares"]["id"]
    r = _empacar(tnf, pl2["id"], pl2["version"], [(fila["id"], fila["plantilla_sugerida_id"])])
    assert r.status_code == 200 and r.json()["resumen"]["cajas_completas"] == 1, r.text
    pl2 = tnf.get(f"/packing-lists/{pl2['id']}").json()
    assert [g["num_cajas"] for g in pl2["grupos"]] == [1, 1] and pl2["grupos"][1]["es_parcial"]
    r = tnf.patch(f"/packing-lists/{pl2['id']}/cajas", {"version": pl2["version"],
                  "grupo_ids": [g["id"] for g in pl2["grupos"]], "confirmar_pesos": True})
    r = tnf.post(f"/packing-lists/{pl2['id']}/finalizar", {"version": r.json()["version"]})
    assert r.status_code == 200, r.text


def test_finalizar_factura(tnf):
    fid = estado["fid"]
    f = tnf.get(f"/facturas/{fid}").json()
    r = tnf.post(f"/facturas/{fid}/finalizar", {"version": f["version"]})
    assert r.status_code == 422 and any("número" in e["mensaje"] for e in r.json()["detalle"])
    r = tnf.patch(f"/facturas/{fid}", {"version": f["version"], "numero": "INV-2026-001", "fecha": "2026-09-20"})
    assert r.status_code == 200
    r = tnf.post(f"/facturas/{fid}/finalizar", {"version": r.json()["version"]})
    assert r.status_code == 200, r.text
    f = tnf.get(f"/facturas/{fid}").json()
    assert f["estado"] == "FINALIZADA" and f["lista_transporte"]


def test_transporte_y_salida(interno, tnf):
    e = interno.get("/embarques").json()[0]
    det = interno.get(f"/embarques/{e['id']}").json()
    unidad = det["unidades"][0]
    disp = interno.get(f"/unidades/{unidad['id']}/disponibles").json()
    grupo = next(g for g in disp if g["factura_id"] == estado["fid"])
    pl_ids = [p["id"] for p in grupo["packing_lists"]]
    r = interno.post(f"/unidades/{unidad['id']}/asignar", {"pl_ids": pl_ids, "modo": "TENTATIVA"})
    assert r.status_code == 200, r.text
    assert r.json()["tentativos"] == len(pl_ids)
    r = interno.post(f"/embarques/{e['id']}/eventos", {"tipo": "SALIDA", "fecha": "2026-10-01T08:00:00"})
    assert r.status_code == 409 and r.json()["codigo"] == "tentativas_pendientes"
    r = interno.post(f"/unidades/{unidad['id']}/confirmar", {"pl_ids": pl_ids})
    assert r.status_code == 200, r.text
    r = interno.post(f"/embarques/{e['id']}/eventos", {"tipo": "SALIDA", "fecha": "2026-10-01T08:00:00"})
    assert r.status_code == 200 and r.json()["estado"] == "EN_TRANSITO"
    # El proveedor ve el seguimiento desde su factura
    f = tnf.get(f"/facturas/{estado['fid']}").json()
    assert f["packing_lists"][0]["transporte"]["estado"] == "EN_TRANSITO"
    # Y no puede usar el módulo de transporte
    assert tnf.get("/embarques").status_code == 403
    # Quitar después de la salida exige motivo
    r = interno.post(f"/unidades/{unidad['id']}/desasignar", {"pl_ids": pl_ids[:1]})
    assert r.status_code == 422


def test_eliminar_linea_con_cascada(vans):
    det = _oc(vans, "4500020001")
    p7, p8 = _pos(det, "7"), _pos(det, "8")
    fid = vans.post("/facturas", {"lineas": [{"posicion_id": p7["id"], "cantidad": 36},
                                            {"posicion_id": p8["id"], "cantidad": 48}]}).json()["id"]
    pl_id = vans.post(f"/facturas/{fid}/packing-lists", {}).json()["id"]
    pl = vans.get(f"/packing-lists/{pl_id}").json()
    t = next(t for t in vans.get("/plantillas").json() if t["nombre"] == "Master 12 pares")
    _empacar(vans, pl_id, pl["version"], [(l["id"], t["id"]) for l in pl["lineas"]], "sin_caja")
    f = vans.get(f"/facturas/{fid}").json()
    linea7 = next(l for l in f["lineas"] if l["talla"] == "7")
    r = vans.post(f"/facturas/{fid}/lineas/eliminar", {"version": f["version"], "linea_ids": [linea7["id"]]})
    assert r.status_code == 409 and r.json()["codigo"] == "requiere_confirmacion"
    r = vans.post(f"/facturas/{fid}/lineas/eliminar", {"version": f["version"], "linea_ids": [linea7["id"]],
                  "confirmar_cascada": True})
    assert r.status_code == 200, r.text
    pl = vans.get(f"/packing-lists/{pl_id}").json()
    assert len(pl["lineas"]) == 1 and pl["totales"]["cajas"] == 4
    assert _pos(_oc(vans, "4500020001"), "7")["disponible"] == 36


def test_mover_cajas(vans):
    fs = vans.get("/facturas").json()["items"]
    fid = fs[0]["id"]
    f = vans.get(f"/facturas/{fid}").json()
    pl_id = f["packing_lists"][0]["id"]
    pl = vans.get(f"/packing-lists/{pl_id}").json()
    g = pl["grupos"][0]
    r = vans.post(f"/packing-lists/{pl_id}/mover-cajas", {"version": pl["version"],
                  "grupos": [{"grupo_id": g["id"], "num_cajas": 1}], "destino_pl_id": None})
    assert r.status_code == 200, r.text
    destino = vans.get(f"/packing-lists/{r.json()['destino_id']}").json()
    origen = vans.get(f"/packing-lists/{pl_id}").json()
    assert destino["totales"]["cajas"] == 1 and destino["lineas"][0]["cantidad"] == 12
    assert origen["totales"]["cajas"] == 3 and origen["lineas"][0]["cantidad"] == 36
    assert origen["lineas"][0]["sin_caja"] == 0


def test_importacion_oc(interno):
    csv = ("proveedor,oc,posicion,sociedad,centro,moneda,incoterm,codigo_sap,talla,cantidad,unidad,precio\n"
           "VANS,4500020099,00010,8000,PA10,USD,FOB,000000000099000010,9,24,PAR,20.5\n"
           "VANS,4500020001,00010,8000,PA10,USD,FOB,000000000020001010,7,10,PAR,25.5\n"
           "XXX,1,1,8000,PA10,USD,FOB,1,1,1,PAR,1\n")
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h,
                       files={"archivo": ("ocs.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    res = r.json()["resumen"]
    assert res["nuevo"] == 1 and res["error"] == 1
    r = interno.post(f"/ordenes/importar/{r.json()['importacion_id']}/aplicar")
    assert r.status_code == 200, r.text
    ocs = interno.get("/ordenes", params={"q": "4500020099"}).json()["items"]
    assert ocs and ocs[0]["por_unidad"]["PAR"]["cantidad"] == 24
    det = interno.get(f"/ordenes/{ocs[0]['id']}/posiciones").json()
    assert det["posiciones"][0]["codigo_sap"] == "000000000099000010"


def test_exportar(tnf):
    r = tnf.get(f"/packing-lists/{estado['pl']}/exportar")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    r = tnf.get(f"/facturas/{estado['fid']}/exportar")
    assert r.status_code == 200


def test_asignacion_automatica(interno, vans):
    """AUTO confirma lo que está listo y deja tentativo lo demás, en un paso."""
    e = interno.post("/embarques", {"tipo_transporte": "MARITIMO", "modalidad": "FCL"}).json()
    nueva = interno.post(f"/embarques/{e['id']}/unidades", {"tipo": "20GP"}).json()["id"]
    disp = interno.get(f"/unidades/{nueva}/disponibles").json()
    pls = [p for g in disp for p in g["packing_lists"]]
    listos = [p for p in pls if p["puede_confirmar"]]
    assert listos and len(listos) < len(pls)
    r = interno.post(f"/unidades/{nueva}/asignar", {"pl_ids": [p["id"] for p in pls], "modo": "AUTO"})
    assert r.status_code == 200, r.text
    assert r.json() == {"asignados": len(pls), "confirmados": len(listos), "tentativos": len(pls) - len(listos)}
    asignados = {p["id"]: p["asignacion"] for p in interno.get(f"/unidades/{nueva}").json()["asignados"]}
    assert all(asignados[p["id"]] == "CONFIRMADA" for p in listos)
    # Confirmar explícitamente sigue exigiendo documentos finalizados
    pendiente = next(p for p in pls if not p["puede_confirmar"])
    r = interno.post(f"/unidades/{nueva}/confirmar", {"pl_ids": [pendiente["id"]]})
    assert r.status_code == 422
    r = interno.post(f"/unidades/{nueva}/desasignar", {"pl_ids": [p["id"] for p in pls], "motivo": "Prueba"})
    assert r.status_code == 200, r.text


def test_dashboard(interno, tnf):
    d = interno.get("/dashboard").json()
    claves = {k["clave"] for k in d["kpis"]}
    assert {"por_facturar", "listas", "tentativas", "en_camino"} <= claves
    assert d["proveedores"] and {p["nombre"] for p in d["proveedores"]} >= {"The North Face", "Vans"}
    assert len(d["facturado_mes"]) == 6 and d["contenedores"] is not None
    # El proveedor solo ve lo suyo y no recibe datos internos
    p = tnf.get("/dashboard").json()
    assert "listas" not in {k["clave"] for k in p["kpis"]}
    assert p["proveedores"] == [] and p["contenedores"] == [] and p["alertas"] == []
    assert any(e["estado"] == "EN_TRANSITO" for e in p["envios"])
    flujo = p["flujo"]
    assert set(flujo) <= {"PAR", "UN"} and flujo["UN"]["embarcado"] > 0


def test_historial(tnf):
    h = tnf.get(f"/facturas/{estado['fid']}/historial").json()
    acciones = {x["accion"] for x in h}
    assert {"crear", "finalizar", "aplicar_plantilla", "asignar_unidad"} <= acciones
