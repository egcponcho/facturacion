"""Pagos a proveedores: lo programado y lo pagado de cada factura comercial.

Una factura se paga en uno o varios pagos, en la moneda de la factura. Cada
pago se programa para una fecha y después se marca pagado (con la fecha real y
la referencia del banco) o se anula; un pago anulado queda en el historial. El
saldo de la factura es su importe menos lo pagado.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import Importe, ahora
from app.modelos.facturacion import Factura

ESTADOS_PAGO = ("PROGRAMADO", "PAGADO", "ANULADO")


class PagoProveedor(DeOrganizacion, Base):
    __tablename__ = "pagos_proveedor"
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    importe: Mapped[float] = mapped_column(Importe)  # en la moneda de la factura
    fecha_programada: Mapped[date] = mapped_column(Date, index=True)
    fecha_pago: Mapped[date | None] = mapped_column(Date)
    referencia: Mapped[str | None] = mapped_column(String(80))  # transferencia, cheque…
    estado: Mapped[str] = mapped_column(String(12), default="PROGRAMADO", index=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)

    factura: Mapped[Factura] = relationship(back_populates="pagos")
