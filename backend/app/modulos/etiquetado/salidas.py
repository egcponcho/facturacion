"""Salidas de las etiquetas: PDF (medida física exacta, una por página o en
hoja), SVG (en milímetros, con el texto en trazos) y PNG (a la resolución
pedida). Dibujan las primitivas que compone render.py. Textos técnicos:
i18n_extraer omite este archivo."""
from __future__ import annotations

import base64
import io
from functools import lru_cache

from fontTools.pens.basePen import BasePen
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

from app.modulos.etiquetado import escritura
from app.modulos.etiquetado.fuentes import _registrada, archivo_fuente, avances
from app.modulos.etiquetado.render import Lienzo, Prim

MM_PT = 72 / 25.4
PT_MM = 25.4 / 72


def datos_imagen(texto: str | None) -> bytes | None:
    if not texto or not texto.startswith("data:image/") or ";base64," not in texto:
        return None
    try:
        return base64.b64decode(texto.split(";base64,", 1)[1], validate=True)
    except ValueError:
        return None



# ---- PDF ---------------------------------------------------------------------------------
def _trazo_pdf(c, p: Prim):
    """Grosor y patrón del trazo en mm (el lienzo del PDF ya está en mm)."""
    c.setLineWidth(p.grosor)
    if p.trazo == "discontinuo":
        c.setDash([3 * p.grosor + 0.7, 2 * p.grosor + 0.5])
    elif p.trazo == "punteado":
        c.setDash([max(p.grosor, 0.18), 2 * p.grosor + 0.35])
    else:
        c.setDash()


class _PlumaPdf(BasePen):
    """Contorno de un glifo (unidades de la fuente) a un trazo de reportlab."""

    def __init__(self, conjunto, trazo):
        super().__init__(conjunto)
        self.trazo = trazo

    def _moveTo(self, p):
        self.trazo.moveTo(*p)

    def _lineTo(self, p):
        self.trazo.lineTo(*p)

    def _curveToOne(self, a, b, c):
        self.trazo.curveTo(*a, *b, *c)

    def _closePath(self):
        self.trazo.close()


def _contornos_pdf(c, texto: str, p: Prim, x: float, base: float) -> None:
    """Una línea en escritura compleja: cada glifo ya con forma, como contorno relleno."""
    tramos, _ = escritura.formar(texto, p.fuente, p.tam, p.espaciado)
    for _fuente, glifo, gx, gy, upm, conjunto in escritura.contornos(tramos, x, base):
        k = p.tam * PT_MM / upm
        c.saveState()
        c.translate(gx, gy)
        c.scale(k, -k)
        trazo = c.beginPath()
        conjunto[glifo].draw(_PlumaPdf(conjunto, trazo))
        c.drawPath(trazo, stroke=0, fill=1, fillMode=0)  # regla de relleno distinta de cero (TrueType)
        c.restoreState()


def dibujar_pdf(c, lienzo: Lienzo, x0: float = 0, y0: float = 0) -> None:
    """Dibuja la etiqueta en un lienzo de reportlab con su esquina superior izquierda en (x0, y0) mm de la página."""
    alto_pag = c._pagesize[1] * PT_MM
    for p in lienzo.prims:
        c.saveState()
        # Coordenadas de la etiqueta (mm, y hacia abajo) → página (pt, y hacia arriba)
        c.translate(x0 * MM_PT, (alto_pag - y0) * MM_PT)
        c.scale(MM_PT, -MM_PT)
        if p.rot:
            c.translate(p.cx, p.cy)
            c.rotate(p.rot)
            c.translate(-p.cx, -p.cy)
        if p.opacidad < 1:
            c.setFillAlpha(p.opacidad)
            c.setStrokeAlpha(p.opacidad)
        if p.tipo in ("rect", "elipse"):
            if p.relleno:
                c.setFillColor(HexColor(p.relleno))
            if p.borde:
                c.setStrokeColor(HexColor(p.borde))
                _trazo_pdf(c, p)
            relleno, borde = bool(p.relleno), bool(p.borde and p.grosor)
            if p.tipo == "elipse":
                c.ellipse(p.x, p.y, p.x + p.w, p.y + p.h, stroke=borde, fill=relleno)
            elif p.radio:
                c.roundRect(p.x, p.y, p.w, p.h, p.radio, stroke=borde, fill=relleno)
            else:
                c.rect(p.x, p.y, p.w, p.h, stroke=borde, fill=relleno)
        elif p.tipo == "linea":
            c.setStrokeColor(HexColor(p.borde))
            _trazo_pdf(c, p)
            c.line(p.x, p.y, p.x + p.w, p.y + p.h)
        elif p.tipo == "imagen":
            c.translate(p.x, p.y + p.h)
            c.scale(1, -1)
            c.drawImage(ImageReader(io.BytesIO(p.imagen)), 0, 0, p.w, p.h, mask="auto")
        elif p.tipo == "texto":
            _registrada(p.fuente)
            c.setFillColor(HexColor(p.color))
            for texto, x, base, w in p.lineas:
                if escritura.compleja(texto):
                    _contornos_pdf(c, texto, p, x, base)
                else:
                    c.saveState()
                    c.translate(x, base)
                    c.scale(PT_MM, -PT_MM)  # el texto se escribe en puntos y hacia arriba
                    t = c.beginText(0, 0)
                    t.setFont(p.fuente, p.tam)
                    t.setCharSpace(p.espaciado)
                    t.textOut(texto)
                    c.drawText(t)
                    c.restoreState()
                if p.subrayado or p.tachado:
                    c.setStrokeColor(HexColor(p.color))
                    c.setLineWidth(max(p.tam * PT_MM * 0.06, 0.1))
                    c.setDash()
                    if p.subrayado:
                        c.line(x, base + p.tam * PT_MM * 0.12, x + w, base + p.tam * PT_MM * 0.12)
                    if p.tachado:
                        c.line(x, base - p.tam * PT_MM * 0.28, x + w, base - p.tam * PT_MM * 0.28)
        c.restoreState()


