"""Categorías de etiquetado: dentro de una familia (calzado → sandalias, botas…),
como las categorías de la clasificación pero sin base oficial: la empresa las
define y las reconoce con condiciones sobre los datos del artículo y del
producto (o las pone a mano en el producto). Las reglas pueden ir a una
categoría: más específica que su familia y más general que el producto.

Una categoría en uso (reglas o productos que la tienen puesta) no se borra: se
desactiva.
"""
from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import Articulo, CategoriaEtiquetado, Producto, Usuario
from app.modulos.acceso.permisos import exigir, exigir_alguno, exigir_interno, proveedor_filtro
from app.modulos.comun.historial import registrar
from app.modulos.etiquetado import campos, familias, reglas
from app.modulos.grupos import arbol

CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{0,19}$")
MAX_PRUEBA = 20000  # artículos que se revisan al probar unas condiciones
EJEMPLOS = 20


def _dict(c: CategoriaEtiquetado, articulos: int | None = None) -> dict:
    return {"id": c.id, "familia_id": c.familia_id, "familia": c.familia.nombre if c.familia else None, "codigo": c.codigo,
            "nombre": c.nombre, "descripcion": c.descripcion, "condiciones": c.condiciones or [], "orden": c.orden,
            "activa": c.activa, "articulos": articulos}


def cargar(db: Session, categoria_id: int) -> CategoriaEtiquetado:
    c = db.get(CategoriaEtiquetado, categoria_id)
    if c is None:
        raise ErrorNegocio("The labeling category does not exist.", 404, "no_encontrado")
    return c


def _articulos(db: Session, familia_id: int | None = None) -> list[Articulo]:
    """Artículos activos (de una familia y sus subfamilias, si se indica)."""
    arts = list(db.scalars(select(Articulo).where(Articulo.activo.is_(True)).options(
        selectinload(Articulo.producto))
        .order_by(Articulo.id).limit(MAX_PRUEBA)))
    if familia_id is not None:
        arts = [a for a in arts if a.familia_efectiva is not None and familia_id in {f.id for f in a.familia_efectiva.ruta()}]
    return arts


def conteos(db: Session) -> dict:
    res: dict = {}
    cache: dict = {}
    for a in _articulos(db):
        c = reglas.categoria_de(db, a, campos.valores_articulo(a), cache)
        if c is not None:
            res[c.id] = res.get(c.id, 0) + 1
    return res


def listar(db: Session, user: Usuario, familia_id: int | None = None) -> list[dict]:
    exigir_interno(user, "etiquetas.ver", "etiquetas.configurar", "etiquetas.familias")
    c = select(CategoriaEtiquetado).order_by(CategoriaEtiquetado.familia_id, CategoriaEtiquetado.orden, CategoriaEtiquetado.id)
    if familia_id:
        c = c.where(CategoriaEtiquetado.familia_id == familia_id)
    n = conteos(db)
    return [_dict(x, n.get(x.id, 0)) for x in db.scalars(c)]


