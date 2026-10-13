"""Núcleo comercial genérico: terceros (clientes, proveedores, transportistas),
documentos comerciales (facturas emitidas y recibidas, notas de crédito y
débito, proformas), impuestos, vencimientos, pagos y su aplicación.

La factura comercial del proveedor contra una OC (modelos/facturacion.py) es
un documento operativo de importación; al finalizarse se registra aquí como
documento recibido (cuentas por pagar) sin perder su relación con la OC, los
packing lists y el transporte.

Reglas que garantiza la base:
- importes en NUMERIC y totales guardados al emitir (core/dinero.py);
- número único por serie, asignado al emitir con el contador bloqueado;
- un documento emitido no se edita: se anula o se rectifica con una nota;
- lo aplicado a un documento nunca supera su saldo (servicio) y cada
  aplicación sale de un pago o de una nota de crédito, nunca de los dos.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import Cantidad, Importe, Precio, Tasa, ahora

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


# ---- Configuración de la facturación --------------------------------------------------------
class TipoDocumento(DeOrganizacion, Base):
    """Clase de documento comercial y su comportamiento: si se emite o se
    recibe, su signo (una nota de crédito resta), si afecta el saldo del
    tercero y si exige un documento de origen."""

    __tablename__ = "tipos_documento"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "codigo", name="uq_tipos_documento_org_codigo"),
        CheckConstraint("clase IN ('FACTURA', 'NOTA_CREDITO', 'NOTA_DEBITO', 'PROFORMA')", name="ck_tipos_documento_clase"),
        CheckConstraint("direccion IN ('EMITIDO', 'RECIBIDO')", name="ck_tipos_documento_direccion"),
        CheckConstraint("signo IN (1, -1)", name="ck_tipos_documento_signo"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    clase: Mapped[str] = mapped_column(String(15))
    direccion: Mapped[str] = mapped_column(String(10))
    signo: Mapped[int] = mapped_column(Integer, default=1)
    afecta_saldo: Mapped[bool] = mapped_column(Boolean, default=True)
    requiere_origen: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Impuesto(DeOrganizacion, Base):
    """Impuesto de los documentos comerciales (IVA, retenciones…) con su
    jurisdicción y vigencia. Distinto de reglas_impuesto, que son los
    impuestos de importación para estimar el costo de un producto."""

    __tablename__ = "impuestos"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "codigo", "vigente_desde", name="uq_impuestos_org_codigo_desde"),
        CheckConstraint("tipo IN ('PORCENTAJE', 'FIJO')", name="ck_impuestos_tipo"),
        CheckConstraint("tasa >= 0", name="ck_impuestos_tasa"),
        CheckConstraint("vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde",
                        name="ck_impuestos_vigencia"),
        ForeignKeyConstraint(["pais"], ["paises.codigo"], name="fk_impuestos_pais"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(12), default="PORCENTAJE")
    tasa: Mapped[float] = mapped_column(Tasa)  # porcentaje (13 = 13 %) o importe fijo por unidad
    pais: Mapped[str | None] = mapped_column(String(2))  # jurisdicción
    es_retencion: Mapped[bool] = mapped_column(Boolean, default=False)  # se resta del total
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CuotaCondicionPago(DeOrganizacion, Base):
    """Cuota de una condición de pago en partes (p. ej. 30 % anticipo, 70 % a 60 días)."""

    __tablename__ = "condicion_pago_cuotas"
    __table_args__ = (
        UniqueConstraint("condicion_id", "numero", name="uq_condicion_pago_cuotas_numero"),
        CheckConstraint("porcentaje > 0 AND porcentaje <= 100", name="ck_condicion_pago_cuotas_porcentaje"),
        CheckConstraint("dias >= 0", name="ck_condicion_pago_cuotas_dias"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    condicion_id: Mapped[int] = mapped_column(ForeignKey("condiciones_pago.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    porcentaje: Mapped[float] = mapped_column(Tasa)
    dias: Mapped[int] = mapped_column(Integer, default=0)


class MetodoPago(DeOrganizacion, Base):
    __tablename__ = "metodos_pago"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_metodos_pago_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class TipoCambio(DeOrganizacion, Base):
    """Tasa de una moneda a otra en una fecha (1 origen = tasa destino)."""

    __tablename__ = "tipos_cambio"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "moneda_origen", "moneda_destino", "fecha", name="uq_tipos_cambio_dia"),
        CheckConstraint("tasa > 0", name="ck_tipos_cambio_tasa"),
        CheckConstraint("moneda_origen <> moneda_destino", name="ck_tipos_cambio_monedas"),
        _fk_codigo("moneda_origen", "monedas", "tipos_cambio"),
        _fk_codigo("moneda_destino", "monedas", "tipos_cambio"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    moneda_origen: Mapped[str] = mapped_column(String(3))
    moneda_destino: Mapped[str] = mapped_column(String(3))
    fecha: Mapped[date] = mapped_column(Date, index=True)
    tasa: Mapped[float] = mapped_column(Numeric(18, 8))
    fuente: Mapped[str | None] = mapped_column(String(80))


class ConfiguracionFiscal(DeOrganizacion, Base):
    """Cómo factura una sociedad: régimen, redondeo, si la numeración legal
    exige no dejar huecos y el proveedor de facturación electrónica."""

    __tablename__ = "configuracion_fiscal"
    __table_args__ = (
        UniqueConstraint("sociedad_id", name="uq_configuracion_fiscal_sociedad"),
        CheckConstraint("redondeo IN ('LINEA', 'DOCUMENTO')", name="ck_configuracion_fiscal_redondeo"),
        ForeignKeyConstraint(["pais"], ["paises.codigo"], name="fk_configuracion_fiscal_pais"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sociedad_id: Mapped[int] = mapped_column(ForeignKey("sociedades.id", ondelete="CASCADE"))
    pais: Mapped[str | None] = mapped_column(String(2))
    regimen: Mapped[str | None] = mapped_column(String(80))
    redondeo: Mapped[str] = mapped_column(String(10), default="LINEA")
    sin_huecos: Mapped[bool] = mapped_column(Boolean, default=False)
    impuestos_defecto: Mapped[str | None] = mapped_column(String(200))  # códigos separados por coma
    proveedor_electronico: Mapped[str | None] = mapped_column(String(60))
    datos: Mapped[dict] = mapped_column(JSON, default=dict)


class PlantillaDocumento(DeOrganizacion, Base):
    """Textos de impresión de un tipo de documento en un idioma."""

    __tablename__ = "plantillas_documento"
    __table_args__ = (UniqueConstraint("tipo_documento_id", "idioma", name="uq_plantillas_documento_tipo_idioma"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_documento_id: Mapped[int] = mapped_column(ForeignKey("tipos_documento.id", ondelete="CASCADE"), index=True)
    idioma: Mapped[str] = mapped_column(String(5), default="es")
    titulo: Mapped[str | None] = mapped_column(String(120))
    encabezado: Mapped[str | None] = mapped_column(Text)
    pie: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ---- Documentos -------------------------------------------------------------------------------
ESTADOS_DOCUMENTO = ("BORRADOR", "EMITIDO", "ANULADO")


class Documento(DeOrganizacion, Base):
    __tablename__ = "documentos"
    __table_args__ = (
        UniqueConstraint("serie_id", "numero", name="uq_documentos_serie_numero"),
        Index("ux_documentos_recibido", "organizacion_id", "tercero_id", "tipo_documento_id", "referencia_externa",
              unique=True, sqlite_where=text("referencia_externa IS NOT NULL AND estado <> 'ANULADO'"),
              postgresql_where=text("referencia_externa IS NOT NULL AND estado <> 'ANULADO'")),
        UniqueConstraint("factura_id", name="uq_documentos_factura"),
        CheckConstraint("estado IN ('BORRADOR', 'EMITIDO', 'ANULADO')", name="ck_documentos_estado"),
        CheckConstraint("tipo_cambio > 0", name="ck_documentos_tipo_cambio"),
        CheckConstraint("total >= 0 AND subtotal >= 0 AND impuestos >= 0 AND retenciones >= 0 AND descuentos >= 0",
                        name="ck_documentos_importes"),
        CheckConstraint("estado = 'BORRADOR' OR (fecha IS NOT NULL AND (numero IS NOT NULL OR referencia_externa IS NOT NULL))",
                        name="ck_documentos_emitido_numerado"),
        CheckConstraint("fecha_vencimiento IS NULL OR fecha IS NULL OR fecha_vencimiento >= fecha",
                        name="ck_documentos_vencimiento"),
        _fk_codigo("moneda", "monedas", "documentos"),
        _fk_codigo("condicion_pago", "condiciones_pago", "documentos"),
        UniqueConstraint("id", "organizacion_id", name="uq_documentos_id_org"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    tipo_documento_id: Mapped[int] = mapped_column(ForeignKey("tipos_documento.id"), index=True)
    serie_id: Mapped[int | None] = mapped_column(ForeignKey("series_documentales.id"), index=True)
    numero: Mapped[str | None] = mapped_column(String(40))  # asignado al emitir
    referencia_externa: Mapped[str | None] = mapped_column(String(60))  # número del tercero (recibidos)
    estado: Mapped[str] = mapped_column(String(10), default="BORRADOR", index=True)
    sociedad_id: Mapped[int] = mapped_column(ForeignKey("sociedades.id"), index=True)
    tercero_id: Mapped[int] = mapped_column(ForeignKey("terceros.id"), index=True)
    fecha: Mapped[date | None] = mapped_column(Date, index=True)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, index=True)
    moneda: Mapped[str] = mapped_column(String(3))
    tipo_cambio: Mapped[float] = mapped_column(Numeric(18, 8), default=1)  # a la moneda de la sociedad
    condicion_pago: Mapped[str | None] = mapped_column(String(20))
    notas: Mapped[str | None] = mapped_column(Text)
    # Totales guardados al emitir (en borrador se recalculan con cada cambio)
    subtotal: Mapped[float] = mapped_column(Importe, default=0)
    descuentos: Mapped[float] = mapped_column(Importe, default=0)
    impuestos: Mapped[float] = mapped_column(Importe, default=0)
    retenciones: Mapped[float] = mapped_column(Importe, default=0)
    total: Mapped[float] = mapped_column(Importe, default=0)
    # Datos del emisor y del receptor tal como eran al emitir
    copia: Mapped[dict] = mapped_column(JSON, default=dict)
    # Factura comercial de proveedor (contra OC) que este documento registra
    factura_id: Mapped[int | None] = mapped_column(ForeignKey("facturas.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    emitido_en: Mapped[datetime | None] = mapped_column(DateTime)
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime)
    motivo_anulacion: Mapped[str | None] = mapped_column(String(500))

    tipo: Mapped[TipoDocumento] = relationship()
    tercero: Mapped[Tercero] = relationship()
    lineas: Mapped[list["DocumentoLinea"]] = relationship(
        back_populates="documento", cascade="all, delete-orphan", order_by="DocumentoLinea.orden")
    vencimientos: Mapped[list["Vencimiento"]] = relationship(
        back_populates="documento", cascade="all, delete-orphan", order_by="Vencimiento.numero")


class DocumentoLinea(DeOrganizacion, Base):
    """Línea de un documento: un artículo, una posición de OC, una línea de
    factura de proveedor o un concepto libre (flete, servicio, cargo)."""

    __tablename__ = "documento_lineas"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_documento_lineas_cantidad"),
        CheckConstraint("precio_unitario >= 0", name="ck_documento_lineas_precio"),
        CheckConstraint("descuento_pct >= 0 AND descuento_pct <= 100", name="ck_documento_lineas_descuento"),
        CheckConstraint("subtotal >= 0 AND impuestos >= 0 AND total >= 0", name="ck_documento_lineas_importes"),
        _fk_codigo("unidad", "unidades_medida", "documento_lineas"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    posicion_oc_id: Mapped[int | None] = mapped_column(ForeignKey("posiciones_oc.id"), index=True)
    factura_linea_id: Mapped[int | None] = mapped_column(ForeignKey("factura_lineas.id"), index=True)
    codigo: Mapped[str | None] = mapped_column(String(40))  # copia del código del artículo
    descripcion: Mapped[str] = mapped_column(String(300))
    cantidad: Mapped[float] = mapped_column(Cantidad)
    unidad: Mapped[str | None] = mapped_column(String(10))
    precio_unitario: Mapped[float] = mapped_column(Precio)
    descuento_pct: Mapped[float] = mapped_column(Tasa, default=0)
    descuento: Mapped[float] = mapped_column(Importe, default=0)
    subtotal: Mapped[float] = mapped_column(Importe, default=0)  # cantidad × precio − descuento
    impuestos: Mapped[float] = mapped_column(Importe, default=0)
    retenciones: Mapped[float] = mapped_column(Importe, default=0)
    total: Mapped[float] = mapped_column(Importe, default=0)
    impuestos_codigos: Mapped[str | None] = mapped_column(String(200))  # los que se aplican (borrador)

    documento: Mapped[Documento] = relationship(back_populates="lineas")
    aplicados: Mapped[list["LineaImpuesto"]] = relationship(back_populates="linea", cascade="all, delete-orphan")


class LineaImpuesto(DeOrganizacion, Base):
    """Impuesto aplicado a una línea: copia de la tasa vigente (un cambio de
    tasa no altera documentos pasados)."""

    __tablename__ = "linea_impuestos"
    __table_args__ = (
        UniqueConstraint("linea_id", "codigo", name="uq_linea_impuestos_linea_codigo"),
        CheckConstraint("base >= 0 AND importe >= 0 AND tasa >= 0", name="ck_linea_impuestos_importes"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    linea_id: Mapped[int] = mapped_column(ForeignKey("documento_lineas.id", ondelete="CASCADE"), index=True)
    impuesto_id: Mapped[int | None] = mapped_column(ForeignKey("impuestos.id", ondelete="SET NULL"), index=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(12))
    tasa: Mapped[float] = mapped_column(Tasa)
    base: Mapped[float] = mapped_column(Importe)
    importe: Mapped[float] = mapped_column(Importe)
    es_retencion: Mapped[bool] = mapped_column(Boolean, default=False)

    linea: Mapped[DocumentoLinea] = relationship(back_populates="aplicados")


class Vencimiento(DeOrganizacion, Base):
    """Cuota a cobrar o pagar de un documento emitido."""

    __tablename__ = "documento_vencimientos"
    __table_args__ = (
        UniqueConstraint("documento_id", "numero", name="uq_documento_vencimientos_numero"),
        CheckConstraint("importe >= 0", name="ck_documento_vencimientos_importe"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    importe: Mapped[float] = mapped_column(Importe)

    documento: Mapped[Documento] = relationship(back_populates="vencimientos")


class RelacionDocumento(DeOrganizacion, Base):
    """Un documento rectifica, anula, sustituye o se generó desde otro."""

    __tablename__ = "documento_relaciones"
    __table_args__ = (
        UniqueConstraint("origen_id", "destino_id", "tipo", name="uq_documento_relaciones"),
        CheckConstraint("origen_id <> destino_id", name="ck_documento_relaciones_distintos"),
        CheckConstraint("tipo IN ('RECTIFICA', 'ANULA', 'SUSTITUYE', 'GENERADO_DESDE')", name="ck_documento_relaciones_tipo"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    origen_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), index=True)  # el nuevo
    destino_id: Mapped[int] = mapped_column(ForeignKey("documentos.id"), index=True)  # al que se refiere
    tipo: Mapped[str] = mapped_column(String(15))


class EnvioDocumento(DeOrganizacion, Base):
    """Estado del envío de un documento a un sistema externo (autoridad fiscal, ERP)."""

    __tablename__ = "documento_envios"
    __table_args__ = (
        UniqueConstraint("documento_id", "sistema", name="uq_documento_envios_sistema"),
        CheckConstraint("estado IN ('PENDIENTE', 'ENVIADO', 'ACEPTADO', 'RECHAZADO', 'ERROR')", name="ck_documento_envios_estado"),
        CheckConstraint("intentos >= 0", name="ck_documento_envios_intentos"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id", ondelete="CASCADE"), index=True)
    sistema: Mapped[str] = mapped_column(String(40))
    estado: Mapped[str] = mapped_column(String(10), default="PENDIENTE")
    identificador_externo: Mapped[str | None] = mapped_column(String(120))
    acuse: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(500))
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class FacturacionRecurrente(DeOrganizacion, Base):
    """Documento que se genera cada cierto tiempo copiando un documento modelo."""

    __tablename__ = "facturacion_recurrente"
    __table_args__ = (
        CheckConstraint("frecuencia IN ('SEMANAL', 'MENSUAL', 'TRIMESTRAL', 'ANUAL')", name="ck_facturacion_recurrente_frecuencia"),
        CheckConstraint("NOT activo OR hasta IS NULL OR hasta >= proxima", name="ck_facturacion_recurrente_vigencia"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    modelo_id: Mapped[int] = mapped_column(ForeignKey("documentos.id"), index=True)
    frecuencia: Mapped[str] = mapped_column(String(12), default="MENSUAL")
    proxima: Mapped[date] = mapped_column(Date, index=True)
    dia: Mapped[int] = mapped_column(Integer, default=1)  # día del mes de referencia (31 = fin de mes)
    hasta: Mapped[date | None] = mapped_column(Date)
    emitir: Mapped[bool] = mapped_column(Boolean, default=False)  # emitir al generar o dejar en borrador
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ---- Pagos ----------------------------------------------------------------------------------
class Pago(DeOrganizacion, Base):
    """Cobro (de un cliente) o pago (a un proveedor)."""

    __tablename__ = "pagos"
    __table_args__ = (
        CheckConstraint("direccion IN ('COBRO', 'PAGO')", name="ck_pagos_direccion"),
        CheckConstraint("estado IN ('REGISTRADO', 'ANULADO')", name="ck_pagos_estado"),
        CheckConstraint("importe > 0", name="ck_pagos_importe"),
        CheckConstraint("tipo_cambio > 0", name="ck_pagos_tipo_cambio"),
        _fk_codigo("moneda", "monedas", "pagos"),
        UniqueConstraint("id", "organizacion_id", name="uq_pagos_id_org"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    direccion: Mapped[str] = mapped_column(String(5))
    estado: Mapped[str] = mapped_column(String(10), default="REGISTRADO", index=True)
    tercero_id: Mapped[int] = mapped_column(ForeignKey("terceros.id"), index=True)
    sociedad_id: Mapped[int] = mapped_column(ForeignKey("sociedades.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    moneda: Mapped[str] = mapped_column(String(3))
    tipo_cambio: Mapped[float] = mapped_column(Numeric(18, 8), default=1)
    importe: Mapped[float] = mapped_column(Importe)
    metodo_pago_id: Mapped[int | None] = mapped_column(ForeignKey("metodos_pago.id"), index=True)
    referencia: Mapped[str | None] = mapped_column(String(80))
    notas: Mapped[str | None] = mapped_column(String(500))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    anulado_en: Mapped[datetime | None] = mapped_column(DateTime)
    motivo_anulacion: Mapped[str | None] = mapped_column(String(500))

    tercero: Mapped[Tercero] = relationship()
    aplicaciones: Mapped[list["Aplicacion"]] = relationship(back_populates="pago", foreign_keys="Aplicacion.pago_id")


class Aplicacion(DeOrganizacion, Base):
    """Cuánto de un pago (o de una nota de crédito) salda un documento y,
    si se indica, cuál de sus cuotas. Permite pagos parciales y un pago para
    varios documentos."""

    __tablename__ = "aplicaciones"
    __table_args__ = (
        CheckConstraint("importe > 0", name="ck_aplicaciones_importe"),
        CheckConstraint("(CASE WHEN pago_id IS NULL THEN 0 ELSE 1 END + CASE WHEN credito_id IS NULL THEN 0 ELSE 1 END) = 1",
                        name="ck_aplicaciones_origen"),
        CheckConstraint("credito_id IS NULL OR credito_id <> documento_id", name="ck_aplicaciones_distintos"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    pago_id: Mapped[int | None] = mapped_column(ForeignKey("pagos.id"), index=True)
    credito_id: Mapped[int | None] = mapped_column(ForeignKey("documentos.id"), index=True)  # nota de crédito
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id"), index=True)
    vencimiento_id: Mapped[int | None] = mapped_column(ForeignKey("documento_vencimientos.id"), index=True)
    importe: Mapped[float] = mapped_column(Importe)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)  # se desactiva al anular el pago o la nota
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    pago: Mapped[Pago | None] = relationship(back_populates="aplicaciones", foreign_keys=[pago_id])
