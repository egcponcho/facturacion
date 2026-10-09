"""Órdenes de compra, sus posiciones e importaciones desde el ERP.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.core.db import Base
from app.modelos.base import Cantidad, ahora, cant

if TYPE_CHECKING:
    from app.modelos.maestros import Articulo, Proveedor


class OrdenCompra(Base):
    __tablename__ = "ordenes_compra"
    __table_args__ = (UniqueConstraint("proveedor_id", "numero"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # Campos propios de la empresa (core/campos_propios.py)
    extra: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    numero: Mapped[str] = mapped_column(String(40))  # formato de cada empresa
    # Empresa que factura, moneda y precio: opcionales al cargar la OC, se exigen al facturar
    sociedad: Mapped[str | None] = mapped_column(String(10), index=True)
    centro: Mapped[str | None] = mapped_column(String(10))
    centro_destino: Mapped[str | None] = mapped_column(String(10))  # centro del país al que va (p. ej. 2220)
    moneda: Mapped[str | None] = mapped_column(String(3))
    incoterm: Mapped[str | None] = mapped_column(String(10))
    fecha: Mapped[date | None] = mapped_column(Date, index=True)
    puerto_despacho: Mapped[str | None] = mapped_column(String(10))
    pais_origen: Mapped[str | None] = mapped_column(String(2))
    pais_procedencia: Mapped[str | None] = mapped_column(String(2))
    fecha_xf_original: Mapped[date | None] = mapped_column(Date)
    fecha_xf: Mapped[date | None] = mapped_column(Date)  # XF actualizada
    fecha_tienda: Mapped[date | None] = mapped_column(Date)  # requerida en tienda
    # Códigos de las dos liberaciones según el ERP de la empresa (catálogo
    # estados_liberacion); `liberada` dice si con ellos se puede facturar.
    liberacion_comercial: Mapped[str] = mapped_column(String(10))
    liberacion_logistica: Mapped[str] = mapped_column(String(10))
    fecha_lib_comercial: Mapped[date | None] = mapped_column(Date)
    fecha_lib_logistica: Mapped[date | None] = mapped_column(Date)
    liberada: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
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
    posicion: Mapped[str] = mapped_column(String(10))  # 10, 20, 30…
    almacen: Mapped[str | None] = mapped_column(String(10))  # cada posición va a su almacén
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    codigo_sap: Mapped[str] = mapped_column(String(40))  # SKU; texto: conserva ceros iniciales
    upc: Mapped[str | None] = mapped_column(String(40))
    estilo: Mapped[str | None] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    talla: Mapped[str | None] = mapped_column(String(20))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    marca: Mapped[str | None] = mapped_column(String(10))
    grupo: Mapped[str | None] = mapped_column(String(15))
    categoria: Mapped[str | None] = mapped_column(String(10))
    tipo_empaque: Mapped[str] = mapped_column(String(10), default="SOLIDO")  # SOLIDO | PREPACK
    # Empaque de la compra (dato de la posición, no del artículo): casepack =
    # unidades exactas por caja master; inner_pack = unidades por paquete
    # interno (todos iguales). Con ambos, el casepack es múltiplo del inner.
    casepack: Mapped[int | None] = mapped_column(Integer)
    inner_pack: Mapped[int | None] = mapped_column(Integer)
    prepack: Mapped[str | None] = mapped_column(String(30))
    unidades_por_caja: Mapped[int | None] = mapped_column(Integer)  # total de la curva
    cantidad: Mapped[float] = mapped_column(Cantidad)
    unidad: Mapped[str] = mapped_column(String(5))  # modulos/maestros/unidades.py: PAR, UN, KG, L, M…
    precio: Mapped[float | None] = mapped_column(Float)
    fecha_entrega: Mapped[date | None] = mapped_column(Date)
    pais_origen: Mapped[str | None] = mapped_column(String(3))
    bloqueada: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_bloqueo: Mapped[str | None] = mapped_column(String(200))

    oc: Mapped[OrdenCompra] = relationship(back_populates="posiciones")
    articulo: Mapped[Articulo | None] = relationship()

    @validates("cantidad")
    def _cantidad(self, _k, v):
        return cant(v)  # sin residuos de coma flotante al sumar y restar


class PerfilImportacion(Base):
    """Cómo leer el archivo de OCs que exporta el ERP de la empresa: el nombre
    de la columna de cada dato del sistema, la fila de los encabezados, el
    formato de las fechas y los valores por defecto de lo que no trae."""

    __tablename__ = "perfiles_importacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    columnas: Mapped[dict] = mapped_column(JSON, default=dict)  # campo → "Columna, Otra columna"
    valores: Mapped[dict] = mapped_column(JSON, default=dict)  # campo → valor por defecto
    fila_encabezado: Mapped[int] = mapped_column(Integer, default=1)
    formato_fecha: Mapped[str | None] = mapped_column(String(12))  # MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD…
    predeterminado: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ImportacionOC(Base):
    __tablename__ = "importaciones_oc"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    nombre_archivo: Mapped[str] = mapped_column(String(300))
    estado: Mapped[str] = mapped_column(String(12), default="PREVIA")  # PREVIA | APLICADA
    filas: Mapped[list] = mapped_column(JSON)
    resultado: Mapped[dict | None] = mapped_column(JSON)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
