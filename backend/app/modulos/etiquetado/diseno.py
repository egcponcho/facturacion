"""El diseño de una versión de etiqueta: medidas y elementos, validados.

Todo se guarda en milímetros (las medidas físicas reales) y los tamaños de
letra en puntos; `unidad` solo dice cómo se muestran en el editor. El origen
está arriba a la izquierda, como se ve la etiqueta. Los elementos se dibujan
en el orden de la lista (el último queda encima).

Un elemento es de un tipo (texto, campo, imagen, código, rectángulo, elipse o
línea) con sus propiedades; no hay una tabla por elemento: el JSON se valida
aquí antes de guardarse y el motor de dibujo (render.py) solo recibe diseños
válidos.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.core.errores import ErrorNegocio

Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Mm = Annotated[float, Field(ge=-1000, le=1000)]
Positivo = Annotated[float, Field(gt=0, le=1000)]
MAX_ELEMENTOS = 300
CAMPO = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")
SIMBOLOGIAS = ("code128", "code39", "ean13", "ean8", "upca", "qr")


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Estilo(_Base):
    fuente: Literal["sans", "serif", "mono"] = "sans"
    tam: float = Field(10, ge=3, le=400)  # puntos
    negrita: bool = False
    cursiva: bool = False
    subrayado: bool = False
    tachado: bool = False
    mayusculas: bool = False
    color: Color = "#000000"
    fondo: Color | None = None
    alin: Literal["izq", "centro", "der"] = "izq"
    valign: Literal["arriba", "medio", "abajo"] = "arriba"
    interlineado: float = Field(1.15, ge=0.7, le=4)
    espaciado: float = Field(0, ge=-2, le=40)  # puntos entre letras
    relleno: float = Field(0, ge=0, le=50)  # mm
    multilinea: bool = False
    ajuste: Literal["reducir", "cortar", "ninguno"] = "reducir"  # si no cabe
    tam_min: float = Field(6, ge=3, le=400)


class Formato(_Base):
    tipo: Literal["auto", "numero", "fecha", "mayus", "minus"] = "auto"
    decimales: int = Field(0, ge=0, le=6)
    miles: bool = True
    fecha: Literal["dd/mm/aaaa", "aaaa-mm-dd", "mm/dd/aaaa", "dd-mmm-aaaa"] = "dd/mm/aaaa"


class Condicion(_Base):
    campo: str = Field(max_length=80)
    op: Literal["existe", "vacio", "igual", "distinto", "contiene"] = "existe"
    valor: str | None = Field(None, max_length=200)


class Elemento(_Base):
    id: str = Field(pattern=r"^[\w-]{1,40}$")
    tipo: Literal["texto", "campo", "imagen", "codigo", "rect", "elipse", "linea"]
    nombre: str | None = Field(None, max_length=60)
    x: Mm = 0
    y: Mm = 0
    w: float = Field(20, ge=0, le=1000)
    h: float = Field(10, ge=0, le=1000)
    rot: float = Field(0, ge=-360, le=360)
    bloqueado: bool = False
    visible: bool = True
    grupo: str | None = Field(None, max_length=40)
    condicion: Condicion | None = None
    # texto: puede llevar campos {{articulo.sku}}; campo: un solo campo con prefijo y sufijo
    contenido: str | None = Field(None, max_length=2000)
    campo: str | None = Field(None, max_length=80)
    prefijo: str | None = Field(None, max_length=100)
    sufijo: str | None = Field(None, max_length=100)
    formato: Formato | None = None
    si_vacio: Literal["advertir", "ocultar", "alternativo", "error"] = "advertir"
    alternativo: str | None = Field(None, max_length=200)
    estilo: Estilo | None = None
    # imagen
    fuente_imagen: Literal["adjunto", "campo", "datos"] | None = None
    adjunto_id: int | None = None
    datos: str | None = Field(None, max_length=700_000)  # data URL pequeña (logo propio de la plantilla)
    encaje: Literal["contener", "cubrir", "estirar"] = "contener"
    # código de barras o QR
    simbologia: Literal["code128", "code39", "ean13", "ean8", "upca", "qr"] | None = None
    valor: str | None = Field(None, max_length=1000)  # texto con {{campos}} (o fijo)
    legible: bool = True  # texto bajo las barras
    margen: float = Field(0, ge=0, le=30)  # zona en blanco alrededor (mm)
    correccion: Literal["L", "M", "Q", "H"] = "M"  # QR
    # formas
    relleno: Color | None = None
    borde: Color | None = None
    grosor: float = Field(0.3, ge=0, le=20)  # mm
    radio: float = Field(0, ge=0, le=100)  # mm
    trazo: Literal["solido", "discontinuo", "punteado"] = "solido"
    color: Color = "#000000"  # código, línea

    @model_validator(mode="after")
    def _segun_tipo(self):
        t = self.tipo
        if t in ("texto", "campo", "imagen", "codigo", "rect", "elipse") and (self.w <= 0 or self.h <= 0):
            raise ValueError("width and height must be greater than zero")
        if t == "campo" and not self.campo:
            raise ValueError("choose the field")
        if t == "codigo" and (not self.simbologia or not (self.valor or "").strip()):
            raise ValueError("choose the symbology and the value to encode")
        if t == "imagen":
            if self.fuente_imagen == "adjunto" and not self.adjunto_id:
                raise ValueError("choose the image")
            if self.fuente_imagen == "campo" and not self.campo:
                raise ValueError("choose the image field")
            if self.fuente_imagen == "datos" and not (self.datos or "").startswith("data:image/"):
                raise ValueError("the image must be a PNG, JPEG or WebP")
            if not self.fuente_imagen:
                raise ValueError("choose the image")
        if t in ("texto", "campo") and self.estilo is None:
            self.estilo = Estilo()
        return self


class Cuadricula(_Base):
    paso: float = Field(1, ge=0.1, le=50)
    ajustar: bool = True
    visible: bool = True


class Borde(_Base):
    color: Color = "#000000"
    grosor: float = Field(0.3, gt=0, le=10)
    radio: float = Field(0, ge=0, le=50)


class Hoja(_Base):
    """Cómo se imprime: una etiqueta por página (rollo o etiquetadora) o
    varias en una hoja con columnas, filas, márgenes y separación."""
    modo: Literal["individual", "hoja"] = "individual"
    papel_ancho: float = Field(215.9, gt=0, le=2000)
    papel_alto: float = Field(279.4, gt=0, le=2000)
    columnas: int = Field(1, ge=1, le=50)
    filas: int = Field(1, ge=1, le=100)
    margen_sup: float = Field(10, ge=0, le=500)
    margen_izq: float = Field(10, ge=0, le=500)
    espacio_h: float = Field(2, ge=0, le=200)
    espacio_v: float = Field(2, ge=0, le=200)


class Variable(_Base):
    """Un dato que se escribe al generar (lote, temporada, destino…): se usa en
    el diseño como {{manual.clave}}; si no se escribe, va el valor por defecto."""
    clave: str = Field(pattern=r"^[a-z][a-z0-9_]{0,29}$")
    etiqueta: str = Field(min_length=1, max_length=60)
    defecto: str | None = Field(None, max_length=200)
    obligatorio: bool = False


class Diseno(_Base):
    esquema: Literal[1] = 1
    unidad: Literal["mm", "cm", "in"] = "mm"
    ancho: Positivo = 100
    alto: Positivo = 50
    margen: float = Field(2, ge=0, le=100)  # área segura de impresión (mm)
    fondo: Color = "#ffffff"
    borde: Borde | None = None
    dpi: int = Field(300, ge=72, le=1200)
    cuadricula: Cuadricula = Cuadricula()
    hoja: Hoja = Hoja()
    elementos: list[Elemento] = Field(default_factory=list, max_length=MAX_ELEMENTOS)
    variables: list[Variable] = Field(default_factory=list, max_length=30)

    @field_validator("variables")
    @classmethod
    def _variables_unicas(cls, v):
        claves = [x.clave for x in v]
        if len(claves) != len(set(claves)):
            raise ValueError("each field to fill in when generating needs its own key")
        return v

    @field_validator("elementos")
    @classmethod
    def _ids_unicos(cls, v):
        ids = [e.id for e in v]
        if len(ids) != len(set(ids)):
            raise ValueError("element ids must be unique")
        return v

    @model_validator(mode="after")
    def _hoja_cabe(self):
        h = self.hoja
        if h.modo == "hoja":
            ancho = h.margen_izq + h.columnas * self.ancho + (h.columnas - 1) * h.espacio_h
            alto = h.margen_sup + h.filas * self.alto + (h.filas - 1) * h.espacio_v
            if ancho > h.papel_ancho + 0.01 or alto > h.papel_alto + 0.01:
                raise ValueError("the labels do not fit on the sheet with these columns, rows and margins")
        return self


def validar(datos) -> dict:
    """El diseño limpio (con los valores por defecto) o 422 con cada problema."""
    try:
        return Diseno.model_validate(datos or {}).model_dump(mode="json")
    except ValidationError as e:
        detalle = [{"campo": ".".join(str(x) for x in err["loc"]), "mensaje": str((err.get("ctx") or {}).get("error") or err["msg"])}
                   for err in e.errors()[:20]]
        raise ErrorNegocio("Check the label design.", 422, "validacion", detalle) from None


def inicial(ancho: float = 100, alto: float = 50) -> dict:
    return validar({"ancho": ancho, "alto": alto})


def campos_usados(diseno: dict) -> set[str]:
    """Campos que el diseño lee (de campos, textos, códigos, imágenes y condiciones)."""
    usados = set()
    for e in diseno.get("elementos", []):
        if e.get("campo"):
            usados.add(e["campo"])
        for texto in (e.get("contenido"), e.get("valor")):
            usados |= set(CAMPO.findall(texto or ""))
        if e.get("condicion"):
            usados.add(e["condicion"]["campo"])
    return usados


def resumen_cambios(antes: dict | None, despues: dict) -> str | None:
    """Qué cambió entre dos diseños, en pocas palabras (para el historial de versiones)."""
    if not antes:
        return None
    cambios = []
    if (antes.get("ancho"), antes.get("alto")) != (despues.get("ancho"), despues.get("alto")):
        cambios.append(f"size {antes.get('ancho'):g}×{antes.get('alto'):g} → {despues['ancho']:g}×{despues['alto']:g} mm")
    for k in ("margen", "fondo", "borde", "dpi", "hoja"):
        if antes.get(k) != despues.get(k):
            cambios.append(f"{k} changed")
    a = {e["id"]: e for e in antes.get("elementos", [])}
    d = {e["id"]: e for e in despues.get("elementos", [])}
    agregados = [d[i].get("nombre") or d[i]["tipo"] for i in d if i not in a]
    quitados = [a[i].get("nombre") or a[i]["tipo"] for i in a if i not in d]
    editados = [d[i].get("nombre") or d[i]["tipo"] for i in d if i in a and a[i] != d[i]]
    if agregados:
        cambios.append("added: " + ", ".join(agregados[:8]))
    if quitados:
        cambios.append("removed: " + ", ".join(quitados[:8]))
    if editados:
        cambios.append("edited: " + ", ".join(editados[:8]))
    if [e["id"] for e in antes.get("elementos", []) if e["id"] in d] != [e["id"] for e in despues.get("elementos", []) if e["id"] in a]:
        cambios.append("layer order changed")
    return "; ".join(cambios) or "no changes"


def valores_manuales(diseno: dict, escritos: dict | None = None, ejemplo: bool = False) -> dict:
    """Los valores de los campos que se escriben al generar: lo escrito o, si no,
    el valor por defecto (en la vista previa de ejemplo, el nombre del campo)."""
    escritos = escritos or {}
    res = {}
    for v in diseno.get("variables") or []:
        valor = escritos.get(v["clave"])
        if valor in (None, ""):
            valor = v.get("defecto") or (f"[{v['etiqueta']}]" if ejemplo else None)
        res[f"manual.{v['clave']}"] = valor
    return res


def manuales_faltantes(diseno: dict, valores: dict) -> list[str]:
    """Campos obligatorios que se escriben al generar y quedaron vacíos."""
    return [v["etiqueta"] for v in diseno.get("variables") or []
            if v.get("obligatorio") and valores.get(f"manual.{v['clave']}") in (None, "")]
