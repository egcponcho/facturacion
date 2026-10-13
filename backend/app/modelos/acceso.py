"""Acceso: roles, usuarios, sesiones y verificación en dos pasos.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    false,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion, UsuarioDeOrganizacion
from app.modelos.base import ahora

if TYPE_CHECKING:
    from app.modelos.maestros import Proveedor, Sociedad
    from app.modelos.transporte import Transportista


class Rol(DeOrganizacion, Base):
    """Rol con sus permisos: el tipo dice qué datos ve el usuario (el
    proveedor solo lo suyo) y los permisos, a qué módulos y acciones entra."""

    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organizacion_id", "nombre", name="uq_roles_org_nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(20))  # admin | interno | proveedor
    permisos: Mapped[list] = mapped_column(JSON, default=list)
    # Grupos de datos que este rol no ve (modulos/acceso/visibilidad.py): precios,
    # códigos internos, fechas internas… El servidor los quita de las respuestas.
    datos_ocultos: Mapped[list] = mapped_column(JSON, default=list)
    # Paneles de la página de inicio que este rol no ve (visibilidad.PANELES_INICIO)
    inicio_oculto: Mapped[list] = mapped_column(JSON, default=list)
    sistema: Mapped[bool] = mapped_column(Boolean, default=False)  # los de fábrica no se borran
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# Alcance de los datos de un usuario (modulos/acceso/permisos.py): proveedores,
# sociedades y transportistas cuyos datos ve; ninguno = sin límite
usuario_proveedores = Table(
    "usuario_proveedores", Base.metadata,
    Column("usuario_id", ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
    Column("proveedor_id", ForeignKey("proveedores.id", ondelete="CASCADE"), primary_key=True, index=True),
)
usuario_sociedades = Table(
    "usuario_sociedades", Base.metadata,
    Column("usuario_id", ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
    Column("sociedad_id", ForeignKey("sociedades.id", ondelete="CASCADE"), primary_key=True, index=True),
)
usuario_transportistas = Table(
    "usuario_transportistas", Base.metadata,
    Column("usuario_id", ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True),
    Column("transportista_id", ForeignKey("transportistas.id", ondelete="CASCADE"), primary_key=True, index=True),
)


class Usuario(UsuarioDeOrganizacion, Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)  # único en toda la plataforma: identifica la organización al entrar
    # Administra la plataforma: crea organizaciones, entra a cualquiera y
    # mantiene los datos compartidos (arancel oficial, motor de clasificación)
    plataforma: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    nombre: Mapped[str] = mapped_column(String(200))
    rol_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)
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
    # Contraseña temporal (creada o restablecida por la administración): hasta
    # cambiarla, el usuario solo puede completar el asistente inicial
    clave_temporal: Mapped[bool] = mapped_column(Boolean, default=False)
    proveedor: Mapped[Proveedor | None] = relationship()
    rol_ref: Mapped[Rol | None] = relationship()
    alcance_proveedores: Mapped[list[Proveedor]] = relationship(secondary=usuario_proveedores)
    alcance_sociedades: Mapped[list[Sociedad]] = relationship(secondary=usuario_sociedades)
    alcance_transportistas: Mapped[list[Transportista]] = relationship(secondary=usuario_transportistas)

    @property
    def rol(self) -> str:
        """Tipo del usuario, derivado (no se guarda): proveedor si tiene un
        proveedor asignado; si no, administración o equipo interno según los
        permisos de su rol."""
        if self.proveedor_id:
            return "proveedor"
        return "admin" if self.rol_ref is not None and "admin" in (self.rol_ref.permisos or []) else "interno"

    @rol.setter
    def rol(self, _valor) -> None:
        """Se deriva del rol asignado y del proveedor; asignarlo no cambia nada."""

    @property
    def empresa(self) -> str | None:
        """Empresa del usuario: su proveedor o su organización (no se guarda aparte)."""
        if self.proveedor is not None:
            return self.proveedor.nombre
        from sqlalchemy.orm import object_session

        from app.modelos.empresa import Organizacion

        db = object_session(self)
        org = db.get(Organizacion, self.organizacion_id) if db is not None and self.organizacion_id else None
        return org.nombre if org else None

    @empresa.setter
    def empresa(self, _valor) -> None:
        """Se deriva del proveedor o de la organización."""

    @property
    def alcance(self) -> dict:
        """{"proveedores": [ids], "sociedades": [códigos], "transportistas": [ids]} (solo lo que limita)."""
        pendiente = self.__dict__.get("_alcance_pendiente")
        if pendiente is not None:
            return pendiente
        res = {"proveedores": sorted(p.id for p in self.alcance_proveedores),
               "sociedades": sorted(s.codigo for s in self.alcance_sociedades),
               "transportistas": sorted(t.id for t in self.alcance_transportistas)}
        return {k: v for k, v in res.items() if v}

    @alcance.setter
    def alcance(self, valor: dict | None) -> None:
        """Se aplica a las tablas de asociación al guardar (ver _aplicar_alcance)."""
        self.__dict__["_alcance_pendiente"] = {k: v for k, v in (valor or {}).items() if v}
        flag_modified_si(self)


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
    # Organización en la que trabaja la sesión (quien administra la plataforma
    # puede entrar a otra); vacía = la del usuario
    organizacion_id: Mapped[int | None] = mapped_column(ForeignKey("organizaciones.id"))

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


def flag_modified_si(u: "Usuario") -> None:
    """Marca al usuario como modificado (si ya está en una sesión) para que se aplique su alcance al guardar."""
    from sqlalchemy.orm import attributes, object_session

    if object_session(u) is not None and u.id is not None:
        attributes.flag_modified(u, "nombre")


@event.listens_for(Session, "before_flush")
def _aplicar_alcance(db: Session, _contexto, _instancias) -> None:
    """El alcance pendiente de un usuario pasa a sus tablas de asociación."""
    from app.modelos.maestros import Proveedor, Sociedad
    from app.modelos.transporte import Transportista

    for u in [*db.new, *db.dirty]:
        if not isinstance(u, Usuario) or "_alcance_pendiente" not in u.__dict__:
            continue
        a = u.__dict__.pop("_alcance_pendiente")
        provs, socs, trans = a.get("proveedores") or [], a.get("sociedades") or [], a.get("transportistas") or []
        u.alcance_proveedores = list(db.scalars(select(Proveedor).where(Proveedor.id.in_(provs)))) if provs else []
        u.alcance_sociedades = list(db.scalars(select(Sociedad).where(Sociedad.codigo.in_(socs)))) if socs else []
        u.alcance_transportistas = list(db.scalars(select(Transportista).where(Transportista.id.in_(trans)))) if trans else []
