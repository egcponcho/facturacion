"""Barras y módulos de los códigos de barras y QR (reportlab), normalizados a
módulo 1 para que el motor los escale a la medida del diseño. Textos
técnicos: i18n_extraer omite este archivo."""
from __future__ import annotations

from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.shapes import mmult

NOMBRE_RL = {"code128": "Code128", "code39": "Standard39", "ean13": "EAN13", "ean8": "EAN8", "upca": "UPCA", "qr": "QR"}


def _rectangulos(drawing) -> list[tuple]:
    """Las barras (o módulos) de un código: (x, y, ancho, alto) en puntos, origen abajo."""
    res = []

    def recorrer(s, t):
        tt = mmult(t, s.transform) if getattr(s, "transform", None) else t
        for c in getattr(s, "contents", None) or []:
            nombre = type(c).__name__
            if nombre == "Group":
                recorrer(c, tt)
            elif nombre in ("Rect", "SRect") and c.fillColor is not None and c.width > 0 and c.height > 0:
                x0, y0 = tt[0] * c.x + tt[2] * c.y + tt[4], tt[1] * c.x + tt[3] * c.y + tt[5]
                res.append((x0, y0, c.width * tt[0], c.height * tt[3]))

    recorrer(drawing.expandUserNodes(), (1, 0, 0, 1, 0, 0))
    return res



def barras(simbologia: str, valor: str, correccion: str = "M") -> tuple[list[tuple], float, float, int]:
    """Barras a escala de módulo 1 (x, y, w, h normalizados: el código mide
    `ancho_modulos` × `alto_modulos`) y cuántos módulos tiene de ancho."""
    if simbologia == "qr":
        d = createBarcodeDrawing("QR", value=valor, barLevel=correccion, barBorder=0, width=100, height=100)
        rects = _rectangulos(d)
        modulo = min(r[2] for r in rects)
        n = round(100 / modulo)
        return [(x / modulo, y / modulo, w / modulo, h / modulo) for x, y, w, h in rects], n, n, n
    extra = {"checksum": 0} if simbologia == "code39" else {}
    d = createBarcodeDrawing(NOMBRE_RL[simbologia], value=valor, barWidth=1, barHeight=1, humanReadable=False, quiet=False, **extra)
    rects = _rectangulos(d)
    ancho = max(x + w for x, _, w, _ in rects)
    return rects, ancho, 1, round(ancho)
