"""Facturas comerciales, sus líneas y archivos adjuntos.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.db import Base
from app.modelos.base import Cantidad, ahora, cant

if TYPE_CHECKING:
    from app.modelos.compras import PosicionOC
    from app.modelos.empaque import PackingList
    from app.modelos.maestros import Proveedor


class Factura(Base):
    __tablename__ = "facturas"
    __table_args__ = (
        # Número único por proveedor (se ignora en facturas canceladas)
        Index(
            "ux_factura_numero",
            "proveedor_id",
            "numero",
            unique=True,
            sqlite_where=text("numero IS NOT NULL AND estado <> 'CANCELADA'"),
            postgresql_where=text("numero IS NOT NULL AND estado <> 'CANCELADA'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    numero: Mapped[str | None] = mapped_column(String(50))
    fecha: Mapped[date | None] = mapped_column(Date)
    moneda: Mapped[str] = mapped_column(String(3))
    incoterm: Mapped[str | None] = mapped_column(String(10))
    sociedad: Mapped[str] = mapped_column(String(10))
    centro: Mapped[str | None] = mapped_column(String(10))
    centro_destino: Mapped[str | None] = mapped_column(String(10))
    condiciones: Mapped[str | None] = mapped_column(String(200))
    observaciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    finalizado_en: Mapped[datetime | None] = mapped_column(DateTime)

    proveedor: Mapped[Proveedor] = relationship()
    lineas: Mapped[list["FacturaLinea"]] = relationship(
        back_populates="factura", cascade="all, delete-orphan", order_by="FacturaLinea.id"
    )
    packing_lists: Mapped[list["PackingList"]] = relationship(
        back_populates="factura", order_by="PackingList.id"
    )


class FacturaLinea(Base):
    __tablename__ = "factura_lineas"
    __table_args__ = (UniqueConstraint("factura_id", "posicion_oc_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    posicion_oc_id: Mapped[int] = mapped_column(ForeignKey("posiciones_oc.id"), index=True)
    cantidad: Mapped[float] = mapped_column(Cantidad)
    precio_unitario: Mapped[float] = mapped_column(Float)
    precio_oc: Mapped[float] = mapped_column(Float)
    motivo_precio: Mapped[str | None] = mapped_column(String(300))
    # Copia de los datos de la OC al momento de facturar (trazabilidad)
    oc_numero: Mapped[str] = mapped_column(String(30))
    almacen: Mapped[str | None] = mapped_column(String(10))
    posicion: Mapped[str] = mapped_column(String(10))
    codigo_sap: Mapped[str] = mapped_column(String(40))
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(40))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    unidad: Mapped[str] = mapped_column(String(5))
    marca: Mapped[str | None] = mapped_column(String(10))
    categoria: Mapped[str | None] = mapped_column(String(10))
    tipo_empaque: Mapped[str] = mapped_column(String(10), default="SOLIDO")
    casepack: Mapped[int | None] = mapped_column(Integer)
    inner_pack: Mapped[int | None] = mapped_column(Integer)
    prepack: Mapped[str | None] = mapped_column(String(30))
    unidades_por_caja: Mapped[int | None] = mapped_column(Integer)
    centro_destino: Mapped[str | None] = mapped_column(String(10))
    # Datos de aduana (editables en la factura)
    pais_origen: Mapped[str | None] = mapped_column(String(3))
    partida_arancelaria: Mapped[str | None] = mapped_column(String(20))
    descripcion_comercial: Mapped[str | None] = mapped_column(String(300))

    factura: Mapped[Factura] = relationship(back_populates="lineas")
    posicion_oc: Mapped[PosicionOC] = relationship()

    @validates("cantidad")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class Archivo(Base):
    __tablename__ = "archivos"
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))  # FACTURA_OFICIAL | OTRO
    nombre: Mapped[str] = mapped_column(String(300))
    ruta: Mapped[str] = mapped_column(String(500))
    tamano: Mapped[int] = mapped_column(Integer)
    subido_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
