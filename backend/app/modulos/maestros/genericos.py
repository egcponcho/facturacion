"""Genéricos: agrupan las tallas (sólidos) y prepacks de un estilo-color. El
código del genérico y el de cada artículo los define la empresa (numéricos o
alfanuméricos); si el código de una talla no se escribe, se arma con el
genérico más un código de talla.

Un genérico se crea una vez con sus datos maestros (estilo, color, marca,
grupo, proveedor, unidad) y luego solo se le agregan tallas con lo propio de
cada una (código de talla, UPC, SKU del proveedor). La ficha técnica y la
clasificación arancelaria son del genérico.
"""
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Articulo, EscalaTalla, GrupoArticulo, Marca, Producto, Proveedor, Usuario
from app.modulos.acceso.permisos import exigir
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto
from app.modulos.maestros import catalogos as cat_svc
from app.modulos.maestros import tallas as tallas_svc
from app.modulos.maestros.unidades import DE_ARTICULO, normalizar
from app.modulos.productos.productos import (
    MSG_CODIGO,
    asegurar_producto,
    codigo_valido,
    descripcion_comercial_simple,
    producto_por_generico,
)


def _articulos(db: Session, gen: str):
    return select(Articulo).where(Articulo.generico == gen)


def _sufijos(db: Session, gen: str) -> set[str]:
    """Códigos de talla ya usados: lo que sigue al genérico en el código de artículo."""
    return {s[len(gen):] for (s,) in db.execute(select(Articulo.sku).where(Articulo.sku.startswith(gen)))}


def sufijo_convencional(talla: str | None) -> str | None:
    """Código de talla usual: la talla numérica por 10 (7 → 070, 7.5 → 075,
    10.5 → 105, 13 → 130). Tallas de letra o prepacks no tienen uno fijo."""
    t = (talla or "").strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,2}(\.\d)?", t):
        return None
    n = round(float(t) * 10)
    return f"{n:03d}" if 0 < n < 1000 and abs(float(t) * 10 - n) < 1e-9 else None


def siguiente_sufijo(db: Session, gen: str, usados: set[str] | None = None, talla: str | None = None, escala=None) -> str:
    """Código de talla para una talla nueva: el de su escala de tallas (o, sin
    escala, la regla usual talla × 10); si está usado, el siguiente libre."""
    usados = usados if usados is not None else _sufijos(db, gen)
    return tallas_svc.codigo(escala, talla, usados)


def detalle(db: Session, user: Usuario, gen: str) -> dict:
    exigir(user, "catalogos.ver")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Generic {gen} does not exist.", 404, "no_encontrado")
    arts = db.scalars(_articulos(db, gen).order_by(Articulo.sku)).all()
    return {
        "generico": gen, "producto_id": p.id, "estilo": p.estilo, "color": p.color, "marca_id": p.marca_id,
        "grupo_id": p.grupo_id, "proveedor_id": p.proveedor_id, "unidad": p.unidad, "nombre": p.nombre,
        "descripcion_comercial": p.descripcion_comercial,
        "tallas": [{"id": a.id, "sku": a.sku, "sufijo": a.sku[len(gen):] if a.sku.startswith(gen) else "", "talla": a.talla, "upc": a.upc,
                    "sku_proveedor": a.sku_proveedor, "tipo": a.tipo, "activo": a.activo} for a in arts],
        "siguiente": siguiente_sufijo(db, gen), "usados": sorted(a.sku[len(gen):] for a in arts if a.sku.startswith(gen)),
    }


def crear(db: Session, user: Usuario, datos) -> dict:
    """Genérico nuevo con sus datos maestros y, si vienen, sus tallas."""
    exigir(user, "catalogos.crear")
    gen = (datos.generico or "").strip().upper()
    errores = []
    if not codigo_valido(gen):
        errores.append({"campo": "generico", "mensaje": f"Generic code: {MSG_CODIGO}"})
    elif producto_por_generico(db, gen) or db.scalar(_articulos(db, gen).limit(1)):
        errores.append({"campo": "generico", "mensaje": f"Generic {gen} already exists: add sizes to it instead."})
    estilo, color = (datos.estilo or "").strip().upper(), (datos.color or "").strip()
    if not estilo or not color:
        errores.append({"campo": "estilo", "mensaje": "Style and color are required."})
    if normalizar(datos.unidad) not in DE_ARTICULO:
        errores.append({"campo": "unidad", "mensaje": f"The unit of a solid is one of {', '.join(DE_ARTICULO)}."})
    marca, grupo, prov = db.get(Marca, datos.marca_id), db.get(GrupoArticulo, datos.grupo_id), db.get(Proveedor, datos.proveedor_id)
    if not marca or not grupo or not prov:
        errores.append({"campo": "marca_id", "mensaje": "Choose the brand, the item group and the supplier."})
    elif marca.id not in {m.id for m in prov.marcas}:
        # Solo las marcas autorizadas al proveedor (Datos maestros → Proveedores)
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
    creadas = agregar_tallas(db, user, gen, datos.tallas or [], getattr(datos, "escala_id", None)) if datos.tallas else []
    return {**detalle(db, user, gen), "creadas": len(creadas)}


