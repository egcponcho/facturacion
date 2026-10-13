from fastapi import APIRouter

from app.esquemas import CierreRecepcionIn, RecepcionSinConteoIn, RecepcionUnidadIn
from app.modulos.recepcion import existencias as inv
from app.modulos.recepcion import recepcion as svc
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/unidades/{unidad_id}/recepcion")
def recepcion(unidad_id: int, db: Db, user: User):
    """Recepción de una unidad de carga: líneas con lo enviado, recibido, dañado y pendiente, sus registros,
    las bodegas donde se puede recibir y qué acciones se pueden hacer (y por qué no)."""
    return svc.detalle(db, user, unidad_id)


@router.post("/unidades/{unidad_id}/recepcion")
def registrar(unidad_id: int, datos: RecepcionUnidadIn, db: Db, user: User, clave: Clave = None):
    """Registra un conteo (parcial o completo) o un ajuste con motivo, en una bodega y con la fecha en que se
    recibió. Al completar lo enviado, la unidad queda recibida."""
    return ejecutar(db, user, clave, lambda: svc.registrar_conteo(db, user, unidad_id, datos))


@router.post("/unidades/{unidad_id}/recepcion/sin-conteo")
def sin_conteo(unidad_id: int, datos: RecepcionSinConteoIn, db: Db, user: User, clave: Clave = None):
    """Confirma lo pendiente de la unidad como recibido completo, sin conteo; queda quién lo hizo."""
    return ejecutar(db, user, clave, lambda: svc.confirmar_sin_conteo(db, user, unidad_id, datos))


@router.post("/unidades/{unidad_id}/recepcion/cerrar")
def cerrar(unidad_id: int, datos: CierreRecepcionIn, db: Db, user: User, clave: Clave = None):
    """Termina la recepción de la unidad; lo que falta queda como faltante (con motivo) y abre su alerta."""
    return ejecutar(db, user, clave, lambda: svc.cerrar(db, user, unidad_id, datos))


@router.get("/existencias")
def existencias(db: Db, user: User, centro: str | None = None, q: str | None = None, proveedor_id: int | None = None):
    """Existencias por bodega y artículo, según las recepciones: recibido, dañado y disponible."""
    return inv.existencias(db, user, centro, q, proveedor_id)


@router.get("/existencias/movimientos")
def movimientos(centro: str, codigo: str, db: Db, user: User, talla: str | None = None, almacen: str | None = None):
    """Ingresos de un artículo en una bodega (kardex): fecha, contenedor, embarque, PL y cantidades."""
    return inv.movimientos(db, user, centro, codigo, talla, almacen)
