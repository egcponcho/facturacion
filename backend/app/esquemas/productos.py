"""Productos: ficha técnica, partidas, aprobación y configuración del motor de clasificación.
"""
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class FichaIn(BaseModel):
    version: int
    tipo: str | None = Field(None, max_length=30)
    ficha: dict = Field(default_factory=dict)
    nombre: str | None = Field(None, max_length=200)
    codigo_generico: str | None = Field(None, max_length=20)
    pais_origen: str | None = Field(None, max_length=2)
    pais_procedencia: str | None = Field(None, max_length=2)
    descripcion_aduana: str | None = Field(None, max_length=400)
    descripcion_comercial: str | None = Field(None, max_length=300)
    notas: str | None = Field(None, max_length=1000)
    alertas_ok: list[str] = Field(default_factory=list, max_length=100)
    tocados: list[str] = Field(default_factory=list, max_length=200)  # lo que eligió la persona (la detección no lo pisa)
    partidas: dict = Field(default_factory=dict)  # {iso: {codigo, manual}}: códigos nacionales escritos a mano


class ClasificarLote(BaseModel):
    """Clasificación masiva: el mismo motor del servidor, producto por producto."""
    ids: list[int] = Field(min_length=1, max_length=2000)


class AprobarIn(BaseModel):
    version: int
    codigo: str | None = Field(None, max_length=20)
    partidas: dict | None = None
    forzar: bool = False


class AprobarLote(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class ObservarIn(BaseModel):
    version: int
    observaciones: str | None = Field(None, max_length=2000)
    resolucion: str | None = Field(None, max_length=200)
    devolver: bool = False


class NuevaVersionIn(BaseModel):
    version: int
    desde: date | None = None
    motivo: str | None = Field(None, max_length=300)


class IncisoIn(BaseModel):
    pais: str = Field(max_length=2)
    codigo: str = Field(max_length=20)
    cond: dict = Field(default_factory=dict)
    dai: str | None = Field(None, max_length=10)
    nota: str | None = Field(None, max_length=300)


class PalabraIn(BaseModel):
    frase: str = Field(max_length=100)
    tipo: str = Field(max_length=30)
    marca: str | None = Field(None, max_length=100)
    atributos: dict = Field(default_factory=dict)


class SinonimoIn(BaseModel):
    palabra: str = Field(max_length=60)
    equivale: str = Field(max_length=30)


class AnalizarIn(BaseModel):
    """Opinión del especialista: el servidor arma la ficha con el motor único."""

    con_fotos: bool = True


class PaisArancelIn(BaseModel):
    iso: str = Field(max_length=2)
    nombre: str = Field(min_length=2, max_length=80)
    digitos: int = Field(ge=6, le=14)
    mcca: bool = False
    impuesto: str | None = Field(None, max_length=60)
    nota: str | None = Field(None, max_length=300)
    base_legal: str | None = Field(None, max_length=300)
    activo: bool = True
    # Esquema del arancel nacional: longitudes admitidas (p. ej. "10,12"), de qué nivel
    # cuelga la precisión nacional, modelo, contexto y fuente oficial
    longitudes: list[int] | None = None
    nivel_base: Literal["HS6", "SAC8", "SAC10"] | None = None
    modelo_arancel: str | None = Field(None, max_length=120)
    contexto: str | None = Field(None, max_length=120)
    fuente: str | None = Field(None, max_length=40)  # código de la fuente oficial


class PartidaSACIn(BaseModel):
    codigo: str = Field(max_length=10)
    descripcion: str = Field(max_length=400)
    nota: str | None = Field(None, max_length=300)
    activo: bool = True
    motivo: str | None = Field(None, max_length=300)  # por qué se reemplaza el texto oficial


class NotaSACIn(BaseModel):
    ambito: str = Field(max_length=16)
    codigo: str = Field(max_length=10)
    numero: str | None = Field(None, max_length=20)
    texto: str = Field(max_length=4000)
    capitulos: list[str] = Field(default_factory=list, max_length=100)
    activo: bool = True
    motivo: str | None = Field(None, max_length=300)


class IncisoEditIn(BaseModel):
    pais: str = Field(max_length=2)
    codigo: str = Field(max_length=20)
    descripcion: str | None = Field(None, max_length=300)
    dai: str | None = Field(None, max_length=10)
    cond: dict = Field(default_factory=dict)
    prio: int = Field(0, ge=0, le=99)
    nota: str | None = Field(None, max_length=300)
    activo: bool = True
    motivo: str | None = Field(None, max_length=300)  # por qué se personaliza una línea oficial
    # Línea nueva: es dato oficial, viene de una publicación (fuente y versión obligatorias)
    fuente: str | None = Field(None, max_length=30)
    version: str | None = Field(None, max_length=30)
    vigente_desde: date | None = None  # si la versión no trae su vigencia (p. ej. una versión dinámica)


class IncisoOverrideIn(BaseModel):
    descripcion: str | None = Field(None, max_length=300)
    nota: str | None = Field(None, max_length=300)
    activo: bool | None = None
    motivo: str = Field(min_length=3, max_length=300)
    vigente_desde: date | None = None
    vigente_hasta: date | None = None


class IdsIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=5000)


