from fastapi import APIRouter, File, UploadFile

from app.esquemas import (
    CajaManual,
    ConMotivo,
    Despaletizar,
    EditarCajas,
    EliminarCajas,
    EmpaqueAplicar,
    EmpaquePrevia,
    Finalizar,
    GuardarPlantilla,
    InnerPackIn,
    Paletizar,
    PalletPatch,
    PLAgregar,
    PLMover,
    PLMoverCajas,
    PLNumeroIn,
    PLQuitar,
    RecepcionIn,
)
from app.modulos.documentos import documentos, exportar
from app.modulos.empaque import packing as svc
from app.web.rutas import Clave, Db, Formato, User, descarga, ejecutar, leer_subida, plantilla_o_vista

router = APIRouter(prefix="/packing-lists")


@router.get("/{pl_id}")
def detalle(pl_id: int, db: Db, user: User):
    """Lista de empaque con sus filas, cajas, pallets, totales, validaciones y acciones permitidas."""
    return svc.detalle_pl(db, user, pl_id)


@router.post("/{pl_id}/agregar")
def agregar(pl_id: int, datos: PLAgregar, db: Db, user: User, clave: Clave = None):
    """Agrega al PL cantidades de la factura aún sin asignar (sin `lineas`, todo el saldo)."""
    return ejecutar(db, user, clave, lambda: svc.agregar_pendientes(db, user, pl_id, datos.version, datos.lineas))


@router.post("/{pl_id}/mover")
def mover(pl_id: int, datos: PLMover, db: Db, user: User, clave: Clave = None):
    """Mueve cantidades sin caja a otro PL de la misma factura o a uno nuevo."""
    return ejecutar(db, user, clave, lambda: svc.mover(db, user, pl_id, datos))


@router.post("/{pl_id}/quitar")
def quitar(pl_id: int, datos: PLQuitar, db: Db, user: User, clave: Clave = None):
    """Quita del PL cantidades sin caja; vuelven al saldo de la factura."""
    return ejecutar(db, user, clave, lambda: svc.quitar(db, user, pl_id, datos))


@router.post("/{pl_id}/mover-cajas")
def mover_cajas(pl_id: int, datos: PLMoverCajas, db: Db, user: User, clave: Clave = None):
    """Mueve cajas con su contenido a otro PL de la misma factura o a uno nuevo."""
    return ejecutar(db, user, clave, lambda: svc.mover_cajas(db, user, pl_id, datos))


@router.post("/{pl_id}/empaque/previa")
def empaque_previa(pl_id: int, datos: EmpaquePrevia, db: Db, user: User):
    """Vista previa del empaque por plantilla: cajas completas y sobrante de cada fila; no guarda."""
    return svc.empaque_previa(db, user, pl_id, datos)


@router.post("/{pl_id}/empaque/aplicar")
def empaque_aplicar(pl_id: int, datos: EmpaqueAplicar, db: Db, user: User, clave: Clave = None):
    """Crea las cajas completas de cada fila con su plantilla; el sobrante va en caja parcial o sin caja."""
    return ejecutar(db, user, clave, lambda: svc.aplicar_empaque(db, user, pl_id, datos))


@router.post("/{pl_id}/cajas")
def crear_caja(pl_id: int, datos: CajaManual, db: Db, user: User, clave: Clave = None):
    """Arma cajas a mano con cantidades sin caja, respetando las reglas de casepack y prepack."""
    return ejecutar(db, user, clave, lambda: svc.crear_caja(db, user, pl_id, datos))


@router.patch("/{pl_id}/cajas")
def editar_cajas(pl_id: int, datos: EditarCajas, db: Db, user: User, clave: Clave = None):
    """Cambia medidas, tara, pesos, tipo, plantilla o cantidad de las cajas elegidas."""
    return ejecutar(db, user, clave, lambda: svc.editar_cajas(db, user, pl_id, datos))


@router.post("/{pl_id}/cajas/eliminar")
def eliminar_cajas(pl_id: int, datos: EliminarCajas, db: Db, user: User, clave: Clave = None):
    """Deshace las cajas elegidas con lo que llevan dentro; su producto queda sin caja."""
    return ejecutar(db, user, clave, lambda: svc.eliminar_cajas(db, user, pl_id, datos))


@router.post("/{pl_id}/pallets")
def paletizar(pl_id: int, datos: Paletizar, db: Db, user: User, clave: Clave = None):
    """Pone cajas en un pallet (u otro contenedor) nuevo o existente, repartidas por igual."""
    return ejecutar(db, user, clave, lambda: svc.paletizar(db, user, pl_id, datos))


