"""Rutas del árbol de grupos de producto (Datos maestros → Grupos de producto).
"""
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.modulos.grupos import arbol
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


class _Cuerpo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Condicion(_Cuerpo):
    campo: str
    op: str
    valor: str | int | float | list | None = None


class CampoGrupo(_Cuerpo):
    """Un dato del producto o del artículo que el grupo pide (obligatorio: se exige al guardar y al etiquetar)."""
    campo: str = Field(max_length=80)
    obligatorio: bool = False


class GrupoIn(_Cuerpo):
    clase: str = "FAMILIA"
    codigo: str
    nombre: str
    descripcion: str | None = None
    padre_id: int | None = None
    condiciones: list[Condicion] = Field(default_factory=list)
    ejes_variante: list[str] = Field(default_factory=list, max_length=20)
    campos: list[CampoGrupo] = Field(default_factory=list, max_length=60)


class GrupoPatch(_Cuerpo):
    codigo: str | None = None
    nombre: str | None = None
    descripcion: str | None = None
    padre_id: int | None = None
    condiciones: list[Condicion] | None = None
    ejes_variante: list[str] | None = Field(None, max_length=20)
    campos: list[CampoGrupo] | None = Field(None, max_length=60)
    orden: int | None = None
    activa: bool | None = None


@router.get("/grupos-producto")
def listar(db: Db, user: User, incluir_inactivos: bool = True):
    """Todos los grupos de producto en orden de árbol, con lo que los usa."""
    return arbol.arbol(db, user, incluir_inactivos)


@router.get("/grupos-producto/campos")
def campos(db: Db, user: User):
    """Datos del artículo y del producto con que se reconoce una categoría, y los operadores."""
    return arbol.campos(db, user)


@router.post("/grupos-producto")
def crear(datos: GrupoIn, db: Db, user: User, clave: Clave = None):
    """Crea una familia (en la raíz o dentro de otra) o una categoría dentro de una familia."""
    return ejecutar(db, user, clave, lambda: arbol.crear(db, user, datos.model_dump(mode="json")))


@router.patch("/grupos-producto/{grupo_id}")
def actualizar(grupo_id: int, datos: GrupoPatch, db: Db, user: User, clave: Clave = None):
    """Cambia el nombre, el lugar en el árbol, las condiciones o si está activo."""
    return ejecutar(db, user, clave, lambda: arbol.actualizar(db, user, grupo_id, datos.model_dump(mode="json",
                                                                                                    exclude_unset=True)))


@router.delete("/grupos-producto/{grupo_id}")
def eliminar(grupo_id: int, db: Db, user: User, clave: Clave = None):
    """Borra un grupo sin uso; si algo lo usa, hay que desactivarlo."""
    return ejecutar(db, user, clave, lambda: arbol.eliminar(db, user, grupo_id))
