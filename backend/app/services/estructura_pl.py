"""Carga masiva de la estructura física de un packing list.

Una fila por producto dentro de su empaque más interno, con el identificador
de cada nivel (una columna por tipo de empaque configurado):

    Pallet | Master carton | Inner pack | Item code | PO | Quantity
    P001   | C001          | PK001      | 30095125070 |  | 6
    P001   | C001          | PK002      | 30095125070 |  | 6
    P001   | C002          |            | 30095125080 |  | 12

Las unidades con la misma estructura y contenido se agrupan (N cajas iguales),
los pesos y el volumen salen de la estructura y las taras de cada tipo, y la
cantidad de cada artículo se valida contra el packing list.
"""
from collections import defaultdict

from sqlalchemy.orm import Session

from ..models import GrupoCajas, GrupoCajasItem, TipoEmpaque, Usuario, cant as cant_norm
from . import empaques
from .common import ErrorNegocio, registrar, tocar
from .plantillas import leer, norm, plantilla


def _tipos(db: Session) -> list[TipoEmpaque]:
    """Tipos activos del más externo al más interno."""
    return sorted(empaques.tipos_activos(db), key=lambda t: -t.nivel)


def plantilla_estructura(db: Session, pl) -> bytes:
    tipos = _tipos(db)
    cols = [{"nombre": t.nombre, "ayuda": f"Identifier of the {t.nombre.lower()} (e.g. {t.prefijo or t.codigo[:2]}001). "
             "Empty if this level is not used.", "ancho": 14} for t in tipos]
    cols += [{"nombre": "Item code", "req": True, "ayuda": "Item code of a row of this packing list.", "ancho": 16},
             {"nombre": "PO", "ayuda": "Only if the same item comes from several POs.", "ancho": 12},
             {"nombre": "Quantity", "req": True, "ayuda": "Units of the item inside its innermost packaging.", "ancho": 10}]
    ejemplos = []
    lineas = [pll.factura_linea for pll in pl.lineas][:2]
    for i, fl in enumerate(lineas, 1):
        for j in (1, 2):
            fila = [f"{t.prefijo or t.codigo[:2]}{(i if t.cuenta_como == 'SOPORTE' else (i - 1) * 2 + j):03d}"
                    if t.cuenta_como != "INTERIOR" else "" for t in tipos]
            ejemplos.append(fila + [fl.codigo_sap, "", fl.casepack or 12])
    return plantilla("Packing list physical structure", cols, ejemplos, [
        "One row per item inside its innermost packaging, with the identifier of every level it is in.",
        "The columns are your packaging types (Master data › Packaging types). Leave empty the levels you do not use.",
        "Units with the same structure and contents are grouped; weights come from the unit weight of each item "
        "plus the tare of each packaging level, and the volume from the outer dimensions.",
        "Uploading replaces the current packing of this packing list.",
    ])


