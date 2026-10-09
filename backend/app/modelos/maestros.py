"""Datos maestros: proveedores, estructura de la empresa (sociedades, centros,
almacenes, contactos), países, acuerdos, marcas, tallas, categorías, estados
de liberación y artículos.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.modelos.productos import Producto
    from app.modelos.transporte import Puerto


proveedor_marcas = Table(
    "proveedor_marcas", Base.metadata,
    Column("proveedor_id", ForeignKey("proveedores.id", ondelete="CASCADE"), primary_key=True),
    Column("marca_id", ForeignKey("marcas.id", ondelete="CASCADE"), primary_key=True),
)


proveedor_sociedades = Table(
    "proveedor_sociedades", Base.metadata,
    Column("proveedor_id", ForeignKey("proveedores.id", ondelete="CASCADE"), primary_key=True),
    Column("sociedad_id", ForeignKey("sociedades.id", ondelete="CASCADE"), primary_key=True),
)


centro_puertos = Table(
    "centro_puertos", Base.metadata,
    Column("centro_id", ForeignKey("centros.id", ondelete="CASCADE"), primary_key=True),
    Column("puerto_id", ForeignKey("puertos.id", ondelete="CASCADE"), primary_key=True),
)


class Proveedor(Base):
    """Proveedor (exportador). Maneja sus propias marcas y artículos y solo
    trabaja con las sociedades que tiene asignadas."""

    __tablename__ = "proveedores"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    id_fiscal: Mapped[str | None] = mapped_column(String(40))
    pais: Mapped[str | None] = mapped_column(String(2))
    direccion: Mapped[str | None] = mapped_column(String(300))
    contacto: Mapped[str | None] = mapped_column(String(120))
    correos: Mapped[str | None] = mapped_column(String(500))
    telefono: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    marcas: Mapped[list["Marca"]] = relationship(secondary=proveedor_marcas, order_by="Marca.codigo")
    sociedades: Mapped[list["Sociedad"]] = relationship(secondary=proveedor_sociedades, order_by="Sociedad.codigo")


class Sociedad(Base):
    """Sociedad legal (compañía de SAP). Sus centros son bodegas fiscales."""

    __tablename__ = "sociedades"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    id_fiscal: Mapped[str | None] = mapped_column(String(30))  # NIT / RUC
    pais: Mapped[str | None] = mapped_column(String(2))
    moneda: Mapped[str] = mapped_column(String(3), default="USD")
    direccion: Mapped[str | None] = mapped_column(String(300))
    correos: Mapped[str | None] = mapped_column(String(500))  # separados por coma
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    centros: Mapped[list["Centro"]] = relationship(back_populates="sociedad", order_by="Centro.codigo")


class Centro(Base):
    """Centro de SAP asignado a una sociedad. Es la bodega fiscal a la que
    llega la mercancía (notify party) y, como centro de destino de la OC,
    indica el país final. Su puerto es el de llegada de los embarques."""

    __tablename__ = "centros"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    sociedad_id: Mapped[int] = mapped_column(ForeignKey("sociedades.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(20), default="BODEGA_FISCAL")
    pais: Mapped[str | None] = mapped_column(String(2))
    puerto: Mapped[str | None] = mapped_column(String(10))  # puerto de llegada
    direccion: Mapped[str | None] = mapped_column(String(300))
    correos: Mapped[str | None] = mapped_column(String(500))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    sociedad: Mapped[Sociedad] = relationship(back_populates="centros")
    # Puertos por donde puede llegar (el principal es "puerto"); los del
    # embarque se sugieren de aquí y se pueden cambiar entre ellos
    puertos: Mapped[list["Puerto"]] = relationship(secondary=centro_puertos, order_by="Puerto.codigo")


class Contacto(Base):
    """Persona de contacto de una sociedad (facturación) o de un centro
    (notify party, recepción)."""

    __tablename__ = "contactos"
    id: Mapped[int] = mapped_column(primary_key=True)
    sociedad_id: Mapped[int | None] = mapped_column(ForeignKey("sociedades.id"), index=True)
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centros.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    cargo: Mapped[str | None] = mapped_column(String(120))
    rol: Mapped[str] = mapped_column(String(15), default="NOTIFY")  # FACTURACION | NOTIFY | LOGISTICA
    correos: Mapped[str | None] = mapped_column(String(500))
    telefono: Mapped[str | None] = mapped_column(String(40))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Almacen(Base):
    """Separación lógica del inventario en el sistema (virtual, detalle,
    mayoreo…); no es un lugar físico. Cada posición de la OC elige el suyo."""

    __tablename__ = "almacenes"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
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


class AcuerdoComercial(Base):
    """Tratado o acuerdo comercial vigente: mercancías originarias de sus países
    de origen entran con preferencia arancelaria a sus países destino si se
    presenta la prueba de origen que pide."""

    __tablename__ = "acuerdos_comerciales"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    origenes: Mapped[str] = mapped_column(String(400))  # ISO separados por coma (US,DO)
    destinos: Mapped[str] = mapped_column(String(100))  # ISO de los países destino (GT,SV,HN…)
    prueba: Mapped[str | None] = mapped_column(String(200))  # certificado o declaración de origen
    nota: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Marca(Base):
    __tablename__ = "marcas"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class EscalaTalla(Base):
    """Escala de tallas reutilizable (calzado, ropa, accesorios u otra): sus
    tallas en orden y cómo se forma el código de cada talla. Los genéricos
    parten de una escala; el código se genera con la regla o se escribe."""

    __tablename__ = "escalas_talla"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[str | None] = mapped_column(String(20))
    # MULTIPLICAR: talla numérica × factor (7.5 × 10 → 075); CONSECUTIVO: 001, 002…;
    # TALLA: la misma talla (S, M, XL). Un código escrito en la lista manda.
    regla: Mapped[str] = mapped_column(String(15), default="CONSECUTIVO")
    factor: Mapped[int | None] = mapped_column(Integer, default=10)
    longitud: Mapped[int | None] = mapped_column(Integer, default=3)
    tallas: Mapped[str] = mapped_column(Text)  # "6, 6.5, 7=070, 8-10" o "S, M, L"
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CategoriaArticulo(Base):
    """Categoría de artículo (calzado, ropa, accesorios…): lista que define
    cada empresa en Datos maestros; la usan los grupos de artículos y las
    escalas de tallas."""

    __tablename__ = "categorias_articulo"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ValorLista(Base):
    """Valor de una lista configurable (unidad de medida, moneda, incoterm, modo
    de transporte…). Las listas y sus atributos están en core/listas.py; cada
    lista usa solo algunas de las columnas de atributos."""

    __tablename__ = "valores_lista"
    __table_args__ = (UniqueConstraint("lista", "codigo", name="uq_valores_lista_lista_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    lista: Mapped[str] = mapped_column(String(30), index=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Atributos (según la lista)
    nombre_plural: Mapped[str | None] = mapped_column(String(120))
    alias: Mapped[str | None] = mapped_column(String(300))
    contable: Mapped[bool | None] = mapped_column(Boolean)
    simbolo: Mapped[str | None] = mapped_column(String(5))
    decimales: Mapped[int | None] = mapped_column(Integer)
    letras_en: Mapped[str | None] = mapped_column(String(120))
    letras_es: Mapped[str | None] = mapped_column(String(120))
    calculo: Mapped[str | None] = mapped_column(String(20))
    factor: Mapped[float | None] = mapped_column(Float)
    icono: Mapped[str | None] = mapped_column(String(20))
    documento: Mapped[str | None] = mapped_column(String(40))
    etiqueta_puerto: Mapped[str | None] = mapped_column(String(40))
    etiqueta_transportista: Mapped[str | None] = mapped_column(String(40))
    etiqueta_unidad: Mapped[str | None] = mapped_column(String(80))
    padre: Mapped[str | None] = mapped_column(String(20))
    consolidado: Mapped[bool | None] = mapped_column(Boolean)
    estados: Mapped[str | None] = mapped_column(String(120))  # varias opciones, separadas por coma


class EstadoLiberacion(Base):
    """Estado de liberación de una OC tal como lo manda el ERP de la empresa.

    Hay dos liberaciones (comercial y logística) y cada empresa define sus
    códigos (p. ej. SAP: comercial C/P, logística 300/301/304), su nombre,
    si permite facturar, cuál es el de «liberada con cambios» y cuál se usa
    cuando el archivo no trae el dato. `alias` son otras palabras que el
    importador acepta (separadas por coma)."""

    __tablename__ = "estados_liberacion"
    __table_args__ = (UniqueConstraint("tipo", "codigo", name="uq_estados_liberacion_tipo_codigo"),)
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


class GrupoArticulo(Base):
    """Grupo de artículos con su categoría (Datos maestros → Categorías)."""

    __tablename__ = "grupos_articulos"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(15), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    categoria: Mapped[str] = mapped_column(String(10))  # código de categorias_articulo
    # Días que este tipo de producto necesita además de los de su región después
    # del puerto (inspección, etiquetado, permisos); se suman a la fecha en tienda
    dias_extra: Mapped[int | None] = mapped_column(Integer)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Prepack(Base):
    """Curva de un estilo-color. Su prepack ID (p. ej. AB12) es la "talla"
    del artículo prepack y se arma con sólidos del mismo estilo y color."""

    __tablename__ = "prepacks"
    __table_args__ = (UniqueConstraint("estilo", "color", "codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10))
    estilo: Mapped[str] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    descripcion: Mapped[str | None] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    componentes: Mapped[list["PrepackComponente"]] = relationship(
        back_populates="prepack", cascade="all, delete-orphan", order_by="PrepackComponente.id"
    )

    @property
    def total(self) -> int:
        return sum(c.cantidad for c in self.componentes)


class Articulo(Base):
    """Dato maestro del artículo (SKU). Un sólido es un estilo-color-talla;
    un prepack es una caja con una curva de sólidos."""

    __tablename__ = "articulos"
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    # Código de artículo de la empresa (numérico o alfanumérico, el formato lo
    # define cada empresa); distinto del SKU del proveedor
    sku: Mapped[str] = mapped_column(String(40), unique=True)  # texto: conserva ceros
    # Genérico: agrupa las tallas y prepacks de un estilo-color, que comparten ficha
    generico: Mapped[str | None] = mapped_column(String(40), index=True)
    sku_proveedor: Mapped[str | None] = mapped_column(String(60), index=True)
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    marca_id: Mapped[int] = mapped_column(ForeignKey("marcas.id"), index=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos_articulos.id"), index=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    unidad: Mapped[str] = mapped_column(String(5))  # PAR | UN | CJ (prepack)
    # Peso neto de una unidad (par, pieza o, en un prepack, la curva completa), en kg.
    # El peso del empaque no va aquí: es la tara de cada nivel de empaque.
    peso_unitario: Mapped[float | None] = mapped_column(Float)
    tipo: Mapped[str] = mapped_column(String(10), default="SOLIDO")  # SOLIDO | PREPACK
    prepack_id: Mapped[int | None] = mapped_column(ForeignKey("prepacks.id"))
    # La ficha técnica y la clasificación son del estilo-color (producto)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    marca: Mapped[Marca] = relationship()
    grupo: Mapped[GrupoArticulo] = relationship()
    prepack: Mapped[Prepack | None] = relationship()
    producto: Mapped[Producto | None] = relationship(back_populates="articulos")


class PrepackComponente(Base):
    __tablename__ = "prepack_componentes"
    __table_args__ = (UniqueConstraint("prepack_id", "articulo_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    prepack_id: Mapped[int] = mapped_column(ForeignKey("prepacks.id"), index=True)
    articulo_id: Mapped[int] = mapped_column(ForeignKey("articulos.id"))
    cantidad: Mapped[int] = mapped_column(Integer)

    prepack: Mapped[Prepack] = relationship(back_populates="componentes")
    articulo: Mapped[Articulo] = relationship()
