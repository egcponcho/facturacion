"""Modelo de datos.

Todo se maneja por cantidades:
  Posición OC --(FacturaLinea.cantidad)--> Factura
  FacturaLinea --(PLLinea.cantidad)--> Packing list
  PLLinea --(GrupoCajasItem.cantidad_por_caja x GrupoCajas.num_cajas)--> Cajas
  Packing list --> Unidad de carga (contenedor, aéreo, LCL...) --> Embarque
"""
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------
# Usuarios y proveedores
# --------------------------------------------------------------------------
class Proveedor(Base):
    __tablename__ = "proveedores"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    nombre: Mapped[str] = mapped_column(String(200))
    rol: Mapped[str] = mapped_column(String(20))  # admin | interno | proveedor
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    password_hash: Mapped[str] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    proveedor: Mapped[Proveedor | None] = relationship()


# --------------------------------------------------------------------------
# Órdenes de compra
# --------------------------------------------------------------------------
class OrdenCompra(Base):
    __tablename__ = "ordenes_compra"
    __table_args__ = (UniqueConstraint("proveedor_id", "numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    numero: Mapped[str] = mapped_column(String(30))
    sociedad: Mapped[str] = mapped_column(String(10))
    centro: Mapped[str | None] = mapped_column(String(10))
    pais_destino: Mapped[str | None] = mapped_column(String(3))
    moneda: Mapped[str] = mapped_column(String(3))
    incoterm: Mapped[str | None] = mapped_column(String(10))
    fecha: Mapped[date | None] = mapped_column(Date)
    liberada: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    proveedor: Mapped[Proveedor] = relationship()
    posiciones: Mapped[list["PosicionOC"]] = relationship(
        back_populates="oc", order_by="PosicionOC.id", cascade="all, delete-orphan"
    )


class PosicionOC(Base):
    __tablename__ = "posiciones_oc"
    __table_args__ = (UniqueConstraint("oc_id", "posicion"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    oc_id: Mapped[int] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    posicion: Mapped[str] = mapped_column(String(10))
    codigo_sap: Mapped[str] = mapped_column(String(40))  # texto: conserva ceros iniciales
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(40))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    cantidad: Mapped[int] = mapped_column(Integer)
    unidad: Mapped[str] = mapped_column(String(5))  # PAR | UN
    precio: Mapped[float] = mapped_column(Float)
    fecha_entrega: Mapped[date | None] = mapped_column(Date)
    pais_origen: Mapped[str | None] = mapped_column(String(3))
    partida_arancelaria: Mapped[str | None] = mapped_column(String(20))
    bloqueada: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_bloqueo: Mapped[str | None] = mapped_column(String(200))

    oc: Mapped[OrdenCompra] = relationship(back_populates="posiciones")


# --------------------------------------------------------------------------
# Facturas
# --------------------------------------------------------------------------
class Factura(Base):
    __tablename__ = "facturas"
    __table_args__ = (
        # Número único por proveedor (se ignora en facturas canceladas)
        Index(
            "ux_factura_numero",
            "proveedor_id",
            "numero",
            unique=True,
            sqlite_where=text("numero IS NOT NULL AND estado <> 'CANCELADA'"),
            postgresql_where=text("numero IS NOT NULL AND estado <> 'CANCELADA'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    numero: Mapped[str | None] = mapped_column(String(50))
    fecha: Mapped[date | None] = mapped_column(Date)
    moneda: Mapped[str] = mapped_column(String(3))
    incoterm: Mapped[str | None] = mapped_column(String(10))
    sociedad: Mapped[str] = mapped_column(String(10))
    centro: Mapped[str | None] = mapped_column(String(10))
    pais_destino: Mapped[str | None] = mapped_column(String(3))
    condiciones: Mapped[str | None] = mapped_column(String(200))
    observaciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    finalizado_en: Mapped[datetime | None] = mapped_column(DateTime)

    proveedor: Mapped[Proveedor] = relationship()
    lineas: Mapped[list["FacturaLinea"]] = relationship(
        back_populates="factura", cascade="all, delete-orphan", order_by="FacturaLinea.id"
    )
    packing_lists: Mapped[list["PackingList"]] = relationship(
        back_populates="factura", order_by="PackingList.id"
    )


class FacturaLinea(Base):
    __tablename__ = "factura_lineas"
    __table_args__ = (UniqueConstraint("factura_id", "posicion_oc_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    posicion_oc_id: Mapped[int] = mapped_column(ForeignKey("posiciones_oc.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)
    precio_unitario: Mapped[float] = mapped_column(Float)
    precio_oc: Mapped[float] = mapped_column(Float)
    motivo_precio: Mapped[str | None] = mapped_column(String(300))
    # Copia de los datos de la OC al momento de facturar (trazabilidad)
    oc_numero: Mapped[str] = mapped_column(String(30))
    posicion: Mapped[str] = mapped_column(String(10))
    codigo_sap: Mapped[str] = mapped_column(String(40))
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(40))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    unidad: Mapped[str] = mapped_column(String(5))
    # Datos de aduana (editables en la factura)
    pais_origen: Mapped[str | None] = mapped_column(String(3))
    partida_arancelaria: Mapped[str | None] = mapped_column(String(20))
    descripcion_comercial: Mapped[str | None] = mapped_column(String(300))

    factura: Mapped[Factura] = relationship(back_populates="lineas")
    posicion_oc: Mapped[PosicionOC] = relationship()


class Archivo(Base):
    __tablename__ = "archivos"
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(30))  # FACTURA_OFICIAL | OTRO
    nombre: Mapped[str] = mapped_column(String(300))
    ruta: Mapped[str] = mapped_column(String(500))
    tamano: Mapped[int] = mapped_column(Integer)
    subido_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    subido_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


# --------------------------------------------------------------------------
# Packing lists y cajas
# --------------------------------------------------------------------------
class PackingList(Base):
    __tablename__ = "packing_lists"
    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("facturas.id"), index=True)
    numero: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20), default="BORRADOR", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    unidad_carga_id: Mapped[int | None] = mapped_column(ForeignKey("unidades_carga.id"), index=True)
    asignacion: Mapped[str | None] = mapped_column(String(12))  # TENTATIVA | CONFIRMADA
    observaciones: Mapped[str | None] = mapped_column(Text)
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


class PLLinea(Base):
    """Parte de una línea de factura dentro de un PL. Puede haber varias
    partes de la misma línea (resultado de dividir)."""

    __tablename__ = "pl_lineas"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    factura_linea_id: Mapped[int] = mapped_column(ForeignKey("factura_lineas.id"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer)

    pl: Mapped[PackingList] = relationship(back_populates="lineas")
    factura_linea: Mapped[FacturaLinea] = relationship()
    items: Mapped[list["GrupoCajasItem"]] = relationship(back_populates="pl_linea")
    recepcion: Mapped["RecepcionLinea | None"] = relationship(
        back_populates="pl_linea", cascade="all, delete-orphan", uselist=False
    )


class GrupoCajas(Base):
    """N cajas iguales. Guarda sus propios valores: la plantilla solo sirvió
    para llenarlos rápido. Si tiene varios items es una caja mixta/surtida;
    el peso y volumen pertenecen al grupo y se cuentan una sola vez."""

    __tablename__ = "grupos_cajas"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_id: Mapped[int] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    num_cajas: Mapped[int] = mapped_column(Integer)
    largo: Mapped[float | None] = mapped_column(Float)  # cm
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    peso_neto_caja: Mapped[float | None] = mapped_column(Float)  # kg
    peso_bruto_caja: Mapped[float | None] = mapped_column(Float)
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantillas_caja.id"))
    plantilla_nombre: Mapped[str | None] = mapped_column(String(100))
    es_parcial: Mapped[bool] = mapped_column(Boolean, default=False)
    peso_estimado: Mapped[bool] = mapped_column(Boolean, default=False)
    observacion: Mapped[str | None] = mapped_column(String(300))

    pl: Mapped[PackingList] = relationship(back_populates="grupos")
    items: Mapped[list["GrupoCajasItem"]] = relationship(
        back_populates="grupo", cascade="all, delete-orphan", order_by="GrupoCajasItem.id"
    )


class GrupoCajasItem(Base):
    __tablename__ = "grupo_cajas_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos_cajas.id"), index=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), index=True)
    cantidad_por_caja: Mapped[int] = mapped_column(Integer)

    grupo: Mapped[GrupoCajas] = relationship(back_populates="items")
    pl_linea: Mapped[PLLinea] = relationship(back_populates="items")


class PlantillaCaja(Base):
    __tablename__ = "plantillas_caja"
    __table_args__ = (UniqueConstraint("proveedor_id", "nombre"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(100))
    cantidad_por_caja: Mapped[int] = mapped_column(Integer)
    unidad: Mapped[str] = mapped_column(String(5))
    largo: Mapped[float | None] = mapped_column(Float)
    ancho: Mapped[float | None] = mapped_column(Float)
    alto: Mapped[float | None] = mapped_column(Float)
    peso_neto: Mapped[float | None] = mapped_column(Float)
    peso_bruto: Mapped[float | None] = mapped_column(Float)
    tara: Mapped[float | None] = mapped_column(Float)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class RecepcionLinea(Base):
    __tablename__ = "recepciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    pl_linea_id: Mapped[int] = mapped_column(ForeignKey("pl_lineas.id"), unique=True)
    cantidad_recibida: Mapped[int] = mapped_column(Integer)
    cantidad_danada: Mapped[int] = mapped_column(Integer, default=0)
    observacion: Mapped[str | None] = mapped_column(String(300))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    pl_linea: Mapped[PLLinea] = relationship(back_populates="recepcion")


# --------------------------------------------------------------------------
# Transporte
# --------------------------------------------------------------------------
class Embarque(Base):
    """Existe desde la planificación (booking), antes de tener BL/AWB."""

    __tablename__ = "embarques"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    tipo_transporte: Mapped[str] = mapped_column(String(12))  # MARITIMO | AEREO | TERRESTRE
    modalidad: Mapped[str | None] = mapped_column(String(10))  # FCL | LCL
    documento_numero: Mapped[str | None] = mapped_column(String(50))  # BL / AWB / CP
    transportista: Mapped[str | None] = mapped_column(String(100))
    puerto_origen: Mapped[str | None] = mapped_column(String(100))
    puerto_destino: Mapped[str | None] = mapped_column(String(100))
    etd: Mapped[date | None] = mapped_column(Date)
    eta: Mapped[date | None] = mapped_column(Date)
    salida_real: Mapped[date | None] = mapped_column(Date)
    arribo_real: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), default="PLANIFICADO")
    observaciones: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    unidades: Mapped[list["UnidadCarga"]] = relationship(
        back_populates="embarque", order_by="UnidadCarga.id", cascade="all, delete-orphan"
    )
    eventos: Mapped[list["EventoEmbarque"]] = relationship(
        back_populates="embarque", order_by="EventoEmbarque.fecha", cascade="all, delete-orphan"
    )


