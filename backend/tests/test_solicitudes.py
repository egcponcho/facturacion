"""Solicitudes de compra: crear, aprobar o rechazar, corregir, cancelar y
convertir en una OC en borrador."""


def _articulo(interno):
    """Un artículo del catálogo con su unidad (para que la OC lo reconozca)."""
    oc = interno.get("/ordenes").json()
    oc = oc["items"][0] if isinstance(oc, dict) else oc[0]
    det = interno.get(f"/ordenes/{oc['id']}").json()
    p = det["posiciones"][0] if "posiciones" in det else det["lineas"][0]
    return p["codigo_articulo"], p["unidad"], det["oc"]["proveedor"]["id"] if isinstance(det["oc"].get("proveedor"), dict) else det["oc"]["proveedor_id"]


def _nueva(api, **extra):
    datos = {"area": "Maintenance", "prioridad": "URGENTE", "motivo": "Spare parts",
             "lineas": [{"descripcion": "Bearing 6204", "cantidad": 10, "precio_estimado": 3.5}], **extra}
    r = api.post("/solicitudes", datos)
    assert r.status_code == 200, r.text
    return r.json()


def test_crear_y_validar(interno):
    s = _nueva(interno)
    assert s["numero"].startswith("SC-") and s["estado"] == "PENDIENTE" and s["prioridad"] == "URGENTE"
    assert s["estimado"] == 35 and s["articulos"] == 1 and s["solicitante"]
    assert _nueva(interno)["numero"] != s["numero"]
    r = interno.post("/solicitudes", {"area": "", "lineas": []})
    assert r.status_code == 422 and {e["campo"] for e in r.json()["detalle"]} >= {"area", "lineas"}
    d = interno.get("/solicitudes").json()
    assert any(x["id"] == s["id"] for x in d["items"]) and d["cuentas"]["por_aprobar"] >= 2


def test_rechazar_corregir_aprobar_cancelar(interno):
    s = _nueva(interno)
    assert interno.post(f"/solicitudes/{s['id']}/rechazar", {}).status_code == 422  # pide motivo
    r = interno.post(f"/solicitudes/{s['id']}/rechazar", {"comentario": "Too expensive"})
    assert r.json()["estado"] == "RECHAZADA" and r.json()["comentario_revision"] == "Too expensive"
    r = interno.put(f"/solicitudes/{s['id']}", {"area": "Maintenance", "lineas": [{"descripcion": "Bearing", "cantidad": 5}]})
    assert r.status_code == 200 and r.json()["estado"] == "PENDIENTE"
    r = interno.post(f"/solicitudes/{s['id']}/aprobar", {})
    assert r.json()["estado"] == "APROBADA"
    assert interno.post(f"/solicitudes/{s['id']}/aprobar", {}).status_code == 409
    assert interno.put(f"/solicitudes/{s['id']}", {"area": "x", "lineas": [{"descripcion": "y", "cantidad": 1}]}).status_code == 409
    assert interno.post(f"/solicitudes/{s['id']}/cancelar").json()["estado"] == "CANCELADA"


def test_convertir_en_oc(interno):
    codigo, unidad, proveedor_id = _articulo(interno)
    a = _nueva(interno, lineas=[{"codigo_articulo": codigo, "descripcion": "x", "cantidad": 12, "unidad": unidad, "precio_estimado": 2}])
    b = _nueva(interno, lineas=[{"codigo_articulo": codigo, "descripcion": "x", "cantidad": 6, "unidad": unidad}])
    assert interno.post("/solicitudes/convertir", {"solicitud_ids": [a["id"]], "proveedor_id": proveedor_id, "oc": "SC-OC-1"}).status_code == 409
    for s in (a, b):
        interno.post(f"/solicitudes/{s['id']}/aprobar", {})
    r = interno.post("/solicitudes/convertir", {"solicitud_ids": [a["id"], b["id"]], "proveedor_id": proveedor_id, "oc": "SC-OC-1"})
    assert r.status_code == 200, r.text
    oc = interno.get(f"/ordenes/{r.json()['oc_id']}").json()
    assert oc["oc"]["estado"] == "BORRADOR" and len(oc["borrador"]["lineas"]) == 2
    for s in (a, b):
        d = interno.get(f"/solicitudes/{s['id']}").json()
        assert d["estado"] == "CONVERTIDA" and d["oc"]["numero"] == "SC-OC-1"


def test_proveedor_no_ve_solicitudes(tnf):
    assert tnf.get("/solicitudes").status_code == 403
