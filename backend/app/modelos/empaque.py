"""Listas de empaque: líneas, grupos de cajas, tipos de empaque, plantillas y
recepción.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import Cantidad, ahora, cant

if TYPE_CHECKING:
    from app.modelos.facturacion import Factura, FacturaLinea
    from app.modelos.transporte import UnidadCarga


# Qué tipos de empaque puede llevar dentro cada tipo (relación configurable)

tipo_empaque_contiene = Table(
    "tipo_empaque_contiene", Base.metadata,
    Column("padre_id", ForeignKey("tipos_empaque.id", ondelete="CASCADE"), primary_key=True),
    Column("hijo_id", ForeignKey("tipos_empaque.id", ondelete="CASCADE"), primary_key=True, index=True),
)


class PackingList(DeOrganizacion, Base):
    __tablename__ = "packing_lists"
    __table_args__ = (UniqueConstraint("factura_id", "numero", name="uq_packing_lists_factura_numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    numero: Mapped[str] = mapped_column(String(40))  # PL-001 por defecto; el proveedor puede poner el suyo
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    unidad_carga_id: Mapped[int | None] = mapped_column(ForeignKey("unidades_carga.id"), index=True)
    asignacion: Mapped[str | None] = mapped_column(String(12))  # TENTATIVA | CONFIRMADA
    observaciones: Mapped[str | None] = mapped_column(Text)
    recolectado_en: Mapped[date | None] = mapped_column(Date)  # retiro en bodega del proveedor
    finalizado_en: Mapped[datetime | None] = mapped_column(DateTime, index=True)  # la última vez que se finalizó
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    factura: Mapped[Factura] = relationship(back_populates="packing_lists")
    lineas: Mapped[list["PLLinea"]] = relationship(
        back_populates="pl", cascade="all, delete-orphan", order_by="PLLinea.id"
    )
    grupos: Mapped[list["GrupoCajas"]] = relationship(
        back_populates="pl", cascade="all, delete-orphan", order_by="GrupoCajas.id"
    )
    unidad: Mapped["UnidadCarga | None"] = relationship(back_populates="packing_lists")


class PLLinea(DeOrganizacion, Base):
    """Parte de una línea de factura dentro de un PL. Puede haber varias
    partes de la misma línea (resultado de dividir)."""

    __tablename__ = "pl_lineas"
    # Cada línea de factura una sola vez por PL: lo que se agrega se suma a su fila
    __table_args__ = (UniqueConstraint("pl_id", "factura_linea_id", name="uq_pl_lineas_pl_factura_linea"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    factura_linea_id: Mapped[int] = mapped_column(ForeignKey("factura_lineas.id"), index=True)
    cantidad: Mapped[float] = mapped_column(Cantidad)

    pl: Mapped[PackingList] = relationship(back_populates="lineas")
    factura_linea: Mapped[FacturaLinea] = relationship()
    items: Mapped[list["GrupoCajasItem"]] = relationship(back_populates="pl_linea")
    recepcion: Mapped["RecepcionLinea | None"] = relationship(
        back_populates="pl_linea", cascade="all, delete-orphan", uselist=False
    )

    @validates("cantidad")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class GrupoCajas(DeOrganizacion, Base):
    """Nodo del árbol físico de empaque: N unidades iguales de un tipo de
    empaque (caja, inner pack, pallet…). `num_cajas` es el total de esas
    unidades en el PL; si tiene padre, se reparten por igual entre las
    unidades del padre (40 inner en 10 cajas = 4 por caja). Lleva producto
    (items, por unidad) y/o empaques hijos.

    Pesos por unidad, calculados de abajo hacia arriba: neto = artículos
    (peso de cada artículo × cantidad) + neto de los hijos; bruto = neto +
    tara propia + tara de los hijos. Si falta el peso de un artículo, el neto
    se escribe a mano (neto_manual). El volumen es el de las medidas
    exteriores: lo que va dentro de otro empaque no suma volumen."""

    __tablename__ = "grupos_cajas"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    num_cajas: Mapped[int] = mapped_column(Integer)
    largo: Mapped[float | None] = mapped_column(Float)  # cm
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    peso_neto_caja: Mapped[float | None] = mapped_column(Float)  # kg
    peso_bruto_caja: Mapped[float | None] = mapped_column(Float)
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantillas_caja.id"), index=True)
    plantilla_nombre: Mapped[str | None] = mapped_column(String(100))
    es_parcial: Mapped[bool] = mapped_column(Boolean, default=False)
    peso_estimado: Mapped[bool] = mapped_column(Boolean, default=False)
    observacion: Mapped[str | None] = mapped_column(String(300))
    tipo_empaque_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_empaque.id"), index=True)
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_cajas.id", ondelete="SET NULL"), index=True)
    tara: Mapped[float | None] = mapped_column(Float)  # kg de una unidad de este empaque vacía
    neto_manual: Mapped[float | None] = mapped_column(Float)  # neto por unidad si falta el peso de algún artículo

    pl: Mapped[PackingList] = relationship(back_populates="grupos")
    tipo_empaque: Mapped["TipoEmpaque | None"] = relationship()
    padre: Mapped["GrupoCajas | None"] = relationship(remote_side=lambda: GrupoCajas.id, back_populates="hijos")
    hijos: Mapped[list["GrupoCajas"]] = relationship(back_populates="padre", order_by="GrupoCajas.id")
    items: Mapped[list["GrupoCajasItem"]] = relationship(
        back_populates="grupo", cascade="all, delete-orphan", order_by="GrupoCajasItem.id"
    )


class GrupoCajasItem(DeOrganizacion, Base):
    __tablename__ = "grupo_cajas_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos_cajas.id"), index=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), index=True)
    cantidad_por_caja: Mapped[float] = mapped_column(Cantidad)

    grupo: Mapped[GrupoCajas] = relationship(back_populates="items")
    pl_linea: Mapped[PLLinea] = relationship(back_populates="items")

    @validates("cantidad_por_caja")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class TipoEmpaque(DeOrganizacion, Base):
    """Unidad logística configurable (inner pack, caja, pallet, bolsa, tambor…).
    Nada está fijo en el código: cada empresa define sus tipos, qué puede
    contener cada uno, su tara, medidas y límites. Un PL se arma como un árbol
    de empaques dentro de empaques con el producto en las hojas."""

    __tablename__ = "tipos_empaque"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_tipos_empaque_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(100))
    nivel: Mapped[int] = mapped_column(Integer, default=1)  # 1 = el más interno
    prefijo: Mapped[str | None] = mapped_column(String(6))  # etiqueta de cada unidad: C1, PK1, P1
    # BULTO: cuenta como bulto del documento; INTERIOR: va dentro de un bulto;
    # SOPORTE: lleva bultos (pallet, rack)
    cuenta_como: Mapped[str] = mapped_column(String(10), default="BULTO")
    uom: Mapped[str | None] = mapped_column(String(10))
    largo: Mapped[float | None] = mapped_column(Float)  # cm, exteriores
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    tara: Mapped[float | None] = mapped_column(Float)  # kg del empaque vacío
    peso_max: Mapped[float | None] = mapped_column(Float)  # kg brutos por unidad
    max_unidades: Mapped[int | None] = mapped_column(Integer)  # unidades de producto por unidad
    max_contenido: Mapped[int | None] = mapped_column(Integer)  # empaques internos por unidad
    contiene_productos: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_productos: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_tallas: Mapped[bool] = mapped_column(Boolean, default=True)
    mezcla_oc: Mapped[bool] = mapped_column(Boolean, default=True)
    identificador: Mapped[str | None] = mapped_column(String(15))  # SERIAL | CODIGO_BARRAS | SSCC
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    contiene: Mapped[list["TipoEmpaque"]] = relationship(
        secondary=tipo_empaque_contiene, primaryjoin=lambda: TipoEmpaque.id == tipo_empaque_contiene.c.padre_id,
        secondaryjoin=lambda: TipoEmpaque.id == tipo_empaque_contiene.c.hijo_id, order_by="TipoEmpaque.nivel")


class RecetaEmpaque(DeOrganizacion, Base):
    """Receta de empaque: cómo se empaca un artículo, en N niveles armados con
    los tipos del catálogo (inner pack ⊂ master ⊂ pallet…). Cada nivel dice
    cuántas unidades del nivel de abajo lleva; el primero, cuántas unidades
    del artículo (pares, piezas o, en un prepack, curvas: la curva es el
    artículo, no el empaque). Es un dato maestro que se reutiliza: las reglas
    de empaque y las posiciones de OC apuntan a ella."""

    __tablename__ = "recetas_empaque"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_recetas_empaque_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    # Creada sola a partir del casepack y el inner pack de las OC (se puede renombrar)
    automatica: Mapped[bool] = mapped_column(Boolean, default=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    niveles: Mapped[list["RecetaNivel"]] = relationship(
        back_populates="receta", cascade="all, delete-orphan", order_by="RecetaNivel.orden")


class RecetaNivel(DeOrganizacion, Base):
    """Un nivel de una receta: tipo de empaque y cuántas unidades del nivel de
    abajo lleva. Las medidas y la tara, si no se escriben, son las del tipo."""

    __tablename__ = "receta_niveles"
    __table_args__ = (UniqueConstraint("receta_id", "orden", name="uq_receta_niveles_receta_orden"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    receta_id: Mapped[int] = mapped_column(ForeignKey("recetas_empaque.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer)  # 1 = el más interno
    tipo_empaque_id: Mapped[int] = mapped_column(ForeignKey("tipos_empaque.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)  # del nivel de abajo (en el 1, del artículo)
    largo: Mapped[float | None] = mapped_column(Float)  # cm
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    tara: Mapped[float | None] = mapped_column(Float)  # kg
    opcional: Mapped[bool] = mapped_column(Boolean, default=False)  # p. ej. el pallet

    receta: Mapped[RecetaEmpaque] = relationship(back_populates="niveles")
    tipo_empaque: Mapped[TipoEmpaque] = relationship()


DESTINOS_REGLA_EMPAQUE = ("EMPRESA", "GRUPO", "PRODUCTO", "ARTICULO")
ORIGENES_RECETA = ("MANUAL", "REGLA", "DATOS")  # elegida a mano, por una regla o desde el casepack de la OC


class ReglaEmpaque(DeOrganizacion, Base):
    """«Para [destino] si [condiciones] → usar [receta]». Gana la más específica
    (artículo, producto, grupo de producto más profundo, toda la empresa); con
    condiciones gana sobre sin condiciones; si aun así empatan, la de menor
    `orden` (arriba en la lista). Se dan de baja, no se borran."""

    __tablename__ = "reglas_empaque"
    __table_args__ = (
        CheckConstraint(
            "(destino = 'EMPRESA' AND grupo_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL)"
            " OR (destino = 'GRUPO' AND grupo_id IS NOT NULL AND producto_id IS NULL AND articulo_id IS NULL)"
            " OR (destino = 'PRODUCTO' AND producto_id IS NOT NULL AND grupo_id IS NULL AND articulo_id IS NULL)"
            " OR (destino = 'ARTICULO' AND articulo_id IS NOT NULL AND grupo_id IS NULL AND producto_id IS NULL)",
            name="ck_reglas_empaque_destino_unico"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    receta_id: Mapped[int] = mapped_column(ForeignKey("recetas_empaque.id"), index=True)
    destino: Mapped[str] = mapped_column(String(10), default="EMPRESA")
    # Destino GRUPO: una familia o categoría del árbol de grupos de producto (y lo que cuelga de ella)
    grupo_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_producto.id"), index=True)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), index=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    # [{"campo": "oc.proveedor", "op": "igual", "valor": "VANS"}]: todas deben cumplirse
    condiciones: Mapped[list] = mapped_column(JSON, default=list)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    motivo: Mapped[str | None] = mapped_column(String(300))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizada_en: Mapped[datetime | None] = mapped_column(DateTime)
    eliminada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    eliminada_en: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    # El destino se lee por el servicio del catálogo (nombre, ruta): aquí solo sus ids
    receta: Mapped[RecetaEmpaque] = relationship()


class PlantillaCaja(DeOrganizacion, Base):
    __tablename__ = "plantillas_caja"
    __table_args__ = (UniqueConstraint("proveedor_id", "nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    cantidad_por_caja: Mapped[float] = mapped_column(Cantidad)
    unidad: Mapped[str] = mapped_column(String(5))
    largo: Mapped[float | None] = mapped_column(Float)
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    # Solo la tara del empaque: el peso neto sale del peso de cada artículo
    tara: Mapped[float | None] = mapped_column(Float)
    tipo_empaque_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_empaque.id"), index=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    tipo_empaque: Mapped["TipoEmpaque | None"] = relationship()

    @validates("cantidad_por_caja")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class RecepcionLinea(DeOrganizacion, Base):
    """Lo recibido de una línea del PL: la suma de sus movimientos de
    recepción (conteos parciales, ajustes, confirmación sin conteo). La fecha
    es la operativa del último movimiento; lo dañado es parte de lo recibido."""

    __tablename__ = "recepciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), unique=True)
    cantidad_recibida: Mapped[float] = mapped_column(Cantidad)
    cantidad_danada: Mapped[float] = mapped_column(Cantidad, default=0)
    observacion: Mapped[str | None] = mapped_column(String(300))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, index=True, default=ahora)

    pl_linea: Mapped[PLLinea] = relationship(back_populates="recepcion")

    @validates("cantidad_recibida", "cantidad_danada")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class RecepcionRegistro(DeOrganizacion, Base):
    """Una recepción en bodega de una unidad de carga (contenedor, guía,
    camión): en qué bodega o bodega fiscal, en qué fecha (la del hecho, no la
    de captura), quién y qué tipo de registro es. Una unidad se puede recibir
    en varias partes (conteos parciales); una corrección es un ajuste con
    motivo. Sus líneas son los movimientos."""

    __tablename__ = "recepcion_registros"
    id: Mapped[int] = mapped_column(primary_key=True)
    unidad_carga_id: Mapped[int] = mapped_column(ForeignKey("unidades_carga.id"), index=True)
    centro: Mapped[str] = mapped_column(String(10), index=True)  # bodega o bodega fiscal que recibe
    fecha: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(12))  # CONTEO | AJUSTE | SIN_CONTEO
    observacion: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    unidad: Mapped["UnidadCarga"] = relationship()
    movimientos: Mapped[list["RecepcionMovimiento"]] = relationship(
        back_populates="registro", cascade="all, delete-orphan", order_by="RecepcionMovimiento.id"
    )


class RecepcionMovimiento(DeOrganizacion, Base):
    """Cantidad recibida y dañada de una línea del PL en un registro. En un
    ajuste puede ser negativa (corrige un conteo anterior)."""

    __tablename__ = "recepcion_movimientos"
    id: Mapped[int] = mapped_column(primary_key=True)
    registro_id: Mapped[int] = mapped_column(ForeignKey("recepcion_registros.id", ondelete="CASCADE"), index=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), index=True)
    cantidad: Mapped[float] = mapped_column(Cantidad, default=0)
    danada: Mapped[float] = mapped_column(Cantidad, default=0)
    observacion: Mapped[str | None] = mapped_column(String(300))

    registro: Mapped[RecepcionRegistro] = relationship(back_populates="movimientos")
    pl_linea: Mapped[PLLinea] = relationship()

    @validates("cantidad", "danada")
    def _cantidad(self, _k, v):
        return cant(v)
