"""Motor de dibujo de etiquetas: medidas físicas exactas en PDF, PNG y SVG,
colores y fuentes, lectura real de los códigos generados (zxing-cpp) y las
validaciones que impiden imprimir una etiqueta incorrecta."""
import io
import xml.etree.ElementTree as ET

import pdfplumber
import pytest
from PIL import Image

from app.core.errores import ErrorNegocio
from app.modulos.etiquetado import diseno as svc_diseno
from app.modulos.etiquetado import render, salidas

zxingcpp = pytest.importorskip("zxingcpp")

MM_PT = 72 / 25.4


def _diseno(elementos, **kw):
    return svc_diseno.validar({"ancho": 100, "alto": 50, "margen": 2, "elementos": elementos, **kw})


def _leer(png_bytes):
    with Image.open(io.BytesIO(png_bytes)) as im:
        return [(r.format.name, r.text) for r in zxingcpp.read_barcodes(im.convert("L"))]


def test_validacion_del_diseno():
    d = svc_diseno.validar({})
    assert (d["ancho"], d["alto"], d["dpi"]) == (100, 50, 300) and d["elementos"] == []
    with pytest.raises(ErrorNegocio):
        svc_diseno.validar({"elementos": [{"id": "a", "tipo": "texto"}, {"id": "a", "tipo": "rect"}]})  # ids repetidos
    with pytest.raises(ErrorNegocio):
        svc_diseno.validar({"elementos": [{"id": "a", "tipo": "codigo", "simbologia": "qr"}]})  # sin valor
    with pytest.raises(ErrorNegocio):
        svc_diseno.validar({"elementos": [{"id": "a", "tipo": "texto", "estilo": {"color": "rojo"}}]})
    with pytest.raises(ErrorNegocio):
        svc_diseno.validar({"elementos": [{"id": "a", "tipo": "rect", "script": "x"}]})  # propiedad desconocida
    with pytest.raises(ErrorNegocio):  # no caben 3 columnas de 100 mm en una carta
        svc_diseno.validar({"hoja": {"modo": "hoja", "columnas": 3, "filas": 1}})


def test_pdf_png_svg_con_medidas_colores_y_fuentes_reales():
    d = _diseno([
        {"id": "fondo", "tipo": "rect", "x": 0, "y": 0, "w": 100, "h": 12, "relleno": "#1565c0"},
        {"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 4, "y": 16, "w": 90, "h": 10,
         "estilo": {"tam": 14, "negrita": True, "color": "#c62828"}},
        {"id": "fijo", "tipo": "texto", "contenido": "Talla {{articulo.talla}}", "x": 4, "y": 30, "w": 60, "h": 8,
         "estilo": {"tam": 10, "fuente": "serif", "cursiva": True}},
    ])
    lz = render.componer(d, {"articulo.sku": "NF0A7QEY", "articulo.talla": "M"})
    assert not lz.problemas
    # PDF: la página mide exactamente 100 × 50 mm, con el texto, su color y la fuente incluida
    with pdfplumber.open(io.BytesIO(salidas.pdf([lz]))) as doc:
        pag = doc.pages[0]
        assert pag.width == pytest.approx(100 * MM_PT, abs=0.01) and pag.height == pytest.approx(50 * MM_PT, abs=0.01)
        texto = pag.extract_text()
        assert "NF0A7QEY" in texto and "Talla M" in texto
        sku = [c for c in pag.chars if c["text"] == "N"][0]
        assert "LiberationSans-Bold" in sku["fontname"] and sku["size"] == pytest.approx(14, abs=0.01)
        assert tuple(round(x, 2) for x in sku["non_stroking_color"]) == (0.78, 0.16, 0.16)
        # El texto está donde se diseñó (x = 4 mm)
        assert sku["x0"] == pytest.approx(4 * MM_PT, abs=0.5)
        talla = [c for c in pag.chars if c["text"] == "T"][0]
        assert "LiberationSerif-Italic" in talla["fontname"]
    # PNG: 100 × 50 mm a 300 ppp = 1181 × 591 px, con la resolución en sus metadatos y los colores
    with Image.open(io.BytesIO(salidas.png(lz))) as im:
        assert im.size == (1181, 591) and round(im.info["dpi"][0]) == 300
        assert im.getpixel((500, 50)) == (21, 101, 192)  # la franja azul
        assert im.getpixel((1100, 560)) == (255, 255, 255)
    # SVG: en milímetros y con el texto en trazos
    raiz = ET.fromstring(salidas.svg(lz))
    assert raiz.get("width") == "100mm" and raiz.get("height") == "50mm" and raiz.get("viewBox") == "0 0 100 50"
    assert len(raiz.findall(".//{http://www.w3.org/2000/svg}path")) >= len("NF0A7QEY") + len("TallaM")


