from datetime import date

from fastapi import APIRouter, Query

from app.esquemas import ConMotivo
from app.esquemas.comercial import (
    AplicarIn,
    DocumentoIn,
    DocumentoPatch,
    Emitir,
    NotaIn,
    PagoIn,
    RecurrenteIn,
    TerceroIn,
    TerceroPatch,
)
from app.modulos.comercial import documentos, pagos, recurrente, terceros
from app.modulos.comun import tabla
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


# ---- Terceros ---------------------------------------------------------------------------
@router.get("/terceros")
def listar_terceros(db: Db, user: User, q: str | None = None, rol: str | None = None, page: int = Query(1, ge=1),
                    size: int = Query(25, ge=1, le=200), orden: str | None = None, f: str | None = None):
    """Terceros (clientes, proveedores, transportistas, agentes), paginados y filtrables por rol y por columna."""
    return terceros.listar(db, user, q, rol, page, size, orden, tabla.leer(f))


@router.get("/terceros/valores")
def valores_terceros(db: Db, user: User, columna: str, buscar: str | None = None, f: str | None = None,
                     q: str | None = None, rol: str | None = None):
    """Valores únicos de una columna de la tabla de terceros."""
    return terceros.valores(db, user, columna, buscar, tabla.leer(f), q, rol)


@router.post("/terceros")
def crear_tercero(datos: TerceroIn, db: Db, user: User, clave: Clave = None):
    """Crea un tercero con sus roles, direcciones y medios de contacto."""
    return ejecutar(db, user, clave, lambda: terceros.crear(db, user, datos))


@router.get("/terceros/{tercero_id}")
def tercero(tercero_id: int, db: Db, user: User):
    """Tercero con sus direcciones y medios de contacto."""
    return terceros.detalle(db, user, tercero_id)


@router.patch("/terceros/{tercero_id}")
def editar_tercero(tercero_id: int, datos: TerceroPatch, db: Db, user: User, clave: Clave = None):
    """Modifica un tercero; su identidad llega a su proveedor o transportista de los datos maestros."""
    return ejecutar(db, user, clave, lambda: terceros.actualizar(db, user, tercero_id, datos))


@router.get("/terceros/{tercero_id}/estado-cuenta")
def estado_cuenta(tercero_id: int, db: Db, user: User, direccion: str = Query("EMITIDO", pattern="^(EMITIDO|RECIBIDO)$")):
    """Documentos con saldo y pagos sin aplicar del tercero (por cobrar o por pagar), con el saldo por moneda."""
    return documentos.estado_cuenta(db, user, tercero_id, direccion)


# ---- Documentos -------------------------------------------------------------------------
@router.get("/comercial/opciones")
def opciones(db: Db, user: User):
    """Sociedades, tipos de documento, impuestos vigentes, métodos y condiciones de pago para los formularios."""
    return documentos.opciones(db, user)


@router.get("/documentos")
def listar_documentos(db: Db, user: User, direccion: str | None = None, estado: str | None = None, q: str | None = None,
                      tercero_id: int | None = None, desde: date | None = None, hasta: date | None = None,
                      cobro: str | None = None, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200),
                      orden: str | None = None, f: str | None = None):
    """Documentos comerciales con su saldo y estado de cobro; filtros por dirección, estado, tercero, fechas y columna."""
    return documentos.listar(db, user, direccion, estado, q, tercero_id, desde, hasta, cobro, page, size, orden, tabla.leer(f))


@router.get("/documentos/valores")
def valores_documentos(db: Db, user: User, columna: str, buscar: str | None = None, f: str | None = None,
                       direccion: str | None = None, estado: str | None = None, q: str | None = None):
    """Valores únicos de una columna de la tabla de documentos."""
    return documentos.valores(db, user, columna, buscar, tabla.leer(f), direccion=direccion, estado=estado, q=q)


@router.post("/documentos")
def crear_documento(datos: DocumentoIn, db: Db, user: User, clave: Clave = None):
    """Crea un documento en borrador (factura, nota, proforma o documento recibido) y calcula sus totales."""
    return ejecutar(db, user, clave, lambda: documentos.crear(db, user, datos))


@router.get("/documentos/{documento_id}")
def documento(documento_id: int, db: Db, user: User):
    """Documento con líneas, impuestos, vencimientos, relaciones y lo aplicado."""
    return documentos.detalle(db, user, documento_id)


