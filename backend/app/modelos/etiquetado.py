"""Etiquetado: familias de etiquetado, plantillas con versiones aprobables,
dónde se aplica cada plantilla y las etiquetas generadas (docs/ETIQUETADO.md).

Una etiqueta referencia el origen de sus datos (artículo, línea de OC, OC,
bulto); no copia la ficha del producto. Lo único que se guarda de los datos es
la instantánea de los valores usados en cada generación, para poder volver a
producir exactamente la misma etiqueta.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import ahora

MODALIDADES = ("ARTICULO", "OC", "OC_ARTICULO")
# Qué representa cada etiqueta: la orden, una línea, una unidad, un bulto…
UNIDADES = ("ORDEN", "LINEA", "UNIDAD", "BULTO", "MANUAL")
ESTADOS_VERSION = ("BORRADOR", "PENDIENTE", "APROBADA", "RECHAZADA", "ARCHIVADA")
AMBITOS = ("GENERAL", "FAMILIA", "PRODUCTO", "ARTICULO", "OC")
FORMATOS = ("PDF", "PNG", "SVG", "ZIP")


def _en(col: str, valores) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in valores)})"


class FamiliaEtiquetado(DeOrganizacion, Base):
    """Familia propia de la empresa para elegir etiquetas (calzado, ropa…).
    Independiente de la clasificación arancelaria. `campos`: los campos
    habituales de la familia y cuáles son obligatorios
    ([{"campo": "articulo.talla", "obligatorio": true}])."""

    __tablename__ = "familias_etiquetado"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_familias_etiquetado_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    campos: Mapped[list] = mapped_column(JSON, default=list)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class PlantillaEtiqueta(DeOrganizacion, Base):
    """Diseño con nombre estable. Lo que se dibuja vive en sus versiones; la
    vigente es la aprobada que se usa en producción (una versión nueva no la
    reemplaza hasta que se aprueba)."""

    __tablename__ = "plantillas_etiqueta"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "nombre", name="uq_plantillas_etiqueta_org_nombre"),
        CheckConstraint(_en("modalidad", MODALIDADES), name="ck_plantillas_etiqueta_modalidad"),
        CheckConstraint(_en("unidad", UNIDADES), name="ck_plantillas_etiqueta_unidad"),
        CheckConstraint("estado IN ('ACTIVA', 'ARCHIVADA')", name="ck_plantillas_etiqueta_estado"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None] = mapped_column(String(500))
    modalidad: Mapped[str] = mapped_column(String(12))  # de dónde salen los datos
    unidad: Mapped[str] = mapped_column(String(10), default="LINEA")  # qué representa cada etiqueta, por defecto
    familia_id: Mapped[int | None] = mapped_column(ForeignKey("familias_etiquetado.id"), index=True)  # para la que se diseñó
    estado: Mapped[str] = mapped_column(String(10), default="ACTIVA", index=True)
    version_vigente_id: Mapped[int | None] = mapped_column(
        ForeignKey("versiones_plantilla.id", name="fk_plantillas_etiqueta_version_vigente_id", use_alter=True))
    origen_id: Mapped[int | None] = mapped_column(  # duplicada de
        ForeignKey("plantillas_etiqueta.id", name="fk_plantillas_etiqueta_origen_id"))
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    familia: Mapped[FamiliaEtiquetado | None] = relationship()
    versiones: Mapped[list["VersionPlantilla"]] = relationship(
        back_populates="plantilla", foreign_keys="VersionPlantilla.plantilla_id", order_by="VersionPlantilla.numero")
    vigente: Mapped["VersionPlantilla | None"] = relationship(foreign_keys=[version_vigente_id], post_update=True)


class VersionPlantilla(DeOrganizacion, Base):
    """Una versión numerada del diseño. Borrador y rechazada se editan; una
    pendiente espera revisión; una aprobada no se modifica nunca (los cambios
    van en una versión nueva); una archivada se conserva para el historial."""

    __tablename__ = "versiones_plantilla"
    __table_args__ = (
        UniqueConstraint("plantilla_id", "numero", name="uq_versiones_plantilla_plantilla_numero"),
        CheckConstraint(_en("estado", ESTADOS_VERSION), name="ck_versiones_plantilla_estado"),
        CheckConstraint("ancho_mm > 0 AND alto_mm > 0", name="ck_versiones_plantilla_medidas"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plantilla_id: Mapped[int] = mapped_column(ForeignKey("plantillas_etiqueta.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(10), default="BORRADOR", index=True)
    diseno: Mapped[dict] = mapped_column(JSON)
    ancho_mm: Mapped[float] = mapped_column(Float)
    alto_mm: Mapped[float] = mapped_column(Float)
    cambios: Mapped[str | None] = mapped_column(Text)  # resumen frente a la versión de la que parte
    basada_en_id: Mapped[int | None] = mapped_column(
        ForeignKey("versiones_plantilla.id", name="fk_versiones_plantilla_basada_en_id"))
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    enviada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    enviada_en: Mapped[datetime | None] = mapped_column(DateTime)
    revisada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    revisada_en: Mapped[datetime | None] = mapped_column(DateTime)
    comentario: Mapped[str | None] = mapped_column(String(1000))  # de la revisión (rechazo o aprobación)
    version: Mapped[int] = mapped_column(Integer, default=1)  # control de concurrencia del borrador

    plantilla: Mapped[PlantillaEtiqueta] = relationship(back_populates="versiones", foreign_keys=[plantilla_id])


class AsignacionEtiqueta(DeOrganizacion, Base):
    """Dónde se aplica una plantilla: a toda la organización, a una familia,
    a un producto (todas sus variantes), a un artículo o, como excepción, a
    una OC. `predeterminada` desempata entre varias del mismo nivel."""

    __tablename__ = "asignaciones_etiqueta"
    __table_args__ = (
        CheckConstraint(_en("ambito", AMBITOS), name="ck_asignaciones_etiqueta_ambito"),
        CheckConstraint(
            "(ambito = 'GENERAL' AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL)"
            " OR (ambito = 'FAMILIA' AND familia_id IS NOT NULL AND producto_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL)"
            " OR (ambito = 'PRODUCTO' AND producto_id IS NOT NULL AND familia_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL)"
            " OR (ambito = 'ARTICULO' AND articulo_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL AND oc_id IS NULL)"
            " OR (ambito = 'OC' AND oc_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL)",
            name="ck_asignaciones_etiqueta_destino"),
        Index("ix_asignaciones_etiqueta_destino", "ambito", "familia_id", "producto_id", "articulo_id", "oc_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    plantilla_id: Mapped[int] = mapped_column(ForeignKey("plantillas_etiqueta.id", ondelete="CASCADE"), index=True)
    ambito: Mapped[str] = mapped_column(String(10))
    familia_id: Mapped[int | None] = mapped_column(ForeignKey("familias_etiquetado.id"), index=True)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), index=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    oc_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    predeterminada: Mapped[bool] = mapped_column(Boolean, default=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo: Mapped[str | None] = mapped_column(String(300))  # por qué (sobre todo en una excepción)
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    plantilla: Mapped[PlantillaEtiqueta] = relationship()


class GeneracionEtiquetas(DeOrganizacion, Base):
    """Un lote de etiquetas generado: quién, cuándo, desde qué OC, con qué
    criterio y formato. Los archivos no se guardan: se vuelven a producir
    exactamente desde la versión y la instantánea de cada ítem (y su huella
    sha256 permite comprobar que son los mismos)."""

    __tablename__ = "generaciones_etiqueta"
    __table_args__ = (
        CheckConstraint(_en("formato", FORMATOS), name="ck_generaciones_etiqueta_formato"),
        CheckConstraint("estado IN ('GENERADA', 'PRUEBA')", name="ck_generaciones_etiqueta_estado"),
        CheckConstraint("total >= 0", name="ck_generaciones_etiqueta_total"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    oc_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    modalidad: Mapped[str] = mapped_column(String(12))
    unidad: Mapped[str] = mapped_column(String(10))
    formato: Mapped[str] = mapped_column(String(4))
    estado: Mapped[str] = mapped_column(String(10), default="GENERADA", index=True)  # PRUEBA: con versiones sin aprobar
    total: Mapped[int] = mapped_column(Integer, default=0)
    parametros: Mapped[dict] = mapped_column(JSON, default=dict)  # hoja, cantidades manuales, selección
    advertencias: Mapped[list] = mapped_column(JSON, default=list)  # las aceptadas al confirmar
    archivo: Mapped[str | None] = mapped_column(String(200))  # nombre del archivo producido
    sha256: Mapped[str | None] = mapped_column(String(64))
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)

    items: Mapped[list["GeneracionItem"]] = relationship(
        back_populates="generacion", cascade="all, delete-orphan", order_by="GeneracionItem.id")


class GeneracionItem(DeOrganizacion, Base):
    """Un grupo de etiquetas iguales salvo su número: la plantilla y la
    versión exactas, el origen (artículo, línea, bulto) y los valores usados."""

    __tablename__ = "generacion_items"
    __table_args__ = (CheckConstraint("cantidad >= 1", name="ck_generacion_items_cantidad"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    generacion_id: Mapped[int] = mapped_column(ForeignKey("generaciones_etiqueta.id", ondelete="CASCADE"), index=True)
    plantilla_id: Mapped[int] = mapped_column(ForeignKey("plantillas_etiqueta.id"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("versiones_plantilla.id"), index=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    posicion_id: Mapped[int | None] = mapped_column(ForeignKey("posiciones_oc.id"), index=True)
    familia_id: Mapped[int | None] = mapped_column(ForeignKey("familias_etiquetado.id"), index=True)
    referencia: Mapped[str | None] = mapped_column(String(120))  # lo que se lee en el historial (SKU, línea, bulto)
    cantidad: Mapped[int] = mapped_column(Integer)
    valores: Mapped[dict] = mapped_column(JSON, default=dict)  # instantánea: campo → valor
    motivo: Mapped[str | None] = mapped_column(String(200))  # por qué se eligió esa plantilla

    generacion: Mapped[GeneracionEtiquetas] = relationship(back_populates="items")
