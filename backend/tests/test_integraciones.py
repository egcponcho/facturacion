"""Capa de integración con sistemas externos: integraciones, mapeos
versionados, entrada de OCs con nombres y códigos propios del sistema externo
(sin tocar el núcleo), salida de facturas, bitácora, referencias externas y
contenido repetido que no se aplica dos veces."""
import csv
import io
import json

import pytest


def _integracion(api, codigo, adaptador="archivo_tabular", **parametros):
    r = api.post("/integraciones", {"codigo": codigo, "nombre": f"ERP {codigo}", "sistema": "ERP de prueba",
                                    "adaptador": adaptador, "parametros": parametros})
    assert r.status_code == 200, r.text
    return r.json()


def _subir(api, integracion_id, entidad, nombre, contenido):
    return api.c.post(f"/api/integraciones/{integracion_id}/entrada/{entidad}", headers=api.h,
                      files={"archivo": (nombre, contenido, "application/octet-stream")})


def test_integracion_validada_y_codigo_unico(admin):
    x = _integracion(admin, "INT-VAL")
    assert x["adaptador"] == "archivo_tabular" and x["parametros"]["fila_encabezado"] == 1
    assert admin.post("/integraciones", {"codigo": "int-val", "nombre": "Otra", "adaptador": "json"}).status_code == 409
    assert admin.post("/integraciones", {"codigo": "X1", "nombre": "X", "adaptador": "sap_rfc"}).status_code == 422
    assert admin.post("/integraciones", {"codigo": "X2", "nombre": "X", "adaptador": "archivo_tabular",
                                         "parametros": {"formato_salida": "pdf"}}).status_code == 422
    meta = admin.get("/integraciones").json()
    assert {a["codigo"] for a in meta["adaptadores"]} == {"archivo_tabular", "json"}
    assert {e["entidad"] for e in meta["entidades"]} == {"ordenes_compra", "facturas"}


def test_sin_permiso_no_se_configura_ni_se_ejecuta(interno, vans):
    assert interno.get("/integraciones").status_code == 403
    assert interno.post("/integraciones", {"codigo": "NO", "nombre": "No", "adaptador": "json"}).status_code == 403
    assert vans.get("/integraciones").status_code == 403


def test_mapeo_versionado(admin):
    x = _integracion(admin, "INT-MAP")
    ruta = f"/integraciones/{x['id']}/mapeos/ordenes_compra/entrada"
    v1 = admin.put(ruta, {"campos": {"oc": "PO Num"}}).json()
    assert v1["version"] == 1 and v1["vigente"]
    assert admin.put(ruta, {"campos": {"oc": "PO Num"}}).json()["version"] == 1  # sin cambios, sin versión nueva
    v2 = admin.put(ruta, {"campos": {"oc": "Order"}}).json()
    assert v2["version"] == 2
    versiones = admin.get(ruta).json()
    assert [(v["version"], v["vigente"]) for v in versiones] == [(2, True), (1, False)]
    # Solo campos internos de la entidad; lo que identifica la línea no lleva valor por defecto
    assert admin.put(ruta, {"campos": {"EBELN": "x"}}).status_code == 422
    assert admin.put(ruta, {"valores": {"oc": "123"}}).status_code == 422
    assert admin.put(f"/integraciones/{x['id']}/mapeos/facturas/entrada", {"campos": {}}).status_code == 422


@pytest.fixture
def base_oc(admin):
    base = admin.get("/ordenes", params={"q": "4400003901", "solo_disponible": False}).json()["items"][0]
    return admin.get(f"/ordenes/{base['id']}/posiciones").json()["posiciones"][0]


