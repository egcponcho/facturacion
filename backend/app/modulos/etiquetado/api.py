"""Etiquetado: familias, campos disponibles, plantillas y sus versiones,
asignaciones, generación y descargas (docs/ETIQUETADO.md)."""
from typing import Any

from fastapi import APIRouter, Body, Query

from app.modulos.acceso.permisos import exigir_alguno
from app.modulos.etiquetado import campos, familias
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


# ---- Campos dinámicos -------------------------------------------------------------------
@router.get("/etiquetas/campos")
def listar_campos(db: Db, user: User, modalidad: str | None = Query(None, pattern="^(ARTICULO|OC|OC_ARTICULO)$")):
    """Campos que se pueden poner en una etiqueta, por grupo, con su origen (tabla.columna) y un ejemplo."""
    exigir_alguno(user, "etiquetas.ver", "etiquetas.disenar")
    return {"grupos": campos.GRUPOS, "modalidades": {k: sorted(v) for k, v in campos.POR_MODALIDAD.items()},
            "campos": [campos.dict_campo(c) for c in campos.catalogo(db, modalidad)]}


# ---- Familias de etiquetado --------------------------------------------------------------
@router.get("/etiquetas/familias")
def listar_familias(db: Db, user: User, activas: bool | None = None):
    """Familias de etiquetado de la empresa con cuántos artículos y diseños tienen."""
    return familias.listar(db, user, activas)


@router.post("/etiquetas/familias")
def crear_familia(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Nueva familia: código, nombre, descripción, orden y campos habituales u obligatorios."""
    return ejecutar(db, user, clave, lambda: familias.crear(db, user, datos))


@router.put("/etiquetas/familias/orden")
def ordenar_familias(db: Db, user: User, ids: list[int] = Body(..., embed=True)):
    """Orden de las familias (todas, en el orden deseado)."""
    return ejecutar(db, user, None, lambda: familias.ordenar(db, user, ids))


@router.patch("/etiquetas/familias/{familia_id}")
def actualizar_familia(familia_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Cambia nombre, descripción, orden, campos o la desactiva (activa: false)."""
    return ejecutar(db, user, clave, lambda: familias.actualizar(db, user, familia_id, datos))


@router.delete("/etiquetas/familias/{familia_id}")
def eliminar_familia(familia_id: int, db: Db, user: User):
    """Borra una familia sin uso (si se usa, se desactiva)."""
    return ejecutar(db, user, None, lambda: familias.eliminar(db, user, familia_id))


@router.get("/etiquetas/articulos")
def articulos_familia(db: Db, user: User, q: str | None = None, familia: str | None = None, marca_id: int | None = None,
                      grupo_id: int | None = None, producto_id: int | None = None, page: int = Query(1, ge=1),
                      size: int = Query(50, ge=1, le=200)):
    """Artículos con su familia de etiquetado (familia=sin: los que no tienen)."""
    return familias.articulos(db, user, q, familia, marca_id, grupo_id, producto_id, page, size)


@router.post("/etiquetas/articulos/familia")
def asignar_familia(db: Db, user: User, familia_id: int | None = Body(None), ids: list[int] | None = Body(None),
                    filtro: dict[str, Any] | None = Body(None), clave: Clave = None):
    """Pone la familia (o la quita, con familia_id vacío) a los artículos elegidos o a todos los del filtro."""
    return ejecutar(db, user, clave, lambda: familias.asignar_articulos(db, user, familia_id, ids, filtro))