@router.post("/{pl_id}/pallets/quitar")
def despaletizar(pl_id: int, datos: Despaletizar, db: Db, user: User, clave: Clave = None):
    """Saca cajas de su pallet o vacía un pallet; los contenedores que quedan vacíos se quitan."""
    return ejecutar(db, user, clave, lambda: svc.despaletizar(db, user, pl_id, datos))


@router.put("/{pl_id}/lineas/{pl_linea_id}/inner")
def definir_inner(pl_id: int, pl_linea_id: int, datos: InnerPackIn, db: Db, user: User, clave: Clave = None):
    """Define el inner pack de una fila del PL cuando la OC no lo trae y la fila aún no tiene cajas."""
    return ejecutar(db, user, clave, lambda: svc.definir_inner(db, user, pl_id, pl_linea_id, datos))


@router.put("/{pl_id}/numero")
def renombrar(pl_id: int, datos: PLNumeroIn, db: Db, user: User, clave: Clave = None):
    """Cambia el número del PL (el del proveedor); único entre los PL vigentes del proveedor."""
    return ejecutar(db, user, clave, lambda: svc.renombrar(db, user, pl_id, datos))


@router.patch("/{pl_id}/pallets/{pallet_id}")
def editar_pallet(pl_id: int, pallet_id: int, datos: PalletPatch, db: Db, user: User, clave: Clave = None):
    """Cambia las medidas o la tara de un pallet del PL."""
    return ejecutar(db, user, clave, lambda: svc.editar_pallet(db, user, pl_id, pallet_id, datos))


@router.post("/{pl_id}/cajas/{grupo_id}/plantilla")
def guardar_plantilla(pl_id: int, grupo_id: int, datos: GuardarPlantilla, db: Db, user: User, clave: Clave = None):
    """Guarda una caja de un solo producto como plantilla de caja del proveedor."""
    return ejecutar(db, user, clave, lambda: svc.guardar_como_plantilla(db, user, pl_id, grupo_id, datos.nombre))


@router.post("/{pl_id}/finalizar")
def finalizar(pl_id: int, datos: Finalizar, db: Db, user: User, clave: Clave = None):
    """Finaliza el PL si no le falta nada (todo en cajas, con medidas y pesos); deja de ser editable."""
    return ejecutar(db, user, clave, lambda: svc.finalizar_pl(db, user, pl_id, datos.version))


@router.post("/{pl_id}/reabrir")
def reabrir(pl_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    """Reabre un PL finalizado para corregirlo (con motivo); si iba en una unidad de carga, sale de ella."""
    return ejecutar(db, user, clave, lambda: svc.reabrir_pl(db, user, pl_id, datos.motivo))


@router.post("/{pl_id}/cancelar")
def cancelar(pl_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    """Cancela el PL (con motivo si ya no es borrador); el proveedor solo cancela borradores."""
    return ejecutar(db, user, clave, lambda: svc.cancelar_pl(db, user, pl_id, datos.motivo))


@router.post("/{pl_id}/recepcion")
def recepcion(pl_id: int, datos: RecepcionIn, db: Db, user: User, clave: Clave = None):
    """Registra lo recibido y lo dañado por fila de un PL cuyo embarque ya llegó; alerta las diferencias."""
    return ejecutar(db, user, clave, lambda: svc.registrar_recepcion(db, user, pl_id, datos))


@router.get("/{pl_id}/exportar")
def exportar_pl(pl_id: int, db: Db, user: User, formato: Formato = "xlsx"):
    """Lista de empaque en PDF o Excel."""
    pl = svc.cargar_pl(db, user, pl_id)
    d = documentos.datos_pl(db, pl)
    contenido = documentos.pdf_pl(d) if formato == "pdf" else exportar.exportar_pl(d)
    return descarga(contenido, f"{pl.factura.numero or f'borrador_{pl.factura_id}'}_{pl.numero}", formato)


@router.get("/{pl_id}/estructura/plantilla")
def plantilla_estructura(pl_id: int, db: Db, user: User, vista: bool = False):
    """Plantilla para cargar la estructura física (una columna por tipo de empaque)."""
    from app.modulos.empaque import estructura_pl

    pl = svc.cargar_pl(db, user, pl_id)
    return plantilla_o_vista(estructura_pl.plantilla_estructura(db, pl), f"structure_{pl.numero}", vista)


@router.post("/{pl_id}/estructura/importar")
async def importar_estructura(pl_id: int, db: Db, user: User, archivo: UploadFile = File(...)):
    """Arma el empaque del PL desde los identificadores de cada nivel (reemplaza el actual)."""
    from app.modulos.empaque import estructura_pl

    pl = svc._editable(db, user, pl_id, None)
    res = estructura_pl.importar_estructura(db, user, pl, archivo.filename or "datos.csv", await leer_subida(archivo))
    db.commit()
    return res
