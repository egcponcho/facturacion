"""Varias empresas en una instalación: cada una ve solo lo suyo, sus códigos
son únicos dentro de ella y tiene su propia configuración."""
import pytest

from tests.conftest import Api


@pytest.fixture(scope="module")
def andes(client):
    return Api(client, "andes@demo.com")


def test_cada_empresa_ve_solo_lo_suyo(interno, andes):
    # Mismo código de proveedor en las dos empresas, cada una ve el suyo
    mios = {p["codigo"]: p["nombre"] for p in interno.get("/proveedores").json()}
    suyos = {p["codigo"]: p["nombre"] for p in andes.get("/proveedores").json()}
    assert mios["TNF"] == "The North Face" and suyos == {"TNF": "Tolima Natural Farms"}

    # Nada de la otra empresa: órdenes, facturas, embarques, búsqueda, tablero, usuarios
    assert andes.get("/ordenes").json()["total"] == 0
    assert andes.get("/facturas").json()["total"] == 0
    assert andes.get("/embarques").json() == []
    assert andes.get("/buscar", params={"q": "TNF-2026"}).json()["grupos"] == []
    assert {u["email"] for u in andes.get("/usuarios").json()} == {"andes@demo.com"}


def test_un_id_de_otra_empresa_no_existe(interno, andes):
    fid = interno.get("/facturas").json()["items"][0]["id"]
    emb = interno.get("/embarques").json()[0]["id"]
    assert andes.get(f"/facturas/{fid}").status_code == 404
    assert andes.get(f"/embarques/{emb}").status_code == 404
    assert andes.post(f"/edicion/factura/{fid}").status_code == 404


def test_configuracion_propia(interno, andes, admin):
    # Andes no deja finalizar a sus proveedores; la empresa principal sí
    reglas = {r["clave"]: r["valor"] for r in andes.get("/organizacion").json()["reglas"]}
    assert reglas["PROVEEDOR_PUEDE_FINALIZAR"] is False
    reglas = {r["clave"]: r["valor"] for r in admin.get("/organizacion").json()["reglas"]}
    assert reglas["PROVEEDOR_PUEDE_FINALIZAR"] is True

    # Solo la administración cambia la configuración, y se valida
    assert interno.put("/organizacion", {"nombre": "Otra"}).status_code == 403
    assert andes.put("/organizacion", {"reglas": {"DIAS_ALERTA_BORRADOR": "x"}}).status_code == 422
    r = andes.put("/organizacion", {"reglas": {"DIAS_ALERTA_BORRADOR": 3}, "preferencias": {"moneda": "COP"}})
    assert r.status_code == 200, r.text
    assert r.json()["preferencias"]["moneda"] == "COP"
    assert andes.get("/auth/me").json()["config"]["dias_alerta_borrador"] == 3
    assert admin.get("/auth/me").json()["config"]["dias_alerta_borrador"] == 7  # la otra no cambia


def test_plataforma_crea_empresas_y_entra(client, admin, andes):
    assert andes.get("/organizaciones").status_code == 403  # no administra la plataforma
    lista = admin.get("/organizaciones").json()
    assert {o["codigo"] for o in lista} >= {"MAIN", "ANDES"}

    r = admin.post("/organizaciones", {"codigo": "pacific", "nombre": "Pacific Imports", "admin_email": "jefe@pacific.demo"})
    assert r.status_code == 200, r.text
    nueva = r.json()
    assert nueva["codigo"] == "PACIFIC" and nueva["clave_temporal"]
    assert admin.post("/organizaciones", {"codigo": "PACIFIC", "nombre": "X", "admin_email": "x@x.demo"}).status_code == 409

    # Quien administra la plataforma entra a la empresa nueva (solo esa sesión) y vuelve
    plataforma = Api(client, "admin@demo.com")
    assert plataforma.post(f"/organizaciones/{nueva['id']}/entrar").status_code == 200
    yo = plataforma.get("/auth/me").json()
    assert yo["organizacion"]["codigo"] == "PACIFIC" and yo["organizacion"]["propia"] is False
    assert {r["nombre"] for r in plataforma.get("/roles").json()["roles"]} >= {"Administrator"}
    assert plataforma.get("/proveedores").json() == []
    assert admin.get("/auth/me").json()["organizacion"]["codigo"] == "MAIN"  # la otra sesión sigue en la suya
    assert plataforma.post("/organizaciones/1/entrar").status_code == 200
    assert plataforma.get("/auth/me").json()["organizacion"]["codigo"] == "MAIN"
