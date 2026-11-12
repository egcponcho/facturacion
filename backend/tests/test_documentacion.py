"""La documentación que sale del código está al día.

docs/MODULOS.md se genera con scripts/documentar_modulos.py desde el contrato
de cada módulo. Si se agrega, quita o cambia un módulo, vuelva a generarlo.
"""
import importlib.util
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("documentar_modulos", BACKEND / "scripts" / "documentar_modulos.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_modulos_md_esta_al_dia():
    script = _script()
    actual = script.DESTINO.read_text(encoding="utf-8") if script.DESTINO.exists() else ""
    assert actual == script.generar(), "docs/MODULOS.md no está al día: corra python scripts/documentar_modulos.py"


def test_los_documentos_citados_en_el_codigo_existen():
    """Cada documento de docs/ que cita un comentario del código existe."""
    import re
    raiz = BACKEND.parent
    citados = set()
    for carpeta, patron in ((BACKEND / "app", "*.py"), (BACKEND / "tests", "*.py"), (raiz / "frontend" / "src", "*.vue"),
                            (raiz / "frontend" / "src", "*.js"), (raiz / "ops", "*.sh")):
        for f in carpeta.rglob(patron):
            citados |= {(m, f.name) for m in re.findall(r"docs/[A-Za-z_/]+\.md", f.read_text(encoding="utf-8"))}
    faltan = sorted(f"{c} (en {f})" for c, f in citados if not (raiz / c).exists())
    assert not faltan, faltan