def agregar_tallas(db: Session, user: Usuario, gen: str, tallas: list, escala_id: int | None = None) -> list[int]:
    """Tallas nuevas de un genérico: heredan sus datos maestros."""
    exigir(user, "catalogos.crear")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Generic {gen} does not exist.", 404, "no_encontrado")
    usados = _sufijos(db, gen)
    escala = db.get(EscalaTalla, escala_id) if escala_id else None
    ya = {a.talla.upper() for a in db.scalars(_articulos(db, gen).where(Articulo.tipo == "SOLIDO")) if a.talla}
    cat = cat_svc.CATALOGOS["articulos"]
    ids, errores = [], []
    for i, t in enumerate(tallas):
        talla = (t.talla or "").strip().upper()
        suf = (t.sufijo or "").strip().upper()
        sku = (getattr(t, "sku", None) or "").strip().upper()
        if not talla:
            errores.append({"campo": f"tallas.{i}", "mensaje": f"Row {i + 1}: the size is required."})
            continue
        if talla in ya:
            errores.append({"campo": f"tallas.{i}", "mensaje": f"Size {talla} already exists in generic {gen}."})
            continue
        if sku:
            if not codigo_valido(sku) or db.scalar(select(Articulo.id).where(Articulo.sku == sku)):
                errores.append({"campo": f"tallas.{i}", "mensaje": f"Row {i + 1}: item code {sku} is taken or not valid."})
                continue
        else:
            if suf and (not re.fullmatch(r"[A-Z0-9._\-/]{1,20}", suf) or suf in usados):
                errores.append({"campo": f"tallas.{i}", "mensaje": f"Row {i + 1}: size code {suf} is taken or not valid."})
                continue
            suf = suf or siguiente_sufijo(db, gen, usados, talla, escala)
            usados.add(suf)
            sku = gen + suf
        ya.add(talla)
        datos = {"sku": sku, "generico": gen, "sku_proveedor": (t.sku_proveedor or "").strip() or None, "upc": (t.upc or "").strip() or None,
                 "estilo": p.estilo, "color": p.color, "talla": talla, "marca_id": p.marca_id, "grupo_id": p.grupo_id,
                 "proveedor_id": p.proveedor_id, "tipo": "SOLIDO", "unidad": p.unidad or "UN",
                 "peso_unitario": getattr(t, "peso_unitario", None)}
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


ORDEN = {"generico": Producto.codigo_generico, "estilo": Producto.estilo, "color": Producto.color}


