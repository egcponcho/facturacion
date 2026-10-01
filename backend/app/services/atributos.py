"""Atributos de la ficha técnica en base de datos (AtributoDef, AtributoOpcion,
AtributoAmbito).

Dos orígenes:
- OFICIAL: hojas Attributes, Attribute_Options y Attribute_Scope del paquete del
  motor dinámico (02); atributos genéricos y por dominio (químicos, materias
  primas, calzado, ropa, accesorios).
- MOTOR: los atributos de la ficha de ropa, calzado y accesorios, con sus
  opciones (motor_meta.json) y las categorías donde aplican (motor_ambitos.json,
  exportado del motor con scripts/motor-ambitos.mjs).

La ficha del navegador toma de aquí etiquetas, opciones activas y atributos
apagados; la lógica de cada pregunta sigue en el motor hasta migrarla a reglas.
"""
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import AtributoAmbito, AtributoDef, AtributoOpcion, DominioClasificacion, Usuario
from .common import ErrorNegocio, exigir, filtro_texto, registrar
from .meta import meta
from .oficial import _si, _txt

DATOS = Path(__file__).resolve().parent.parent / "data"
TIPOS_DATO = {"text", "select", "multi_select", "boolean", "number", "composition", "country", "measurement_set"}
TIPO_MOTOR = {"seg": "select", "select": "select", "check": "boolean", "num": "number"}
AMBITOS = ("SYSTEM", "DOMAIN", "CHAPTER", "HEADING", "SUBHEADING", "CATEGORY")
MODOS = ("SHOW", "REQUIRE", "HIDE")
# Familia de cada grupo de categorías del motor → dominio de clasificación
DOMINIO_GRUPO = {"prenda": "APPAREL", "calzado": "FOOTWEAR", "calzado_acc": "FOOTWEAR"}


# ---- Carga desde el paquete oficial ----------------------------------------------
def importar_hojas(db: Session, hojas: dict, cuenta, error) -> None:
    """Hojas Attributes, Attribute_Options y Attribute_Scope (actualiza por código)."""
    dominios = {d.codigo for d in db.scalars(select(DominioClasificacion))}
    for i, f in enumerate(hojas.get("Attributes", [])):
        cod = _txt(f.get("attribute_code"))
        tipo = (_txt(f.get("data_type")) or "text").lower()
        dom = (_txt(f.get("domain_hint")) or "CORE").upper()
        if not cod:
            error("Attributes", f["_fila"], "Attribute code is required.")
            continue
        if tipo not in TIPOS_DATO:
            error("Attributes", f["_fila"], f"Data type {tipo} is not valid.")
            continue
        if dom != "CORE" and dom not in dominios:
            error("Attributes", f["_fila"], f"Domain {dom} does not exist.")
            continue
        x = db.scalar(select(AtributoDef).where(AtributoDef.codigo == cod))
        nuevo = x is None
        x = x or AtributoDef(codigo=cod, origen="OFICIAL", orden=(i + 1) * 10)
        x.etiqueta = _txt(f.get("label")) or cod
        x.tipo_dato, x.unidad, x.dominio = tipo, _txt(f.get("default_unit")), dom
        x.multiple = _si(f.get("multi_select"))
        x.usado_clasificacion = _si(f.get("used_by_classification")) if f.get("used_by_classification") is not None else True
        x.descripcion = _txt(f.get("description"))
        db.add(x)
        cuenta("Attributes", nuevo)
    db.flush()
    attrs = {a.codigo: a for a in db.scalars(select(AtributoDef))}

    for f in hojas.get("Attribute_Options", []):
        a = attrs.get(_txt(f.get("attribute_code")) or "")
        cod = (_txt(f.get("option_code")) or "").upper()
        if not a or not cod:
            error("Attribute_Options", f["_fila"], "The attribute does not exist or the option code is empty.")
            continue
        if a.tipo_dato not in ("select", "multi_select"):
            error("Attribute_Options", f["_fila"], f"{a.codigo} is not a selection attribute.")
            continue
        x = db.scalar(select(AtributoOpcion).where(AtributoOpcion.atributo_id == a.id, AtributoOpcion.codigo == cod))
        nuevo = x is None
        x = x or AtributoOpcion(atributo=a, codigo=cod)
        x.etiqueta = _txt(f.get("label")) or cod
        x.alias = _txt(f.get("aliases_synonyms"))
        x.orden = int(f.get("sort_order") or 0)
        x.activo = _si(f.get("active")) if f.get("active") is not None else True
        db.add(x)
        cuenta("Attribute_Options", nuevo)

    for f in hojas.get("Attribute_Scope", []):
        a = attrs.get(_txt(f.get("attribute_code")) or "")
        tipo = (_txt(f.get("scope_type")) or "").upper()
        cod = (_txt(f.get("scope_code")) or "").upper()
        modo = (_txt(f.get("mode")) or "SHOW").upper()
        if not a or tipo not in AMBITOS or not cod or modo not in MODOS:
            error("Attribute_Scope", f["_fila"], "Attribute, scope type (SYSTEM, DOMAIN, CHAPTER, HEADING, SUBHEADING, CATEGORY), "
                                                 "scope code and mode (SHOW, REQUIRE, HIDE) are required.")
            continue
        if tipo == "DOMAIN" and cod not in dominios:
            error("Attribute_Scope", f["_fila"], f"Domain {cod} does not exist.")
            continue
        x = db.scalar(select(AtributoAmbito).where(AtributoAmbito.atributo_id == a.id, AtributoAmbito.tipo_ambito == tipo,
                                                   AtributoAmbito.codigo_ambito == cod))
        nuevo = x is None
        x = x or AtributoAmbito(atributo=a, tipo_ambito=tipo, codigo_ambito=cod)
        x.modo, x.prioridad = modo, int(f.get("priority") or 500)
        x.nota = _txt(f.get("condition_dependency"))
        x.activo = _si(f.get("active")) if f.get("active") is not None else True
        db.add(x)
        cuenta("Attribute_Scope", nuevo)
    db.flush()


