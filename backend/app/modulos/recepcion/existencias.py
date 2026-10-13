"""Existencias por bodega: lo que entró a cada bodega o bodega fiscal con
las recepciones de los contenedores (conteos, ajustes y confirmaciones sin
conteo), por artículo y almacén lógico. Lo dañado se recibe pero no está
disponible. Cada cifra se abre en sus movimientos (kardex de ingresos).

Hoy el sistema registra los ingresos de importación; las salidas y los
traslados entre bodegas los lleva el ERP.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modelos import (
    Centro,
    Embarque,
    Factura,
    FacturaLinea,
    PackingList,
    PLLinea,
    Proveedor,
    RecepcionMovimiento,
    RecepcionRegistro,
    Sociedad,
    UnidadCarga,
    Usuario,
)
from app.modelos.base import cant
from app.modulos.acceso.permisos import exigir_alguno, sociedades_de
from app.modulos.comun.texto import filtro_texto

MAX_FILAS = 5000


def _base(db: Session, user: Usuario, centro: str | None, q: str | None, proveedor_id: int | None):
    exigir_alguno(user, "inventario.ver", "recepcion.registrar")
    consulta = (
        select()
        .select_from(RecepcionMovimiento)
        .join(RecepcionRegistro, RecepcionRegistro.id == RecepcionMovimiento.registro_id)
        .join(PLLinea, PLLinea.id == RecepcionMovimiento.pl_linea_id)
        .join(FacturaLinea, FacturaLinea.id == PLLinea.factura_linea_id)
        .join(Factura, Factura.id == FacturaLinea.factura_id)
        .join(Proveedor, Proveedor.id == Factura.proveedor_id)
    )
    soc = sociedades_de(user)
    if soc:
        consulta = consulta.where(RecepcionRegistro.centro.in_(
            select(Centro.codigo).join(Sociedad, Sociedad.id == Centro.sociedad_id).where(Sociedad.codigo.in_(soc))))
    if centro:
        consulta = consulta.where(RecepcionRegistro.centro.in_([c.strip().upper() for c in centro.split(",") if c.strip()]))
    if proveedor_id:
        consulta = consulta.where(Factura.proveedor_id == proveedor_id)
    if q:
        consulta = consulta.where(filtro_texto(q, lambda p: [
            FacturaLinea.codigo_articulo.ilike(p), FacturaLinea.descripcion.ilike(p), FacturaLinea.estilo.ilike(p),
            FacturaLinea.oc_numero.ilike(p), Proveedor.nombre.ilike(p)]))
    return consulta


def existencias(db: Session, user: Usuario, centro: str | None = None, q: str | None = None,
                proveedor_id: int | None = None) -> dict:
    claves = (RecepcionRegistro.centro, FacturaLinea.almacen, FacturaLinea.codigo_articulo, FacturaLinea.talla,
              FacturaLinea.unidad, Proveedor.id, Proveedor.nombre)
    consulta = _base(db, user, centro, q, proveedor_id).add_columns(
        *claves,
        func.max(FacturaLinea.descripcion), func.max(FacturaLinea.estilo), func.max(FacturaLinea.color),
        func.sum(RecepcionMovimiento.cantidad), func.sum(RecepcionMovimiento.danada),
        func.max(RecepcionRegistro.fecha), func.count(func.distinct(RecepcionRegistro.id)),
    ).group_by(*claves).order_by(RecepcionRegistro.centro, FacturaLinea.codigo_articulo, FacturaLinea.talla)
    filas = db.execute(consulta.limit(MAX_FILAS + 1)).all()
    nombres = dict(db.execute(select(Centro.codigo, Centro.nombre)).all())
    tipos = dict(db.execute(select(Centro.codigo, Centro.tipo)).all())
    items = []
    for (c, almacen, codigo, talla, unidad, prov_id, prov, desc, estilo, color, recibido, danado, ultimo, ingresos) in filas[:MAX_FILAS]:
        recibido, danado = cant(recibido or 0), cant(danado or 0)
        if not recibido and not danado:
            continue  # un ajuste dejó la fila en cero
        items.append({
            "centro": c, "centro_nombre": nombres.get(c), "centro_tipo": tipos.get(c), "almacen": almacen,
            "codigo": codigo, "talla": talla, "descripcion": desc, "estilo": estilo, "color": color, "unidad": unidad,
            "proveedor_id": prov_id, "proveedor": prov, "recibido": recibido, "danado": danado,
            "disponible": cant(recibido - danado), "ultimo_ingreso": ultimo, "ingresos": ingresos,
        })
    bodegas: dict[str, dict] = {}
    for it in items:
        b = bodegas.setdefault(it["centro"], {"centro": it["centro"], "nombre": it["centro_nombre"],
                                              "tipo": it["centro_tipo"], "articulos": 0, "por_unidad": {}})
        b["articulos"] += 1
        u = b["por_unidad"].setdefault(it["unidad"], {"recibido": 0, "danado": 0, "disponible": 0})
        for k in ("recibido", "danado", "disponible"):
            u[k] = cant(u[k] + it[k])
    return {"items": items, "truncado": len(filas) > MAX_FILAS, "bodegas": list(bodegas.values())}


def movimientos(db: Session, user: Usuario, centro: str, codigo: str, talla: str | None = None,
                almacen: str | None = None) -> list[dict]:
    """Kardex de ingresos de un artículo en una bodega."""
    consulta = _base(db, user, centro, None, None).add_columns(
        RecepcionRegistro.fecha, RecepcionRegistro.tipo, RecepcionRegistro.observacion, RecepcionRegistro.usuario_id,
        RecepcionMovimiento.cantidad, RecepcionMovimiento.danada, RecepcionMovimiento.observacion,
        UnidadCarga.id, UnidadCarga.numero, UnidadCarga.etiqueta, Embarque.id, Embarque.codigo,
        PackingList.id, PackingList.numero, Factura.id, Factura.numero, FacturaLinea.oc_numero,
    ).join(UnidadCarga, UnidadCarga.id == RecepcionRegistro.unidad_carga_id) \
        .join(Embarque, Embarque.id == UnidadCarga.embarque_id) \
        .join(PackingList, PackingList.id == PLLinea.pl_id) \
        .where(FacturaLinea.codigo_articulo == codigo) \
        .order_by(RecepcionRegistro.fecha.desc(), RecepcionRegistro.id.desc())
    consulta = consulta.where(FacturaLinea.talla == talla) if talla else consulta.where(FacturaLinea.talla.is_(None))
    if almacen:
        consulta = consulta.where(FacturaLinea.almacen == almacen)
    filas = db.execute(consulta.limit(500)).all()
    usuarios = dict(db.execute(select(Usuario.id, Usuario.nombre).where(
        Usuario.id.in_({f[3] for f in filas if f[3]}))).all()) if filas else {}
    return [{
        "fecha": f[0], "tipo": f[1], "observacion": f[6] or f[2], "usuario": usuarios.get(f[3]),
        "cantidad": cant(f[4]), "danada": cant(f[5]), "unidad_id": f[7], "unidad": f[8] or f[9],
        "embarque_id": f[10], "embarque": f[11], "pl_id": f[12], "pl": f[13], "factura_id": f[14],
        "factura": f[15], "oc": f[16],
    } for f in filas]
