"""Cantidades con su unidad de medida, en texto.
"""


def unidad_txt(unidad: str, cantidad: int | None = None) -> str:
    from app.modulos.maestros.unidades import texto

    return texto(unidad, cantidad)


def cant_txt(cantidad: int, unidad: str) -> str:
    return f"{cantidad:,} {unidad_txt(unidad, cantidad)}"
