from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from app.esquemas import (
    ConMotivo,
    FacturaAgregar,
    FacturaCabecera,
    FacturaCrear,
    FacturaEditarLineas,
    FacturaEliminarLineas,
    Finalizar,
    PLCrear,
)
from app.modulos.documentos import documentos, exportar
from app.modulos.empaque import packing
from app.modulos.facturacion import facturas as svc
from app.web.rutas import Clave, Db, Formato, User, descarga, ejecutar, leer_subida

router = APIRouter()


@router.get("/facturas")
def listar(
    db: Db,
    user: User,
    proveedor_id: int | None = None,
    estado: str | None = None,
    q: str | None = None,
    vista: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
    orden: str | None = None,
):
    """Facturas visibles, paginadas y filtrables (estado, texto, vista), con su avance en listas de empaque."""
    return svc.listar_facturas(db, user, proveedor_id, estado, q, vista, page, size, orden)


@router.post("/facturas")
def crear(datos: FacturaCrear, db: Db, user: User, clave: Clave = None):
    """Crea una factura en borrador con posiciones de OCs aprobadas y liberadas de un solo proveedor."""
    return ejecutar(db, user, clave, lambda: svc.crear_factura(db, user, datos))


@router.get("/facturas/{factura_id}")
def detalle(factura_id: int, db: Db, user: User):
    """Detalle de la factura: líneas, cantidades en PL, datos pendientes y acciones permitidas al usuario."""
    return svc.detalle_factura(db, user, factura_id)


@router.patch("/facturas/{factura_id}")
def cabecera(factura_id: int, datos: FacturaCabecera, db: Db, user: User, clave: Clave = None):
    """Modifica la cabecera de una factura en borrador o en corrección (número, fecha, incoterm…)."""
    return ejecutar(db, user, clave, lambda: svc.actualizar_cabecera(db, user, factura_id, datos))


@router.post("/facturas/{factura_id}/lineas")
def agregar(factura_id: int, datos: FacturaAgregar, db: Db, user: User, clave: Clave = None):
    """Agrega posiciones de OC a una factura en borrador o en corrección; si ya están, suma la cantidad."""
    return ejecutar(db, user, clave, lambda: svc.agregar_lineas(db, user, factura_id, datos.version, datos.lineas))


@router.patch("/facturas/{factura_id}/lineas")
def editar(factura_id: int, datos: FacturaEditarLineas, db: Db, user: User, clave: Clave = None):
    """Edita cantidad, precio (con motivo), origen o descripción de líneas de una factura editable."""
    return ejecutar(db, user, clave, lambda: svc.editar_lineas(db, user, factura_id, datos))


@router.post("/facturas/{factura_id}/lineas/eliminar")
def eliminar(factura_id: int, datos: FacturaEliminarLineas, db: Db, user: User, clave: Clave = None):
    """Quita líneas de una factura editable; si están en PL, pide confirmación y también las quita de ahí."""
    return ejecutar(db, user, clave, lambda: svc.eliminar_lineas(db, user, factura_id, datos))


@router.post("/facturas/{factura_id}/finalizar")
def finalizar(factura_id: int, datos: Finalizar, db: Db, user: User, clave: Clave = None):
    """Finaliza la factura (y, si se pide, sus listas de empaque) cuando no le falta ningún dato."""
    return ejecutar(db, user, clave,
                    lambda: svc.finalizar(db, user, factura_id, datos.version, datos.incluir_packing_lists))


@router.post("/facturas/{factura_id}/reabrir")
def reabrir(factura_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    """Reabre con motivo una factura finalizada cuyos PL no viajan aún; los PL salen de su unidad de carga."""
    return ejecutar(db, user, clave, lambda: svc.reabrir(db, user, factura_id, datos.motivo))


@router.post("/facturas/{factura_id}/cancelar")
def cancelar(factura_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    """Cancela la factura y sus listas de empaque; el proveedor solo puede cancelar borradores."""
    return ejecutar(db, user, clave, lambda: svc.cancelar(db, user, factura_id, datos.motivo))


@router.get("/facturas/{factura_id}/historial")
def historial(factura_id: int, db: Db, user: User):
    """Historial de la factura y de sus listas de empaque, del más reciente al más antiguo."""
    return svc.historial_factura(db, user, factura_id)


@router.get("/facturas/{factura_id}/archivos")
def archivos(factura_id: int, db: Db, user: User):
    """Archivos adjuntos de la factura (la factura oficial y otros documentos)."""
    return svc.listar_archivos(db, user, factura_id)


@router.post("/facturas/{factura_id}/archivos")
async def subir(factura_id: int, db: Db, user: User, archivo: UploadFile = File(...),
                tipo: str = Form("FACTURA_OFICIAL")):
    """Adjunta a la factura su factura oficial u otro documento; no se admite en facturas canceladas."""
    contenido = await leer_subida(archivo)
    res = svc.subir_archivo(db, user, factura_id, archivo.filename or "archivo", contenido, tipo)
    db.commit()
    return res


@router.get("/archivos/{archivo_id}")
def descargar(archivo_id: int, db: Db, user: User):
    """Descarga un archivo adjunto a una factura."""
    a = svc.obtener_archivo(db, user, archivo_id)
    return FileResponse(a.ruta, filename=a.nombre)


@router.get("/facturas/{factura_id}/exportar")
def exportar_factura(factura_id: int, db: Db, user: User, formato: Formato = "xlsx"):
    """Factura comercial en PDF o Excel."""
    f = svc.cargar_factura(db, user, factura_id)
    d = documentos.datos_factura(db, f)
    contenido = documentos.pdf_factura(d) if formato == "pdf" else exportar.exportar_factura(d)
    return descarga(contenido, f"factura_{f.numero or f'borrador_{f.id}'}", formato)


@router.post("/facturas/{factura_id}/packing-lists")
def crear_pl(factura_id: int, datos: PLCrear, db: Db, user: User, clave: Clave = None):
    """Crea una lista de empaque (PL) de la factura con las cantidades indicadas o con todo lo pendiente."""
    return ejecutar(db, user, clave, lambda: packing.crear_pl(db, user, factura_id, datos.lineas))