@pytest.mark.parametrize("simb,valor,leido,formato", [
    ("code128", "{{articulo.sku}}", "NF0A7QEY-JK3", "Code128"),
    ("ean13", "590123412345", "5901234123457", "EAN13"),
    ("ean13", "5901234123457", "5901234123457", "EAN13"),
    ("upca", "03600029145", "0036000291452", "EAN13"),  # el lector informa un UPC-A como EAN-13 con un 0 delante
    ("ean8", "9638507", "96385074", "EAN8"),
    ("code39", "ABC-123", "ABC-123", "Code39"),
    ("qr", "https://ejemplo.test/oc/{{oc.numero}}", "https://ejemplo.test/oc/4500012345", "QRCode"),
])
def test_los_codigos_generados_se_leen(simb, valor, leido, formato):
    alto = 40 if simb == "qr" else 25
    d = _diseno([{"id": "c", "tipo": "codigo", "simbologia": simb, "valor": valor, "x": 10, "y": 5, "w": 80 if simb != "qr" else 40,
                  "h": alto, "margen": 1}])
    lz = render.componer(d, {"articulo.sku": "NF0A7QEY-JK3", "oc.numero": "4500012345"})
    assert not lz.errores, lz.problemas
    assert (formato, leido) in _leer(salidas.png(lz, dpi=300))


def test_codigos_validados_sin_inventar_identificadores():
    def errores(simb, valor, **kw):
        e = {"id": "c", "tipo": "codigo", "simbologia": simb, "valor": valor, "x": 5, "y": 5, "w": 60, "h": 30, **kw}
        return {p["codigo"] for p in render.componer(_diseno([e]), {}).errores}

    assert errores("ean13", "5901234123458") == {"codigo_invalido"}  # dígito verificador incorrecto
    assert errores("ean13", "NF0A7QEY") == {"codigo_invalido"}  # un SKU interno no es un EAN
    assert errores("code39", "abc") == {"codigo_invalido"}
    assert errores("code128", "Ñandú") == {"codigo_invalido"}
    assert errores("code128", "{{articulo.upc}}") == {"codigo_sin_valor"}
    assert errores("ean13", "590123412345", w=12) == {"codigo_pequeno"}  # barra más fina que 0.264 mm
    assert errores("qr", "x", color="#bbbbbb") == {"codigo_contraste"}
    assert errores("qr", "x", color="#ffffff", relleno="#000000") == {"codigo_contraste"}  # invertido


