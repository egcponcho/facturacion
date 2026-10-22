"""Integración con sistemas externos (ERP u otros), desacoplada del núcleo.

El núcleo no sabe de ningún ERP. Una integración dice cómo se traducen sus
datos a los del sistema y vuelta:

- `integraciones`: un sistema externo de la empresa y el adaptador de formato
  con que se intercambia (archivo tabular, JSON…). Sin credenciales en claro.
- `integracion_mapeos`: por entidad y dirección, qué campo externo corresponde
  a cada campo interno, los valores por defecto y la traducción de códigos.
  Cada cambio crea una versión nueva; las anteriores se conservan (`vigente`).
- `referencias_externas`: el identificador de un registro en el sistema
  externo. Permite relacionar, actualizar en lugar de duplicar y saber de dónde
  vino o a dónde se envió cada registro.
- `integracion_ejecuciones`: la bitácora de cada intercambio (quién, cuándo,
  qué, con qué resultado y qué filas fallaron). La huella del contenido impide
  aplicar dos veces el mismo archivo.

Ver docs/reestructuracion/02-arquitectura.md §4 y app/modulos/integraciones.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import ahora

DIRECCIONES = ("ENTRADA", "SALIDA")
ESTADOS_EJECUCION = ("PREVIA", "APLICADA", "CON_ERRORES", "FALLIDA")


class Integracion(DeOrganizacion, Base):
    """Un sistema externo con el que la empresa intercambia datos."""

    __tablename__ = "integraciones"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_integraciones_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(100))
    sistema: Mapped[str | None] = mapped_column(String(60))  # descriptivo: «SAP S/4», «Odoo 17»… (no cambia el comportamiento)
    adaptador: Mapped[str] = mapped_column(String(30))  # código de un adaptador registrado (integraciones/adaptadores.py)
    parametros: Mapped[dict] = mapped_column(JSON, default=dict)  # validados por el adaptador (delimitador, hoja…)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    mapeos: Mapped[list[IntegracionMapeo]] = relationship(back_populates="integracion", cascade="all, delete-orphan")


class IntegracionMapeo(DeOrganizacion, Base):
    """Cómo se traduce una entidad en una dirección. Inmutable: editar crea la
    versión siguiente y deja la anterior como histórica."""

    __tablename__ = "integracion_mapeos"
    __table_args__ = (
        UniqueConstraint("integracion_id", "entidad", "direccion", "version", name="uq_integracion_mapeos_version"),
        CheckConstraint("direccion IN ('ENTRADA', 'SALIDA')", name="ck_integracion_mapeos_direccion"),
        CheckConstraint("version >= 1", name="ck_integracion_mapeos_version"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    integracion_id: Mapped[int] = mapped_column(ForeignKey("integraciones.id", ondelete="CASCADE"), index=True)
    entidad: Mapped[str] = mapped_column(String(30))  # ordenes_compra, facturas… (integraciones/entidades.py)
    direccion: Mapped[str] = mapped_column(String(10))
    version: Mapped[int] = mapped_column(Integer, default=1)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    campos: Mapped[dict] = mapped_column(JSON, default=dict)  # campo interno → nombre del campo externo
    valores: Mapped[dict] = mapped_column(JSON, default=dict)  # campo interno → valor por defecto
    codigos: Mapped[dict] = mapped_column(JSON, default=dict)  # campo interno → {código externo: código interno}
    formato_fecha: Mapped[str | None] = mapped_column(String(12))  # DD/MM/YYYY…; vacío: ISO o el del usuario
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    integracion: Mapped[Integracion] = relationship(back_populates="mapeos")


class ReferenciaExterna(DeOrganizacion, Base):
    """El identificador de un registro del sistema en un sistema externo."""

    __tablename__ = "referencias_externas"
    __table_args__ = (
        # Un código externo apunta a un solo registro y un registro tiene un solo código por sistema
        UniqueConstraint("integracion_id", "entidad", "codigo_externo", name="uq_referencias_externas_codigo"),
        UniqueConstraint("integracion_id", "entidad", "interno_id", name="uq_referencias_externas_interno"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    integracion_id: Mapped[int] = mapped_column(ForeignKey("integraciones.id", ondelete="CASCADE"), index=True)
    entidad: Mapped[str] = mapped_column(String(30))
    interno_id: Mapped[int] = mapped_column(Integer)
    codigo_externo: Mapped[str] = mapped_column(String(120))
    ejecucion_id: Mapped[int | None] = mapped_column(ForeignKey("integracion_ejecuciones.id"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)


class EjecucionIntegracion(DeOrganizacion, Base):
    """Un intercambio con el sistema externo y su resultado."""

    __tablename__ = "integracion_ejecuciones"
    __table_args__ = (
        CheckConstraint("direccion IN ('ENTRADA', 'SALIDA')", name="ck_integracion_ejecuciones_direccion"),
        CheckConstraint("estado IN ('PREVIA', 'APLICADA', 'CON_ERRORES', 'FALLIDA')", name="ck_integracion_ejecuciones_estado"),
        Index("ix_integracion_ejecuciones_huella", "integracion_id", "entidad", "huella"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    integracion_id: Mapped[int] = mapped_column(ForeignKey("integraciones.id", ondelete="CASCADE"), index=True)
    mapeo_id: Mapped[int | None] = mapped_column(ForeignKey("integracion_mapeos.id"))
    entidad: Mapped[str] = mapped_column(String(30))
    direccion: Mapped[str] = mapped_column(String(10))
    estado: Mapped[str] = mapped_column(String(12), default="PREVIA")
    archivo: Mapped[str | None] = mapped_column(String(300))
    huella: Mapped[str | None] = mapped_column(String(64))  # sha256 del contenido recibido o enviado
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    filas: Mapped[list] = mapped_column(JSON, default=list)  # filas ya traducidas a campos internos (entrada)
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)  # creados, actualizados, sin_cambio, rechazados…
    errores: Mapped[list] = mapped_column(JSON, default=list)  # [{fila, mensajes}]
    importacion_oc_id: Mapped[int | None] = mapped_column(ForeignKey("importaciones_oc.id"))
    iniciada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime)
