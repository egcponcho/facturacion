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


# ---- Referencias externas: nunca se reasignan en silencio ------------------------------------
def _con_integracion(fn):
    """Corre fn(db, integración) dentro de una transacción que se deshace al final."""
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import Integracion

    with SessionLocal() as db, en_organizacion(1):
        x = Integracion(codigo="REF-UNIT", nombre="Refs", adaptador="json", parametros={}, activa=True)
        db.add(x)
        db.flush()
        try:
            return fn(db, x)
        finally:
            db.rollback()


def test_una_referencia_externa_no_se_reasigna_en_silencio():
    from app.modelos import ReferenciaExterna
    from app.modulos.integraciones import servicio

    def prueba(db, x):
        assert servicio._referenciar(db, x, "ordenes_compra", [(1, "A"), (3, "C")], None) == (2, [])
        # El mismo vínculo otra vez: sin conflicto
        assert servicio._referenciar(db, x, "ordenes_compra", [(1, "A")], None) == (1, [])
        # El código A ya es del registro 1: no pasa al 2
        hechas, conflictos = servicio._referenciar(db, x, "ordenes_compra", [(2, "A")], None)
        assert hechas == 0 and [(c["motivo"], c["vinculado_a"]) for c in conflictos] == [("codigo_ocupado", 1)]
        # El registro 1 ya tiene el código A: B no lo reemplaza
        hechas, conflictos = servicio._referenciar(db, x, "ordenes_compra", [(1, "B")], None)
        assert hechas == 0 and [(c["motivo"], c["codigo_actual"]) for c in conflictos] == [("otro_codigo", "A")]
        refs = {(r.interno_id, r.codigo_externo) for r in db.query(ReferenciaExterna).filter_by(integracion_id=x.id)}
        assert refs == {(1, "A"), (3, "C")}
        # Cada conflicto se explica como error de la ejecución, con qué hacer
        (err,) = servicio._errores_de_conflictos(conflictos)
        assert err["fila"] is None and "unlink" in err["mensajes"][0]

    _con_integracion(prueba)


def test_la_unicidad_la_garantiza_la_base(monkeypatch):
    """Si dos ejecuciones vinculan lo mismo a la vez (la consulta previa no ve la otra), la llave
    única de la base lo impide y queda como conflicto, no como error del servidor."""
    from app.modulos.integraciones import servicio

    def prueba(db, x):
        servicio._referenciar(db, x, "facturas", [(10, "F-1")], None)
        monkeypatch.setattr(servicio, "_referencia", lambda *a, **k: None)
        hechas, conflictos = servicio._referenciar(db, x, "facturas", [(11, "F-1")], None)
        assert hechas == 0 and [c["motivo"] for c in conflictos] == ["simultaneo"]

    _con_integracion(prueba)


def test_desvincular_pide_permiso_y_motivo(admin, interno):
    x = _integracion(admin, "INT-DESV")
    r = admin.c.post(f"/api/integraciones/{x['id']}/salida/facturas", headers=admin.h)
    assert r.status_code == 200, r.text
    ref = admin.get(f"/integraciones/{x['id']}/referencias").json()[0]
    ruta = f"/integraciones/{x['id']}/referencias/{ref['id']}/desvincular"
    assert interno.post(ruta, {"motivo": "Wrong link"}).status_code == 403
    assert admin.post(ruta, {"motivo": " "}).status_code == 422
    d = admin.post(ruta, {"motivo": "Linked to the wrong invoice"})
    assert d.status_code == 200, d.text
    assert all(x_["id"] != ref["id"] for x_ in admin.get(f"/integraciones/{x['id']}/referencias").json())
    assert admin.post(ruta, {"motivo": "Again"}).status_code == 404
    # La siguiente salida vuelve a vincular lo que quedó libre
    r = admin.c.post(f"/api/integraciones/{x['id']}/salida/facturas", headers=admin.h)
    assert r.headers["X-Registros"] == "1"


