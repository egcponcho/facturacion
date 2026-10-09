"""Acceso: roles, usuarios, sesiones y verificación en dos pasos.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.modelos.base import ahora

if TYPE_CHECKING:
    from app.modelos.maestros import Proveedor


class Rol(Base):
    """Rol con sus permisos: el tipo dice qué datos ve el usuario (el
    proveedor solo lo suyo) y los permisos, a qué módulos y acciones entra."""

    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(20))  # admin | interno | proveedor
    permisos: Mapped[list] = mapped_column(JSON, default=list)
    # Grupos de datos que este rol no ve (modulos/acceso/visibilidad.py): precios,
    # códigos internos, fechas internas… El servidor los quita de las respuestas.
    datos_ocultos: Mapped[list] = mapped_column(JSON, default=list)
    sistema: Mapped[bool] = mapped_column(Boolean, default=False)  # los de fábrica no se borran
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(20))  # tipo del rol: admin | interno | proveedor
    rol_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    # Alcance de los datos (modulos/acceso/permisos.py): {"proveedores": [ids], "sociedades": [códigos]}
    alcance: Mapped[dict] = mapped_column(JSON, default=dict)
    password_hash: Mapped[str] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Seguridad del acceso: celular registrado para la verificación en dos
    # pasos, intentos fallidos y bloqueo temporal.
    telefono: Mapped[str | None] = mapped_column(String(20))  # formato E.164: +50370000000
    dos_pasos: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime)
    password_cambiado_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Idioma, formatos de fecha/hora/número, tema, filas por página (solo lo que difiere del defecto)
    preferencias: Mapped[dict] = mapped_column(JSON, default=dict)
    # Datos del perfil: la foto la cambia el usuario; cargo, área y empresa, la administración
    foto: Mapped[str | None] = mapped_column(Text)  # imagen pequeña (data URL)
    cargo: Mapped[str | None] = mapped_column(String(120))
    area: Mapped[str | None] = mapped_column(String(120))
    empresa: Mapped[str | None] = mapped_column(String(200))
    # Contraseña temporal (creada o restablecida por la administración): hasta
    # cambiarla, el usuario solo puede completar el asistente inicial
    clave_temporal: Mapped[bool] = mapped_column(Boolean, default=False)
    proveedor: Mapped[Proveedor | None] = relationship()
    rol_ref: Mapped[Rol | None] = relationship()


class SesionUsuario(Base):
    """Sesión iniciada. La cookie lleva un token aleatorio; aquí solo se guarda
    su hash. Vence por inactividad y por duración máxima, y se revoca al
    cerrar sesión o al cambiar la contraseña."""

    __tablename__ = "sesiones"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    creada: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    expira: Mapped[datetime] = mapped_column(DateTime)
    ultima_actividad: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    ip: Mapped[str | None] = mapped_column(String(64))
    agente: Mapped[str | None] = mapped_column(String(300))
    revocada: Mapped[bool] = mapped_column(Boolean, default=False)

    usuario: Mapped[Usuario] = relationship()


class DesafioDosPasos(Base):
    """Código de un solo uso enviado por SMS al celular registrado."""

    __tablename__ = "desafios_dos_pasos"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    codigo_hash: Mapped[str] = mapped_column(String(64))
    expira: Mapped[datetime] = mapped_column(DateTime)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    envios: Mapped[int] = mapped_column(Integer, default=1)
    ultimo_envio: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    usado: Mapped[bool] = mapped_column(Boolean, default=False)

    usuario: Mapped[Usuario] = relationship()
