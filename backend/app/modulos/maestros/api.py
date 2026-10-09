from fastapi import APIRouter, Body, File, Query, Request, UploadFile

from app import esquemas as s
from app.core.api import Clave, Db, Formato, User, descarga, ejecutar, plantilla_o_vista
from app.modulos.maestros import cargas, genericos
from app.modulos.maestros import catalogos as svc

router = APIRouter(prefix="/catalogos")
RESERVADOS = {"q", "orden", "page", "size"}


@router.get("")
def meta(db: Db, user: User):
    return svc.meta(db, user)


@router.post("/genericos")
def crear_generico(datos: s.GenericoIn, db: Db, user: User, clave: Clave = None):
    """Genérico (8 dígitos) con sus datos maestros y sus tallas."""
    return ejecutar(db, user, clave, lambda: genericos.crear(db, user, datos))


@router.get("/genericos")
def genericos_lista(request: Request, db: Db, user: User, orden: str | None = None, page: int = Query(1, ge=1),
                    size: int = Query(25, ge=1, le=200)):
    filtros = {k: v for k, v in request.query_params.items() if k not in RESERVADOS and v != ""}
    if request.query_params.get("q"):
        filtros["q"] = request.query_params["q"]
    return genericos.listar(db, user, filtros, orden, page, size)


@router.put("/genericos/{gen}")
def editar_generico(gen: str, datos: s.GenericoEditIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: genericos.editar(db, user, gen, datos))


@router.get("/genericos/{gen}")
def generico(gen: str, db: Db, user: User):
    return genericos.detalle(db, user, gen)


@router.post("/genericos/{gen}/tallas")
def agregar_tallas(gen: str, datos: s.TallasIn, db: Db, user: User, clave: Clave = None):
    def hacer():
        genericos.agregar_tallas(db, user, gen, datos.tallas, datos.escala_id)
        return genericos.detalle(db, user, gen)
    return ejecutar(db, user, clave, hacer)


@router.get("/escalas/{escala_id}/tallas")
def tallas_escala(escala_id: int, db: Db, user: User):
    """Tallas de una escala con el código que tendrá cada una."""
    from app.core.errores import ErrorNegocio
    from app.modelos import EscalaTalla
    from app.modulos.acceso.permisos import exigir
    from app.modulos.maestros import tallas as tallas_svc

    exigir(user, "catalogos.ver")
    e = db.get(EscalaTalla, escala_id)
    if not e:
        raise ErrorNegocio("The size scale does not exist.", 404, "no_encontrado")
    return {"id": e.id, "codigo": e.codigo, "nombre": e.nombre, "tallas": tallas_svc.con_codigos(e)}


@router.post("/{tipo}/importar")
async def importar(tipo: str, db: Db, user: User, archivo: UploadFile = File(...)):
    """Artículos (con su ficha técnica), prepacks o cualquier catálogo desde Excel o CSV."""
    res = cargas.importar_catalogo(db, user, tipo, archivo.filename or "datos.csv", await archivo.read())
    db.commit()
    return res


@router.get("/{tipo}/plantilla")
def plantilla(tipo: str, db: Db, user: User, vista: bool = False):
    return plantilla_o_vista(cargas.plantilla_catalogo(db, user, tipo), f"template_{tipo}", vista)


@router.get("/{tipo}/exportar")
def exportar(tipo: str, request: Request, db: Db, user: User, q: str | None = None, orden: str | None = None,
             formato: Formato = "xlsx"):
    filtros = {k: v for k, v in request.query_params.items() if k not in RESERVADOS | {"formato"}}
    return descarga(cargas.exportar_catalogo(db, user, tipo, q, filtros, orden, formato), f"{tipo}", formato)


@router.get("/prepacks/{prepack_id}/componentes")
def componentes(prepack_id: int, db: Db, user: User):
    return svc.componentes(db, user, prepack_id)


@router.get("/explosion/{sku}")
def explosion(sku: str, db: Db, user: User):
    return svc.explosion(db, user, sku)


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