class UnidadCarga(Base):
    __tablename__ = "unidades_carga"
    id: Mapped[int] = mapped_column(primary_key=True)
    embarque_id: Mapped[int] = mapped_column(ForeignKey("embarques.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))
    etiqueta: Mapped[str] = mapped_column(String(30))  # "40HC #1" mientras no hay número
    numero: Mapped[str | None] = mapped_column(String(20))
    sello: Mapped[str | None] = mapped_column(String(30))
    capacidad_cbm: Mapped[float | None] = mapped_column(Float)
    capacidad_kg: Mapped[float | None] = mapped_column(Float)

    embarque: Mapped[Embarque] = relationship(back_populates="unidades")
    packing_lists: Mapped[list[PackingList]] = relationship(back_populates="unidad")


class EventoEmbarque(Base):
    __tablename__ = "eventos_embarque"
    id: Mapped[int] = mapped_column(primary_key=True)
    embarque_id: Mapped[int] = mapped_column(ForeignKey("embarques.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    fecha: Mapped[datetime] = mapped_column(DateTime)
    ubicacion: Mapped[str | None] = mapped_column(String(150))
    observacion: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    embarque: Mapped[Embarque] = relationship(back_populates="eventos")


# --------------------------------------------------------------------------
# Soporte: historial, alertas, idempotencia, importaciones
# --------------------------------------------------------------------------
class Historial(Base):
    __tablename__ = "historial"
    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(30))
    entidad_id: Mapped[int] = mapped_column(Integer)
    factura_id: Mapped[int | None] = mapped_column(Integer, index=True)
    accion: Mapped[str] = mapped_column(String(60))
    detalle: Mapped[dict | list | None] = mapped_column(JSON)
    motivo: Mapped[str | None] = mapped_column(String(500))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)

    usuario: Mapped[Usuario | None] = relationship()


class Alerta(Base):
    __tablename__ = "alertas"
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"))
    tipo: Mapped[str] = mapped_column(String(40))
    mensaje: Mapped[str] = mapped_column(String(500))
    referencia: Mapped[dict | None] = mapped_column(JSON)
    resuelta: Mapped[bool] = mapped_column(Boolean, default=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class Idempotencia(Base):
    __tablename__ = "idempotencia"
    clave: Mapped[str] = mapped_column(String(160), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(Integer)
    respuesta: Mapped[dict | list | None] = mapped_column(JSON)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class ImportacionOC(Base):
    __tablename__ = "importaciones_oc"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    nombre_archivo: Mapped[str] = mapped_column(String(300))
    estado: Mapped[str] = mapped_column(String(12), default="PREVIA")  # PREVIA | APLICADA
    filas: Mapped[list] = mapped_column(JSON)
    resultado: Mapped[dict | None] = mapped_column(JSON)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
