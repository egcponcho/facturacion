"""Varias organizaciones en una instalación: cada una ve solo sus datos, sus
códigos son únicos dentro de ella, los datos compartidos los cambia la
plataforma y quien la administra entra a cualquiera para dar soporte."""
import pytest
from conftest import Api
from sqlalchemy import text


@pytest.fixture(scope="module")
def otra(client, admin):
    """Una segunda organización con su administrador; al terminar se suspende
    (con una sola organización activa el resto de las pruebas no cambia)."""
    r = admin.post("/plataforma/organizaciones", {"codigo": "andina", "nombre": "Comercial Andina", "pais": "co",
                                                  "admin_email": "andina@demo.com", "admin_nombre": "Andina admin",
                                                  "admin_telefono": "+573000000001"})
    assert r.status_code == 200, r.text
    org = r.json()
    assert org["codigo"] == "ANDINA" and org["password_temporal"]
    api = Api(client, "andina@demo.com", org["password_temporal"])
    assert api.post("/auth/password", {"actual": org["password_temporal"], "nueva": "Cordillera#2026x"}).status_code == 200
    yield org, api
    admin.patch(f"/plataforma/organizaciones/{org['id']}", {"activa": False})


def test_alta_y_validaciones(admin, interno, otra):
    org, _ = otra
    assert interno.post("/plataforma/organizaciones", {"codigo": "X", "nombre": "X", "admin_email": "x@x.com"}).status_code == 403
    assert admin.post("/plataforma/organizaciones", {"codigo": "ANDINA", "nombre": "Repetida",
                                                     "admin_email": "otro@demo.com"}).status_code == 409
    # El correo identifica al usuario en toda la plataforma
    assert admin.post("/plataforma/organizaciones", {"codigo": "NUEVA", "nombre": "Nueva",
                                                     "admin_email": "interno@demo.com"}).status_code == 409
    lista = {o["codigo"]: o for o in admin.get("/plataforma/organizaciones").json()}
    assert lista["ANDINA"]["usuarios"] == 1 and lista["MAIN"]["usuarios"] >= 4


def test_cada_organizacion_ve_solo_lo_suyo(admin, interno, otra):
    _, andina = otra
    yo = andina.get("/auth/me").json()
    assert yo["organizacion"]["nombre"] == "Comercial Andina" and yo["plataforma"] is False
    assert andina.get("/ordenes", params={"solo_disponible": False}).json()["items"] == []
    assert andina.get("/facturas").json()["items"] == []
    assert andina.get("/proveedores").json() == []
    assert [u["email"] for u in andina.get("/usuarios").json()] == ["andina@demo.com"]
    assert {r["nombre"] for r in andina.get("/roles").json()["roles"]} >= {"Administrator", "Internal team", "Supplier"}
    # Empieza con sus listas de valores de fábrica
    assert {v["codigo"] for v in andina.get("/listas").json()["moneda"]} >= {"USD", "EUR"}
    # Un id de otra organización no existe para ella
    factura = interno.get("/facturas").json()["items"][0]
    oc = interno.get("/ordenes", params={"solo_disponible": False}).json()["items"][0]
    producto = interno.get("/productos", params={"size": 1}).json()["items"][0]
    assert andina.get(f"/facturas/{factura['id']}").status_code == 404
    assert andina.get(f"/ordenes/{oc['id']}/posiciones").status_code == 404
    assert andina.get(f"/productos/{producto['id']}").status_code == 404
    usuario_main = next(u for u in admin.get("/usuarios").json() if u["email"] == "interno@demo.com")
    assert andina.patch(f"/usuarios/{usuario_main['id']}", {"cargo": "x"}).status_code == 404
    # Su bitácora es solo suya
    assert all(x["entidad"] != "factura" for x in andina.get("/auditoria", params={"size": 200}).json()["items"])


def test_codigos_unicos_por_organizacion(admin, interno, otra):
    _, andina = otra
    r = andina.post("/catalogos/proveedores", {"codigo": "VANS", "nombre": "Vans Andina", "pais": "CN"})
    assert r.status_code == 200, r.text
    assert andina.post("/catalogos/proveedores", {"codigo": "VANS", "nombre": "Repetido"}).status_code == 409
    nombres_main = {p["nombre"] for p in interno.get("/catalogos/proveedores").json()["items"]}
    assert "Vans Andina" not in nombres_main and "Vans" in nombres_main
    # Correos únicos en toda la plataforma
    assert andina.post("/usuarios", {"email": "interno@demo.com", "nombre": "Copia", "rol": "interno",
                                     "telefono": "+573000000002"}).status_code == 409


