"""Registros del sistema: historial de cambios, alertas, metas, idempotencia y
edición exclusiva.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.modelos.base import ahora

if TYPE_CHECKING:
    from app.modelos.acceso import Usuario


class Historial(Base):
    __tablename__ = "historial"
    __table_args__ = (Index("ix_historial_entidad", "entidad", "entidad_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(30))
    entidad_id: Mapped[int] = mapped_column(Integer)
    factura_id: Mapped[int | None] = mapped_column(Integer, index=True)
    accion: Mapped[str] = mapped_column(String(60))
    detalle: Mapped[dict | list | None] = mapped_column(JSON)
    motivo: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)

    usuario: Mapped[Usuario | None] = relationship()


class Alerta(Base):
    __tablename__ = "alertas"
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    mensaje: Mapped[str] = mapped_column(String(500))
    referencia: Mapped[dict | None] = mapped_column(JSON)
    resuelta: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Meta(Base):
    """Valores del sistema, como la versión del esquema."""

    __tablename__ = "meta"
    clave: Mapped[str] = mapped_column(String(40), primary_key=True)
    valor: Mapped[str] = mapped_column(String(200))


class Idempotencia(Base):
    __tablename__ = "idempotencia"
    clave: Mapped[str] = mapped_column(String(160), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer)
    respuesta: Mapped[dict | list | None] = mapped_column(JSON)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Edicion(Base):
    """Quién está editando un documento. Mientras el permiso esté vigente,
    los demás lo ven en solo lectura y el servidor rechaza sus cambios. La
    pantalla lo renueva mientras está abierta; si se cierra o pierde conexión,
    vence solo."""
    __tablename__ = "ediciones"
    __table_args__ = (UniqueConstraint("entidad", "entidad_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(30))  # factura | packing_list | embarque | producto | orden
    entidad_id: Mapped[int] = mapped_column(Integer)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    desde: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    vence: Mapped[datetime] = mapped_column(DateTime)
    usuario: Mapped[Usuario] = relationship()
