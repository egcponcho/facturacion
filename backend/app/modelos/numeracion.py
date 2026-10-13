"""Series de numeración de documentos y sus contadores.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion


class SerieDocumental(DeOrganizacion, Base):
    """Cómo se numera una clase de documento: prefijo, dígitos, si el
    contador vuelve a 1 cada año y, opcionalmente, la sociedad o el tipo de
    documento comercial a los que pertenece. El número se asigna al emitir,
    dentro de la misma transacción y con el contador bloqueado
    (core/numeracion.py): dos usuarios a la vez nunca reciben el mismo."""

    __tablename__ = "series_documentales"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "codigo", name="uq_series_documentales_org_codigo"),
        CheckConstraint("digitos BETWEEN 1 AND 12", name="ck_series_documentales_digitos"),
        CheckConstraint("reinicio IN ('NUNCA', 'ANUAL')", name="ck_series_documentales_reinicio"),
        CheckConstraint("vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde",
                        name="ck_series_documentales_vigencia"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    # Qué numera: «embarque», o el código de un tipo de documento comercial
    objeto: Mapped[str] = mapped_column(String(30), index=True)
    tipo_documento_id: Mapped[int | None] = mapped_column(
        ForeignKey("tipos_documento.id", name="fk_series_documentales_tipo_documento_id"), index=True)
    sociedad_id: Mapped[int | None] = mapped_column(ForeignKey("sociedades.id"), index=True)
    prefijo: Mapped[str] = mapped_column(String(20), default="")
    digitos: Mapped[int] = mapped_column(Integer, default=4)
    reinicio: Mapped[str] = mapped_column(String(10), default="NUNCA")  # NUNCA | ANUAL ({año} en el prefijo)
    predeterminada: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)

    contadores: Mapped[list["ContadorSerie"]] = relationship(back_populates="serie", cascade="all, delete-orphan")


class ContadorSerie(DeOrganizacion, Base):
    """Siguiente número de una serie en un periodo («» si no reinicia; el año si reinicia cada año)."""

    __tablename__ = "contadores_serie"
    __table_args__ = (
        UniqueConstraint("serie_id", "periodo", name="uq_contadores_serie_serie_periodo"),
        CheckConstraint("siguiente >= 1", name="ck_contadores_serie_siguiente"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    serie_id: Mapped[int] = mapped_column(ForeignKey("series_documentales.id", ondelete="CASCADE"), index=True)
    periodo: Mapped[str] = mapped_column(String(10), default="")
    siguiente: Mapped[int] = mapped_column(Integer, default=1)

    serie: Mapped[SerieDocumental] = relationship(back_populates="contadores")
