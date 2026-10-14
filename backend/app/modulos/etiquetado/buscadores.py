"""Búsquedas del asistente de etiquetado: órdenes de compra (por familia),
listas de empaque y sus niveles de empaque."""
from __future__ import annotations

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.modelos import Articulo, GeneracionEtiquetas, OrdenCompra, PosicionOC, Usuario
from app.modulos.acceso.permisos import exigir, proveedor_filtro
from app.modulos.comun.texto import filtro_texto
from app.modulos.etiquetado import campos, familias, generacion

MAX_ORDENES = 200


def ordenes_familia(db: Session, user: Usuario, familia_id: int | None = None, q: str | None = None,
                    estado: str | None = None, page: int = 1, size: int = 50, solo_ids: bool = False) -> dict:
    """Órdenes de compra con artículos de la familia (o todas, sin familia), con
    cuántas líneas y artículos distintos de la familia tienen y si ya se
    generaron etiquetas para ellas."""
    exigir(user, "etiquetas.generar")
    lineas = select(PosicionOC.oc_id, func.count(PosicionOC.id).label("lineas"),
                    func.count(distinct(PosicionOC.articulo_id)).label("articulos")).join(Articulo, Articulo.id == PosicionOC.articulo_id)
    if familia_id:
        familias.cargar(db, familia_id)
        lineas = lineas.where(familias.familia_sql() == familia_id)
    sub = lineas.group_by(PosicionOC.oc_id).subquery()
    c = select(OrdenCompra, sub.c.lineas, sub.c.articulos).join(sub, sub.c.oc_id == OrdenCompra.id)
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(OrdenCompra.proveedor_id.in_(prov))
    if estado:
        c = c.where(OrdenCompra.estado == estado.upper())
    else:
        c = c.where(OrdenCompra.estado.not_in(("BORRADOR", "CANCELADA")))
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [OrdenCompra.numero.ilike(p)]))
    if solo_ids:
        return {"ids": [o.id for o, _, _ in db.execute(c.order_by(OrdenCompra.id).limit(MAX_ORDENES * 5))]}
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.execute(c.order_by(OrdenCompra.fecha.desc().nulls_last(), OrdenCompra.id.desc())
                       .offset((page - 1) * size).limit(size)).all()
    ids = [o.id for o, _, _ in filas]
    hechas = dict(db.execute(select(GeneracionEtiquetas.oc_id, func.count()).where(
        GeneracionEtiquetas.oc_id.in_(ids), GeneracionEtiquetas.estado == "GENERADA").group_by(GeneracionEtiquetas.oc_id)).all())
    return {"total": total, "items": [{
        "id": o.id, "numero": o.numero, "proveedor": o.proveedor.nombre if o.proveedor else None, "estado": o.estado,
        "fecha": o.fecha, "lineas": lineas_, "articulos": articulos_, "generaciones": hechas.get(o.id, 0),
        "bultos": len(campos.bultos(db, o.id))} for o, lineas_, articulos_ in filas]}


def buscar_packing(db: Session, user: Usuario, q: str | None = None, size: int = 30) -> list[dict]:
    """Listas de empaque (no canceladas) dentro del alcance del usuario, por número de lista o de factura."""
    from app.modelos import Factura, PackingList
    from app.modulos.acceso.permisos import sociedades_de

    exigir(user, "etiquetas.generar")
    c = select(PackingList).join(Factura, Factura.id == PackingList.factura_id).where(PackingList.estado != "CANCELADO")
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(Factura.proveedor_id.in_(prov))
    soc = sociedades_de(user)
    if soc:
        c = c.where(Factura.sociedad.in_(soc))
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [PackingList.numero.ilike(p), Factura.numero.ilike(p)]))
    return [{"id": pl.id, "numero": pl.numero, "factura": pl.factura.numero, "estado": pl.estado,
             "proveedor": pl.factura.proveedor.nombre if pl.factura.proveedor else None,
             "etiquetas_reales": generacion.pl_permite_reales(pl)}
            for pl in db.scalars(c.order_by(PackingList.id.desc()).limit(size))]


def packing(db: Session, user: Usuario, pl_id: int) -> dict:
    """Una lista de empaque con sus niveles de empaque (cuántas unidades de cada tipo)."""
    exigir(user, "etiquetas.generar")
    pl = generacion.cargar_pl(db, user, pl_id)
    return {"id": pl.id, "numero": pl.numero, "factura": pl.factura.numero, "estado": pl.estado,
            "proveedor": pl.factura.proveedor.nombre if pl.factura.proveedor else None,
            "etiquetas_reales": generacion.pl_permite_reales(pl),
            "niveles": campos.niveles_pl(pl), "superiores": len(campos.unidades_pl(pl, superiores=True))}
