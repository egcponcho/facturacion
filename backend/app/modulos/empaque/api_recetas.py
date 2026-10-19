"""Rutas de las recetas de empaque y las reglas de empaque.
"""
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.modulos.empaque import recetas
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


class _Cuerpo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NivelIn(_Cuerpo):
    tipo_empaque_id: int | None = None
    cantidad: int | float | str | None = None
    largo: float | None = None
    ancho: float | None = None
    alto: float | None = None
    tara: float | None = None
    opcional: bool = False


class RecetaIn(_Cuerpo):
    codigo: str
    nombre: str
    descripcion: str | None = None
    niveles: list[NivelIn]


class RecetaPatch(_Cuerpo):
    codigo: str | None = None
    nombre: str | None = None
    descripcion: str | None = None
    activa: bool | None = None
    niveles: list[NivelIn] | None = None
    version: int | None = None


class CalcularIn(_Cuerpo):
    niveles: list[NivelIn]
    articulo_id: int | None = None


class Condicion(_Cuerpo):
    campo: str
    op: str
    valor: str | int | float | list | None = None


class ReglaIn(_Cuerpo):
    id: int | None = None  # al probar o medir una regla en edición
    receta_id: int | None = None
    destino: str = "EMPRESA"
    familia_id: int | None = None
    producto_id: int | None = None
    articulo_id: int | None = None
    condiciones: list[Condicion] = Field(default_factory=list)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None
    motivo: str | None = None
    activa: bool = True
    version: int | None = None
    aplicar: bool = False  # al guardar: aplicarla a las posiciones abiertas que siguen a las reglas


class OrdenIn(_Cuerpo):
    ids: list[int]


class ProbarIn(_Cuerpo):
    oc_id: int
    regla: ReglaIn | None = None


class ImpactoIn(_Cuerpo):
    regla: ReglaIn | None = None
    quitar: int | None = None


class ReaplicarIn(_Cuerpo):
    oc_id: int | None = None


class RecetaPosicionIn(_Cuerpo):
    receta_id: int | None = None  # sin receta: la que digan las reglas


def _d(m: BaseModel | None) -> dict | None:
    return m.model_dump(mode="json", exclude_unset=True) if m is not None else None


# ---- Recetas ------------------------------------------------------------------
@router.get("/recetas-empaque")
def listar_recetas(db: Db, user: User, incluir_inactivas: bool = False):
    """Recetas de empaque con su forma (niveles y unidades) y dónde se usan."""
    return recetas.listar_recetas(db, user, incluir_inactivas)


@router.post("/recetas-empaque/calcular")
def calcular(datos: CalcularIn, db: Db, user: User):
    """Totales de cada nivel de una receta sin guardar: unidades, volumen, tara y, con un artículo, pesos."""
    from app.modulos.acceso.permisos import exigir_alguno

    exigir_alguno(user, "catalogos.ver", "oc.empaque")
    return recetas.calcular(db, [n.model_dump() for n in datos.niveles], datos.articulo_id)


@router.post("/recetas-empaque")
def crear_receta(datos: RecetaIn, db: Db, user: User, clave: Clave = None):
    """Crea una receta: código único y niveles del más interno al más externo."""
    return ejecutar(db, user, clave, lambda: recetas.crear_receta(db, user, _d(datos)))


@router.get("/recetas-empaque/{receta_id}")
def receta(receta_id: int, db: Db, user: User):
    """Una receta con sus niveles y dónde se usa."""
    return recetas.detalle_receta(db, user, receta_id)


@router.patch("/recetas-empaque/{receta_id}")
def actualizar_receta(receta_id: int, datos: RecetaPatch, db: Db, user: User, clave: Clave = None):
    """Cambia una receta; las posiciones que ya la usan conservan su foto."""
    return ejecutar(db, user, clave, lambda: recetas.actualizar_receta(db, user, receta_id, _d(datos)))


@router.delete("/recetas-empaque/{receta_id}")
def eliminar_receta(receta_id: int, db: Db, user: User, clave: Clave = None):
    """Borra una receta sin uso; si está en uso, la desactiva."""
    return ejecutar(db, user, clave, lambda: recetas.eliminar_receta(db, user, receta_id))


# ---- Reglas -------------------------------------------------------------------
@router.get("/reglas-empaque")
def listar_reglas(db: Db, user: User):
    """Reglas de empaque en el orden de la lista."""
    return recetas.listar_reglas(db, user)


@router.get("/reglas-empaque/campos")
def campos_reglas(db: Db, user: User):
    """Datos que pueden usar las condiciones, operadores, destinos y familias."""
    return recetas.catalogo_campos(db, user)


@router.post("/reglas-empaque")
def crear_regla(datos: ReglaIn, db: Db, user: User, clave: Clave = None):
    """Crea una regla «para [destino] si [condiciones] → usar [receta]» al final de la lista."""
    return ejecutar(db, user, clave, lambda: recetas.crear_regla(db, user, _d(datos)))


@router.put("/reglas-empaque/orden")
def ordenar_reglas(datos: OrdenIn, db: Db, user: User, clave: Clave = None):
    """Nuevo orden de la lista (decide solo entre reglas igual de específicas)."""
    return ejecutar(db, user, clave, lambda: recetas.ordenar_reglas(db, user, datos.ids))


@router.post("/reglas-empaque/probar")
def probar(datos: ProbarIn, db: Db, user: User):
    """Receta de cada posición de una OC hoy y según las reglas (con la regla en edición), regla por regla."""
    return recetas.probar(db, user, datos.oc_id, _d(datos.regla))


@router.post("/reglas-empaque/impacto")
def impacto(datos: ImpactoIn, db: Db, user: User):
    """Cuántas posiciones abiertas cambiarían de receta al guardar (o dar de baja) una regla."""
    return recetas.impacto(db, user, _d(datos.regla), datos.quitar)


@router.post("/reglas-empaque/reaplicar")
def reaplicar(datos: ReaplicarIn, db: Db, user: User, clave: Clave = None):
    """Aplica las reglas a las posiciones abiertas sin facturar que siguen a las reglas."""
    return ejecutar(db, user, clave, lambda: {"cambiaron": recetas.reaplicar(db, user, datos.oc_id)})


@router.patch("/reglas-empaque/{regla_id}")
def actualizar_regla(regla_id: int, datos: ReglaIn, db: Db, user: User, clave: Clave = None):
    """Cambia una regla (destino, condiciones, receta, vigencia o motivo); queda en el historial."""
    return ejecutar(db, user, clave, lambda: recetas.actualizar_regla(db, user, regla_id, _d(datos)))


@router.delete("/reglas-empaque/{regla_id}")
def eliminar_regla(regla_id: int, db: Db, user: User, aplicar: bool = False, clave: Clave = None):
    """Da de baja una regla (queda en el historial)."""
    return ejecutar(db, user, clave, lambda: recetas.eliminar_regla(db, user, regla_id, aplicar))


# ---- Posición de OC -----------------------------------------------------------
@router.put("/ordenes/{oc_id}/posiciones/{posicion_id}/receta")
def receta_posicion(oc_id: int, posicion_id: int, datos: RecetaPosicionIn, db: Db, user: User, clave: Clave = None):
    """Elige a mano la receta de una posición, o la devuelve a las reglas (sin receta)."""
    return ejecutar(db, user, clave, lambda: recetas.elegir_en_posicion(db, user, oc_id, posicion_id, datos.receta_id))
