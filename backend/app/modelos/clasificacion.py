"""Clasificación arancelaria: arancel oficial versionado, capa nacional,
configuración del motor (dominios, categorías, atributos, reglas) y
conocimiento de la empresa.
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
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.modelos.base import ahora

if TYPE_CHECKING:
    from app.modelos.acceso import Usuario


class PaisArancel(Base):
    """País destino con arancel propio: cuántos dígitos usa su código nacional
    y si pertenece al Mercado Común Centroamericano (comparte el SAC a 8-10
    dígitos). Se pueden agregar países y cargar sus códigos."""

    __tablename__ = "paises_arancel"
    id: Mapped[int] = mapped_column(primary_key=True)
    iso: Mapped[str] = mapped_column(String(2), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    digitos: Mapped[int] = mapped_column(Integer, default=10)  # longitud habitual (sugerencia, no regla fija)
    # Esquema del código nacional: longitudes admitidas (p. ej. "8,10,12"); vacío = 8 a 14 dígitos
    longitudes: Mapped[str | None] = mapped_column(String(40))
    nivel_base: Mapped[str | None] = mapped_column(String(10))  # HS6 | SAC8: de qué nivel cuelga la precisión nacional; SAC10: el código nacional es la línea regional del SAC
    modelo_arancel: Mapped[str | None] = mapped_column(String(120))  # SAC regional + precisión nacional, nacional propio…
    contexto: Mapped[str | None] = mapped_column(String(120))
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    mcca: Mapped[bool] = mapped_column(Boolean, default=False)
    impuesto: Mapped[str | None] = mapped_column(String(60))  # p. ej. "VAT 13%"
    nota: Mapped[str | None] = mapped_column(String(300))
    base_legal: Mapped[str | None] = mapped_column(String(300))  # arancel y norma que lo pone en vigor
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Fuentes por tipo de dato (hoja Country_Source_Map): códigos = fuente_id
    fuente_regulaciones_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id", name="fk_paises_fuente_reg"))
    fuente_impuestos_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id", name="fk_paises_fuente_imp"))
    ingesta: Mapped[str | None] = mapped_column(String(120))  # conector, API, PDF…
    autenticacion_fuente: Mapped[str | None] = mapped_column(String(40))
    estado_fuente: Mapped[str | None] = mapped_column(String(200))

    def longitudes_validas(self) -> list[int]:
        """Longitudes admitidas del código nacional. Sin esquema configurado se
        acepta la precisión nacional de 8 a 14 dígitos (no se fija un número)."""
        lista = [int(x) for x in (self.longitudes or "").split(",") if x.strip().isdigit()]
        return lista or list(range(8, 15))

    def error_longitud(self, codigo: str) -> str | None:
        n = len(codigo)
        if n in self.longitudes_validas():
            return None
        if self.longitudes:
            return f"{self.nombre} accepts national codes of {self.longitudes.replace(',', ', ')} digits; you entered {n}."
        return f"National codes have 8 to 14 digits; you entered {n}."


class FuenteOficial(Base):
    """Fuente oficial de datos arancelarios (SIECA, SAT, DGA, ATENA, ANA…):
    de dónde sale cada dato, cómo se consulta y cuándo se verificó."""

    __tablename__ = "fuentes_oficiales"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)  # SRC-SIECA-ACI
    ambito: Mapped[str] = mapped_column(String(20))  # Regional | GT | SV | … | International
    autoridad: Mapped[str] = mapped_column(String(150))
    dataset: Mapped[str] = mapped_column(String(200))
    uso: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(400))
    acceso: Mapped[str | None] = mapped_column(String(60))  # PDF público, aplicación web, API…
    autenticacion: Mapped[str | None] = mapped_column(String(60))
    nota_version: Mapped[str | None] = mapped_column(String(300))
    verificacion: Mapped[str | None] = mapped_column(String(120))
    # Trazabilidad: el documento o dataset oficial exacto y quién y cuándo lo verificó
    # contra la publicación. Sin verificación la fuente no respalda ningún dato oficial.
    documento: Mapped[str | None] = mapped_column(String(300))
    verificado_en: Mapped[date | None] = mapped_column(Date)
    verificado_por: Mapped[str | None] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class VersionDataset(Base):
    """Versión (instantánea) de un conjunto de datos oficial: el SAC regional,
    el arancel nacional de un país, sus regulaciones… Lo publicado no se
    sobrescribe: una actualización crea otra versión."""

    __tablename__ = "versiones_dataset"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)  # SAC-2025-V6
    dataset: Mapped[str] = mapped_column(String(120))
    etiqueta: Mapped[str] = mapped_column(String(200))
    estado: Mapped[str] = mapped_column(String(12), default="BORRADOR")  # BORRADOR | PUBLICADA | DINAMICA | ARCHIVADA
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    checksum: Mapped[str | None] = mapped_column(String(64))
    nota: Mapped[str | None] = mapped_column(String(400))
    importado_en: Mapped[datetime | None] = mapped_column(DateTime)
    # De qué arancel es: REGIONAL (SAC) o el ISO del país. El motor elige la
    # versión vigente de cada ámbito por estado y fechas (resolver_version_vigente)
    ambito: Mapped[str | None] = mapped_column(String(10), index=True)

    fuente: Mapped[FuenteOficial | None] = relationship()


class ControlCapitulo(Base):
    """Qué capítulos del SAC usa el clasificador: activos, habilitados para
    clasificar, si generan candidatos automáticos o solo se eligen a mano."""

    __tablename__ = "control_capitulos"
    id: Mapped[int] = mapped_column(primary_key=True)
    capitulo: Mapped[str] = mapped_column(String(2), unique=True)
    seccion: Mapped[str | None] = mapped_column(String(6))
    titulo: Mapped[str] = mapped_column(String(400))
    activo: Mapped[bool] = mapped_column(Boolean, default=False)
    clasificacion: Mapped[bool] = mapped_column(Boolean, default=False)  # habilitado para clasificar
    candidato_auto: Mapped[bool] = mapped_column(Boolean, default=False)
    solo_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    archivado: Mapped[bool] = mapped_column(Boolean, default=False)
    alcance: Mapped[str | None] = mapped_column(String(200))  # dominios iniciales (texto de referencia)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id"))
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    nota: Mapped[str | None] = mapped_column(String(300))

    version: Mapped[VersionDataset | None] = relationship()


class DominioClasificacion(Base):
    """Familia comercial (químicos, materias primas, calzado, ropa,
    accesorios…). Ayuda a elegir preguntas y candidatos; nunca obliga ni
    excluye un capítulo por sí sola."""

    __tablename__ = "dominios_clasificacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(400))
    modo: Mapped[str] = mapped_column(String(10), default="AUTO")  # AUTO | MANUAL
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # BORRADOR: se arma y se prueba sin que la ficha la ofrezca ni toque artículos reales; PUBLICADA: en uso
    estado: Mapped[str] = mapped_column(String(10), default="PUBLICADA", server_default="PUBLICADA")

    capitulos: Mapped[list["DominioCapitulo"]] = relationship(back_populates="dominio", cascade="all, delete-orphan")


class CategoriaProducto(Base):
    """Categoría inicial de la ficha («¿Qué es el producto?»): sale de la
    configuración, no del código. Cada una pertenece a un dominio; todas usan
    la misma ficha dinámica (atributos, ámbitos y reglas del motor único)."""

    __tablename__ = "categorias_producto"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    grupo: Mapped[str | None] = mapped_column(String(80))  # encabezado en la lista
    dominio: Mapped[str | None] = mapped_column(String(30), index=True)  # código de DominioClasificacion
    alias: Mapped[str | None] = mapped_column(String(400))  # palabras para buscarla, separadas por ;
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Familia de producto (prenda, calzado…), nombre corto, nombre para la
    # descripción aduanera, patrones para reconocerla en el nombre del estilo
    # y capítulos compatibles (un código de otro capítulo se marca como error)
    familia: Mapped[str | None] = mapped_column(String(30))
    nombre_corto: Mapped[str | None] = mapped_column(String(80))
    nombre_aduana: Mapped[str | None] = mapped_column(String(120))
    patrones: Mapped[list | None] = mapped_column(JSON)
    capitulos: Mapped[list | None] = mapped_column(JSON)
    # Cómo se arma su descripción aduanera: {material, requiere, si_falta, como, si}
    plantilla_aduana: Mapped[dict | None] = mapped_column(JSON)
    # Palabras del texto oficial del arancel que suele usar la categoría (p. ej.
    # «hilados»): solo ordenan candidatos del árbol, nunca fijan un código
    terminos: Mapped[str | None] = mapped_column(String(400))


class DominioCapitulo(Base):
    """Capítulo relacionado con un dominio: PRIMARY genera candidatos
    automáticos; SECONDARY queda disponible si los datos lo justifican."""

    __tablename__ = "dominio_capitulos"
    __table_args__ = (UniqueConstraint("dominio_id", "capitulo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    dominio_id: Mapped[int] = mapped_column(ForeignKey("dominios_clasificacion.id", ondelete="CASCADE"), index=True)
    capitulo: Mapped[str] = mapped_column(String(2))
    relevancia: Mapped[str] = mapped_column(String(10), default="PRIMARY")  # PRIMARY | SECONDARY
    habilitado: Mapped[bool] = mapped_column(Boolean, default=True)
    proposito: Mapped[str | None] = mapped_column(String(300))

    dominio: Mapped[DominioClasificacion] = relationship(back_populates="capitulos")


class NodoArancel(Base):
    """Nodo del árbol arancelario oficial de una versión: capítulo (2), partida
    (4), subpartida (6) e inciso SAC (8-10) o nacional. Datos oficiales
    solamente: las condiciones del producto viven en las reglas del motor.
    Lo publicado no se borra; una nueva versión del arancel trae otro árbol."""

    __tablename__ = "nodos_arancel"
    __table_args__ = (UniqueConstraint("version_id", "pais", "codigo_norm"),
                      Index("ix_nodos_arancel_version_padre", "version_id", "padre_id"))
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("versiones_dataset.id"), index=True)
    nomenclatura: Mapped[str] = mapped_column(String(10), default="SAC")  # SAC | HS | NACIONAL
    pais: Mapped[str | None] = mapped_column(String(2))  # vacío = regional
    nivel: Mapped[str] = mapped_column(String(12))  # CAPITULO | PARTIDA | SUBPARTIDA | INCISO
    codigo: Mapped[str] = mapped_column(String(20))  # como se muestra: 6404.19.90.00
    codigo_norm: Mapped[str] = mapped_column(String(16), index=True)  # solo dígitos
    padre_id: Mapped[int | None] = mapped_column(ForeignKey("nodos_arancel.id"))
    descripcion: Mapped[str] = mapped_column(Text)  # texto oficial completo
    texto_propio: Mapped[str | None] = mapped_column(String(400))  # solo el renglón de este nivel
    dai: Mapped[str | None] = mapped_column(String(12))
    hojas: Mapped[int] = mapped_column(Integer, default=0)  # hijos directos (para el árbol)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    estado: Mapped[str] = mapped_column(String(12), default="PUBLICADO")
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    nota: Mapped[str | None] = mapped_column(String(300))


class AtributoDef(Base):
    """Atributo de la ficha técnica que el motor puede preguntar. OFICIAL viene
    del paquete del motor dinámico (genérico por dominio); MOTOR son los
    atributos de la ficha de ropa, calzado y accesorios; USUARIO, los creados a
    mano. Solo con datos se agregan preguntas: no hace falta tocar el código."""

    __tablename__ = "atributos_def"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    etiqueta: Mapped[str] = mapped_column(String(200))
    tipo_dato: Mapped[str] = mapped_column(String(20), default="text")  # text | select | multi_select | boolean | number | composition | country | measurement_set
    unidad: Mapped[str | None] = mapped_column(String(10))
    multiple: Mapped[bool] = mapped_column(Boolean, default=False)
    usado_clasificacion: Mapped[bool] = mapped_column(Boolean, default=True)
    dominio: Mapped[str | None] = mapped_column(String(30))  # CORE o código de dominio (pista, no restricción)
    descripcion: Mapped[str | None] = mapped_column(String(400))
    # De dónde sale la definición (todas son configuración del motor, ninguna es dato oficial):
    # PAQUETE (paquete 02 del motor) | MOTOR (ficha y categorías técnicas incluidas) | USUARIO
    origen: Mapped[str] = mapped_column(String(10), default="PAQUETE")
    de_composicion: Mapped[bool] = mapped_column(Boolean, default=False)  # se deduce de la composición
    informativo: Mapped[bool] = mapped_column(Boolean, default=False)  # no cambia el código, solo describe
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id"))
    # Comportamiento en la ficha, como datos (app/modulos/productos/ficha.py):
    # sección (producto | caracteristicas | composicion | nacional | derivado),
    # valor por defecto, derivación (lo que fija la composición, una constante
    # u otro atributo), bloqueos de la casilla [{condiciones, mensaje}],
    # patrones de detección por texto y control preferido (lista, botones)
    seccion: Mapped[str] = mapped_column(String(16), default="caracteristicas")
    valor_defecto: Mapped[str | None] = mapped_column(String(60))
    derivacion: Mapped[dict | None] = mapped_column(JSON)
    bloqueo: Mapped[list | None] = mapped_column(JSON)
    patrones: Mapped[list | None] = mapped_column(JSON)
    patrones_falso: Mapped[list | None] = mapped_column(JSON)
    control: Mapped[str | None] = mapped_column(String(12))
    # En la descripción aduanera (casillas): {frase, nombre, comercial, orden, cuando}
    texto_aduana: Mapped[dict | None] = mapped_column(JSON)
    # Otros códigos con los que llega el mismo atributo (otro paquete, una SDS, una carga): se resuelven a este
    alias: Mapped[list | None] = mapped_column(JSON)

    opciones: Mapped[list["AtributoOpcion"]] = relationship(back_populates="atributo", cascade="all, delete-orphan",
                                                           order_by="AtributoOpcion.orden")
    ambitos: Mapped[list["AtributoAmbito"]] = relationship(back_populates="atributo", cascade="all, delete-orphan")


class AtributoOpcion(Base):
    """Valor posible de un atributo de selección, con sinónimos para leerlo
    desde el texto del proveedor. Desactivar una opción no borra las fichas
    guardadas: la ficha avisa y la quita cuando se vuelve a editar."""

    __tablename__ = "atributo_opciones"
    __table_args__ = (UniqueConstraint("atributo_id", "codigo"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    atributo_id: Mapped[int] = mapped_column(ForeignKey("atributos_def.id", ondelete="CASCADE"), index=True)
    codigo: Mapped[str] = mapped_column(String(60))
    etiqueta: Mapped[str] = mapped_column(String(300))
    alias: Mapped[str | None] = mapped_column(String(400))  # separados por ;
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Combinaciones imposibles [{condiciones, mensaje}], respuestas que completa
    # al elegirla {atributo: valor} y patrones para detectarla en el texto
    bloqueo: Mapped[list | None] = mapped_column(JSON)
    implica: Mapped[dict | None] = mapped_column(JSON)
    patrones: Mapped[list | None] = mapped_column(JSON)
    # En la descripción aduanera: {nombre, comercial, frase, orden, cuando}
    texto_aduana: Mapped[dict | None] = mapped_column(JSON)
    # Palabras del texto oficial del arancel que suele usar esta opción: solo
    # ordenan los candidatos del árbol (nunca fijan un código)
    terminos: Mapped[str | None] = mapped_column(String(400))

    atributo: Mapped[AtributoDef] = relationship(back_populates="opciones")


class AtributoAmbito(Base):
    """Dónde aparece un atributo: en todo el sistema, en un dominio, un
    capítulo/partida/subpartida o una categoría de producto, con modo
    SHOW (preguntar), REQUIRE (obligatorio) o HIDE (no preguntar) y, si hace
    falta, las respuestas que lo activan (lista de alternativas {atributo: valor})."""

    __tablename__ = "atributo_ambitos"
    __table_args__ = (UniqueConstraint("atributo_id", "tipo_ambito", "codigo_ambito"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    atributo_id: Mapped[int] = mapped_column(ForeignKey("atributos_def.id", ondelete="CASCADE"), index=True)
    tipo_ambito: Mapped[str] = mapped_column(String(12))  # SYSTEM | DOMAIN | CHAPTER | HEADING | SUBHEADING | CATEGORY
    codigo_ambito: Mapped[str] = mapped_column(String(40))  # ALL, CHEMICALS, 64, 6404, calzado…
    modo: Mapped[str] = mapped_column(String(8), default="SHOW")  # SHOW | REQUIRE | HIDE
    prioridad: Mapped[int] = mapped_column(Integer, default=500)
    condicion: Mapped[list | None] = mapped_column(JSON)  # [{atributo: valor}, …] cualquiera activa
    nota: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    atributo: Mapped[AtributoDef] = relationship(back_populates="ambitos")


class NotaSAC(Base):
    """Nota legal del SAC (Reglas Generales, notas de sección, de capítulo o de
    subpartida) que se tiene en cuenta al clasificar. `capitulos` dice a qué
    capítulos aplica (vacío: a todos) y `claves` qué datos de la ficha toca."""

    __tablename__ = "notas_sac"
    id: Mapped[int] = mapped_column(primary_key=True)
    ambito: Mapped[str] = mapped_column(String(16))  # reglas | seccion | capitulo | subpartida | complementaria
    codigo: Mapped[str] = mapped_column(String(10))  # RGI, XI, 64…
    numero: Mapped[str] = mapped_column(String(20))
    texto: Mapped[str] = mapped_column(Text)
    capitulos: Mapped[list] = mapped_column(JSON, default=list)
    claves: Mapped[list] = mapped_column(JSON, default=list)
    # Qué es el texto: solo los OFFICIAL_* son texto legal publicado (con fuente y
    # versión); la guía del clasificador y la interna son ayudas, nunca ley
    tipo_fuente: Mapped[str] = mapped_column(String(24), default="INTERNAL_GUIDANCE")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    TIPOS = {"OFFICIAL_LEGAL": "Official legal text", "OFFICIAL_TARIFF": "Official tariff text",
             "OFFICIAL_NATIONAL": "Official national text", "CLASSIFIER_GUIDANCE": "Classifier guidance (summary, not the legal text)",
             "INTERNAL_GUIDANCE": "Internal guidance (company)", "COMPANY_HISTORY": "Company history"}
    OFICIALES = ("OFFICIAL_LEGAL", "OFFICIAL_TARIFF", "OFFICIAL_NATIONAL")

    @property
    def oficial(self) -> bool:
        return self.tipo_fuente in self.OFICIALES

    # Nota oficial versionada: de qué versión y fuente sale y su vigencia (no se edita; se le pone un override)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id", name="fk_notas_version"))
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id", name="fk_notas_fuente"))
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)


class OverrideArancel(Base):
    """Capa CUSTOM encima del dato oficial: nunca se toca el oficial. Guarda el
    valor propio (descripción interna, nota, texto de una nota, activa o no)
    con su motivo, quién, cuándo y vigencia. Un cambio nuevo del mismo campo
    deja el anterior en el historial (inactivo); quitar el override vuelve al
    texto oficial."""

    __tablename__ = "overrides_arancel"
    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10))  # NODO | NOTA | INCISO
    objetivo: Mapped[str] = mapped_column(String(40), index=True)  # código del nodo, id de la nota…
    campo: Mapped[str] = mapped_column(String(30))  # descripcion | nota | texto | activo
    valor: Mapped[str | None] = mapped_column(Text)
    valor_oficial: Mapped[str | None] = mapped_column(Text)  # lo que decía el oficial al crear el override
    motivo: Mapped[str] = mapped_column(String(300))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    usuario: Mapped["Usuario | None"] = relationship()


class IncisoNacional(Base):
    """Línea arancelaria nacional OFICIAL de un país (capa OFFICIAL TARIFF DATA):
    existe solo porque una fuente oficial la publicó, con su fuente, versión y
    vigencia. Lo que la empresa aprende de ella va a HistorialClasificacion; las
    condiciones que la eligen son reglas del motor (NATIONAL_SELECT)."""

    __tablename__ = "incisos_nacionales"
    id: Mapped[int] = mapped_column(primary_key=True)
    pais: Mapped[str] = mapped_column(String(2), index=True)
    codigo: Mapped[str] = mapped_column(String(14))
    sub6: Mapped[str] = mapped_column(String(6), index=True)
    dai: Mapped[str | None] = mapped_column(String(10))
    descripcion: Mapped[str | None] = mapped_column(String(300))
    nota: Mapped[str | None] = mapped_column(String(300))
    fuente: Mapped[str] = mapped_column(String(12), default="oficial")  # solo oficial: tiene fuente y versión
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    # Dato oficial (paquete 03): versión, fuente, vigencia y código base SAC/HS del que cuelga
    codigo_oficial: Mapped[str | None] = mapped_column(String(30))  # ID de la fuente (National code ID)
    codigo_base: Mapped[str | None] = mapped_column(String(14))
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id", name="fk_incisos_version"))
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id", name="fk_incisos_fuente"))
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str | None] = mapped_column(String(300))

    # Las condiciones que eligen este código ya no viven en el código oficial:
    # son una regla de selección nacional (ReglaClasificacion NATIONAL_SELECT).
    regla: Mapped["ReglaClasificacion | None"] = relationship(back_populates="inciso", uselist=False, lazy="selectin",
                                                               cascade="all, delete-orphan")

    @property
    def cond(self) -> dict:
        """Condiciones de la regla de selección, en el formato del motor."""
        return self.regla.cond() if self.regla else {}

    @cond.setter
    def cond(self, valor: dict | None) -> None:
        self._regla_nacional().poner_cond(valor or {})
        self._limpiar_regla()

    @property
    def prio(self) -> int:
        return self.regla.prioridad if self.regla else 0

    @prio.setter
    def prio(self, valor: int | None) -> None:
        self._regla_nacional().prioridad = int(valor or 0)
        self._limpiar_regla()

    def _regla_nacional(self) -> "ReglaClasificacion":
        if not self.regla:
            self.regla = ReglaClasificacion.nacional(self)
        self.regla.pais, self.regla.codigo_ambito = self.pais, self.sub6 or ""
        return self.regla

    def _limpiar_regla(self) -> None:
        # Sin condiciones ni prioridad, el código se elige sin regla
        if self.regla and not self.regla.condiciones and not self.regla.prioridad:
            self.regla = None


class Regulacion(Base):
    """Requisito no arancelario de un país (permiso, licencia, registro,
    etiquetado…) para un código o patrón de códigos (p. ej. 3304*). Un código
    puede tener cero, uno o varios. Se publica con base legal y vigencia."""

    __tablename__ = "regulaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)  # Regulation ID
    pais: Mapped[str] = mapped_column(String(2), index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id"))
    tipo_ambito: Mapped[str] = mapped_column(String(14), default="PATTERN")  # NATIONAL_CODE | SUBHEADING | HEADING | CHAPTER | PATTERN
    patron: Mapped[str] = mapped_column(String(40))  # código o prefijo, * = todos
    tipo: Mapped[str] = mapped_column(String(30))  # PERMIT | LICENSE | REGISTRATION | CERTIFICATE | LABELING | SANITARY | PHYTOSANITARY | OTHER
    nombre: Mapped[str] = mapped_column(String(300))
    autoridad: Mapped[str | None] = mapped_column(String(200))
    codigo_permiso: Mapped[str | None] = mapped_column(String(60))
    obligatorio: Mapped[bool] = mapped_column(Boolean, default=True)
    condicion: Mapped[dict | None] = mapped_column(JSON)
    base_legal: Mapped[str | None] = mapped_column(String(400))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    url: Mapped[str | None] = mapped_column(String(300))
    nota: Mapped[str | None] = mapped_column(String(400))


class ReglaImpuesto(Base):
    """Impuesto de importación de un país (DAI, IVA, ITBMS, ISC…) para un
    código o patrón, con tasa, base de cálculo, umbrales, base legal y
    vigencia. El DAI de cada código nacional sigue en el código; aquí van los
    demás tributos y cualquier excepción."""

    __tablename__ = "reglas_impuesto"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)  # Tax rule ID
    pais: Mapped[str] = mapped_column(String(2), index=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id"))
    patron: Mapped[str] = mapped_column(String(40), default="*")
    tipo: Mapped[str] = mapped_column(String(20))  # DAI | IVA | ITBMS | ISV | ISC | SELECTIVO | OTRO
    tasa: Mapped[float | None] = mapped_column(Float)
    base_calculo: Mapped[str | None] = mapped_column(String(80))  # CIF, CIF + DAI…
    umbral_desde: Mapped[float | None] = mapped_column(Float)
    umbral_hasta: Mapped[float | None] = mapped_column(Float)
    formula: Mapped[str | None] = mapped_column(String(300))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
    vigente_hasta: Mapped[date | None] = mapped_column(Date)
    fuente_id: Mapped[int | None] = mapped_column(ForeignKey("fuentes_oficiales.id"))
    url: Mapped[str | None] = mapped_column(String(300))
    base_legal: Mapped[str | None] = mapped_column(String(400))


class ReglaClasificacion(Base):
    """Regla del motor de clasificación, en datos y no en código.

    Reglas del sistema (paquete 02: capítulos habilitados, prioridad legal,
    preguntas que discriminan, revisión por ambigüedad…) y reglas de selección
    nacional (NATIONAL_SELECT): las condiciones del producto que eligen un
    código nacional dentro de su subpartida. Las condiciones se agrupan: dentro
    de un grupo se cumplen todas (Y); entre grupos basta uno (O)."""

    __tablename__ = "reglas_clasificacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    tipo_ambito: Mapped[str] = mapped_column(String(14), default="SYSTEM")  # SYSTEM | DOMAIN | CHAPTER | HEADING | SUBHEADING | CATEGORY | NATIONAL_CODE
    codigo_ambito: Mapped[str] = mapped_column(String(40), default="ALL")
    pais: Mapped[str | None] = mapped_column(String(2), index=True)
    tipo_regla: Mapped[str] = mapped_column(String(20))  # HARD_CONSTRAINT | SOFT_SIGNAL | QUESTION_GATE | REVIEW_GATE | NATIONAL_SELECT
    prioridad: Mapped[int] = mapped_column(Integer, default=0)
    tipo_fuente: Mapped[str] = mapped_column(String(20), default="INTERNAL_ENGINE")  # INTERNAL_ENGINE | LEGAL_NOTE | NATIONAL_TARIFF | LEARNED | MANUAL
    familia: Mapped[str | None] = mapped_column(String(30))
    efecto: Mapped[str | None] = mapped_column(String(500))
    # Qué hace la regla cuando sus condiciones se cumplen (motor_clasificacion):
    # {"tipo": RESTRICT|EXCLUDE|BOOST|ASK|REVIEW, "codigos": [...], "peso": n,
    #  "atributos": [...], "mensaje": "..."}. Sin acción, las del motor base
    # gobiernan por familia (BUILTIN).
    accion: Mapped[dict | None] = mapped_column(JSON)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    requiere_revision: Mapped[bool] = mapped_column(Boolean, default=False)
    inciso_id: Mapped[int | None] = mapped_column(ForeignKey("incisos_nacionales.id", ondelete="CASCADE"), unique=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("versiones_dataset.id"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora, onupdate=ahora)
    # Revisión: sube con cada cambio; la evidencia de una clasificación guarda
    # la revisión y una foto de la regla tal como era al aplicarse
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Nota legal que la fundamenta (evidencia; la nota sola no ejecuta nada)
    nota_id: Mapped[int | None] = mapped_column(ForeignKey("notas_sac.id", ondelete="SET NULL", name="fk_reglas_nota"))

    inciso: Mapped[IncisoNacional | None] = relationship(back_populates="regla")
    condiciones: Mapped[list["CondicionRegla"]] = relationship(back_populates="regla", cascade="all, delete-orphan",
                                                               lazy="selectin", order_by="[CondicionRegla.grupo, CondicionRegla.id]")

    # Las condiciones que eligen una línea oficial son configuración propia
    # (MANUAL) salvo las que el clasificador lee del texto oficial, que su carga
    # marca CLASSIFIER (capa sistema): nunca son legales

    @classmethod
    def nacional(cls, x: IncisoNacional) -> "ReglaClasificacion":
        import secrets

        return cls(codigo=f"NAC-{secrets.token_hex(5).upper()}", tipo_ambito="NATIONAL_CODE", codigo_ambito=x.sub6 or "",
                   pais=x.pais, tipo_regla="NATIONAL_SELECT", tipo_fuente="MANUAL",
                   familia="NATIONAL_CODE", prioridad=0)

    def cond(self) -> dict:
        """Condiciones como las entiende el motor de la ficha:
        {atributo: valor | [valores] | sí/no, cifMax, cifMin}."""
        out: dict = {}
        for c in self.condiciones:
            if c.campo == "valorCIF":
                out["cifMax" if c.operador == "LTE" else "cifMin"] = c.valor
            else:
                out[c.campo] = c.valor
        return out

    def poner_cond(self, cond: dict) -> None:
        self.condiciones = [CondicionRegla.desde_cond(k, v) for k, v in cond.items() if v not in (None, "", [])]


class CondicionRegla(Base):
    """Condición de una regla: campo (atributo de la ficha o del sistema),
    operador y valor. Para la selección nacional los operadores son los que
    entiende el motor: EQUAL, IN y, para el valor CIF, LTE o GT."""

    __tablename__ = "reglas_condiciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    regla_id: Mapped[int] = mapped_column(ForeignKey("reglas_clasificacion.id", ondelete="CASCADE"), index=True)
    grupo: Mapped[int] = mapped_column(Integer, default=1)
    campo: Mapped[str] = mapped_column(String(60))
    operador: Mapped[str] = mapped_column(String(10), default="EQUAL")  # EQUAL | NOT_EQUAL | IN | GT | GTE | LT | LTE | BETWEEN | EXISTS
    valor: Mapped[object | None] = mapped_column(JSON)
    valor_hasta: Mapped[object | None] = mapped_column(JSON)
    negado: Mapped[bool] = mapped_column(Boolean, default=False)

    regla: Mapped[ReglaClasificacion] = relationship(back_populates="condiciones")

    @classmethod
    def desde_cond(cls, k: str, v) -> "CondicionRegla":
        if k in ("cifMax", "cifMin"):
            return cls(campo="valorCIF", operador="LTE" if k == "cifMax" else "GT", valor=v)
        return cls(campo=k, operador="IN" if isinstance(v, list) else "EQUAL", valor=v)


class PalabraClave(Base):
    """Frase del nombre del estilo que el clasificador aprendió a reconocer
    (p. ej. "old skool" es un tenis)."""

    __tablename__ = "clasif_palabras"
    id: Mapped[int] = mapped_column(primary_key=True)
    frase: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[str] = mapped_column(String(30))
    marca: Mapped[str | None] = mapped_column(String(100))
    atributos: Mapped[dict] = mapped_column(JSON, default=dict)
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class ClaseMaterial(Base):
    """Clase de material que reconoce la composición (cerámica, vidrio, metal…).
    Las de base vienen con el motor; aquí se agregan clases nuevas o más
    palabras para una que ya existe, y la palabra con la que va en la
    descripción aduanera. Una derivación de modo «clase» la lleva a las
    opciones de un atributo."""

    __tablename__ = "clases_material"
    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    palabras: Mapped[str | None] = mapped_column(String(1000))  # palabras o patrones simples (porcelanas?), separadas por espacio o coma
    texto_aduana: Mapped[str | None] = mapped_column(String(60))  # CERÁMICA, METAL…
    origen: Mapped[str] = mapped_column(String(10), default="USUARIO")  # MOTOR (de base) | USUARIO
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class SinonimoBusqueda(Base):
    """Palabra equivalente para buscar en el texto oficial del arancel (en
    español): un nombre en inglés u otro término comercial («drill» →
    «taladro», «mug» → «taza jarro»). Solo ayuda a encontrar candidatos;
    nunca confirma un código."""

    __tablename__ = "sinonimos_busqueda"
    id: Mapped[int] = mapped_column(primary_key=True)
    palabra: Mapped[str] = mapped_column(String(60), unique=True)
    equivale: Mapped[str] = mapped_column(String(300))  # palabras del texto oficial, separadas por espacio
    origen: Mapped[str] = mapped_column(String(10), default="USUARIO")  # MOTOR (de base) | USUARIO
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class TraduccionCatalogo(Base):
    """Traducción de un texto del catálogo (pregunta, opción, categoría,
    familia…) a un idioma de la interfaz. El texto en inglés es la clave, como
    en el resto de la interfaz: la ficha, las listas y los documentos en
    pantalla lo muestran en el idioma de cada usuario."""

    __tablename__ = "traducciones_catalogo"
    __table_args__ = (UniqueConstraint("texto", "idioma"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(String(400))
    idioma: Mapped[str] = mapped_column(String(5), index=True)
    traduccion: Mapped[str] = mapped_column(String(400))
    origen: Mapped[str] = mapped_column(String(10), default="USUARIO")  # MOTOR (de base) | USUARIO


class SinonimoMaterial(Base):
    """Palabra de composición que el clasificador aprendió (p. ej. "cordura" es nylon)."""

    __tablename__ = "clasif_sinonimos"
    id: Mapped[int] = mapped_column(primary_key=True)
    palabra: Mapped[str] = mapped_column(String(60), unique=True)
    equivale: Mapped[str] = mapped_column(String(30))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class HistorialClasificacion(Base):
    """Conocimiento de la empresa (capa COMPANY KNOWLEDGE): un código que la
    empresa usó, con los datos del producto que lo eligieron. Viene de
    clasificaciones aprobadas, correcciones de un especialista, lo que se
    enseñó desde la ficha o un historial importado. Solo ordena candidatos
    que el motor ya permite (historical_confidence): nunca crea un código, un
    DAI ni modifica un dato oficial, y el código debe existir en la capa oficial
    para poder usarse."""

    __tablename__ = "historial_clasificacion"
    id: Mapped[int] = mapped_column(primary_key=True)
    pais: Mapped[str | None] = mapped_column(String(2), index=True)  # vacío = HS6/SAC regional
    codigo: Mapped[str] = mapped_column(String(14), index=True)
    sub6: Mapped[str] = mapped_column(String(6), index=True)
    categoria: Mapped[str | None] = mapped_column(String(40))
    condiciones: Mapped[dict] = mapped_column(JSON, default=dict)  # hechos del producto que llevaron a este código
    origen: Mapped[str] = mapped_column(String(12))  # APROBACION | CORRECCION | ENSENADO | IMPORTADO
    conteo: Mapped[int] = mapped_column(Integer, default=1)  # productos o artículos que lo respaldan
    producto_id: Mapped[int | None] = mapped_column(ForeignKey("productos.id", ondelete="SET NULL"))
    nota: Mapped[str | None] = mapped_column(String(300))
    creado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)


class LoteOficial(Base):
    """Carga de un paquete oficial por etapas: se sube a una previa (staging),
    se revisan las diferencias contra lo vigente (nuevo, cambio, sin cambio,
    error, advertencia) y solo al publicar se aplica. Nunca borra lo publicado."""

    __tablename__ = "lotes_oficiales"
    id: Mapped[int] = mapped_column(primary_key=True)
    archivo: Mapped[str] = mapped_column(String(300))
    checksum: Mapped[str] = mapped_column(String(64))
    contenido: Mapped[bytes] = mapped_column(LargeBinary)
    estado: Mapped[str] = mapped_column(String(12), default="PREVIA")  # PREVIA | PUBLICADA | DESCARTADA
    resumen: Mapped[dict] = mapped_column(JSON, default=dict)  # por hoja: nuevos, cambios, sin_cambio, errores
    errores: Mapped[list] = mapped_column(JSON, default=list)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime)
    publicado_por: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id", name="fk_lotes_publicado_por"))

    filas: Mapped[list["FilaLoteOficial"]] = relationship(back_populates="lote", cascade="all, delete-orphan",
                                                          order_by="FilaLoteOficial.id")


class FilaLoteOficial(Base):
    """Diferencia de un registro en la previa: qué tabla y clave, la acción y
    los valores antes y después de los campos que cambian."""

    __tablename__ = "lotes_oficiales_filas"
    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes_oficiales.id", ondelete="CASCADE"), index=True)
    tabla: Mapped[str] = mapped_column(String(40))
    clave: Mapped[str] = mapped_column(String(120))
    accion: Mapped[str] = mapped_column(String(10))  # NUEVO | CAMBIO
    antes: Mapped[dict | None] = mapped_column(JSON)
    despues: Mapped[dict | None] = mapped_column(JSON)
    advertencia: Mapped[str | None] = mapped_column(String(300))

    lote: Mapped[LoteOficial] = relationship(back_populates="filas")


@event.listens_for(ReglaClasificacion, "before_insert")

@event.listens_for(ReglaClasificacion, "before_update")

def _regla_nacional_al_dia(_mapper, _conn, r: ReglaClasificacion) -> None:
    """La regla de selección nacional sigue al código que elige (país y
    subpartida), aunque se haya creado antes de llenarlos."""
    if r.tipo_regla == "NATIONAL_SELECT" and r.inciso is not None:
        r.pais, r.codigo_ambito = r.inciso.pais, r.inciso.sub6 or ""
