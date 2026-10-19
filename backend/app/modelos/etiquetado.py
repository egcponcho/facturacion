"""Etiquetado: tipos de etiqueta, familias de etiquetado, plantillas con
versiones aprobables, qué diseño usa cada cosa (usos de diseño) y las
etiquetas generadas (docs/ETIQUETADO.md).

Una etiqueta referencia el origen de sus datos (artículo, línea de OC, OC,
bulto); no copia la ficha del producto. Lo único que se guarda de los datos es
la instantánea de los valores usados en cada generación, para poder volver a
producir exactamente la misma etiqueta.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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

from app.core.db import Base
from app.core.organizacion import DeOrganizacion
from app.modelos.base import ahora

# Qué se etiqueta: un artículo (con o sin OC: la OC solo agrega datos), un
# bulto de una lista de empaque o un documento (la OC o la lista completa)
SUJETOS = ("ARTICULO", "BULTO", "DOCUMENTO")
# Cuántas etiquetas salen de cada registro
CANTIDADES = ("POR_UNIDAD", "POR_LINEA", "POR_ARTICULO", "POR_BULTO", "POR_DOCUMENTO", "MANUAL")
CANTIDADES_DE = {"ARTICULO": ("POR_UNIDAD", "POR_LINEA", "POR_ARTICULO", "MANUAL"), "BULTO": ("POR_BULTO",),
                 "DOCUMENTO": ("POR_DOCUMENTO", "MANUAL")}
# Dónde se pone un diseño, de lo más específico a lo más general (reglas.py)
NIVELES = ("SKU", "PRODUCTO", "CATEGORIA", "FAMILIA", "TIPO_EMPAQUE", "GENERAL")
NIVELES_DE = {"ARTICULO": ("SKU", "PRODUCTO", "CATEGORIA", "FAMILIA", "GENERAL"), "BULTO": ("TIPO_EMPAQUE", "GENERAL"),
              "DOCUMENTO": ("GENERAL",)}
# Columna del destino de cada nivel
DESTINO_DE = {"SKU": "articulo_id", "PRODUCTO": "producto_id", "CATEGORIA": "categoria_id", "FAMILIA": "familia_id",
              "TIPO_EMPAQUE": "tipo_empaque_id"}
# Dónde va la etiqueta (a qué se pega), según lo que lleva el diseño:
# - artículo: la línea del documento de origen (posición de la OC desde una OC,
#   línea de la lista de empaque desde una lista), la posición de la OC, la
#   línea de la lista de empaque, cada variante (SKU) o el artículo genérico
#   (producto estilo-color);
# - documento: el de origen, la OC o la lista de empaque;
# - bulto: cada empaque (inner, caja, pallet…; ver tipos_etiqueta_empaques).
ALCANCES_DE = {"ARTICULO": ("LINEA", "POSICION_OC", "POSICION_PL", "ARTICULO", "PRODUCTO"),
               "DOCUMENTO": ("DOCUMENTO", "OC", "PL"), "BULTO": ("EMPAQUE",)}
ALCANCES = tuple(dict.fromkeys(a for v in ALCANCES_DE.values() for a in v))
# Cuántas salen de cada lugar, dicho en una regla: una, una por unidad o a mano
CANTIDADES_REGLA = ("UNA", "POR_UNIDAD", "MANUAL")
# Una regla usa un diseño o dice que ese tipo de etiqueta no va ahí
ACCIONES = ("USAR", "NO_LLEVA")
# Excepciones: NINGUNO es el diseño normal de la celda; OC manda sobre todo;
# las demás se revisan en este orden dentro de su celda
CONTEXTOS = ("NINGUNO", "OC", "CENTRO_DESTINO", "PAIS_DESTINO", "SOCIEDAD", "PROVEEDOR", "CONDICION")
ESTADOS_VERSION = ("BORRADOR", "PENDIENTE", "APROBADA", "RECHAZADA", "ARCHIVADA")
FORMATOS = ("PDF", "PNG", "SVG", "ZIP")
TIPOS_CAMPO = ("texto", "numero", "fecha")
# Qué hacer si las fuentes de un campo lógico traen valores distintos
POLITICAS_CAMPO = ("PRIMERA", "ADVERTIR", "BLOQUEAR")
ORIGENES_TRABAJO = ("OC", "ARTICULOS", "PACKING")
ESTADOS_TRABAJO = ("BORRADOR", "VALIDADO", "EN_PROCESO", "GENERADO", "PARCIAL", "ERROR", "CANCELADO")
ESTADOS_REGISTRO = ("LISTO", "ADVERTENCIA", "ERROR", "GENERADO", "OMITIDO")


def _en(col: str, valores) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in valores)})"


def _solo(nivel: str, columna: str | None) -> str:
    otras = [c for c in ("familia_id", "categoria_id", "producto_id", "articulo_id", "tipo_empaque_id") if c != columna]
    return "(" + " AND ".join([f"nivel = '{nivel}'"] + ([f"{columna} IS NOT NULL"] if columna else [])
                              + [f"{c} IS NULL" for c in otras]) + ")"


# Cada nivel lleva solo su destino (el de toda la empresa, ninguno)
CK_DESTINO_USO = " OR ".join([_solo("GENERAL", None), _solo("FAMILIA", "familia_id"), _solo("CATEGORIA", "categoria_id"),
                              _solo("PRODUCTO", "producto_id"), _solo("SKU", "articulo_id"),
                              _solo("TIPO_EMPAQUE", "tipo_empaque_id")])


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
    # Subfamilia de (hereda los campos obligatorios y las reglas de su familia)
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("familias_etiquetado.id"), index=True)

    padre: Mapped["FamiliaEtiquetado | None"] = relationship(remote_side=lambda: FamiliaEtiquetado.id)

    def ruta(self) -> list["FamiliaEtiquetado"]:
        """La familia y sus antecesoras, de la raíz a ella (sin repetir si hubiera un ciclo)."""
        res, f = [], self
        while f is not None and f not in res:
            res.insert(0, f)
            f = f.padre
        return res


class TipoEtiqueta(DeOrganizacion, Base):
    """Una clase de etiqueta física que la empresa imprime (colgante, precio,
    caja master, contenido de OC…): qué se etiqueta (sujeto) y cuántas salen
    de cada registro. Cada diseño es de un tipo; un registro puede llevar una
    etiqueta de cada tipo de su sujeto."""

    __tablename__ = "tipos_etiqueta"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "codigo", name="uq_tipos_etiqueta_org_codigo"),
        UniqueConstraint("id", "organizacion_id", name="uq_tipos_etiqueta_id_org"),
        CheckConstraint(_en("sujeto", SUJETOS), name="ck_tipos_etiqueta_sujeto"),
        CheckConstraint(_en("cantidad", CANTIDADES), name="ck_tipos_etiqueta_cantidad"),
        CheckConstraint("alcance IS NULL OR " + _en("alcance", ALCANCES), name="ck_tipos_etiqueta_alcance"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30))
    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    sujeto: Mapped[str] = mapped_column(String(10))
    cantidad: Mapped[str] = mapped_column(String(14))
    # Todo sujeto debe tener diseño de este tipo (si no, la cobertura lo marca y el trabajo lo bloquea)
    obligatoria: Mapped[bool] = mapped_column(Boolean, default=False)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Dónde va por defecto (ALCANCES_DE[sujeto]); vacío: lo de antes (la línea o el documento de origen,
    # o cada variante si sale una por artículo). Una regla puede decir otro lugar.
    alcance: Mapped[str | None] = mapped_column(String(12))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1)


class CategoriaEtiquetado(DeOrganizacion, Base):
    """Una categoría dentro de una familia de etiquetado (sandalias, botas…;
    camisas, pantalones…), como en la clasificación: se reconoce sola por
    condiciones sobre los datos del artículo y del producto, o se pone a mano
    en el producto. Sin condiciones, solo se pone a mano. Las reglas pueden ir
    a una categoría: más específica que su familia, más general que el producto."""

    __tablename__ = "categorias_etiquetado"
    __table_args__ = (UniqueConstraint("organizacion_id", "codigo", name="uq_categorias_etiquetado_org_codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    familia_id: Mapped[int] = mapped_column(ForeignKey("familias_etiquetado.id"), index=True)
    codigo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    # [{"campo": "articulo.descripcion", "op": "contiene", "valor": "sandal"}]: todas deben cumplirse
    condiciones: Mapped[list] = mapped_column(JSON, default=list)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    familia: Mapped[FamiliaEtiquetado] = relationship()


class TipoEtiquetaEmpaque(DeOrganizacion, Base):
    """A qué tipos de empaque se aplica un tipo de etiqueta de bulto (la
    etiqueta del inner no es la de la caja ni la del pallet). Sin filas, el
    tipo se aplica a todos los empaques."""

    __tablename__ = "tipos_etiqueta_empaques"
    tipo_etiqueta_id: Mapped[int] = mapped_column(ForeignKey("tipos_etiqueta.id", ondelete="CASCADE"), primary_key=True)
    tipo_empaque_id: Mapped[int] = mapped_column(ForeignKey("tipos_empaque.id", ondelete="CASCADE"), primary_key=True, index=True)


class PlantillaEtiqueta(DeOrganizacion, Base):
    """Diseño con nombre estable. Lo que se dibuja vive en sus versiones; la
    vigente es la aprobada que se usa en producción (una versión nueva no la
    reemplaza hasta que se aprueba)."""

    __tablename__ = "plantillas_etiqueta"
    __table_args__ = (
        UniqueConstraint("organizacion_id", "nombre", name="uq_plantillas_etiqueta_org_nombre"),
        CheckConstraint("estado IN ('ACTIVA', 'ARCHIVADA')", name="ck_plantillas_etiqueta_estado"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    descripcion: Mapped[str | None] = mapped_column(String(500))
    tipo_etiqueta_id: Mapped[int] = mapped_column(ForeignKey("tipos_etiqueta.id"), index=True)
    estado: Mapped[str] = mapped_column(String(10), default="ACTIVA", index=True)
    version_vigente_id: Mapped[int | None] = mapped_column(
        ForeignKey("versiones_plantilla.id", name="fk_plantillas_etiqueta_version_vigente_id", use_alter=True))
    origen_id: Mapped[int | None] = mapped_column(  # duplicada de
        ForeignKey("plantillas_etiqueta.id", name="fk_plantillas_etiqueta_origen_id"))
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    tipo: Mapped[TipoEtiqueta] = relationship()
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
    revisada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))  # última revisión (aprobó o rechazó)
    revisada_en: Mapped[datetime | None] = mapped_column(DateTime)
    aprobada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    aprobada_en: Mapped[datetime | None] = mapped_column(DateTime)
    comentario: Mapped[str | None] = mapped_column(String(1000))  # de la revisión (rechazo o aprobación)
    version: Mapped[int] = mapped_column(Integer, default=1)  # control de concurrencia del borrador

    plantilla: Mapped[PlantillaEtiqueta] = relationship(back_populates="versiones", foreign_keys=[plantilla_id])


class UsoDiseno(DeOrganizacion, Base):
    """Qué diseño usa un tipo de etiqueta en un lugar (reglas.py).

    La celda es (tipo de etiqueta, nivel, destino): toda la empresa, una
    familia (y sus subfamilias), un producto (estilo-color), un SKU o un tipo
    de empaque. Cada celda tiene a lo sumo un diseño normal
    (`contexto_tipo` NINGUNO, sin vigencia) y sus excepciones: por destino,
    país, sociedad, proveedor o condiciones, con motivo y vigencia opcional.
    Una excepción de una OC concreta (`oc_id`) manda sobre todo. Nunca se
    borra: se da de baja (`eliminado_en`) y el historial guarda cada cambio."""

    __tablename__ = "usos_diseno"
    __table_args__ = (
        CheckConstraint(_en("nivel", NIVELES), name="ck_usos_diseno_nivel"),
        CheckConstraint(_en("contexto_tipo", CONTEXTOS), name="ck_usos_diseno_contexto_tipo"),
        CheckConstraint(CK_DESTINO_USO, name="ck_usos_diseno_destino"),
        CheckConstraint(_en("accion", ACCIONES), name="ck_usos_diseno_accion"),
        CheckConstraint("(accion = 'USAR') = (plantilla_id IS NOT NULL)", name="ck_usos_diseno_plantilla"),
        CheckConstraint("alcance IS NULL OR " + _en("alcance", ALCANCES), name="ck_usos_diseno_alcance"),
        CheckConstraint("cantidad IS NULL OR " + _en("cantidad", CANTIDADES_REGLA), name="ck_usos_diseno_cantidad"),
        CheckConstraint("(contexto_tipo = 'OC') = (oc_id IS NOT NULL)", name="ck_usos_diseno_oc"),
        CheckConstraint("contexto_tipo <> 'NINGUNO' OR (vigente_desde IS NULL AND vigente_hasta IS NULL)",
                        name="ck_usos_diseno_normal_sin_vigencia"),
        CheckConstraint("vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde",
                        name="ck_usos_diseno_vigencia"),
        # Un solo diseño normal vigente por celda
        Index("uq_usos_diseno_normal", "organizacion_id", "celda", unique=True,
              sqlite_where=text("contexto_tipo = 'NINGUNO' AND eliminado_en IS NULL"),
              postgresql_where=text("contexto_tipo = 'NINGUNO' AND eliminado_en IS NULL")),
        Index("ix_usos_diseno_celda", "celda"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_etiqueta_id: Mapped[int] = mapped_column(ForeignKey("tipos_etiqueta.id"), index=True)
    # Vacío cuando la regla dice que ese tipo de etiqueta no va ahí (accion NO_LLEVA)
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantillas_etiqueta.id"), index=True)
    nivel: Mapped[str] = mapped_column(String(12))
    familia_id: Mapped[int | None] = mapped_column(ForeignKey("familias_etiquetado.id"), index=True)
    categoria_id: Mapped[int | None] = mapped_column(ForeignKey("categorias_etiquetado.id"), index=True)
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id"), index=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    tipo_empaque_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_empaque.id"), index=True)
    # tipo:nivel:destino (se calcula al guardar): agrupa la celda y la hace única
    celda: Mapped[str] = mapped_column(String(60))
    contexto_tipo: Mapped[str] = mapped_column(String(14), default="NINGUNO")
    contexto_valores: Mapped[list] = mapped_column(JSON, default=list)  # códigos (país, centro, sociedad) o ids (proveedor)
    oc_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    # [{"campo": "articulo.marca_codigo", "op": "en", "valor": ["TNF"]}]: todas deben cumplirse (reglas.py)
    condiciones: Mapped[list] = mapped_column(JSON, default=list)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    # Lo que decide la regla además del diseño: si la etiqueta va (USAR) o no (NO_LLEVA), dónde va
    # (ALCANCES; vacío = lo del tipo), cuántas salen (CANTIDADES_REGLA; vacío = lo del tipo) y, entre
    # reglas del mismo lugar que aplican a la vez, cuál gana (mayor prioridad; si empatan, la más antigua)
    accion: Mapped[str] = mapped_column(String(8), default="USAR", server_default="USAR")
    alcance: Mapped[str | None] = mapped_column(String(12))
    cantidad: Mapped[str | None] = mapped_column(String(10))
    prioridad: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    motivo: Mapped[str | None] = mapped_column(String(300))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime)
    eliminado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    eliminado_en: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    plantilla: Mapped[PlantillaEtiqueta | None] = relationship()
    tipo: Mapped[TipoEtiqueta] = relationship()

    @property
    def destino_id(self) -> int | None:
        col = DESTINO_DE.get(self.nivel)
        return getattr(self, col) if col else None


class CampoEtiqueta(DeOrganizacion, Base):
    """Campo lógico de la empresa: un dato de la etiqueta que puede venir de
    varias fuentes del catálogo, en un orden de precedencia (UPC = primero el
    de la línea de la OC, si no el del artículo). Se usa en los diseños como
    `logico.<clave>`; la instantánea guarda de qué fuente salió el valor."""

    __tablename__ = "campos_etiqueta"
    __table_args__ = (UniqueConstraint("organizacion_id", "clave", name="uq_campos_etiqueta_org_clave"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(String(40))
    etiqueta: Mapped[str] = mapped_column(String(80))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(10), default="texto")
    fuentes: Mapped[list] = mapped_column(JSON, default=list)  # claves del catálogo, en orden
    politica: Mapped[str] = mapped_column(String(10), default="PRIMERA")
    sujetos: Mapped[list] = mapped_column(JSON, default=list)  # ARTICULO, BULTO, DOCUMENTO; vacío = todos
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime)
    version: Mapped[int] = mapped_column(Integer, default=1)


class TrabajoEtiquetas(DeOrganizacion, Base):
    """Un trabajo de etiquetado: lo que se eligió en el asistente (origen,
    registros, empaque, diseños, formato), guardado como borrador en cada paso
    para seguir después. Se valida en el servidor (sus registros quedan en
    trabajo_etiqueta_registros) y cada generación es una ejecución
    (generaciones_etiqueta.trabajo_id)."""

    __tablename__ = "trabajos_etiqueta"
    __table_args__ = (UniqueConstraint("id", "organizacion_id", name="uq_trabajos_etiqueta_id_org"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    origen: Mapped[str] = mapped_column(String(10))
    estado: Mapped[str] = mapped_column(String(12), default="BORRADOR", index=True)
    paso: Mapped[int] = mapped_column(Integer, default=0)  # paso del asistente donde quedó
    parametros: Mapped[dict] = mapped_column(JSON, default=dict)
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)  # de la última validación o generación
    total: Mapped[int] = mapped_column(Integer, default=0)  # etiquetas a generar
    progreso: Mapped[int] = mapped_column(Integer, default=0)  # etiquetas dibujadas (generación en segundo plano)
    error: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)  # control de concurrencia
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    validado_en: Mapped[datetime | None] = mapped_column(DateTime)
    generado_en: Mapped[datetime | None] = mapped_column(DateTime)
    # Ejecución en segundo plano (trabajos.py): quién la tiene tomada y hasta cuándo.
    # Otro proceso solo la toma cuando el arriendo venció (el que la tenía se detuvo)
    ejecutor: Mapped[str | None] = mapped_column(String(80))
    arriendo_hasta: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    latido_en: Mapped[datetime | None] = mapped_column(DateTime)
    intentos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    registros: Mapped[list["TrabajoRegistro"]] = relationship(
        back_populates="trabajo", cascade="all, delete-orphan", order_by="TrabajoRegistro.orden")


class TrabajoRegistro(DeOrganizacion, Base):
    """Un registro validado del trabajo: un grupo de etiquetas iguales salvo su
    número (una línea, un artículo, un bulto…) con el diseño y la regla
    elegidos, sus problemas y, ya generado, la ejecución que lo produjo."""

    __tablename__ = "trabajo_etiqueta_registros"
    __table_args__ = (UniqueConstraint("trabajo_id", "clave", name="uq_trabajo_etiqueta_registros_trabajo_clave"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    trabajo_id: Mapped[int] = mapped_column(ForeignKey("trabajos_etiqueta.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)
    clave: Mapped[str] = mapped_column(String(80))
    referencia: Mapped[str | None] = mapped_column(String(160))
    oc_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    posicion_id: Mapped[int | None] = mapped_column(ForeignKey("posiciones_oc.id"), index=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    pl_id: Mapped[int | None] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    plantilla_id: Mapped[int | None] = mapped_column(ForeignKey("plantillas_etiqueta.id"), index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_plantilla.id"), index=True)
    tipo_etiqueta_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_etiqueta.id"), index=True)
    uso_id: Mapped[int | None] = mapped_column(ForeignKey("usos_diseno.id", ondelete="SET NULL"), index=True)
    cantidad: Mapped[int] = mapped_column(Integer, default=0)
    estado: Mapped[str] = mapped_column(String(12), default="LISTO", index=True)
    problemas: Mapped[list] = mapped_column(JSON, default=list)
    motivo: Mapped[str | None] = mapped_column(String(300))
    # Lo que se revisó: valores que lee su diseño, versión y cantidad (para avisar si cambian antes de generar)
    revisado: Mapped[dict | None] = mapped_column(JSON)
    generacion_id: Mapped[int | None] = mapped_column(ForeignKey("generaciones_etiqueta.id", ondelete="SET NULL"), index=True)

    trabajo: Mapped[TrabajoEtiquetas] = relationship(back_populates="registros")


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
        CheckConstraint("(anulada_en IS NULL) = (motivo_anulacion IS NULL)", name="ck_generaciones_etiqueta_anulada"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    oc_id: Mapped[int | None] = mapped_column(ForeignKey("ordenes_compra.id"), index=True)
    pl_id: Mapped[int | None] = mapped_column(ForeignKey("packing_lists.id"), index=True)  # generada desde una lista de empaque
    # Generación masiva: los lotes hechos juntos (una OC por lote) comparten este código
    lote: Mapped[str | None] = mapped_column(String(36), index=True)
    formato: Mapped[str] = mapped_column(String(4))
    estado: Mapped[str] = mapped_column(String(10), default="GENERADA", index=True)  # PRUEBA: con versiones sin aprobar
    total: Mapped[int] = mapped_column(Integer, default=0)
    parametros: Mapped[dict] = mapped_column(JSON, default=dict)  # hoja, cantidades manuales, selección
    advertencias: Mapped[list] = mapped_column(JSON, default=list)  # las aceptadas al confirmar
    archivo: Mapped[str | None] = mapped_column(String(200))  # nombre del archivo producido
    sha256: Mapped[str | None] = mapped_column(String(64))
    creada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, index=True)
    # Ejecución de un trabajo; generado ≠ descargado ≠ impreso (este, solo con confirmación expresa)
    trabajo_id: Mapped[int | None] = mapped_column(ForeignKey("trabajos_etiqueta.id"), index=True)
    descargas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    descargada_en: Mapped[datetime | None] = mapped_column(DateTime)
    impresa_en: Mapped[datetime | None] = mapped_column(DateTime)
    impresa_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    impresion: Mapped[dict | None] = mapped_column(JSON)  # {cantidad, impresora, observacion}
    # Anulada (con motivo): no se descarga ni se imprime; sus registros del trabajo vuelven a quedar pendientes
    anulada_en: Mapped[datetime | None] = mapped_column(DateTime)
    anulada_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    motivo_anulacion: Mapped[str | None] = mapped_column(String(300))
    # Copias idénticas pedidas después: [{n, en, por, motivo, formato, total, seleccion}]
    reimpresiones: Mapped[list | None] = mapped_column(JSON)

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
    tipo_etiqueta_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_etiqueta.id"), index=True)
    articulo_id: Mapped[int | None] = mapped_column(ForeignKey("articulos.id"), index=True)
    # Identidad estable del bulto (lista de empaque, grupo de cajas y unidad dentro del grupo)
    pl_id: Mapped[int | None] = mapped_column(ForeignKey("packing_lists.id"), index=True)
    grupo_cajas_id: Mapped[int | None] = mapped_column(ForeignKey("grupos_cajas.id", ondelete="SET NULL"), index=True)
    bulto_indice: Mapped[int | None] = mapped_column(Integer)
    posicion_id: Mapped[int | None] = mapped_column(ForeignKey("posiciones_oc.id"), index=True)
    familia_id: Mapped[int | None] = mapped_column(ForeignKey("familias_etiquetado.id"), index=True)
    referencia: Mapped[str | None] = mapped_column(String(120))  # lo que se lee en el historial (SKU, línea, bulto)
    cantidad: Mapped[int] = mapped_column(Integer)
    valores: Mapped[dict] = mapped_column(JSON, default=dict)  # instantánea: campo → valor
    motivo: Mapped[str | None] = mapped_column(String(200))  # por qué se eligió esa plantilla
    # El registro del trabajo que produjo este grupo: único, así un registro nunca se genera dos veces
    trabajo_registro_id: Mapped[int | None] = mapped_column(
        ForeignKey("trabajo_etiqueta_registros.id", ondelete="SET NULL"), unique=True)

    generacion: Mapped[GeneracionEtiquetas] = relationship(back_populates="items")
