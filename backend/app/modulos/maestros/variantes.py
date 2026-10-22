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
from sqlalchemy.orm import Session, object_session

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


def de_linea(linea, db: Session | None = None) -> dict:
    """Los valores de variante guardados en una línea de OC o de factura, en orden.

    Las líneas anteriores al modelo genérico no tienen `variante`: solo las
    columnas de sistema (`color`, `talla`). Se leen con el atributo que declara
    esa columna (`atributos_variante.columna`), sin suponer su código.
    """
    db = db or object_session(linea)
    if getattr(linea, "variante", None):
        return ordenar(db, linea.variante) if db is not None else dict(linea.variante)
    if db is None:
        return {}
    return {a.codigo: getattr(linea, a.columna) for a in atributos(db)
            if a.columna and getattr(linea, a.columna, None) not in (None, "")}


def texto(valores: dict | None) -> str:
    """«BLACK · 9.5»: los valores ya ordenados, separados."""
    return SEPARADOR.join(str(v) for v in (valores or {}).values() if v not in (None, ""))


def nombres(db: Session) -> dict[str, str]:
    return {a.codigo: a.nombre for a in atributos(db)}


def texto_linea(valores: dict | None) -> str | None:
    """El texto de la variante guardada en una línea de documento (o None)."""
    return texto(valores) or None


ORDEN_LETRAS = ["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL", "4XL", "5XL"]
EQUIV_LETRAS = {"2XS": "XXS", "3XS": "XXXS", "2XL": "XXL", "3XL": "XXXL", "XXXXL": "4XL"}


def rango(valores: list) -> str:
    """Valores de un atributo en texto corto: tramos seguidos como «7–10» y
    los saltos separados por comas («7–9, 11»). Sirve para números (tallas,
    volúmenes, concentraciones), para la escala de letras S, M, L… y, si no es
    ninguna de las dos, deja la lista sin repetidos."""
    ts = [str(t).strip().upper() for t in valores if str(t or "").strip()]
    if not ts:
        return ""

    def tramos(valores: list, paso, texto) -> str:
        grupos, actual = [], [valores[0]]
        for v in valores[1:]:
            if abs((v - actual[-1]) - paso) < 1e-9:
                actual.append(v)
            else:
                grupos.append(actual)
                actual = [v]
        grupos.append(actual)
        out = []
        for g in grupos:
            if len(g) >= 3:
                out.append(f"{texto(g[0])}–{texto(g[-1])}")
            else:
                out += [texto(x) for x in g]
        return ", ".join(out)

    try:
        nums = sorted({float(t.replace(",", ".")) for t in ts})
        paso = 0.5 if any(not n.is_integer() for n in nums) else 1
        return tramos(nums, paso, lambda n: str(int(n)) if n.is_integer() else str(n))
    except ValueError:
        pass
    letras = [EQUIV_LETRAS.get(t, t) for t in ts]
    if all(t in ORDEN_LETRAS for t in letras):
        idx = sorted({ORDEN_LETRAS.index(t) for t in letras})
        return tramos(idx, 1, lambda i: ORDEN_LETRAS[i])
    return ", ".join(dict.fromkeys(ts))


def resumen(db: Session | None, articulos: list) -> str:
    """Las variantes de un producto por atributo, en texto corto: «Size 7–12 ·
    Color BLACK, WHITE» o «Concentration 5 %, 10 % · Container 1 L, 5 L». Los
    packs no cuentan: no son una variante sino una combinación de ellas."""
    if db is None:
        return ""
    por_atributo: dict[str, list] = {}
    for a in articulos:
        if getattr(a, "tipo", "SOLIDO") == "PREPACK":
            continue
        for k, v in de_articulo(db, a).items():
            por_atributo.setdefault(k, []).append(v)
    nombres_atr = nombres(db)
    return SEPARADOR.join(f"{nombres_atr.get(k, k)} {rango(vs)}" for k, vs in por_atributo.items())
