"""Vocabulario de búsqueda en el texto oficial del arancel (SinonimoBusqueda).

El texto oficial está en español: un nombre en inglés («Cordless drill») o un
término comercial no encuentra nada si no se sabe a qué palabras del texto
oficial equivale. Este vocabulario (de base y editable) solo ayuda a encontrar
candidatos: nunca confirma un código.
"""
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..datos import MOTOR
from ..models import SinonimoBusqueda, Usuario
from .common import ErrorNegocio, exigir, registrar


def sembrar(db: Session) -> int:
    """El vocabulario de base (no pisa lo editado)."""
    d = json.loads((MOTOR / "sinonimos_busqueda.json").read_text(encoding="utf-8"))
    existentes = {x.palabra for x in db.scalars(select(SinonimoBusqueda))}
    n = 0
    for x in d["sinonimos"]:
        if x["palabra"] not in existentes:
            db.add(SinonimoBusqueda(palabra=x["palabra"], equivale=x["equivale"], origen="MOTOR", activo=True))
            n += 1
    db.flush()
    return n


def _dict(x: SinonimoBusqueda) -> dict:
    return {"id": x.id, "palabra": x.palabra, "equivale": x.equivale, "origen": x.origen, "activo": x.activo}


def listar(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "clasificacion.ver")
    return [_dict(x) for x in db.scalars(select(SinonimoBusqueda).order_by(SinonimoBusqueda.palabra))]


def guardar(db: Session, user: Usuario, sid: int | None, datos: dict) -> dict:
    from .indice_arbol import palabras

    exigir(user, "clasificacion.configurar")
    x = db.get(SinonimoBusqueda, sid) if sid else None
    if sid and not x:
        raise ErrorNegocio("The search word does not exist.", 404, "no_encontrado")
    if not x:
        p = " ".join(palabras(datos.get("palabra") or ""))
        if not p:
            raise ErrorNegocio("Write the word to look for (3 letters or more).", 422, "validacion")
        if db.scalar(select(SinonimoBusqueda.id).where(SinonimoBusqueda.palabra == p)):
            raise ErrorNegocio(f"«{p}» already has its equivalents: edit them.", 422, "validacion")
        x = SinonimoBusqueda(palabra=p, origen="USUARIO", activo=True)
        db.add(x)
    if datos.get("equivale") is not None:
        eq = " ".join(dict.fromkeys(palabras(datos["equivale"])))
        if not eq:
            raise ErrorNegocio("Write the words of the official text it is equivalent to.", 422, "validacion")
        x.equivale = eq
    if datos.get("activo") is not None:
        x.activo = bool(datos["activo"])
    if not x.equivale:
        raise ErrorNegocio("Write the words of the official text it is equivalent to.", 422, "validacion")
    db.flush()
    registrar(db, user, "aranceles", x.id, "sinonimo_busqueda", {"palabra": x.palabra, "equivale": x.equivale})
    return _dict(x)