# ---- Importación: estructura detectada y filas rechazadas descargables ------------------------
def test_estructura_y_filas_rechazadas(admin, base_oc):
    x = _integracion(admin, "INT-REJ")
    contenido = ("proveedor,oc,posicion,sociedad,centro,almacen,centro_destino,moneda,incoterm,codigo_articulo,Quantity,precio\n"
                 f"VANS,4400009881,10,8000,8020,BF20,2220,USD,FOB,{base_oc['codigo_articulo']},,25.5\n")
    r = _subir(admin, x["id"], "ordenes_compra", "mal.csv", contenido.encode())
    assert r.status_code == 200, r.text
    previa = r.json()
    # Falta la columna de la cantidad: se ve en la estructura antes de aplicar
    est = previa["estructura"]
    assert "cantidad" in est["faltan"] and "Quantity" in est["sin_usar"]
    assert next(c for c in est["campos"] if c["campo"] == "oc")["encontrada"]
    # Las filas rechazadas se descargan con sus columnas originales y el motivo
    d = admin.c.get(f"/api/integraciones/ejecuciones/{previa['id']}/rechazadas", headers=admin.h, params={"idioma": "en"})
    assert d.status_code == 200, d.text
    filas = list(csv.DictReader(io.StringIO(d.content.decode("utf-8-sig"))))
    assert len(filas) == 1 and filas[0]["oc"] == "4400009881" and "cantidad" in filas[0]["Reason"]
    assert list(filas[0])[0] == "Row" and list(filas[0])[-1] == "Reason"
    # En español: cabeceras y motivo traducidos; las columnas del archivo, tal cual
    d = admin.c.get(f"/api/integraciones/ejecuciones/{previa['id']}/rechazadas", headers=admin.h, params={"idioma": "es"})
    filas = list(csv.DictReader(io.StringIO(d.content.decode("utf-8-sig"))))
    assert list(filas[0])[0] == "Fila" and filas[0]["Motivo"].startswith("Faltan valores obligatorios") and "oc" in filas[0]
    # Sin filas aplicables no se aplica nada (ni queda el contenido como «ya aplicado»)
    assert previa["resumen"]["aplicables"] == 0
    r = admin.post(f"/integraciones/ejecuciones/{previa['id']}/aplicar")
    assert r.status_code == 422 and r.json()["codigo"] == "sin_filas_validas"
    # Corregido el mapeo, el mismo archivo se vuelve a cargar y se aplica
    assert admin.put(f"/integraciones/{x['id']}/mapeos/ordenes_compra/entrada", {"campos": {"cantidad": "Quantity"}}).status_code == 200
    contenido = contenido.replace(",,25.5", ",4,25.5")
    r = _subir(admin, x["id"], "ordenes_compra", "bien.csv", contenido.encode())
    assert r.status_code == 200 and r.json()["resumen"]["aplicables"] == 1 and not r.json()["estructura"]["faltan"], r.text
    assert admin.post(f"/integraciones/ejecuciones/{r.json()['id']}/aplicar").json()["estado"] == "APLICADA"
    # El mismo contenido con el mismo mapeo ya no se aplica otra vez
    assert _subir(admin, x["id"], "ordenes_compra", "bien.csv", contenido.encode()).status_code == 409
    # Con otra versión del mapeo el mismo contenido se puede volver a leer (el núcleo no repite lo que ya está)
    assert admin.put(f"/integraciones/{x['id']}/mapeos/ordenes_compra/entrada",
                     {"campos": {"cantidad": "Quantity"}, "valores": {"unidad": "PR"}}).json()["version"] == 2
    r = _subir(admin, x["id"], "ordenes_compra", "bien.csv", contenido.encode())
    assert r.status_code == 200 and r.json()["resumen"].get("nuevo", 0) == 0, r.text


def test_otra_empresa_no_ve_las_integraciones(admin, client):
    from conftest import Api

    x = _integracion(admin, "INT-AISL")
    admin.c.post(f"/api/integraciones/{x['id']}/salida/facturas", headers=admin.h)
    ejec = admin.get(f"/integraciones/{x['id']}/ejecuciones").json()["items"][0]
    r = admin.post("/plataforma/organizaciones", {"codigo": "INTAIS", "nombre": "Second integrations company", "pais": "gt",
                                                  "admin_email": "intais@demo.com", "admin_nombre": "Integrations admin 2",
                                                  "admin_telefono": "+50200000019"})
    assert r.status_code == 200, r.text
    org = r.json()
    otra = Api(client, "intais@demo.com", org["password_temporal"])
    assert otra.post("/auth/password", {"actual": org["password_temporal"], "nueva": "Integraciones#2026x"}).status_code == 200
    try:
        assert all(i["id"] != x["id"] for i in otra.get("/integraciones").json()["integraciones"])
        assert otra.get(f"/integraciones/{x['id']}/ejecuciones").status_code == 404
        assert otra.get(f"/integraciones/ejecuciones/{ejec['id']}").status_code == 404
        assert otra.c.get(f"/api/integraciones/ejecuciones/{ejec['id']}/rechazadas", headers=otra.h).status_code == 404
        assert otra.get(f"/integraciones/{x['id']}/referencias").json() == []
        assert otra.put(f"/integraciones/{x['id']}/mapeos/facturas/salida", {"campos": {}}).status_code == 404
        assert otra.c.post(f"/api/integraciones/{x['id']}/salida/facturas", headers=otra.h).status_code == 404
    finally:
        admin.patch(f"/plataforma/organizaciones/{org['id']}", {"activa": False})


def test_tope_de_filas_por_archivo(admin, base_oc, monkeypatch):
    """Un archivo con más filas de las permitidas no se procesa (ni por integración ni a mano)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "IMPORTACION_MAX_FILAS", 1)
    x = _integracion(admin, "INT-TOPE", adaptador="json")
    fila = {"proveedor": "VANS", "oc": "4400009891", "posicion": "10", "codigo_articulo": base_oc["codigo_articulo"], "cantidad": 1}
    r = _subir(admin, x["id"], "ordenes_compra", "dos.json", json.dumps([fila, {**fila, "posicion": "20"}]).encode())
    assert r.status_code == 413 and r.json()["codigo"] == "demasiadas_filas"
    cabecera = "proveedor,oc,posicion,sociedad,centro,almacen,centro_destino,moneda,incoterm,sku,cantidad,precio\n"
    lineas = "".join(f"VANS,4400009891,{p},8000,8020,BF20,2220,USD,FOB,{base_oc['codigo_articulo']},1,2\n" for p in (10, 20))
    m = admin.c.post("/api/ordenes/importar/previa", headers=admin.h,
                     files={"archivo": ("dos.csv", (cabecera + lineas).encode(), "text/csv")})
    assert m.status_code == 413, m.text
