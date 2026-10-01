"""Estructura física del packing list: un árbol de empaques dentro de empaques.

Cada nodo (GrupoCajas) son N unidades iguales de un tipo de empaque
configurable. `num_cajas` es el total de esas unidades en el PL; si el nodo
tiene padre, se reparten por igual entre las unidades del padre:

    Pallet ×1
      └ Caja ×10            (10 cajas en el pallet)
          └ Inner pack ×40  (4 inner por caja)
              └ producto: 6 pares por inner

Pesos por unidad, de abajo hacia arriba:
    neto  = Σ artículos (peso unitario del artículo × cantidad) + neto de los hijos
    tara  = tara propia + tara de los hijos
    bruto = neto + tara
Ej.: 10 kg de producto + 4 inner de 0.075 kg + caja de 0.7 kg = 11 kg por caja;
10 cajas sobre un pallet de 20 kg = 130 kg.

El volumen (CBM) es el de las medidas exteriores de los nodos raíz: lo que va
dentro de otro empaque no suma volumen.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GrupoCajas, PackingList, TipoEmpaque

CUENTA = {"BULTO": "Package", "INTERIOR": "Inner unit", "SOPORTE": "Support (pallet)"}
IDENTIFICADORES = {"SERIAL": "Serial number", "CODIGO_BARRAS": "Barcode", "SSCC": "SSCC (GS1)"}


# ---- Peso de los artículos --------------------------------------------------
def peso_articulo(articulo) -> float | None:
    """Peso neto de una unidad del artículo. Un prepack sin peso propio suma el
    de sus sólidos (curva × peso de cada talla)."""
    if not articulo:
        return None
    if articulo.peso_unitario:
        return articulo.peso_unitario
    if articulo.tipo == "PREPACK" and articulo.prepack and articulo.prepack.componentes:
        pesos = [(c.cantidad, c.articulo.peso_unitario) for c in articulo.prepack.componentes]
        if all(p for _, p in pesos):
            return round(sum(n * p for n, p in pesos), 4)
    return None


def peso_linea(fl) -> float | None:
    """Peso unitario de una línea de factura (del artículo de su posición de OC)."""
    return peso_articulo(fl.posicion_oc.articulo if fl.posicion_oc else None)


# ---- Árbol ------------------------------------------------------------------
def raices(pl: PackingList) -> list[GrupoCajas]:
    return [g for g in pl.grupos if g.padre is None]


def hijos(pl: PackingList, g: GrupoCajas) -> list[GrupoCajas]:
    return [h for h in pl.grupos if h.padre is g]


def por_padre(g: GrupoCajas, hijo: GrupoCajas) -> float:
    """Unidades del hijo dentro de cada unidad del padre."""
    return hijo.num_cajas / g.num_cajas if g.num_cajas else 0


def descendientes(pl: PackingList, g: GrupoCajas) -> list[GrupoCajas]:
    res = []
    for h in hijos(pl, g):
        res.append(h)
        res.extend(descendientes(pl, h))
    return res


def ancestros(g: GrupoCajas) -> list[GrupoCajas]:
    res, p = [], g.padre
    while p is not None and p not in res:
        res.append(p)
        p = p.padre
    return res


def contenido(pl: PackingList, g: GrupoCajas) -> list[tuple]:
    """Producto que lleva una unidad del nodo, contando lo que va en sus
    empaques internos: [(pl_linea, cantidad por unidad)]."""
    tot: dict = {}
    orden = []
    for it in g.items:
        if it.pl_linea not in tot:
            orden.append(it.pl_linea)
        tot[it.pl_linea] = tot.get(it.pl_linea, 0) + it.cantidad_por_caja
    for h in hijos(pl, g):
        f = por_padre(g, h)
        for pll, n in contenido(pl, h):
            if pll not in tot:
                orden.append(pll)
            tot[pll] = tot.get(pll, 0) + n * f
    return [(pll, int(tot[pll]) if float(tot[pll]).is_integer() else tot[pll]) for pll in orden]


def nodo_bulto(g: GrupoCajas) -> GrupoCajas:
    """El bulto que contiene a un nodo interno (o el mismo nodo)."""
    for x in [g, *ancestros(g)]:
        if cuenta_como(x) == "BULTO":
            return x
    return g


def cuenta_como(g: GrupoCajas) -> str:
    return g.tipo_empaque.cuenta_como if g.tipo_empaque else "BULTO"


def prefijo(g: GrupoCajas) -> str:
    t = g.tipo_empaque
    return (t.prefijo or t.codigo[:2]) if t else "C"


def nombre_tipo(g: GrupoCajas) -> str:
    return g.tipo_empaque.nombre if g.tipo_empaque else "Carton"


# ---- Pesos ------------------------------------------------------------------
def recalcular(pl: PackingList) -> None:
    """Calcula el peso neto y bruto por unidad de cada nodo (de las hojas a la
    raíz) y lo guarda en el nodo. Sin el peso de algún artículo, el neto propio
    es el escrito a mano (neto_manual) y queda por confirmar."""
    hechos: dict[int, tuple] = {}

    def calc(g: GrupoCajas, visitados: set) -> tuple:
        if id(g) in hechos:
            return hechos[id(g)]
        if id(g) in visitados:  # ciclo: no debería pasar (se valida al anidar)
            return (None, g.tara or 0)
        visitados = visitados | {id(g)}
        pesos = [(it.cantidad_por_caja, peso_linea(it.pl_linea.factura_linea)) for it in g.items]
        if all(p is not None for _, p in pesos):
            neto = sum(n * p for n, p in pesos)
            g.peso_estimado = False
        else:
            neto = g.neto_manual
        tara = g.tara or 0
        for h in hijos(pl, g):
            hn, ht = calc(h, visitados)
            f = por_padre(g, h)
            neto = None if neto is None or hn is None else neto + hn * f
            tara += ht * f
        g.peso_neto_caja = round(neto, 4) if neto is not None else None
        g.peso_bruto_caja = round(neto + tara, 4) if neto is not None else None
        hechos[id(g)] = (neto, tara)
        return hechos[id(g)]

    for g in pl.grupos:
        calc(g, set())


def calculado(g: GrupoCajas) -> bool:
    """El neto sale completo del peso de los artículos (no se escribió a mano)."""
    return all(peso_linea(it.pl_linea.factura_linea) is not None for it in g.items)


# ---- Numeración y etiquetas -------------------------------------------------
def numeracion(pl: PackingList) -> dict[int, tuple[int, int]]:
    """Rango de numeración de cada nodo dentro de su tipo de empaque
    (C1–C10, PK1–PK40, P1), en el orden del PL."""
    res, sig = {}, defaultdict(lambda: 1)
    for g in _orden_arbol(pl):
        k = prefijo(g)
        res[g.id] = (sig[k], sig[k] + g.num_cajas - 1)
        sig[k] += g.num_cajas
    return res


def _orden_arbol(pl: PackingList) -> list[GrupoCajas]:
    """Nodos en orden de lectura: cada raíz seguida de sus hijos."""
    out = []

    def visitar(g, vistos):
        if id(g) in vistos:
            return
        vistos.add(id(g))
        out.append(g)
        for h in hijos(pl, g):
            visitar(h, vistos)

    vistos: set = set()
    for g in raices(pl):
        visitar(g, vistos)
    for g in pl.grupos:  # por si quedó algo suelto
        visitar(g, vistos)
    return out


def rango_txt(pl: PackingList, g: GrupoCajas, rangos=None) -> str:
    d, h = (rangos or numeracion(pl))[g.id]
    p = prefijo(g)
    return f"{p}{d}" if d == h else f"{p}{d}–{p}{h}"


# ---- Totales ----------------------------------------------------------------
def volumen(g: GrupoCajas) -> float | None:
    if g.largo and g.ancho and g.alto:
        return g.largo * g.ancho * g.alto / 1_000_000
    return None


def totales(pl: PackingList) -> dict:
    """Peso y volumen del PL desde su estructura: se suman los nodos raíz
    (cada uno ya incluye lo que lleva dentro)."""
    neto = bruto = cbm = 0.0
    sin_peso = 0
    for g in raices(pl):
        if g.peso_neto_caja is None:
            sin_peso += g.num_cajas
        neto += (g.peso_neto_caja or 0) * g.num_cajas
        bruto += (g.peso_bruto_caja or 0) * g.num_cajas
        cbm += (volumen(g) or 0) * g.num_cajas
    por_tipo: dict[str, dict] = {}
    for g in pl.grupos:
        k = g.tipo_empaque.codigo if g.tipo_empaque else "CAJA"
        d = por_tipo.setdefault(k, {"codigo": k, "nombre": nombre_tipo(g), "cuenta_como": cuenta_como(g), "unidades": 0})
        d["unidades"] += g.num_cajas
    return {
        "bultos": sum(g.num_cajas for g in pl.grupos if cuenta_como(g) == "BULTO"),
        "soportes": sum(g.num_cajas for g in pl.grupos if cuenta_como(g) == "SOPORTE"),
        "peso_neto": round(neto, 3), "peso_bruto": round(bruto, 3), "cbm": round(cbm, 4),
        "sin_peso": sin_peso, "por_tipo": sorted(por_tipo.values(), key=lambda x: x["codigo"]),
    }


# ---- Validaciones -----------------------------------------------------------
def validar(pl: PackingList, rangos=None) -> list[dict]:
    """Capacidad, peso, mezcla y relaciones permitidas entre tipos de empaque."""
    rangos = rangos or numeracion(pl)
    errores = []
    for g in pl.grupos:
        t = g.tipo_empaque
        nom = f"{nombre_tipo(g)} {rango_txt(pl, g, rangos)}"
        hs = hijos(pl, g)
        p = g.padre
        if p is not None:
            if g.num_cajas % p.num_cajas:
                errores.append({"grupo_id": g.id, "mensaje": f"{nom}: {g.num_cajas} units cannot be split evenly "
                                f"into {p.num_cajas} {nombre_tipo(p).lower()} units."})
            if p.tipo_empaque and t and t not in p.tipo_empaque.contiene:
                errores.append({"grupo_id": g.id, "mensaje": f"{nom}: a {p.tipo_empaque.nombre.lower()} cannot "
                                f"contain a {t.nombre.lower()} (packaging types)."})
        if not t:
            continue
        if g.items and not t.contiene_productos:
            errores.append({"grupo_id": g.id, "mensaje": f"{nom}: a {t.nombre.lower()} does not hold products "
                            "directly; put them in an inner packaging."})
        cont = contenido(pl, g)
        unidades = sum(n for _, n in cont)
        if t.max_unidades and unidades > t.max_unidades:
            errores.append({"grupo_id": g.id, "mensaje": f"{nom}: {unidades:g} units per {t.nombre.lower()}; "
                            f"the maximum is {t.max_unidades}."})
        internos = sum(por_padre(g, h) for h in hs)
        if t.max_contenido and internos > t.max_contenido:
            errores.append({"grupo_id": g.id, "mensaje": f"{nom}: {internos:g} inner units per {t.nombre.lower()}; "
                            f"the maximum is {t.max_contenido}."})
        if t.peso_max and g.peso_bruto_caja and g.peso_bruto_caja > t.peso_max:
            errores.append({"grupo_id": g.id, "mensaje": f"{nom}: {g.peso_bruto_caja:g} kg gross per unit; "
                            f"the maximum is {t.peso_max:g} kg."})
        lineas = [pll for pll, _ in cont]
        if not t.mezcla_productos and len({(x.factura_linea.estilo, x.factura_linea.color) for x in lineas}) > 1:
            errores.append({"grupo_id": g.id, "mensaje": f"{nom}: a {t.nombre.lower()} cannot mix products."})
        if not t.mezcla_tallas and len({x.factura_linea.talla for x in lineas}) > 1:
            errores.append({"grupo_id": g.id, "mensaje": f"{nom}: a {t.nombre.lower()} cannot mix sizes."})
        if not t.mezcla_oc and len({x.factura_linea.oc_numero for x in lineas}) > 1:
            errores.append({"grupo_id": g.id, "mensaje": f"{nom}: a {t.nombre.lower()} cannot mix POs."})
    return errores


# ---- Tipos ------------------------------------------------------------------
def tipos_activos(db: Session) -> list[TipoEmpaque]:
    return list(db.scalars(select(TipoEmpaque).where(TipoEmpaque.activo).order_by(TipoEmpaque.nivel, TipoEmpaque.codigo)))


def tipo_bulto(db: Session) -> TipoEmpaque | None:
    """Tipo por defecto de una caja con producto: el bulto de menor nivel que lleva producto."""
    return next((t for t in tipos_activos(db) if t.cuenta_como == "BULTO" and t.contiene_productos), None)


def tipo_interior(tipo: TipoEmpaque | None) -> TipoEmpaque | None:
    """Empaque interno con producto que puede ir dentro de `tipo` (p. ej. el
    inner pack de una caja)."""
    if not tipo:
        return None
    return next((t for t in tipo.contiene if t.activo and t.contiene_productos and t.nivel < tipo.nivel), None)


def tipo_soporte(db: Session) -> TipoEmpaque | None:
    return next((t for t in tipos_activos(db) if t.cuenta_como == "SOPORTE"), None)


def tipo_dict(t: TipoEmpaque) -> dict:
    return {"id": t.id, "codigo": t.codigo, "nombre": t.nombre, "nivel": t.nivel, "prefijo": t.prefijo,
            "cuenta_como": t.cuenta_como, "largo": t.largo, "ancho": t.ancho, "alto": t.alto, "tara": t.tara,
            "peso_max": t.peso_max, "max_unidades": t.max_unidades, "max_contenido": t.max_contenido,
            "contiene_productos": t.contiene_productos, "contiene": [x.id for x in t.contiene]}
