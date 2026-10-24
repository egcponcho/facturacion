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

from app.modelos import ClasificacionProducto, Producto, ProductoComex

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


def _ficha(x: ProductoComex) -> FichaComex:
    c = x.clasificacion
    return FichaComex(producto_id=x.producto_id, estado=x.estado, aprobado=x.aprobado, codigo=x.codigo,
                      sugerido=c.sugerido if c is not None else None, pais_origen=x.pais_origen,
                      pais_procedencia=x.pais_procedencia, descripcion_aduana=x.descripcion_aduana,
                      descripcion_comercial=x.descripcion_comercial, revisado_en=c.revisado_en if c is not None else None)


def fichas(db: Session, producto_ids: Iterable[int | None]) -> dict[int, FichaComex]:
    """{producto: ficha} en una consulta."""
    ids = sorted({i for i in producto_ids if i})
    if not ids:
        return {}
    return {x.producto_id: _ficha(x) for x in db.scalars(
        select(ProductoComex).where(ProductoComex.producto_id.in_(ids))
        .options(selectinload(ProductoComex.producto).selectinload(Producto.clasificacion)))}


def ficha(db: Session, producto_id: int | None) -> FichaComex | None:
    return fichas(db, [producto_id]).get(producto_id) if producto_id else None


def de_articulos(db: Session, articulo_ids: Iterable[int | None]) -> dict[int, FichaComex]:
    """{artículo: la ficha de su producto} (una variante, un pack o un kit usa la de su producto)."""
    from app.modulos.catalogo import servicio as catalogo

    productos = catalogo.productos_de(db, articulo_ids)
    f = fichas(db, productos.values())
    return {a: f[p] for a, p in productos.items() if p in f}


def _de_proveedores(c, proveedores):
    """Sin lista (None), de todos; con lista (aunque esté vacía), solo de esos proveedores."""
    from app.modulos.catalogo import servicio as catalogo

    if proveedores is None:
        return c
    return c.where(ProductoComex.producto_id.in_(catalogo.ids_productos(proveedores=list(proveedores))))


def contar_por_estado(db: Session, proveedores: Iterable[int] | None = None) -> dict[str, int]:
    """{estado de la ficha: cuántos productos} (de esos proveedores, si se da la lista)."""
    return dict(db.execute(_de_proveedores(select(ProductoComex.estado, func.count()), proveedores)
                           .group_by(ProductoComex.estado)).all())


def contar(db: Session, estados: Iterable[str], proveedores: Iterable[int] | None = None,
           revisado_desde: datetime | None = None, revisado_hasta: datetime | None = None) -> int:
    """Cuántas fichas están en esos estados (y, si se dan, revisadas en ese periodo)."""
    c = _de_proveedores(select(func.count()).select_from(ProductoComex).where(ProductoComex.estado.in_(list(estados))),
                        proveedores)
    if revisado_desde is not None or revisado_hasta is not None:
        c = c.join(ClasificacionProducto, ClasificacionProducto.producto_id == ProductoComex.producto_id)
        if revisado_desde is not None:
            c = c.where(ClasificacionProducto.revisado_en >= revisado_desde)
        if revisado_hasta is not None:
            c = c.where(ClasificacionProducto.revisado_en < revisado_hasta)
    return db.scalar(c) or 0


def ids_productos(*, estados: Iterable[str] | None = None, codigo: str | None = None,
                  proveedores: Iterable[int] | None = None) -> Select:
    """`select(id)` de productos por estado de su ficha o por su partida aprobada (contiene esos dígitos)."""
    c = _de_proveedores(select(ProductoComex.producto_id), proveedores)
    if estados is not None:
        c = c.where(ProductoComex.estado.in_(list(estados)))
    if codigo is not None:
        d = digitos(codigo)
        c = c.where(ProductoComex.codigo.like(f"%{d}%")) if d else c.where(false())
    return c