def _validar(db: Session, datos: dict, actual: CategoriaEtiquetado | None) -> dict:
    errores, limpio = [], {}
    if actual is None or "familia_id" in datos:
        try:
            limpio["familia_id"] = familias.cargar(db, int(datos.get("familia_id") or 0)).id
        except (TypeError, ValueError, ErrorNegocio):
            errores.append({"campo": "familia_id", "mensaje": "Choose the labeling family."})
    if actual is None or "codigo" in datos:
        codigo = (datos.get("codigo") or "").strip().upper()
        if not CODIGO.match(codigo):
            errores.append({"campo": "codigo", "mensaje": "Use capital letters, digits, - _ or . (up to 20)."})
        elif arbol.codigo_ocupado(db, codigo, actual.id if actual else None):
            errores.append({"campo": "codigo", "mensaje": "Another family or category has this code."})
        limpio["codigo"] = codigo
    if actual is None or "nombre" in datos:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre or len(nombre) > 100:
            errores.append({"campo": "nombre", "mensaje": "Enter the name (up to 100 characters)."})
        limpio["nombre"] = nombre
    if "descripcion" in datos:
        limpio["descripcion"] = (datos.get("descripcion") or "").strip()[:300] or None
    if "condiciones" in datos:
        limpio["condiciones"] = reglas.validar_condiciones(db, datos.get("condiciones") or [])
    if "orden" in datos:
        try:
            limpio["orden"] = max(int(datos["orden"]), 0)
        except (TypeError, ValueError):
            errores.append({"campo": "orden", "mensaje": "Write a whole number."})
    if "activa" in datos:
        limpio["activa"] = bool(datos["activa"])
    if errores:
        raise ErrorNegocio("Check the category.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "etiquetas.familias")
    limpio = _validar(db, datos, None)
    if "orden" not in limpio:
        limpio["orden"] = (db.scalar(select(func.max(CategoriaEtiquetado.orden)).where(
            CategoriaEtiquetado.familia_id == limpio["familia_id"])) or 0) + 10
    c = CategoriaEtiquetado(**{"activa": True, "condiciones": [], **limpio})
    db.add(c)
    db.flush()
    registrar(db, user, "categoria_etiquetado", c.id, "crear", {"codigo": c.codigo, "familia_id": c.familia_id})
    return _dict(c, conteos(db).get(c.id, 0))


def actualizar(db: Session, user: Usuario, categoria_id: int, datos: dict) -> dict:
    exigir(user, "etiquetas.familias")
    c = cargar(db, categoria_id)
    limpio = _validar(db, datos, c)
    if "familia_id" in limpio and limpio["familia_id"] != c.familia_id and _en_uso(db, c):
        raise ErrorNegocio("The category is in use (rules or products): it cannot move to another family.", 409, "en_uso")
    cambios = {k: [getattr(c, k), v] for k, v in limpio.items() if getattr(c, k) != v}
    for k, v in limpio.items():
        setattr(c, k, v)
    db.flush()
    if cambios:
        registrar(db, user, "categoria_etiquetado", c.id, "editar", {k: v for k, v in cambios.items() if k != "condiciones"}
                  | ({"condiciones": True} if "condiciones" in cambios else {}))
    return _dict(c, conteos(db).get(c.id, 0))


def _en_uso(db: Session, c: CategoriaEtiquetado) -> bool:
    return arbol.en_uso(db, c)


def eliminar(db: Session, user: Usuario, categoria_id: int) -> dict:
    exigir(user, "etiquetas.familias")
    c = cargar(db, categoria_id)
    if _en_uso(db, c):
        raise ErrorNegocio("The category has rules or products: deactivate it instead.", 409, "en_uso")
    registrar(db, user, "categoria_etiquetado", c.id, "eliminar", {"codigo": c.codigo})
    db.delete(c)
    db.flush()
    return {"ok": True}


def probar(db: Session, user: Usuario, datos: dict) -> dict:
    """Qué artículos de la familia caerían en una categoría con estas condiciones
    (sin guardar), cuáles ya están en otra y cuáles cambiarían; como «probar» en
    la clasificación."""
    exigir_alguno(user, "etiquetas.familias", "etiquetas.configurar")
    fam = familias.cargar(db, int(datos.get("familia_id") or 0))
    condiciones = reglas.validar_condiciones(db, datos.get("condiciones") or [])
    propia = int(datos["categoria_id"]) if datos.get("categoria_id") else None
    cache: dict = {}
    entran, ejemplos, en_otra = 0, [], 0
    revisados = _articulos(db, fam.id)
    for a in revisados:
        v = campos.valores_articulo(a)
        if not condiciones or not all(reglas.cumple_condicion(x, v) for x in condiciones):
            continue
        entran += 1
        actual = reglas.categoria_de(db, a, v, cache)
        if actual is not None and actual.id != propia:
            en_otra += 1
        if len(ejemplos) < EJEMPLOS:
            ejemplos.append({"articulo_id": a.id, "sku": a.sku, "descripcion": a.descripcion, "categoria_actual": actual.nombre if actual else None})
    return {"revisados": len(revisados), "entran": entran, "en_otra": en_otra, "ejemplos": ejemplos}


def asignar_productos(db: Session, user: Usuario, categoria_id: int | None, ids: list[int]) -> dict:
    """Pone a mano la categoría de varios productos (o la quita: vuelve a reconocerse sola)."""
    exigir(user, "etiquetas.familias")
    if not ids:
        raise ErrorNegocio("Choose the products.", 422, "validacion")
    cat = cargar(db, categoria_id) if categoria_id else None
    if cat is not None and not cat.activa:
        raise ErrorNegocio("The category is inactive.", 422, "validacion")
    c = select(Producto).where(Producto.id.in_(set(ids)))
    prov = proveedor_filtro(user)
    if prov is not None:
        c = c.where(Producto.proveedor_id.in_(prov))
    elegidos = list(db.scalars(c))
    if len(elegidos) != len(set(ids)):
        raise ErrorNegocio("Some products do not exist or are out of your scope.", 404, "no_encontrado")
    cambiados = [p for p in elegidos if p.categoria_etiquetado_id != (cat.id if cat else None)]
    if cat is not None:  # quitarla deja la misma familia
        from app.modulos.etiquetado.familias import _exigir_atributos

        _exigir_atributos(db, cambiados, cat)
    for p in cambiados:
        p.categoria_etiquetado_id = cat.id if cat else None
    db.flush()
    if cambiados:
        registrar(db, user, "categoria_etiquetado", cat.id if cat else 0, "asignar_productos",
                  {"categoria_id": cat.id if cat else None, "productos": [p.codigo_generico or p.nombre for p in cambiados[:50]]})
    return {"cambiados": len(cambiados), "elegidos": len(elegidos)}