# ---- Carga desde el motor de la ficha -----------------------------------------------
def cargar_motor(db: Session) -> int:
    """Siembra los atributos de la ficha actual (ropa, calzado, accesorios) con
    sus opciones y categorías. No pisa lo editado: solo agrega lo que falta."""
    ambitos = json.loads((DATOS / "motor_ambitos.json").read_text(encoding="utf-8"))
    grupo = {t["k"]: t["grupoTipo"] for g in meta()["tipos"] for t in g["tipos"]}
    existentes = {a.codigo: a for a in db.scalars(select(AtributoDef).options(selectinload(AtributoDef.opciones)))}
    base = (db.scalar(select(func.max(AtributoDef.orden))) or 0) + 10
    nuevos = 0
    for i, m in enumerate(meta()["attrs"]):
        cats = ambitos.get(m["id"], {})
        doms = [DOMINIO_GRUPO.get(grupo.get(c, ""), "ACCESSORIES_MERCH") for c in cats]
        a = existentes.get(m["id"])
        if not a:
            a = AtributoDef(codigo=m["id"], etiqueta=m["label"], tipo_dato=TIPO_MOTOR.get(m["tipo"], "text"), origen="MOTOR",
                            dominio=max(set(doms), key=doms.count) if doms else None, de_composicion=bool(m.get("deComp")),
                            informativo=bool(m.get("info")), orden=base + i * 10, usado_clasificacion=not m.get("info"))
            db.add(a)
            nuevos += 1
        tiene = {o.codigo for o in a.opciones}
        for j, o in enumerate(m.get("ops") or []):
            if o["v"] not in tiene:
                a.opciones.append(AtributoOpcion(codigo=o["v"], etiqueta=o["l"], orden=(j + 1) * 10))
        tiene = {(x.tipo_ambito, x.codigo_ambito) for x in a.ambitos}
        for cat, conds in cats.items():
            if ("CATEGORY", cat) in tiene:
                continue
            cond = None if conds == [None] else [c for c in conds if c]
            a.ambitos.append(AtributoAmbito(tipo_ambito="CATEGORY", codigo_ambito=cat, modo="SHOW", prioridad=500,
                                            condicion=cond, nota="Asked when another answer activates it." if cond else None))
    db.flush()
    return nuevos


