"""Valores de variante de artículos y líneas de documento.

Las reglas de orden, texto y resumen viven en el catálogo
(`catalogo/valores.py`); aquí quedan las que reciben objetos (un artículo, una
línea de OC o de factura) mientras sus usuarios pasan al servicio del catálogo.
"""
from sqlalchemy.orm import Session, object_session

from app.modelos import Articulo
from app.modulos.catalogo import valores as _valores
from app.modulos.catalogo.valores import (  # noqa: F401  (los usan quienes aún importan desde aquí)
    SEPARADOR,
    aplica,
    atributos,
    de_catalogo,
    de_grupo,
    ejes_de_grupo,
    nombres,
    olvidar,
    orden_de_valores,
    ordenados,
    ordenar,
    rango,
    texto,
)


def ordenar_producto(db: Session | None, valores: dict | None) -> dict:
    """Los valores de los atributos de producto en el orden de sus atributos."""
    return _valores.ordenar(db, valores, "PRODUCTO")


def de_articulo(db: Session, a: Articulo | None) -> dict:
    """Los valores de variante del artículo, en orden."""
    return ordenar(db, a.variantes) if a is not None else {}


def de_linea(linea, db: Session | None = None) -> dict:
    """Los valores de variante guardados en una línea de OC o de factura, en orden."""
    db = db or object_session(linea)
    if not getattr(linea, "variante", None):
        return {}
    return ordenar(db, linea.variante)


def de_producto_linea(linea, db: Session | None = None) -> dict:
    """La foto de los atributos del producto guardada en una línea (marca, modelo…), en orden."""
    return ordenar_producto(db or object_session(linea), getattr(linea, "atributos", None))


def texto_linea(valores: dict | None) -> str | None:
    """El texto de la variante guardada en una línea de documento (o None)."""
    return texto(valores) or None


def _simples(articulos: list) -> list[dict]:
    return [a.variantes for a in articulos if getattr(a, "tipo", "SOLIDO") != "PREPACK"]


def por_atributo(db: Session | None, articulos: list, ejes: list[str] | None = None) -> list[dict]:
    """Las variantes de un producto por atributo (los packs no cuentan): [{codigo, nombre, valores, texto}]."""
    return _valores.por_atributo(db, _simples(articulos), ejes)


def resumen(db: Session | None, articulos: list) -> str:
    """Las variantes de un producto por atributo, en texto corto (los packs no cuentan)."""
    return _valores.resumen(db, _simples(articulos))