def cabe(hoja: dict, ancho: float, alto: float) -> bool:
    """Si las columnas y filas de etiquetas de esta medida caben en el papel."""
    a = hoja["margen_izq"] + hoja["columnas"] * ancho + (hoja["columnas"] - 1) * hoja["espacio_h"]
    b = hoja["margen_sup"] + hoja["filas"] * alto + (hoja["filas"] - 1) * hoja["espacio_v"]
    return a <= hoja["papel_ancho"] + 0.01 and b <= hoja["papel_alto"] + 0.01


def pdf(lienzos: list[Lienzo], hoja: dict | None = None, titulo: str = "Labels") -> bytes:
    """Un PDF con una etiqueta por página (medida exacta) o varias por hoja."""
    from reportlab.pdfgen.canvas import Canvas

    buf = io.BytesIO()
    if not lienzos:
        raise ValueError("no labels")
    W, H = lienzos[0].ancho, lienzos[0].alto
    en_hoja = hoja and hoja.get("modo") == "hoja"
    tam = (hoja["papel_ancho"] * MM_PT, hoja["papel_alto"] * MM_PT) if en_hoja else (W * MM_PT, H * MM_PT)
    c = Canvas(buf, pagesize=tam, pageCompression=1, invariant=1)  # sin fecha ni id al azar: el mismo lote da el mismo archivo
    c.setTitle(titulo)
    c.setCreator("Labels")
    c.setViewerPreference("PrintScaling", "None")  # imprimir al 100 %: el visor no cambia la escala
    if not en_hoja:
        for i, lz in enumerate(lienzos):
            if i:
                c.showPage()
            if (lz.ancho, lz.alto) != (W, H):
                c.setPageSize((lz.ancho * MM_PT, lz.alto * MM_PT))
                W, H = lz.ancho, lz.alto
            dibujar_pdf(c, lz)
    else:
        # Cada celda mide lo que su etiqueta: si cambia la medida, la etiqueta
        # empieza otra hoja (las celdas de la anterior no le sirven)
        por_hoja = hoja["columnas"] * hoja["filas"]
        k = 0
        for i, lz in enumerate(lienzos):
            if not cabe(hoja, lz.ancho, lz.alto):
                raise ValueError(f"a {lz.ancho:g}×{lz.alto:g} mm label does not fit on the sheet")
            if (lz.ancho, lz.alto) != (W, H) or k == por_hoja:
                if i:
                    c.showPage()
                W, H, k = lz.ancho, lz.alto, 0
            fila, col = divmod(k, hoja["columnas"])
            dibujar_pdf(c, lz, hoja["margen_izq"] + col * (W + hoja["espacio_h"]), hoja["margen_sup"] + fila * (H + hoja["espacio_v"]))
            k += 1
    c.showPage()
    c.save()
    return buf.getvalue()


# ---- SVG ---------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _fuente_svg(nombre: str):
    from fontTools.ttLib import TTFont as FT

    f = FT(str(archivo_fuente(nombre)))
    return f, f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm


@lru_cache(maxsize=20000)
def _glifo(nombre: str, ch: str) -> str:
    from fontTools.pens.svgPathPen import SVGPathPen

    _, glifos, cmap, _ = _fuente_svg(nombre)
    g = cmap.get(ord(ch)) or cmap.get(ord("?"))
    if not g:
        return ""
    pen = SVGPathPen(glifos)
    glifos[g].draw(pen)
    return pen.getCommands()


