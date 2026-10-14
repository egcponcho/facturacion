"""Barras y módulos de los códigos de barras y QR (reportlab), normalizados a
módulo 1 para que el motor los escale a la medida del diseño. Textos
técnicos: i18n_extraer omite este archivo."""
from __future__ import annotations

from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics.shapes import mmult

NOMBRE_RL = {"code128": "Code128", "code39": "Standard39", "ean13": "EAN13", "ean8": "EAN8", "upca": "UPCA", "qr": "QR"}
# Las que dibuja zxing-cpp (formato, opciones): GS1 y las matriciales que reportlab no tiene
ZXING = {"gs1_128": ("Code128", "gs1"), "sscc": ("Code128", "gs1"), "itf14": ("ITF14", None),
         "datamatrix": ("DataMatrix", None), "gs1_datamatrix": ("DataMatrix", "gs1"), "pdf417": ("PDF417", None)}
# Matriciales (se dibujan con módulos cuadrados, sin estirar)
MATRICIALES = {"qr", "datamatrix", "gs1_datamatrix", "pdf417"}
CATALOGO = [
    ("code128", "CODE 128", "Internal codes, references: letters and digits"),
    ("code39", "CODE 39", "Capital letters and digits"),
    ("ean13", "EAN-13", "Registered GS1 retail code (13 digits with check digit)"),
    ("upca", "UPC-A", "Registered GS1 retail code (12 digits)"),
    ("ean8", "EAN-8", "Short GS1 retail code (8 digits)"),
    ("itf14", "ITF-14", "GS1 code of a carton (GTIN-14)"),
    ("gs1_128", "GS1-128", "GS1 data with application identifiers, like (01)…(17)…"),
    ("sscc", "SSCC", "GS1 serial number of a logistic unit (17 or 18 digits)"),
    ("qr", "QR", "Any text or link"),
    ("datamatrix", "DATA MATRIX", "Small square code for any text"),
    ("gs1_datamatrix", "GS1 DATA MATRIX", "GS1 data with application identifiers in a square code"),
    ("pdf417", "PDF417", "Long text in a stacked code (documents, shipping)"),
]


def catalogo() -> list[dict]:
    return [{"codigo": c, "nombre": n, "descripcion": d, "matricial": c in MATRICIALES} for c, n, d in CATALOGO]


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



def _zxing(simbologia: str, valor: str) -> tuple[list[tuple], float, float, int]:
    """Barras o módulos que dibuja zxing-cpp, a escala de módulo 1. Las lineales se
    leen de una fila (alto 1, el motor las estira); las matriciales, completas
    (y desde abajo, como el QR)."""
    import zxingcpp

    formato, opciones = ZXING[simbologia]
    kw = {"options": opciones} if opciones else {}
    cod = zxingcpp.create_barcode(valor, getattr(zxingcpp.BarcodeFormat, formato), **kw)
    filas = memoryview(cod.to_image(scale=1, add_quiet_zones=False)).tolist()
    alto, ancho = len(filas), len(filas[0])

    def corridas(fila):
        res, x = [], 0
        while x < ancho:
            if fila[x] == 0:
                ini = x
                while x < ancho and fila[x] == 0:
                    x += 1
                res.append((ini, x - ini))
            else:
                x += 1
        return res

    if simbologia not in MATRICIALES:
        return [(x, 0, w, 1) for x, w in corridas(filas[alto // 2])], ancho, 1, ancho
    rects = [(x, alto - 1 - y, w, 1) for y, fila in enumerate(filas) for x, w in corridas(fila)]
    return rects, ancho, alto, ancho


def barras(simbologia: str, valor: str, correccion: str = "M") -> tuple[list[tuple], float, float, int]:
    """Barras a escala de módulo 1 (x, y, w, h normalizados: el código mide
    `ancho_modulos` × `alto_modulos`) y cuántos módulos tiene de ancho."""
    if simbologia in ZXING:
        return _zxing(simbologia, valor)
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
