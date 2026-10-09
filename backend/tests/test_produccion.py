"""Arranque en producción (SEED_DEMO=0): sin clave secreta no arranca; una
instalación nueva queda con su empresa, los roles de fábrica y el primer
administrador con contraseña temporal; nada de la demostración."""
import json
import os
import subprocess
import sys
import tempfile

from test_cargas import RAIZ

PROGRAMA = """
import json
from fastapi.testclient import TestClient
with TestClient(app := __import__("app.main", fromlist=["app"]).app) as c:
    r = c.post("/api/auth/login", json={"email": "jefa@empresa.com", "password": "Inicial#2026x"})
from sqlalchemy import select
from app.core.db import SessionLocal
from app.modelos import Organizacion, Rol, Usuario
db = SessionLocal()
u = db.scalar(select(Usuario))
print(json.dumps({"empresa": db.get(Organizacion, 1).nombre, "roles": sorted(r.nombre for r in db.scalars(select(Rol))),
                  "usuarios": [[x.email, x.rol, x.clave_temporal] for x in db.scalars(select(Usuario))],
                  "login": r.status_code, "temporal": r.json().get("clave_temporal")}))
"""


def _arrancar(tmp: str, **extra) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp}/p.db", "SEED_DEMO": "0", "UPLOAD_DIR": tmp,
           "PYTHONPATH": str(RAIZ), "DOS_PASOS": "0", **extra}
    env.pop("SECRET_KEY", None) if "SECRET_KEY" not in extra else None
    return subprocess.run([sys.executable, "-c", PROGRAMA], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=600)


def test_sin_clave_secreta_no_arranca():
    with tempfile.TemporaryDirectory() as tmp:
        r = _arrancar(tmp)
        assert r.returncode != 0 and "Falta SECRET_KEY" in r.stderr
        r = _arrancar(tmp, SECRET_KEY="corta")
        assert r.returncode != 0 and "muy corta" in r.stderr


def test_instalacion_nueva_con_primer_administrador():
    with tempfile.TemporaryDirectory() as tmp:
        r = _arrancar(tmp, SECRET_KEY="k" * 40, EMPRESA_NOMBRE="Importadora Ejemplo",
                      ADMIN_EMAIL="Jefa@Empresa.com", ADMIN_PASSWORD="Inicial#2026x")
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout.strip().splitlines()[-1])
        assert d["empresa"] == "Importadora Ejemplo"
        assert {"Administrator", "Supplier", "Internal team"} <= set(d["roles"])
        assert d["usuarios"] == [["jefa@empresa.com", "admin", True]]
        # Entra con la contraseña inicial y el sistema le pide cambiarla
        assert d["login"] == 200, d