@router.patch("/documentos/{documento_id}")
def editar_documento(documento_id: int, datos: DocumentoPatch, db: Db, user: User, clave: Clave = None):
    """Modifica un borrador y recalcula sus totales (un documento emitido no se edita)."""
    return ejecutar(db, user, clave, lambda: documentos.actualizar(db, user, documento_id, datos))


@router.delete("/documentos/{documento_id}")
def eliminar_documento(documento_id: int, db: Db, user: User, clave: Clave = None):
    """Elimina un borrador."""
    return ejecutar(db, user, clave, lambda: documentos.eliminar(db, user, documento_id))


@router.post("/documentos/{documento_id}/emitir")
def emitir(documento_id: int, datos: Emitir, db: Db, user: User, clave: Clave = None):
    """Emite el documento: número de su serie, totales, datos de las partes y vencimientos quedan fijos."""
    return ejecutar(db, user, clave, lambda: documentos.emitir(db, user, documento_id, datos.version))


@router.post("/documentos/{documento_id}/anular")
def anular(documento_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    """Anula con motivo un documento emitido sin pagos aplicados."""
    return ejecutar(db, user, clave, lambda: documentos.anular(db, user, documento_id, datos.motivo))


@router.post("/documentos/{documento_id}/nota")
def nota(documento_id: int, datos: NotaIn, db: Db, user: User, clave: Clave = None):
    """Borrador de nota de crédito o débito que rectifica el documento (todas o algunas de sus líneas)."""
    return ejecutar(db, user, clave, lambda: documentos.nota(db, user, documento_id, datos))


# ---- Pagos ---------------------------------------------------------------------------------
@router.get("/pagos")
def listar_pagos(db: Db, user: User, direccion: str | None = None, estado: str | None = None, q: str | None = None,
                 tercero_id: int | None = None, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200),
                 orden: str | None = None, f: str | None = None):
    """Cobros y pagos con lo aplicado y lo que queda sin aplicar."""
    return pagos.listar(db, user, direccion, estado, q, tercero_id, page, size, orden, tabla.leer(f))


@router.get("/pagos/valores")
def valores_pagos(db: Db, user: User, columna: str, buscar: str | None = None, f: str | None = None,
                  direccion: str | None = None, estado: str | None = None, q: str | None = None):
    """Valores únicos de una columna de la tabla de pagos."""
    return pagos.valores(db, user, columna, buscar, tabla.leer(f), direccion=direccion, estado=estado, q=q)


@router.post("/pagos")
def registrar_pago(datos: PagoIn, db: Db, user: User, clave: Clave = None):
    """Registra un cobro o un pago y lo aplica a uno o varios documentos (lo no aplicado queda a favor)."""
    return ejecutar(db, user, clave, lambda: pagos.registrar_pago(db, user, datos))


@router.get("/pagos/{pago_id}")
def pago(pago_id: int, db: Db, user: User):
    """Pago con sus aplicaciones."""
    return pagos.detalle(db, user, pago_id)


@router.post("/pagos/{pago_id}/aplicar")
def aplicar(pago_id: int, datos: AplicarIn, db: Db, user: User, clave: Clave = None):
    """Aplica lo que queda de un pago a otros documentos."""
    return ejecutar(db, user, clave, lambda: pagos.aplicar(db, user, pago_id, datos))


@router.post("/pagos/{pago_id}/anular")
def anular_pago(pago_id: int, datos: ConMotivo, db: Db, user: User, clave: Clave = None):
    """Anula con motivo un pago; sus aplicaciones dejan de saldar los documentos."""
    return ejecutar(db, user, clave, lambda: pagos.anular(db, user, pago_id, datos.motivo))


# ---- Facturación recurrente --------------------------------------------------------------------
@router.get("/recurrentes")
def listar_recurrentes(db: Db, user: User):
    """Facturación recurrente: documentos modelo que se copian cada cierto tiempo."""
    return recurrente.listar(db, user)


@router.post("/recurrentes")
def crear_recurrente(datos: RecurrenteIn, db: Db, user: User, clave: Clave = None):
    """Programa la copia periódica de un documento modelo."""
    return ejecutar(db, user, clave, lambda: recurrente.crear(db, user, datos))


@router.post("/recurrentes/generar")
def generar(db: Db, user: User, hasta: date | None = None, clave: Clave = None):
    """Genera los documentos recurrentes que tocan hasta la fecha (hoy por defecto)."""
    return ejecutar(db, user, clave, lambda: recurrente.generar(db, user, hasta))