def test_entrada_de_ocs_con_nombres_y_codigos_externos(admin, base_oc):
    x = _integracion(admin, "INT-OC", delimitador=";")
    # El sistema externo llama a sus columnas a su manera y manda sus propios códigos de liberación
    assert admin.put(f"/integraciones/{x['id']}/mapeos/ordenes_compra/entrada", {
        "campos": {"proveedor": "Vendor", "oc": "Order", "posicion": "Item", "sociedad": "Legal entity",
                   "centro": "Site", "almacen": "Store", "centro_destino": "Final site", "codigo_articulo": "Material",
                   "cantidad": "Qty", "precio": "Net price", "liberacion_comercial": "Approval",
                   "liberacion_logistica": "Logistics", "fecha_xf": "Ready date"},
        "valores": {"moneda": "USD", "incoterm": "FOB"},
        "codigos": {"liberacion_comercial": {"APPROVED": "C"}, "liberacion_logistica": {"GO": "300"}},
        "formato_fecha": "DD/MM/YYYY",
    }).status_code == 200
    contenido = ("Vendor;Order;Item;Legal entity;Site;Store;Final site;Material;Qty;Net price;Approval;Logistics;Ready date\n"
                 f"VANS;4400009871;10;8000;8020;BF20;2220;{base_oc['codigo_articulo']};12;25.5;APPROVED;GO;15/12/2026\n"
                 f"VANS;4400009871;20;8000;8020;BF20;2220;{base_oc['codigo_articulo']};;25.5;APPROVED;GO;15/12/2026\n")
    r = _subir(admin, x["id"], "ordenes_compra", "erp.csv", contenido.encode())
    assert r.status_code == 200, r.text
    previa = r.json()
    assert previa["estado"] == "PREVIA" and previa["resumen"]["leidas"] == 2
    assert previa["resumen"]["rechazadas"] == 1 and "Qty" in previa["errores"][0]["mensajes"][0]
    assert previa["resumen"]["nuevo"] == 1
    ap = admin.post(f"/integraciones/ejecuciones/{previa['id']}/aplicar").json()
    assert ap["estado"] == "CON_ERRORES" and ap["resumen"]["aplicadas"] == 1 and ap["resumen"]["referencias"] == 1
    oc = admin.get("/ordenes", params={"q": "4400009871", "solo_disponible": False}).json()["items"][0]
    det = admin.get(f"/ordenes/{oc['id']}/posiciones").json()
    assert det["oc"]["liberacion_comercial"] == "C" and det["oc"]["liberacion_logistica"] == "300"
    assert str(det["oc"]["fecha_xf"]).startswith("2026-12-15")
    refs = admin.get(f"/integraciones/{x['id']}/referencias", params={"entidad": "ordenes_compra"}).json()
    assert refs == [{**refs[0], "interno_id": oc["id"], "codigo_externo": "VANS/4400009871"}]
    # Aplicar de nuevo no repite; subir el mismo contenido se rechaza con la ejecución anterior
    assert admin.post(f"/integraciones/ejecuciones/{previa['id']}/aplicar").json()["ya_aplicada"] is True
    r = _subir(admin, x["id"], "ordenes_compra", "erp.csv", contenido.encode())
    assert r.status_code == 409 and r.json()["detalle"]["ejecucion_id"] == previa["id"]
    bitacora = admin.get(f"/integraciones/{x['id']}/ejecuciones").json()
    assert bitacora["total"] == 1 and bitacora["items"][0]["archivo"] == "erp.csv"


def test_entrada_en_json(admin, base_oc):
    x = _integracion(admin, "INT-JSON", adaptador="json", raiz="pedidos")
    datos = {"pedidos": [{"proveedor": "VANS", "oc": "4400009872", "posicion": "10", "sociedad": "8000", "centro": "8020",
                          "almacen": "BF20", "centro_destino": "2220", "moneda": "USD", "incoterm": "FOB",
                          "codigo_articulo": base_oc["codigo_articulo"], "cantidad": 3, "precio": 25.5,
                          "liberacion_comercial": "C", "liberacion_logistica": "300"}]}
    # Sin mapeo, los campos se buscan con su nombre interno
    r = _subir(admin, x["id"], "ordenes_compra", "pedidos.json", json.dumps(datos).encode())
    assert r.status_code == 200 and r.json()["resumen"]["nuevo"] == 1, r.text
    assert admin.post(f"/integraciones/ejecuciones/{r.json()['id']}/aplicar").json()["estado"] == "APLICADA"
    assert _subir(admin, x["id"], "ordenes_compra", "malo.json", b"{no es json").status_code == 422


def test_salida_de_facturas_finalizadas(admin):
    x = _integracion(admin, "INT-FAC")
    assert admin.put(f"/integraciones/{x['id']}/mapeos/facturas/salida", {
        "campos": {"factura": "InvoiceNo", "oc": "PurchaseOrder", "codigo_articulo": "Material", "cantidad": "Quantity",
                   "moneda": "Curr"},
        "codigos": {"moneda": {"DOLLAR": "USD"}},
    }).status_code == 200
    r = admin.c.post(f"/api/integraciones/{x['id']}/salida/facturas", headers=admin.h)
    assert r.status_code == 200, r.text
    filas = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert filas and list(filas[0]) == ["InvoiceNo", "Curr", "PurchaseOrder", "Material", "Quantity"]
    assert {f["Curr"] for f in filas} == {"DOLLAR"}  # el código interno sale con el código externo
    enviadas = int(r.headers["X-Registros"])
    assert enviadas >= 1 and len(admin.get(f"/integraciones/{x['id']}/referencias").json()) == enviadas
    # Con «solo nuevas», lo ya enviado no sale otra vez
    r2 = admin.c.post(f"/api/integraciones/{x['id']}/salida/facturas", headers=admin.h)
    assert r2.headers["X-Registros"] == "0"
    r3 = admin.c.post(f"/api/integraciones/{x['id']}/salida/facturas", headers=admin.h, params={"solo_nuevas": "false"})
    assert int(r3.headers["X-Registros"]) == enviadas
    # Una integración inactiva no intercambia
    datos = {k: x[k] for k in ("codigo", "nombre", "sistema", "adaptador", "parametros")}
    assert admin.put(f"/integraciones/{x['id']}", {**datos, "activa": False}).status_code == 200
    assert admin.c.post(f"/api/integraciones/{x['id']}/salida/facturas", headers=admin.h).status_code == 409
