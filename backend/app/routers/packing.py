from fastapi import APIRouter
from fastapi.responses import Response

from ..schemas import (
    CajaManual,
    ConMotivo,
    Despaletizar,
    EditarCajas,
    EliminarCajas,
    EmpaqueAplicar,
    EmpaquePrevia,
    Finalizar,
    GuardarPlantilla,
    Paletizar,
    PalletPatch,
    PLAgregar,
    PLMover,
    PLMoverCajas,
    PLQuitar,
    RecepcionIn,
)
from ..services import exportar
from ..services.partes import partes
from ..services import packing as svc
from .base import XLSX, Clave, Db, User, ejecutar

router = APIRouter(prefix="/packing-lists")


@router.get("/{pl_id}")
def detalle(pl_id: int, db: Db, user: User):
    return svc.detalle_pl(db, user, pl_id)


@router.post("/{pl_id}/agregar")
def agregar(pl_id: int, datos: PLAgregar, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.agregar_pendientes(db, user, pl_id, datos.version, datos.lineas))


@router.post("/{pl_id}/mover")
def mover(pl_id: int, datos: PLMover, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.mover(db, user, pl_id, datos))


@router.post("/{pl_id}/quitar")
def quitar(pl_id: int, datos: PLQuitar, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.quitar(db, user, pl_id, datos))


@router.post("/{pl_id}/mover-cajas")
def mover_cajas(pl_id: int, datos: PLMoverCajas, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.mover_cajas(db, user, pl_id, datos))


@router.post("/{pl_id}/empaque/previa")
def empaque_previa(pl_id: int, datos: EmpaquePrevia, db: Db, user: User):
    return svc.empaque_previa(db, user, pl_id, datos)


@router.post("/{pl_id}/empaque/aplicar")
def empaque_aplicar(pl_id: int, datos: EmpaqueAplicar, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.aplicar_empaque(db, user, pl_id, datos))


@router.post("/{pl_id}/cajas")
def crear_caja(pl_id: int, datos: CajaManual, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.crear_caja(db, user, pl_id, datos))


@router.patch("/{pl_id}/cajas")
def editar_cajas(pl_id: int, datos: EditarCajas, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.editar_cajas(db, user, pl_id, datos))


@router.post("/{pl_id}/cajas/eliminar")
def eliminar_cajas(pl_id: int, datos: EliminarCajas, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.eliminar_cajas(db, user, pl_id, datos))


@router.post("/{pl_id}/pallets")
def paletizar(pl_id: int, datos: Paletizar, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.paletizar(db, user, pl_id, datos))


@router.post("/{pl_id}/pallets/quitar")
def despaletizar(pl_id: int, datos: Despaletizar, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.despaletizar(db, user, pl_id, datos))


@router.patch("/{pl_id}/pallets/{pallet_id}")
def editar_pallet(pl_id: int, pallet_id: int, datos: PalletPatch, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.editar_pallet(db, user, pl_id, pallet_id, datos))


@router.post("/{pl_id}/cajas/{grupo_id}/plantilla")
def guardar_plantilla(pl_id: int, grupo_id: int, datos: GuardarPlantilla, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_como_plantilla(db, user, pl_id, grupo_id, datos.nombre))


@router.post("/{pl_id}/finalizar")
def finalizar(pl_id: int, datos: Finalizar, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.finalizar_pl(db, user, pl_id, datos.version))


@router.post("/{pl_id}/reabrir")
def reabrir(pl_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.reabrir_pl(db, user, pl_id, datos.motivo))


@router.post("/{pl_id}/cancelar")
def cancelar(pl_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.cancelar_pl(db, user, pl_id, datos.motivo))


@router.post("/{pl_id}/recepcion")
def recepcion(pl_id: int, datos: RecepcionIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.registrar_recepcion(db, user, pl_id, datos))


@router.get("/{pl_id}/exportar")
def exportar_xlsx(pl_id: int, db: Db, user: User):
    pl = svc.cargar_pl(db, user, pl_id)
    nombre = f"{(pl.factura.numero or f'borrador_{pl.factura_id}').replace('/', '-')}_{pl.numero}.xlsx"
    return Response(exportar.exportar_pl(pl, partes(db, pl.factura.sociedad, pl.factura.centro, pl.factura.centro_destino)), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
