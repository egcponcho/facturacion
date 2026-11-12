"""Productos que detienen facturas: una línea de factura en curso sin partida
arancelaria no se puede finalizar mientras la ficha de su producto no esté
aprobada (solo cuando la empresa exige datos de aduana)."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modelos import Factura, FacturaLinea, PosicionOC
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comex import servicio as comex


def productos_que_bloquean(db: Session, prov: frozenset | None = None) -> set[int]:
    """Los productos sin ficha aprobada que dejan una factura en curso sin partida."""
    from app.modulos.acceso.permisos import exige_datos_aduana
    from app.modulos.facturacion.estados import EDITABLE_FACTURA

    if not exige_datos_aduana():
        return set()
    c = (select(PosicionOC.articulo_id).join(FacturaLinea, FacturaLinea.posicion_oc_id == PosicionOC.id)
         .join(Factura, Factura.id == FacturaLinea.factura_id)
         .where(Factura.estado.in_(EDITABLE_FACTURA),
                or_(FacturaLinea.partida_arancelaria.is_(None), FacturaLinea.partida_arancelaria == "")).distinct())
    if prov:
        c = c.where(Factura.proveedor_id.in_(prov))
    productos = set(catalogo.productos_de(db, db.scalars(c)).values())
    fichas = comex.fichas(db, productos)
    return {p for p in productos if p in fichas and not fichas[p].aprobado}