@lru_cache(maxsize=20000)
def _glifo_id(fuente: str, glifo: str) -> str:
    from fontTools.pens.svgPathPen import SVGPathPen

    conjunto = escritura._glifos(fuente)[0]
    pen = SVGPathPen(conjunto)
    conjunto[glifo].draw(pen)
    return pen.getCommands()


def _n(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") or "0"


def _dash_svg(p: Prim) -> str:
    if p.trazo == "discontinuo":
        return f' stroke-dasharray="{_n(3 * p.grosor + 0.7)} {_n(2 * p.grosor + 0.5)}"'
    if p.trazo == "punteado":
        return f' stroke-dasharray="{_n(max(p.grosor, 0.18))} {_n(2 * p.grosor + 0.35)}"'
    return ""


def svg(lienzo: Lienzo) -> str:
    """SVG autónomo en milímetros; el texto va en trazos (no depende de fuentes instaladas)."""
    W, H = lienzo.ancho, lienzo.alto
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_n(W)}mm" height="{_n(H)}mm" viewBox="0 0 {_n(W)} {_n(H)}">']
    for p in lienzo.prims:
        tr = f' transform="rotate({_n(p.rot)} {_n(p.cx)} {_n(p.cy)})"' if p.rot else ""
        op = f' opacity="{_n(p.opacidad)}"' if p.opacidad < 1 else ""
        if p.tipo == "rect":
            borde = f' stroke="{p.borde}" stroke-width="{_n(p.grosor)}"{_dash_svg(p)}' if p.borde and p.grosor else ""
            rx = f' rx="{_n(p.radio)}"' if p.radio else ""
            out.append(f'<rect x="{_n(p.x)}" y="{_n(p.y)}" width="{_n(p.w)}" height="{_n(p.h)}"{rx} fill="{p.relleno or "none"}"{borde}{tr}{op}/>')
        elif p.tipo == "elipse":
            borde = f' stroke="{p.borde}" stroke-width="{_n(p.grosor)}"{_dash_svg(p)}' if p.borde and p.grosor else ""
            out.append(f'<ellipse cx="{_n(p.x + p.w / 2)}" cy="{_n(p.y + p.h / 2)}" rx="{_n(p.w / 2)}" ry="{_n(p.h / 2)}" '
                       f'fill="{p.relleno or "none"}"{borde}{tr}{op}/>')
        elif p.tipo == "linea":
            out.append(f'<line x1="{_n(p.x)}" y1="{_n(p.y)}" x2="{_n(p.x + p.w)}" y2="{_n(p.y + p.h)}" stroke="{p.borde}" '
                       f'stroke-width="{_n(p.grosor)}"{_dash_svg(p)}{tr}{op}/>')
        elif p.tipo == "imagen":
            from PIL import Image

            with Image.open(io.BytesIO(p.imagen)) as im:
                mime = Image.MIME.get(im.format, "image/png")
            b64 = base64.b64encode(p.imagen).decode()
            out.append(f'<image x="{_n(p.x)}" y="{_n(p.y)}" width="{_n(p.w)}" height="{_n(p.h)}" preserveAspectRatio="none" '
                       f'href="data:{mime};base64,{b64}"{tr}{op}/>')
        elif p.tipo == "texto":
            _, _, _, upm = _fuente_svg(p.fuente)
            escala = p.tam * PT_MM / upm
            partes = []
            for texto, x, base, w in p.lineas:
                if escritura.compleja(texto):
                    tramos, _ = escritura.formar(texto, p.fuente, p.tam, p.espaciado)
                    for fuente, glifo, gx, gy, upm, _c in escritura.contornos(tramos, x, base):
                        d = _glifo_id(fuente, glifo)
                        k = p.tam * PT_MM / upm
                        if d:
                            partes.append(f'<path transform="translate({_n(gx)} {_n(gy)}) scale({k:.6f} {-k:.6f})" d="{d}"/>')
                    continue
                for ch, dx in zip(texto, avances(texto, p.fuente, p.tam, p.espaciado), strict=True):
                    d = _glifo(p.fuente, ch)
                    if d:
                        partes.append(f'<path transform="translate({_n(x + dx)} {_n(base)}) scale({escala:.6f} {-escala:.6f})" d="{d}"/>')
                grosor = max(p.tam * PT_MM * 0.06, 0.1)
                if p.subrayado:
                    partes.append(f'<rect x="{_n(x)}" y="{_n(base + p.tam * PT_MM * 0.12 - grosor / 2)}" width="{_n(w)}" height="{_n(grosor)}"/>')
                if p.tachado:
                    partes.append(f'<rect x="{_n(x)}" y="{_n(base - p.tam * PT_MM * 0.28 - grosor / 2)}" width="{_n(w)}" height="{_n(grosor)}"/>')
            out.append(f'<g fill="{p.color}"{tr}{op}>{"".join(partes)}</g>')
    out.append("</svg>")
    return "".join(out)


