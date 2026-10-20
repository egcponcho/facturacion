"""Variantes de un producto de cualquier tipo.

Cada familia del árbol de grupos de producto dice con qué atributos de variante
se distinguen las variantes de sus productos (`ejes_variante`, en orden): un
calzado por color y talla, un químico por concentración y envase, un alimento
por sabor y presentación. Una familia sin ejes usa los de su padre; sin
ninguno, valen todos los atributos activos de la empresa.

Las líneas de OC y de factura guardan los valores de variante del artículo
(`variante`) y su texto se arma en el orden de los atributos («BLACK · 9.5»).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Articulo, AtributoVariante

SEPARADOR = " · "


def atributos(db: Session) -> list[AtributoVariante]:
    """Los atributos de variante activos, en su orden (una vez por sesión)."""
    res = db.info.get("atributos_variante")
    if res is None:
        res = db.info["atributos_variante"] = list(db.scalars(
            select(AtributoVariante).where(AtributoVariante.activo.is_(True))
            .order_by(AtributoVariante.orden, AtributoVariante.codigo)))
    return res


def ejes_de_grupo(grupo) -> list[str]:
    """Los ejes de la familia o de la primera antecesora que los tenga."""
    for g in reversed(grupo.ruta() if grupo is not None else []):
        if g.ejes_variante:
            return list(g.ejes_variante)
    return []


def ejes(db: Session, articulo: Articulo | None = None) -> list[str]:
    """Con qué atributos se distinguen las variantes del producto del artículo."""
    propios = ejes_de_grupo(articulo.familia_efectiva) if articulo is not None else []
    return propios or [a.codigo for a in atributos(db)]


def ordenar(db: Session, valores: dict | None) -> dict:
    """Los valores en el orden de los atributos (los que no son atributos, al final)."""
    valores = {k: v for k, v in (valores or {}).items() if v not in (None, "")}
    orden = [a.codigo for a in atributos(db)]
    return {**{k: valores[k] for k in orden if k in valores}, **{k: v for k, v in valores.items() if k not in orden}}


def de_articulo(db: Session, a: Articulo | None) -> dict:
    """Los valores de variante del artículo, en orden."""
    return ordenar(db, a.variantes) if a is not None else {}


def texto(valores: dict | None) -> str:
    """«BLACK · 9.5»: los valores ya ordenados, separados."""
    return SEPARADOR.join(str(v) for v in (valores or {}).values() if v not in (None, ""))


def nombres(db: Session) -> dict[str, str]:
    return {a.codigo: a.nombre for a in atributos(db)}
