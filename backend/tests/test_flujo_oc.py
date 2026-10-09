"""Ciclo de vida de la OC (docs/FLUJOS.md §1): borrador del asistente con
validación por paso, envío por la misma validación que una carga del ERP,
aprobación por reglas (monto, moneda) con cuatro ojos, rechazo, cancelación,
cierre, reapertura, historial y avance logístico."""
import pytest
from conftest import Api
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import Articulo, Producto, Proveedor, Rol


def _articulos(codigo_proveedor: str, n: int = 2) -> list[str]:
    with SessionLocal() as db:
        prov = db.scalar(select(Proveedor).where(Proveedor.codigo == codigo_proveedor))
        return [a.sku for a in db.scalars(select(Articulo).where(Articulo.proveedor_id == prov.id, Articulo.activo.is_(True),
                                                                Articulo.tipo != "PREPACK").order_by(Articulo.id).limit(n))]


def _cabecera(numero: str, **extra) -> dict:
    return {"proveedor": "VANS", "oc": numero, "sociedad": "8000", "fecha_oc": "2026-10-01", "moneda": "USD",
            "incoterm": "FOB", "condicion_pago": "NETO30", "centro": "8020", "centro_destino": "2220",
            "fecha_xf": "2026-11-15", "fecha_tienda": "2027-01-10", "pais_origen": "CN", **extra}


def _borrador_completo(api, numero: str, precio: float = 10.0) -> dict:
    oc = api.post("/ordenes/borrador", {"cabecera": _cabecera(numero)})
    assert oc.status_code == 200, oc.text
    oc = oc.json()
    lineas = [{"codigo_sap": sku, "cantidad": 12, "precio": precio} for sku in _articulos("VANS")]
    r = api.patch(f"/ordenes/{oc['oc']['id']}", {"version": oc["oc"]["version"], "lineas": lineas})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def reglas_aprobacion(admin):
    """Una regla: desde 100 USD aprueba el rol del equipo interno."""
    rol = next(r for r in admin.get("/roles").json()["roles"] if r["nombre"] == "Internal team")
    assert admin.put("/organizacion", {"aprobaciones_oc": [
        {"nombre": "Purchases over 100", "monto_minimo": 100, "moneda": "USD", "rol_id": rol["id"]}]}).status_code == 200
    yield rol
    admin.put("/organizacion", {"aprobaciones_oc": []})


def test_asistente_valida_por_paso_y_guarda_borrador(interno):
    # Validación en el acto, sin guardar
    r = interno.post("/ordenes/validar", {"paso": "general", "cabecera": {"proveedor": "NOEXISTE"}}).json()
    campos = {e["campo"] for e in r["errores"]}
    assert {"proveedor", "sociedad"} <= campos
    r = interno.post("/ordenes/validar", {"paso": "articulos", "cabecera": {"proveedor": "VANS"},
                                          "lineas": [{"codigo_sap": "NOEXISTE", "cantidad": 0}]}).json()
    assert {"lineas.0.codigo_sap", "lineas.0.cantidad"} <= {e["campo"] for e in r["errores"]}
    r = interno.post("/ordenes/validar", {"paso": "logistica", "cabecera": {"fecha_xf": "2026-12-01", "fecha_tienda": "2026-11-01"}}).json()
    assert any(e["campo"] == "fecha_tienda" for e in r["errores"])
    # El borrador se guarda aunque falten datos; cada paso dice qué le falta
    oc = interno.post("/ordenes/borrador", {"cabecera": {"proveedor": "VANS", "oc": "BOR-0001", "sociedad": "8000"}}).json()
    assert oc["oc"]["estado"] == "BORRADOR" and oc["puede"]["enviar"] and oc["oc"]["origen"] == "PLATAFORMA"
    pasos = {p["clave"]: p for p in oc["pasos"]}
    assert pasos["general"]["completo"] and not pasos["articulos"]["completo"] and not pasos["condiciones"]["completo"]
    # Un borrador no se puede facturar ni aparece entre las disponibles
    disponibles = interno.get("/ordenes", params={"q": "BOR-0001"}).json()["items"]
    assert disponibles == []
    todas = interno.get("/ordenes", params={"q": "BOR-0001", "solo_disponible": False}).json()["items"]
    assert todas[0]["estado"] == "BORRADOR"
    # Enviar incompleto dice qué falta, paso por paso
    r = interno.post(f"/ordenes/{oc['oc']['id']}/enviar", {"version": oc["oc"]["version"]})
    assert r.status_code == 422 and {e["paso"] for e in r.json()["detalle"]} >= {"articulos", "condiciones", "logistica"}
    # Un borrador nunca enviado se puede borrar
    assert interno.delete_(f"/ordenes/{oc['oc']['id']}").status_code == 200
    assert interno.get(f"/ordenes/{oc['oc']['id']}").status_code == 404


