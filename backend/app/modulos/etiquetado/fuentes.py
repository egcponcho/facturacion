"""Fuentes de las etiquetas (Liberation, en data/fuentes): nombres, archivos y
medidas. Todas las salidas miden el texto igual (avance de cada letra, sin
interletraje). Textos técnicos: i18n_extraer omite este archivo."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PT_MM = 25.4 / 72
FUENTES = Path(__file__).resolve().parents[2] / "data" / "fuentes"
# Marca de agua de las etiquetas de prueba (versión sin aprobar)
MARCA_PRUEBA = "TEST · NOT APPROVED"
FAMILIAS = {"sans": "LiberationSans", "serif": "LiberationSerif", "mono": "LiberationMono"}


def nombre_fuente(fuente: str, negrita: bool, cursiva: bool) -> str:
    estilo = "BoldItalic" if negrita and cursiva else "Bold" if negrita else "Italic" if cursiva else "Regular"
    return f"{FAMILIAS[fuente]}-{estilo}"


def archivo_fuente(nombre: str) -> Path:
    return FUENTES / f"{nombre}.ttf"


@lru_cache(maxsize=None)
def _registrada(nombre: str) -> str:
    pdfmetrics.registerFont(TTFont(nombre, str(archivo_fuente(nombre))))
    return nombre


def ancho_texto(texto: str, nombre: str, tam_pt: float, espaciado_pt: float = 0) -> float:
    """Ancho en mm (avance de cada letra, sin interletraje: igual en las tres salidas)."""
    if not texto:
        return 0.0
    return (pdfmetrics.stringWidth(texto, _registrada(nombre), tam_pt) + espaciado_pt * (len(texto) - 1)) * PT_MM


def avances(texto: str, nombre: str, tam_pt: float, espaciado_pt: float = 0) -> list[float]:
    """Posición x (mm) de cada letra desde el inicio de la línea."""
    xs, x = [], 0.0
    fuente = _registrada(nombre)
    for ch in texto:
        xs.append(x)
        x += (pdfmetrics.stringWidth(ch, fuente, tam_pt) + espaciado_pt) * PT_MM
    return xs
