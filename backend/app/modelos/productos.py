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
    from app.modelos.grupos import GrupoProducto
    from app.modelos.maestros import Articulo, Atributo, Proveedor


class Producto(DeOrganizacion, Base):
    """Un producto de cualquier tipo (un químico, una prenda, una materia prima,
    un electrodoméstico, un alimento…): su código propio (`codigo_generico`), su
    nombre, la unidad de sus variantes, su familia y, si se compra, su proveedor.
    Todo lo demás (marca, modelo, material…) son sus atributos de producto
    (producto_atributos), los que dice su familia. Lo comparten todas sus
    variantes (artículos) y sus compuestos. Con el complemento de comercio
    exterior, aquí viven también su ficha técnica y su clasificación arancelaria."""

    __tablename__ = "productos"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo_generico", name="uq_productos_org_codigo_generico"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    # Quién lo vende (opcional): un proveedor solo ve y carga sus propios productos
    proveedor_id: Mapped[int | None] = mapped_column(ForeignKey("proveedores.id"), index=True)
    # Su grupo de producto (modelos/grupos.py): una familia, que heredan sus tallas que no tienen
    # una propia, o una categoría puesta a mano (que dice también su familia). Sin categoría a
    # mano, la categoría se reconoce sola por las condiciones de las categorías.
    grupo_producto_id: Mapped[int | None] = mapped_column(
        ForeignKey("grupos_producto.id", name="fk_productos_grupo_producto_id"), index=True)
    # Código del producto (el «genérico»): lo comparten todas sus variantes y compuestos
    codigo_generico: Mapped[str | None] = mapped_column(String(40), index=True)
    unidad: Mapped[str | None] = mapped_column(String(5))  # unidad de sus variantes simples (lista «unidad»)
    nombre: Mapped[str | None] = mapped_column(String(200))  # nombre comercial
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

    proveedor: Mapped["Proveedor | None"] = relationship()
    atributos: Mapped[list["ProductoAtributo"]] = relationship(
        back_populates="producto", cascade="all, delete-orphan", lazy="selectin", order_by="ProductoAtributo.id")
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
    grupo_producto: Mapped["GrupoProducto | None"] = relationship()

    # La familia y la categoría a mano, leídas del grupo de producto (en consultas, por su id)
    @hybrid_property
    def familia_etiquetado_id(self) -> int | None:
        g = self.grupo_producto
        return g.familia.id if g is not None and g.familia is not None else None

    @familia_etiquetado_id.inplace.setter
    def _familia_etiquetado_id_set(self, familia_id: int | None) -> None:
        """Poner la familia: se conserva la categoría a mano si es de esa familia."""
        g = self.grupo_producto
        if g is not None and g.clase == "CATEGORIA" and familia_id is not None and g.padre_id == familia_id:
            return
        self._poner_grupo(familia_id)

    @familia_etiquetado_id.inplace.expression
    @classmethod
    def _familia_etiquetado_id_expr(cls):
        from sqlalchemy import case, select

        from app.modelos.grupos import GrupoProducto

        return (select(case((GrupoProducto.clase == "CATEGORIA", GrupoProducto.padre_id), else_=GrupoProducto.id))
                .where(GrupoProducto.id == cls.grupo_producto_id).correlate_except(GrupoProducto).scalar_subquery())

    @hybrid_property
    def categoria_etiquetado_id(self) -> int | None:
        g = self.grupo_producto
        return g.id if g is not None and g.clase == "CATEGORIA" else None

    @categoria_etiquetado_id.inplace.setter
    def _categoria_etiquetado_id_set(self, categoria_id: int | None) -> None:
        """Poner la categoría a mano; quitarla deja la familia que la contenía."""
        if categoria_id is not None:
            self._poner_grupo(categoria_id)
        elif self.grupo_producto is not None and self.grupo_producto.clase == "CATEGORIA":
            self._poner_grupo(self.grupo_producto.padre_id)

    @categoria_etiquetado_id.inplace.expression
    @classmethod
    def _categoria_etiquetado_id_expr(cls):
        from sqlalchemy import select

        from app.modelos.grupos import GrupoProducto

        return (select(GrupoProducto.id).where(GrupoProducto.id == cls.grupo_producto_id, GrupoProducto.clase == "CATEGORIA")
                .correlate_except(GrupoProducto).scalar_subquery())

    def _poner_grupo(self, grupo_id: int | None) -> None:
        from sqlalchemy.orm import object_session

        from app.modelos.grupos import GrupoProducto

        db = object_session(self)
        self.grupo_producto = db.get(GrupoProducto, grupo_id) if grupo_id is not None and db is not None else None
        self.grupo_producto_id = grupo_id

    @property
    def valores(self) -> dict:
        """{código del atributo: valor} de sus atributos de producto."""
        return {x.atributo.codigo: x.valor for x in self.atributos}

    def valor(self, codigo: str) -> str | None:
        return next((x.valor for x in self.atributos if x.atributo.codigo == codigo), None)

    def valor_de_catalogo(self, catalogo: str) -> str | None:
        """El código guardado en su atributo que apunta a ese catálogo (la marca: «marcas»)."""
        return next((x.valor for x in self.atributos if x.atributo.catalogo == catalogo), None)

    @property
    def marca_codigo(self) -> str | None:
        return self.valor_de_catalogo("marcas")

    @property
    def aprobado(self) -> bool:
        return self.estado in ("aprobado", "corregido") and bool(self.codigo)

    @property
    def revisado_por(self) -> "Usuario | None":
        return self.clasificacion.revisado_por if self.clasificacion else None


class ProductoAtributo(DeOrganizacion, Base):
    """Valor de un atributo de producto (uno por atributo): la marca, el modelo, el material…"""

    __tablename__ = "producto_atributos"
    __table_args__ = (UniqueConstraint("producto_id", "atributo_id", name="uq_producto_atributos_producto_atributo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    producto_id: Mapped[int] = mapped_column(ForeignKey("productos.id", ondelete="CASCADE"), index=True)
    atributo_id: Mapped[int] = mapped_column(ForeignKey("atributos.id"), index=True)
    valor: Mapped[str] = mapped_column(String(200))

    producto: Mapped[Producto] = relationship(back_populates="atributos")
    atributo: Mapped["Atributo"] = relationship(lazy="joined")


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
