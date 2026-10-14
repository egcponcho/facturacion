"""Productos: ficha técnica, partidas por país, fotos, documentos y versiones.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import Tasa, ahora
from app.modelos.empresa import ConAdjunto

if TYPE_CHECKING:
    from app.modelos.acceso import Usuario
    from app.modelos.maestros import Articulo, GrupoArticulo, Marca, Proveedor


class Producto(DeOrganizacion, Base):
    """Ficha técnica de un estilo-color de un proveedor. La comparten todas sus
    tallas (artículos) y sus prepacks; aquí vive su clasificación arancelaria:
    la partida SAC aprobada y el código nacional de cada país destino."""

    __tablename__ = "productos"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo_generico", name="uq_productos_org_codigo_generico"), UniqueConstraint("proveedor_id", "estilo", "color"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proveedor_id: Mapped[int] = mapped_column(ForeignKey("proveedores.id"), index=True)
    estilo: Mapped[str] = mapped_column(String(40))
    color: Mapped[str | None] = mapped_column(String(60))
    marca_id: Mapped[int | None] = mapped_column(ForeignKey("marcas.id"), index=True)
    grupo_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_articulos.id"), index=True)
    # Familia de etiquetado del estilo-color: la heredan sus tallas que no tienen una propia
    familia_etiquetado_id: Mapped[int | None] = mapped_column(
        ForeignKey("familias_etiquetado.id", name="fk_productos_familia_etiquetado_id"), index=True)
    # Genérico: los primeros 8 dígitos del código de artículo (estilo-color). Todas
    # sus tallas (los 3 últimos dígitos), sólidos y prepacks, comparten esta ficha
    codigo_generico: Mapped[str | None] = mapped_column(String(40), index=True)
    unidad: Mapped[str | None] = mapped_column(String(5))  # unidad de sus tallas sólidas: PAR | UN
    nombre: Mapped[str | None] = mapped_column(String(200))  # nombre comercial del estilo
    # Ficha técnica: tipo de producto del clasificador, atributos, composición
    # por parte, uso, tallas, usuario y datos que piden los aranceles nacionales
    tipo: Mapped[str | None] = mapped_column(String(30))
    ficha: Mapped[dict] = mapped_column(JSON, default=dict)
    # Dos descripciones que se arman solas con la ficha (se pueden editar):
    # la técnica en español para la DUCA y la comercial para catálogos y documentos
    descripcion_aduana: Mapped[str | None] = mapped_column(String(400))
    descripcion_comercial: Mapped[str | None] = mapped_column(String(300))
    pais_origen: Mapped[str | None] = mapped_column(String(2))
    pais_procedencia: Mapped[str | None] = mapped_column(String(2))
    ficha_completa: Mapped[bool] = mapped_column(Boolean, default=False)
    faltan: Mapped[list] = mapped_column(JSON, default=list)
    # Versión de la ficha: al cambiar una ficha aprobada se cierra y se abre otra
    version_ficha: Mapped[int] = mapped_column(Integer, default=1)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    # borrador | sugerida (borrador completo) | revision (enviada) | aprobado | corregido | observado
    estado: Mapped[str] = mapped_column(String(12), default="borrador", index=True)
    # Clasificación genérica aprobada: el HS6 (estable, internacional) y la
    # línea regional SAC. Cada país tiene su propia clasificación (PartidaPais);
    # un código nacional nunca se guarda como código del producto. El trabajo
    # de clasificar (sugerencias, evidencia, análisis, revisión) vive aparte,
    # en ClasificacionProducto.
    codigo: Mapped[str | None] = mapped_column(String(14))  # HS6 aprobado
    sac_codigo: Mapped[str | None] = mapped_column(String(10))  # línea SAC regional aprobada
    notas: Mapped[str | None] = mapped_column(String(1000))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)  # control de concurrencia

    proveedor: Mapped["Proveedor"] = relationship()
    marca: Mapped["Marca | None"] = relationship()
    grupo: Mapped["GrupoArticulo | None"] = relationship()
    clasificacion: Mapped["ClasificacionProducto | None"] = relationship(
        back_populates="producto", cascade="all, delete-orphan", uselist=False, lazy="joined")
    articulos: Mapped[list["Articulo"]] = relationship(back_populates="producto", order_by="Articulo.id")
    partidas: Mapped[list["PartidaPais"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", order_by="PartidaPais.pais"
    )
    fotos: Mapped[list["ProductoFoto"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", order_by="ProductoFoto.id"
    )
    documentos: Mapped[list["ProductoDocumento"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", order_by="ProductoDocumento.id"
    )
    versiones: Mapped[list["ProductoVersion"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", order_by="ProductoVersion.version"
    )

    @property
    def aprobado(self) -> bool:
        return self.estado in ("aprobado", "corregido") and bool(self.codigo)

    @property
    def revisado_por(self) -> "Usuario | None":
        return self.clasificacion.revisado_por if self.clasificacion else None


class ClasificacionProducto(DeOrganizacion, Base):
    """Trabajo de clasificación de un producto (1:1): lo que sugirió el motor
    o trajo el proveedor, la evidencia y el análisis, y quién lo revisó. El
    resultado aprobado (HS6 y línea SAC) queda en el producto."""

    __tablename__ = "clasificaciones_producto"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(
        ForeignKey("productos.id", ondelete="CASCADE", name="fk_clasificaciones_producto_producto_id"), unique=True, index=True)
    sugerido: Mapped[str | None] = mapped_column(String(14))  # HS6 del motor
    propuesta: Mapped[str | None] = mapped_column(String(14))  # HS6 traído de un archivo o del proveedor
    sac_sugerido: Mapped[str | None] = mapped_column(String(10))  # línea SAC regional sugerida (8-10)
    version_arancel_id: Mapped[int | None] = mapped_column(
        ForeignKey("versiones_dataset.id", name="fk_clasificaciones_producto_version"), index=True)
    evidencia: Mapped[dict | None] = mapped_column(JSON)  # versión, reglas, candidatos y razones al aprobar
    confianza: Mapped[str | None] = mapped_column(String(10))
    fuente: Mapped[str | None] = mapped_column(String(12))  # regla | historial | criterio
    perfil: Mapped[str | None] = mapped_column(String(200), index=True)
    analisis: Mapped[dict | None] = mapped_column(JSON)  # razones, fundamento, alternativas, alertas
    alertas_ok: Mapped[list] = mapped_column(JSON, default=list)
    observaciones: Mapped[str | None] = mapped_column(String(2000))  # del especialista
    resolucion: Mapped[str | None] = mapped_column(String(200))  # resolución anticipada o criterio DGA
    opinion_ia: Mapped[dict | None] = mapped_column(JSON)
    revisado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", name="fk_clasificaciones_producto_revisado_por"), index=True)
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime, index=True)

    producto: Mapped[Producto] = relationship(back_populates="clasificacion")
    revisado_por: Mapped["Usuario | None"] = relationship()


def _de_clasificacion(campo: str, vacio=None):
    """Dato del trabajo de clasificación leído y escrito desde el producto
    (la fila se crea al escribir). En consultas es el valor de su fila."""

    def leer(self):
        c = self.clasificacion
        v = getattr(c, campo) if c is not None else None
        return vacio() if v is None and vacio else v

    def escribir(self, valor):
        if self.clasificacion is None:
            if valor is None:
                return
            self.clasificacion = ClasificacionProducto()
        setattr(self.clasificacion, campo, valor)

    def expresion(cls):
        from sqlalchemy import select

        return (select(getattr(ClasificacionProducto, campo)).where(ClasificacionProducto.producto_id == cls.id)
                .correlate_except(ClasificacionProducto).scalar_subquery())

    return hybrid_property(leer, escribir, expr=expresion)


CAMPOS_CLASIFICACION = ("sugerido", "propuesta", "sac_sugerido", "version_arancel_id", "evidencia", "confianza", "fuente",
                        "perfil", "analisis", "alertas_ok", "observaciones", "resolucion", "opinion_ia", "revisado_por_id",
                        "revisado_en")
for _campo in CAMPOS_CLASIFICACION:
    setattr(Producto, _campo, _de_clasificacion(_campo, list if _campo == "alertas_ok" else None))


class PartidaPais(DeOrganizacion, Base):
    """Código arancelario nacional del producto en un país destino."""

    __tablename__ = "partidas_pais"
    __table_args__ = (UniqueConstraint("producto_id", "pais"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    pais: Mapped[str] = mapped_column(String(2))
    codigo: Mapped[str] = mapped_column(String(14))
    dai: Mapped[float | None] = mapped_column(Tasa)  # derecho arancelario a la importación, %
    estado: Mapped[str] = mapped_column(String(12))  # ok | auto | sac | nuevo | sinarancel | elegir
    fuente: Mapped[str | None] = mapped_column(String(12))  # base | aprendido | manual | arancel
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    # Clasificación nacional con evidencia: la línea oficial elegida (no un
    # código recortado), su versión y fuente, lo sugerido frente a lo final,
    # el motivo si se cambió y lo que aplicaba al aprobar (regla, impuestos, regulaciones)
    inciso_id: Mapped[int | None] = mapped_column(ForeignKey("incisos_nacionales.id", ondelete="SET NULL", name="fk_partidas_inciso"), index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id", name="fk_partidas_version"))
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id", name="fk_partidas_fuente"))
    sugerido: Mapped[str | None] = mapped_column(String(14))
    motivo: Mapped[str | None] = mapped_column(String(300))  # por qué el final difiere del sugerido
    aprobado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", name="fk_partidas_aprobado_por"))
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime)
    evidencia: Mapped[dict | None] = mapped_column(JSON)  # regla nacional, condiciones, impuestos y regulaciones

    producto: Mapped[Producto] = relationship(back_populates="partidas")


class ProductoFoto(ConAdjunto, DeOrganizacion, Base):
    __tablename__ = "producto_fotos"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)

    producto: Mapped[Producto] = relationship(back_populates="fotos")


class ProductoDocumento(ConAdjunto, DeOrganizacion, Base):
    """Ficha técnica del proveedor o del laboratorio (SDS, TDS, COA): evidencia
    técnica del producto (capa de la empresa). Sus datos (CAS, composición,
    estado físico, densidad, pH…) son hechos para la ficha; nunca una fuente
    arancelaria: no dan códigos, DAI, impuestos ni regulaciones."""

    __tablename__ = "producto_documentos"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # lista tipo_documento (SDS, TDS, COA…)
    emisor: Mapped[str | None] = mapped_column(String(200))  # proveedor o laboratorio
    fecha_documento: Mapped[date | None] = mapped_column(Date)
    datos: Mapped[dict] = mapped_column(JSON, default=dict)  # {atributo técnico: valor} leídos del documento

    producto: Mapped[Producto] = relationship(back_populates="documentos")


class ProductoVersion(DeOrganizacion, Base):
    """Versión cerrada de la ficha técnica, con su vigencia y la partida que tenía."""

    __tablename__ = "producto_versiones"
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    desde: Mapped[date | None] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date)
    motivo: Mapped[str | None] = mapped_column(String(300))
    datos: Mapped[dict] = mapped_column(JSON)  # copia de la ficha y su clasificación
    cerrado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    cerrado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    producto: Mapped[Producto] = relationship(back_populates="versiones")
