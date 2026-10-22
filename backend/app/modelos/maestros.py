"""Datos maestros: proveedores, estructura de la empresa (sociedades, centros,
almacenes, contactos), países, acuerdos, marcas, escalas de valores, estados
de liberación, atributos y artículos (variantes de los productos).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    UniqueConstraint,
    event,
    false,
    select,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, Session, mapped_column, object_session, relationship
from sqlalchemy.orm.attributes import flag_dirty

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import ahora
from app.modelos.comercial import ConContacto, ExtensionDeTercero

if TYPE_CHECKING:
    from app.modelos.comercial import Direccion, MedioContacto, Tercero
    from app.modelos.productos import Producto
    from app.modelos.transporte import Puerto


proveedor_marcas = Table(
    "proveedor_marcas", Base.metadata,
    Column("proveedor_id", ForeignKey("proveedores.id", ondelete="CASCADE"), primary_key=True),
    Column("marca_id", ForeignKey("marcas.id", ondelete="CASCADE"), primary_key=True, index=True),
)


proveedor_sociedades = Table(
    "proveedor_sociedades", Base.metadata,
    Column("proveedor_id", ForeignKey("proveedores.id", ondelete="CASCADE"), primary_key=True),
    Column("sociedad_id", ForeignKey("sociedades.id", ondelete="CASCADE"), primary_key=True, index=True),
)


centro_puertos = Table(
    "centro_puertos", Base.metadata,
    Column("centro_id", ForeignKey("centros.id", ondelete="CASCADE"), primary_key=True),
    Column("puerto_id", ForeignKey("puertos.id", ondelete="CASCADE"), primary_key=True, index=True),
)


class Proveedor(ExtensionDeTercero, DeOrganizacion, Base):
    """Proveedor (exportador). Maneja sus propias marcas y artículos y solo
    trabaja con las sociedades que tiene asignadas."""

    __tablename__ = "proveedores"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_proveedores_org_codigo"),
                      UniqueConstraint("tercero_id", name="uq_proveedores_tercero"))
    id: Mapped[int] = mapped_column(primary_key=True)
    # Identidad fiscal compartida con sus otros roles (cliente, transportista): modelos/comercial.py
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("terceros.id", name="fk_proveedores_tercero_id"))
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(200))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    id_fiscal: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(2))
    # Dirección, contacto, correos y teléfono viven en su tercero (ExtensionDeTercero)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    tercero: Mapped["Tercero | None"] = relationship()
    marcas: Mapped[list["Marca"]] = relationship(secondary=proveedor_marcas, order_by="Marca.codigo")
    sociedades: Mapped[list["Sociedad"]] = relationship(secondary=proveedor_sociedades, order_by="Sociedad.codigo")


class Sociedad(ConContacto, DeOrganizacion, Base):
    """Sociedad legal de la empresa (la razón social que compra e importa; en un
    ERP suele llamarse compañía o sociedad). Sus centros son bodegas fiscales."""

    __tablename__ = "sociedades"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_sociedades_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(120))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    id_fiscal: Mapped[str | None] = mapped_column(String(30))  # NIT / RUC
    pais: Mapped[str | None] = mapped_column(String(2))
    moneda: Mapped[str] = mapped_column(String(3), default="USD")
    # Dirección fiscal y correos de facturación: direcciones y medios_contacto (ConContacto)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    centros: Mapped[list["Centro"]] = relationship(back_populates="sociedad", order_by="Centro.codigo")
    medios: Mapped[list["MedioContacto"]] = relationship(cascade="all, delete-orphan", foreign_keys="MedioContacto.sociedad_id")
    direcciones: Mapped[list["Direccion"]] = relationship(cascade="all, delete-orphan", foreign_keys="Direccion.sociedad_id")
    _uso_correos = "FACTURACION"


class Centro(ConContacto, DeOrganizacion, Base):
    """Centro (planta o bodega) de una sociedad. Es la bodega fiscal a la que
    llega la mercancía (notify party) y, como centro de destino de la OC,
    indica el país final. Su puerto es el de llegada de los embarques."""

    __tablename__ = "centros"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_centros_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(10))
    sociedad_id: Mapped[int] = mapped_column(ForeignKey("sociedades.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(20), default="BODEGA_FISCAL")
    pais: Mapped[str | None] = mapped_column(String(2))
    puerto: Mapped[str | None] = mapped_column(String(10))  # puerto de llegada
    # Dirección de entrega y correos del notify: direcciones y medios_contacto (ConContacto)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sociedad: Mapped[Sociedad] = relationship(back_populates="centros")
    medios: Mapped[list["MedioContacto"]] = relationship(cascade="all, delete-orphan", foreign_keys="MedioContacto.centro_id")
    direcciones: Mapped[list["Direccion"]] = relationship(cascade="all, delete-orphan", foreign_keys="Direccion.centro_id")
    _uso_correos = "NOTIFY"
    _tipo_direccion = "ENTREGA"
    # Puertos por donde puede llegar (el principal es "puerto"); los del
    # embarque se sugieren de aquí y se pueden cambiar entre ellos
    puertos: Mapped[list["Puerto"]] = relationship(secondary=centro_puertos, order_by="Puerto.codigo")


class Contacto(ConContacto, DeOrganizacion, Base):
    """Persona de contacto de una sociedad (facturación) o de un centro
    (notify party, recepción)."""

    __tablename__ = "contactos"
    id: Mapped[int] = mapped_column(primary_key=True)
    sociedad_id: Mapped[int | None] = mapped_column(ForeignKey("sociedades.id"), index=True)
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centros.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    cargo: Mapped[str | None] = mapped_column(String(120))
    rol: Mapped[str] = mapped_column(String(15), default="NOTIFY")  # FACTURACION | NOTIFY | LOGISTICA
    # Persona de contacto de un tercero (proveedor, transportista…)
    tercero_id: Mapped[int | None] = mapped_column(
        ForeignKey("terceros.id", ondelete="CASCADE", name="fk_contactos_tercero_id"), index=True)
    # Correos y teléfono: medios_contacto (ConContacto)
    medios: Mapped[list["MedioContacto"]] = relationship(cascade="all, delete-orphan", foreign_keys="MedioContacto.contacto_id")

    def _lista_direcciones(self, crear: bool = False):
        return []
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Almacen(DeOrganizacion, Base):
    """Separación lógica del inventario en el sistema (virtual, detalle,
    mayoreo…); no es un lugar físico. Cada posición de la OC elige el suyo."""

    __tablename__ = "almacenes"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_almacenes_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10))
    sociedad_id: Mapped[int] = mapped_column(ForeignKey("sociedades.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(10))  # VIRTUAL | DETALLE | MAYOREO
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sociedad: Mapped[Sociedad] = relationship()


class Pais(Base):
    __tablename__ = "paises"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(2), unique=True)  # ISO 3166-1 alfa-2
    nombre: Mapped[str] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(10))  # región de origen para los lead times (ASIA…)
    nombre_id_fiscal: Mapped[str | None] = mapped_column(String(30))  # NIT, RUC, RFC, EIN…: como se lee en los documentos
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


acuerdo_origenes = Table(
    "acuerdo_origenes", Base.metadata,
    Column("acuerdo_id", ForeignKey("acuerdos_comerciales.id", ondelete="CASCADE"), primary_key=True),
    Column("pais_id", ForeignKey("paises.id"), primary_key=True, index=True),
)
acuerdo_destinos = Table(
    "acuerdo_destinos", Base.metadata,
    Column("acuerdo_id", ForeignKey("acuerdos_comerciales.id", ondelete="CASCADE"), primary_key=True),
    Column("pais_id", ForeignKey("paises.id"), primary_key=True, index=True),
)


class AcuerdoComercial(Base):
    """Tratado o acuerdo comercial vigente: mercancías originarias de sus países
    de origen entran con preferencia arancelaria a sus países destino si se
    presenta la prueba de origen que pide."""

    __tablename__ = "acuerdos_comerciales"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    prueba: Mapped[str | None] = mapped_column(String(200))  # certificado o declaración de origen
    nota: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # Países de origen cuyas mercancías tienen la preferencia y países destino donde aplica
    origenes: Mapped[list[Pais]] = relationship(secondary=acuerdo_origenes, order_by="Pais.codigo")
    destinos: Mapped[list[Pais]] = relationship(secondary=acuerdo_destinos, order_by="Pais.codigo")


class Marca(DeOrganizacion, Base):
    __tablename__ = "marcas"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_marcas_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(100))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class EscalaValores(DeOrganizacion, Base):
    """Escala de valores reutilizable de un atributo de variante (una serie de
    medidas, presentaciones 250 ml / 500 ml / 1 L, concentraciones…): sus valores
    en orden y cómo se forma el código de cada uno. Al crear las variantes de un
    producto se parte de una escala; el código se genera con la regla o se escribe."""

    __tablename__ = "escalas_valores"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_escalas_valores_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    atributo: Mapped[str] = mapped_column(String(20))  # código del atributo de variante cuyos valores ordena
    # MULTIPLICAR: valor numérico × factor (7.5 × 10 → 075); CONSECUTIVO: 001, 002…;
    # VALOR: el mismo valor (S, M, XL). Un código escrito en la lista manda.
    regla: Mapped[str] = mapped_column(String(15), default="CONSECUTIVO")
    factor: Mapped[int | None] = mapped_column(Integer, default=10)
    longitud: Mapped[int | None] = mapped_column(Integer, default=3)
    # Valores en orden, cada uno con su código escrito (o null): [{"valor": "7", "codigo": "070"}]
    lista_valores: Mapped[list] = mapped_column("valores", JSON, default=list)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def valores(self) -> str:
        """Los valores como se escriben en el formulario ("6, 6.5, 7=070")."""
        return ", ".join(f"{x['valor']}={x['codigo']}" if x.get("codigo") else x["valor"] for x in self.lista_valores or [])

    @valores.setter
    def valores(self, texto: str) -> None:
        from app.modulos.maestros.escalas import valores_de

        self.lista_valores = [{"valor": v, "codigo": c} for v, c in valores_de(texto)]


class ValorLista(DeOrganizacion, Base):
    """Valor de una lista simple (tipos de centro, almacén, contacto, impuesto
    y documento técnico; modalidades e hitos del transporte). Las listas que
    tienen reglas propias y que los documentos referencian (monedas, unidades,
    modos de transporte, incoterms y condiciones de pago) tienen su tabla."""

    __tablename__ = "valores_lista"
    __table_args__ = (UniqueConstraint("organizacion_id", "lista", "codigo", name="uq_valores_lista_org_lista_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    lista: Mapped[str] = mapped_column(String(30), index=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Atributos de algunas listas: modo de transporte de una modalidad, si es
    # consolidada, y estados del embarque en los que se registra un hito
    padre: Mapped[str | None] = mapped_column(String(20))
    consolidado: Mapped[bool | None] = mapped_column(Boolean)
    estados: Mapped[str | None] = mapped_column(String(120))  # varias opciones, separadas por coma


class Moneda(DeOrganizacion, Base):
    """Moneda de OCs, facturas y documentos: decimales con los que se redondean
    sus importes (core/dinero.py) y cómo se escribe el total en letras."""

    __tablename__ = "monedas"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_monedas_org_codigo"),
                      CheckConstraint("decimales BETWEEN 0 AND 4", name="ck_monedas_decimales"))
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(3))  # ISO 4217
    nombre: Mapped[str] = mapped_column(String(120))
    simbolo: Mapped[str | None] = mapped_column(String(5))
    decimales: Mapped[int] = mapped_column(Integer, default=2)
    letras_en: Mapped[str | None] = mapped_column(String(120))  # singular|plural
    letras_es: Mapped[str | None] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class UnidadMedida(DeOrganizacion, Base):
    """Unidad en que se cuenta o mide un artículo: lo contable va en enteros.
    Con `base` y `equivale` se convierte a otra unidad de la lista (una docena
    = 12 unidades, un gramo = 0.001 kg): cualquier magnitud, sin tocar el código."""

    __tablename__ = "unidades_medida"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_unidades_medida_org_codigo"),
                      CheckConstraint("(base IS NULL) = (equivale IS NULL)", name="ck_unidades_medida_base_equivale"),
                      CheckConstraint("equivale IS NULL OR equivale > 0", name="ck_unidades_medida_equivale"),
                      CheckConstraint("base IS NULL OR base <> codigo", name="ck_unidades_medida_base"))
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(120))
    nombre_plural: Mapped[str | None] = mapped_column(String(120))
    alias: Mapped[str | None] = mapped_column(String(300))  # otros nombres en archivos, separados por coma
    contable: Mapped[bool] = mapped_column(Boolean, default=True)
    compuesto: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())  # solo packs y kits
    base: Mapped[str | None] = mapped_column(String(10))  # código de la unidad a la que se convierte
    equivale: Mapped[float | None] = mapped_column(Float)  # cuántas unidades base es una de esta
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ModoTransporte(DeOrganizacion, Base):
    """Cómo viaja la mercancía (marítimo, aéreo, terrestre…) y cómo se
    sugieren sus unidades de carga."""

    __tablename__ = "modos_transporte"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_modos_transporte_org_codigo"),
                      CheckConstraint("calculo IN ('VOLUMEN', 'PESO_COBRABLE')", name="ck_modos_transporte_calculo"),
                      CheckConstraint("factor IS NULL OR factor > 0", name="ck_modos_transporte_factor"))
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    calculo: Mapped[str] = mapped_column(String(20), default="VOLUMEN")
    factor: Mapped[float | None] = mapped_column(Float)  # kg por m³ (peso cobrable)
    icono: Mapped[str | None] = mapped_column(String(20))
    documento: Mapped[str | None] = mapped_column(String(40))  # B/L, AWB…
    etiqueta_puerto: Mapped[str | None] = mapped_column(String(40))
    etiqueta_transportista: Mapped[str | None] = mapped_column(String(40))
    etiqueta_unidad: Mapped[str | None] = mapped_column(String(80))  # singular|plural
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Incoterm(DeOrganizacion, Base):
    __tablename__ = "incoterms"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_incoterms_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CondicionPago(DeOrganizacion, Base):
    """Condición comercial de pago (anticipo, neto 30…). `dias` es el plazo
    del vencimiento único; las condiciones en cuotas las detallan sus cuotas."""

    __tablename__ = "condiciones_pago"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_condiciones_pago_org_codigo"),
                      CheckConstraint("dias IS NULL OR dias >= 0", name="ck_condiciones_pago_dias"))
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    alias: Mapped[str | None] = mapped_column(String(300))
    dias: Mapped[int | None] = mapped_column(Integer)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class EstadoLiberacion(DeOrganizacion, Base):
    """Estado de liberación de una OC tal como lo manda el ERP de la empresa.

    Hay dos liberaciones (comercial y logística) y cada empresa define sus
    códigos (los que manda su ERP, p. ej. comercial C/P, logística 300/301/304), su nombre,
    si permite facturar, cuál es el de «liberada con cambios» y cuál se usa
    cuando el archivo no trae el dato. `alias` son otras palabras que el
    importador acepta (separadas por coma)."""

    __tablename__ = "estados_liberacion"
    __table_args__ = (UniqueConstraint("organizacion_id", "tipo", "codigo", name="uq_estados_liberacion_org_tipo_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))  # COMERCIAL | LOGISTICA
    codigo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(80))
    libera: Mapped[bool] = mapped_column(Boolean, default=False)  # con este estado se puede facturar
    con_cambios: Mapped[bool] = mapped_column(Boolean, default=False)  # liberada que cambió después
    predeterminado: Mapped[bool] = mapped_column(Boolean, default=False)  # si el archivo no trae el dato
    alias: Mapped[str | None] = mapped_column(String(300))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Articulo(DeOrganizacion, Base):
    """Variante de un producto (SKU): lo que se compra, se factura, se empaca y se
    etiqueta. Solo guarda lo que es suyo: su código, su unidad, su peso y si es
    simple o compuesta. Lo que la distingue de las otras variantes son sus valores
    de atributo (articulo_atributos); sus códigos de barras, del proveedor o de
    pack viven en articulo_codigos; un pack o un kit dice su contenido en
    articulo_componentes. Marca, modelo, proveedor y familia son del producto."""

    __tablename__ = "articulos"
    __table_args__ = (UniqueConstraint("organizacion_id", "sku", name="uq_articulos_org_sku"),
                      CheckConstraint("tipo IN ('SOLIDO', 'PREPACK')", name="ck_articulos_tipo"))
    id: Mapped[int] = mapped_column(primary_key=True)
    # Código de artículo de la empresa (numérico o alfanumérico, el formato lo define cada empresa)
    sku: Mapped[str] = mapped_column(String(40))  # texto: conserva ceros
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", name="fk_articulos_producto_id"), index=True)
    descripcion: Mapped[str | None] = mapped_column(String(300))  # se arma con el producto y los valores
    unidad: Mapped[str] = mapped_column(String(5))  # código de la lista de unidades (unidades_medida)
    # Peso neto de una unidad (en un compuesto, todo su contenido), en kg. La tara es de cada nivel de empaque.
    peso_unitario: Mapped[float | None] = mapped_column(Float)
    tipo: Mapped[str] = mapped_column(String(10), default="SOLIDO")  # SOLIDO (simple) | PREPACK (pack o kit)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    producto: Mapped[Producto] = relationship(back_populates="articulos")
    # Valores de los atributos de variante (la fuente de verdad de lo que distingue a la variante)
    atributos: Mapped[list["ArticuloAtributo"]] = relationship(
        back_populates="articulo", cascade="all, delete-orphan", lazy="selectin", order_by="ArticuloAtributo.id")
    codigos: Mapped[list["ArticuloCodigo"]] = relationship(
        back_populates="articulo", cascade="all, delete-orphan", lazy="selectin", order_by="ArticuloCodigo.id")
    componentes: Mapped[list["ArticuloComponente"]] = relationship(
        back_populates="compuesto", cascade="all, delete-orphan", foreign_keys="ArticuloComponente.compuesto_id",
        order_by="ArticuloComponente.id")

    # ---- Lo que es del producto, leído desde la variante (también en consultas) ----------
    @hybrid_property
    def generico(self) -> str | None:
        return self.producto.codigo_generico if self.producto is not None else None

    @generico.inplace.expression
    @classmethod
    def _generico_expr(cls):
        from app.modelos.productos import Producto

        return select(Producto.codigo_generico).where(Producto.id == cls.producto_id).scalar_subquery()

    @hybrid_property
    def proveedor_id(self) -> int | None:
        return self.producto.proveedor_id if self.producto is not None else None

    @proveedor_id.inplace.expression
    @classmethod
    def _proveedor_id_expr(cls):
        from app.modelos.productos import Producto

        return select(Producto.proveedor_id).where(Producto.id == cls.producto_id).scalar_subquery()

    @property
    def grupo_producto(self):
        return self.producto.grupo_producto if self.producto is not None else None

    @property
    def familia_efectiva(self):
        """La familia del artículo: la de su producto (si el producto tiene una categoría, su familia)."""
        g = self.grupo_producto
        return g.familia if g is not None else None

    # ---- Códigos -------------------------------------------------------------------------
    def codigo(self, tipo: str) -> str | None:
        """El primer código de ese tipo (BARRAS, PROVEEDOR, PACK)."""
        return next((c.valor for c in self.codigos if c.tipo == tipo), None)

    def poner_codigo(self, tipo: str, valor: str | None, proveedor_id: int | None = None) -> None:
        """Deja un solo código de ese tipo (vacío lo quita); los demás tipos no cambian."""
        valor = (valor or "").strip() or None
        actuales = [c for c in self.codigos if c.tipo == tipo]
        if actuales and valor and actuales[0].valor == valor and len(actuales) == 1:
            return
        for c in actuales:
            self.codigos.remove(c)
        if valor:
            self.codigos.append(ArticuloCodigo(tipo=tipo, valor=valor[:60], proveedor_id=proveedor_id,
                                               organizacion_id=self.organizacion_id))

    @property
    def codigo_barras(self) -> str | None:
        return self.codigo("BARRAS")

    @property
    def codigo_proveedor(self) -> str | None:
        return self.codigo("PROVEEDOR")

    @property
    def codigo_pack(self) -> str | None:
        """Identificador corto de un pack o kit (p. ej. AB12)."""
        return self.codigo("PACK")

    # ---- Contenido de un compuesto --------------------------------------------------------
    @property
    def total_componentes(self) -> int:
        return sum(c.cantidad for c in self.componentes)

    @property
    def es_kit(self) -> bool:
        """Un kit junta variantes de varios productos; un pack, variantes de su propio producto."""
        return any(c.componente.producto_id != self.producto_id for c in self.componentes)

    # ---- Valores de variante ----------------------------------------------------------------
    @property
    def variantes(self) -> dict:
        """{código del atributo: valor} de los atributos de variante."""
        pendiente = getattr(self, "_variantes_pendientes", None)
        if pendiente is not None:
            return dict(pendiente)
        return {x.atributo.codigo: x.valor for x in self.atributos}

    @variantes.setter
    def variantes(self, valores: dict) -> None:
        # Se aplica al guardar (hook _aplicar_variantes): ahí se conocen los atributos
        self._variantes_pendientes = {k: v for k, v in (valores or {}).items() if v not in (None, "")}
        db = object_session(self)
        if db is not None:
            db.info.setdefault("variantes_pendientes", set()).add(self)
            flag_dirty(self)  # aunque nada más cambie, el guardado aplica los valores


TIPOS_CODIGO = ("BARRAS", "PROVEEDOR", "PACK")


class ArticuloCodigo(DeOrganizacion, Base):
    """Un código de la variante: de barras (GTIN, EAN, UPC), el del proveedor (de
    cuál proveedor) o el identificador de un pack. Una variante puede tener varios."""

    __tablename__ = "articulo_codigos"
    __table_args__ = (UniqueConstraint("articulo_id", "tipo", "valor", name="uq_articulo_codigos_articulo_tipo_valor"),
                      CheckConstraint("tipo IN ('BARRAS', 'PROVEEDOR', 'PACK')", name="ck_articulo_codigos_tipo"))
    id: Mapped[int] = mapped_column(primary_key=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))
    valor: Mapped[str] = mapped_column(String(60), index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)  # en un código del proveedor

    articulo: Mapped[Articulo] = relationship(back_populates="codigos")


class ArticuloComponente(DeOrganizacion, Base):
    """Contenido de un pack o un kit: cuántas unidades de cada variante simple lleva."""

    __tablename__ = "articulo_componentes"
    __table_args__ = (UniqueConstraint("compuesto_id", "componente_id", name="uq_articulo_componentes_compuesto_componente"),
                      CheckConstraint("cantidad >= 1", name="ck_articulo_componentes_cantidad"))
    id: Mapped[int] = mapped_column(primary_key=True)
    compuesto_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="CASCADE"), index=True)
    componente_id: Mapped[int] = mapped_column(ForeignKey("articulos.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)

    compuesto: Mapped[Articulo] = relationship(back_populates="componentes", foreign_keys=[compuesto_id])
    componente: Mapped[Articulo] = relationship(foreign_keys=[componente_id], lazy="joined")


NIVELES_ATRIBUTO = ("PRODUCTO", "VARIANTE")
TIPOS_ATRIBUTO = ("texto", "numero", "opcion", "fecha", "bool", "catalogo")
# Catálogos a los que puede apuntar un atributo de tipo catálogo (su valor es el código del registro)
CATALOGOS_ATRIBUTO = ("marcas",)


class Atributo(DeOrganizacion, Base):
    """Un dato que la empresa define para sus productos o sus variantes: marca,
    modelo, material, número ONU (del producto); talla, color, sabor,
    presentación, concentración (de la variante)… Cada familia dice cuáles usa,
    cuáles son obligatorios (grupos_producto.campos) y con cuáles se distinguen
    sus variantes (grupos_producto.ejes_variante)."""

    __tablename__ = "atributos"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_atributos_org_codigo"),
                      CheckConstraint("nivel IN ('PRODUCTO', 'VARIANTE')", name="ck_atributos_nivel"),
                      CheckConstraint("tipo IN ('texto', 'numero', 'opcion', 'fecha', 'bool', 'catalogo')",
                                      name="ck_atributos_tipo"),
                      CheckConstraint("(tipo = 'catalogo') = (catalogo IS NOT NULL)", name="ck_atributos_catalogo"))
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(60))
    nivel: Mapped[str] = mapped_column(String(10), default="VARIANTE", server_default="VARIANTE")
    # Qué valor lleva: texto libre, un número (en su unidad: 220 V, 500 ml), una de sus opciones,
    # una fecha, sí/no o un registro de un catálogo (catalogo: marcas…)
    tipo: Mapped[str] = mapped_column(String(10), default="texto", server_default="texto")
    opciones: Mapped[str | None] = mapped_column(String(500))  # separadas por coma (tipo opción)
    catalogo: Mapped[str | None] = mapped_column(String(30))  # tipo catálogo
    unidad: Mapped[str | None] = mapped_column(String(10))  # código de la unidad de medida (tipo número)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ArticuloAtributo(DeOrganizacion, Base):
    """Valor de un atributo de variante en un artículo (uno por atributo)."""

    __tablename__ = "articulo_atributos"
    __table_args__ = (UniqueConstraint("articulo_id", "atributo_id", name="uq_articulo_atributos_articulo_atributo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="CASCADE"), index=True)
    atributo_id: Mapped[int] = mapped_column(ForeignKey("atributos.id"), index=True)
    valor: Mapped[str] = mapped_column(String(60))

    articulo: Mapped[Articulo] = relationship(back_populates="atributos")
    atributo: Mapped[Atributo] = relationship(lazy="joined")


@event.listens_for(Session, "before_flush")
def _aplicar_variantes(db, _contexto, _instancias) -> None:
    """Los valores de variante escritos con `articulo.variantes = {...}` pasan a
    sus filas de articulo_atributos (solo atributos de variante que existen)."""
    candidatos = [x for x in {*db.new, *db.dirty, *db.info.pop("variantes_pendientes", set())} if isinstance(x, Articulo)]
    por_codigo = None
    for a in candidatos:
        pendiente = a.__dict__.pop("_variantes_pendientes", None)
        if pendiente is None:
            continue
        if por_codigo is None:
            with db.no_autoflush:
                por_codigo = {x.codigo: x for x in db.scalars(select(Atributo).where(Atributo.nivel == "VARIANTE"))}
        actuales = {x.atributo.codigo: x for x in a.atributos}
        for codigo, x in list(actuales.items()):
            if codigo not in pendiente:
                a.atributos.remove(x)
        for codigo, valor in pendiente.items():
            if codigo not in por_codigo:
                continue
            texto = valor_variante(valor)
            if codigo in actuales:
                if actuales[codigo].valor != texto:
                    actuales[codigo].valor = texto
            else:
                # Misma organización que el artículo (este hook puede correr después del que la asigna)
                a.atributos.append(ArticuloAtributo(atributo=por_codigo[codigo], valor=texto,
                                                    organizacion_id=a.organizacion_id))


def valor_variante(v) -> str:
    """Texto guardado de un valor de variante: un número entero sin «.0»."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)[:60]


class ArticuloVersion(DeOrganizacion, Base):
    """Cómo era el artículo cuando un documento lo usó: sus datos, sus atributos de
    variante, sus campos propios, sus componentes y su producto (con la ficha).
    Una versión nueva solo cuando algo cambió (la huella es de los datos); las
    líneas de OC y de factura guardan la suya y no cambian si el artículo cambia
    después (maestros/versiones.py)."""

    __tablename__ = "articulo_versiones"
    __table_args__ = (UniqueConstraint("articulo_id", "numero", name="uq_articulo_versiones_articulo_numero"),
                      CheckConstraint("numero >= 1", name="ck_articulo_versiones_numero"))
    id: Mapped[int] = mapped_column(primary_key=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    huella: Mapped[str] = mapped_column(String(64), index=True)
    datos: Mapped[dict] = mapped_column(JSON)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    articulo: Mapped[Articulo] = relationship()
