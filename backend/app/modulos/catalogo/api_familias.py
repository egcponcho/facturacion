"""Rutas de las familias del catálogo: el controlador único (familias, subfamilias y
categorías, sus productos y las secciones de cada módulo)."""
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.modulos.catalogo import familias
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


class _Cuerpo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Condicion(_Cuerpo):
    campo: str
    op: str
    valor: str | int | float | list | None = None


class CampoGrupo(_Cuerpo):
    """Un dato del producto o del artículo que la familia exige a sus productos al guardarlos."""
    campo: str = Field(max_length=80)
    obligatorio: bool = False


class GrupoIn(_Cuerpo):
    clase: str = "FAMILIA"
    codigo: str
    nombre: str
    descripcion: str | None = None
    padre_id: int | None = None
    condiciones: list[Condicion] = Field(default_factory=list)
    atributos: list[str] = Field(default_factory=list, max_length=100)
    campos: list[CampoGrupo] = Field(default_factory=list, max_length=60)
    activa: bool = True


class GrupoPatch(_Cuerpo):
    codigo: str | None = None
    nombre: str | None = None
    descripcion: str | None = None
    padre_id: int | None = None
    condiciones: list[Condicion] | None = None
    atributos: list[str] | None = Field(None, max_length=100)
    campos: list[CampoGrupo] | None = Field(None, max_length=60)
    orden: int | None = None
    activa: bool | None = None


class Orden(_Cuerpo):
    ids: list[int] = Field(max_length=2000)


class Prueba(_Cuerpo):
    familia_id: int
    categoria_id: int | None = None
    condiciones: list[Condicion] = Field(default_factory=list)


class AsignarFamilia(_Cuerpo):
    familia_id: int | None = None
    ids: list[int] = Field(max_length=5000)


class AsignarCategoria(_Cuerpo):
    categoria_id: int | None = None
    ids: list[int] = Field(max_length=5000)


@router.get("/grupos-producto")
def listar(db: Db, user: User, incluir_inactivos: bool = True, clase: str | None = None):
    """Todas las familias y categorías en orden de árbol, con lo que las usa."""
    return familias.arbol(db, user, incluir_inactivos, clase.upper() if clase else None)


@router.get("/grupos-producto/campos")
def campos(db: Db, user: User):
    """Datos del catálogo con que se reconoce una categoría, y los operadores."""
    return familias.campos(db, user)


@router.get("/grupos-producto/categorias")
def categorias(db: Db, user: User, familia_id: int | None = None):
    """Las categorías (de una familia), con cuántos artículos caen en cada una."""
    return familias.categorias(db, user, familia_id)


@router.post("/grupos-producto/categorias/probar")
def probar(datos: Prueba, db: Db, user: User):
    """Qué artículos de la familia caerían en una categoría con estas condiciones (no guarda)."""
    return familias.probar(db, user, datos.model_dump(mode="json"))


@router.put("/grupos-producto/orden")
def ordenar(datos: Orden, db: Db, user: User):
    """El orden de las familias y categorías (el de la lista)."""
    return ejecutar(db, user, None, lambda: familias.ordenar(db, user, datos.ids))


@router.post("/grupos-producto/productos/familia")
def asignar_productos(datos: AsignarFamilia, db: Db, user: User):
    """Pone (o quita) la familia de esos productos."""
    return ejecutar(db, user, None, lambda: familias.asignar_productos(db, user, datos.familia_id, datos.ids))


@router.post("/grupos-producto/articulos/familia")
def asignar_articulos(datos: AsignarFamilia, db: Db, user: User):
    """Pone (o quita) la familia de los productos de esos artículos."""
    return ejecutar(db, user, None, lambda: familias.asignar_articulos(db, user, datos.familia_id, datos.ids))


@router.post("/grupos-producto/productos/categoria")
def asignar_categoria(datos: AsignarCategoria, db: Db, user: User):
    """Pone a mano la categoría de esos productos (o la quita: se reconoce sola)."""
    return ejecutar(db, user, None, lambda: familias.asignar_categoria(db, user, datos.categoria_id, datos.ids))


@router.post("/grupos-producto")
def crear(datos: GrupoIn, db: Db, user: User, clave: Clave = None):
    """Crea una familia (en la raíz o dentro de otra) o una categoría dentro de una familia."""
    return ejecutar(db, user, clave, lambda: familias.crear(db, user, datos.model_dump(mode="json")))


@router.patch("/grupos-producto/{grupo_id}")
def actualizar(grupo_id: int, datos: GrupoPatch, db: Db, user: User, clave: Clave = None):
    """Cambia el nombre, el lugar en el árbol, las condiciones, los atributos o si está activa."""
    return ejecutar(db, user, clave, lambda: familias.actualizar(db, user, grupo_id, datos.model_dump(mode="json",
                                                                                                       exclude_unset=True)))


@router.delete("/grupos-producto/{grupo_id}")
def eliminar(grupo_id: int, db: Db, user: User, clave: Clave = None):
    """Borra una familia o categoría sin uso; si algo la usa, hay que desactivarla."""
    return ejecutar(db, user, clave, lambda: familias.eliminar(db, user, grupo_id))


@router.get("/grupos-producto/{grupo_id}/secciones")
def secciones(grupo_id: int, db: Db, user: User):
    """Lo que cada módulo guarda de la familia (una pestaña por sección)."""
    return familias.leer_secciones(db, user, grupo_id)


@router.put("/grupos-producto/{grupo_id}/secciones/{clave_seccion}")
def guardar_seccion(grupo_id: int, clave_seccion: str, datos: dict, db: Db, user: User):
    """Guarda la sección de un módulo (sus datos los valida el módulo)."""
    return ejecutar(db, user, None, lambda: familias.guardar_seccion(db, user, grupo_id, clave_seccion, datos))