def test_texto_largo_vacio_condiciones_y_limites():
    largo = "Men's waterproof breathable rain jacket with adjustable hood"
    base = {"x": 2, "y": 2, "w": 40, "h": 6, "estilo": {"tam": 12}}
    reducido = render.componer(_diseno([{"id": "t", "tipo": "texto", "contenido": "Men's waterproof rain jacket", **base,
                                         "estilo": {"tam": 12, "tam_min": 6}}]), {})
    assert 6 <= reducido.prims[-1].tam < 12 and not reducido.advertencias
    cortado = render.componer(_diseno([{"id": "t", "tipo": "texto", "contenido": largo, **base,
                                        "estilo": {"tam": 12, "ajuste": "cortar"}}]), {})
    assert cortado.prims[-1].lineas[0][0].endswith("…") and {p["codigo"] for p in cortado.advertencias} == {"texto_cortado"}
    desborda = render.componer(_diseno([{"id": "t", "tipo": "texto", "contenido": largo, **base,
                                         "estilo": {"tam": 12, "ajuste": "ninguno"}}]), {})
    assert {p["codigo"] for p in desborda.advertencias} == {"texto_desborda"}
    multilinea = render.componer(_diseno([{"id": "t", "tipo": "texto", "contenido": largo, "x": 2, "y": 2, "w": 40, "h": 30,
                                           "estilo": {"tam": 9, "multilinea": True}}]), {})
    assert len(multilinea.prims[-1].lineas) >= 3 and not multilinea.problemas
    # Campo vacío: advertir, ocultar, texto alternativo o error
    campo = {"id": "c", "tipo": "campo", "campo": "articulo.color", "x": 2, "y": 2, "w": 40, "h": 8}
    assert {p["codigo"] for p in render.componer(_diseno([campo]), {}).advertencias} == {"campo_vacio"}
    assert not render.componer(_diseno([{**campo, "si_vacio": "ocultar"}]), {}).problemas
    alt = render.componer(_diseno([{**campo, "si_vacio": "alternativo", "alternativo": "N/A"}]), {})
    assert alt.prims[-1].lineas[0][0] == "N/A"
    assert {p["codigo"] for p in render.componer(_diseno([{**campo, "si_vacio": "error"}]), {}).errores} == {"campo_obligatorio"}
    # Condición: el elemento solo aparece si el campo tiene valor
    cond = {"id": "x", "tipo": "texto", "contenido": "PREPACK", "x": 2, "y": 2, "w": 30, "h": 8,
            "condicion": {"campo": "articulo.prepack", "op": "existe"}}
    assert len(render.componer(_diseno([cond]), {}).prims) == 1  # solo el fondo
    assert len(render.componer(_diseno([cond]), {"articulo.prepack": "PPK-6"}).prims) == 2
    # Límites
    fuera = render.componer(_diseno([{"id": "f", "tipo": "rect", "x": 120, "y": 2, "w": 10, "h": 5, "relleno": "#000000"}]), {})
    assert {p["codigo"] for p in fuera.errores} == {"fuera_de_la_etiqueta"}
    parcial = render.componer(_diseno([{"id": "p", "tipo": "texto", "contenido": "x", "x": 95, "y": 2, "w": 10, "h": 5}]), {})
    assert {p["codigo"] for p in parcial.advertencias} == {"fuera_de_limites"}
    pequeno = render.componer(_diseno([{"id": "s", "tipo": "texto", "contenido": "x", "x": 3, "y": 3, "w": 10, "h": 5,
                                        "estilo": {"tam": 4, "tam_min": 3}}]), {})
    assert {p["codigo"] for p in pequeno.advertencias} == {"texto_pequeno"}


def test_formatos_de_numeros_y_fechas():
    assert render.formatear(1234.5, {"tipo": "numero", "decimales": 2}) == "1,234.50"
    assert render.formatear(1234.5, {"tipo": "numero", "decimales": 1, "miles": False}) == "1234.5"
    assert render.formatear(120, None, "numero") == "120"
    assert render.formatear("2026-10-14", {"tipo": "fecha", "fecha": "dd-mmm-aaaa"}) == "14-OCT-2026"
    assert render.formatear("2026-10-14", None, "fecha") == "14/10/2026"
    assert render.formatear("negro", {"tipo": "mayus"}) == "NEGRO"
    assert render.formatear("", None) is None


def test_hoja_de_varias_etiquetas_y_giro():
    d = svc_diseno.validar({"ancho": 60, "alto": 30, "hoja": {"modo": "hoja", "papel_ancho": 210, "papel_alto": 297,
                                                              "columnas": 3, "filas": 8, "margen_sup": 10, "margen_izq": 7,
                                                              "espacio_h": 2.5, "espacio_v": 4},
                            "elementos": [{"id": "t", "tipo": "texto", "contenido": "{{etiqueta.numero}}", "x": 18, "y": 11, "w": 24,
                                           "h": 8, "rot": 90}]})
    lienzos = [render.componer(d, {"etiqueta.numero": i}) for i in range(1, 31)]
    with pdfplumber.open(io.BytesIO(salidas.pdf(lienzos, d["hoja"]))) as doc:
        assert len(doc.pages) == 2  # 24 por hoja
        assert doc.pages[0].width == pytest.approx(210 * MM_PT, abs=0.01)
        # La segunda etiqueta queda en la columna 2: x = 7 + 60 + 2.5 mm
        textos = doc.pages[0].extract_words()
        assert len(textos) >= 24
    with Image.open(io.BytesIO(salidas.png(lienzos[0], dpi=200))) as im:
        assert im.size == (round(60 * 200 / 25.4), round(30 * 200 / 25.4))
        assert im.convert("L").getextrema()[0] < 128  # hay texto oscuro (girado, dentro de la etiqueta)
    assert not lienzos[0].problemas
    girado = render.componer(svc_diseno.validar({"ancho": 60, "alto": 30, "elementos": [
        {"id": "t", "tipo": "texto", "contenido": "x", "x": 5, "y": 5, "w": 30, "h": 10, "rot": 90}]}), {})
    assert {p["codigo"] for p in girado.advertencias} == {"fuera_de_limites"}  # girado, se sale por arriba
