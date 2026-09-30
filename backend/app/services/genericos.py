"""Genéricos: el código de artículo tiene 11 dígitos; los 8 primeros son el
genérico (estilo-color) y los 3 últimos la talla (sólidos y prepacks).

Un genérico se crea una vez con sus datos maestros (estilo, color, marca,
grupo, proveedor, unidad) y luego solo se le agregan tallas con lo propio de
cada una (código de talla, UPC, SKU del proveedor). La ficha técnica y la
clasificación arancelaria son del genérico.
"""
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Articulo, GrupoArticulo, Marca, Producto, Proveedor, Usuario
from . import catalogos as cat_svc
from .common import ErrorNegocio, exigir, registrar
from .productos import asegurar_producto, descripcion_comercial_simple, producto_por_generico

RE_GEN = re.compile(r"^3\d{7}$")


def _sufijos(db: Session, gen: str) -> set[str]:
    return {s[8:] for (s,) in db.execute(select(Articulo.sku).where(Articulo.sku.startswith(gen)))}


def siguiente_sufijo(db: Session, gen: str, usados: set[str] | None = None) -> str:
    usados = usados if usados is not None else _sufijos(db, gen)
    n = max([int(x) for x in usados if x.isdigit()] or [0]) + 1
    while f"{n:03d}" in usados:
        n += 1
    if n > 999:
        raise ErrorNegocio(f"Generic {gen} has no free size codes.", 422, "sin_codigos")
    return f"{n:03d}"


def detalle(db: Session, user: Usuario, gen: str) -> dict:
    exigir(user, "catalogos.ver")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Generic {gen} does not exist.", 404, "no_encontrado")
    arts = db.scalars(select(Articulo).where(Articulo.sku.startswith(gen)).order_by(Articulo.sku)).all()
    return {
        "generico": gen, "producto_id": p.id, "estilo": p.estilo, "color": p.color, "marca_id": p.marca_id,
        "grupo_id": p.grupo_id, "proveedor_id": p.proveedor_id, "unidad": p.unidad, "nombre": p.nombre,
        "descripcion_comercial": p.descripcion_comercial,
        "tallas": [{"id": a.id, "sku": a.sku, "sufijo": a.sku[8:], "talla": a.talla, "upc": a.upc,
                    "sku_proveedor": a.sku_proveedor, "tipo": a.tipo, "activo": a.activo} for a in arts],
        "siguiente": siguiente_sufijo(db, gen),
    }


def crear(db: Session, user: Usuario, datos) -> dict:
    """Genérico nuevo con sus datos maestros y, si vienen, sus tallas."""
    exigir(user, "catalogos.editar")
    gen = (datos.generico or "").strip()
    errores = []
    if not RE_GEN.match(gen):
        errores.append({"campo": "generico", "mensaje": "The generic has 8 digits and starts with 3 (e.g. 30095125)."})
    elif producto_por_generico(db, gen) or _sufijos(db, gen):
        errores.append({"campo": "generico", "mensaje": f"Generic {gen} already exists: add sizes to it instead."})
    estilo, color = (datos.estilo or "").strip().upper(), (datos.color or "").strip()
    if not estilo or not color:
        errores.append({"campo": "estilo", "mensaje": "Style and color are required."})
    if datos.unidad not in ("PAR", "UN"):
        errores.append({"campo": "unidad", "mensaje": "The unit of a solid is PAR (pairs) or UN (units)."})
    marca, grupo, prov = db.get(Marca, datos.marca_id), db.get(GrupoArticulo, datos.grupo_id), db.get(Proveedor, datos.proveedor_id)
    if not marca or not grupo or not prov:
        errores.append({"campo": "marca_id", "mensaje": "Choose the brand, the item group and the supplier."})
    elif prov.marcas and marca.id not in {m.id for m in prov.marcas}:
        errores.append({"campo": "marca_id", "mensaje": f"{marca.codigo} is not a brand of {prov.nombre}."})
    if errores:
        raise ErrorNegocio("Check the generic.", 422, "validacion", errores)
    p = Producto(codigo_generico=gen, proveedor_id=prov.id, estilo=estilo, color=color, marca_id=marca.id,
                 grupo_id=grupo.id, unidad=datos.unidad, nombre=(datos.nombre or "").strip()[:200] or None,
                 ficha={}, faltan=[], alertas_ok=[])
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"{estilo} {color} already exists for this supplier with another generic.", 409,
                           "duplicado") from None
    p.descripcion_comercial = descripcion_comercial_simple(p)
    registrar(db, user, "genericos", p.id, "crear", {"generico": gen, "estilo": estilo, "color": color})
    creadas = agregar_tallas(db, user, gen, datos.tallas or []) if datos.tallas else []
    return {**detalle(db, user, gen), "creadas": len(creadas)}


def agregar_tallas(db: Session, user: Usuario, gen: str, tallas: list) -> list[int]:
    """Tallas nuevas de un genérico: heredan sus datos maestros."""
    exigir(user, "catalogos.editar")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Generic {gen} does not exist.", 404, "no_encontrado")
    usados = _sufijos(db, gen)
    ya = {a.talla.upper() for a in db.scalars(select(Articulo).where(Articulo.sku.startswith(gen), Articulo.tipo == "SOLIDO"))
          if a.talla}
    cat = cat_svc.CATALOGOS["articulos"]
    ids, errores = [], []
    for i, t in enumerate(tallas):
        talla = (t.talla or "").strip().upper()
        suf = (t.sufijo or "").strip()
        if not talla:
            errores.append({"campo": f"tallas.{i}", "mensaje": f"Row {i + 1}: the size is required."})
            continue
        if talla in ya:
            errores.append({"campo": f"tallas.{i}", "mensaje": f"Size {talla} already exists in generic {gen}."})
            continue
        if suf and (not re.fullmatch(r"\d{3}", suf) or suf in usados):
            errores.append({"campo": f"tallas.{i}", "mensaje": f"Row {i + 1}: size code {suf} is taken or not 3 digits."})
            continue
        suf = suf or siguiente_sufijo(db, gen, usados)
        usados.add(suf)
        ya.add(talla)
        datos = {"sku": gen + suf, "sku_proveedor": (t.sku_proveedor or "").strip() or None, "upc": (t.upc or "").strip() or None,
                 "estilo": p.estilo, "color": p.color, "talla": talla, "marca_id": p.marca_id, "grupo_id": p.grupo_id,
                 "proveedor_id": p.proveedor_id, "tipo": "SOLIDO", "unidad": p.unidad or "UN"}
        try:
            limpio = cat_svc._limpiar(db, cat, {k: v for k, v in datos.items() if v is not None}, parcial=False)
        except ErrorNegocio as e:
            errores += [{"campo": f"tallas.{i}", "mensaje": f"Size {talla}: {d['mensaje']}"} for d in e.detalle or []]
            continue
        a = Articulo(**limpio, activo=True)
        db.add(a)
        db.flush()
        asegurar_producto(db, a)
        ids.append(a.id)
    if errores:
        raise ErrorNegocio("Some sizes could not be added.", 422, "validacion", errores)
    registrar(db, user, "genericos", p.id, "tallas", {"generico": gen, "tallas": [t.talla for t in tallas]})
    return ids
