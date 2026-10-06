"""Dominios y categorías de producto como configuración (CRUD).

Agregar un dominio nuevo (p. ej. ELECTRONICS) con sus categorías, atributos,
ámbitos y reglas, y habilitar sus capítulos, basta para que la ficha lo
ofrezca y el motor lo clasifique: no hace falta programar una ficha.
"""
import json
import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CategoriaProducto, DominioClasificacion, Usuario
from .common import ErrorNegocio, exigir, registrar

DATOS = Path(__file__).resolve().parent.parent / "data"
DOMINIO_GRUPO = {"prenda": "APPAREL", "calzado": "FOOTWEAR", "calzado_acc": "FOOTWEAR"}
# Categorías iniciales de los dominios que no tienen ficha especializada
GENERICAS = [("quimico", "Chemical product", "CHEMICALS", "Chemicals and raw materials", "chemical; reagent; solvent; acid; químico"),
             ("materia_prima", "Raw material or semi-processed input", "RAW_MATERIALS", "Chemicals and raw materials",
              "raw material; yarn; resin; sheet; materia prima"),
             ("otro", "Other product", None, "Other", "other; otro")]


def sembrar(db: Session) -> int:
    """Categorías iniciales (motor_atributos.json y las genéricas por dominio).
    Crea las que faltan y completa los campos vacíos; la base manda después."""
    datos = json.loads((DATOS / "motor_atributos.json").read_text(encoding="utf-8"))
    existentes = {c.codigo: c for c in db.scalars(select(CategoriaProducto))}
    n = 0
    filas = [{**c, "dominio": DOMINIO_GRUPO.get(c.get("familia") or "", "ACCESSORIES_MERCH")} for c in datos["categorias"]]
    filas += [{"codigo": cod, "nombre": nombre, "grupo": grupo, "dominio": dom, "alias": alias, "orden": 5000 + i}
              for i, (cod, nombre, dom, grupo, alias) in enumerate(GENERICAS)]
    for c in filas:
        x = existentes.get(c["codigo"])
        if not x:
            x = CategoriaProducto(codigo=c["codigo"], nombre=c["nombre"], orden=c.get("orden", 0), activo=True)
            db.add(x)
            n += 1
        for k in ("grupo", "dominio", "alias", "familia", "nombre_corto", "nombre_aduana", "patrones", "capitulos", "plantilla_aduana"):
            if getattr(x, k) in (None, [], "", {}) and c.get(k) not in (None, [], "", {}):
                setattr(x, k, c[k])
    db.flush()
    return n


def _cat(x: CategoriaProducto) -> dict:
    return {c: getattr(x, c) for c in ("id", "codigo", "nombre", "grupo", "dominio", "alias", "orden", "activo", "familia",
                                       "nombre_corto", "nombre_aduana", "patrones", "capitulos", "plantilla_aduana")}


def categorias(db: Session, solo_activas: bool = True) -> list[dict]:
    q = select(CategoriaProducto).order_by(CategoriaProducto.orden, CategoriaProducto.nombre)
    if solo_activas:
        q = q.where(CategoriaProducto.activo.is_(True))
    return [_cat(x) for x in db.scalars(q)]


def guardar_categoria(db: Session, user: Usuario, cat_id: int | None, datos: dict) -> dict:
    exigir(user, "aranceles.editar")
    x = db.get(CategoriaProducto, cat_id) if cat_id else None
    if cat_id and not x:
        raise ErrorNegocio("The category does not exist.", 404, "no_encontrado")
    if not x:
        cod = re.sub(r"[^a-z0-9_]+", "_", (datos.get("codigo") or datos.get("nombre") or "").strip().lower()).strip("_")[:40]
        if not cod or db.scalar(select(CategoriaProducto.id).where(CategoriaProducto.codigo == cod)):
            raise ErrorNegocio("Give the category a code that is not in use.", 422, "validacion")
        x = CategoriaProducto(codigo=cod, orden=(db.scalar(select(func.max(CategoriaProducto.orden))) or 0) + 10)
        db.add(x)
    for k in ("nombre", "grupo", "dominio", "alias", "orden", "activo", "familia", "nombre_corto", "nombre_aduana", "patrones", "capitulos",
              "plantilla_aduana"):
        if k in datos and datos[k] is not None:
            setattr(x, k, datos[k])
    if x.capitulos is not None:
        x.capitulos = sorted({"".join(ch for ch in str(c) if ch.isdigit())[:2] for c in x.capitulos if str(c).strip()})
    if not (x.nombre or "").strip():
        raise ErrorNegocio("The name is required.", 422, "validacion")
    if x.dominio and not db.scalar(select(DominioClasificacion.id).where(DominioClasificacion.codigo == x.dominio)):
        raise ErrorNegocio(f"Domain {x.dominio} does not exist.", 422, "validacion")
    db.flush()
    registrar(db, user, "aranceles", x.id, "categoria", {"codigo": x.codigo, "dominio": x.dominio})
    return _cat(x)


def guardar_dominio(db: Session, user: Usuario, dom_id: int | None, datos: dict) -> dict:
    """Crea o edita un dominio. No se borra: se desactiva (archiva)."""
    exigir(user, "aranceles.editar")
    d = db.get(DominioClasificacion, dom_id) if dom_id else None
    if dom_id and not d:
        raise ErrorNegocio("The domain does not exist.", 404, "no_encontrado")
    if not d:
        cod = re.sub(r"[^A-Z0-9_]+", "_", (datos.get("codigo") or "").strip().upper()).strip("_")[:30]
        if not cod or db.scalar(select(DominioClasificacion.id).where(DominioClasificacion.codigo == cod)):
            raise ErrorNegocio("Give the domain a code that is not in use (e.g. ELECTRONICS).", 422, "validacion")
        d = DominioClasificacion(codigo=cod, orden=(db.scalar(select(func.max(DominioClasificacion.orden))) or 0) + 10)
        db.add(d)
    for k in ("nombre", "descripcion", "modo", "activo", "orden"):
        if k in datos and datos[k] is not None:
            setattr(d, k, datos[k].upper() if k == "modo" else datos[k])
    if not (d.nombre or "").strip():
        raise ErrorNegocio("The name is required.", 422, "validacion")
    if d.modo not in ("AUTO", "MANUAL"):
        raise ErrorNegocio("Mode must be AUTO or MANUAL.", 422, "validacion")
    db.flush()
    registrar(db, user, "aranceles", d.id, "dominio", {"codigo": d.codigo, "activo": d.activo})
    return {"id": d.id, "codigo": d.codigo, "nombre": d.nombre, "descripcion": d.descripcion, "modo": d.modo, "activo": d.activo}
