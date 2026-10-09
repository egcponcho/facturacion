"""Empresa de la instalación.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.modelos.base import ahora


class Organizacion(Base):
    """La empresa que usa esta instalación (un solo registro, id 1).

    Guarda sus datos generales (nombre, razón social, logo) y en
    `configuracion` sus preferencias y reglas de negocio, que se cambian en
    Configuración → Empresa sin tocar código ni variables de entorno."""

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
