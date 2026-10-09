"""La carga de datos incluidos está separada por capa: con datos reales
(SEED_DEMO=0) entran el motor y lo oficial, nunca la empresa de demostración."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

PROGRAMA = """
import json
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from app.main import app
with TestClient(app):
    pass
from app.core.db import SessionLocal
from app.modelos import (AcuerdoComercial, AtributoDef, HistorialClasificacion, IncisoNacional, NodoArancel, PalabraClave,
                        PaisArancel, Producto, Usuario, VersionDataset)
db = SessionLocal()
n = lambda m: db.scalar(select(func.count()).select_from(m))
print(json.dumps({"versiones": n(VersionDataset), "nodos": n(NodoArancel), "atributos": n(AtributoDef),
                  "lineas": n(IncisoNacional), "historial": n(HistorialClasificacion), "palabras": n(PalabraClave),
                  "acuerdos": n(AcuerdoComercial), "productos": n(Producto), "usuarios": n(Usuario),
                  "sac10": [p.iso for p in db.scalars(select(PaisArancel).where(PaisArancel.nivel_base == "SAC10"))]}))
"""


def _arrancar(tmp: str) -> dict:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp}/real.db", "SEED_DEMO": "0", "SECRET_KEY": "x" * 40, "UPLOAD_DIR": tmp, "PYTHONPATH": str(RAIZ)}
    r = subprocess.run([sys.executable, "-c", PROGRAMA], cwd=RAIZ, env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-4000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_datos_reales_sin_demostracion():
    with tempfile.TemporaryDirectory() as tmp:
        d = _arrancar(tmp)
        # Motor y datos oficiales incluidos
        assert d["versiones"] >= 6 and d["nodos"] > 13000 and d["atributos"] > 100
        # Nada de la empresa de demostración: ni historial, ni palabras clave, ni acuerdos de ejemplo, ni usuarios o productos
        assert d["historial"] == d["palabras"] == d["acuerdos"] == d["productos"] == d["usuarios"] == 0
        # Ningún país se declara SAC10 por su cuenta: sin esa configuración no hay líneas nacionales
        assert d["sac10"] == [] and d["lineas"] == 0
        # Un segundo arranque no vuelve a cargar lo oficial (se pone al día por la carga por etapas)
        assert _arrancar(tmp)["versiones"] == d["versiones"]


def test_archivos_separados_por_capa():
    data = RAIZ / "app" / "data"
    assert {p.name for p in (data / "oficial").iterdir()} >= {"01_carga_oficial_catalogos_v3.xlsx", "03_carga_nacional_regulaciones_v3.xlsx",
                                                             "sac_oficial.json", "aci_incisos.json", "sac_notas.json"}
    assert {p.name for p in (data / "motor").iterdir()} >= {"02_carga_motor_dinamico_v3.xlsx", "familias", "sac_explicativas.json",
                                                           "interpretacion_aci.json"}
    assert {p.name for p in (data / "motor" / "familias").iterdir()} == {"comun.json", "calzado.json", "ropa.json", "accesorios.json",
                                                                       "quimicos.json", "materias_primas.json"}
    assert {p.name for p in (data / "demo").iterdir()} >= {"historial_empresa_demo.json", "palabras_empresa_demo.json", "acuerdos_demo.json"}
    assert not [p for p in data.iterdir() if p.is_file()]  # nada suelto fuera de su capa
