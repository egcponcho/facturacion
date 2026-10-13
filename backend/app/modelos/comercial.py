"""Terceros: la identidad fiscal de proveedores y transportistas (y de
cualquier otra parte), sus direcciones y sus medios de contacto. Un proveedor
o un transportista de los datos maestros es la extensión de su tercero.

La facturación es la del proveedor contra la OC (modelos/facturacion.py): el
sistema no emite ni cobra documentos comerciales propios.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    event,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import Importe, ahora

if TYPE_CHECKING:
    from app.modelos.maestros import Contacto

ROLES_TERCERO = ("CLIENTE", "PROVEEDOR", "TRANSPORTISTA", "AGENTE")


def _fk_codigo(columna: str, catalogo: str, tabla: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(["organizacion_id", columna], [f"{catalogo}.organizacion_id", f"{catalogo}.codigo"],
                                name=f"fk_{tabla}_{columna}")


# ---- Terceros --------------------------------------------------------------------------
class Tercero(DeOrganizacion, Base):
    """Persona o empresa con la que se comercia. Su identidad fiscal es una
    sola aunque cumpla varios roles (cliente y proveedor a la vez); lo propio
    de cada rol vive en su tabla (proveedores, transportistas) o en el rol."""

    __tablename__ = "terceros"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "codigo", name="uq_terceros_org_codigo"),
        Index("ux_terceros_id_fiscal", "organizacion_id", "pais", "id_fiscal", unique=True,
              sqlite_where=text("id_fiscal IS NOT NULL"), postgresql_where=text("id_fiscal IS NOT NULL")),
        CheckConstraint("tipo_persona IN ('JURIDICA', 'NATURAL')", name="ck_terceros_tipo_persona"),
        ForeignKeyConstraint(["pais"], ["paises.codigo"], name="fk_terceros_pais"),
        _fk_codigo("moneda", "monedas", "terceros"),
        _fk_codigo("condicion_pago", "condiciones_pago", "terceros"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(30))
    tipo_persona: Mapped[str] = mapped_column(String(10), default="JURIDICA")
    nombre: Mapped[str] = mapped_column(String(200))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    tipo_identificacion: Mapped[str | None] = mapped_column(String(20))  # NIT, RUC, VAT, EIN…
    id_fiscal: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(2))
    moneda: Mapped[str | None] = mapped_column(String(3))  # predeterminada de sus documentos
    condicion_pago: Mapped[str | None] = mapped_column(String(20))
    limite_credito: Mapped[float | None] = mapped_column(Importe)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    roles: Mapped[list["TerceroRol"]] = relationship(back_populates="tercero", cascade="all, delete-orphan")
    direcciones: Mapped[list["Direccion"]] = relationship(
        back_populates="tercero", cascade="all, delete-orphan", foreign_keys="Direccion.tercero_id")
    medios: Mapped[list["MedioContacto"]] = relationship(
        back_populates="tercero", cascade="all, delete-orphan", foreign_keys="MedioContacto.tercero_id")
    contactos: Mapped[list["Contacto"]] = relationship(cascade="all, delete-orphan", foreign_keys="Contacto.tercero_id")

    def tiene_rol(self, rol: str) -> bool:
        return any(r.rol == rol for r in self.roles)


class TerceroRol(DeOrganizacion, Base):
    __tablename__ = "tercero_roles"
    __table_args__ = (
        UniqueConstraint("tercero_id", "rol", name="uq_tercero_roles_tercero_rol"),
        CheckConstraint("rol IN ('CLIENTE', 'PROVEEDOR', 'TRANSPORTISTA', 'AGENTE')", name="ck_tercero_roles_rol"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tercero_id: Mapped[int] = mapped_column(ForeignKey("terceros.id", ondelete="CASCADE"), index=True)
    rol: Mapped[str] = mapped_column(String(15))

    tercero: Mapped[Tercero] = relationship(back_populates="roles")


# Dueño de una dirección o un medio de contacto: un tercero, una sociedad, un
# centro o una persona de contacto (exactamente uno)
_UN_DUENO = ("(CASE WHEN tercero_id IS NULL THEN 0 ELSE 1 END + CASE WHEN sociedad_id IS NULL THEN 0 ELSE 1 END"
             " + CASE WHEN centro_id IS NULL THEN 0 ELSE 1 END{extra}) = 1")


class Direccion(DeOrganizacion, Base):
    """Dirección tipada (fiscal, entrega, recogida) de un tercero, una sociedad o un centro."""

    __tablename__ = "direcciones"
    __table_args__ = (
        CheckConstraint(_UN_DUENO.format(extra=""), name="ck_direcciones_dueno"),
        CheckConstraint("tipo IN ('FISCAL', 'ENTREGA', 'RECOGIDA', 'OTRA')", name="ck_direcciones_tipo"),
        ForeignKeyConstraint(["pais"], ["paises.codigo"], name="fk_direcciones_pais"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id", ondelete="CASCADE"), index=True)
    sociedad_id: Mapped[int | None] = mapped_column(ForeignKey("sociedades.id", ondelete="CASCADE"), index=True)
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centros.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(10), default="FISCAL")
    linea1: Mapped[str] = mapped_column(String(300))
    linea2: Mapped[str | None] = mapped_column(String(300))
    ciudad: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    codigo_postal: Mapped[str | None] = mapped_column(String(20))
    pais: Mapped[str | None] = mapped_column(String(2))
    principal: Mapped[bool] = mapped_column(Boolean, default=True)

    tercero: Mapped[Tercero | None] = relationship(back_populates="direcciones", foreign_keys=[tercero_id])

    def texto(self) -> str:
        return ", ".join(x for x in (self.linea1, self.linea2, self.ciudad, self.region, self.codigo_postal) if x)


class MedioContacto(DeOrganizacion, Base):
    """Un correo, teléfono o sitio de un tercero, una sociedad, un centro o una
    persona de contacto; uno por fila (no listas separadas por comas)."""

    __tablename__ = "medios_contacto"
    __table_args__ = (
        CheckConstraint(_UN_DUENO.format(extra=" + CASE WHEN contacto_id IS NULL THEN 0 ELSE 1 END"),
                        name="ck_medios_contacto_dueno"),
        CheckConstraint("tipo IN ('CORREO', 'TELEFONO', 'MOVIL', 'WEB', 'OTRO')", name="ck_medios_contacto_tipo"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id", ondelete="CASCADE"), index=True)
    sociedad_id: Mapped[int | None] = mapped_column(ForeignKey("sociedades.id", ondelete="CASCADE"), index=True)
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centros.id", ondelete="CASCADE"), index=True)
    contacto_id: Mapped[int | None] = mapped_column(ForeignKey("contactos.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(10), default="CORREO")
    valor: Mapped[str] = mapped_column(String(200))
    uso: Mapped[str | None] = mapped_column(String(20))  # FACTURACION, NOTIFY, LOGISTICA… (lista tipo_contacto)
    principal: Mapped[bool] = mapped_column(Boolean, default=False)

    tercero: Mapped[Tercero | None] = relationship(back_populates="medios", foreign_keys=[tercero_id])


# ---- Correos, teléfono, dirección y contacto como datos normalizados ---------------------------
def _correos(texto: str | None) -> list[str]:
    import re

    vistos = []
    for x in re.split(r"[,;\s]+", texto or ""):
        x = x.strip().lower()
        if x and x not in vistos:
            vistos.append(x)
    return vistos


class ConContacto:
    """Los datos de contacto de un dueño (sociedad, centro, contacto, o el
    tercero de un proveedor o transportista) viven en medios_contacto y
    direcciones, uno por fila. Estas propiedades los leen y escriben con la
    forma de siempre: `correos` (varios, separados por coma), `telefono` y
    `direccion` (la principal)."""

    _uso_correos: str | None = None
    _tipo_direccion = "FISCAL"

    # Dónde viven: la colección de medios y la de direcciones del dueño
    def _lista_medios(self, crear: bool = False):
        return self.medios

    def _lista_direcciones(self, crear: bool = False):
        return self.direcciones

    @property
    def correos(self) -> str | None:
        lista = self._lista_medios() or []
        vals = [m.valor for m in sorted(lista, key=lambda m: (not m.principal, m.id or 0)) if m.tipo == "CORREO"]
        return ", ".join(vals) or None

    @correos.setter
    def correos(self, texto: str | None) -> None:
        lista = self._lista_medios(crear=True)
        for m in [m for m in lista if m.tipo == "CORREO"]:
            lista.remove(m)
        for i, c in enumerate(_correos(texto)):
            lista.append(MedioContacto(tipo="CORREO", valor=c, uso=self._uso_correos, principal=i == 0))

    @property
    def telefono(self) -> str | None:
        lista = self._lista_medios() or []
        return next((m.valor for m in sorted(lista, key=lambda m: (not m.principal, m.id or 0))
                     if m.tipo in ("TELEFONO", "MOVIL")), None)

    @telefono.setter
    def telefono(self, valor: str | None) -> None:
        lista = self._lista_medios(crear=True)
        for m in [m for m in lista if m.tipo == "TELEFONO"]:
            lista.remove(m)
        if valor and str(valor).strip():
            lista.append(MedioContacto(tipo="TELEFONO", valor=str(valor).strip()[:200], principal=True))

    @property
    def direccion(self) -> str | None:
        lista = self._lista_direcciones() or []
        d = next(iter(sorted(lista, key=lambda d: (d.tipo != self._tipo_direccion, not d.principal, d.id or 0))), None)
        return d.texto() if d else None

    @direccion.setter
    def direccion(self, texto: str | None) -> None:
        lista = self._lista_direcciones(crear=True)
        actual = next((d for d in lista if d.tipo == self._tipo_direccion and d.principal), None)
        if not texto or not str(texto).strip():
            if actual is not None:
                lista.remove(actual)
            return
        if actual is None:
            lista.append(Direccion(tipo=self._tipo_direccion, linea1=str(texto).strip()[:300], principal=True,
                                   pais=getattr(self, "pais", None)))
        elif actual.texto() != str(texto).strip():
            actual.linea1, actual.linea2, actual.ciudad, actual.region, actual.codigo_postal = (
                str(texto).strip()[:300], None, None, None, None)


class ExtensionDeTercero(ConContacto):
    """Proveedor o transportista: su contacto vive en su tercero (se crea al
    escribir un dato de contacto si aún no lo tiene; ver _completar_terceros)."""

    _rol_tercero = "PROVEEDOR"

    def _tercero_propio(self, crear: bool):
        if self.tercero is None and crear:
            t = Tercero(nombre=getattr(self, "nombre", None) or "", activo=True)
            t.roles.append(TerceroRol(rol=self._rol_tercero))
            self.tercero = t
        return self.tercero

    def _lista_medios(self, crear: bool = False):
        t = self._tercero_propio(crear)
        return t.medios if t is not None else []

    def _lista_direcciones(self, crear: bool = False):
        t = self._tercero_propio(crear)
        return t.direcciones if t is not None else []

    @property
    def contacto(self) -> str | None:
        t = self.tercero
        return next((c.nombre for c in sorted(t.contactos, key=lambda c: c.id or 0)), None) if t is not None else None

    @contacto.setter
    def contacto(self, nombre: str | None) -> None:
        from app.modelos.maestros import Contacto

        t = self._tercero_propio(crear=bool(nombre))
        if t is None:
            return
        actual = next(iter(sorted(t.contactos, key=lambda c: c.id or 0)), None)
        if not nombre or not str(nombre).strip():
            if actual is not None:
                t.contactos.remove(actual)
        elif actual is None:
            t.contactos.append(Contacto(nombre=str(nombre).strip()[:120], rol="LOGISTICA", activo=True))
        else:
            actual.nombre = str(nombre).strip()[:120]




@event.listens_for(Session, "before_flush")
def _completar_terceros(db: Session, _contexto, _instancias) -> None:
    """El tercero de un proveedor o transportista lleva su identidad: nombre,
    razón social, identificación fiscal y país; uno nuevo toma un código libre."""
    for obj in [*db.new, *db.dirty]:
        if not isinstance(obj, ExtensionDeTercero) or obj.tercero is None:
            continue
        t = obj.tercero
        if obj.nombre and t.nombre != obj.nombre:
            t.nombre = obj.nombre
        for k in ("razon_social", "id_fiscal", "pais"):
            v = getattr(obj, k, None)
            if v and getattr(t, k) != v:
                setattr(t, k, v)
        if not t.codigo:
            base = "".join(ch for ch in (obj.codigo or obj.nombre or "T").upper() if ch.isalnum() or ch in "._-")[:26] or "T"
            pendientes = {x.codigo for x in db.new if isinstance(x, Tercero) and x is not t}
            codigo, n = base, 1
            while codigo in pendientes or db.scalar(select(Tercero.id).where(Tercero.codigo == codigo)):
                n += 1
                codigo = f"{base}-{n}"
            t.codigo = codigo
