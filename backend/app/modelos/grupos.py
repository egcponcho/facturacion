"""Grupos de producto: un solo árbol de la empresa para agrupar lo que vende
(calzado → calzado técnico → sandalias…), compartido por el etiquetado, las
reglas de empaque y lo que venga (docs/GRUPOS_PRODUCTO.md).

Cada nodo es de una clase:
- FAMILIA: se asigna a mano a grupos de artículos, productos o artículos; puede
  tener subfamilias (hijas FAMILIA) sin límite de niveles.
- CATEGORIA: hoja dentro de una familia que se reconoce sola por condiciones
  sobre los datos del artículo, o se pone a mano en el producto.

Reemplaza a familias_etiquetado y categorias_etiquetado (migración 0081): sus
filas se copiaron 1:1 y `legado_familia_id` / `legado_categoria_id` guardan de
cuál salió cada nodo. Las tablas anteriores quedan congeladas, solo para volver
atrás.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import ahora

CLASES_GRUPO = ("FAMILIA", "CATEGORIA")


class GrupoProducto(DeOrganizacion, Base):
    """Un nodo del árbol de grupos de producto (familia o categoría)."""

    __tablename__ = "grupos_producto"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "codigo", name="uq_grupos_producto_org_codigo"),
        CheckConstraint("clase IN ('FAMILIA', 'CATEGORIA')", name="ck_grupos_producto_clase"),
        # Una categoría siempre está dentro de una familia
        CheckConstraint("clase = 'FAMILIA' OR padre_id IS NOT NULL", name="ck_grupos_producto_categoria_padre"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    clase: Mapped[str] = mapped_column(String(10))
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_producto.id"), index=True)
    # [{"campo": "articulo.descripcion", "op": "contiene", "valor": "sandal"}]: todas deben cumplirse.
    # Una categoría con condiciones se reconoce sola; sin condiciones, solo se pone a mano.
    condiciones: Mapped[list] = mapped_column(JSON, default=list)
    # Los campos habituales del grupo y cuáles son obligatorios ([{"campo": "articulo.talla", "obligatorio": true}])
    campos: Mapped[list] = mapped_column(JSON, default=list)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    # De qué familia o categoría de etiquetado se copió (migración 0081); vacío en los nodos nuevos
    legado_familia_id: Mapped[int | None] = mapped_column(Integer)
    legado_categoria_id: Mapped[int | None] = mapped_column(Integer)

    padre: Mapped["GrupoProducto | None"] = relationship(remote_side=lambda: GrupoProducto.id)

    __mapper_args__ = {"polymorphic_on": "clase", "polymorphic_abstract": True}

    def ruta(self) -> list["GrupoProducto"]:
        """El nodo y sus antecesores, de la raíz a él (sin repetir si hubiera un ciclo)."""
        res, g = [], self
        while g is not None and g not in res:
            res.insert(0, g)
            g = g.padre
        return res

    @property
    def familia(self) -> "GrupoProducto | None":
        """La familia del nodo: él mismo si es una familia; si es una categoría, la familia que la contiene."""
        return self if self.clase == "FAMILIA" else self.padre


class GrupoFamilia(GrupoProducto):
    """Familia (o subfamilia): se asigna a mano a grupos de artículos, productos o artículos."""

    __mapper_args__ = {"polymorphic_identity": "FAMILIA"}


class GrupoCategoria(GrupoProducto):
    """Categoría dentro de una familia: se reconoce por condiciones o se pone a mano en el producto."""

    __mapper_args__ = {"polymorphic_identity": "CATEGORIA"}

    # La familia que la contiene (el padre del nodo), con el nombre que usa el etiquetado
    familia_id = synonym("padre_id")
