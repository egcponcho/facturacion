from datetime import date

from fastapi import APIRouter, File, Query, Request, UploadFile

from .. import schemas as s
from ..services import aranceles as svc
from .base import Clave, Db, Formato, User, descarga, ejecutar, plantilla_o_vista

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
def sac_plantilla(user: User, vista: bool = False):
    return plantilla_o_vista(svc.plantilla_sac(), "template_sac", vista)


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


@router.get("/aranceles/condiciones")
def condiciones(db: Db, user: User, pais: str | None = None, codigo: str | None = None):
    """Condiciones que aplican a un código nacional según el país y la subpartida."""
    return svc.condiciones_aplicables(db, user, pais, codigo)


@router.get("/aranceles/notas")
def notas(request: Request, db: Db, user: User):
    """Notas legales del SAC que el sistema tiene en cuenta al clasificar."""
    return svc.listar_notas(db, user, dict(request.query_params))


@router.get("/aranceles/notas/plantilla")
def notas_plantilla(user: User, vista: bool = False):
    return plantilla_o_vista(svc.plantilla_notas(), "template_sac_notes", vista)


@router.get("/aranceles/notas/exportar")
def notas_exportar(request: Request, db: Db, user: User, formato: Formato = "xlsx"):
    return descarga(svc.exportar_notas(db, user, dict(request.query_params), formato), f"sac_notes_{date.today():%Y%m%d}", formato)


@router.post("/aranceles/notas/importar")
async def notas_importar(db: Db, user: User, archivo: UploadFile = File(...)):
    r = svc.importar_notas(db, user, archivo.filename or "", await archivo.read())
    db.commit()
    return r


@router.post("/aranceles/notas")
def crear_nota(datos: s.NotaSACIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_nota(db, user, datos))


@router.put("/aranceles/notas/{nota_id}")
def editar_nota(nota_id: int, datos: s.NotaSACIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_nota(db, user, datos, nota_id))


@router.delete("/aranceles/notas/{nota_id}")
def borrar_nota(nota_id: int, db: Db, user: User):
    svc.borrar_nota(db, user, nota_id)
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
def codigos_plantilla(db: Db, user: User, pais: str | None = None, vista: bool = False):
    return plantilla_o_vista(svc.plantilla_incisos(db, pais), f"template_national_codes{'_' + pais if pais else ''}", vista)


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


# ---- Capa oficial: fuentes, versiones, capítulos y dominios ------------------------
@router.get("/aranceles/oficial/fuentes")
def oficial_fuentes(db: Db, user: User):
    from ..services import oficial

    return oficial.fuentes_y_versiones(db, user)


@router.get("/aranceles/oficial/capitulos")
def oficial_capitulos(db: Db, user: User, q: str | None = None, estado: str | None = None, dominio: str | None = None):
    from ..services import oficial

    return oficial.capitulos(db, user, q, estado, dominio)


@router.patch("/aranceles/oficial/capitulos")
def oficial_capitulos_editar(datos: s.CapitulosPatch, db: Db, user: User, clave: Clave = None):
    from ..services import oficial

    return ejecutar(db, user, clave, lambda: oficial.actualizar_capitulos(
        db, user, datos.ids, datos.model_dump(exclude={"ids"})))


@router.get("/aranceles/oficial/dominios")
def oficial_dominios(db: Db, user: User):
    from ..services import oficial

    return oficial.dominios(db, user)


@router.put("/aranceles/oficial/dominios/{dominio_id}/capitulos/{capitulo}")
def oficial_dominio_capitulo(dominio_id: int, capitulo: str, datos: s.DominioCapituloIn, db: Db, user: User,
                             clave: Clave = None):
    from ..services import oficial

    return ejecutar(db, user, clave, lambda: oficial.guardar_dominio_capitulo(
        db, user, dominio_id, capitulo, datos.relevancia, datos.habilitado, datos.quitar))


@router.get("/aranceles/oficial/paquete/{numero}")
def oficial_paquete(numero: int, user: User, vista: bool = False):
    """Descarga el paquete Excel oficial incluido (01 catálogos, 02 motor, 03 nacional)."""
    from ..services import oficial

    nombre = next((n for n in sorted(p.name for p in oficial.CARPETA.iterdir() if p.suffix == ".xlsx") if n.startswith(f"{numero:02d}_")), None)
    if not nombre:
        from ..services.common import ErrorNegocio

        raise ErrorNegocio("The package does not exist.", 404, "no_encontrado")
    return plantilla_o_vista((oficial.CARPETA / nombre).read_bytes(), nombre[:-5], vista)


@router.post("/aranceles/oficial/importar")
async def oficial_importar(db: Db, user: User, archivo: UploadFile = File(...)):
    """Carga un paquete oficial (Sources, Versions, Countries, Chapter_Control, Domains, Domain_Chapter_Map)."""
    from ..services import oficial
    from ..services.common import exigir

    exigir(user, "aranceles.editar")
    r = oficial.importar(db, await archivo.read(), user, archivo.filename or "")
    db.commit()
    return r
