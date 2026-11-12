import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["UPLOAD_DIR"] = f"{_tmp}/archivos"
os.environ["SEED_DEMO"] = "1"
# Hash de contraseñas más liviano: las pruebas crean y verifican muchas
os.environ.setdefault("PBKDF2_ITERACIONES", "20000")
os.environ["COOKIE_SEGURA"] = "0"
os.environ["FRONTEND_DIST"] = f"{_tmp}/no-existe"
# La recuperación de trabajos de etiquetado se prueba llamándola (test_etiquetado_durable.py)
os.environ["ETIQUETAS_RECUPERAR_SEG"] = "0"
# Canal de cambios: revisión rápida para probarlo sin esperas largas
os.environ["CAMBIOS_INTERVALO_SEG"] = "0.3"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# PostgreSQL de pruebas: siempre desde cero (si no, los datos de la corrida
# anterior se quedan y el sembrado no se repite mientras no cambie el esquema)
if os.environ.get("TEST_DATABASE_URL"):
    from sqlalchemy import create_engine, text

    _motor = create_engine(os.environ["TEST_DATABASE_URL"])
    with _motor.begin() as _c:
        _c.execute(text("DROP SCHEMA public CASCADE"))
        _c.execute(text("CREATE SCHEMA public"))
    _motor.dispose()

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


PASSWORD = "Supplier2026"


def iniciar_sesion(client, email, password=PASSWORD) -> str:
    """Contraseña y código de verificación (en la demo el código viene en la
    respuesta). Devuelve el token de la sesión (el valor de la cookie)."""
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    if r.json()["dos_pasos"]:
        d = r.json()
        r = client.post("/api/auth/verificar", json={"desafio": d["desafio"], "codigo": d["codigo_demo"]})
        assert r.status_code == 200, r.text
    token = r.cookies["sesion"]
    client.cookies.clear()
    return token


class Api:
    def __init__(self, client, email, password=PASSWORD):
        self.c = client
        self.h = {"Authorization": f"Bearer {iniciar_sesion(client, email, password)}"}
        self.yo = self.c.get("/api/auth/me", headers=self.h).json()

    def get(self, url, **kw):
        # Las pruebas leen los documentos (PDF/Excel) en inglés, salvo que pidan otro idioma.
        # Los parámetros escritos en la ruta se suman a `params` (httpx 0.28 reemplaza
        # la consulta de la URL cuando recibe `params`, y los filtros se perdían).
        ruta, _, consulta = url.partition("?")
        pares = list(httpx.QueryParams(consulta).multi_items()) + list(httpx.QueryParams(kw.get("params") or {}).multi_items())
        if not any(k == "idioma" for k, _ in pares):
            pares.insert(0, ("idioma", "en"))
        kw["params"] = pares
        return self.c.get("/api" + ruta, headers=self.h, **kw)

    def post(self, url, json=None, clave=None, **kw):
        h = dict(self.h)
        if clave:
            h["Idempotency-Key"] = clave
        return self.c.post("/api" + url, json=json, headers=h, **kw)

    def patch(self, url, json=None):
        return self.c.patch("/api" + url, json=json, headers=self.h)

    def put(self, url, json=None):
        return self.c.put("/api" + url, json=json, headers=self.h)

    def delete_(self, url):
        return self.c.delete("/api" + url, headers=self.h)


@pytest.fixture(scope="session")
def tnf(client):
    return Api(client, "tnf@demo.com")


@pytest.fixture(scope="session")
def vans(client):
    return Api(client, "vans@demo.com")


@pytest.fixture(scope="session")
def interno(client):
    return Api(client, "interno@demo.com")


@pytest.fixture(scope="session")
def admin(client):
    return Api(client, "admin@demo.com")


def con_atributos(api, familia_id):
    """Una familia de prueba que va a recibir productos de la demostración lleva sus atributos
    (los que no son generales: color, talla, género…): un producto solo pasa a una familia donde
    valen los atributos que ya tiene."""
    codigos = [a["codigo"] for a in api.get("/catalogos/atributos", params={"size": 100}).json()["items"] if not a["general"]]
    r = api.patch(f"/grupos-producto/{familia_id}", {"atributos": codigos})
    assert r.status_code == 200, r.text


def familia_de(articulo_id=None, producto_id=None):
    """La familia que tiene ahora el producto (o el producto del artículo), para dejarla como estaba."""
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import Articulo, Producto

    with SessionLocal() as db, en_organizacion(1):
        p = db.get(Articulo, articulo_id).producto if articulo_id else db.get(Producto, producto_id)
        return p.familia_etiquetado_id


def familia_demo(codigo="FOOTWEAR"):
    """El id de una familia de la demostración (FOOTWEAR, FOOTWEAR-TECH, APPAREL, ACCESSORIES)."""
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import GrupoProducto

    with SessionLocal() as db, en_organizacion(1):
        return db.scalar(select(GrupoProducto.id).where(GrupoProducto.codigo == codigo))