class TallaIn(BaseModel):
    talla: str = Field(max_length=20)
    sufijo: str | None = Field(None, max_length=20)  # código de talla tras el genérico; vacío = el siguiente libre
    sku: str | None = Field(None, max_length=40)  # código de artículo completo, si la empresa usa otro formato
    upc: str | None = Field(None, max_length=40)
    sku_proveedor: str | None = Field(None, max_length=60)
    peso_unitario: float | None = Field(None, ge=0)  # kg netos de una unidad de esta talla


class CambioFichaIn(BaseModel):
    campo: str = Field(max_length=60)
    valor: Any = None


class SesionClasificacionIn(BaseModel):
    """Entrada del motor único: la ficha natural del producto (o texto libre y
    respuestas para la sesión de clasificación)."""
    texto: str = Field("", max_length=2000)
    dominio: str | None = Field(None, max_length=30)
    categoria: str | None = Field(None, max_length=40)
    respuestas: dict = Field(default_factory=dict)  # atajo: respuestas sueltas (se suman a la ficha)
    ficha: dict | None = None
    estilo: str | None = Field(None, max_length=200)
    nombre: str | None = Field(None, max_length=200)
    uso: str | None = Field(None, max_length=200)
    tallas: str | None = Field(None, max_length=200)
    marca: str | None = Field(None, max_length=120)
    proveedor: str | None = Field(None, max_length=200)
    origen: str | None = Field(None, max_length=2)
    generico: str | None = Field(None, max_length=40)
    tocados: list[str] = Field(default_factory=list)
    autos: list[str] = Field(default_factory=list)
    cambio: CambioFichaIn | None = None
    detectar: bool | None = None
    producto_id: int | None = None
    codigo_final: str | None = Field(None, max_length=14)
    partidas: dict = Field(default_factory=dict)
    alertas_ok: list[str] = Field(default_factory=list)
    fecha: date | None = None
    paises: bool = True


class GenericoIn(BaseModel):
    generico: str = Field(max_length=40)
    estilo: str = Field(max_length=40)
    color: str = Field(max_length=60)
    marca_id: int
    grupo_id: int
    proveedor_id: int
    unidad: str = Field(max_length=5)
    nombre: str | None = Field(None, max_length=200)
    tallas: list[TallaIn] = Field(default_factory=list, max_length=200)
    escala_id: int | None = None  # escala de tallas de la que parten los códigos


class TallasIn(BaseModel):
    tallas: list[TallaIn] = Field(min_length=1, max_length=200)
    escala_id: int | None = None


class GenericoEditIn(BaseModel):
    estilo: str = Field(max_length=40)
    color: str = Field(max_length=60)
    marca_id: int
    grupo_id: int
    proveedor_id: int
    unidad: str = Field(max_length=5)
