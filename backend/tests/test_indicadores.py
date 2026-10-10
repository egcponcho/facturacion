"""Tableros por módulo: cada indicador dice su fórmula, período y fuente, se
calcula con el alcance de datos del usuario y cada persona (o su rol) elige
cuáles ve y en qué orden."""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.modelos import Articulo, Factura, OrdenCompra, Proveedor


def _indicador(tablero: dict, clave: str):
    return next(i for i in tablero["indicadores"] if i["clave"] == clave)


def _aprobar_oc(api, numero: str) -> dict:
    """Una OC enviada sin reglas de aprobación queda aprobada en el acto."""
    with SessionLocal() as db:
        prov = db.scalar(select(Proveedor).where(Proveedor.codigo == "VANS"))
        sku = db.scalar(select(Articulo.sku).where(Articulo.proveedor_id == prov.id, Articulo.activo.is_(True),
                                                    Articulo.tipo != "PREPACK").order_by(Articulo.id))
    cab = {"proveedor": "VANS", "oc": numero, "sociedad": "8000", "fecha_oc": "2026-10-01", "moneda": "USD", "incoterm": "FOB",
           "condicion_pago": "NETO30", "centro": "8020", "centro_destino": "2220", "fecha_xf": "2026-11-15",
           "fecha_tienda": "2027-01-10", "pais_origen": "CN"}
    oc = api.post("/ordenes/borrador", {"cabecera": cab}).json()
    oc = api.patch(f"/ordenes/{oc['oc']['id']}", {"version": oc["oc"]["version"],
                                                  "lineas": [{"codigo_sap": sku, "cantidad": 10, "precio": 5}]}).json()
    r = api.post(f"/ordenes/{oc['oc']['id']}/enviar", {"version": oc["oc"]["version"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_cada_indicador_explica_su_formula_periodo_y_fuente(interno):
    modulos = {m["clave"] for m in interno.get("/tableros").json()}
    assert {"compras", "facturacion", "logistica", "productos"} <= modulos
    for modulo in modulos:
        t = interno.get(f"/tableros/{modulo}", params={"dias": 90}).json()
        assert t["periodo"]["dias"] == 90 and t["periodo"]["desde"] and t["periodo"]["hasta"]
        assert t["catalogo"] and all(i["formula"] and i["fuente"] and i["momento"] in ("hoy", "periodo") for i in t["catalogo"])
        for i in t["indicadores"]:
            assert i["valor"] is None or isinstance(i["valor"], (int, float))
    # Un período que no existe vuelve a 30 días
    assert interno.get("/tableros/compras", params={"dias": 3}).json()["periodo"]["dias"] == 30
    assert interno.get("/tableros/otro").status_code == 404


def test_los_valores_salen_de_los_datos(interno):
    antes = _indicador(interno.get("/tableros/compras", params={"dias": 7}).json(), "oc_aprobadas")["valor"]
    _aprobar_oc(interno, "KPI-0001")
    despues = _indicador(interno.get("/tableros/compras", params={"dias": 7}).json(), "oc_aprobadas")["valor"]
    assert despues == antes + 1
    # Facturas finalizadas en los últimos 365 días: lo que dice la base de datos
    t = interno.get("/tableros/facturacion", params={"dias": 365}).json()
    desde = datetime.combine(date.today() - timedelta(days=364), datetime.min.time())
    with SessionLocal() as db:
        esperado = db.scalar(select(func.count()).select_from(Factura).where(
            Factura.finalizado_en >= desde, Factura.estado != "CANCELADA"))
    assert _indicador(t, "facturas_finalizadas")["valor"] == esperado
    # Los indicadores del período traen el período anterior para comparar
    assert "anterior" in _indicador(t, "facturas_finalizadas")


def test_un_proveedor_ve_solo_sus_numeros(tnf, interno):
    tnf_t = tnf.get("/tableros/facturacion", params={"dias": 365}).json()
    desde = datetime.combine(date.today() - timedelta(days=364), datetime.min.time())
    with SessionLocal() as db:
        prov = db.scalar(select(Proveedor.id).where(Proveedor.codigo == "TNF"))
        propias = db.scalar(select(func.count()).select_from(Factura).where(
            Factura.finalizado_en >= desde, Factura.estado != "CANCELADA", Factura.proveedor_id == prov))
        en_aprobacion = db.scalar(select(func.count()).select_from(OrdenCompra).where(
            OrdenCompra.estado == "EN_APROBACION", OrdenCompra.proveedor_id == prov))
    assert _indicador(tnf_t, "facturas_finalizadas")["valor"] == propias
    assert _indicador(tnf.get("/tableros/compras").json(), "oc_en_aprobacion")["valor"] == en_aprobacion
    # Logística es del equipo interno: el proveedor no la ve
    assert "logistica" not in {m["clave"] for m in tnf.get("/tableros").json()}
    assert tnf.get("/tableros/logistica").status_code == 403


def test_cada_persona_y_cada_rol_eligen_sus_indicadores(admin, interno):
    t = interno.get("/tableros/compras").json()
    assert t["origen"] in ("sistema", "rol")
    # La persona elige y ordena
    r = interno.put("/tableros/compras/propios", {"claves": ["oc_atrasadas", "oc_en_aprobacion"]})
    assert r.status_code == 200, r.text
    t = interno.get("/tableros/compras").json()
    assert t["elegidos"] == ["oc_atrasadas", "oc_en_aprobacion"] and t["origen"] == "usuario"
    assert [i["clave"] for i in t["indicadores"]] == ["oc_atrasadas", "oc_en_aprobacion"]
    assert interno.put("/tableros/compras/propios", {"claves": ["no_existe"]}).status_code == 422
    # La administración deja los del rol: los ve quien no eligió los suyos
    rol = next(r["id"] for r in admin.get("/roles").json()["roles"] if r["nombre"] == interno.yo["rol_nombre"])
    assert interno.put(f"/tableros/compras/rol/{rol}", {"claves": ["oc_aprobadas"]}).status_code == 403
    assert admin.put(f"/tableros/compras/rol/{rol}", {"claves": ["oc_aprobadas", "saldo_por_facturar"]}).status_code == 200
    assert interno.get("/tableros/compras").json()["origen"] == "usuario"
    interno.put("/tableros/compras/propios", {"claves": None})
    t = interno.get("/tableros/compras").json()
    assert t["origen"] == "rol" and t["elegidos"] == ["oc_aprobadas", "saldo_por_facturar"]
    admin.put(f"/tableros/compras/rol/{rol}", {"claves": None})
    assert interno.get("/tableros/compras").json()["origen"] == "sistema"


def test_un_rol_sin_precios_no_ve_los_montos(client, admin):
    rol = admin.post("/roles", {"nombre": "KPI reader", "permisos": ["oc.ver", "factura.ver"], "datos_ocultos": ["precios"]}).json()
    u = admin.post("/usuarios", {"email": "kpi@demo.com", "nombre": "KPI reader", "rol_id": rol["id"],
                                 "telefono": "+50370000152", "dos_pasos": True}).json()
    from conftest import Api

    api = Api(client, "kpi@demo.com", u["password_temporal"])
    api.post("/auth/password", {"actual": u["password_temporal"], "nueva": "Ver#Indicadores2026"})
    claves = {c["clave"] for c in api.get("/tableros/compras").json()["catalogo"]}
    assert "saldo_por_facturar" not in claves and "oc_aprobadas" in claves
    assert "importe_facturado" not in {c["clave"] for c in api.get("/tableros/facturacion").json()["catalogo"]}