# ---- Consulta ---------------------------------------------------------------------
def _ambito_dict(x: AtributoAmbito) -> dict:
    return {"id": x.id, "tipo_ambito": x.tipo_ambito, "codigo_ambito": x.codigo_ambito, "modo": x.modo,
            "prioridad": x.prioridad, "condicion": x.condicion, "nota": x.nota, "activo": x.activo}


def _opcion_dict(x: AtributoOpcion) -> dict:
    return {"id": x.id, "codigo": x.codigo, "etiqueta": x.etiqueta, "alias": x.alias, "orden": x.orden, "activo": x.activo}


def _dict(a: AtributoDef, detalle: bool = False) -> dict:
    d = {c: getattr(a, c) for c in ("id", "codigo", "etiqueta", "tipo_dato", "unidad", "multiple", "usado_clasificacion",
                                     "dominio", "descripcion", "origen", "de_composicion", "informativo", "orden", "activo")}
    d["n_opciones"] = sum(1 for o in a.opciones if o.activo)
    d["n_ambitos"] = len(a.ambitos)
    if detalle:
        d["opciones"] = [_opcion_dict(o) for o in a.opciones]
        d["ambitos"] = [_ambito_dict(x) for x in sorted(a.ambitos, key=lambda x: (AMBITOS.index(x.tipo_ambito), -x.prioridad, x.codigo_ambito))]
    else:
        d["ambitos_resumen"] = sorted({f"{x.tipo_ambito}:{x.codigo_ambito}" for x in a.ambitos})[:12]
    return d


def listar(db: Session, user: Usuario, q: str | None = None, dominio: str | None = None, origen: str | None = None) -> dict:
    exigir(user, "aranceles.ver")
    consulta = select(AtributoDef).options(selectinload(AtributoDef.opciones), selectinload(AtributoDef.ambitos))
    if q:
        consulta = consulta.where(filtro_texto(q, lambda p: [AtributoDef.codigo.ilike(p), AtributoDef.etiqueta.ilike(p),
                                                             AtributoDef.descripcion.ilike(p), AtributoDef.dominio.ilike(p)]))
    if dominio:
        consulta = consulta.where(AtributoDef.dominio == dominio)
    if origen:
        consulta = consulta.where(AtributoDef.origen == origen)
    items = [_dict(a) for a in db.scalars(consulta.order_by(AtributoDef.orden, AtributoDef.codigo))]
    por = dict(db.execute(select(AtributoDef.origen, func.count()).group_by(AtributoDef.origen)).all())
    return {"items": items, "por_origen": por, "total": sum(por.values())}


def detalle(db: Session, user: Usuario, atributo_id: int) -> dict:
    exigir(user, "aranceles.ver")
    a = db.get(AtributoDef, atributo_id)
    if not a:
        raise ErrorNegocio("The attribute does not exist.", 404, "no_encontrado")
    return _dict(a, True)


def config_motor(db: Session) -> dict:
    """Lo que la ficha del navegador toma de la base: etiqueta, opciones activas
    y atributos apagados de los atributos del motor; y los atributos oficiales
    con sus ámbitos (para las fichas genéricas por dominio)."""
    attrs = list(db.scalars(select(AtributoDef).options(selectinload(AtributoDef.opciones), selectinload(AtributoDef.ambitos))
                            .order_by(AtributoDef.orden)))
    return {
        "motor": {a.codigo: {"etiqueta": a.etiqueta, "activo": a.activo,
                             "opciones": {o.codigo: {"etiqueta": o.etiqueta, "activo": o.activo, "orden": o.orden} for o in a.opciones}}
                  for a in attrs if a.origen == "MOTOR"},
        "genericos": [{**_dict(a, True)} for a in attrs if a.origen != "MOTOR" and a.activo],
    }


# ---- Edición ----------------------------------------------------------------------
CAMPOS = ("etiqueta", "descripcion", "unidad", "dominio", "activo", "usado_clasificacion", "orden")


