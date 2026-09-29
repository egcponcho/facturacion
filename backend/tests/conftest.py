import os
import sys
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["UPLOAD_DIR"] = f"{_tmp}/archivos"
os.environ["SEED_DEMO"] = "1"
os.environ["FRONTEND_DIST"] = f"{_tmp}/no-existe"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


class Api:
    def __init__(self, client, email):
        self.c = client
        r = client.post("/api/auth/login", json={"email": email, "password": "demo123"})
        assert r.status_code == 200, r.text
        self.h = {"Authorization": f"Bearer {r.json()['token']}"}
        self.yo = r.json()["usuario"]

    def get(self, url, **kw):
        return self.c.get("/api" + url, headers=self.h, **kw)

    def post(self, url, json=None, clave=None, **kw):
        h = dict(self.h)
        if clave:
            h["Idempotency-Key"] = clave
        return self.c.post("/api" + url, json=json, headers=h, **kw)

    def patch(self, url, json=None):
        return self.c.patch("/api" + url, json=json, headers=self.h)

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
