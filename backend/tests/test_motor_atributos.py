"""El motor de la ficha (JavaScript) frente al catálogo de atributos de la base."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node no está instalado")


def test_reglas_extraidas_al_dia_con_el_motor():
    """motor_reglas.json (la lógica de clasificarReglas como reglas de datos) se
    regenera con scripts/motor-reglas.mjs al cambiar el motor; el script además
    comprueba la paridad del árbol con motor.js sobre muestras al azar."""
    r = subprocess.run([NODE, "scripts/motor-reglas.mjs", "--verificar"], cwd=RAIZ / "frontend", capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-2000:] + "\nEjecuta node scripts/motor-reglas.mjs"


def test_motor_aplica_el_catalogo_de_la_base():
    script = """
const M = await import(process.argv[2])
const s = { tipo: 'camiseta', comp: {} }
const antes = [M.ATTR_BY.polo.aplica(s), M.opcionesValidas(M.ATTR_BY.tejido, { tipo: 'camisa' }).map(o => o.v)]
M.setAtributos({ motor: { polo: { activo: false, etiqueta: 'Polo collar', opciones: {} },
  tejido: { etiqueta: 'Fabric', opciones: { plano: { activo: false, orden: 5 }, punto: { activo: true, orden: 10 } } } } })
const despues = [M.ATTR_BY.polo.aplica(s), M.ATTR_BY.polo.label, M.opcionesValidas(M.ATTR_BY.tejido, { tipo: 'camisa' }).map(o => o.v),
  M.ATTR_BY.tejido.ops.map(o => o.v)]
M.setAtributos({ motor: {} })
const restaurado = [M.ATTR_BY.polo.aplica(s), M.opcionesValidas(M.ATTR_BY.tejido, { tipo: 'camisa' }).map(o => o.v)]
console.log(JSON.stringify({ antes, despues, restaurado }))
"""
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "p.mjs"
        f.write_text(script)
        r = subprocess.run([NODE, str(f), str(RAIZ / "frontend/src/clasificacion/motor.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["antes"] == [True, ["punto", "plano"]]
    # Atributo apagado, etiqueta editada, opción desactivada y nuevo orden
    assert d["despues"] == [False, "Polo collar", ["punto"], ["plano", "punto"]]
    assert d["restaurado"] == d["antes"]
