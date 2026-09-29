from fastapi import APIRouter, Body, File, Query, Request, UploadFile

from ..services import catalogos as svc
from .base import Clave, Db, User, ejecutar

router = APIRouter(prefix="/catalogos")
RESERVADOS = {"q", "orden", "page", "size"}


@router.get("")
def meta(db: Db, user: User):
    return svc.meta(db, user)


@router.post("/articulos/importar")
async def importar_articulos(db: Db, user: User, archivo: UploadFile = File(...)):
    res = svc.importar_articulos(db, user, archivo.filename or "articulos.csv", await archivo.read())
    db.commit()
    return res


@router.post("/prepacks/importar")
async def importar_prepacks(db: Db, user: User, archivo: UploadFile = File(...)):
    res = svc.importar_prepacks(db, user, archivo.filename or "prepacks.csv", await archivo.read())
    db.commit()
    return res


@router.get("/prepacks/{prepack_id}/componentes")
def componentes(prepack_id: int, db: Db, user: User):
    return svc.componentes(db, user, prepack_id)


@router.put("/prepacks/{prepack_id}/componentes")
def guardar_componentes(prepack_id: int, db: Db, user: User, items: list[dict] = Body(...), clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_componentes(db, user, prepack_id, items))


@router.get("/{tipo}/opciones")
def opciones(tipo: str, db: Db, user: User):
    return svc.opciones(db, user, tipo)


@router.get("/{tipo}")
def listar(tipo: str, request: Request, db: Db, user: User, q: str | None = None, orden: str | None = None,
           page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    filtros = {k: v for k, v in request.query_params.items() if k not in RESERVADOS}
    return svc.listar(db, user, tipo, q, filtros, orden, page, size)


@router.post("/{tipo}")
def crear(tipo: str, db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.crear(db, user, tipo, datos))


@router.patch("/{tipo}/{obj_id}")
def actualizar(tipo: str, obj_id: int, db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.actualizar(db, user, tipo, obj_id, datos))


@router.delete("/{tipo}/{obj_id}")
def eliminar(tipo: str, obj_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.eliminar(db, user, tipo, obj_id))
