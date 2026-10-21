"""Datos maestros: proveedores, estructura de la empresa (sociedades, centros,
almacenes, contactos), países, acuerdos, marcas, tallas, categorías, estados
de liberación y artículos.
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
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, object_session, relationship, synonym
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
    """Sociedad legal (compañía de SAP). Sus centros son bodegas fiscales."""

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
    """Centro de SAP asignado a una sociedad. Es la bodega fiscal a la que
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


class EscalaTalla(DeOrganizacion, Base):
    """Escala de valores reutilizable de un atributo de variante (tallas de
    calzado o ropa, presentaciones 250 ml / 500 ml / 1 L, concentraciones…):
    sus valores en orden y cómo se forma el código de cada uno. Al crear las
    variantes de un producto se parte de una escala; el código se genera con
    la regla o se escribe."""

    __tablename__ = "escalas_talla"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_escalas_talla_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[str | None] = mapped_column(String(20))
    atributo: Mapped[str] = mapped_column(String(20), default="TALLA", server_default="TALLA")  # su atributo de variante
    # MULTIPLICAR: talla numérica × factor (7.5 × 10 → 075); CONSECUTIVO: 001, 002…;
    # TALLA: la misma talla (S, M, XL). Un código escrito en la lista manda.
    regla: Mapped[str] = mapped_column(String(15), default="CONSECUTIVO")
    factor: Mapped[int | None] = mapped_column(Integer, default=10)
    longitud: Mapped[int | None] = mapped_column(Integer, default=3)
    # Tallas en orden, cada una con su código escrito (o null): [{"talla": "7", "codigo": "070"}]
    lista_tallas: Mapped[list] = mapped_column("tallas", JSON, default=list)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def tallas(self) -> str:
        """Las tallas como se escriben en el formulario ("6, 6.5, 7=070")."""
        return ", ".join(f"{x['talla']}={x['codigo']}" if x.get("codigo") else x["talla"] for x in self.lista_tallas or [])

    @tallas.setter
    def tallas(self, texto: str) -> None:
        from app.modulos.maestros.tallas import tallas_de

        self.lista_tallas = [{"talla": t, "codigo": c} for t, c in tallas_de(texto)]


class CategoriaArticulo(DeOrganizacion, Base):
    """Categoría de artículo (calzado, ropa, accesorios…): lista que define
    cada empresa en Datos maestros; la usan los grupos de artículos y las
    escalas de tallas."""

    __tablename__ = "categorias_articulo"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_categorias_articulo_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10))
    nombre: Mapped[str] = mapped_column(String(100))
    # Dominio de clasificación de la línea (calzado, ropa…): la ficha técnica
    # ofrece primero sus categorías de producto (taxonomía única: línea
    # comercial → dominio → categoría de producto)
    dominio: Mapped[str | None] = mapped_column(
        ForeignKey("dominios_clasificacion.codigo", name="fk_categorias_articulo_dominio", onupdate="CASCADE"), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


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
    códigos (p. ej. SAP: comercial C/P, logística 300/301/304), su nombre,
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


class GrupoArticulo(DeOrganizacion, Base):
    """Grupo de artículos con su categoría (Datos maestros → Categorías)."""

    __tablename__ = "grupos_articulos"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_grupos_articulos_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(15))
    nombre: Mapped[str] = mapped_column(String(100))
    categoria: Mapped[str] = mapped_column(String(10))  # código de categorias_articulo
    # Días que este tipo de producto necesita además de los de su región después
    # del puerto (inspección, etiquetado, permisos); se suman a la fecha en tienda
    dias_extra: Mapped[int | None] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Familia (grupo de producto) de todos los artículos del grupo (salvo los que tienen la suya propia)
    grupo_producto_id: Mapped[int | None] = mapped_column(
        ForeignKey("grupos_producto.id", name="fk_grupos_articulos_grupo_producto_id"), index=True)
    # Congelada desde la migración 0081 (apunta a la tabla anterior), solo para volver atrás
    familia_etiquetado_anterior_id: Mapped[int | None] = mapped_column(
        "familia_etiquetado_id", ForeignKey("familias_etiquetado.id", name="fk_grupos_articulos_familia_etiquetado_id"), index=True)

    grupo_producto: Mapped["GrupoProducto | None"] = relationship()  # noqa: F821
    # Nombres con los que el etiquetado los conoce
    familia_etiquetado_id = synonym("grupo_producto_id")
    familia_etiquetado = synonym("grupo_producto")


