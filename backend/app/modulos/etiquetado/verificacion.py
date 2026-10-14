"""Verificación de lectura: se dibuja la etiqueta y se leen sus códigos de
barras y QR con un lector (zxing-cpp) para comprobar que dicen lo que deben.

Si el lector no está instalado en el servidor, la verificación no se hace y
se informa (nunca se da por verificada).
"""
from __future__ import annotations

import io

from app.modulos.etiquetado import render, salidas


def disponible() -> bool:
    try:
        import zxingcpp  # noqa: F401
    except ImportError:
        return False
    return True


def _esperados(diseno: dict, valores: dict, tipos: dict) -> list[tuple[dict, str]]:
    """(elemento, texto que el lector debe devolver) de cada código visible y válido."""
    res = []
    for e in diseno.get("elementos", []):
        if e.get("tipo") != "codigo" or not e.get("visible", True) or not render.cumple(e.get("condicion"), valores):
            continue
        crudo, vacios = render.valor_codigo(e, valores, tipos)
        if vacios:
            continue
        valor, error = render.validar_codigo(e["simbologia"], crudo)
        if error:
            continue
        if e["simbologia"] in ("ean13", "ean8", "upca"):
            valor = valor + str(render._digito_gs1(valor))
        res.append((e, valor))
    return res


def verificar(lienzo: render.Lienzo, diseno: dict, valores: dict, tipos: dict) -> list[dict]:
    """Problemas de lectura de los códigos de una etiqueta ya dibujada."""
    esperados = _esperados(diseno, valores, tipos)
    if not esperados:
        return []
    if not disponible():
        return [{"nivel": "info", "codigo": "verificacion_no_disponible", "elemento": None, "categoria": "codigo",
                 "mensaje": "The barcode reader is not installed on the server: the codes were validated but not read back."}]
    import zxingcpp
    from PIL import Image

    with Image.open(io.BytesIO(salidas.png(lienzo, max(lienzo.dpi, 300)))) as im:
        leidos = {x.text for x in zxingcpp.read_barcodes(im.convert("L"))}
    res = []
    for e, valor in esperados:
        if valor not in leidos:
            res.append({"nivel": "error", "codigo": "codigo_ilegible", "elemento": e.get("id"), "categoria": "codigo",
                        "nombre": e.get("nombre") or e.get("tipo"),
                        "mensaje": f"The {e['simbologia'].upper()} code «{valor}» could not be read back from the drawn label."})
    return res
