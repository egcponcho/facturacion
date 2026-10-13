"""Fuentes de datos del generador de reportes.

Cada fuente dice qué tabla consulta, qué permiso pide, cómo se limita al
alcance de datos del usuario y qué campos ofrece: su título, su tipo (para
saber qué filtros y medidas admite) y, si es un dato reservado, su grupo de
visibilidad (precios, códigos internos…: un rol que no lo ve no lo puede
pedir). El generador solo arma consultas con estos campos: nunca SQL que
venga de afuera.
"""
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modelos import (
    Embarque,
    Factura,
    FacturaLinea,
    OrdenCompra,
    PosicionOC,
    Producto,
    Proveedor,
    Transportista,
    UnidadCarga,
    Usuario,
)
from app.modulos.seguimiento.indicadores import _emb, _fact, _oc, _prod

TIPOS = ("texto", "numero", "moneda", "fecha", "estado")


@dataclass(frozen=True)
class Campo:
    clave: str
    titulo: str
    tipo: str
    expr: Callable  # () -> expresión SQL
    grupo: str | None = None  # grupo de visibilidad (acceso/visibilidad.py)
    opciones: tuple = ()  # (código, texto) de un campo de estado


@dataclass(frozen=True)
class Fuente:
    clave: str
    titulo: str
    descripcion: str
    permiso: str
    desde: Callable  # (select) -> select con sus uniones
    alcance: Callable  # (db, user) -> condiciones
    campos: list[Campo] = field(default_factory=list)

    def campo(self, clave: str) -> Campo | None:
        return next((c for c in self.campos if c.clave == clave), None)


ESTADOS_OC = (("BORRADOR", "Draft"), ("EN_APROBACION", "Pending approval"), ("RECHAZADA", "Rejected"),
              ("APROBADA", "Approved"), ("CERRADA", "Closed"), ("CANCELADA", "Cancelled"))
ESTADOS_FACTURA = (("BORRADOR", "Draft"), ("EN_CORRECCION", "In correction"), ("FINALIZADA", "Finalized"),
                   ("CANCELADA", "Cancelled"))
ESTADOS_EMBARQUE = (("PLANIFICADO", "Planned"), ("EN_TRANSITO", "In transit"), ("ARRIBADO", "Arrived"),
                    ("ENTREGADO", "Delivered"), ("RECIBIDO", "Received"), ("CANCELADO", "Called off"))
ESTADOS_FICHA = (("borrador", "Draft"), ("sugerida", "Draft · complete"), ("revision", "In review"),
                 ("observado", "Returned"), ("aprobado", "Approved"), ("corregido", "Approved (corrected)"))
MODOS = (("MARITIMO", "Sea"), ("AEREO", "Air"), ("TERRESTRE", "Road"))


def _facturado_linea():
    return (select(func.coalesce(func.sum(FacturaLinea.cantidad), 0)).join(Factura, Factura.id == FacturaLinea.factura_id)
            .where(FacturaLinea.posicion_oc_id == PosicionOC.id, Factura.estado != "CANCELADA").scalar_subquery())


