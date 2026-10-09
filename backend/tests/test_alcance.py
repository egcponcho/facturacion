"""Alcance de los datos de cada usuario (Usuarios y accesos → Usuario):
proveedores que representa o que atiende y sociedades. Vacío = sin límite."""
import pytest


def _usuario(admin, email):
    return next(u for u in admin.get("/usuarios").json() if u["email"] == email)


def _proveedores(admin):
    return {p["codigo"]: p["id"] for p in admin.get("/catalogos/proveedores").json()["items"]}


@pytest.fixture
def con_alcance(admin):
    """Asigna un alcance y lo deja como estaba al terminar."""
    cambiados = []

    def poner(email, alcance):
        u = _usuario(admin, email)
        cambiados.append((u["id"], u["alcance"]))
        r = admin.patch(f"/usuarios/{u['id']}", {"alcance": alcance})
        assert r.status_code == 200, r.text

    yield poner
    for uid, antes in reversed(cambiados):
        admin.patch(f"/usuarios/{uid}", {"alcance": antes})


def test_validaciones(admin):
    u = _usuario(admin, "interno@demo.com")
    assert admin.patch(f"/usuarios/{u['id']}", {"alcance": {"marcas": [1]}}).status_code == 422
    assert admin.patch(f"/usuarios/{u['id']}", {"alcance": {"proveedores": [999999]}}).status_code == 422
    assert admin.patch(f"/usuarios/{u['id']}", {"alcance": {"sociedades": ["NOEXISTE"]}}).status_code == 422


def test_proveedor_que_representa_a_otro(admin, vans, con_alcance):
    prov = _proveedores(admin)
    oc_tnf = admin.get("/ordenes", params={"proveedor_id": prov["TNF"], "solo_disponible": False}).json()["items"][0]
    assert all(o["proveedor"] != oc_tnf["proveedor"] for o in vans.get("/ordenes", params={"solo_disponible": False}).json()["items"])
    assert vans.get(f"/ordenes/{oc_tnf['id']}/posiciones").status_code == 404
    con_alcance("vans@demo.com", {"proveedores": [prov["TNF"]]})
    nombres = {o["proveedor"] for o in vans.get("/ordenes", params={"solo_disponible": False, "size": 200}).json()["items"]}
    assert oc_tnf["proveedor"] in nombres and len(nombres) == 2
    assert vans.get(f"/ordenes/{oc_tnf['id']}/posiciones").status_code == 200
    assert {p["id"] for p in vans.get("/proveedores").json()} == {prov["VANS"], prov["TNF"]}
    # Puede elegir uno de los suyos
    solo_tnf = vans.get("/ordenes", params={"proveedor_id": prov["TNF"], "solo_disponible": False, "size": 200}).json()["items"]
    assert solo_tnf and {o["proveedor"] for o in solo_tnf} == {oc_tnf["proveedor"]}


def test_interno_limitado_a_un_proveedor(admin, interno, con_alcance):
    prov = _proveedores(admin)
    con_alcance("interno@demo.com", {"proveedores": [prov["VANS"]]})
    ocs = interno.get("/ordenes", params={"solo_disponible": False, "size": 200}).json()["items"]
    assert ocs and len({o["proveedor"] for o in ocs}) == 1
    # Pedir otro proveedor no amplía su alcance
    otros = interno.get("/ordenes", params={"proveedor_id": prov["TNF"], "solo_disponible": False, "size": 200}).json()["items"]
    assert {o["proveedor"] for o in otros} == {o["proveedor"] for o in ocs}
    assert {p["id"] for p in interno.get("/proveedores").json()} == {prov["VANS"]}


def test_interno_limitado_a_sociedades(admin, interno, con_alcance):
    socs = [s["codigo"] for s in admin.get("/catalogos/sociedades").json()["items"]]
    oc = interno.get("/ordenes", params={"solo_disponible": False}).json()["items"][0]
    factura = interno.get("/facturas").json()["items"][0]
    embarques = interno.get("/embarques").json()
    otra = next(s for s in socs if s != oc["sociedad"])
    con_alcance("interno@demo.com", {"sociedades": [otra]})
    assert all(o["sociedad"] == otra for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 200}).json()["items"])
    assert interno.get(f"/ordenes/{oc['id']}/posiciones").status_code == 404
    if factura["sociedad"] != otra:
        assert interno.get(f"/facturas/{factura['id']}").status_code == 404
    assert all(f["sociedad"] == otra for f in interno.get("/facturas").json()["items"])
    assert len(interno.get("/embarques").json()) <= len(embarques)
    # Sin alcance vuelve a verlo todo
    con_alcance("interno@demo.com", {})
    assert interno.get(f"/ordenes/{oc['id']}/posiciones").status_code == 200


def test_agente_de_carga_ve_solo_sus_embarques(admin, interno, con_alcance):
    embarques = interno.get("/embarques").json()
    con_transportista = [e for e in embarques if e.get("transportista_id")]
    if not con_transportista:
        pytest.skip("La demostración no tiene embarques con transportista")
    t = con_transportista[0]["transportista_id"]
    con_alcance("interno@demo.com", {"transportistas": [t]})
    visibles = interno.get("/embarques").json()
    assert visibles and all(e["transportista_id"] == t for e in visibles)
    otro = next((e for e in embarques if e.get("transportista_id") != t), None)
    if otro:
        assert interno.get(f"/embarques/{otro['id']}").status_code == 404