def guardar(db: Session, user: Usuario, atributo_id: int | None, datos: dict) -> dict:
    exigir(user, "aranceles.editar")
    if atributo_id:
        a = db.get(AtributoDef, atributo_id)
        if not a:
            raise ErrorNegocio("The attribute does not exist.", 404, "no_encontrado")
    else:
        cod = (datos.get("codigo") or "").strip()
        if not cod or db.scalar(select(AtributoDef.id).where(AtributoDef.codigo == cod)):
            raise ErrorNegocio("Give the attribute a code that is not in use.", 422, "validacion")
        tipo = datos.get("tipo_dato") or "text"
        if tipo not in TIPOS_DATO:
            raise ErrorNegocio(f"Data type {tipo} is not valid.", 422, "validacion")
        a = AtributoDef(codigo=cod, tipo_dato=tipo, origen="USUARIO", multiple=tipo == "multi_select",
                        orden=(db.scalar(select(func.max(AtributoDef.orden))) or 0) + 10)
    for k in CAMPOS:
        if k in datos and datos[k] is not None:
            setattr(a, k, datos[k])
    if not (a.etiqueta or "").strip():
        raise ErrorNegocio("The label is required.", 422, "validacion")
    db.add(a)
    db.flush()
    registrar(db, user, "aranceles", a.id, "atributo", {"codigo": a.codigo, "cambios": {k: datos[k] for k in CAMPOS if k in datos}})
    return _dict(a, True)


def guardar_opcion(db: Session, user: Usuario, atributo_id: int, opcion_id: int | None, datos: dict) -> dict:
    exigir(user, "aranceles.editar")
    a = db.get(AtributoDef, atributo_id)
    if not a or a.tipo_dato not in ("select", "multi_select"):
        raise ErrorNegocio("The attribute does not exist or does not have options.", 404, "no_encontrado")
    if opcion_id:
        o = db.get(AtributoOpcion, opcion_id)
        if not o or o.atributo_id != a.id:
            raise ErrorNegocio("The option does not exist.", 404, "no_encontrado")
    else:
        cod = (datos.get("codigo") or "").strip()
        if not cod or any(x.codigo == cod for x in a.opciones):
            raise ErrorNegocio("Give the option a code that is not in use.", 422, "validacion")
        o = AtributoOpcion(atributo=a, codigo=cod, orden=max([x.orden for x in a.opciones] or [0]) + 10)
    for k in ("etiqueta", "alias", "orden", "activo"):
        if k in datos and datos[k] is not None:
            setattr(o, k, datos[k])
    if not (o.etiqueta or "").strip():
        raise ErrorNegocio("The label is required.", 422, "validacion")
    db.add(o)
    db.flush()
    return _dict(a, True)


def guardar_ambito(db: Session, user: Usuario, atributo_id: int, ambito_id: int | None, datos: dict) -> dict:
    exigir(user, "aranceles.editar")
    a = db.get(AtributoDef, atributo_id)
    if not a:
        raise ErrorNegocio("The attribute does not exist.", 404, "no_encontrado")
    if ambito_id:
        x = db.get(AtributoAmbito, ambito_id)
        if not x or x.atributo_id != a.id:
            raise ErrorNegocio("The scope does not exist.", 404, "no_encontrado")
        if datos.get("quitar"):
            db.delete(x)
            db.flush()
            db.refresh(a)
            return _dict(a, True)
    else:
        tipo = (datos.get("tipo_ambito") or "").upper()
        cod = (datos.get("codigo_ambito") or "").strip()
        if tipo not in AMBITOS or not cod:
            raise ErrorNegocio("Choose the scope type and its code.", 422, "validacion")
        if tipo != "CATEGORY":
            cod = cod.upper()
        if any(y.tipo_ambito == tipo and y.codigo_ambito == cod for y in a.ambitos):
            raise ErrorNegocio("The attribute already has that scope.", 422, "validacion")
        x = AtributoAmbito(atributo=a, tipo_ambito=tipo, codigo_ambito=cod)
    modo = (datos.get("modo") or x.modo or "SHOW").upper()
    if modo not in MODOS:
        raise ErrorNegocio("Mode must be SHOW, REQUIRE or HIDE.", 422, "validacion")
    x.modo = modo
    for k in ("prioridad", "nota", "activo"):
        if k in datos and datos[k] is not None:
            setattr(x, k, datos[k])
    db.add(x)
    db.flush()
    return _dict(a, True)
