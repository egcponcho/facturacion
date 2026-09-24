from fastapi import APIRouter, File, Query, UploadFile

from ..services import ordenes as svc
from .base import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/ordenes")
def listar(
    db: Db,
    user: User,
    proveedor_id: int | None = None,
    q: str | None = None,
    centro: str | None = None,
    solo_disponible: bool = True,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    return svc.listar_ordenes(db, user, proveedor_id, q, centro, solo_disponible, page, size)


@router.get("/ordenes/{oc_id}/posiciones")
def posiciones(oc_id: int, db: Db, user: User):
    return svc.posiciones_oc(db, user, oc_id)


@router.post("/ordenes/importar/previa")
async def importar_previa(db: Db, user: User, archivo: UploadFile = File(...)):
    contenido = await archivo.read()
    res = svc.importar_previa(db, user, archivo.filename or "archivo.csv", contenido)
    db.commit()
    return res


@router.post("/ordenes/importar/{importacion_id}/aplicar")
def importar_aplicar(importacion_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.importar_aplicar(db, user, importacion_id))
