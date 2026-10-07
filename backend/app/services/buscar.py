"""Búsqueda global: un número o un texto encuentra el registro sin saber en
qué módulo está.

Busca con la misma regla inteligente de las listas (`common.filtro_texto`:
sin mayúsculas ni acentos, términos en cualquier orden, varios códigos a la
vez) en órdenes de compra y sus posiciones (SKU, UPC, estilo, color),
productos, artículos, facturas, packing lists, embarques (BL/AWB), unidades de
carga (contenedor, sello), proveedores, marcas y documentos adjuntos.

Cada grupo respeta los permisos del usuario y, para un proveedor, solo sus
propios datos. Cada resultado trae la ruta de la pantalla que lo abre.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Archivo,
    Articulo,
    Embarque,
    Factura,
    Marca,
    OrdenCompra,
    PackingList,
    PosicionOC,
    Producto,
    ProductoDocumento,
    Proveedor,
    UnidadCarga,
)
from .cantidades import nombre_factura
from .common import filtro_texto, proveedor_filtro, terminos, tiene

POR_GRUPO = 6


def _filas(db: Session, consulta, limite: int = POR_GRUPO):
    return db.execute(consulta.limit(limite)).unique().all()


def buscar(db: Session, user, q: str | None, limite: int = POR_GRUPO) -> dict:
    q = (q or "").strip()
    if not terminos(q) or len(q) < 2:
        return {"q": q, "grupos": [], "total": 0}
    prov = proveedor_filtro(user)
    grupos: list[dict] = []

    def grupo(tipo: str, items: list[dict], ver_todos: str | None = None) -> None:
        if items:
            grupos.append({"tipo": tipo, "items": items, "ver_todos": ver_todos})

    if tiene(user, "oc.ver"):
        # Órdenes por número; las posiciones llevan a su OC (SKU, UPC, estilo, color)
        c = filtro_texto(q, lambda p: [OrdenCompra.numero.ilike(p)])
        cons = select(OrdenCompra).where(c).order_by(OrdenCompra.fecha.desc().nullslast())
        if prov:
            cons = cons.where(OrdenCompra.proveedor_id == prov)
        ocs = {o.id: o for (o,) in _filas(db, cons, limite)}
        cp = filtro_texto(q, lambda p: [PosicionOC.codigo_sap.ilike(p), PosicionOC.upc.ilike(p), PosicionOC.estilo.ilike(p),
                                        PosicionOC.color.ilike(p), PosicionOC.descripcion.ilike(p)])
        cons = select(PosicionOC).join(OrdenCompra).where(cp)
        if prov:
            cons = cons.where(OrdenCompra.proveedor_id == prov)
        coincidencias: dict[int, str] = {}
        for (p,) in _filas(db, cons, limite * 4):
            if len(ocs) >= limite and p.oc_id not in ocs:
                continue
            ocs.setdefault(p.oc_id, p.oc)
            coincidencias.setdefault(p.oc_id, " · ".join(x for x in (p.codigo_sap, p.estilo, p.color) if x))
        grupo("ordenes", [{"id": o.id, "titulo": o.numero, "sub": " · ".join(x for x in (o.proveedor.nombre if o.proveedor else "",
                                                                                         coincidencias.get(o.id, "")) if x),
                           "estado": "RELEASED" if o.liberada else "PENDING", "ruta": f"/ordenes?q={o.numero}"}
                          for o in list(ocs.values())[:limite]], f"/ordenes?q={q}")

        c = filtro_texto(q, lambda p: [Factura.numero.ilike(p)])
        cons = select(Factura).where(c).order_by(Factura.creado_en.desc())
        if prov:
            cons = cons.where(Factura.proveedor_id == prov)
        grupo("facturas", [{"id": f.id, "titulo": nombre_factura(f), "sub": f.proveedor.nombre if f.proveedor else "",
                            "estado": f.estado, "ruta": f"/facturas/{f.id}"} for (f,) in _filas(db, cons, limite)], f"/facturas?q={q}")

        c = filtro_texto(q, lambda p: [PackingList.numero.ilike(p)])
        cons = select(PackingList).join(Factura).where(c).order_by(PackingList.creado_en.desc())
        if prov:
            cons = cons.where(Factura.proveedor_id == prov)
        grupo("packing_lists", [{"id": pl.id, "titulo": pl.numero, "sub": nombre_factura(pl.factura), "estado": pl.estado,
                                 "ruta": f"/packing-lists/{pl.id}"} for (pl,) in _filas(db, cons, limite)])

    if tiene(user, "producto.ver"):
        c = filtro_texto(q, lambda p: [Producto.estilo.ilike(p), Producto.color.ilike(p), Producto.nombre.ilike(p),
                                       Producto.codigo_generico.ilike(p), Producto.codigo.ilike(p)])
        cons = select(Producto).where(c).order_by(Producto.actualizado_en.desc().nullslast())
        if prov:
            cons = cons.where(Producto.proveedor_id == prov)
        productos = {p.id: p for (p,) in _filas(db, cons, limite)}
        # Un SKU o UPC de un artículo lleva a su producto
        c = filtro_texto(q, lambda p: [Articulo.sku.ilike(p), Articulo.upc.ilike(p), Articulo.sku_proveedor.ilike(p)])
        cons = select(Articulo).where(c, Articulo.producto_id.is_not(None))
        if prov:
            cons = cons.where(Articulo.proveedor_id == prov)
        for (a,) in _filas(db, cons, limite):
            if len(productos) < limite:
                productos.setdefault(a.producto_id, a.producto)
        grupo("productos", [{"id": p.id, "titulo": " · ".join(x for x in (p.estilo, p.color) if x) or p.nombre or f"#{p.id}",
                             "sub": " · ".join(x for x in (p.nombre, p.codigo) if x), "estado": p.estado,
                             "ruta": f"/productos/{p.id}"} for p in productos.values()], f"/productos?q={q}&estado=")

    if tiene(user, "transporte.gestionar"):
        c = filtro_texto(q, lambda p: [Embarque.codigo.ilike(p), Embarque.documento_numero.ilike(p)])
        cons = select(Embarque).where(c).order_by(Embarque.etd.desc().nullslast())
        grupo("embarques", [{"id": e.id, "titulo": e.codigo, "sub": " · ".join(x for x in (e.documento_numero, e.puerto_origen,
                                                                                          e.puerto_destino) if x),
                             "estado": e.estado, "ruta": f"/transporte/embarques/{e.id}"} for (e,) in _filas(db, cons, limite)])
        c = filtro_texto(q, lambda p: [UnidadCarga.numero.ilike(p), UnidadCarga.etiqueta.ilike(p), UnidadCarga.sello.ilike(p)])
        cons = select(UnidadCarga).where(c)
        grupo("unidades", [{"id": u.id, "titulo": u.numero or u.etiqueta or f"#{u.id}",
                            "sub": " · ".join(x for x in (u.tipo, u.embarque.codigo if u.embarque else "") if x),
                            "ruta": f"/transporte/embarques/{u.embarque_id}"} for (u,) in _filas(db, cons, limite) if u.embarque_id])

    if tiene(user, "catalogos.ver") and not prov:
        c = filtro_texto(q, lambda p: [Proveedor.codigo.ilike(p), Proveedor.nombre.ilike(p), Proveedor.razon_social.ilike(p)])
        grupo("proveedores", [{"id": p.id, "titulo": p.nombre, "sub": p.codigo, "ruta": f"/mantenimiento?catalogo=proveedores&q={p.codigo}"}
                              for (p,) in _filas(db, select(Proveedor).where(c), limite)])
        c = filtro_texto(q, lambda p: [Marca.codigo.ilike(p), Marca.nombre.ilike(p)])
        grupo("marcas", [{"id": m.id, "titulo": m.nombre, "sub": m.codigo, "ruta": f"/mantenimiento?catalogo=marcas&q={m.codigo}"}
                         for (m,) in _filas(db, select(Marca).where(c), limite)])

    docs = []
    if tiene(user, "oc.ver"):
        c = filtro_texto(q, lambda p: [Archivo.nombre.ilike(p), Archivo.tipo.ilike(p)])
        cons = select(Archivo).join(Factura).where(c)
        if prov:
            cons = cons.where(Factura.proveedor_id == prov)
        docs += [{"id": f"f{a.id}", "titulo": a.nombre, "sub": a.tipo or "", "ruta": f"/facturas/{a.factura_id}?tab=archivos"}
                 for (a,) in _filas(db, cons, limite)]
    if tiene(user, "producto.ver"):
        c = filtro_texto(q, lambda p: [ProductoDocumento.nombre.ilike(p), ProductoDocumento.tipo.ilike(p)])
        cons = select(ProductoDocumento).join(Producto).where(c)
        if prov:
            cons = cons.where(Producto.proveedor_id == prov)
        docs += [{"id": f"p{d.id}", "titulo": d.nombre, "sub": d.tipo or "", "ruta": f"/productos/{d.producto_id}"}
                 for (d,) in _filas(db, cons, limite)]
    grupo("documentos", docs[:limite])
    return {"q": q, "grupos": grupos, "total": sum(len(g["items"]) for g in grupos)}