class Prepack(DeOrganizacion, Base):
    """Artículo compuesto. Una CURVA (prepack) reparte tallas de un mismo
    estilo-color y su prepack ID (p. ej. AB12) es la "talla" del artículo; un
    KIT junta artículos de cualquier estilo (un juego, un set de regalo)."""

    __tablename__ = "prepacks"
    __table_args__ = (UniqueConstraint("organizacion_id", "estilo", "color", "codigo", name="uq_prepacks_org_estilo_color_codigo"),
                      CheckConstraint("tipo IN ('CURVA', 'KIT')", name="ck_prepacks_tipo"))
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10), default="CURVA", server_default="CURVA")
    codigo: Mapped[str] = mapped_column(String(10))
    estilo: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    descripcion: Mapped[str | None] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    componentes: Mapped[list["PrepackComponente"]] = relationship(
        back_populates="prepack", cascade="all, delete-orphan", order_by="PrepackComponente.id"
    )

    @property
    def total(self) -> int:
        return sum(c.cantidad for c in self.componentes)


class Articulo(DeOrganizacion, Base):
    """Dato maestro del artículo (SKU): una variante de un producto de cualquier
    tipo, distinguida por sus valores de variante (talla, color, sabor,
    presentación…), o un compuesto que junta otras (un pack o un kit)."""

    __tablename__ = "articulos"
    __table_args__ = (UniqueConstraint("organizacion_id", "sku", name="uq_articulos_org_sku"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    # Código de artículo de la empresa (numérico o alfanumérico, el formato lo
    # define cada empresa); distinto del SKU del proveedor
    sku: Mapped[str] = mapped_column(String(40))  # texto: conserva ceros
    # Genérico: agrupa las tallas y prepacks de un estilo-color, que comparten ficha
    generico: Mapped[str | None] = mapped_column(String(40), index=True)
    sku_proveedor: Mapped[str | None] = mapped_column(String(60), index=True)
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str | None] = mapped_column(String(40))  # opcional: modelo o estilo, si la empresa lo usa
    color: Mapped[str | None] = mapped_column(String(60))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    marca_id: Mapped[int] = mapped_column(ForeignKey("marcas.id"), index=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos_articulos.id"), index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)
    unidad: Mapped[str] = mapped_column(String(5))  # PAR | UN | CJ (prepack)
    # Peso neto de una unidad (par, pieza o, en un prepack, la curva completa), en kg.
    # El peso del empaque no va aquí: es la tara de cada nivel de empaque.
    peso_unitario: Mapped[float | None] = mapped_column(Float)
    tipo: Mapped[str] = mapped_column(String(10), default="SOLIDO")  # SOLIDO | PREPACK
    prepack_id: Mapped[int | None] = mapped_column(ForeignKey("prepacks.id"), index=True)
    # La ficha técnica y la clasificación son del estilo-color (producto)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), index=True)
    # Familia propia (grupo de producto, modelos/grupos.py): qué etiquetas y qué empaque le
    # corresponden; no es su clasificación arancelaria
    grupo_producto_id: Mapped[int | None] = mapped_column(
        ForeignKey("grupos_producto.id", name="fk_articulos_grupo_producto_id"), index=True)
    # Congelada desde la migración 0081 (apunta a la tabla anterior), solo para volver atrás
    familia_etiquetado_anterior_id: Mapped[int | None] = mapped_column(
        "familia_etiquetado_id", ForeignKey("familias_etiquetado.id", name="fk_articulos_familia_etiquetado_id"), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    marca: Mapped[Marca] = relationship()
    grupo: Mapped[GrupoArticulo] = relationship()
    prepack: Mapped[Prepack | None] = relationship()
    producto: Mapped[Producto | None] = relationship(back_populates="articulos")
    grupo_producto: Mapped["GrupoProducto | None"] = relationship()  # noqa: F821
    # Nombres con los que el etiquetado los conoce
    familia_etiquetado_id = synonym("grupo_producto_id")
    familia_etiquetado = synonym("grupo_producto")

    @property
    def familia_efectiva(self):
        """La familia del artículo (grupo de producto de clase FAMILIA): la suya
        propia, si no la de su producto (estilo-color) y si no la de su grupo."""
        if self.grupo_producto is not None:
            return self.grupo_producto
        p = self.producto
        if p is not None and p.grupo_producto is not None:
            return p.grupo_producto.familia
        return self.grupo.grupo_producto if self.grupo else None

    @property
    def familia_origen(self) -> str | None:
        """De dónde sale la familia: ARTICULO (propia), PRODUCTO o GRUPO (heredada); None si no tiene."""
        if self.familia_etiquetado_id:
            return "ARTICULO"
        if self.producto is not None and self.producto.familia_etiquetado_id:
            return "PRODUCTO"
        return "GRUPO" if self.grupo and self.grupo.familia_etiquetado_id else None
    # Valores de los atributos de variante propios de la empresa (material,
    # voltaje, sabor…); talla y color son columnas
    atributos: Mapped[list["ArticuloAtributo"]] = relationship(
        back_populates="articulo", cascade="all, delete-orphan", lazy="selectin", order_by="ArticuloAtributo.id")

    @property
    def variantes(self) -> dict:
        """{código del atributo: valor} de los atributos propios."""
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


class AtributoVariante(DeOrganizacion, Base):
    """Dimensión que distingue las variantes de un producto (talla, color,
    sabor, presentación, concentración, voltaje…). Talla y color vienen de
    fábrica (`columna`: el artículo guarda además una copia en su columna);
    la empresa agrega las suyas y les da nombre, tipo y orden. Cada familia de
    productos dice cuáles usa (grupos_producto.ejes_variante)."""

    __tablename__ = "atributos_variante"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_atributos_variante_org_codigo"),
                      CheckConstraint("columna IS NULL OR columna IN ('talla', 'color')", name="ck_atributos_variante_columna"),
                      CheckConstraint("tipo IN ('texto', 'numero', 'opcion')", name="ck_atributos_variante_tipo"))
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(60))
    columna: Mapped[str | None] = mapped_column(String(10))  # talla | color: atributo de sistema
    # Qué valor lleva: texto libre, un número (en su unidad: 220 V, 500 ml) o una de sus opciones
    tipo: Mapped[str] = mapped_column(String(10), default="texto", server_default="texto")
    opciones: Mapped[str | None] = mapped_column(String(500))  # separadas por coma (tipo opción)
    unidad: Mapped[str | None] = mapped_column(String(10))  # código de la unidad de medida (tipo número)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ArticuloAtributo(DeOrganizacion, Base):
    """Valor de un atributo de variante en un artículo (uno por atributo)."""

    __tablename__ = "articulo_atributos"
    __table_args__ = (UniqueConstraint("articulo_id", "atributo_id", name="uq_articulo_atributos_articulo_atributo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id", ondelete="CASCADE"), index=True)
    atributo_id: Mapped[int] = mapped_column(ForeignKey("atributos_variante.id"), index=True)
    valor: Mapped[str] = mapped_column(String(60))

    articulo: Mapped[Articulo] = relationship(back_populates="atributos")
    atributo: Mapped[AtributoVariante] = relationship(lazy="joined")


@event.listens_for(Session, "before_flush")
def _aplicar_variantes(db, _contexto, _instancias) -> None:
    """Los valores de variante viven en articulo_atributos, también talla y color
    (atributos de sistema). Las columnas talla y color del artículo son una copia
    para lo que todavía las lee: si cambian a mano, mandan y pasan a sus filas;
    si cambian los valores, se copian a las columnas. En un prepack la «talla» es
    su ID de prepack, no un valor de variante."""
    candidatos = [x for x in {*db.new, *db.dirty, *db.info.pop("variantes_pendientes", set())} if isinstance(x, Articulo)]
    if not candidatos:
        return
    por_codigo = None
    for a in candidatos:
        pendiente = a.__dict__.pop("_variantes_pendientes", None)
        estado = inspect(a)
        nuevo = a in db.new
        cambio_col = {col: nuevo or estado.attrs[col].history.has_changes() for col in COLUMNAS_SISTEMA}
        if pendiente is None and not any(cambio_col.values()):
            continue
        if por_codigo is None:
            with db.no_autoflush:
                por_codigo = {x.codigo: x for x in db.scalars(select(AtributoVariante))}
        sistema = {x.columna: x.codigo for x in por_codigo.values() if x.columna}
        actuales = {x.atributo.codigo: x for x in a.atributos}
        final = dict(pendiente) if pendiente is not None else {k: x.valor for k, x in actuales.items()}
        for col, codigo in sistema.items():
            if col == "talla" and a.tipo == "PREPACK":
                final.pop(codigo, None)
                continue
            if cambio_col[col] or codigo not in final:
                valor = getattr(a, col)
                if valor not in (None, ""):
                    final[codigo] = valor
                else:
                    final.pop(codigo, None)
        for codigo, x in list(actuales.items()):
            if codigo not in final:
                a.atributos.remove(x)
        for codigo, valor in final.items():
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
        for col, codigo in sistema.items():
            if col == "talla" and a.tipo == "PREPACK":
                continue
            valor = valor_variante(final[codigo]) if final.get(codigo) not in (None, "") else None
            if getattr(a, col) != valor:
                setattr(a, col, valor)


COLUMNAS_SISTEMA = ("talla", "color")


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


class PrepackComponente(DeOrganizacion, Base):
    __tablename__ = "prepack_componentes"
    __table_args__ = (UniqueConstraint("prepack_id", "articulo_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    prepack_id: Mapped[int] = mapped_column(ForeignKey("prepacks.id"), index=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)

    prepack: Mapped[Prepack] = relationship(back_populates="componentes")
    articulo: Mapped[Articulo] = relationship()