def buscar_documentos(db: Session, q: str, proveedores: Iterable[int] | None = None, limite: int = 6) -> list[dict]:
    """Documentos técnicos (SDS, TDS, COA…) cuyo nombre o tipo coinciden con el texto."""
    from app.modelos import Adjunto, ProductoDocumento
    from app.modulos.comun.texto import filtro_texto

    c = filtro_texto(q, lambda p: [Adjunto.nombre.ilike(p), ProductoDocumento.tipo.ilike(p)])
    cons = select(ProductoDocumento).join(Adjunto, Adjunto.id == ProductoDocumento.adjunto_id).where(c)
    if proveedores is not None:
        from app.modulos.catalogo import servicio as catalogo

        cons = cons.where(ProductoDocumento.producto_id.in_(catalogo.ids_productos(proveedores=list(proveedores))))
    return [{"id": d.id, "nombre": d.nombre, "tipo": d.tipo, "producto_id": d.producto_id}
            for d in db.scalars(cons.limit(limite)).unique()]


def sql_ficha(producto_id) -> dict:
    """Expresiones de la ficha del producto cuyo id es `producto_id` (una columna): estado, tipo de
    producto, país de origen y fecha de revisión, para reportes."""
    def de(col):
        return select(col).where(ProductoComex.producto_id == producto_id).scalar_subquery()

    revisado = (select(ClasificacionProducto.revisado_en).where(ClasificacionProducto.producto_id == producto_id)
                .scalar_subquery())
    return {"estado": de(ProductoComex.estado), "tipo": de(ProductoComex.tipo), "pais_origen": de(ProductoComex.pais_origen),
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


# ---- Datos de la ficha técnica que se imprimen (etiquetas) --------------------------------------
def defs_ficha(db: Session) -> dict[str, dict]:
    """Atributos activos de la ficha técnica: los de cualquier tipo de producto, definidos con datos.
    Una vez por sesión."""
    from app.modelos import AtributoDef

    res = db.info.get("defs_ficha")
    if res is None:
        res = db.info["defs_ficha"] = {
            a.codigo: {"etiqueta": a.etiqueta, "tipo": a.tipo_dato, "unidad": a.unidad,
                       "opciones": {o.codigo: o.etiqueta for o in a.opciones}}
            for a in db.scalars(select(AtributoDef).options(selectinload(AtributoDef.opciones))
                                .where(AtributoDef.activo.is_(True)).order_by(AtributoDef.orden, AtributoDef.codigo))}
    return res


def texto_ficha(d: dict, v):
    """El valor de un atributo de la ficha como se imprime: el nombre de la opción,
    Sí/No, la lista de opciones o la composición; un número queda número."""
    if v is None or v == "" or v == [] or v == {}:
        return None
    if d["tipo"] == "boolean":
        return "Yes" if v else "No"
    if d["tipo"] == "number":
        return v
    if isinstance(v, list):
        return ", ".join(str(d["opciones"].get(x, x)) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k.replace('_', ' ').capitalize()}: {x}" for k, x in v.items() if x not in (None, "")) or None
    return d["opciones"].get(v, v)


def composicion(ficha: dict | None) -> str | None:
    comp = (ficha or {}).get("comp")
    if isinstance(comp, dict):
        partes = [f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in comp.items() if v]
        return "; ".join(partes) or None
    return str(comp) if comp else None


def valores_etiqueta(db: Session, producto_ids: Iterable[int | None]) -> dict[int, dict]:
    """{producto: lo de su ficha que puede imprimir una etiqueta}: descripción comercial, país de
    origen, composición, uso y cada atributo de la ficha («producto.atributo.X»)."""
    ids = sorted({i for i in producto_ids if i})
    if not ids:
        return {}
    defs = defs_ficha(db)
    res = {}
    for p in db.scalars(select(ProductoComex).where(ProductoComex.producto_id.in_(ids))):
        ficha_ = p.ficha or {}
        v = {"producto.descripcion_comercial": p.descripcion_comercial, "producto.pais_origen": p.pais_origen,
             "producto.composicion": composicion(ficha_), "producto.uso": ficha_.get("uso")}
        v.update({f"producto.atributo.{k}": texto_ficha(defs[k], x) for k, x in ficha_.items() if k in defs})
        res[p.producto_id] = v
    return res
