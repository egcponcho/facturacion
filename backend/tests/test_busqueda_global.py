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

    from app.db import SessionLocal
    from app.models import OrdenCompra, Usuario

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
