"""Facturas y pagos a proveedores: lista con cuadre de tres vías, resumen,
programar, pagar y anular pagos, y vencimiento propio."""
from datetime import date, timedelta


def test_lista_y_cuadre(interno):
    r = interno.get("/pagos/facturas", params={"vista": "todas"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d["cuentas"]) == {"por_pagar", "diferencias", "pagadas", "todas"}
    assert d["items"], "la demo tiene facturas finalizadas"
    for f in d["items"]:
        assert f["cuadre"] in ("CUADRA", "PRECIO", "CANTIDAD", "POR_RECIBIR")
        assert f["estado_pago"] in ("PENDIENTE", "PROGRAMADA", "VENCIDA", "PAGADA")
        assert f["saldo"] == f["importe"] - f["pagado"]
        assert f["vence"]
    det = interno.get(f"/pagos/facturas/{d['items'][0]['id']}").json()
    assert det["lineas"] and {"facturado", "recibido", "precio_oc", "precio"} <= set(det["lineas"][0])


def test_proveedor_no_ve_pagos(tnf):
    assert tnf.get("/pagos/facturas").status_code == 403


def test_programar_pagar_y_anular(interno):
    f = interno.get("/pagos/facturas").json()["items"][0]
    fecha = (date.today() + timedelta(days=7)).isoformat()
    r = interno.post("/pagos/programar", {"factura_ids": [f["id"]], "fecha": fecha})
    assert r.status_code == 200, r.text
    det = interno.get(f"/pagos/facturas/{f['id']}").json()
    assert det["estado_pago"] == "PROGRAMADA" and det["programado"] == f["saldo"]
    pago = next(p for p in det["pagos"] if p["estado"] == "PROGRAMADO")
    # Nada más que programar
    assert interno.post("/pagos/programar", {"factura_ids": [f["id"]], "fecha": fecha}).status_code == 409

    res = interno.get("/pagos/resumen").json()
    assert len(res["semanas"]) == 6 and {t["tramo"] for t in res["antiguedad"]} == {"por_vencer", "1_15", "16_30", "mas_30"}

    r = interno.post(f"/pagos/{pago['id']}/anular")
    assert r.status_code == 200, r.text
    assert r.json()["estado_pago"] != "PROGRAMADA"
    interno.post("/pagos/programar", {"factura_ids": [f["id"]], "fecha": fecha})
    pago = next(p for p in interno.get(f"/pagos/facturas/{f['id']}").json()["pagos"] if p["estado"] == "PROGRAMADO")
    r = interno.post(f"/pagos/{pago['id']}/pagar", {"fecha": date.today().isoformat(), "referencia": "TRF-1"})
    assert r.status_code == 200, r.text
    assert r.json()["estado_pago"] == "PAGADA" and r.json()["saldo"] == 0
    assert interno.post(f"/pagos/{pago['id']}/anular").status_code == 409
    assert any(x["id"] == f["id"] for x in interno.get("/pagos/facturas", params={"vista": "pagadas"}).json()["items"])


def test_vencimiento_propio(interno):
    f = interno.get("/pagos/facturas").json()["items"][-1]
    ayer = (date.today() - timedelta(days=1)).isoformat()
    r = interno.put(f"/pagos/facturas/{f['id']}/vence", {"vence": ayer})
    assert r.status_code == 200, r.text
    assert r.json()["vence"] == ayer and r.json()["vence_propio"]
    if r.json()["estado_pago"] != "PROGRAMADA":
        assert r.json()["estado_pago"] == "VENCIDA"
    r = interno.put(f"/pagos/facturas/{f['id']}/vence", {"vence": None})
    assert not r.json()["vence_propio"]