def listar(db: Session, user: Usuario, filtros: dict, orden: str | None, page: int, size: int) -> dict:
    """Vista compacta de artículos: un renglón por genérico con sus datos y
    sus tallas; se despliega para ver cada artículo."""
    from sqlalchemy import func, or_

    from app.modulos.acceso.permisos import proveedor_filtro
    from app.modulos.productos.productos import ESTADOS, fmt_codigo, rango_tallas

    exigir(user, "catalogos.ver")
    q = select(Producto).where(Producto.codigo_generico.is_not(None))
    prov = proveedor_filtro(user, filtros.get("proveedor_id"))
    if prov:
        q = q.where(Producto.proveedor_id == int(prov))
    for campo in ("marca_id", "grupo_id"):
        if filtros.get(campo):
            q = q.where(getattr(Producto, campo).in_([int(x) for x in str(filtros[campo]).split(",") if x.strip().isdigit()]))
    if filtros.get("unidad"):
        q = q.where(Producto.unidad == filtros["unidad"])
    if filtros.get("q"):
        q = q.where(filtro_texto(filtros["q"], lambda t: [
            Producto.codigo_generico.ilike(t), Producto.estilo.ilike(t), Producto.color.ilike(t),
            Producto.id.in_(select(Articulo.producto_id).where(or_(Articulo.sku.ilike(t), Articulo.upc.ilike(t), Articulo.sku_proveedor.ilike(t))))]))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    col, _, d = (orden or "generico:asc").partition(":")
    c = ORDEN.get(col, Producto.codigo_generico)
    filas = db.scalars(q.order_by(c.desc() if d == "desc" else c.asc(), Producto.id).offset((page - 1) * size).limit(size)).all()
    arts: dict[int, list] = {}
    if filas:
        for a in db.scalars(select(Articulo).where(Articulo.producto_id.in_([p.id for p in filas])).order_by(Articulo.sku)):
            arts.setdefault(a.producto_id, []).append(a)
    items = []
    for p in filas:
        ls = arts.get(p.id, [])
        solidos = [a for a in ls if a.tipo == "SOLIDO"]
        items.append({
            "generico": p.codigo_generico, "producto_id": p.id, "estilo": p.estilo, "color": p.color,
            "marca_id": p.marca_id, "marca": p.marca.codigo if p.marca else None, "marca_nombre": p.marca.nombre if p.marca else None,
            "grupo_id": p.grupo_id, "grupo": p.grupo.codigo if p.grupo else None,
            "proveedor_id": p.proveedor_id, "proveedor": p.proveedor.nombre if p.proveedor else None,
            "unidad": p.unidad, "tallas": [a.talla for a in solidos], "rango_tallas": rango_tallas([a.talla for a in solidos]),
            "n_tallas": len(solidos), "n_prepacks": len(ls) - len(solidos), "activos": sum(1 for a in ls if a.activo),
            "descripcion_comercial": p.descripcion_comercial, "estado": p.estado, "estado_txt": ESTADOS.get(p.estado, p.estado),
            "codigo": fmt_codigo(p.codigo) if p.codigo else None,
        })
    return {"items": items, "total": total, "page": page, "size": size}


def editar(db: Session, user: Usuario, gen: str, datos) -> dict:
    """Cambia los datos maestros del genérico y los pasa a todas sus tallas."""
    exigir(user, "catalogos.editar")
    p = producto_por_generico(db, gen)
    if not p:
        raise ErrorNegocio(f"Generic {gen} does not exist.", 404, "no_encontrado")
    arts = db.scalars(_articulos(db, gen)).all()
    estilo, color = (datos.estilo or p.estilo).strip().upper(), (datos.color or p.color or "").strip()
    errores = []
    if (estilo != p.estilo or color != (p.color or "")) and any(a.tipo == "PREPACK" for a in arts):
        errores.append({"campo": "estilo", "mensaje": "The generic has prepacks: its style and color cannot change."})
    if normalizar(datos.unidad) not in DE_ARTICULO:
        errores.append({"campo": "unidad", "mensaje": f"The unit is one of {', '.join(DE_ARTICULO)}."})
    marca, grupo, prov = db.get(Marca, datos.marca_id), db.get(GrupoArticulo, datos.grupo_id), db.get(Proveedor, datos.proveedor_id)
    if not marca or not grupo or not prov:
        errores.append({"campo": "marca_id", "mensaje": "Choose the brand, the item group and the supplier."})
    elif marca.id not in {m.id for m in prov.marcas}:
        # Solo las marcas autorizadas al proveedor (Datos maestros → Proveedores)
        errores.append({"campo": "marca_id", "mensaje": f"{marca.codigo} is not a brand of {prov.nombre}."})
    if errores:
        raise ErrorNegocio("Check the generic.", 422, "validacion", errores)
    antes = {"estilo": p.estilo, "color": p.color, "marca_id": p.marca_id, "grupo_id": p.grupo_id,
             "proveedor_id": p.proveedor_id, "unidad": p.unidad}
    p.estilo, p.color, p.marca_id, p.grupo_id, p.proveedor_id, p.unidad = estilo, color, marca.id, grupo.id, prov.id, datos.unidad
    for a in arts:
        a.marca_id, a.grupo_id, a.proveedor_id = marca.id, grupo.id, prov.id
        if a.tipo == "SOLIDO":
            a.estilo, a.color, a.unidad = estilo, color, datos.unidad
    try:
        db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"{estilo} {color} already exists for this supplier with another generic.", 409, "duplicado") from None
    if not (p.ficha or {}).get("comManual"):
        db.refresh(p)
        p.descripcion_comercial = descripcion_comercial_simple(p)
    registrar(db, user, "genericos", p.id, "editar", {"generico": gen, "antes": antes})
    return detalle(db, user, gen)
