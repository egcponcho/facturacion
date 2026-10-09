"""Búsqueda global: un número encuentra su registro sin saber el módulo, y cada
quien solo ve lo que su rol y su proveedor permiten."""


def _buscar(api, q):
    r = api.get("/buscar", params={"q": q})
    assert r.status_code == 200, r.text
    return {g["tipo"]: g["items"] for g in r.json()["grupos"]}


def test_encuentra_por_tipo(interno):
    oc = interno.get("/ordenes", params={"size": 1}).json()["items"][0]
    g = _buscar(interno, oc["numero"])
    assert any(x["titulo"] == oc["numero"] and x["ruta"].startswith("/ordenes") for x in g["ordenes"])
    # Sin mayúsculas ni acentos, y por partes del nombre
    prov = interno.get("/catalogos/proveedores").json()["items"][0]
    g = _buscar(interno, prov["nombre"].lower()[:5])
    assert any(x["titulo"] == prov["nombre"] for x in g.get("proveedores", []))
    # Un estilo lleva al producto
    p = interno.get("/productos", params={"estado": "", "size": 1}).json()["items"][0]
    g = _buscar(interno, p["estilo"])
    assert any(x["ruta"] == f"/productos/{p['id']}" for x in g["productos"])


def test_vacio_y_corto(interno):
    assert interno.get("/buscar", params={"q": " "}).json()["grupos"] == []
    assert interno.get("/buscar", params={"q": "a"}).json()["grupos"] == []


def test_proveedor_solo_ve_lo_suyo(interno, vans):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.modelos import OrdenCompra, Usuario

    with SessionLocal() as db:
        prov = db.scalar(select(Usuario.proveedor_id).where(Usuario.rol == "proveedor", Usuario.proveedor_id.is_not(None),
                                                            Usuario.email.ilike("%vans%")))
        ajena = db.scalar(select(OrdenCompra.numero).where(OrdenCompra.proveedor_id != prov))
        suyas = {n for (n,) in db.execute(select(OrdenCompra.numero).where(OrdenCompra.proveedor_id == prov))}
    assert prov and ajena
    g = _buscar(vans, ajena)
    assert ajena not in {x["titulo"] for x in g.get("ordenes", [])}
    assert "proveedores" not in g and "embarques" not in g
    g = _buscar(interno, ajena)
    assert ajena in {x["titulo"] for x in g["ordenes"]}
    una = next(iter(suyas))
    assert una in {x["titulo"] for x in _buscar(vans, una)["ordenes"]}


def test_home_necesita_atencion(interno, vans):
    """Cada indicador del Home abre la lista ya filtrada y solo aparece lo que tiene algo pendiente."""
    d = interno.get("/dashboard").json()
    assert d["atencion"] and all(x["valor"] and x["ruta"].startswith("/") for x in d["atencion"])
    tonos = [x["tono"] for x in d["atencion"]]
    assert tonos == sorted(tonos, key=["error", "alerta", "info"].index)  # lo que bloquea, primero
    # El proveedor no ve lo que no puede abrir (embarques)
    assert all(x["ruta"] != "/transporte" for x in vans.get("/dashboard").json()["atencion"])
    # «Productos que bloquean facturas» filtra la lista de productos
    r = interno.get("/productos", params={"estado": "bloquean"}).json()
    assert r["total"] == r["kpis"]["bloquean"]


def test_vistas_guardadas(interno):
    """Una vista guardada conserva sus filtros con nombre y es solo del usuario."""
    r = interno.put("/perfil/vistas/seguimiento", [{"nombre": "Riesgo  VANS", "query": {"riesgo": "ATRASO", "vista": "ordenes", "q": ""}}])
    assert r.status_code == 200, r.text
    assert r.json()["vistas"]["seguimiento"] == [{"nombre": "Riesgo VANS", "query": {"riesgo": "ATRASO", "vista": "ordenes"}}]
    assert interno.get("/auth/me").json()["preferencias"]["vistas"]["seguimiento"][0]["nombre"] == "Riesgo VANS"
    assert interno.put("/perfil/vistas/seguimiento", [{"nombre": "A", "query": {}}, {"nombre": "a", "query": {}}]).status_code == 422
    assert interno.put("/perfil/vistas/otra", []).status_code == 404
    assert interno.put("/perfil/vistas/seguimiento", []).json()["vistas"] == {}
