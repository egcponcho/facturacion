"""Solicitudes de compra: lo que piden las áreas antes de que exista una orden.

Un área (mantenimiento, una bodega, una tienda…) pide artículos con cantidad
y un precio estimado. La solicitud llega pendiente de aprobación; quien
aprueba la aprueba o la rechaza con un comentario. Las aprobadas se convierten
en una orden de compra en borrador (una o varias solicitudes del mismo
proveedor en la misma OC) y quedan enlazadas a ella.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import Cantidad, Precio, ahora

if TYPE_CHECKING:
    from app.modelos.acceso import Usuario
    from app.modelos.compras import OrdenCompra
    from app.modelos.maestros import Proveedor

ESTADOS_SOLICITUD = ("PENDIENTE", "APROBADA", "RECHAZADA", "CONVERTIDA", "CANCELADA")
PRIORIDADES = ("NORMAL", "URGENTE")


class SolicitudCompra(DeOrganizacion, Base):
    __tablename__ = "solicitudes_compra"
    __table_args__ = (UniqueConstraint("organizacion_id", "numero", name="uq_solicitudes_compra_org_numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(30))  # de la serie «solicitud» (SC-0001…)
    area: Mapped[str] = mapped_column(String(80))  # quién pide: departamento, bodega, tienda…
    centro: Mapped[str | None] = mapped_column(String(10))  # dónde se necesita
    solicitante_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[date] = mapped_column(Date, index=True)
    fecha_requerida: Mapped[date | None] = mapped_column(Date)
    prioridad: Mapped[str] = mapped_column(String(10), default="NORMAL")
    estado: Mapped[str] = mapped_column(String(12), default="PENDIENTE", index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)  # sugerido
    moneda: Mapped[str | None] = mapped_column(String(3))  # del precio estimado
    motivo: Mapped[str | None] = mapped_column(String(500))
    comentario_revision: Mapped[str | None] = mapped_column(String(500))
    revisada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    revisada_en: Mapped[datetime | None] = mapped_column(DateTime)
    oc_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)

    solicitante: Mapped[Usuario | None] = relationship(foreign_keys=[solicitante_id])
    proveedor: Mapped[Proveedor | None] = relationship()
    oc: Mapped[OrdenCompra | None] = relationship()
    lineas: Mapped[list[SolicitudLinea]] = relationship(back_populates="solicitud", cascade="all, delete-orphan",
                                                        order_by="SolicitudLinea.id")


class SolicitudLinea(DeOrganizacion, Base):
    __tablename__ = "solicitud_lineas"
    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitudes_compra.id"), index=True)
    codigo_articulo: Mapped[str | None] = mapped_column(String(40))  # del catálogo; vacío si aún no existe
    descripcion: Mapped[str] = mapped_column(String(300))
    cantidad: Mapped[float] = mapped_column(Cantidad)
    unidad: Mapped[str | None] = mapped_column(String(5))
    precio_estimado: Mapped[float | None] = mapped_column(Precio)

    solicitud: Mapped[SolicitudCompra] = relationship(back_populates="lineas")
