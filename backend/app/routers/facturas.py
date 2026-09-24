from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response

from ..schemas import (
    ConMotivo,
    FacturaAgregar,
    FacturaCabecera,
    FacturaCrear,
    FacturaEditarLineas,
    FacturaEliminarLineas,
    Finalizar,
    PLCrear,
)
from ..services import exportar
from ..services import facturas as svc
from ..services import packing
from .base import XLSX, Clave, Db, User, ejecutar

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
):
    return svc.listar_facturas(db, user, proveedor_id, estado, q, vista, page, size)


@router.post("/facturas")
def crear(datos: FacturaCrear, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.crear_factura(db, user, datos))


@router.get("/facturas/{factura_id}")
def detalle(factura_id: int, db: Db, user: User):
    return svc.detalle_factura(db, user, factura_id)


@router.patch("/facturas/{factura_id}")
def cabecera(factura_id: int, datos: FacturaCabecera, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.actualizar_cabecera(db, user, factura_id, datos))


@router.post("/facturas/{factura_id}/lineas")
def agregar(factura_id: int, datos: FacturaAgregar, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.agregar_lineas(db, user, factura_id, datos.version, datos.lineas))


@router.patch("/facturas/{factura_id}/lineas")
def editar(factura_id: int, datos: FacturaEditarLineas, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.editar_lineas(db, user, factura_id, datos))


@router.post("/facturas/{factura_id}/lineas/eliminar")
def eliminar(factura_id: int, datos: FacturaEliminarLineas, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.eliminar_lineas(db, user, factura_id, datos))


@router.post("/facturas/{factura_id}/finalizar")
def finalizar(factura_id: int, datos: Finalizar, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave,
                    lambda: svc.finalizar(db, user, factura_id, datos.version, datos.incluir_packing_lists))


@router.post("/facturas/{factura_id}/reabrir")
def reabrir(factura_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.reabrir(db, user, factura_id, datos.motivo))


@router.post("/facturas/{factura_id}/cancelar")
def cancelar(factura_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.cancelar(db, user, factura_id, datos.motivo))


@router.get("/facturas/{factura_id}/historial")
def historial(factura_id: int, db: Db, user: User):
    return svc.historial_factura(db, user, factura_id)


@router.get("/facturas/{factura_id}/archivos")
def archivos(factura_id: int, db: Db, user: User):
    return svc.listar_archivos(db, user, factura_id)


@router.post("/facturas/{factura_id}/archivos")
async def subir(factura_id: int, db: Db, user: User, archivo: UploadFile = File(...),
                tipo: str = Form("FACTURA_OFICIAL")):
    contenido = await archivo.read()
    res = svc.subir_archivo(db, user, factura_id, archivo.filename or "archivo", contenido, tipo)
    db.commit()
    return res


@router.get("/archivos/{archivo_id}")
def descargar(archivo_id: int, db: Db, user: User):
    a = svc.obtener_archivo(db, user, archivo_id)
    return FileResponse(a.ruta, filename=a.nombre)


@router.get("/facturas/{factura_id}/exportar")
def exportar_xlsx(factura_id: int, db: Db, user: User):
    f = svc.cargar_factura(db, user, factura_id)
    nombre = f"factura_{(f.numero or f'borrador_{f.id}').replace('/', '-')}.xlsx"
    return Response(exportar.exportar_factura(f), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/facturas/{factura_id}/packing-lists")
def crear_pl(factura_id: int, datos: PLCrear, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: packing.crear_pl(db, user, factura_id, datos.lineas))
