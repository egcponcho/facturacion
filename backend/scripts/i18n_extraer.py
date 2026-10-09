"""Textos del servidor que llegan a la pantalla (mensajes de error, etiquetas
de catálogos y permisos, tareas del tablero, estados…), como plantillas con
{0}, {1}… en lugar de los valores. El frontend los traduce aunque lleguen ya
armados. Escribe app/i18n/claves.json.

Uso: python scripts/i18n_extraer.py
"""
import ast
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "app"
# Documentos y plantillas para aduana/ERP, datos de demostración y textos oficiales: no se traducen aquí
# (rutas dentro de app/; una carpeta omite todo lo que contiene)
OMITIR = ("main.py", "core/config.py", "core/db.py", "core/seguridad.py", "core/dependencias.py",
          "core/migraciones.py", "modelos/", "esquemas/__init__.py", "instalacion/demo.py", "instalacion/inicial.py",
          "modulos/documentos/documentos.py",
          "modulos/documentos/exportar.py", "modulos/documentos/plantillas.py", "modulos/acceso/sms.py",
          "modulos/clasificacion/especialista.py")
MODELOS: set = set()
ESPANOL = re.compile(r"[áéíóúñ¿¡]|\b(de|del|la|el|los|las|y|para|con|por|una|que)\b", re.I)


def es_texto(s: str) -> bool:
    t = s.strip()
    if not re.search(r"[A-Za-z]{2,}", t) or not re.search(r"[a-z]", t):
        return False
    if re.match(r"^(/|#|\.|@|https?:|var\(|%|\{)", t) and not re.search(r"\s", t):
        return False
    if re.fullmatch(r"[\w.:-]+", t) and not re.search(r"[A-Z]", t):
        return False
    if not re.search(r"\s", t) and re.search(r"[:/_?=\-]", t):
        return False
    if re.fullmatch(r"[a-z]+[A-Z]\w*", t):
        return False
    if t.startswith("^") or t.startswith("attachment;") or t.startswith("\\b") or t.endswith("%") or "|\\(" in t:  # patrones
        return False
    if ESPANOL.search(t):
        return False
    if re.fullmatch(r"\w+\.\w+", t) or t in MODELOS or "max-age" in t or "self'" in t:
        return False
    if re.search(r"\b(select|where|join)\b", t) and "(" in t:
        return False
    return True


def plantilla(nodo: ast.JoinedStr) -> str:
    out, n = "", 0
    for v in nodo.values:
        if isinstance(v, ast.Constant):
            out += str(v.value)
        else:
            out += "{" + str(n) + "}"
            n += 1
    return out


def docstrings(arbol) -> set:
    ids = set()
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body:
            p = n.body[0]
            if isinstance(p, ast.Expr) and isinstance(getattr(p, "value", None), ast.Constant):
                ids.add(id(p.value))
    return ids


def extraer() -> list[str]:
    claves = set()
    for ruta in RAIZ.rglob("*.py"):
        if ruta.relative_to(RAIZ).as_posix().startswith(OMITIR):
            # De los documentos (PDF/Excel), solo los textos que pasan por L()
            for n in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "L" and n.args \
                        and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                    claves.add(n.args[0].value)
            continue
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        docs = docstrings(arbol)
        dentro_fstring = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.JoinedStr):
                for v in n.values:
                    dentro_fstring.add(id(v))
                t = plantilla(n)
                if es_texto(t) and re.search(r"[A-Za-z]{3,}", re.sub(r"\{\d\}", "", t)):
                    claves.add(t)
        for n in ast.walk(arbol):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and id(n) not in dentro_fstring:
                # El vocabulario del lector de composiciones (palabras en minúscula) no es texto de pantalla
                if es_texto(n.value) and not (ruta.name == "composicion.py" and not n.value[:1].isupper()):
                    claves.add(n.value)
    # Concatenaciones "texto: " + ", ".join(...) quedan como su parte fija
    return sorted(claves)


if __name__ == "__main__":
    for ruta in [*(RAIZ / "modelos").glob("*.py"), RAIZ / "modulos" / "productos" / "ficha.py"]:
        MODELOS.update(re.findall(r"^class (\w+)", ruta.read_text(encoding="utf-8"), re.M))
    lista = extraer()
    (RAIZ / "i18n" / "claves.json").write_text(json.dumps(lista, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(len(lista), "textos del servidor")
