"""Transporte: transportistas, tipos de unidad, puertos, lead times, embarques y
unidades de carga.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.modelos.base import ahora

if TYPE_CHECKING:
    from app.modelos.empaque import PackingList
    from app.modelos.maestros import Sociedad


transportista_sociedades = Table(
    "transportista_sociedades", Base.metadata,
    Column("transportista_id", ForeignKey("transportistas.id", ondelete="CASCADE"), primary_key=True),
    Column("sociedad_id", ForeignKey("sociedades.id", ondelete="CASCADE"), primary_key=True),
)


class Transportista(Base):
    """Naviera, aerolínea o empresa de transporte terrestre registrada, con
    las sociedades para las que puede trabajar."""

    __tablename__ = "transportistas"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(150))
    tipo: Mapped[str] = mapped_column(String(12))  # MARITIMO | AEREO | TERRESTRE | MULTIMODAL
    codigo_internacional: Mapped[str | None] = mapped_column(String(10))  # SCAC o prefijo IATA
    id_fiscal: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(2))
    contacto: Mapped[str | None] = mapped_column(String(120))
    correos: Mapped[str | None] = mapped_column(String(500))
    telefono: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sociedades: Mapped[list["Sociedad"]] = relationship(secondary=transportista_sociedades, order_by="Sociedad.codigo")


class TipoUnidad(Base):
    """Tipo de unidad de carga por modo de transporte (contenedores, LCL,
    guía aérea, camión…) con su capacidad nominal."""

    __tablename__ = "tipos_unidad"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    modo: Mapped[str] = mapped_column(String(12))  # MARITIMO | AEREO | TERRESTRE
    modalidad: Mapped[str] = mapped_column(String(10))  # FCL | LCL | AEREO | FTL | LTL
    capacidad_cbm: Mapped[float | None] = mapped_column(Float)
    capacidad_kg: Mapped[float | None] = mapped_column(Float)
    requiere_sello: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class RegionLeadTime(Base):
    """Región de origen (Asia, Centroamérica…): agrupa países para filtrar,
    comparar y para que un plan de lead time aplique a toda la región."""

    __tablename__ = "regiones_leadtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    predeterminada: Mapped[bool] = mapped_column(Boolean, default=False)  # para orígenes sin región
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class PasoLeadTime(Base):
    """Catálogo de pasos de lead time (Booking, Liberación, XF, ETD, ETA,
    Aduana…). Cada empresa crea los suyos. `hito` enlaza el paso con una fecha
    que el sistema mide (liberación logística, XF, salida, arribo, entrega,
    ingreso, tienda); un paso sin hito es solo de planificación."""

    __tablename__ = "pasos_leadtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    hito: Mapped[str | None] = mapped_column(String(15))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ReglaLeadTime(Base):
    """Configuración de lead time de un nivel geográfico: GLOBAL, REGION, PAIS
    o PUERTO. Hereda la del nivel superior (Puerto > País > Región > Global) y
    define solo lo que cambia: pasos que agrega, sobrescribe o quita, y si
    quiere, otro orden. `pasos` es JSON:
        {"pasos": [{"paso", "ref", "dias", "habiles", "modo", "quitar"}], "orden": [códigos] | null}
    `dias` es relativo al paso de referencia (negativo = antes)."""

    __tablename__ = "reglas_leadtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    nivel: Mapped[str] = mapped_column(String(10))  # GLOBAL | REGION | PAIS | PUERTO
    region: Mapped[str | None] = mapped_column(String(10))
    pais: Mapped[str | None] = mapped_column(String(2))
    puerto: Mapped[str | None] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(100))
    pasos: Mapped[str] = mapped_column(Text, default="{}")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Puerto(Base):
    __tablename__ = "puertos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)  # UN/LOCODE
    nombre: Mapped[str] = mapped_column(String(100))
    pais: Mapped[str] = mapped_column(String(2))
    tipo: Mapped[str] = mapped_column(String(12), default="MARITIMO")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Embarque(Base):
    """Existe desde la planificación (booking), antes de tener BL/AWB."""

    __tablename__ = "embarques"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    tipo_transporte: Mapped[str] = mapped_column(String(12))  # MARITIMO | AEREO | TERRESTRE
    documento_numero: Mapped[str | None] = mapped_column(String(50))  # BL / AWB / CP
    transportista_id: Mapped[int | None] = mapped_column(ForeignKey("transportistas.id"), index=True)
    transportista: Mapped[str | None] = mapped_column(String(150))  # nombre al momento de asignarlo
    puerto_origen: Mapped[str | None] = mapped_column(String(10))  # códigos del catálogo de puertos
    puerto_destino: Mapped[str | None] = mapped_column(String(10))
    centro: Mapped[str | None] = mapped_column(String(10), index=True)  # centro al que llega; su puerto debe coincidir
    etd: Mapped[date | None] = mapped_column(Date, index=True)
    eta: Mapped[date | None] = mapped_column(Date)
    salida_real: Mapped[date | None] = mapped_column(Date)
    arribo_real: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="PLANIFICADO", index=True)
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    unidades: Mapped[list["UnidadCarga"]] = relationship(
        back_populates="embarque", order_by="UnidadCarga.id", cascade="all, delete-orphan"
    )
    eventos: Mapped[list["EventoEmbarque"]] = relationship(
        back_populates="embarque", order_by="EventoEmbarque.fecha", cascade="all, delete-orphan"
    )


class UnidadCarga(Base):
    __tablename__ = "unidades_carga"
    id: Mapped[int] = mapped_column(primary_key=True)
    embarque_id: Mapped[int] = mapped_column(ForeignKey("embarques.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))
    etiqueta: Mapped[str] = mapped_column(String(30))  # "40HC #1" mientras no hay número
    numero: Mapped[str | None] = mapped_column(String(20))
    sello: Mapped[str | None] = mapped_column(String(30))
    capacidad_cbm: Mapped[float | None] = mapped_column(Float)
    capacidad_kg: Mapped[float | None] = mapped_column(Float)

    embarque: Mapped[Embarque] = relationship(back_populates="unidades")
    packing_lists: Mapped[list[PackingList]] = relationship(back_populates="unidad")


class EventoEmbarque(Base):
    __tablename__ = "eventos_embarque"
    id: Mapped[int] = mapped_column(primary_key=True)
    embarque_id: Mapped[int] = mapped_column(ForeignKey("embarques.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    fecha: Mapped[datetime] = mapped_column(DateTime)
    ubicacion: Mapped[str | None] = mapped_column(String(150))
    observacion: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    embarque: Mapped[Embarque] = relationship(back_populates="eventos")
