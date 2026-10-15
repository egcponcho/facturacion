"""Escrituras que no son latinas en las etiquetas: chino y japonés (CJK), árabe
(de derecha a izquierda, con las letras unidas) y devanagari (letras que se
combinan). Liberation no las tiene, así que cada tramo de texto se escribe con
su fuente Noto (data/fuentes, SIL OFL 1.1) y se le da forma con HarfBuzz
(uharfbuzz). Las tres salidas dibujan los mismos glifos en las mismas
posiciones: el PDF y el SVG como contornos, el PNG con el mismo motor de forma.

Orden de los tramos: si la primera letra con dirección es árabe, la línea va de
derecha a izquierda (los tramos se invierten); los números y el texto latino
dentro de ella se leen de izquierda a derecha. No se aplica el algoritmo
bidireccional completo de Unicode (paréntesis espejados, incrustaciones).
Textos técnicos: i18n_extraer omite este archivo."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from functools import lru_cache

from app.modulos.etiquetado.fuentes import PT_MM, archivo_fuente

# (desde, hasta, escritura)
RANGOS = (
    (0x0600, 0x06FF, "arabe"), (0x0750, 0x077F, "arabe"), (0x08A0, 0x08FF, "arabe"), (0xFB50, 0xFDFF, "arabe"),
    (0xFE70, 0xFEFF, "arabe"),
    (0x0900, 0x097F, "devanagari"), (0xA8E0, 0xA8FF, "devanagari"),
    (0x2E80, 0x2FDF, "cjk"), (0x3000, 0x30FF, "cjk"), (0x3100, 0x31FF, "cjk"), (0x3200, 0x33FF, "cjk"),
    (0x3400, 0x4DBF, "cjk"), (0x4E00, 0x9FFF, "cjk"), (0xF900, 0xFAFF, "cjk"), (0xFE30, 0xFE4F, "cjk"),
    (0xFF00, 0xFFEF, "cjk"),
)
FUENTE = {"arabe": "NotoSansArabic", "devanagari": "NotoSansDevanagari", "cjk": "NotoSansSC"}
DE_DERECHA = {"arabe"}


def escritura(ch: str) -> str | None:
    o = ord(ch)
    for a, b, nombre in RANGOS:
        if a <= o <= b:
            return nombre
    return None


def compleja(texto: str) -> bool:
    """El texto lleva letras que Liberation no tiene o que necesitan forma."""
    return any(ord(c) >= 0x0600 and escritura(c) for c in texto)


def _neutro(ch: str) -> bool:
    return ch.isspace() or not (ch.isalnum() or escritura(ch))


def fuente_de(esc: str | None, nombre_latino: str) -> str:
    if esc is None:
        return nombre_latino
    return f"{FUENTE[esc]}-{'Bold' if 'Bold' in nombre_latino else 'Regular'}"


@dataclass
class Tramo:
    texto: str
    fuente: str
    x: float = 0.0  # mm desde el inicio de la línea
    ancho: float = 0.0
    de_derecha: bool = False
    glifos: list = field(default_factory=list)  # (id del glifo, x, y) en mm desde el inicio del tramo


def _tramos(texto: str) -> tuple[list[tuple[str, str | None, bool]], bool]:
    """Partes seguidas con la misma escritura (texto, escritura, de derecha a izquierda) y si la
    línea va de derecha a izquierda. Los espacios y signos entre dos partes con la misma
    dirección van con ellas; si no, toman la dirección de la línea (Unicode, reglas N1 y N2)."""
    fichas: list[list] = []  # [texto, clave]; clave: escritura, None (latino) o "neutro"
    for ch in texto:
        clave = escritura(ch) or ("neutro" if _neutro(ch) else None)
        if fichas and fichas[-1][1] == clave:
            fichas[-1][0] += ch
        else:
            fichas.append([ch, clave])
    fuertes = [f for f in fichas if f[1] != "neutro"]
    derecha = bool(fuertes) and fuertes[0][1] in DE_DERECHA
    salida: list[list] = []  # [texto, escritura, de derecha]
    for n, (t, clave) in enumerate(fichas):
        if clave != "neutro":
            d = clave in DE_DERECHA
            if salida and salida[-1][2] == d and salida[-1][1] == clave:
                salida[-1][0] += t
            else:
                salida.append([t, clave, d])
            continue
        antes = salida[-1] if salida else None
        despues = next((f for f in fichas[n + 1:] if f[1] != "neutro"), None)
        d = antes[2] if antes and despues and antes[2] == (despues[1] in DE_DERECHA) else derecha
        if antes and antes[2] == d:
            antes[0] += t
        elif despues and (despues[1] in DE_DERECHA) == d and fichas[n + 1][1] != "neutro":
            fichas[n + 1][0] = t + fichas[n + 1][0]
        else:
            salida.append([t, None, d])
    return [(t, e, d) for t, e, d in salida], derecha


def _orden_visual(tramos: list, derecha: bool) -> list:
    """Reordena los tramos (regla L2 de Unicode): nivel de la línea 0 (izquierda a derecha) o 1;
    un tramo con la otra dirección sube un nivel; de mayor a menor nivel impar, se invierte cada
    secuencia seguida de ese nivel o más."""
    base = 1 if derecha else 0
    niveles = [base + (1 if tr.de_derecha != derecha else 0) for tr in tramos]
    orden = list(range(len(tramos)))
    for nivel in range(max(niveles, default=0), 0, -1):
        i = 0
        while i < len(orden):
            if niveles[orden[i]] >= nivel:
                j = i
                while j < len(orden) and niveles[orden[j]] >= nivel:
                    j += 1
                orden[i:j] = reversed(orden[i:j])
                i = j
            else:
                i += 1
    return [tramos[k] for k in orden]


@lru_cache(maxsize=16)
def _hb(fuente: str):
    import uharfbuzz as hb

    datos = archivo_fuente(fuente).read_bytes()
    cara = hb.Face(hb.Blob(datos))
    f = hb.Font(cara)
    return f, cara.upem


@lru_cache(maxsize=4096)
def formar(texto: str, nombre_latino: str, tam_pt: float, espaciado_pt: float = 0) -> tuple[tuple[Tramo, ...], float]:
    """Tramos de la línea en orden visual (de izquierda a derecha) con sus glifos y el ancho total en mm."""
    import uharfbuzz as hb

    partes, base_derecha = _tramos(texto)
    tramos = []
    for t, esc, derecha in partes:
        fuente = fuente_de(esc, nombre_latino)
        f, upm = _hb(fuente)
        buf = hb.Buffer()
        buf.add_str(t)
        buf.guess_segment_properties()
        buf.direction = "rtl" if derecha else "ltr"
        hb.shape(f, buf, {"kern": True, "liga": True})
        k = tam_pt * PT_MM / upm
        x, glifos = 0.0, []
        clusters = [i.cluster for i in buf.glyph_infos]
        for n, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions, strict=True)):
            glifos.append((info.codepoint, x + pos.x_offset * k, pos.y_offset * k))
            x += pos.x_advance * k
            # El espaciado entre letras va entre grupos (no dentro de una letra con sus signos)
            if espaciado_pt and n + 1 < len(clusters) and clusters[n + 1] != info.cluster:
                x += espaciado_pt * PT_MM
        tramos.append(Tramo(t, fuente, 0.0, x, derecha, glifos))
    tramos = _orden_visual(tramos, base_derecha)
    x = 0.0
    for i, tr in enumerate(tramos):
        tr.x = x
        x += tr.ancho + (espaciado_pt * PT_MM if i + 1 < len(tramos) else 0)
    return tuple(tramos), x


def ancho(texto: str, nombre_latino: str, tam_pt: float, espaciado_pt: float = 0) -> float:
    return formar(texto, nombre_latino, tam_pt, espaciado_pt)[1]


# fontTools lee cada glifo la primera vez que se dibuja y eso no es seguro entre
# hilos: dos miniaturas o PDF a la vez sobre la misma fuente se pisaban
# («'Glyph' object has no attribute 'flags'»). Todo dibujo de glifos pasa por aquí.
CANDADO_GLIFOS = threading.RLock()


@lru_cache(maxsize=16)
def _glifos(fuente: str):
    from fontTools.ttLib import TTFont as FT

    f = FT(str(archivo_fuente(fuente)))
    return f.getGlyphSet(), f.getGlyphOrder(), f["head"].unitsPerEm


def contornos(tramos, x0: float, base: float):
    """(fuente, glifo, x, y, escala, conjunto de glifos) de cada glifo para dibujarlo como contorno (y hacia abajo)."""
    for tr in tramos:
        conjunto, orden, upm = _glifos(tr.fuente)
        for gid, gx, gy in tr.glifos:
            if gid < len(orden):
                yield tr.fuente, orden[gid], x0 + tr.x + gx, base - gy, upm, conjunto
