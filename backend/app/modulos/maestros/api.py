from fastapi import APIRouter, Body, File, Query, Request, UploadFile

from app import esquemas as s
from app.modulos.comun import tabla
from app.modulos.maestros import cargas, genericos, versiones
from app.modulos.maestros import catalogos as svc
from app.web.rutas import Clave, Db, Formato, User, descarga, ejecutar, leer_subida, plantilla_o_vista

router = APIRouter(prefix="/catalogos")
# `f` son los filtros por columna (app/modulos/comun/tabla.py); `columna` y
# `buscar`, los de la ruta de valores de una columna
RESERVADOS = {"q", "orden", "page", "size", "f", "columna", "buscar"}


def _filtros(request: Request, *quitar: str) -> dict:
    """Filtros por campo de la pantalla: los parámetros que no son de la tabla."""
    return {k: v for k, v in request.query_params.items() if k not in RESERVADOS | set(quitar)}


@router.get("")
def meta(db: Db, user: User):
    """Catálogos de datos maestros con sus campos, total de registros, gobierno y acciones permitidas."""
    return svc.meta(db, user)


@router.post("/genericos")
def crear_generico(datos: s.GenericoIn, db: Db, user: User, clave: Clave = None):
    """Producto nuevo con su núcleo, sus atributos y, si vienen, sus variantes."""
    return ejecutar(db, user, clave, lambda: genericos.crear(db, user, datos))


@router.get("/genericos")
def genericos_lista(request: Request, db: Db, user: User, orden: str | None = None, page: int = Query(1, ge=1),
                    size: int = Query(25, ge=1, le=200), f: str | None = None):
    """Artículos agrupados por producto (un renglón con sus variantes), con filtros, filtros por columna, orden y paginación."""
    filtros = {k: v for k, v in _filtros(request).items() if v != ""}
    if request.query_params.get("q"):
        filtros["q"] = request.query_params["q"]
    return genericos.listar(db, user, filtros, orden, page, size, tabla.leer(f))


@router.get("/genericos/valores")
def genericos_valores(request: Request, db: Db, user: User, columna: str, buscar: str | None = None, f: str | None = None):
    """Valores únicos de una columna de la vista por producto (con cuántos productos tienen cada uno) bajo los demás filtros."""
    filtros = {k: v for k, v in _filtros(request).items() if v != ""}
    if request.query_params.get("q"):
        filtros["q"] = request.query_params["q"]
    return genericos.valores(db, user, columna, buscar, tabla.leer(f), filtros)


@router.put("/genericos/{gen}")
def editar_generico(gen: str, datos: s.GenericoEditIn, db: Db, user: User, clave: Clave = None):
    """Cambia el núcleo y los atributos de un producto (los comparten todas sus variantes)."""
    return ejecutar(db, user, clave, lambda: genericos.editar(db, user, gen, datos))


@router.get("/genericos/{gen}")
def generico(gen: str, db: Db, user: User):
    """Producto con sus atributos, sus variantes y el siguiente sufijo de código libre."""
    return genericos.detalle(db, user, gen)


@router.post("/genericos/{gen}/variantes")
def agregar_variantes(gen: str, datos: s.VariantesIn, db: Db, user: User, clave: Clave = None):
    """Agrega variantes a un producto, escritas o combinadas, y devuelve el producto."""
    def hacer():
        genericos.agregar_variantes(db, user, gen, datos.variantes, datos.escala_id, datos.combinar)
        return genericos.detalle(db, user, gen)
    return ejecutar(db, user, clave, hacer)


@router.get("/escalas/{escala_id}/valores")
def valores_escala(escala_id: int, db: Db, user: User):
    """Valores de una escala con el código que tendrá cada uno."""
    from app.core.errores import ErrorNegocio
    from app.modelos import EscalaValores
    from app.modulos.acceso.permisos import exigir
    from app.modulos.maestros import escalas

    exigir(user, "catalogos.ver")
    e = db.get(EscalaValores, escala_id)
    if not e:
        raise ErrorNegocio("The value scale does not exist.", 404, "no_encontrado")
    return {"id": e.id, "codigo": e.codigo, "nombre": e.nombre, "atributo": e.atributo, "valores": escalas.con_codigos(e)}


@router.post("/{tipo}/importar")
async def importar(tipo: str, db: Db, user: User, archivo: UploadFile = File(...)):
    """Productos y variantes, packs y kits o cualquier catálogo desde Excel o CSV."""
    res = cargas.importar_catalogo(db, user, tipo, archivo.filename or "datos.csv", await leer_subida(archivo))
    db.commit()
    return res


@router.get("/{tipo}/plantilla")
def plantilla(tipo: str, db: Db, user: User, vista: bool = False):
    """Plantilla Excel para cargar un catálogo; con vista=1, su vista previa en JSON."""
    return plantilla_o_vista(cargas.plantilla_catalogo(db, user, tipo), f"template_{tipo}", vista)


@router.get("/{tipo}/exportar")
def exportar(tipo: str, request: Request, db: Db, user: User, q: str | None = None, orden: str | None = None,
             formato: Formato = "xlsx", f: str | None = None):
    """Exporta un catálogo en Excel o PDF con la búsqueda, los filtros (también los de cada columna) y el orden de la pantalla."""
    filtros = _filtros(request, "formato")
    return descarga(cargas.exportar_catalogo(db, user, tipo, q, filtros, orden, formato, tabla.leer(f)), f"{tipo}", formato)


@router.post("/compuestos")
def crear_compuesto(db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Pack o kit nuevo: su código de artículo y su contenido (variantes y cantidades), que ya no cambia."""
    return ejecutar(db, user, clave, lambda: svc.crear_compuesto(db, user, datos))


@router.get("/compuestos/{articulo_id}/componentes")
def componentes(articulo_id: int, db: Db, user: User):
    """Contenido de un pack o un kit (variante y cantidad) con su total."""
    return svc.componentes(db, user, articulo_id)


@router.get("/articulos/{articulo_id}/versiones")
def versiones_articulo(articulo_id: int, db: Db, user: User):
    """Versiones del artículo: cómo era cuando cada OC o factura lo usó y qué cambió de una a otra."""
    return versiones.listar(db, user, articulo_id)


@router.get("/explosion/{sku}")
def explosion(sku: str, db: Db, user: User):
    """Contenido de un pack o un kit, de solo lectura. Requiere el permiso oc.ver."""
    return svc.explosion(db, user, sku)


@router.get("/{tipo}/valores")
def valores(tipo: str, request: Request, db: Db, user: User, columna: str, buscar: str | None = None, q: str | None = None,
            f: str | None = None):
    """Valores únicos de una columna de un catálogo (con cuántos registros tienen cada uno) bajo los demás filtros."""
    return svc.valores(db, user, tipo, columna, buscar, tabla.leer(f), q, _filtros(request))


@router.get("/{tipo}/opciones")
def opciones(tipo: str, db: Db, user: User):
    """Lista corta (id, código, texto) de un catálogo para selects y filtros."""
    return svc.opciones(db, user, tipo)


@router.get("/{tipo}")
def listar(tipo: str, request: Request, db: Db, user: User, q: str | None = None, orden: str | None = None,
           page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200), f: str | None = None):
    """Registros de un catálogo con búsqueda, filtros por campo y por columna, orden y paginación."""
    return svc.listar(db, user, tipo, q, _filtros(request), orden, page, size, tabla.leer(f))


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
