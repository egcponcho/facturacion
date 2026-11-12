"""Packs y kits: el contenido de un artículo compuesto, su explosión en
componentes y su carga masiva desde Excel o CSV.
"""
import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.archivos import abrir_libro
from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    ArticuloCodigo,
    ArticuloComponente,
    Usuario,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.comun.historial import registrar
from app.modulos.comun.normalizar import celda, encabezado
from app.modulos.maestros import gobierno, unidades
from app.modulos.maestros.listado import descripcion_articulo
from app.modulos.productos.productos import (
    asegurar_producto,
    codigo_valido,
)


# ---- Packs y kits: su contenido -------------------------------------------
def componentes(db: Session, user: Usuario, articulo_id: int, validar: bool = True) -> dict:
    if validar:
        exigir(user, "catalogos.ver")
    a = db.get(Articulo, articulo_id)
    if not a or a.tipo != "PREPACK":
        raise ErrorNegocio("That item is not a pack or kit.", 404, "no_encontrado")
    from app.modulos.maestros import variantes as var_svc

    return {
        "id": a.id, "sku": a.sku, "unidad": a.unidad, "codigo": a.codigo_pack, "descripcion": descripcion_articulo(a),
        "generico": a.generico, "kit": a.es_kit, "total": a.total_componentes,
        "marca": a.producto.marca_codigo if a.producto else None,
        "unidad_componentes": a.componentes[0].componente.unidad if a.componentes else None,
        "componentes": [{"articulo_id": x.componente_id, "sku": x.componente.sku, "unidad": x.componente.unidad,
                         "valores": var_svc.de_articulo(db, x.componente),
                         "variante": var_svc.texto(var_svc.de_articulo(db, x.componente)) or None,
                         "cantidad": x.cantidad} for x in a.componentes],
    }


def _validar_contenido(db: Session, items: list[dict], kit: bool = False) -> tuple[list, list]:
    """Solo artículos simples con cantidad y sin repetir artículo. Un pack junta
    variantes de un mismo producto (tallas, sabores, presentaciones…) en una misma
    unidad; un kit junta artículos de cualquier producto."""
    errores = []
    arts = []
    for it in items:
        a = db.get(Articulo, int(it.get("articulo_id") or 0))
        try:
            cant = int(it.get("cantidad") or 0)
        except (TypeError, ValueError):
            cant = 0
        if not a:
            errores.append({"mensaje": "One of the items does not exist."})
            continue
        if a.tipo != "SOLIDO":
            errores.append({"mensaje": f"{a.sku}: a pack or kit only carries simple items."})
        if cant < 1:
            errores.append({"mensaje": f"{a.sku}: the quantity must be greater than zero."})
        arts.append((a, cant))
    if not arts:
        errores.append({"mensaje": "The contents need at least one simple item."})
    if len({a.id for a, _ in arts}) != len(arts):
        errores.append({"mensaje": "An item appears twice in the contents."})
    if not kit and arts:
        producto = arts[0][0].producto_id
        otros = [a for a, _ in arts if a.producto_id != producto]
        if otros:
            lista = ", ".join(f"{a.sku} ({a.generico})" for a in otros)
            errores.append({"mensaje": f"A pack carries variants of one product ({arts[0][0].generico}): {lista} is another "
                                       "product. Use a kit."})
        if len({a.unidad for a, _ in arts}) > 1:
            errores.append({"mensaje": "The variants of a pack go in the same unit."})
    return arts, errores


def crear_compuesto(db: Session, user: Usuario, datos: dict) -> dict:
    """Crea el pack o el kit completo en un paso: su artículo con su propio código, su
    identificador (p. ej. AB12) y su contenido. Un pack es del producto de sus variantes
    y comparte su ficha; un kit es su propio producto. El contenido ya no cambia."""
    import re

    exigir(user, "catalogos.crear")
    gobierno.exigir_responsable(db, user, "articulos")
    sku = str(datos.get("sku") or "").strip().upper()
    codigo = str(datos.get("codigo") or "").strip().upper()
    kit = str(datos.get("tipo") or "PACK").upper() == "KIT"
    unidad = unidades.normalizar(datos.get("unidad")) or unidades.de_compuesto()
    errores = []
    if not codigo_valido(sku):
        errores.append({"campo": "sku", "mensaje": "Item code: letters and numbers (also . - _ /), up to 40 characters."})
    elif db.scalar(select(Articulo.id).where(Articulo.sku == sku)):
        errores.append({"campo": "sku", "mensaje": f"Code {sku} already exists in the item master."})
    if not re.fullmatch(r"[A-Z0-9]{2,10}", codigo):
        errores.append({"campo": "codigo", "mensaje": "Pack ID: letters and numbers, for example AB12."})
    if unidad not in unidades.codigos() or not unidades.contable(unidad):
        errores.append({"campo": "unidad", "mensaje": "A pack or kit is counted in whole units: choose a counted unit."})
    arts, err = _validar_contenido(db, datos.get("componentes") or [], kit=kit)
    errores += err
    base = arts[0][0] if arts else None
    # Un kit es su propio producto; un pack es del producto de sus variantes
    generico = sku if kit else (base.generico if base else None)
    if generico and not kit and not errores and db.scalar(
            select(ArticuloCodigo.id).join(Articulo).where(Articulo.producto_id == base.producto_id,
                                                          ArticuloCodigo.tipo == "PACK", ArticuloCodigo.valor == codigo)):
        errores.append({"campo": "codigo", "mensaje": f"Pack {codigo} already exists for product {generico}."})
    if errores:
        raise ErrorNegocio("The pack is not valid.", 422, "validacion", errores)
    prod = base.producto
    nombre = (prod.nombre if prod and prod.nombre else None) or generico
    total = sum(c for _, c in arts)
    descripcion = (str(datos.get("descripcion") or "").strip()[:300]
                   or (f"{nombre} kit {codigo} ({total} pieces)" if kit else
                       f"{nombre} pack {codigo} ({total} {unidades.texto(base.unidad, total)})"))
    art = Articulo(sku=sku, descripcion=descripcion, unidad=unidad, tipo="PREPACK", activo=True,
                   peso_unitario=round(sum((a.peso_unitario or 0) * c for a, c in arts), 4)
                   if all(a.peso_unitario for a, _ in arts) else None)
    if kit:
        asegurar_producto(db, art, generico, prod.proveedor_id if prod else None)
    else:
        art.producto = prod
    db.add(art)
    art.poner_codigo("PACK", codigo)
    art.poner_codigo("BARRAS", (datos.get("codigo_barras") or "").strip() or None)
    for a, cant in arts:
        art.componentes.append(ArticuloComponente(componente=a, cantidad=cant, organizacion_id=art.organizacion_id))
    db.flush()
    registrar(db, user, "articulos", art.id, "crear",
              {"sku": sku, "pack": codigo, "kit": kit, "contenido": {a.sku: c for a, c in arts}})
    return componentes(db, user, art.id)


