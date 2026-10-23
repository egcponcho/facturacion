"""Variantes de un producto de cualquier tipo.

Cada atributo vale en sus familias (y en sus subfamilias y categorías) o, si
es general, en todas (atributo_familias). Las variantes de un producto se
distinguen por los atributos de variante que valen en su familia, en el orden
de los atributos: un calzado por color y talla, un químico por concentración y
envase, un alimento por sabor y presentación. Un producto sin familia solo
lleva atributos generales.

Las líneas de OC y de factura guardan los valores de variante del artículo
(`variante`) y su texto se arma en el orden de los atributos («BLACK · 9.5»).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session, selectinload

from app.modelos import Articulo, Atributo

SEPARADOR = " · "


def atributos(db: Session, nivel: str = "VARIANTE") -> list[Atributo]:
    """Los atributos activos de ese nivel (VARIANTE o PRODUCTO), en su orden (una vez por sesión)."""
    clave = f"atributos_{nivel}"
    res = db.info.get(clave)
    if res is None:
        res = db.info[clave] = list(db.scalars(
            select(Atributo).where(Atributo.activo.is_(True), Atributo.nivel == nivel)
            .options(selectinload(Atributo.familias)).order_by(Atributo.orden, Atributo.codigo)))
    return res


def olvidar(db: Session) -> None:
    """Después de cambiar atributos o sus familias: la próxima lectura los vuelve a cargar."""
    for k in ("atributos_VARIANTE", "atributos_PRODUCTO", "orden_valores"):
        db.info.pop(k, None)


def aplica(atributo: Atributo, grupo) -> bool:
    """El atributo vale en el grupo (familia o categoría): es general o es de él o de una familia que lo contiene."""
    if atributo.general:
        return True
    ruta = {g.id for g in grupo.ruta()} if grupo is not None else set()
    return any(f.id in ruta for f in atributo.familias)


def de_grupo(db: Session, grupo, nivel: str = "VARIANTE") -> list[Atributo]:
    """Los atributos activos de ese nivel que valen en el grupo, en su orden."""
    return [a for a in atributos(db, nivel) if aplica(a, grupo)]


def ejes_de_grupo(db: Session, grupo) -> list[str]:
    """Con qué atributos se distinguen las variantes de los productos del grupo, en orden."""
    return [a.codigo for a in de_grupo(db, grupo)]


def ordenar(db: Session, valores: dict | None) -> dict:
    """Los valores en el orden de los atributos (los que no son atributos, al final)."""
    valores = {k: v for k, v in (valores or {}).items() if v not in (None, "")}
    orden = [a.codigo for a in atributos(db)]
    return {**{k: valores[k] for k in orden if k in valores}, **{k: v for k, v in valores.items() if k not in orden}}


def ordenar_producto(db: Session | None, valores: dict | None) -> dict:
    """Los valores de los atributos de producto en el orden de sus atributos."""
    valores = {k: v for k, v in (valores or {}).items() if v not in (None, "")}
    if db is None:
        return valores
    orden = [a.codigo for a in atributos(db, "PRODUCTO")]
    return {**{k: valores[k] for k in orden if k in valores}, **{k: v for k, v in valores.items() if k not in orden}}


def de_articulo(db: Session, a: Articulo | None) -> dict:
    """Los valores de variante del artículo, en orden."""
    return ordenar(db, a.variantes) if a is not None else {}


def de_linea(linea, db: Session | None = None) -> dict:
    """Los valores de variante guardados en una línea de OC o de factura, en orden."""
    db = db or object_session(linea)
    if not getattr(linea, "variante", None):
        return {}
    return ordenar(db, linea.variante) if db is not None else dict(linea.variante)


def de_producto_linea(linea, db: Session | None = None) -> dict:
    """La foto de los atributos del producto guardada en una línea (marca, modelo…), en orden."""
    return ordenar_producto(db or object_session(linea), getattr(linea, "atributos", None))


def texto(valores: dict | None) -> str:
    """«BLACK · 9.5»: los valores ya ordenados, separados."""
    return SEPARADOR.join(str(v) for v in (valores or {}).values() if v not in (None, ""))


def nombres(db: Session) -> dict[str, str]:
    return {a.codigo: a.nombre for a in (*atributos(db), *atributos(db, "PRODUCTO"))}


def texto_linea(valores: dict | None) -> str | None:
    """El texto de la variante guardada en una línea de documento (o None)."""
    return texto(valores) or None


def rango(valores: list, orden: list[str] | None = None) -> str:
    """Valores de un atributo en texto corto: tramos seguidos como «7–10» y los
    saltos separados por comas («7–9, 11»). Los números se ordenan como números;
    los demás valores, en el orden que la empresa les dio (las opciones del
    atributo o sus escalas de valores: S, M, L… o 250 ml, 500 ml, 1 L) y, si no
    están ahí, en el orden en que aparecen."""
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
    lista = [str(x).strip().upper() for x in (orden or [])]
    if lista and all(t in lista for t in ts):
        idx = sorted({lista.index(t) for t in ts})
        return tramos(idx, 1, lambda i: lista[i])
    return ", ".join(dict.fromkeys(ts))


def orden_de_valores(db: Session) -> dict[str, list[str]]:
    """{atributo: valores en orden}: sus opciones y los valores de sus escalas (una vez por sesión)."""
    res = db.info.get("orden_valores")
    if res is None:
        from app.modelos import EscalaValores

        res = {}
        for a in atributos(db):
            res[a.codigo] = [o.strip() for o in (a.opciones or "").split(",") if o.strip()]
        for e in db.scalars(select(EscalaValores).where(EscalaValores.activo.is_(True)).order_by(EscalaValores.id)):
            lista = res.setdefault(e.atributo, [])
            lista += [x["valor"] for x in e.lista_valores or [] if x.get("valor") and x["valor"] not in lista]
        db.info["orden_valores"] = res
    return res


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
    nombres_atr, orden = nombres(db), orden_de_valores(db)
    return SEPARADOR.join(f"{nombres_atr.get(k, k)} {rango(vs, orden.get(k))}" for k, vs in por_atributo.items())


def de_catalogo(db: Session | None, valores: dict | None, catalogo: str) -> str | None:
    """El valor del atributo de producto que apunta a ese catálogo (la marca: «marcas»), si lo hay."""
    if db is None or not valores:
        return None
    return next((valores[a.codigo] for a in atributos(db, "PRODUCTO") if a.catalogo == catalogo and valores.get(a.codigo)), None)
