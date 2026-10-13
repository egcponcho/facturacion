"""La factura comercial del proveedor (contra OC) como documento recibido.

Al finalizarse, la factura queda registrada en el núcleo comercial como
documento recibido (cuentas por pagar): mismas líneas, mismo total y la
referencia a sus líneas de factura y posiciones de OC. Al reabrirse vuelve a
borrador (si no tiene pagos) y al cancelarse se anula; su relación con los
packing lists, el transporte y la recepción no cambia.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Documento, DocumentoLinea, Proveedor, Sociedad, UnidadMedida, Usuario
from app.modulos.comercial import documentos as docs
from app.modulos.comercial import terceros as svc_terceros

TIPO = "FACTURA_PROVEEDOR"


def documento_de(db: Session, factura_id: int) -> Documento | None:
    return db.scalar(select(Documento).where(Documento.factura_id == factura_id))


def registrar(db: Session, user: Usuario, f) -> Documento:
    """Crea o actualiza el documento recibido de la factura y lo emite."""
    tipo = docs.tipo_por_codigo(db, TIPO)
    prov = db.get(Proveedor, f.proveedor_id)
    tercero = svc_terceros.asegurar(db, prov, "PROVEEDOR")
    soc = db.scalar(select(Sociedad).where(Sociedad.codigo == f.sociedad))
    d = documento_de(db, f.id)
    if d is None:
        d = Documento(tipo_documento_id=tipo.id, factura_id=f.id, estado="BORRADOR", creado_por=user.id if user else None,
                      version=1)
        d.tipo = tipo
        db.add(d)
    elif d.estado == "EMITIDO":
        return d
    d.sociedad_id, d.tercero_id = soc.id, tercero.id
    d.fecha, d.moneda, d.tipo_cambio = f.fecha, f.moneda, 1
    d.referencia_externa = f.numero
    d.condicion_pago = tercero.condicion_pago
    d.notas = f.condiciones
    d.lineas.clear()
    db.flush()
    unidades = set(db.scalars(select(UnidadMedida.codigo)))
    for i, x in enumerate(f.lineas, start=1):
        d.lineas.append(DocumentoLinea(
            orden=i, posicion_oc_id=x.posicion_oc_id, factura_linea_id=x.id,
            articulo_id=x.posicion_oc.articulo_id if x.posicion_oc else None, codigo=x.codigo_articulo,
            descripcion=(x.descripcion_comercial or x.descripcion or x.codigo_articulo)[:300], cantidad=x.cantidad,
            unidad=x.unidad if x.unidad in unidades else None, precio_unitario=x.precio_unitario, descuento_pct=0))
    db.flush()
    docs.emitir(db, user, d.id, interno=True)
    return d


def reabrir(db: Session, f) -> None:
    """La factura vuelve a corrección: su documento, a borrador (sin pagos)."""
    d = documento_de(db, f.id)
    if d is None or d.estado != "EMITIDO":
        return
    if docs.aplicado(db, d.id) > 0:
        raise ErrorNegocio("The invoice has payments registered: it cannot be reopened.", 409, "con_pagos")
    d.estado, d.emitido_en = "BORRADOR", None
    d.version += 1
    d.vencimientos.clear()
    db.flush()


def anular(db: Session, user: Usuario, f, motivo: str) -> None:
    d = documento_de(db, f.id)
    if d is None:
        return
    if d.estado == "BORRADOR":  # nunca llegó a ser una cuenta por pagar
        db.delete(d)
        db.flush()
    elif d.estado == "EMITIDO":
        docs.anular(db, user, d.id, motivo, interno=True)
