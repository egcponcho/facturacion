"""Resumen del módulo de productos (como el tablero de productos del ERP):
cuánto hay, en qué estado está, cómo se reparte por familia, qué falta por
completar, lo último modificado y la puesta en marcha (lo que hay que
configurar antes de crear productos). Cada cifra abre el catálogo filtrado.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modelos import Articulo, AtributoVariante, EscalaTalla, GrupoFamilia, GrupoProducto, Marca, Prepack, Producto, Proveedor, Usuario
from app.modulos.acceso.permisos import tiene
from app.modulos.productos import productos as svc

RECIENTES = 6
FAMILIAS = 8


def resumen(db: Session, user: Usuario) -> dict:
    base, prov = svc._consulta_productos(db, user, {})
    sub = base.subquery()
    ids = select(sub.c.id)
    total = db.scalar(select(func.count()).select_from(sub)) or 0
    por_estado = dict(db.execute(select(sub.c.estado, func.count()).group_by(sub.c.estado)).all())
    activos = select(Articulo).where(Articulo.activo.is_(True), Articulo.producto_id.in_(ids)).subquery()
    variantes = db.scalar(select(func.count()).select_from(activos)) or 0
    sin_codigo_barras = db.scalar(select(func.count()).select_from(activos).where(
        func.coalesce(activos.c.upc, "") == "")) or 0
    sin_variantes = db.scalar(select(func.count()).select_from(sub).where(
        ~sub.c.id.in_(select(Articulo.producto_id).where(Articulo.producto_id.is_not(None))))) or 0
    sin_familia = db.scalar(select(func.count()).select_from(sub).where(sub.c.grupo_producto_id.is_(None))) or 0
    familias = db.execute(select(GrupoProducto.id, GrupoProducto.codigo, GrupoProducto.nombre, func.count(sub.c.id))
                          .join(sub, sub.c.grupo_producto_id == GrupoProducto.id)
                          .group_by(GrupoProducto.id, GrupoProducto.codigo, GrupoProducto.nombre)
                          .order_by(func.count(sub.c.id).desc(), GrupoProducto.nombre)).all()
    recientes = db.scalars(base.order_by(Producto.actualizado_en.desc(), Producto.id.desc()).limit(RECIENTES)).all()
    res = {
        "total": total, "variantes": variantes, "sin_variantes": sin_variantes, "sin_familia": sin_familia,
        "sin_codigo_barras": sin_codigo_barras,
        "por_estado": {
            # Partición exacta (suma el total); «observado» es un borrador devuelto
            "borradores": sum(por_estado.get(e, 0) for e in svc.BORRADORES if e != "observado"),
            "revision": por_estado.get("revision", 0),
            "observado": por_estado.get("observado", 0),
            "aprobados": sum(por_estado.get(e, 0) for e in svc.APROBADOS),
        },
        "bloquean": len(svc.ids_bloquean_facturas(db, prov)),
        "por_familia": [{"id": i, "codigo": c, "nombre": n, "productos": k} for i, c, n, k in familias[:FAMILIAS]],
        "otras_familias": sum(k for *_, k in familias[FAMILIAS:]),
        "recientes": [{"id": p.id, "codigo": p.codigo_generico, "nombre": p.nombre or p.descripcion_comercial,
                       "estado": p.estado, "actualizado_en": p.actualizado_en,
                       "familia": p.grupo_producto.nombre if p.grupo_producto else None} for p in recientes],
        "configuracion": None,
    }
    # Puesta en marcha: solo para quien configura los datos maestros
    if tiene(user, "catalogos.ver"):
        def contar(modelo, *cond):
            return db.scalar(select(func.count()).select_from(modelo).where(*cond)) or 0

        res["configuracion"] = {
            "familias": contar(GrupoFamilia, GrupoFamilia.activa.is_(True)),
            "atributos_variante": contar(AtributoVariante),
            "escalas": contar(EscalaTalla),
            "marcas": contar(Marca),
            "proveedores": contar(Proveedor),
            "compuestos": contar(Prepack, Prepack.activo.is_(True)),
        }
    return res