def importar_estructura(db: Session, user: Usuario, pl, nombre: str, contenido: bytes) -> dict:
    from .packing import _rehacer

    tipos = _tipos(db)
    alias = {"item_code": "sku", "item": "sku", "sku": "sku", "codigo_de_articulo": "sku", "articulo": "sku",
             "po": "oc", "oc": "oc", "purchase_order": "oc", "quantity": "cantidad", "qty": "cantidad", "cantidad": "cantidad"}
    for t in tipos:
        for k in (t.nombre, t.codigo, t.prefijo or ""):
            if k:
                alias[norm(k)] = f"t{t.id}"
    filas = leer(nombre, contenido, alias)
    por_id = {t.id: t for t in tipos}
    errores = []
    # Capacidad de cada fila del PL (se reemplaza el empaque actual)
    libre = {pll.id: pll.cantidad for pll in pl.lineas}
    unidades: dict[tuple, dict] = {}

    def unidad(clave, tipo, padre):
        u = unidades.get(clave)
        if u is None:
            u = unidades[clave] = {"tipo": tipo, "padre": padre, "items": defaultdict(int), "hijos": [], "id": clave[1]}
            if padre:
                unidades[padre]["hijos"].append(clave)
        elif u["padre"] != padre:
            raise ValueError(f"{tipo.nombre} {clave[1]} appears inside two different packages.")
        return clave

    for f in filas:
        ref = f"Row {f['_fila']}"
        ruta = [(por_id[int(k[1:])], (f.get(k) or "").strip().upper()) for k in sorted(
            (k for k in f if k.startswith("t") and k[1:].isdigit()), key=lambda k: -por_id[int(k[1:])].nivel)]
        ruta = [(t, i) for t, i in ruta if i]
        sku, oc = (f.get("sku") or "").strip().upper(), (f.get("oc") or "").strip()
        try:
            cant = cant_norm(float((f.get("cantidad") or "0").replace(",", ".")))
        except ValueError:
            cant = 0
        if not ruta or not sku or cant <= 0:
            errores.append({"fila": ref, "mensaje": "Enter at least one packaging identifier, the item code and a quantity."})
            continue
        malos = [f"{a.nombre} → {b.nombre}" for (a, _), (b, _) in zip(ruta, ruta[1:]) if b not in a.contiene]
        if malos:
            errores.append({"fila": ref, "mensaje": f"Not allowed by the packaging types: {', '.join(malos)}."})
            continue
        if not ruta[-1][0].contiene_productos:
            errores.append({"fila": ref, "mensaje": f"A {ruta[-1][0].nombre.lower()} does not hold products directly."})
            continue
        candidatas = [pll for pll in pl.lineas if pll.factura_linea.codigo_sap.upper() == sku
                      and (not oc or pll.factura_linea.oc_numero == oc)]
        if not candidatas:
            errores.append({"fila": ref, "mensaje": f"Item {sku} of PO {oc} is not in this packing list." if oc
                            else f"Item {sku} is not in this packing list."})
            continue
        try:
            padre = None
            for t, ident in ruta:
                padre = unidad((t.id, ident), t, padre)
        except ValueError as e:
            errores.append({"fila": ref, "mensaje": str(e)})
            continue
        resto = cant
        for pll in candidatas:
            toma = min(resto, libre[pll.id])
            if toma:
                unidades[padre]["items"][pll.id] += toma
                libre[pll.id] -= toma
                resto -= toma
        if resto:
            errores.append({"fila": ref, "mensaje": f"Item {sku}: {resto} more than the quantity in this packing list."})
    if errores:
        raise ErrorNegocio("The structure has errors; nothing was changed.", 422, "validacion", errores)
    if not unidades:
        raise ErrorNegocio("The file has no rows.", 422, "validacion")

    # Agrupar unidades iguales (misma estructura y contenido) en nodos de N unidades
    firmas: dict[tuple, tuple] = {}

    def firma(k):
        if k not in firmas:
            u = unidades[k]
            hijos = defaultdict(int)
            for h in u["hijos"]:
                hijos[firma(h)] += 1
            firmas[k] = (u["tipo"].id, tuple(sorted(u["items"].items())), tuple(sorted(hijos.items())))
        return firmas[k]

    lineas = {pll.id: pll for pll in pl.lineas}
    for g in list(pl.grupos):
        pl.grupos.remove(g)
    db.flush()
    creados = 0

    def crear(grupo: list, padre, total: int):
        nonlocal creados
        rep = unidades[grupo[0]]
        t = rep["tipo"]
        ids = sorted(unidades[k]["id"] for k in grupo)
        g = GrupoCajas(num_cajas=total, tipo_empaque=t, padre=padre, largo=t.largo, ancho=t.ancho, alto=t.alto, tara=t.tara,
                       observacion=f"IDs: {', '.join(ids[:6])}{'…' if len(ids) > 6 else ''}" if padre is None else None)
        for pll_id, n in rep["items"].items():
            g.items.append(GrupoCajasItem(pl_linea=lineas[pll_id], cantidad_por_caja=n))
        pl.grupos.append(g)
        creados += 1
        por_firma = defaultdict(list)
        for h in rep["hijos"]:
            por_firma[firma(h)].append(h)
        for hs in por_firma.values():
            crear(hs, g, total * len(hs))

    raices = defaultdict(list)
    for k, u in unidades.items():
        if u["padre"] is None:
            raices[firma(k)].append(k)
    for grupo in raices.values():
        crear(grupo, None, len(grupo))
    _rehacer(db, pl)
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "importar_estructura",
              {"unidades": len(unidades), "grupos": creados}, factura_id=pl.factura_id)
    return {"creados": creados, "actualizados": 0, "errores": [], "unidades": len(unidades), "version": pl.version}
