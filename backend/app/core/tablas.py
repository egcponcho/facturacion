"""Tablas del núcleo: lo que `core` guarda en la base sin saber de ningún módulo.

- Campos propios que la empresa agrega a sus entidades (core/campos_propios.py).
- Cómo lee la empresa los estados de sus documentos (core/estados.py).
- Series de numeración y sus contadores (core/numeracion.py).

Están aquí y no en `app/modelos` porque `core` no importa nada de afuera;
`app/modelos/__init__.py` las reexporta para el resto del sistema.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion


class DefinicionCampo(DeOrganizacion, Base):
    """Campo propio que la empresa agrega a una entidad (proveedores, OCs,
    facturas…; los productos y sus variantes tienen atributos: modelos/maestros.py).
    La clave técnica es estable; la etiqueta se cambia libremente. Los valores van en la columna `extra` (JSON) de cada
    registro con esa clave (core/campos_propios.py). Un campo indexado tiene en
    PostgreSQL un índice sobre su valor para filtrarlo e informarlo rápido."""

    __tablename__ = "definiciones_campo"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "entidad", "clave", name="uq_definiciones_campo_org_entidad_clave"),
        CheckConstraint("tipo IN ('texto', 'numero', 'fecha', 'bool', 'opcion')", name="ck_definiciones_campo_tipo"),
        CheckConstraint("entidad IN ('proveedores', 'sociedades', 'centros', 'marcas', 'transportistas', 'ordenes', "
                        "'facturas')", name="ck_definiciones_campo_entidad"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(20), index=True)
    clave: Mapped[str] = mapped_column(String(30))
    etiqueta: Mapped[str] = mapped_column(String(60))
    tipo: Mapped[str] = mapped_column(String(10), default="texto")
    opciones: Mapped[list] = mapped_column(JSON, default=list)
    obligatorio: Mapped[bool] = mapped_column(Boolean, default=False)
    indexado: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)


class EstadoDocumento(DeOrganizacion, Base):
    """Cómo lee la empresa un estado de un documento: su etiqueta, su color y
    su lugar en filtros y listas. El código es fijo (lo usa el sistema para
    decidir, core/estados.py); sin fila, el estado se muestra como viene de
    fábrica."""

    __tablename__ = "estados_documento"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "documento", "codigo", name="uq_estados_documento_org_documento_codigo"),
        CheckConstraint("tono IS NULL OR tono IN ('neutro', 'info', 'ok', 'aviso', 'error')", name="ck_estados_documento_tono"),
        CheckConstraint("documento IN ('oc', 'avance', 'factura', 'pl', 'embarque', 'producto', 'documento', 'cobro', "
                        "'pago')", name="ck_estados_documento_documento"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    documento: Mapped[str] = mapped_column(String(20))
    codigo: Mapped[str] = mapped_column(String(30))
    etiqueta: Mapped[str | None] = mapped_column(String(60))
    tono: Mapped[str | None] = mapped_column(String(10))
    orden: Mapped[int | None] = mapped_column(Integer)



class SerieDocumental(DeOrganizacion, Base):
    """Cómo se numera una clase de documento: prefijo, dígitos, si el
    contador vuelve a 1 cada año y, opcionalmente, la sociedad a la que
    pertenece. El número se asigna al emitir,
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
    # Qué numera: «embarque»
    objeto: Mapped[str] = mapped_column(String(30), index=True)
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
