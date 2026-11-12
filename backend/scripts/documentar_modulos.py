"""Escribe docs/MODULOS.md a partir del contrato de cada módulo (app/core/modulos.py).

Lo que dice el documento sale del código: nombre y descripción del contrato,
rutas de sus routers, tareas de fondo, si la empresa puede apagarlo
(acceso/permisos.MODULOS_ACTIVABLES) y de qué otros módulos importa algo.
tests/test_documentacion.py falla si el archivo no está al día.

Uso (desde backend): python scripts/documentar_modulos.py
"""
import ast
import sys
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
RAIZ = BACKEND.parent
DESTINO = RAIZ / "docs" / "MODULOS.md"
METODOS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
sys.path.insert(0, str(BACKEND))


def _usa(clave: str) -> list[str]:
    """Los otros módulos de los que importa algo (leyendo el código, sin ejecutarlo)."""
    usados = set()
    for archivo in (BACKEND / "app" / "modulos" / clave).rglob("*.py"):
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            nombres = []
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                nombres = [f"{nodo.module}.{a.name}" for a in nodo.names] if nodo.module == "app.modulos" else [nodo.module]
            for n in nombres:
                p = n.split(".")
                if p[:2] == ["app", "modulos"] and len(p) > 2 and p[2] != clave:
                    usados.add(p[2])
    return sorted(usados)


def _rutas(modulo) -> tuple[int, list[str]]:
    """Cuántas operaciones tiene y bajo qué prefijos de /api viven."""
    total, prefijos = 0, set()
    for router in modulo.rutas():
        for r in router.routes:
            metodos = METODOS & set(getattr(r, "methods", ()) or ())
            if not metodos:
                continue
            total += len(metodos)
            prefijos.add("/api/" + r.path.strip("/").split("/")[0])
    return total, sorted(prefijos)


def generar() -> str:
    from app.core import modulos
    from app.modulos.acceso.permisos import MODULOS_ACTIVABLES

    contratos = modulos.cargar()
    pantallas = {p.name for p in (RAIZ / "frontend" / "src" / "modulos").iterdir() if p.is_dir()}
    usado_por = defaultdict(list)
    usa = {m.clave: _usa(m.clave) for m in contratos}
    for clave, otros in usa.items():
        for o in otros:
            usado_por[o].append(clave)

    l = [
        "# Módulos",
        "",
        "<!-- Archivo generado por backend/scripts/documentar_modulos.py desde el contrato de cada",
        "     módulo (app/modulos/<clave>/modulo.py). No lo edite a mano: cambie el contrato y vuelva",
        "     a generarlo. tests/test_documentacion.py falla si no está al día. -->",
        "",
        "Cada carpeta de `backend/app/modulos/` es un módulo con su contrato `modulo.py`. Cómo",
        "funciona el contrato y cómo se conectan los módulos sin conocerse está en",
        "[ARQUITECTURA.md](ARQUITECTURA.md#módulos). La lista también se consulta en la API:",
        "`GET /api/modulos`.",
        "",
        "«Se puede apagar» indica que la empresa lo desactiva en Configuración → Empresa →",
        "Módulos. «Usa» son los módulos de los que importa código: es deuda que se va",
        "reduciendo (tests/test_dependencias.py), porque lo ideal es conectarse por registros.",
        "",
        "| Módulo | Clave | Operaciones | Se puede apagar | Usa |",
        "|---|---|---:|---|---|",
    ]
    for m in contratos:
        total, _ = _rutas(m)
        l.append(f"| [{m.nombre}](#{m.clave}) | `{m.clave}` | {total} | "
                 f"{'sí' if m.clave in MODULOS_ACTIVABLES else 'no'} | {', '.join(usa[m.clave]) or '—'} |")
    for m in contratos:
        total, prefijos = _rutas(m)
        l += ["", f'<a id="{m.clave}"></a>', "", f"## {m.nombre}", "", m.descripcion, ""]
        l.append(f"- **Código:** `backend/app/modulos/{m.clave}/`"
                 + (f" · **Pantallas:** `frontend/src/modulos/{m.clave}/`" if m.clave in pantallas else ""))
        if total:
            l.append(f"- **API:** {total} operaciones en " + ", ".join(f"`{p}`" for p in prefijos)
                     + f" (sección «{m.seccion}» de `/docs`)")
        if m.tareas:
            l.append("- **Tareas de fondo:** " + ", ".join(f"`{t.__name__}`" for t in m.tareas))
        if m.al_cargar:
            l.append("- **Se inscribe en registros de otros** al cargar (ver su `modulo.py`)")
        if m.clave in MODULOS_ACTIVABLES:
            l.append("- **Se puede apagar:** " + MODULOS_ACTIVABLES[m.clave][0])
        if usa[m.clave]:
            l.append("- **Usa:** " + ", ".join(f"`{o}`" for o in usa[m.clave]))
        if usado_por[m.clave]:
            l.append("- **Lo usan:** " + ", ".join(f"`{o}`" for o in sorted(usado_por[m.clave])))
    return "\n".join(l) + "\n"


if __name__ == "__main__":
    DESTINO.write_text(generar(), encoding="utf-8")
    print(f"Escrito {DESTINO.relative_to(RAIZ)}")
