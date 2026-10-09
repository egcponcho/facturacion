"""Capa oficial del arancel: países, fuentes, versiones, notas, códigos nacionales y reglas.
"""
from datetime import date

from pydantic import BaseModel, Field


class CapitulosPatch(BaseModel):
    ids: list[int] = Field(min_length=1)
    activo: bool | None = None
    clasificacion: bool | None = None
    candidato_auto: bool | None = None
    solo_manual: bool | None = None
    archivado: bool | None = None


class AtributoIn(BaseModel):
    # Una parte de la composición es comp.<parte>
    codigo: str | None = Field(None, max_length=40, pattern=r"^(comp\.)?[A-Za-z][A-Za-z0-9_]*$")
    etiqueta: str | None = Field(None, max_length=200)
    tipo_dato: str | None = None
    unidad: str | None = Field(None, max_length=10)
    dominio: str | None = Field(None, max_length=30)
    descripcion: str | None = Field(None, max_length=400)
    activo: bool | None = None
    usado_clasificacion: bool | None = None
    orden: int | None = None
    # Comportamiento (validado en el servidor: ver modulos/clasificacion/validacion_config.py)
    seccion: str | None = None
    informativo: bool | None = None
    valor_defecto: str | None = Field(None, max_length=60)
    control: str | None = Field(None, max_length=12)
    alias: list[str] | None = None
    derivacion: dict | None = None
    bloqueo: list | None = None
    patrones: list | None = None
    patrones_falso: list | None = None
    texto_aduana: dict | list | None = None


class SinonimoBusquedaIn(BaseModel):
    palabra: str | None = Field(None, max_length=60)
    equivale: str | None = Field(None, max_length=300)
    activo: bool | None = None


class ConfirmarPartidaIn(BaseModel):
    codigo: str = Field(max_length=20)


class ClaseMaterialIn(BaseModel):
    codigo: str | None = Field(None, max_length=30)
    nombre: str | None = Field(None, max_length=80)
    palabras: str | None = Field(None, max_length=1000)  # palabras o patrones simples, separadas por espacio o coma
    texto_aduana: str | None = Field(None, max_length=60)
    activo: bool | None = None


class AtributoOpcionIn(BaseModel):
    codigo: str | None = Field(None, max_length=60)
    etiqueta: str | None = Field(None, max_length=300)
    alias: str | None = Field(None, max_length=400)
    terminos: str | None = Field(None, max_length=400)  # palabras del texto oficial (solo ordenan candidatos)
    orden: int | None = None
    activo: bool | None = None
    bloqueo: list | None = None  # [{condiciones, mensaje}]: cuándo no se puede elegir
    implica: dict | None = None  # {atributo: valor}: lo que completa al elegirla
    patrones: list | None = None  # cómo se reconoce en el nombre, el uso o la composición
    texto_aduana: dict | list | None = None  # frase, nombre o nombre comercial en la descripción aduanera


class AtributoAmbitoIn(BaseModel):
    condicion: list | None = None  # [{campo, operador, valor, grupo}] — dependencia: solo se pregunta si se cumple
    tipo_ambito: str | None = None
    codigo_ambito: str | None = Field(None, max_length=40)
    modo: str | None = None
    prioridad: int | None = Field(None, ge=0, le=10000)
    nota: str | None = Field(None, max_length=300)
    activo: bool | None = None
    quitar: bool = False


class RegulacionIn(BaseModel):
    codigo: str | None = Field(None, max_length=40)
    pais: str | None = Field(None, max_length=2)
    patron: str | None = Field(None, max_length=40)
    tipo: str | None = Field(None, max_length=30)
    nombre: str | None = Field(None, max_length=300)
    autoridad: str | None = Field(None, max_length=200)
    codigo_permiso: str | None = Field(None, max_length=60)
    obligatorio: bool | None = None
    base_legal: str | None = Field(None, max_length=400)
    activo: bool | None = None
    url: str | None = Field(None, max_length=300)
    nota: str | None = Field(None, max_length=400)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None


class ImpuestoIn(BaseModel):
    codigo: str | None = Field(None, max_length=40)
    pais: str | None = Field(None, max_length=2)
    patron: str | None = Field(None, max_length=40)
    tipo: str | None = Field(None, max_length=20)
    tasa: float | None = Field(None, ge=0, le=1000)
    base_calculo: str | None = Field(None, max_length=80)
    umbral_desde: float | None = None
    umbral_hasta: float | None = None
    formula: str | None = Field(None, max_length=300)
    base_legal: str | None = Field(None, max_length=400)
    activo: bool | None = None
    url: str | None = Field(None, max_length=300)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None


class CondicionIn(BaseModel):
    grupo: int = Field(1, ge=1, le=20)
    campo: str = Field(max_length=60)
    operador: str = "EQUAL"
    valor: str | int | float | bool | list | None = None
    valor_hasta: str | int | float | None = None
    negado: bool = False


class ReglaIn(BaseModel):
    tipo_ambito: str | None = Field(None, max_length=14)
    codigo_ambito: str | None = Field(None, max_length=40)
    tipo_regla: str | None = Field(None, max_length=20)
    familia: str | None = Field(None, max_length=30)
    accion: dict | None = None
    prioridad: int | None = Field(None, ge=0, le=10000)
    efecto: str | None = Field(None, max_length=500)
    activo: bool | None = None
    requiere_revision: bool | None = None
    condiciones: list[CondicionIn] | None = None
    tipo_fuente: str | None = Field(None, pattern="^(MANUAL|LEGAL_NOTE)$")
    nota_id: int | None = None


class DominioIn(BaseModel):
    codigo: str | None = Field(None, max_length=30)
    nombre: str | None = Field(None, max_length=100)
    descripcion: str | None = Field(None, max_length=400)
    modo: str | None = Field(None, max_length=10)
    activo: bool | None = None
    orden: int | None = None


class CategoriaIn(BaseModel):
    codigo: str | None = Field(None, max_length=40)
    nombre: str | None = Field(None, max_length=120)
    grupo: str | None = Field(None, max_length=80)
    dominio: str | None = Field(None, max_length=30)
    alias: str | None = Field(None, max_length=400)
    orden: int | None = None
    activo: bool | None = None
    familia: str | None = Field(None, max_length=30)
    nombre_corto: str | None = Field(None, max_length=80)
    nombre_aduana: str | None = Field(None, max_length=120)
    patrones: list[dict] | None = None  # [{re, prioridad}] para reconocerla en el nombre
    capitulos: list[str] | None = None  # capítulos compatibles
    plantilla_aduana: dict | None = None
    terminos: str | None = Field(None, max_length=400)  # palabras del texto oficial (solo ordenan candidatos)


class DominioCapituloIn(BaseModel):
    relevancia: str | None = None
    habilitado: bool | None = None
    quitar: bool = False


class VerificarFuenteIn(BaseModel):
    documento: str | None = Field(None, max_length=300)  # documento o dataset oficial exacto que se revisó
    url: str | None = Field(None, max_length=400)
    verificado_en: date | None = None
