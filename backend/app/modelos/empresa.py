"""Organizaciones (empresas cliente) de la instalación.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import ahora


class Organizacion(Base):
    """Una empresa cliente. Sus datos están aislados de las demás
    (`core/organizacion.py`); una instalación de una sola empresa usa la 1.

    Guarda sus datos generales (nombre, razón social, logo) y en
    `configuracion` sus preferencias, marca, terminología, campos propios,
    módulos y reglas de negocio, que se cambian en Configuración → Empresa sin
    tocar código ni variables de entorno."""

    __tablename__ = "organizaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    id_fiscal: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(2))
    logo: Mapped[str | None] = mapped_column(Text)  # imagen pequeña (data URL)
    configuracion: Mapped[dict] = mapped_column(JSON, default=dict)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Adjunto(DeOrganizacion, Base):
    """Archivo subido (factura oficial, foto, ficha técnica…): sus datos en la
    base y su contenido en el almacén (core/almacen.py). Cada uso (archivos de
    la factura, fotos y documentos del producto) lo referencia con su llave."""

    __tablename__ = "adjuntos"
    __table_args__ = (CheckConstraint("tamano >= 0", name="ck_adjuntos_tamano"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(300))
    clave: Mapped[str] = mapped_column(String(500))  # ruta dentro del almacén
    tipo_mime: Mapped[str] = mapped_column(String(100))
    tamano: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    subido_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", name="fk_adjuntos_subido_por"), index=True)
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class ConAdjunto:
    """Uso de un adjunto: la llave y, para leerlo, su nombre, ruta, tamaño y tipo."""

    @declared_attr
    def adjunto_id(cls) -> Mapped[int]:  # noqa: N805
        return mapped_column(ForeignKey("adjuntos.id", name=f"fk_{cls.__tablename__}_adjunto_id"), unique=True, index=True)

    @declared_attr
    def adjunto(cls) -> Mapped[Adjunto]:  # noqa: N805
        return relationship(Adjunto, lazy="joined")

    @property
    def nombre(self) -> str:
        return self.adjunto.nombre

    @property
    def ruta(self) -> str:
        from app.core.almacen import ruta

        return ruta(self.adjunto.clave)

    @property
    def tamano(self) -> int:
        return self.adjunto.tamano

    @property
    def tipo_mime(self) -> str:
        return self.adjunto.tipo_mime

    @property
    def subido_en(self):
        return self.adjunto.subido_en
