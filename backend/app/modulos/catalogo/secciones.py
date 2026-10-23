"""Secciones de la familia: lo que cada módulo guarda de una familia.

La familia es una sola y la edita el catálogo (`catalogo/familias.py`). Cada
módulo que necesita algo de ella (logística sus días extra, etiquetado los
campos que sus etiquetas piden, empaque sus reglas…) registra aquí su sección:
cómo se lee, cómo se guarda y qué cuenta como uso. El catálogo no conoce a los
módulos: los recorre por este registro, y la pantalla de la familia muestra una
pestaña por sección.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Usuario
from app.modulos.acceso.permisos import exigir_alguno, tiene


@dataclass(frozen=True)
class SeccionFamilia:
    clave: str  # «logistica», «etiquetado»…
    nombre: str  # el título de la pestaña (en inglés; la interfaz lo traduce)
    orden: int
    leer: Callable[[Session, int], dict]  # (db, familia_id) → lo de la sección
    permisos_ver: tuple[str, ...]
    guardar: Callable[[Session, Usuario, int, dict], dict] | None = None  # (db, user, familia_id, datos) → lo guardado
    permisos_editar: tuple[str, ...] = ()
    # {familia_id: {qué: cuántos}} de lo que apunta a las familias: una familia en uso no se borra
    usos: Callable[[Session], dict[int, dict[str, int]]] | None = None
    solo_familias: bool = False  # no aplica a una categoría


_SECCIONES: dict[str, SeccionFamilia] = {}


def registrar_seccion_familia(seccion: SeccionFamilia) -> None:
    _SECCIONES[seccion.clave] = seccion


def secciones() -> list[SeccionFamilia]:
    return sorted(_SECCIONES.values(), key=lambda s: (s.orden, s.clave))


def seccion(clave: str) -> SeccionFamilia:
    s = _SECCIONES.get(clave)
    if s is None:
        raise ErrorNegocio("That section of the family does not exist.", 404, "no_encontrado")
    return s


def usos(db: Session) -> dict[int, dict[str, int]]:
    """{familia: {qué: cuántos}} de todos los módulos."""
    res: dict[int, dict[str, int]] = {}
    for s in secciones():
        for fid, cuenta in (s.usos(db) if s.usos else {}).items():
            res.setdefault(fid, {}).update({k: n for k, n in cuenta.items() if n})
    return res


def leer_todas(db: Session, user: Usuario, familia_id: int, es_categoria: bool) -> list[dict]:
    """Las secciones que el usuario puede ver, con lo suyo y si las puede cambiar."""
    res = []
    for s in secciones():
        if (s.solo_familias and es_categoria) or not any(tiene(user, p) for p in s.permisos_ver):
            continue
        res.append({"clave": s.clave, "nombre": s.nombre, "datos": s.leer(db, familia_id),
                    "editable": s.guardar is not None and any(tiene(user, p) for p in s.permisos_editar)})
    return res


def guardar(db: Session, user: Usuario, familia_id: int, clave: str, datos: dict) -> dict:
    s = seccion(clave)
    if s.guardar is None:
        raise ErrorNegocio("This section is changed from its own module.", 422, "validacion")
    exigir_alguno(user, *s.permisos_editar)
    return {"clave": s.clave, "nombre": s.nombre, "datos": s.guardar(db, user, familia_id, datos), "editable": True}
