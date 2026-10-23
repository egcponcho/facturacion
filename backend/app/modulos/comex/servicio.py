"""Lo que los demás módulos leen del comercio exterior de un producto.

La OC y la factura toman de aquí la partida aprobada, el país de origen y la
descripción aduanera; los tableros, cuántas fichas hay en cada estado. Como el
catálogo, devuelve fichas armadas (datos simples) y nunca objetos de la base.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, false, func, select
from sqlalchemy.orm import Session, selectinload

from app.modelos import ClasificacionProducto, Producto

# Estados de la ficha técnica: borrador (incompleto o completo) → enviada a revisión → aprobada o devuelta
ESTADOS = {"borrador": "Draft", "sugerida": "Draft · complete", "revision": "In review", "aprobado": "Approved",
           "corregido": "Corrected", "observado": "Returned"}
APROBADOS = ("aprobado", "corregido")
BORRADORES = ("borrador", "sugerida", "observado")
PENDIENTES = BORRADORES + ("revision",)


def digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def fmt_codigo(c) -> str:
    """«640419» → «6404.19»; «64041990» → «6404.19.90»."""
    d = digitos(c)
    if len(d) <= 4:
        return d
    o = d[:4] + "." + d[4:6]
    for i in range(6, len(d), 2):
        o += "." + d[i:i + 2]
    return o


@dataclass(frozen=True, slots=True)
class FichaComex:
    """La ficha de comercio exterior de un producto, como la usan la OC, la factura y los tableros."""

    producto_id: int
    estado: str
    aprobado: bool
    codigo: str | None  # HS6 aprobado (dígitos)
    sugerido: str | None  # HS6 que sugirió el motor, mientras no esté aprobado
    pais_origen: str | None
    pais_procedencia: str | None
    descripcion_aduana: str | None
    descripcion_comercial: str | None
    revisado_en: datetime | None

    @property
    def estado_txt(self) -> str:
        return ESTADOS.get(self.estado, self.estado)

    @property
    def partida(self) -> str | None:
        """Lo que va en la OC y la factura: la subpartida de 6 dígitos aprobada. El país destino de la
        OC es solo una proyección, así que nunca se usa la línea nacional de un país ni el SAC regional."""
        d = digitos(self.codigo)
        return fmt_codigo(d[:6]) if self.aprobado and len(d) >= 6 else None

    def resumen(self) -> dict:
        """Resumen corto para mostrar junto al artículo en la OC o la factura."""
        return {"estado": self.estado, "texto": self.estado_txt, "producto_id": self.producto_id,
                "codigo": fmt_codigo(self.codigo) if self.aprobado else None,
                "sugerido": fmt_codigo(self.sugerido) if self.sugerido and not self.aprobado else None}


SIN_PRODUCTO = {"estado": None, "texto": "No product"}


def _ficha(p: Producto) -> FichaComex:
    c = p.clasificacion
    return FichaComex(producto_id=p.id, estado=p.estado, aprobado=p.aprobado, codigo=p.codigo,
                      sugerido=c.sugerido if c is not None else None, pais_origen=p.pais_origen,
                      pais_procedencia=p.pais_procedencia, descripcion_aduana=p.descripcion_aduana,
                      descripcion_comercial=p.descripcion_comercial, revisado_en=c.revisado_en if c is not None else None)


def fichas(db: Session, producto_ids: Iterable[int | None]) -> dict[int, FichaComex]:
    """{producto: ficha} en una consulta."""
    ids = sorted({i for i in producto_ids if i})
    if not ids:
        return {}
    return {p.id: _ficha(p) for p in db.scalars(select(Producto).where(Producto.id.in_(ids))
                                                 .options(selectinload(Producto.clasificacion)))}


def ficha(db: Session, producto_id: int | None) -> FichaComex | None:
    return fichas(db, [producto_id]).get(producto_id) if producto_id else None


def _de_proveedores(c, proveedores):
    """Sin lista (None), de todos; con lista (aunque esté vacía), solo de esos proveedores."""
    return c if proveedores is None else c.where(Producto.proveedor_id.in_(list(proveedores)))


def contar_por_estado(db: Session, proveedores: Iterable[int] | None = None) -> dict[str, int]:
    """{estado de la ficha: cuántos productos} (de esos proveedores, si se da la lista)."""
    return dict(db.execute(_de_proveedores(select(Producto.estado, func.count()), proveedores)
                           .group_by(Producto.estado)).all())


def contar(db: Session, estados: Iterable[str], proveedores: Iterable[int] | None = None,
           revisado_desde: datetime | None = None, revisado_hasta: datetime | None = None) -> int:
    """Cuántas fichas están en esos estados (y, si se dan, revisadas en ese periodo)."""
    c = _de_proveedores(select(func.count()).select_from(Producto).where(Producto.estado.in_(list(estados))), proveedores)
    if revisado_desde is not None or revisado_hasta is not None:
        c = c.join(ClasificacionProducto, ClasificacionProducto.producto_id == Producto.id)
        if revisado_desde is not None:
            c = c.where(ClasificacionProducto.revisado_en >= revisado_desde)
        if revisado_hasta is not None:
            c = c.where(ClasificacionProducto.revisado_en < revisado_hasta)
    return db.scalar(c) or 0


def ids_productos(*, estados: Iterable[str] | None = None, codigo: str | None = None,
                  proveedores: Iterable[int] | None = None) -> Select:
    """`select(id)` de productos por estado de su ficha o por su partida aprobada (contiene esos dígitos)."""
    c = _de_proveedores(select(Producto.id), proveedores)
    if estados is not None:
        c = c.where(Producto.estado.in_(list(estados)))
    if codigo is not None:
        d = digitos(codigo)
        c = c.where(Producto.codigo.like(f"%{d}%")) if d else c.where(false())
    return c


def buscar_documentos(db: Session, q: str, proveedores: Iterable[int] | None = None, limite: int = 6) -> list[dict]:
    """Documentos técnicos (SDS, TDS, COA…) cuyo nombre o tipo coinciden con el texto."""
    from app.modelos import Adjunto, ProductoDocumento
    from app.modulos.comun.texto import filtro_texto

    c = filtro_texto(q, lambda p: [Adjunto.nombre.ilike(p), ProductoDocumento.tipo.ilike(p)])
    cons = _de_proveedores(select(ProductoDocumento).join(Producto).join(Adjunto, Adjunto.id == ProductoDocumento.adjunto_id)
                           .where(c), proveedores)
    return [{"id": d.id, "nombre": d.nombre, "tipo": d.tipo, "producto_id": d.producto_id}
            for d in db.scalars(cons.limit(limite)).unique()]


def sql_ficha(producto_id) -> dict:
    """Expresiones de la ficha del producto cuyo id es `producto_id` (una columna): estado, tipo de
    producto, país de origen y fecha de revisión, para reportes."""
    def de(col):
        return select(col).where(Producto.id == producto_id).scalar_subquery()

    revisado = (select(ClasificacionProducto.revisado_en).where(ClasificacionProducto.producto_id == producto_id)
                .scalar_subquery())
    return {"estado": de(Producto.estado), "tipo": de(Producto.tipo), "pais_origen": de(Producto.pais_origen),
            "revisado_en": revisado}


def sin_marca(texto: str | None, marca: str | None = None) -> str | None:
    """Descripción aduanera sin la marca: la marca va en su propio campo en la factura y el
    packing list, así no se repite."""
    if not texto:
        return texto
    t = re.sub(r"[,;]?\s*\bMARCA\s+[^,;]+", "", str(texto), flags=re.I)
    for m in [x for x in {marca or ""} if x.strip()]:
        t = re.sub(rf"[,;]?\s*\b{re.escape(m.strip())}\b", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" ,;") or None
