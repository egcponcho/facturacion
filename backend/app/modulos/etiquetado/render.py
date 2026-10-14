"""Motor de dibujo de etiquetas: un solo cálculo, tres salidas.

`componer()` toma un diseño validado y los valores de una etiqueta y produce
una lista de primitivas en milímetros (texto ya partido en líneas y
posicionado, rectángulos, elipses, líneas, imágenes y las barras de los
códigos) más los problemas encontrados (errores que impiden imprimir y
advertencias). PDF, SVG y PNG dibujan esas mismas primitivas con las mismas
fuentes (data/fuentes): lo que se ve en una salida es lo que sale en las otras.

Las medidas son físicas: el PDF mide exactamente el ancho y alto de la
etiqueta y pide al visor que no cambie la escala al imprimir.
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.modulos.etiquetado.codigos import barras
from app.modulos.etiquetado.diseno import CAMPO
from app.modulos.etiquetado.fuentes import MARCA_PRUEBA, ancho_texto, nombre_fuente

MM_PT = 72 / 25.4
PT_MM = 25.4 / 72
MESES = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
# Ancho mínimo del módulo (la barra más fina) para leerse con un lector común, en mm
MODULO_MINIMO = {"ean13": 0.264, "ean8": 0.264, "upca": 0.264, "code128": 0.19, "code39": 0.19, "qr": 0.25}
TEXTO_MINIMO_PT = 5
CONTRASTE_MINIMO = 3.0


# ---- Primitivas --------------------------------------------------------------------------
@dataclass
class Prim:
    tipo: str  # rect | elipse | linea | texto | imagen
    x: float = 0
    y: float = 0
    w: float = 0
    h: float = 0
    rot: float = 0
    cx: float = 0  # centro de giro (mm)
    cy: float = 0
    relleno: str | None = None
    borde: str | None = None
    grosor: float = 0
    radio: float = 0
    trazo: str = "solido"
    # texto: líneas (texto, x, línea base) en mm
    lineas: list = field(default_factory=list)
    fuente: str = ""
    tam: float = 0
    color: str = "#000000"
    espaciado: float = 0
    subrayado: bool = False
    tachado: bool = False
    # imagen
    imagen: bytes | None = None
    opacidad: float = 1.0


@dataclass
class Lienzo:
    ancho: float
    alto: float
    fondo: str
    prims: list[Prim]
    problemas: list[dict]
    dpi: int = 300

    @property
    def errores(self) -> list[dict]:
        return [p for p in self.problemas if p["nivel"] == "error"]

    @property
    def advertencias(self) -> list[dict]:
        return [p for p in self.problemas if p["nivel"] == "advertencia"]


def _problema(lista, nivel, codigo, elemento, mensaje):
    lista.append({"nivel": nivel, "codigo": codigo, "elemento": elemento.get("id") if elemento else None,
                  "nombre": (elemento.get("nombre") or elemento.get("campo") or elemento.get("tipo")) if elemento else None,
                  "mensaje": mensaje})


# ---- Valores -----------------------------------------------------------------------------
def vacio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _fecha(v):
    if isinstance(v, (date, datetime)):
        return v if isinstance(v, date) else v.date()
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def formatear(v, formato: dict | None, tipo: str = "texto") -> str | None:
    """El valor como se imprime: número con decimales y miles, fecha con su patrón, mayúsculas…"""
    if vacio(v):
        return None
    f = formato or {}
    t = f.get("tipo", "auto")
    if t == "numero" or (t == "auto" and (tipo == "numero" or isinstance(v, (int, float))) and not isinstance(v, bool)):
        try:
            n = float(v)
        except (TypeError, ValueError):
            return str(v)
        dec = f.get("decimales", 0) if t == "numero" else (0 if n == int(n) else 2)
        txt = f"{n:,.{dec}f}" if f.get("miles", True) else f"{n:.{dec}f}"
        return txt
    if t == "fecha" or (t == "auto" and tipo == "fecha"):
        d = _fecha(v)
        if d is None:
            return str(v)
        patron = f.get("fecha", "dd/mm/aaaa")
        return {"dd/mm/aaaa": d.strftime("%d/%m/%Y"), "aaaa-mm-dd": d.isoformat(), "mm/dd/aaaa": d.strftime("%m/%d/%Y"),
                "dd-mmm-aaaa": f"{d.day:02d}-{MESES[d.month - 1]}-{d.year}"}[patron]
    s = str(v)
    if t == "mayus":
        return s.upper()
    if t == "minus":
        return s.lower()
    return s


def sustituir(texto: str, valores: dict, tipos: dict) -> tuple[str, list[str]]:
    """Reemplaza {{campo}} por su valor; devuelve el texto y los campos vacíos."""
    vacios = []

    def uno(m):
        clave = m.group(1)
        v = formatear(valores.get(clave), None, tipos.get(clave, "texto"))
        if v is None:
            vacios.append(clave)
            return ""
        return v

    return CAMPO.sub(uno, texto or ""), vacios


def cumple(condicion: dict | None, valores: dict) -> bool:
    if not condicion:
        return True
    v = valores.get(condicion["campo"])
    op, esperado = condicion.get("op", "existe"), (condicion.get("valor") or "")
    if op == "existe":
        return not vacio(v)
    if op == "vacio":
        return vacio(v)
    s = "" if v is None else str(v)
    if op == "igual":
        return s.strip().lower() == esperado.strip().lower()
    if op == "distinto":
        return s.strip().lower() != esperado.strip().lower()
    return esperado.strip().lower() in s.lower()


# ---- Colores ------------------------------------------------------------------------------
def _lum(color: str) -> float:
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in (r, g, b)]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contraste(a: str, b: str) -> float:
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# ---- Códigos de barras y QR ----------------------------------------------------------------
def _digito_gs1(digitos: str) -> int:
    s = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digitos)))
    return (10 - s % 10) % 10


def validar_codigo(simbologia: str, valor: str) -> tuple[str | None, str | None]:
    """(valor a codificar, error). Los GS1 (EAN, UPC) exigen solo dígitos y su
    dígito verificador: un código interno no se convierte en uno comercial."""
    v = (valor or "").strip()
    if not v:
        return None, "There is no value to encode."
    largos = {"ean13": 13, "ean8": 8, "upca": 12}
    if simbologia in largos:
        n = largos[simbologia]
        if not v.isdigit() or len(v) not in (n - 1, n):
            return None, f"{simbologia.upper()} needs {n - 1} or {n} digits (it got «{v}»)."
        if len(v) == n and int(v[-1]) != _digito_gs1(v[:-1]):
            return None, f"The check digit of «{v}» is wrong for {simbologia.upper()}."
        return v[: n - 1], None
    if simbologia == "code39":
        if not re.fullmatch(r"[0-9A-Z\-. $/+%]{1,80}", v):
            return None, "CODE 39 only takes capital letters, digits, space and - . $ / + % (up to 80)."
        return v, None
    if simbologia == "code128":
        if len(v) > 80 or any(not 32 <= ord(c) <= 126 for c in v):
            return None, "CODE 128 takes up to 80 printable ASCII characters (no accents)."
        return v, None
    if len(v.encode("utf-8")) > 1200:
        return None, "The QR content is too long (up to 1,200 bytes)."
    return v, None


# ---- Texto -------------------------------------------------------------------------------
def _partir(texto: str, nombre: str, tam: float, esp: float, ancho: float) -> list[str]:
    """Líneas que caben en `ancho` (por palabras; una palabra larga se corta)."""
    lineas = []
    for parrafo in texto.split("\n"):
        actual = ""
        for palabra in parrafo.split(" "):
            prueba = f"{actual} {palabra}" if actual else palabra
            if ancho_texto(prueba, nombre, tam, esp) <= ancho + 1e-6:
                actual = prueba
                continue
            if actual:
                lineas.append(actual)
            actual = palabra
            while ancho_texto(actual, nombre, tam, esp) > ancho + 1e-6 and len(actual) > 1:
                corte = len(actual)
                while corte > 1 and ancho_texto(actual[:corte], nombre, tam, esp) > ancho:
                    corte -= 1
                lineas.append(actual[:corte])
                actual = actual[corte:]
        lineas.append(actual)
    return lineas


def _cortar(texto: str, nombre: str, tam: float, esp: float, ancho: float) -> str:
    if ancho_texto(texto, nombre, tam, esp) <= ancho:
        return texto
    while texto and ancho_texto(texto + "…", nombre, tam, esp) > ancho:
        texto = texto[:-1]
    return texto + "…"


def _texto(e: dict, texto: str, prims: list, problemas: list) -> None:
    est = e["estilo"]
    if est.get("mayusculas"):
        texto = texto.upper()
    nombre = nombre_fuente(est["fuente"], est["negrita"], est["cursiva"])
    rel = est["relleno"]
    ancho, alto = max(e["w"] - 2 * rel, 0.1), max(e["h"] - 2 * rel, 0.1)
    tam, esp = est["tam"], est["espaciado"]

    def maquetar(t):
        lineas = _partir(texto, nombre, t, esp, ancho) if est["multilinea"] else texto.split("\n")[:1]
        alto_linea = t * est["interlineado"] * PT_MM
        cabe = all(ancho_texto(x, nombre, t, esp) <= ancho + 1e-6 for x in lineas) and \
            (len(lineas) - 1) * alto_linea + t * PT_MM <= alto + 1e-6
        return lineas, alto_linea, cabe

    lineas, alto_linea, cabe = maquetar(tam)
    if not cabe and est["ajuste"] == "reducir":
        while not cabe and tam - 0.25 >= est["tam_min"]:
            tam -= 0.25
            lineas, alto_linea, cabe = maquetar(tam)
    if not cabe and est["ajuste"] == "cortar":
        maximo = max(int((alto - tam * PT_MM) // alto_linea) + 1, 1) if est["multilinea"] else 1
        if len(lineas) > maximo:
            lineas = lineas[:maximo]
            lineas[-1] = lineas[-1] + "…"
        lineas = [_cortar(x, nombre, tam, esp, ancho) for x in lineas]
        cabe = True
        _problema(problemas, "advertencia", "texto_cortado", e, "The text does not fit: it is shortened with «…».")
    if not cabe:
        _problema(problemas, "advertencia", "texto_desborda", e, "The text overflows its box.")
    if tam < TEXTO_MINIMO_PT:
        _problema(problemas, "advertencia", "texto_pequeno", e, f"The text is {tam:g} pt: it may not be legible.")
    # Posición: ascenso aproximado de la letra (0.8 del tamaño) para la primera línea base
    total = (len(lineas) - 1) * alto_linea + tam * PT_MM
    y0 = e["y"] + rel + {"arriba": 0, "medio": (alto - total) / 2, "abajo": alto - total}[est["valign"]]
    salida = []
    for i, linea in enumerate(lineas):
        w = ancho_texto(linea, nombre, tam, esp)
        x = e["x"] + rel + {"izq": 0, "centro": (ancho - w) / 2, "der": ancho - w}[est["alin"]]
        salida.append((linea, x, y0 + i * alto_linea + tam * PT_MM * 0.8, w))
    if est.get("fondo"):
        prims.append(Prim("rect", e["x"], e["y"], e["w"], e["h"], relleno=est["fondo"], **_giro(e)))
    prims.append(Prim("texto", e["x"], e["y"], e["w"], e["h"], lineas=salida, fuente=nombre, tam=tam, color=est["color"],
                      espaciado=esp, subrayado=est["subrayado"], tachado=est["tachado"], **_giro(e)))


def caja_girada(e: dict) -> tuple[float, float, float, float]:
    """Caja que ocupa el elemento una vez girado sobre su centro (x1, y1, x2, y2)."""
    if not e.get("rot"):
        return e["x"], e["y"], e["x"] + e["w"], e["y"] + e["h"]
    a = math.radians(e["rot"])
    cx, cy = e["x"] + e["w"] / 2, e["y"] + e["h"] / 2
    puntos = [(e["x"] + dx, e["y"] + dy) for dx in (0, e["w"]) for dy in (0, e["h"])]
    xs = [cx + (x - cx) * math.cos(a) - (y - cy) * math.sin(a) for x, y in puntos]
    ys = [cy + (x - cx) * math.sin(a) + (y - cy) * math.cos(a) for x, y in puntos]
    return min(xs), min(ys), max(xs), max(ys)


def _giro(e: dict) -> dict:
    return {"rot": e.get("rot") or 0, "cx": e["x"] + e["w"] / 2, "cy": e["y"] + e["h"] / 2}


# ---- Imágenes ----------------------------------------------------------------------------
def _encaje(img: bytes, e: dict) -> tuple[float, float, float, float] | None:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(img)) as im:
            iw, ih = im.size
    except Exception:  # noqa: BLE001 - un archivo que no es imagen
        return None
    if e["encaje"] == "estirar":
        return e["x"], e["y"], e["w"], e["h"]
    escala = (min if e["encaje"] == "contener" else max)(e["w"] / iw, e["h"] / ih)
    w, h = iw * escala, ih * escala
    return e["x"] + (e["w"] - w) / 2, e["y"] + (e["h"] - h) / 2, w, h


# ---- Composición ---------------------------------------------------------------------------
def componer(diseno: dict, valores: dict, tipos: dict | None = None, imagen_adjunta=None, prueba: bool = False) -> Lienzo:
    """Primitivas y problemas de una etiqueta con estos valores.

    tipos: campo → texto | numero | fecha | imagen (para formatear).
    imagen_adjunta(adjunto_id) → bytes | None: lee una imagen subida."""
    tipos = tipos or {}
    prims: list[Prim] = []
    problemas: list[dict] = []
    W, H, margen, fondo = diseno["ancho"], diseno["alto"], diseno["margen"], diseno["fondo"]
    prims.append(Prim("rect", 0, 0, W, H, relleno=fondo))
    for e in diseno.get("elementos", []):
        if not e.get("visible", True) or not cumple(e.get("condicion"), valores):
            continue
        # Límites (de la caja ya girada): fuera de la etiqueta es un error; fuera del área segura, una advertencia
        x1, y1, x2, y2 = caja_girada(e)
        if x2 <= 0 or y2 <= 0 or x1 >= W or y1 >= H:
            _problema(problemas, "error", "fuera_de_la_etiqueta", e, "The element is outside the label.")
            continue
        if x1 < -0.01 or y1 < -0.01 or x2 > W + 0.01 or y2 > H + 0.01:
            _problema(problemas, "advertencia", "fuera_de_limites", e, "Part of the element is outside the label.")
        elif e["tipo"] != "rect" and (x1 < margen - 0.01 or y1 < margen - 0.01 or x2 > W - margen + 0.01
                                      or y2 > H - margen + 0.01):
            _problema(problemas, "advertencia", "fuera_area_segura", e, "The element is outside the safe print area.")
        t = e["tipo"]
        if t == "rect":
            prims.append(Prim("rect", e["x"], e["y"], e["w"], e["h"], relleno=e.get("relleno"), borde=e.get("borde"),
                              grosor=e["grosor"], radio=e["radio"], trazo=e["trazo"], **_giro(e)))
        elif t == "elipse":
            prims.append(Prim("elipse", e["x"], e["y"], e["w"], e["h"], relleno=e.get("relleno"), borde=e.get("borde"),
                              grosor=e["grosor"], trazo=e["trazo"], **_giro(e)))
        elif t == "linea":
            prims.append(Prim("linea", e["x"], e["y"], e["w"], e["h"], borde=e["color"], grosor=e["grosor"], trazo=e["trazo"],
                              **_giro(e)))
        elif t in ("texto", "campo"):
            if t == "texto":
                texto, vacios = sustituir(e.get("contenido") or "", valores, tipos)
                for c in vacios:
                    _problema(problemas, "advertencia", "campo_vacio", e, f"The field {c} is empty.")
            else:
                v = formatear(valores.get(e["campo"]), e.get("formato"), tipos.get(e["campo"], "texto"))
                if v is None:
                    regla = e.get("si_vacio", "advertir")
                    if regla == "ocultar":
                        continue
                    if regla == "error":
                        _problema(problemas, "error", "campo_obligatorio", e, f"The field {e['campo']} is required and empty.")
                        continue
                    if regla == "alternativo":
                        v = e.get("alternativo") or ""
                    else:
                        _problema(problemas, "advertencia", "campo_vacio", e, f"The field {e['campo']} is empty.")
                        v = ""
                texto = f"{e.get('prefijo') or ''}{v}{e.get('sufijo') or ''}" if v else v
            if texto:
                _texto(e, texto, prims, problemas)
        elif t == "imagen":
            from app.modulos.etiquetado.salidas import datos_imagen

            img = None
            if e.get("fuente_imagen") == "adjunto":
                img = imagen_adjunta(e["adjunto_id"]) if imagen_adjunta else None
            elif e.get("fuente_imagen") == "campo":
                img = datos_imagen(valores.get(e["campo"]))
            else:
                img = datos_imagen(e.get("datos"))
            caja = _encaje(img, e) if img else None
            if caja is None:
                if e.get("si_vacio") == "error":
                    _problema(problemas, "error", "imagen_faltante", e, "The image is missing.")
                elif e.get("si_vacio") != "ocultar":
                    _problema(problemas, "advertencia", "imagen_faltante", e, "The image is missing.")
                continue
            x, y, w, h = caja
            prims.append(Prim("imagen", x, y, w, h, imagen=img, **_giro(e)))
        elif t == "codigo":
            _codigo(e, valores, tipos, fondo, prims, problemas)
    if diseno.get("borde"):
        b = diseno["borde"]
        prims.append(Prim("rect", b["grosor"] / 2, b["grosor"] / 2, W - b["grosor"], H - b["grosor"], borde=b["color"],
                          grosor=b["grosor"], radio=b["radio"]))
    if prueba:
        tam = max(min(W, H) / 4 * MM_PT, 6)
        txt = MARCA_PRUEBA
        nombre = nombre_fuente("sans", True, False)
        while ancho_texto(txt, nombre, tam) > math.hypot(W, H) * 0.85 and tam > 4:
            tam -= 0.5
        w = ancho_texto(txt, nombre, tam)
        prims.append(Prim("texto", 0, 0, W, H, lineas=[(txt, (W - w) / 2, H / 2 + tam * PT_MM * 0.35, w)], fuente=nombre, tam=tam,
                          color="#d32f2f", rot=-math.degrees(math.atan2(H, W)), cx=W / 2, cy=H / 2, opacidad=0.35))
    return Lienzo(W, H, fondo, prims, problemas, diseno.get("dpi", 300))


def _codigo(e: dict, valores: dict, tipos: dict, fondo: str, prims: list, problemas: list) -> None:
    simb = e["simbologia"]
    crudo, vacios = sustituir(e["valor"], valores, tipos)
    if vacios:
        _problema(problemas, "error", "codigo_sin_valor", e, f"The code has no value: {', '.join(vacios)} is empty.")
        return
    valor, error = validar_codigo(simb, crudo)
    if error:
        _problema(problemas, "error", "codigo_invalido", e, error)
        return
    claro = e.get("relleno") or fondo
    if contraste(e["color"], claro) < CONTRASTE_MINIMO or _lum(e["color"]) > _lum(claro):
        _problema(problemas, "error", "codigo_contraste", e,
                  "The code needs dark bars on a light background with enough contrast to be read.")
    m = e["margen"]
    caja_w, caja_h = e["w"] - 2 * m, e["h"] - 2 * m
    if e.get("relleno"):
        prims.append(Prim("rect", e["x"], e["y"], e["w"], e["h"], relleno=e["relleno"], **_giro(e)))
    rects, ancho_mod, alto_mod, modulos = barras(simb, valor, e.get("correccion", "M"))
    texto_legible = None
    if simb == "qr":
        lado = min(caja_w, caja_h)
        modulo = lado / modulos
        x0, y0 = e["x"] + m + (caja_w - lado) / 2, e["y"] + m + (caja_h - lado) / 2
        alto_barras = lado
    else:
        modulo = caja_w / ancho_mod
        alto_texto = 0
        if e.get("legible"):
            tam = max(min(caja_h * 0.22 * MM_PT, 10), 4)
            # Los GS1 se leen con su dígito verificador
            texto_legible = (crudo if simb in ("code128", "code39") else valor + str(_digito_gs1(valor)), tam)
            alto_texto = tam * PT_MM * 1.15
        alto_barras = caja_h - alto_texto
        x0, y0 = e["x"] + m, e["y"] + m
        if alto_barras < 8:
            _problema(problemas, "advertencia", "codigo_bajo", e, f"The bars are {alto_barras:.1f} mm high: scanners read better from 8 mm.")
    minimo = MODULO_MINIMO[simb]
    if modulo < minimo - 1e-9:
        _problema(problemas, "error", "codigo_pequeno", e,
                  f"The narrowest bar is {modulo:.3f} mm; {simb.upper()} needs at least {minimo} mm: make the code larger.")
    giro = _giro(e)
    for x, y, w, h in rects:
        if simb == "qr":
            prims.append(Prim("rect", x0 + x * modulo, y0 + (alto_mod - y - h) * modulo, w * modulo, h * modulo, relleno=e["color"], **giro))
        else:
            prims.append(Prim("rect", x0 + x * modulo, y0, w * modulo, alto_barras, relleno=e["color"], **giro))
    if texto_legible:
        txt, tam = texto_legible
        nombre = nombre_fuente("mono" if simb in ("code128", "code39") else "sans", False, False)
        w = ancho_texto(txt, nombre, tam)
        prims.append(Prim("texto", lineas=[(txt, e["x"] + m + (caja_w - w) / 2, y0 + alto_barras + tam * PT_MM * 0.95, w)],
                          fuente=nombre, tam=tam, color=e["color"], **giro))


