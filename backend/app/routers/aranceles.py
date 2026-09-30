from datetime import date

from fastapi import APIRouter, File, Query, Request, UploadFile

from .. import schemas as s
from ..services import aranceles as svc
from .base import Clave, Db, Formato, User, descarga, ejecutar

router = APIRouter()
XLSX = "xlsx"


def _filtros(request: Request, claves: tuple) -> dict:
    return {k: v for k, v in request.query_params.items() if k in claves and v != ""}


F_INC = ("pais", "q", "capitulo", "fuente", "activo")
F_SAC = ("q", "capitulo", "nivel", "fuente")


@router.get("/aranceles/opciones")
def opciones(db: Db, user: User):
    return svc.opciones(db, user)


@router.get("/aranceles/paises")
def paises(db: Db, user: User):
    return svc.paises(db, user)


@router.post("/aranceles/paises")
def crear_pais(datos: s.PaisArancelIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_pais(db, user, datos))


@router.put("/aranceles/paises/{pais_id}")
def editar_pais(pais_id: int, datos: s.PaisArancelIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_pais(db, user, datos, pais_id))


@router.delete("/aranceles/paises/{pais_id}")
def borrar_pais(pais_id: int, db: Db, user: User):
    svc.borrar_pais(db, user, pais_id)
    db.commit()
    return {"ok": True}


@router.get("/aranceles/sac")
def sac(request: Request, db: Db, user: User, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500)):
    return svc.listar_sac(db, user, _filtros(request, F_SAC), page, size)


@router.get("/aranceles/sac/exportar")
def sac_exportar(request: Request, db: Db, user: User, formato: Formato = "xlsx"):
    return descarga(svc.exportar_sac(db, user, _filtros(request, F_SAC), formato), f"sac_{date.today():%Y%m%d}", formato)


@router.get("/aranceles/sac/plantilla")
def sac_plantilla(user: User):
    return descarga(svc.plantilla_sac(), "template_sac", XLSX)


@router.post("/aranceles/sac/importar")
async def sac_importar(db: Db, user: User, archivo: UploadFile = File(...)):
    r = svc.importar_sac(db, user, archivo.filename or "", await archivo.read())
    db.commit()
    return r


@router.post("/aranceles/sac")
def crear_sac(datos: s.PartidaSACIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_sac(db, user, datos))


@router.put("/aranceles/sac/{sac_id}")
def editar_sac(sac_id: int, datos: s.PartidaSACIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_sac(db, user, datos, sac_id))


@router.delete("/aranceles/sac/{sac_id}")
def borrar_sac(sac_id: int, db: Db, user: User):
    svc.borrar_sac(db, user, sac_id)
    db.commit()
    return {"ok": True}


@router.get("/aranceles/codigos")
def codigos(request: Request, db: Db, user: User, orden: str | None = None, page: int = Query(1, ge=1),
            size: int = Query(50, ge=1, le=500)):
    return svc.listar_incisos(db, user, _filtros(request, F_INC), page, size, orden)


@router.get("/aranceles/codigos/exportar")
def codigos_exportar(request: Request, db: Db, user: User, orden: str | None = None, formato: Formato = "xlsx"):
    return descarga(svc.exportar_incisos(db, user, _filtros(request, F_INC), orden, formato),
                    f"national_codes_{date.today():%Y%m%d}", formato)


@router.get("/aranceles/codigos/plantilla")
def codigos_plantilla(db: Db, user: User, pais: str | None = None):
    return descarga(svc.plantilla_incisos(db, pais), f"template_national_codes{'_' + pais if pais else ''}", XLSX)


@router.post("/aranceles/codigos/importar")
async def codigos_importar(db: Db, user: User, archivo: UploadFile = File(...), pais: str | None = None,
                           reemplazar: bool = False):
    r = svc.importar_incisos(db, user, archivo.filename or "", await archivo.read(), pais, reemplazar)
    db.commit()
    return r


@router.post("/aranceles/codigos")
def crear_codigo(datos: s.IncisoEditIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_inciso(db, user, datos))


@router.put("/aranceles/codigos/{inciso_id}")
def editar_codigo(inciso_id: int, datos: s.IncisoEditIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_inciso(db, user, datos, inciso_id))


@router.post("/aranceles/codigos/borrar")
def borrar_codigos(datos: s.IdsIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.borrar_incisos(db, user, datos.ids))