# ---- PNG ---------------------------------------------------------------------------------
@lru_cache(maxsize=256)
def _fuente_png(nombre: str, tam_px: float, forma: bool = False):
    from PIL import ImageFont

    if forma:
        return ImageFont.truetype(str(archivo_fuente(nombre)), size=tam_px, layout_engine=ImageFont.Layout.RAQM)
    return ImageFont.truetype(str(archivo_fuente(nombre)), size=tam_px)


def png(lienzo: Lienzo, dpi: int | None = None) -> bytes:
    """Imagen a la resolución del diseño (o la pedida), con las medidas físicas en sus metadatos."""
    from PIL import Image, ImageDraw

    dpi = dpi or lienzo.dpi
    k = dpi / 25.4
    W, H = max(round(lienzo.ancho * k), 1), max(round(lienzo.alto * k), 1)
    base = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    for p in lienzo.prims:
        capa = Image.new("RGBA", (W, H), (0, 0, 0, 0)) if (p.rot or p.opacidad < 1) else base
        d = ImageDraw.Draw(capa)
        caja = [round(p.x * k), round(p.y * k), round((p.x + p.w) * k) - 1, round((p.y + p.h) * k) - 1]
        ancho = max(round(p.grosor * k), 1) if p.grosor else 0
        if p.tipo == "rect":
            if p.radio:
                d.rounded_rectangle(caja, radius=round(p.radio * k), fill=p.relleno, outline=p.borde if ancho else None, width=ancho)
            else:
                d.rectangle(caja, fill=p.relleno, outline=p.borde if ancho else None, width=ancho)
        elif p.tipo == "elipse":
            d.ellipse(caja, fill=p.relleno, outline=p.borde if ancho else None, width=ancho)
        elif p.tipo == "linea":
            d.line([(p.x * k, p.y * k), ((p.x + p.w) * k, (p.y + p.h) * k)], fill=p.borde, width=ancho or 1)
        elif p.tipo == "imagen":
            with Image.open(io.BytesIO(p.imagen)) as im:
                im = im.convert("RGBA").resize((max(round(p.w * k), 1), max(round(p.h * k), 1)), Image.LANCZOS)
                capa.alpha_composite(im, (round(p.x * k), round(p.y * k)))
        elif p.tipo == "texto":
            fuente = _fuente_png(p.fuente, p.tam * dpi / 72)
            for texto, x, base_y, w in p.lineas:
                if escritura.compleja(texto):
                    # Cada tramo con su fuente Noto y el mismo motor de forma (raqm usa HarfBuzz)
                    tramos, _ = escritura.formar(texto, p.fuente, p.tam, p.espaciado)
                    for tr in tramos:
                        f = _fuente_png(tr.fuente, p.tam * dpi / 72, True)
                        d.text(((x + tr.x) * k, base_y * k), tr.texto, font=f, fill=p.color, anchor="ls",
                               direction="rtl" if tr.de_derecha else "ltr")
                    continue
                for ch, dx in zip(texto, avances(texto, p.fuente, p.tam, p.espaciado), strict=True):
                    d.text(((x + dx) * k, base_y * k), ch, font=fuente, fill=p.color, anchor="ls")
                grosor = max(round(p.tam * PT_MM * 0.06 * k), 1)
                if p.subrayado:
                    yy = (base_y + p.tam * PT_MM * 0.12) * k
                    d.line([(x * k, yy), ((x + w) * k, yy)], fill=p.color, width=grosor)
                if p.tachado:
                    yy = (base_y - p.tam * PT_MM * 0.28) * k
                    d.line([(x * k, yy), ((x + w) * k, yy)], fill=p.color, width=grosor)
        if capa is not base:
            if p.opacidad < 1:
                alfa = capa.getchannel("A").point(lambda a, o=p.opacidad: round(a * o))
                capa.putalpha(alfa)
            if p.rot:
                capa = capa.rotate(-p.rot, center=(p.cx * k, p.cy * k), resample=Image.BICUBIC)
            base.alpha_composite(capa)
    salida = Image.new("RGB", (W, H), "white")
    salida.paste(base, mask=base.getchannel("A"))
    buf = io.BytesIO()
    salida.save(buf, "PNG", dpi=(dpi, dpi), optimize=True)
    return buf.getvalue()
