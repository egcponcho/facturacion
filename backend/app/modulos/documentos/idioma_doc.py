"""Idioma de los documentos que se descargan (PDF y Excel).

Cada persona elige en su perfil el idioma de sus documentos (español o
inglés); una descarga también puede pedirlo con ?idioma=es|en. Los textos de
los documentos se escriben en inglés y `L()` los devuelve en el idioma de la
descarga en curso, con la traducción de app/i18n/es.json (la misma de la
pantalla, que genera frontend/scripts/i18n-extraer.mjs).
"""
import json
import re
from contextvars import ContextVar
from pathlib import Path

IDIOMAS = ("es", "en")
_idioma: ContextVar[str] = ContextVar("idioma_documento", default="en")
_ES: dict[str, str] = {}
_ARCHIVO = Path(__file__).resolve().parents[2] / "i18n" / "es.json"


def _cargar() -> dict[str, str]:
    if not _ES and _ARCHIVO.exists():
        _ES.update(json.loads(_ARCHIVO.read_text(encoding="utf-8")))
    return _ES


def usar(idioma: str | None) -> None:
    _idioma.set(idioma if idioma in IDIOMAS else "en")


def actual() -> str:
    return _idioma.get()


def _propios() -> dict[str, str]:
    """Textos propios de la empresa en el idioma del documento (Configuración → Empresa)."""
    from app.core.empresa import configuracion_actual

    return (configuracion_actual().get("textos") or {}).get(_idioma.get()) or {}


def L(texto, *args) -> str:
    """Texto del documento en su idioma; {0}, {1}… se reemplazan por args."""
    if texto is None:
        return texto
    t = str(texto)
    if t in _propios():
        t = _propios()[t]
    elif _idioma.get() == "es":
        t = _cargar().get(t, t)
    if args:
        t = re.sub(r"\{(\d)\}", lambda m: "" if int(m.group(1)) >= len(args) or args[int(m.group(1))] is None
                   else str(args[int(m.group(1))]), t)
    return t


_PLANTILLAS: list[tuple[re.Pattern, str]] = []


def armado(texto: str | None) -> str | None:
    """Un mensaje ya armado («Missing required values: Qty.») en el idioma del documento: se
    reconoce por su plantilla («Missing required values: {0}.»). Las partes variables son datos
    (columnas, códigos) y quedan tal cual."""
    if not texto or _idioma.get() != "es":
        return texto
    es = _cargar()
    if texto in es:
        return es[texto]
    if not _PLANTILLAS:
        for clave in sorted((k for k in es if "{0}" in k), key=len, reverse=True):
            partes = re.split(r"\{(\d)\}", clave)
            patron = "".join(re.escape(x) if i % 2 == 0 else "(.+?)" for i, x in enumerate(partes))
            _PLANTILLAS.append((re.compile(f"^{patron}$", re.S), clave))
    for patron, clave in _PLANTILLAS:
        m = patron.match(texto)
        if m:
            orden = [int(x) for x in re.findall(r"\{(\d)\}", clave)]
            args: list = [None] * (max(orden) + 1)
            for i, n in enumerate(orden):
                args[n] = m.group(i + 1)
            return L(clave, *args)
    return texto


def _celda(v):
    """Una celda de un reporte: se traducen los textos del sistema (estados,
    «Pending»…), no los datos (códigos en mayúsculas, descripciones)."""
    if isinstance(v, str) and v in _propios():
        return _propios()[v]
    if isinstance(v, str) and re.search(r"[a-z]", v) and _idioma.get() == "es" and v in _cargar():
        return _ES[v]
    return v


def reporte(titulo: str, subtitulo: str, indicadores: list, columnas: list, filas: list[list], hojas: list[dict] | None = None):
    """Títulos, columnas, indicadores y estados de un reporte en el idioma del documento."""
    columnas = [(L(c[0]), *c[1:]) for c in columnas]
    indicadores = [(L(k), _celda(v)) for k, v in indicadores]
    filas = [[_celda(v) for v in f] for f in filas]
    hojas = [{**h, "titulo": L(h["titulo"]), "columnas": [(L(c[0]), *c[1:]) for c in h["columnas"]],
              "filas": [[_celda(v) for v in f] for f in h["filas"]]} for h in hojas or []]
    return L(titulo), L(subtitulo), indicadores, columnas, filas, hojas
