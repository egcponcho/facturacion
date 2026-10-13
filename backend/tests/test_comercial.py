"""Núcleo comercial: terceros, documentos con impuestos y cuotas, emisión con
número de serie, cobros parciales, notas de crédito, anulaciones, cuentas por
pagar desde la factura de proveedor y facturación recurrente."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.errores import ErrorNegocio
from app.core.organizacion import en_organizacion
from app.modelos import Documento, Factura, Usuario


def _d(v) -> Decimal:
    return Decimal(str(v))


@pytest.fixture(scope="module")
def config(interno):
    """Impuestos (IVA 13 % y retención 1 %), una condición en dos cuotas y un cliente."""
    def asegurar(catalogo, datos, clave="codigo"):
        items = interno.get(f"/catalogos/{catalogo}", params={"size": 200}).json()["items"]
        previo = next((x for x in items if x.get(clave) == datos[clave]), None)
        if previo:
            return previo
        r = interno.post(f"/catalogos/{catalogo}", datos)
        assert r.status_code == 200, r.text
        return r.json()

    asegurar("impuestos", {"codigo": "IVA13", "nombre": "VAT 13 %", "tipo": "PORCENTAJE", "tasa": 13, "pais": "SV",
                           "vigente_desde": "2020-01-01"})
    asegurar("impuestos", {"codigo": "RET1", "nombre": "Withholding 1 %", "tipo": "PORCENTAJE", "tasa": 1,
                           "es_retencion": True})
    cond = asegurar("condiciones_pago", {"codigo": "C3070", "nombre": "30 % now, 70 % at 60 days"})
    for n, pct, dias in ((1, 30, 0), (2, 70, 60)):
        cuotas = interno.get("/catalogos/cuotas_pago", params={"size": 200}).json()["items"]
        if not any(c["condicion_id"] == cond["id"] and c["numero"] == n for c in cuotas):
            r = interno.post("/catalogos/cuotas_pago", {"condicion_id": cond["id"], "numero": n, "porcentaje": pct, "dias": dias})
            assert r.status_code == 200, r.text
    r = interno.post("/terceros", {"codigo": "CLI-ACME", "nombre": "Acme Retail", "razon_social": "Acme Retail, S.A.",
                                   "tipo_identificacion": "NIT", "id_fiscal": "0614-999999-101-1", "pais": "SV",
                                   "moneda": "USD", "roles": ["CLIENTE"],
                                   "direcciones": [{"tipo": "FISCAL", "linea1": "Av. Norte 100", "ciudad": "San Salvador",
                                                    "pais": "SV"}],
                                   "medios": [{"tipo": "CORREO", "valor": "ap@acme.demo", "uso": "FACTURACION",
                                               "principal": True}]})
    assert r.status_code == 200, r.text
    yield {"cliente": r.json(), "condicion": cond}
    # La condición de prueba deja de ofrecerse (los documentos que la usan la conservan)
    interno.patch(f"/catalogos/condiciones_pago/{cond['id']}", {"activo": False})


def _factura(interno, config, lineas=None, **kw):
    datos = {"tipo": "FACTURA", "sociedad": "8000", "tercero_id": config["cliente"]["id"], "fecha": "2026-10-01",
             "lineas": lineas or [
                 {"descripcion": "Consulting services", "cantidad": 3, "unidad": "UN", "precio_unitario": "33.335",
                  "impuestos": ["IVA13"]},
                 {"descripcion": "Training", "cantidad": 1, "precio_unitario": 100, "descuento_pct": 10,
                  "impuestos": ["IVA13", "RET1"]}], **kw}
    r = interno.post("/documentos", datos)
    assert r.status_code == 200, r.text
    return r.json()


def test_tercero_con_identidad_unica(interno, config):
    t = interno.get(f"/terceros/{config['cliente']['id']}").json()
    assert t["roles"] == ["CLIENTE"] and t["correo"] == "ap@acme.demo" and "Av. Norte 100" in t["direccion"]
    # La misma identificación fiscal en el mismo país no se repite
    r = interno.post("/terceros", {"nombre": "Acme bis", "id_fiscal": "0614-999999-101-1", "pais": "SV", "roles": ["CLIENTE"]})
    assert r.status_code == 422 and "tax ID" in r.text
    r = interno.post("/terceros", {"nombre": "Bad mail", "roles": ["CLIENTE"], "medios": [{"tipo": "CORREO", "valor": "x@"}]})
    assert r.status_code == 422
    # Los proveedores de los datos maestros ya son terceros con su rol
    proveedores = interno.get("/terceros", params={"rol": "PROVEEDOR"}).json()["items"]
    assert {"VANS", "TNF"} <= {p["codigo"] for p in proveedores}


def test_borrador_calcula_exacto(interno, config):
    d = _factura(interno, config)
    assert d["estado"] == "BORRADOR" and d["numero"] is None
    l1, l2 = d["lineas"]
    # 3 × 33.335 = 100.005 → 100.01 (mitad hacia arriba); IVA 13 % = 13.00
    assert _d(l1["subtotal"]) == Decimal("100.01") and _d(l1["impuestos"]) == Decimal("13.00")
    # 100 − 10 % = 90; IVA 11.70; retención 0.90
    assert _d(l2["subtotal"]) == Decimal("90") and _d(l2["impuestos"]) == Decimal("11.7") and _d(l2["retenciones"]) == Decimal("0.9")
    assert _d(d["subtotal"]) == Decimal("190.01") and _d(d["descuentos"]) == Decimal("10")
    assert _d(d["total"]) == Decimal("190.01") + Decimal("24.70") - Decimal("0.90")
    assert {i["codigo"] for i in d["impuestos_detalle"]} == {"IVA13", "RET1"}
    # En borrador se edita y se recalcula
    r = interno.patch(f"/documentos/{d['id']}", {"version": d["version"], "lineas": [
        {"descripcion": "Only one line", "cantidad": 2, "precio_unitario": 50, "impuestos": []}]})
    assert r.status_code == 200 and _d(r.json()["total"]) == Decimal("100")
    assert interno.delete_(f"/documentos/{d['id']}").status_code == 200


def test_emitir_numera_fija_y_crea_cuotas(interno, config):
    d = _factura(interno, config, condicion_pago="C3070")
    e = interno.post(f"/documentos/{d['id']}/emitir", {"version": d["version"]})
    assert e.status_code == 200, e.text
    e = e.json()
    assert e["estado"] == "EMITIDO" and e["numero"].startswith("F-") and e["copia"]["tercero"]["id_fiscal"] == "0614-999999-101-1"
    total = _d(e["total"])
    v1, v2 = e["vencimientos"]
    assert _d(v1["importe"]) + _d(v2["importe"]) == total
    assert v2["fecha"] == (date(2026, 10, 1) + timedelta(days=60)).isoformat() and e["fecha_vencimiento"] == v2["fecha"]
    # Emitido: no se edita, no se emite dos veces, no se borra
    assert interno.patch(f"/documentos/{d['id']}", {"notas": "x"}).status_code == 409
    assert interno.post(f"/documentos/{d['id']}/emitir", {}).status_code == 409
    assert interno.delete_(f"/documentos/{d['id']}").status_code == 409
    # El siguiente toma el número siguiente de la serie
    otro = _factura(interno, config)
    e2 = interno.post(f"/documentos/{otro['id']}/emitir", {}).json()
    assert int(e2["numero"].split("-")[1]) == int(e["numero"].split("-")[1]) + 1


def test_cobros_parciales_y_saldo(interno, config):
    d = _factura(interno, config, fecha=date.today().isoformat(), condicion_pago="NETO30")
    d = interno.post(f"/documentos/{d['id']}/emitir", {}).json()
    total = _d(d["total"])
    base = {"direccion": "COBRO", "tercero_id": config["cliente"]["id"], "sociedad": "8000", "fecha": "2026-10-05",
            "moneda": "USD", "metodo_pago": "TRANSFERENCIA"}
    r = interno.post("/pagos", {**base, "importe": "100", "aplicaciones": [{"documento_id": d["id"], "importe": "100"}]})
    assert r.status_code == 200, r.text
    doc = interno.get(f"/documentos/{d['id']}").json()
    assert _d(doc["saldo"]) == total - 100 and doc["estado_cobro"] == "PARCIAL"
    # Más que el saldo: no
    r = interno.post("/pagos", {**base, "importe": "500", "aplicaciones": [{"documento_id": d["id"], "importe": "500"}]})
    assert r.status_code == 422 and "balance" in r.text
    # Lo aplicado no supera el pago
    r = interno.post("/pagos", {**base, "importe": "10", "aplicaciones": [{"documento_id": d["id"], "importe": "20"}]})
    assert r.status_code == 422
    # Un anticipo sin aplicar y luego aplicado
    anticipo = interno.post("/pagos", {**base, "importe": str(total)}).json()
    assert _d(anticipo["sin_aplicar"]) == total
    cuenta = interno.get(f"/terceros/{config['cliente']['id']}/estado-cuenta").json()
    assert any(p["id"] == anticipo["id"] for p in cuenta["pagos_sin_aplicar"])
    r = interno.post(f"/pagos/{anticipo['id']}/aplicar", {"aplicaciones": [{"documento_id": d["id"], "importe": str(total - 100)}]})
    assert r.status_code == 200, r.text
    doc = interno.get(f"/documentos/{d['id']}").json()
    assert _d(doc["saldo"]) == 0 and doc["estado_cobro"] == "PAGADO"
    # Con pagos no se anula; anulando el pago vuelve el saldo
    assert interno.post(f"/documentos/{d['id']}/anular", {"motivo": "error"}).status_code == 409
    assert interno.post(f"/pagos/{anticipo['id']}/anular", {"motivo": "bounced"}).status_code == 200
    assert _d(interno.get(f"/documentos/{d['id']}").json()["saldo"]) == total - 100


def test_nota_de_credito_rectifica_y_se_aplica(interno, config):
    d = interno.post(f"/documentos/{_factura(interno, config)['id']}/emitir", {}).json()
    r = interno.post(f"/documentos/{d['id']}/nota", {"tipo": "NOTA_CREDITO", "motivo": "Returned training",
                                                    "lineas": [{"indice": 1, "cantidad": 1}]})
    assert r.status_code == 200, r.text
    nc = r.json()
    assert nc["relaciones"][0]["tipo"] == "RECTIFICA" and nc["relaciones"][0]["documento_id"] == d["id"]
    nc = interno.post(f"/documentos/{nc['id']}/emitir", {}).json()
    assert nc["numero"].startswith("NC-")
    doc = interno.get(f"/documentos/{d['id']}").json()
    assert _d(doc["saldo"]) == _d(d["total"]) - _d(nc["total"])
    # Una nota de crédito no puede pasar el total del documento que corrige
    r = interno.post(f"/documentos/{d['id']}/nota", {"tipo": "NOTA_CREDITO", "motivo": "Too much"})
    big = interno.post(f"/documentos/{r.json()['id']}/emitir", {})
    assert big.status_code == 422 and "exceed" in big.text
    # Una nota exige su documento de origen
    sin_origen = interno.post("/documentos", {"tipo": "NOTA_CREDITO", "sociedad": "8000", "tercero_id": config["cliente"]["id"],
                                              "lineas": [{"descripcion": "x", "cantidad": 1, "precio_unitario": 1}]}).json()
    assert interno.post(f"/documentos/{sin_origen['id']}/emitir", {}).status_code == 422
    # Anular la nota devuelve el saldo
    assert interno.post(f"/documentos/{nc['id']}/anular", {"motivo": "mistake"}).status_code == 200
    assert _d(interno.get(f"/documentos/{d['id']}").json()["saldo"]) == _d(d["total"])


def test_reglas_de_las_partes(interno, config):
    # Una factura emitida es para un cliente; VANS es proveedor
    vans = next(t for t in interno.get("/terceros", params={"rol": "PROVEEDOR"}).json()["items"] if t["codigo"] == "VANS")
    r = interno.post("/documentos", {"tipo": "FACTURA", "sociedad": "8000", "tercero_id": vans["id"],
                                     "lineas": [{"descripcion": "x", "cantidad": 1, "precio_unitario": 1}]})
    assert r.status_code == 422 and "not a customer" in r.text
    # Un impuesto inexistente o fuera de vigencia se rechaza
    r = interno.post("/documentos", {"tipo": "FACTURA", "sociedad": "8000", "tercero_id": config["cliente"]["id"],
                                     "fecha": "2019-01-01",
                                     "lineas": [{"descripcion": "x", "cantidad": 1, "precio_unitario": 1, "impuestos": ["IVA13"]}]})
    assert r.status_code == 422 and "not in force" in r.text
    # Sin permiso comercial no hay acceso
    assert interno.c.get("/api/documentos").status_code in (401, 403)


def test_factura_de_proveedor_es_cuenta_por_pagar(interno):
    with SessionLocal() as db, en_organizacion(1):
        from app.modulos.comercial import proveedores as cxp

        f = db.scalar(select(Factura).where(Factura.estado == "FINALIZADA").order_by(Factura.id))
        user = db.scalar(select(Usuario).where(Usuario.email == "interno@demo.com"))
        d = cxp.registrar(db, user, f)
        db.commit()
        fid, did, total = f.id, d.id, sum(_d(x.cantidad) * _d(x.precio_unitario) for x in f.lineas)
    doc = interno.get(f"/documentos/{did}").json()
    assert doc["direccion"] == "RECIBIDO" and doc["factura_id"] == fid and doc["estado"] == "EMITIDO"
    assert abs(_d(doc["total"]) - total) <= Decimal("0.01") * len(doc["lineas"])
    assert all(x["factura_linea_id"] for x in doc["lineas"])
    # Se paga como cualquier documento recibido
    r = interno.post("/pagos", {"direccion": "PAGO", "tercero_id": doc["tercero_id"], "sociedad": doc["sociedad"],
                                "fecha": "2026-10-10", "moneda": doc["moneda"], "importe": "1",
                                "aplicaciones": [{"documento_id": did, "importe": "1"}]})
    assert r.status_code == 200, r.text
    # No se edita aquí ni se reabre su factura mientras tenga pagos
    assert interno.patch(f"/documentos/{did}", {"notas": "x"}).status_code == 409
    with SessionLocal() as db, en_organizacion(1):
        from app.modulos.comercial import proveedores as cxp

        with pytest.raises(ErrorNegocio):
            cxp.reabrir(db, db.get(Factura, fid))
    interno.post(f"/pagos/{r.json()['id']}/anular", {"motivo": "test"})
    # Un cobro no salda una factura recibida
    r = interno.post("/pagos", {"direccion": "COBRO", "tercero_id": doc["tercero_id"], "sociedad": doc["sociedad"],
                                "fecha": "2026-10-10", "moneda": doc["moneda"], "importe": "1",
                                "aplicaciones": [{"documento_id": did, "importe": "1"}]})
    assert r.status_code == 422


def test_facturacion_recurrente(interno, config):
    modelo = _factura(interno, config, lineas=[{"descripcion": "Monthly fee", "cantidad": 1, "precio_unitario": 50}])
    r = interno.post("/recurrentes", {"nombre": "Fee", "modelo_id": modelo["id"], "frecuencia": "MENSUAL",
                                      "proxima": "2026-01-31", "hasta": "2026-04-30", "emitir": True})
    assert r.status_code == 200, r.text
    r = interno.post("/recurrentes/generar?hasta=2026-12-31", {})
    assert r.status_code == 200, r.text
    creados = r.json()
    mias = [c for c in creados if c["recurrente"] == "Fee"]
    assert [c["fecha"] for c in mias] == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]
    assert all(interno.get(f"/documentos/{c['documento_id']}").json()["estado"] == "EMITIDO" for c in mias)
    assert not [c for c in interno.post("/recurrentes/generar?hasta=2026-12-31", {}).json() if c["recurrente"] == "Fee"]


def test_listas_filtran_por_columna(interno, config):
    r = interno.get("/documentos", params={"direccion": "EMITIDO", "f": '{"estado": ["EMITIDO"]}'}).json()
    assert r["total"] >= 1 and all(x["estado"] == "EMITIDO" for x in r["items"])
    valores = interno.get("/documentos/valores", params={"columna": "tipo"}).json()
    assert {"FACTURA"} <= {v["valor"] for v in valores}
    assert interno.get("/pagos", params={"direccion": "COBRO"}).json()["total"] >= 1
    with SessionLocal() as db:
        assert db.scalar(select(Documento.id).where(Documento.estado == "EMITIDO", Documento.numero.is_(None),
                                                    Documento.referencia_externa.is_(None))) is None


def test_busqueda_por_texto(interno, config):
    assert [x["codigo"] for x in interno.get("/terceros", params={"q": "acme retail"}).json()["items"]] == ["CLI-ACME"]
    assert interno.get("/terceros", params={"q": "0614-999999"}).json()["total"] == 1
    docs = interno.get("/documentos", params={"q": "acme", "direccion": ""}).json()["items"]
    assert docs and all(d["tercero"] == "Acme Retail" for d in docs)
    assert interno.get("/pagos", params={"q": "acme"}).json()["total"] >= 1