FUENTES: dict[str, Fuente] = {f.clave: f for f in [
    Fuente(
        "ordenes", "Purchase orders", "One row per purchase order, with its totals.", "oc.ver",
        lambda q: q.select_from(OrdenCompra).join(Proveedor, Proveedor.id == OrdenCompra.proveedor_id),
        lambda db, user: _oc(user),
        [
            Campo("numero", "PO", "texto", lambda: OrdenCompra.numero),
            Campo("proveedor", "Supplier", "texto", lambda: Proveedor.nombre),
            Campo("sociedad", "Company", "texto", lambda: OrdenCompra.sociedad, "codigos_internos"),
            Campo("estado", "Status", "estado", lambda: OrdenCompra.estado, opciones=ESTADOS_OC),
            Campo("fecha", "PO date", "fecha", lambda: OrdenCompra.fecha),
            Campo("fecha_xf", "XF date", "fecha", lambda: OrdenCompra.fecha_xf),
            Campo("fecha_tienda", "In-store date", "fecha", lambda: OrdenCompra.fecha_tienda, "fechas_internas"),
            Campo("aprobada_en", "Approved on", "fecha", lambda: func.date(OrdenCompra.aprobada_en)),
            Campo("moneda", "Currency", "texto", lambda: OrdenCompra.moneda),
            Campo("incoterm", "Incoterm", "texto", lambda: OrdenCompra.incoterm),
            Campo("condicion_pago", "Payment terms", "texto", lambda: OrdenCompra.condicion_pago),
            Campo("centro_destino", "Destination plant", "texto", lambda: OrdenCompra.centro_destino, "codigos_internos"),
            Campo("puerto_despacho", "Port of loading", "texto", lambda: OrdenCompra.puerto_despacho),
            Campo("pais_origen", "Country of origin", "texto", lambda: OrdenCompra.pais_origen),
            Campo("lineas", "Lines", "numero", lambda: select(func.count(PosicionOC.id))
                  .where(PosicionOC.oc_id == OrdenCompra.id).scalar_subquery()),
            Campo("cantidad", "Quantity", "numero", lambda: select(func.coalesce(func.sum(PosicionOC.cantidad), 0))
                  .where(PosicionOC.oc_id == OrdenCompra.id).scalar_subquery()),
            Campo("valor", "PO value", "moneda", lambda: select(func.coalesce(func.sum(PosicionOC.cantidad * PosicionOC.precio), 0))
                  .where(PosicionOC.oc_id == OrdenCompra.id).scalar_subquery(), "precios"),
        ],
    ),
    Fuente(
        "lineas_oc", "Purchase order lines", "One row per PO line (item, quantity, invoiced).", "oc.ver",
        lambda q: q.select_from(PosicionOC).join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id)
        .join(Proveedor, Proveedor.id == OrdenCompra.proveedor_id),
        lambda db, user: _oc(user),
        [
            Campo("oc", "PO", "texto", lambda: OrdenCompra.numero),
            Campo("posicion", "Line", "texto", lambda: PosicionOC.posicion),
            Campo("proveedor", "Supplier", "texto", lambda: Proveedor.nombre),
            Campo("estado_oc", "PO status", "estado", lambda: OrdenCompra.estado, opciones=ESTADOS_OC),
            Campo("codigo_sap", "Item code", "texto", lambda: PosicionOC.codigo_sap),
            Campo("estilo", "Style", "texto", lambda: PosicionOC.estilo),
            Campo("color", "Color", "texto", lambda: PosicionOC.color),
            Campo("talla", "Size", "texto", lambda: PosicionOC.talla),
            Campo("marca", "Brand", "texto", lambda: PosicionOC.marca),
            Campo("grupo", "Item group", "texto", lambda: PosicionOC.grupo),
            Campo("almacen", "Warehouse", "texto", lambda: PosicionOC.almacen, "codigos_internos"),
            Campo("unidad", "UoM", "texto", lambda: PosicionOC.unidad),
            Campo("fecha_xf", "XF date", "fecha", lambda: OrdenCompra.fecha_xf),
            Campo("cantidad", "Quantity", "numero", lambda: PosicionOC.cantidad),
            Campo("facturado", "Invoiced", "numero", _facturado_linea),
            Campo("pendiente", "To invoice", "numero", lambda: PosicionOC.cantidad - _facturado_linea()),
            Campo("precio", "Unit price", "moneda", lambda: PosicionOC.precio, "precios"),
            Campo("importe", "Amount", "moneda", lambda: PosicionOC.cantidad * PosicionOC.precio, "precios"),
        ],
    ),
    Fuente(
        "facturas", "Invoices", "One row per commercial invoice.", "factura.ver",
        lambda q: q.select_from(Factura).join(Proveedor, Proveedor.id == Factura.proveedor_id),
        lambda db, user: _fact(user),
        [
            Campo("numero", "Invoice", "texto", lambda: Factura.numero),
            Campo("proveedor", "Supplier", "texto", lambda: Proveedor.nombre),
            Campo("estado", "Status", "estado", lambda: Factura.estado, opciones=ESTADOS_FACTURA),
            Campo("fecha", "Date", "fecha", lambda: Factura.fecha),
            Campo("finalizado_en", "Finalized on", "fecha", lambda: func.date(Factura.finalizado_en)),
            Campo("sociedad", "Company", "texto", lambda: Factura.sociedad, "codigos_internos"),
            Campo("moneda", "Currency", "texto", lambda: Factura.moneda),
            Campo("incoterm", "Incoterm", "texto", lambda: Factura.incoterm),
            Campo("lineas", "Lines", "numero", lambda: select(func.count(FacturaLinea.id))
                  .where(FacturaLinea.factura_id == Factura.id).scalar_subquery()),
            Campo("cantidad", "Quantity", "numero", lambda: select(func.coalesce(func.sum(FacturaLinea.cantidad), 0))
                  .where(FacturaLinea.factura_id == Factura.id).scalar_subquery()),
            Campo("importe", "Amount", "moneda", lambda: select(func.coalesce(func.sum(FacturaLinea.cantidad * FacturaLinea.precio_unitario), 0))
                  .where(FacturaLinea.factura_id == Factura.id).scalar_subquery(), "precios"),
        ],
    ),
    Fuente(
        "embarques", "Shipments", "One row per shipment, with its route, dates and load units.", "transporte.gestionar",
        lambda q: q.select_from(Embarque).outerjoin(Transportista, Transportista.id == Embarque.transportista_id),
        _emb,
        [
            Campo("codigo", "Shipment", "texto", lambda: Embarque.codigo),
            Campo("estado", "Status", "estado", lambda: Embarque.estado, opciones=ESTADOS_EMBARQUE),
            Campo("tipo_transporte", "Mode", "estado", lambda: Embarque.tipo_transporte, opciones=MODOS),
            Campo("transportista", "Carrier", "texto", lambda: Transportista.nombre),
            Campo("documento_numero", "B/L / AWB", "texto", lambda: Embarque.documento_numero),
            Campo("puerto_origen", "Port of loading", "texto", lambda: Embarque.puerto_origen),
            Campo("puerto_destino", "Port of discharge", "texto", lambda: Embarque.puerto_destino),
            Campo("centro", "Plant", "texto", lambda: Embarque.centro, "codigos_internos"),
            Campo("etd", "ETD", "fecha", lambda: Embarque.etd),
            Campo("eta", "ETA", "fecha", lambda: Embarque.eta),
            Campo("salida_real", "Actual departure", "fecha", lambda: Embarque.salida_real),
            Campo("arribo_real", "Actual arrival", "fecha", lambda: Embarque.arribo_real),
            Campo("unidades", "Load units", "numero", lambda: select(func.count(UnidadCarga.id))
                  .where(UnidadCarga.embarque_id == Embarque.id).scalar_subquery()),
        ],
    ),
    Fuente(
        "productos", "Products", "One row per product (style and color) with its technical sheet status.", "producto.ver",
        lambda q: q.select_from(Producto).join(Proveedor, Proveedor.id == Producto.proveedor_id),
        lambda db, user: _prod(user),
        [
            Campo("codigo_generico", "Generic", "texto", lambda: Producto.codigo_generico),
            Campo("estilo", "Style", "texto", lambda: Producto.estilo),
            Campo("color", "Color", "texto", lambda: Producto.color),
            Campo("proveedor", "Supplier", "texto", lambda: Proveedor.nombre),
            Campo("estado", "Sheet status", "estado", lambda: Producto.estado, opciones=ESTADOS_FICHA),
            Campo("tipo", "Product type", "texto", lambda: Producto.tipo),
            Campo("pais_origen", "Country of origin", "texto", lambda: Producto.pais_origen),
            Campo("revisado_en", "Reviewed on", "fecha", lambda: func.date(Producto.revisado_en)),
        ],
    ),
]}


def disponibles(user: Usuario) -> list[Fuente]:
    from app.modulos.acceso.permisos import tiene

    return [f for f in FUENTES.values() if tiene(user, f.permiso)]


def visible(campo: Campo) -> bool:
    from app.modulos.acceso import visibilidad

    return not campo.grupo or not visibilidad.oculto(campo.grupo)


def describir(f: Fuente) -> dict:
    return {"clave": f.clave, "titulo": f.titulo, "descripcion": f.descripcion,
            "campos": [{"clave": c.clave, "titulo": c.titulo, "tipo": c.tipo, "opciones": [list(o) for o in c.opciones]}
                       for c in f.campos if visible(c)]}


def alcance(db: Session, user: Usuario, f: Fuente) -> list:
    return f.alcance(db, user)