def explosion(db: Session, user: Usuario, sku: str) -> dict:
    """Contenido de un pack o un kit, de solo lectura (para OC, factura, packing list y seguimiento)."""
    exigir(user, "oc.ver")
    a = db.scalar(select(Articulo).where(Articulo.sku == sku))
    if not a or a.tipo != "PREPACK" or not a.componentes:
        raise ErrorNegocio("That code is not a pack or kit.", 404, "no_encontrado")
    return componentes(db, user, a.id, validar=False)


# ---- Carga masiva ----------------------------------------------------------
# Columnas de las plantillas en inglés -> nombre interno (también se aceptan los internos)
COLUMNAS_EN = {"description": "descripcion", "supplier": "proveedor", "type": "tipo", "uom": "unidad", "unit": "unidad",
               "hs_code": "partida_arancelaria", "country_of_origin": "pais_origen", "pack_item_code": "sku_pack",
               "pack_id": "pack", "item_code": "sku", "quantity": "cantidad", "qty": "cantidad", "kind": "tipo"}
CAMPO_EN = {"proveedor": "Supplier"}


def _filas_archivo(nombre: str, contenido: bytes) -> list[dict]:
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        wb = abrir_libro(contenido, read_only=True, data_only=True)
        filas = [[celda(v) for v in f] for f in wb.active.iter_rows(values_only=True)]
    else:
        texto = contenido.decode("utf-8-sig", errors="replace")
        delim = ";" if texto[:2000].count(";") > texto[:2000].count(",") else ","
        filas = [[v.strip() for v in f] for f in csv.reader(io.StringIO(texto), delimiter=delim)]
    if not filas:
        return []
    enc = [COLUMNAS_EN.get(encabezado(h), encabezado(h)) for h in filas[0]]
    return [{**{enc[i]: (f[i] if i < len(f) else "") for i in range(len(enc))}, "_fila": n}
            for n, f in enumerate(filas[1:], start=2) if any(f)]


def importar_compuestos(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Columnas: sku_pack (código de artículo del pack o kit), pack (su identificador, p. ej.
    AB12), tipo (PACK o KIT), descripcion, sku (variante simple) y cantidad. Una fila por
    variante del contenido. Un compuesto que ya existe no cambia."""
    exigir(user, "catalogos.crear")
    filas = _filas_archivo(nombre, contenido)
    grupos: dict[str, dict] = {}
    errores = []
    for f in filas:
        sku_pp = (f.get("sku_pack") or f.get("sku_prepack") or "").strip().upper()
        codigo = (f.get("pack") or f.get("prepack_id") or "").strip().upper()
        sku = (f.get("sku") or "").strip()
        if not sku_pp or not codigo or not sku:
            errores.append({"fila": f["_fila"], "mensaje": "Missing pack item code, pack ID or item code."})
            continue
        a = db.scalar(select(Articulo).where(Articulo.sku == sku))
        if not a:
            errores.append({"fila": f["_fila"], "mensaje": f"Item code {sku} does not exist in the item master."})
            continue
        g = grupos.setdefault(sku_pp, {"codigo": codigo, "tipo": (f.get("tipo") or "PACK").strip().upper(),
                                       "descripcion": f.get("descripcion") or None, "items": []})
        g["items"].append({"articulo_id": a.id, "cantidad": f.get("cantidad") or 0})
    creados = sin_cambio = 0
    for sku_pp, g in grupos.items():
        existente = db.scalar(select(Articulo).where(Articulo.sku == sku_pp))
        if existente:
            actual = {x.componente_id: x.cantidad for x in existente.componentes}
            nueva = {it["articulo_id"]: int(it["cantidad"] or 0) for it in g["items"]}
            if actual == nueva:
                sin_cambio += 1
            else:
                errores.append({"fila": sku_pp, "mensaje": "The pack already exists with other contents; "
                                                           "the contents cannot change. Use a new code."})
            continue
        try:
            with db.begin_nested():
                crear_compuesto(db, user, {"sku": sku_pp, **g, "componentes": g["items"]})
            creados += 1
        except ErrorNegocio as e:
            errores.append({"fila": sku_pp, "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    return {"creados": creados, "actualizados": 0, "sin_cambio": sin_cambio, "errores": errores[:200]}