def test_sin_reglas_se_aprueba_al_enviar(interno):
    oc = _borrador_completo(interno, "ASIS-0001")
    assert all(p["completo"] for p in oc["pasos"])
    r = interno.post(f"/ordenes/{oc['oc']['id']}/enviar", {"version": oc["oc"]["version"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["oc"]["estado"] == "APROBADA" and d["oc"]["liberada"] and d["oc"]["condicion_pago"] == "NETO30"
    assert len(d["posiciones"]) == 2 and all(p["estado"] == "DISPONIBLE" for p in d["posiciones"])
    assert d["avance"]["codigo"] == "SIN_FACTURAR" and d["borrador"] is None
    acciones = [h["accion"] for h in interno.get(f"/ordenes/{d['oc']['id']}/historial").json()]
    assert acciones[0] == "enviada" and "borrador_creado" in acciones
    # Ya enviada no se borra (se cancela)
    assert interno.delete_(f"/ordenes/{d['oc']['id']}").status_code == 409


def test_aprobacion_por_reglas_con_cuatro_ojos(client, admin, interno, reglas_aprobacion):
    oc = _borrador_completo(interno, "ASIS-0002", precio=50)  # 2 líneas × 12 × 50 = 1 200 USD
    d = interno.post(f"/ordenes/{oc['oc']['id']}/enviar", {"version": oc["oc"]["version"]}).json()
    assert d["oc"]["estado"] == "EN_APROBACION" and not d["oc"]["liberada"]
    assert [a["regla"] for a in d["aprobaciones"]] == ["Purchases over 100"] and d["aprobaciones"][0]["actual"]
    # Mientras espera aprobación no se factura
    pos = d["posiciones"][0]
    r = interno.post("/facturas", {"lineas": [{"posicion_id": pos["id"], "cantidad": 1}]})
    assert r.status_code == 422 and "pending approval" in r.text
    # Quien la envió no la aprueba: ni se le ofrece ni está en su bandeja
    assert not d["puede"]["aprobar"] and not d["puede"]["rechazar"]
    assert all(x["id"] != d["oc"]["id"] for x in interno.get("/ordenes/pendientes-aprobacion").json())
    r = interno.post(f"/ordenes/{d['oc']['id']}/aprobar", {})
    assert r.status_code == 403 and r.json()["codigo"] == "cuatro_ojos"
    # Otra persona del rol aprobador sí; queda en su bandeja
    u = admin.post("/usuarios", {"email": "aprobador@demo.com", "nombre": "Approver", "rol_id": reglas_aprobacion["id"],
                                 "telefono": "+50370000130", "dos_pasos": True}).json()
    aprobador = Api(client, "aprobador@demo.com", u["password_temporal"])
    aprobador.post("/auth/password", {"actual": u["password_temporal"], "nueva": "Aprueba#Clave2026"})
    assert any(x["id"] == d["oc"]["id"] for x in aprobador.get("/ordenes/pendientes-aprobacion").json())
    assert aprobador.get(f"/ordenes/{d['oc']['id']}").json()["puede"]["aprobar"]
    r = aprobador.post(f"/ordenes/{d['oc']['id']}/aprobar", {"comentario": "Budget ok"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["oc"]["estado"] == "APROBADA" and d["oc"]["liberada"]
    assert d["aprobaciones"][0]["estado"] == "APROBADA" and d["aprobaciones"][0]["usuario"] == "Approver"
    assert d["aprobaciones"][0]["comentario"] == "Budget ok"


def test_rechazo_y_reenvio(admin, interno, reglas_aprobacion):
    oc = _borrador_completo(interno, "ASIS-0003", precio=50)
    d = interno.post(f"/ordenes/{oc['oc']['id']}/enviar", {"version": oc["oc"]["version"]}).json()
    assert admin.post(f"/ordenes/{d['oc']['id']}/rechazar", {}).status_code == 422  # pide motivo
    d = admin.post(f"/ordenes/{d['oc']['id']}/rechazar", {"motivo": "Price too high"}).json()
    assert d["oc"]["estado"] == "RECHAZADA" and d["oc"]["motivo_estado"] == "Price too high" and d["puede"]["editar"]
    # Al editarla vuelve a borrador con sus datos y se puede reenviar
    lineas = [{**x, "precio": 4} for x in d["borrador"]["lineas"]]
    d = interno.patch(f"/ordenes/{d['oc']['id']}", {"version": d["oc"]["version"], "lineas": lineas}).json()
    assert d["oc"]["estado"] == "BORRADOR"
    d = interno.post(f"/ordenes/{d['oc']['id']}/enviar", {"version": d["oc"]["version"]}).json()
    assert d["oc"]["estado"] == "APROBADA"  # 96 USD: ya no aplica la regla


def test_cancelar_cerrar_y_reabrir(admin, interno):
    oc = _borrador_completo(interno, "ASIS-0004")
    d = interno.post(f"/ordenes/{oc['oc']['id']}/enviar", {"version": oc["oc"]["version"]}).json()
    pos = d["posiciones"][0]
    f = interno.post("/facturas", {"lineas": [{"posicion_id": pos["id"], "cantidad": 6}]})
    assert f.status_code == 200, f.text
    # Con una factura activa no se cancela; se cierra lo pendiente
    r = interno.post(f"/ordenes/{d['oc']['id']}/cancelar", {"motivo": "No longer needed"})
    assert r.status_code == 409 and r.json()["codigo"] == "facturada"
    d = interno.post(f"/ordenes/{d['oc']['id']}/cerrar", {"motivo": "Short shipment accepted"}).json()
    assert d["oc"]["estado"] == "CERRADA" and all(p["estado"] == "NO_DISPONIBLE" for p in d["posiciones"][1:])
    assert d["avance"]["codigo"] == "FACTURADA_PARCIAL"
    d = admin.post(f"/ordenes/{d['oc']['id']}/reabrir", {"motivo": "Supplier will ship the rest"}).json()
    assert d["oc"]["estado"] == "APROBADA"
    # Transición no permitida: aprobar algo que no espera aprobación
    r = admin.post(f"/ordenes/{d['oc']['id']}/aprobar", {})
    assert r.status_code == 409 and r.json()["codigo"] == "transicion_invalida"
    interno.post(f"/facturas/{f.json()['id']}/cancelar", {"motivo": "prueba"})
    d = interno.post(f"/ordenes/{d['oc']['id']}/cancelar", {"motivo": "No longer needed"}).json()
    assert d["oc"]["estado"] == "CANCELADA" and not d["oc"]["liberada"]


def test_una_carga_no_cambia_una_oc_en_flujo(interno):
    oc = interno.post("/ordenes/borrador", {"cabecera": {"proveedor": "VANS", "oc": "BOR-0002", "sociedad": "8000"}}).json()
    sku = _articulos("VANS", 1)[0]
    csv = ("supplier,po_number,line,company,plant,currency,incoterm,item_code,quantity,unit_price\n"
           f"VANS,BOR-0002,10,8000,8020,USD,FOB,{sku},5,9\n")
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h, files={"archivo": ("o.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["resumen"]["conflicto"] == 1
    assert "draft" in str(r.json()["filas"])
    interno.delete_(f"/ordenes/{oc['oc']['id']}")


def test_obligatorios_y_reglas_configurables(admin, interno):
    try:
        assert admin.put("/organizacion", {"obligatorios": {"orden": ["incoterm", "no_existe"]}}).status_code == 422
        assert admin.put("/organizacion", {"obligatorios": {"orden": ["incoterm", "puerto_despacho"]}}).status_code == 200
        r = interno.post("/ordenes/validar", {"paso": "condiciones", "cabecera": {"moneda": "USD"}, "lineas": []}).json()
        assert any(e["campo"] == "incoterm" for e in r["errores"])
        r = interno.post("/ordenes/validar", {"paso": "logistica", "cabecera": {"fecha_xf": "2026-12-01"}}).json()
        assert any(e["campo"] == "puerto_despacho" for e in r["errores"])
        assert "incoterm" in interno.get("/ordenes/formulario").json()["obligatorios"]
    finally:
        admin.put("/organizacion", {"obligatorios": {"orden": []}})
    # Reglas de aprobación inválidas
    assert admin.put("/organizacion", {"aprobaciones_oc": [{"nombre": "X", "monto_minimo": -1, "moneda": "USD", "rol_id": 1}]}).status_code == 422
    assert admin.put("/organizacion", {"aprobaciones_oc": [{"nombre": "X", "monto_minimo": 5, "moneda": "ZZZ", "rol_id": 1}]}).status_code == 422
    # Los permisos nuevos existen y el proveedor no los tiene
    with SessionLocal() as db:
        interno_rol = db.scalar(select(Rol).where(Rol.nombre == "Internal team"))
        assert {"oc.editar", "oc.aprobar", "oc.cancelar"} <= set(interno_rol.permisos)


def test_avance_en_la_lista(interno):
    items = interno.get("/ordenes", params={"solo_disponible": False, "size": 50}).json()["items"]
    assert items and all(i["estado"] for i in items)
    oc = items[0]
    d = interno.get(f"/ordenes/{oc['id']}").json()
    assert d["avance"]["codigo"] in ("SIN_FACTURAR", "FACTURADA_PARCIAL", "FACTURADA", "EMBARCADA_PARCIAL", "EN_TRANSITO",
                                     "RECIBIDA_PARCIAL", "RECIBIDA")
    assert 0 <= d["avance"]["facturado"] <= 100


def test_articulos_del_asistente_y_datos_de_aduana(interno):
    """La lista de artículos del asistente (con búsqueda en el servidor) y los
    datos de aduana, que se piden en el paso de logística y no antes."""
    r = interno.get("/ordenes/formulario/articulos", params={"proveedor": "VANS"})
    assert r.status_code == 200, r.text
    arts = r.json()
    assert arts and all({"valor", "texto", "unidad", "tipo", "pais_origen"} <= set(a) for a in arts)
    buscado = interno.get("/ordenes/formulario/articulos", params={"proveedor": "VANS", "q": arts[0]["valor"]}).json()
    assert arts[0]["valor"] in [a["valor"] for a in buscado]
    # Con el país de origen en la ficha del producto no hace falta en la OC
    with SessionLocal() as db:
        prov = db.scalar(select(Proveedor).where(Proveedor.codigo == "VANS"))
        art = next(a for a in db.scalars(select(Articulo).where(Articulo.proveedor_id == prov.id, Articulo.activo.is_(True))
                                         .order_by(Articulo.id)) if a.producto and a.producto.pais_origen)
        sku, producto_id, origen = art.sku, art.producto_id, art.producto.pais_origen
    lineas = [{"codigo_sap": sku, "cantidad": 1}]
    cab = {k: v for k, v in _cabecera("ADU-1").items() if k != "pais_origen"}

    def errores_origen(paso: str, cabecera: dict) -> list:
        r = interno.post("/ordenes/validar", {"paso": paso, "cabecera": cabecera, "lineas": lineas}).json()["errores"]
        return [e for e in r if e["campo"] == "pais_origen"]

    assert not errores_origen("logistica", cab)
    # Sin él en la ficha, la OC tiene que traerlo (en logística, no en los pasos anteriores)
    with SessionLocal() as db:
        db.get(Producto, producto_id).pais_origen = None
        db.commit()
    try:
        assert errores_origen("logistica", cab)
        assert not errores_origen("logistica", {**cab, "pais_origen": "CN"})
        for paso in ("general", "articulos", "condiciones"):
            assert not errores_origen(paso, cab)
    finally:
        with SessionLocal() as db:
            db.get(Producto, producto_id).pais_origen = origen
            db.commit()
