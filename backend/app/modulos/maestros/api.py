from fastapi import APIRouter, Body, File, Query, Request, UploadFile

from app import esquemas as s
from app.modulos.maestros import cargas, genericos
from app.modulos.maestros import catalogos as svc
from app.web.rutas import Clave, Db, Formato, User, descarga, ejecutar, leer_subida, plantilla_o_vista

router = APIRouter(prefix="/catalogos")
RESERVADOS = {"q", "orden", "page", "size"}


@router.get("")
def meta(db: Db, user: User):
    """Catálogos de datos maestros con sus campos, total de registros, gobierno y acciones permitidas."""
    return svc.meta(db, user)


@router.post("/genericos")
def crear_generico(datos: s.GenericoIn, db: Db, user: User, clave: Clave = None):
    """Genérico (8 dígitos) con sus datos maestros y sus tallas."""
    return ejecutar(db, user, clave, lambda: genericos.crear(db, user, datos))


@router.get("/genericos")
def genericos_lista(request: Request, db: Db, user: User, orden: str | None = None, page: int = Query(1, ge=1),
                    size: int = Query(25, ge=1, le=200)):
    """Artículos agrupados por genérico (un renglón con sus tallas), con filtros, orden y paginación."""
    filtros = {k: v for k, v in request.query_params.items() if k not in RESERVADOS and v != ""}
    if request.query_params.get("q"):
        filtros["q"] = request.query_params["q"]
    return genericos.listar(db, user, filtros, orden, page, size)


@router.put("/genericos/{gen}")
def editar_generico(gen: str, datos: s.GenericoEditIn, db: Db, user: User, clave: Clave = None):
    """Cambia los datos maestros de un genérico y los pasa a todas sus tallas."""
    return ejecutar(db, user, clave, lambda: genericos.editar(db, user, gen, datos))


@router.get("/genericos/{gen}")
def generico(gen: str, db: Db, user: User):
    """Genérico con sus datos maestros, sus tallas y el siguiente sufijo de código libre."""
    return genericos.detalle(db, user, gen)


@router.post("/genericos/{gen}/tallas")
def agregar_tallas(gen: str, datos: s.TallasIn, db: Db, user: User, clave: Clave = None):
    """Agrega tallas a un genérico (heredan sus datos maestros) y devuelve el genérico actualizado."""
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
    res = cargas.importar_catalogo(db, user, tipo, archivo.filename or "datos.csv", await leer_subida(archivo))
    db.commit()
    return res


@router.get("/{tipo}/plantilla")
def plantilla(tipo: str, db: Db, user: User, vista: bool = False):
    """Plantilla Excel para cargar un catálogo; con vista=1, su vista previa en JSON."""
    return plantilla_o_vista(cargas.plantilla_catalogo(db, user, tipo), f"template_{tipo}", vista)


@router.get("/{tipo}/exportar")
def exportar(tipo: str, request: Request, db: Db, user: User, q: str | None = None, orden: str | None = None,
             formato: Formato = "xlsx"):
    """Exporta un catálogo en Excel o PDF con la búsqueda, los filtros y el orden de la pantalla."""
    filtros = {k: v for k, v in request.query_params.items() if k not in RESERVADOS | {"formato"}}
    return descarga(cargas.exportar_catalogo(db, user, tipo, q, filtros, orden, formato), f"{tipo}", formato)


@router.get("/prepacks/{prepack_id}/componentes")
def componentes(prepack_id: int, db: Db, user: User):
    """Componentes de un prepack (artículo, talla y cantidad) con su total."""
    return svc.componentes(db, user, prepack_id)


@router.get("/explosion/{sku}")
def explosion(sku: str, db: Db, user: User):
    """Explosión de un artículo prepack en sus componentes, de solo lectura. Requiere el permiso oc.ver."""
    return svc.explosion(db, user, sku)


@router.get("/{tipo}/opciones")
def opciones(tipo: str, db: Db, user: User):
    """Lista corta (id, código, texto) de un catálogo para selects y filtros."""
    return svc.opciones(db, user, tipo)


@router.get("/{tipo}")
def listar(tipo: str, request: Request, db: Db, user: User, q: str | None = None, orden: str | None = None,
           page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    """Registros de un catálogo con búsqueda, filtros por campo, orden y paginación."""
    filtros = {k: v for k, v in request.query_params.items() if k not in RESERVADOS}
    return svc.listar(db, user, tipo, q, filtros, orden, page, size)


@router.post("/{tipo}")
def crear(tipo: str, db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Crea un registro del catálogo; si tiene responsables, solo ellos o la administración pueden hacerlo."""
    return ejecutar(db, user, clave, lambda: svc.crear(db, user, tipo, datos))


@router.patch("/{tipo}/{obj_id}")
def actualizar(tipo: str, obj_id: int, db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Cambia un registro del catálogo y deja en su historial qué cambió."""
    return ejecutar(db, user, clave, lambda: svc.actualizar(db, user, tipo, obj_id, datos))


@router.delete("/{tipo}/{obj_id}")
def eliminar(tipo: str, obj_id: int, db: Db, user: User, clave: Clave = None):
    """Elimina un registro que ningún documento usa; si está en uso, se debe desactivar."""
    return ejecutar(db, user, clave, lambda: svc.eliminar(db, user, tipo, obj_id))


@router.get("/{tipo}/{obj_id}/historial")
def historial(tipo: str, obj_id: int, db: Db, user: User):
    """Quién cambió el registro, cuándo y qué."""
    return svc.historial(db, user, tipo, obj_id)


@router.put("/{tipo}/gobierno")
def gobierno(tipo: str, db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Responsables del catálogo y datos que la empresa vuelve obligatorios."""
    return ejecutar(db, user, clave, lambda: svc.guardar_gobierno(db, user, tipo, datos))