def test_datos_compartidos_los_cambia_la_plataforma(admin, interno, otra):
    _, andina = otra
    # Con dos organizaciones activas, editar el arancel o el motor afecta a todas
    assert "aranceles.editar" not in interno.get("/auth/me").json()["permisos"]
    assert "aranceles.editar" in admin.get("/auth/me").json()["permisos"]
    pais = andina.get("/catalogos/paises").json()["items"][0]
    r = andina.patch(f"/catalogos/paises/{pais['id']}", {"nombre": pais["nombre"]})
    assert r.status_code == 403 and r.json()["codigo"] in ("dato_compartido", "sin_permiso")
    # Los datos compartidos sí se leen
    assert andina.get("/catalogos/paises").json()["items"]


def test_plataforma_entra_a_otra_organizacion(admin, otra):
    org, andina = otra
    try:
        assert admin.post("/plataforma/entrar", {"organizacion_id": org["id"]}).status_code == 200
        yo = admin.get("/auth/me").json()
        assert yo["organizacion"]["nombre"] == "Comercial Andina" and yo["organizacion"]["propia"] is False
        assert "admin" in yo["permisos"]
        assert [p["codigo"] for p in admin.get("/catalogos/proveedores").json()["items"]] == ["VANS"]
        # Su propio perfil se sigue editando desde ahí
        assert admin.patch("/perfil", {"cargo": "Platform support"}).status_code == 200
        # Lo que hace queda en la bitácora de esa organización
        acciones = [x["accion"] for x in andina.get("/auditoria").json()["items"]]
        assert "entrada_plataforma" in acciones
    finally:
        admin.post("/plataforma/entrar", {"organizacion_id": None})
        admin.patch("/perfil", {"cargo": "Systems administrator"})
    assert admin.get("/auth/me").json()["organizacion"]["nombre"] == "Distribuidora de Marcas"


def test_organizacion_suspendida(client, admin, otra):
    org, andina = otra
    assert admin.patch(f"/plataforma/organizaciones/{org['id']}", {"activa": False}).status_code == 200
    try:
        assert andina.get("/auth/me").status_code == 401
        r = client.post("/api/auth/login", json={"email": "andina@demo.com", "password": "Cordillera#2026x"})
        assert r.status_code == 403 and r.json()["codigo"] == "organizacion_inactiva"
        # Con una sola organización activa, el equipo interno vuelve a editar el arancel
        assert admin.patch("/plataforma/organizaciones/1", {"activa": False}).status_code == 422
    finally:
        admin.patch(f"/plataforma/organizaciones/{org['id']}", {"activa": True})


def test_seguridad_por_fila_en_postgresql(otra):
    """Aun con SQL escrito a mano, una transacción de una organización no lee
    ni escribe filas de otra (políticas RLS de la migración 0047)."""
    from app.core.db import engine

    if engine.dialect.name != "postgresql":
        pytest.skip("RLS solo existe en PostgreSQL")
    org, _ = otra
    fijar = text("SELECT set_config('app.organizacion_id', :o, true)")
    with engine.begin() as con:
        total = con.execute(text("SELECT count(*) FROM proveedores")).scalar()
    with engine.begin() as con:
        con.execute(fijar, {"o": str(org["id"])})
        assert con.execute(text("SELECT codigo FROM proveedores")).scalars().all() == ["VANS"]
        assert con.execute(text("SELECT count(*) FROM facturas")).scalar() == 0
    with engine.begin() as con:  # sin organización fijada (arranque, migraciones): todo
        assert con.execute(text("SELECT count(*) FROM proveedores")).scalar() == total
    with pytest.raises(Exception, match="row-level security"):
        with engine.begin() as con:
            con.execute(fijar, {"o": str(org["id"])})
            con.execute(text("INSERT INTO proveedores (codigo, nombre, activo, extra, organizacion_id) "
                             "VALUES ('INTRUSO', 'x', true, '{}', 1)"))
