"""Listas de empaque: líneas, grupos de cajas, tipos de empaque, plantillas y
recepción.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import Cantidad, ahora, cant

if TYPE_CHECKING:
    from app.modelos.facturacion import Factura, FacturaLinea
    from app.modelos.transporte import UnidadCarga


# Qué tipos de empaque puede llevar dentro cada tipo (relación configurable)

tipo_empaque_contiene = Table(
    "tipo_empaque_contiene", Base.metadata,
    Column("padre_id", ForeignKey("tipos_empaque.id", ondelete="CASCADE"), primary_key=True),
    Column("hijo_id", ForeignKey("tipos_empaque.id", ondelete="CASCADE"), primary_key=True),
)


class PackingList(DeOrganizacion, Base):
    __tablename__ = "packing_lists"
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    numero: Mapped[str] = mapped_column(String(40))  # PL-001 por defecto; el proveedor puede poner el suyo
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    unidad_carga_id: Mapped[int | None] = mapped_column(ForeignKey("unidades_carga.id"), index=True)
    asignacion: Mapped[str | None] = mapped_column(String(12))  # TENTATIVA | CONFIRMADA
    observaciones: Mapped[str | None] = mapped_column(Text)
    recolectado_en: Mapped[date | None] = mapped_column(Date)  # retiro en bodega del proveedor
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    factura: Mapped[Factura] = relationship(back_populates="packing_lists")
    lineas: Mapped[list["PLLinea"]] = relationship(
        back_populates="pl", cascade="all, delete-orphan", order_by="PLLinea.id"
    )
    grupos: Mapped[list["GrupoCajas"]] = relationship(
        back_populates="pl", cascade="all, delete-orphan", order_by="GrupoCajas.id"
    )
    unidad: Mapped["UnidadCarga | None"] = relationship(back_populates="packing_lists")


class PLLinea(DeOrganizacion, Base):
    """Parte de una línea de factura dentro de un PL. Puede haber varias
    partes de la misma línea (resultado de dividir)."""

    __tablename__ = "pl_lineas"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    factura_linea_id: Mapped[int] = mapped_column(ForeignKey("factura_lineas.id"), index=True)
    cantidad: Mapped[float] = mapped_column(Cantidad)

    pl: Mapped[PackingList] = relationship(back_populates="lineas")
    factura_linea: Mapped[FacturaLinea] = relationship()
    items: Mapped[list["GrupoCajasItem"]] = relationship(back_populates="pl_linea")
    recepcion: Mapped["RecepcionLinea | None"] = relationship(
        back_populates="pl_linea", cascade="all, delete-orphan", uselist=False
    )

    @validates("cantidad")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class GrupoCajas(DeOrganizacion, Base):
    """Nodo del árbol físico de empaque: N unidades iguales de un tipo de
    empaque (caja, inner pack, pallet…). `num_cajas` es el total de esas
    unidades en el PL; si tiene padre, se reparten por igual entre las
    unidades del padre (40 inner en 10 cajas = 4 por caja). Lleva producto
    (items, por unidad) y/o empaques hijos.

    Pesos por unidad, calculados de abajo hacia arriba: neto = artículos
    (peso de cada artículo × cantidad) + neto de los hijos; bruto = neto +
    tara propia + tara de los hijos. Si falta el peso de un artículo, el neto
    se escribe a mano (neto_manual). El volumen es el de las medidas
    exteriores: lo que va dentro de otro empaque no suma volumen."""

    __tablename__ = "grupos_cajas"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    num_cajas: Mapped[int] = mapped_column(Integer)
    largo: Mapped[float | None] = mapped_column(Float)  # cm
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    peso_neto_caja: Mapped[float | None] = mapped_column(Float)  # kg
    peso_bruto_caja: Mapped[float | None] = mapped_column(Float)
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantillas_caja.id"))
    plantilla_nombre: Mapped[str | None] = mapped_column(String(100))
    es_parcial: Mapped[bool] = mapped_column(Boolean, default=False)
    peso_estimado: Mapped[bool] = mapped_column(Boolean, default=False)
    observacion: Mapped[str | None] = mapped_column(String(300))
    tipo_empaque_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_empaque.id"))
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_cajas.id", ondelete="SET NULL"), index=True)
    tara: Mapped[float | None] = mapped_column(Float)  # kg de una unidad de este empaque vacía
    neto_manual: Mapped[float | None] = mapped_column(Float)  # neto por unidad si falta el peso de algún artículo

    pl: Mapped[PackingList] = relationship(back_populates="grupos")
    tipo_empaque: Mapped["TipoEmpaque | None"] = relationship()
    padre: Mapped["GrupoCajas | None"] = relationship(remote_side=lambda: GrupoCajas.id, back_populates="hijos")
    hijos: Mapped[list["GrupoCajas"]] = relationship(back_populates="padre", order_by="GrupoCajas.id")
    items: Mapped[list["GrupoCajasItem"]] = relationship(
        back_populates="grupo", cascade="all, delete-orphan", order_by="GrupoCajasItem.id"
    )


class GrupoCajasItem(DeOrganizacion, Base):
    __tablename__ = "grupo_cajas_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos_cajas.id"), index=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), index=True)
    cantidad_por_caja: Mapped[float] = mapped_column(Cantidad)

    grupo: Mapped[GrupoCajas] = relationship(back_populates="items")
    pl_linea: Mapped[PLLinea] = relationship(back_populates="items")

    @validates("cantidad_por_caja")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class TipoEmpaque(DeOrganizacion, Base):
    """Unidad logística configurable (inner pack, caja, pallet, bolsa, tambor…).
    Nada está fijo en el código: cada empresa define sus tipos, qué puede
    contener cada uno, su tara, medidas y límites. Un PL se arma como un árbol
    de empaques dentro de empaques con el producto en las hojas."""

    __tablename__ = "tipos_empaque"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_tipos_empaque_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(100))
    nivel: Mapped[int] = mapped_column(Integer, default=1)  # 1 = el más interno
    prefijo: Mapped[str | None] = mapped_column(String(6))  # etiqueta de cada unidad: C1, PK1, P1
    # BULTO: cuenta como bulto del documento; INTERIOR: va dentro de un bulto;
    # SOPORTE: lleva bultos (pallet, rack)
    cuenta_como: Mapped[str] = mapped_column(String(10), default="BULTO")
    uom: Mapped[str | None] = mapped_column(String(10))
    largo: Mapped[float | None] = mapped_column(Float)  # cm, exteriores
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    tara: Mapped[float | None] = mapped_column(Float)  # kg del empaque vacío
    peso_max: Mapped[float | None] = mapped_column(Float)  # kg brutos por unidad
    max_unidades: Mapped[int | None] = mapped_column(Integer)  # unidades de producto por unidad
    max_contenido: Mapped[int | None] = mapped_column(Integer)  # empaques internos por unidad
    contiene_productos: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_productos: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_tallas: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_oc: Mapped[bool] = mapped_column(Boolean, default=True)
    identificador: Mapped[str | None] = mapped_column(String(15))  # SERIAL | CODIGO_BARRAS | SSCC
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    contiene: Mapped[list["TipoEmpaque"]] = relationship(
        secondary=tipo_empaque_contiene, primaryjoin=lambda: TipoEmpaque.id == tipo_empaque_contiene.c.padre_id,
        secondaryjoin=lambda: TipoEmpaque.id == tipo_empaque_contiene.c.hijo_id, order_by="TipoEmpaque.nivel")


class PlantillaCaja(DeOrganizacion, Base):
    __tablename__ = "plantillas_caja"
    __table_args__ = (UniqueConstraint("proveedor_id", "nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    cantidad_por_caja: Mapped[float] = mapped_column(Cantidad)
    unidad: Mapped[str] = mapped_column(String(5))
    largo: Mapped[float | None] = mapped_column(Float)
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    # Solo la tara del empaque: el peso neto sale del peso de cada artículo
    tara: Mapped[float | None] = mapped_column(Float)
    tipo_empaque_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_empaque.id"))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    tipo_empaque: Mapped["TipoEmpaque | None"] = relationship()

    @validates("cantidad_por_caja")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class RecepcionLinea(DeOrganizacion, Base):
    __tablename__ = "recepciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), unique=True)
    cantidad_recibida: Mapped[float] = mapped_column(Cantidad)
    cantidad_danada: Mapped[float] = mapped_column(Cantidad, default=0)
    observacion: Mapped[str | None] = mapped_column(String(300))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    pl_linea: Mapped[PLLinea] = relationship(back_populates="recepcion")

    @validates("cantidad_recibida", "cantidad_danada")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar
