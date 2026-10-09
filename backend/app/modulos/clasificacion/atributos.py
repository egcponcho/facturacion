"""Atributos de la ficha técnica en base de datos (AtributoDef, AtributoOpcion,
AtributoAmbito).

Dos orígenes:
- PAQUETE: hojas Attributes, Attribute_Options, Attribute_Scope y
  Attribute_Scope_Conditions de un paquete del motor (el 02 incluido u otro que
  se cargue); un atributo que ya existe con otro código se declara «Same as» y
  queda como alias, nunca duplicado.
- MOTOR: las preguntas de cada familia (calzado, ropa, accesorios, químicos y
  materias primas, data/motor/familias), con su comportamiento como datos: cuándo aplican
  (ámbitos con condiciones), lo que fija la composición, opciones imposibles,
  implicaciones y patrones de detección. Los ejecuta app/modulos/productos/ficha.py.
- USUARIO: los creados a mano, con las mismas capacidades.
"""
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import AtributoAmbito, AtributoDef, AtributoOpcion, DominioClasificacion, Usuario
from app.modulos.acceso.permisos import exigir
from app.modulos.clasificacion.oficial import _si, _txt
from app.modulos.comun.historial import registrar
from app.modulos.comun.texto import filtro_texto

TIPOS_DATO = {"text", "select", "multi_select", "boolean", "number", "composition", "country", "measurement_set"}
TIPO_MOTOR = {"seg": "select", "select": "select", "check": "boolean", "num": "number"}
AMBITOS = ("SYSTEM", "DOMAIN", "CHAPTER", "HEADING", "SUBHEADING", "CATEGORY")
MODOS = ("SHOW", "REQUIRE", "HIDE")


# ---- Carga desde el paquete oficial ----------------------------------------------
def json_celda(v, columna: str):
    """Una celda con JSON (patrones, derivación, textos…): vacía → None."""
    t = _txt(v)
    if t is None:
        return None
    try:
        return json.loads(t)
    except ValueError as e:
        raise ErrorNegocio(f"{columna} is not valid JSON ({e}).", 422, "configuracion_invalida") from None


def _comportamiento_hojas(db: Session, hojas: dict, error) -> None:
    """Columnas de comportamiento de Attributes (Section, Informative, Default
    value, Aliases, Derivation/Blocks/Patterns/False patterns/Customs text JSON) y
    de Attribute_Options (Blocks/Implies/Patterns/Customs text JSON), validadas
    con lo ya cargado: un paquete trae una familia completa, no solo sus nombres."""
    from app.modulos.clasificacion import validacion_config as v

    ctx = v.Contexto(db)
    for f in hojas.get("Attributes", []):
        if _txt(f.get("same_as")):
            continue
        a = ctx.attrs.get(_txt(f.get("attribute_code")) or "")
        if not a:
            continue
        try:
            with db.begin_nested():
                if _txt(f.get("section")):
                    if f["section"] not in v.SECCIONES:
                        v.error(f"Section must be one of {', '.join(v.SECCIONES)}.")
                    a.seccion = f["section"]
                if f.get("informative") is not None:
                    a.informativo = _si(f.get("informative"))
                if _txt(f.get("default_value")) is not None:
                    a.valor_defecto = _txt(f.get("default_value"))
                if _txt(f.get("aliases")):
                    a.alias = v.alias(ctx, a, [x.strip() for x in str(f["aliases"]).replace(";", ",").split(",") if x.strip()], a.codigo)
                for col, campo, fn in (("derivation_json", "derivacion", lambda x: v.derivacion(ctx, a, x, f"{a.codigo} (derivation)")),
                                       ("blocks_json", "bloqueo", lambda x: v.bloqueos(ctx, x, f"{a.codigo} (blocks)")),
                                       ("patterns_json", "patrones", lambda x: v.patrones(ctx, x, f"{a.codigo} (patterns)")),
                                       ("false_patterns_json", "patrones_falso", lambda x: v.patrones(ctx, x, f"{a.codigo} (false patterns)")),
                                       ("customs_text_json", "texto_aduana", lambda x: v.textos_aduana(ctx, x, f"{a.codigo} (customs text)"))):
                    x = json_celda(f.get(col), col)
                    if x is not None:
                        setattr(a, campo, fn(x))
                db.flush()
        except ErrorNegocio as e:
            error("Attributes", f["_fila"], str(e))
    for f in hojas.get("Attribute_Options", []):
        a = ctx.attrs.get(ctx.canon.get(_txt(f.get("attribute_code")) or "", ""))
        cod = (_txt(f.get("option_code")) or "").lower()
        o = next((o for o in (a.opciones if a else []) if o.codigo.lower() == cod), None)
        if not o:
            continue
        try:
            with db.begin_nested():
                for col, campo, fn in (("blocks_json", "bloqueo", lambda x: v.bloqueos(ctx, x, f"{a.codigo} = {o.codigo} (blocks)")),
                                       ("implies_json", "implica", lambda x: v.implica(ctx, a, x, f"{a.codigo} = {o.codigo} (implies)")),
                                       ("patterns_json", "patrones", lambda x: v.patrones(ctx, x, f"{a.codigo} = {o.codigo} (patterns)")),
                                       ("customs_text_json", "texto_aduana",
                                        lambda x: v.textos_aduana(ctx, x, f"{a.codigo} = {o.codigo} (customs text)"))):
                    x = json_celda(f.get(col), col)
                    if x is not None:
                        setattr(o, campo, fn(x))
                db.flush()
        except ErrorNegocio as e:
            error("Attribute_Options", f["_fila"], str(e))


def canonicos(db: Session) -> dict[str, str]:
    """Cada código con el que puede llegar un atributo → su código en la ficha
    (el propio y sus alias)."""
    out: dict[str, str] = {}
    for a in db.scalars(select(AtributoDef)):
        out[a.codigo] = a.codigo
        for x in a.alias or []:
            out.setdefault(str(x), a.codigo)
    return out


def _condiciones_hoja(filas: list[dict], hoja: str, error, ctx) -> list[dict] | None:
    """Filas con Group, Field (o Attribute/system field), Operator, Value, Value to y
    Negated → condiciones del motor, validadas con las mismas reglas que en la
    pantalla (validacion_config). Sin contexto no se validan los campos (reglas
    internas del motor, que leen campos del sistema). None si alguna fila falla."""
    from app.modulos.clasificacion import validacion_config as v
    from app.modulos.clasificacion.reglas import _valor

    out, ok = [], True
    for f in filas:
        c = {"grupo": int(f.get("group") or 1), "campo": _txt(f.get("field")) or _txt(f.get("attribute_system_field")),
             "operador": (_txt(f.get("operator")) or "EQUAL").upper(), "valor": _valor(f.get("value")),
             "valor_hasta": _valor(f.get("value_to")), "negado": _si(f.get("negated"))}
        if not c["campo"] or c["operador"] not in v.OPERADORES:
            error(hoja, f["_fila"], f"Field and operator ({', '.join(v.OPERADORES)}) are required.")
            ok = False
            continue
        if ctx is not None:
            try:
                c = v.condiciones(ctx, [c], "Condition")[0]
            except ErrorNegocio as e:
                error(hoja, f["_fila"], e.mensaje)
                ok = False
                continue
        out.append(c)
    return out if ok else None


def _codigo_ambito(db: Session, tipo: str, cod: str, dominios: set) -> tuple[str | None, str | None]:
    """El código del ámbito tal como se guarda y, si no es válido, por qué."""
    from app.modelos import CategoriaProducto

    if tipo == "CATEGORY":  # los códigos de categoría van en minúsculas: se respetan tal cual
        cat = db.scalar(select(CategoriaProducto.codigo).where(func.lower(CategoriaProducto.codigo) == cod.lower()))
        return (cat, None) if cat else (None, f"Category {cod} does not exist.")
    cod = cod.upper()
    if tipo == "DOMAIN" and cod not in dominios:
        return None, f"Domain {cod} does not exist."
    if tipo in ("CHAPTER", "HEADING", "SUBHEADING"):
        dig = "".join(ch for ch in cod if ch.isdigit())
        if len(dig) != {"CHAPTER": 2, "HEADING": 4, "SUBHEADING": 6}[tipo]:
            return None, f"{tipo.capitalize()} {cod} must have {({'CHAPTER': 2, 'HEADING': 4, 'SUBHEADING': 6})[tipo]} digits."
        cod = dig
    if tipo == "SYSTEM":
        cod = "ALL"
    return cod, None


def importar_hojas(db: Session, hojas: dict, cuenta, error) -> None:
    """Hojas Attributes, Attribute_Options, Attribute_Scope y
    Attribute_Scope_Conditions (actualiza por código). Un atributo que ya existe
    con otro código se declara con «Same as»: se reutiliza (sus opciones, ámbitos
    y las condiciones que lo nombran se resuelven a él) en vez de duplicarlo."""
    dominios = {d.codigo for d in db.scalars(select(DominioClasificacion))}
    canon = canonicos(db)
    for i, f in enumerate(hojas.get("Attributes", [])):
        cod = _txt(f.get("attribute_code"))
        tipo = (_txt(f.get("data_type")) or "text").lower()
        dom = (_txt(f.get("domain_hint")) or "CORE").upper()
        igual = _txt(f.get("same_as"))
        if not cod:
            error("Attributes", f["_fila"], "Attribute code is required.")
            continue
        if tipo not in TIPOS_DATO:
            error("Attributes", f["_fila"], f"Data type {tipo} is not valid.")
            continue
        if dom != "CORE" and dom not in dominios:
            error("Attributes", f["_fila"], f"Domain {dom} does not exist.")
            continue
        if igual:
            base = db.scalar(select(AtributoDef).where(AtributoDef.codigo == canon.get(igual, igual)))
            if not base:
                error("Attributes", f["_fila"], f"{cod}: «Same as» {igual} is not an attribute.")
                continue
            if base.tipo_dato != tipo:
                error("Attributes", f["_fila"], f"{cod} is {tipo} but {base.codigo} is {base.tipo_dato}: they cannot be the same attribute.")
                continue
            propio = db.scalar(select(AtributoDef).where(AtributoDef.codigo == cod))
            if propio and propio.id != base.id:
                error("Attributes", f["_fila"], f"{cod} already exists as its own attribute: it cannot also be {base.codigo}.")
                continue
            if cod != base.codigo and cod not in (base.alias or []):
                base.alias = [*(base.alias or []), cod]
            canon[cod] = base.codigo
            cuenta("Attributes", False)
            continue
        if canon.get(cod, cod) != cod:
            error("Attributes", f["_fila"], f"{cod} is already an alias of {canon[cod]}: use «Same as» or another code.")
            continue
        x = db.scalar(select(AtributoDef).where(AtributoDef.codigo == cod))
        nuevo = x is None
        x = x or AtributoDef(codigo=cod, origen="PAQUETE", orden=(i + 1) * 10)
        x.etiqueta = _txt(f.get("label")) or cod
        x.tipo_dato, x.unidad, x.dominio = tipo, _txt(f.get("default_unit")), dom
        x.multiple = _si(f.get("multi_select"))
        x.usado_clasificacion = _si(f.get("used_by_classification")) if f.get("used_by_classification") is not None else True
        x.descripcion = _txt(f.get("description"))
        db.add(x)
        canon[cod] = cod
        cuenta("Attributes", nuevo)
    db.flush()
    attrs = {a.codigo: a for a in db.scalars(select(AtributoDef))}

    def atributo(f):
        return attrs.get(canon.get(_txt(f.get("attribute_code")) or "", ""))

    for f in hojas.get("Attribute_Options", []):
        a = atributo(f)
        cod = _txt(f.get("option_code")) or ""
        if not a or not cod:
            error("Attribute_Options", f["_fila"], "The attribute does not exist or the option code is empty.")
            continue
        if a.tipo_dato not in ("select", "multi_select"):
            error("Attribute_Options", f["_fila"], f"{a.codigo} is not a selection attribute.")
            continue
        x = next((o for o in a.opciones if o.codigo.lower() == cod.lower()), None)
        nuevo = x is None
        x = x or AtributoOpcion(atributo=a, codigo=cod)
        x.etiqueta = _txt(f.get("label")) or x.etiqueta or cod
        x.alias = _txt(f.get("aliases_synonyms"))
        x.orden = int(f.get("sort_order") or 0)
        x.activo = _si(f.get("active")) if f.get("active") is not None else True
        db.add(x)
        cuenta("Attribute_Options", nuevo)

    ambitos: dict[tuple, AtributoAmbito] = {}
    for f in hojas.get("Attribute_Scope", []):
        a = atributo(f)
        tipo = (_txt(f.get("scope_type")) or "").upper()
        modo = (_txt(f.get("mode")) or "SHOW").upper()
        if not a or tipo not in AMBITOS or not _txt(f.get("scope_code")) or modo not in MODOS:
            error("Attribute_Scope", f["_fila"], "Attribute, scope type (SYSTEM, DOMAIN, CHAPTER, HEADING, SUBHEADING, CATEGORY), "
                                                 "scope code and mode (SHOW, REQUIRE, HIDE) are required.")
            continue
        cod, problema = _codigo_ambito(db, tipo, _txt(f.get("scope_code")), dominios)
        if problema:
            error("Attribute_Scope", f["_fila"], problema)
            continue
        x = next((y for y in a.ambitos if y.tipo_ambito == tipo and y.codigo_ambito == cod), None)
        nuevo = x is None
        x = x or AtributoAmbito(atributo=a, tipo_ambito=tipo, codigo_ambito=cod)
        x.modo, x.prioridad = modo, int(f.get("priority") or 500)
        x.nota = _txt(f.get("condition_dependency"))
        x.activo = _si(f.get("active")) if f.get("active") is not None else True
        db.add(x)
        ambitos[(a.codigo, tipo, cod)] = x
        cuenta("Attribute_Scope", nuevo)

    # Condiciones de cada ámbito: se reemplazan completas (la hoja es la verdad)
    por_ambito: dict[tuple, list] = {}
    for f in hojas.get("Attribute_Scope_Conditions", []):
        a = atributo(f)
        tipo = (_txt(f.get("scope_type")) or "").upper()
        cod, problema = _codigo_ambito(db, tipo, _txt(f.get("scope_code")) or "", dominios) if a and tipo in AMBITOS else (None, None)
        x = ambitos.get((a.codigo, tipo, cod)) if a and cod else None
        if x is None and a and cod:
            x = next((y for y in a.ambitos if y.tipo_ambito == tipo and y.codigo_ambito == cod), None)
        if not x:
            error("Attribute_Scope_Conditions", f["_fila"], problema or "The attribute has no such scope (add it in Attribute_Scope).")
            continue
        por_ambito.setdefault(id(x), [x, []])[1].append(f)
    db.flush()
    _comportamiento_hojas(db, hojas, error)
    from app.modulos.clasificacion.validacion_config import Contexto

    ctx = Contexto(db)
    for x, filas in por_ambito.values():
        conds = _condiciones_hoja(filas, "Attribute_Scope_Conditions", error, ctx)
        if conds is not None and conds != (x.condicion or []):
            x.condicion = conds
            cuenta("Attribute_Scope_Conditions", False)
    db.flush()


# ---- Carga de los atributos de la semilla por familia ------------------------------
def cargar_motor(db: Session) -> int:
    """Siembra o completa las preguntas de cada familia (data/motor/familias)
    con su comportamiento como datos (derivación, bloqueos, implicaciones,
    patrones de detección, ámbitos con condiciones, términos de búsqueda).
    Crea lo que falta y completa lo que está vacío; nunca pisa lo que alguien editó."""
    from app.modulos.clasificacion.semilla_familias import semilla

    datos = semilla()
    existentes = {a.codigo: a for a in db.scalars(select(AtributoDef).options(selectinload(AtributoDef.opciones), selectinload(AtributoDef.ambitos)))}
    dominio_cat = {c["codigo"]: c.get("dominio") for c in datos["categorias"]}
    nuevos = 0
    for m in datos["atributos"]:
        doms = [dominio_cat[x["codigo_ambito"]] for x in m.get("ambitos") or []
                if x["tipo_ambito"] == "CATEGORY" and dominio_cat.get(x["codigo_ambito"])]
        dominio = max(set(doms), key=doms.count) if len(set(doms)) == 1 else None
        a = existentes.get(m["codigo"])
        if not a:
            a = AtributoDef(codigo=m["codigo"], etiqueta=m["etiqueta"], tipo_dato=m["tipo_dato"], origen="MOTOR", orden=m.get("orden", 0),
                            informativo=bool(m.get("informativo")), usado_clasificacion=not m.get("informativo"), unidad=m.get("unidad"),
                            de_composicion=m.get("seccion") == "composicion" or m["tipo_dato"] == "composition", descripcion=m.get("ayuda"),
                            dominio=dominio)
            db.add(a)
            existentes[a.codigo] = a
            nuevos += 1
        for k in ("seccion", "valor_defecto", "derivacion", "bloqueo", "patrones", "patrones_falso", "control", "texto_aduana"):
            if getattr(a, k) in (None, [], {}) and m.get(k) not in (None, [], {}):
                setattr(a, k, m[k])
        if a.seccion is None:
            a.seccion = "caracteristicas"
        ops = {o.codigo: o for o in a.opciones}
        for o in m.get("opciones") or []:
            x = ops.get(o["codigo"])
            if not x:
                x = AtributoOpcion(codigo=o["codigo"], etiqueta=o["etiqueta"], orden=o.get("orden", 0))
                a.opciones.append(x)
            for k in ("bloqueo", "implica", "patrones", "texto_aduana", "terminos"):
                if getattr(x, k) in (None, [], {}, "") and o.get(k) not in (None, [], {}, ""):
                    setattr(x, k, o[k])
        amb = {(x.tipo_ambito, x.codigo_ambito) for x in a.ambitos}
        for x in m.get("ambitos") or []:
            if (x["tipo_ambito"], x["codigo_ambito"]) not in amb:
                amb.add((x["tipo_ambito"], x["codigo_ambito"]))
                a.ambitos.append(AtributoAmbito(tipo_ambito=x["tipo_ambito"], codigo_ambito=x["codigo_ambito"], modo=x.get("modo") or "SHOW",
                                                prioridad=x.get("prioridad", 500), condicion=x.get("condicion")))
    db.flush()
    return nuevos


# ---- Consulta ---------------------------------------------------------------------
def _ambito_dict(x: AtributoAmbito) -> dict:
    return {"id": x.id, "tipo_ambito": x.tipo_ambito, "codigo_ambito": x.codigo_ambito, "modo": x.modo,
            "prioridad": x.prioridad, "condicion": x.condicion, "nota": x.nota, "activo": x.activo}


def _opcion_dict(x: AtributoOpcion) -> dict:
    return {"id": x.id, "codigo": x.codigo, "etiqueta": x.etiqueta, "alias": x.alias, "terminos": x.terminos, "orden": x.orden, "activo": x.activo,
            "bloqueo": x.bloqueo or [], "implica": x.implica or {}, "patrones": x.patrones or [], "texto_aduana": x.texto_aduana}


def _dict(a: AtributoDef, detalle: bool = False) -> dict:
    d = {c: getattr(a, c) for c in ("id", "codigo", "etiqueta", "tipo_dato", "unidad", "multiple", "usado_clasificacion",
                                     "dominio", "descripcion", "origen", "de_composicion", "informativo", "orden", "activo", "alias")}
    d["n_opciones"] = sum(1 for o in a.opciones if o.activo)
    d["n_ambitos"] = len(a.ambitos)
    if detalle:
        for k in ("seccion", "valor_defecto", "control", "derivacion", "texto_aduana"):
            d[k] = getattr(a, k)
        for k in ("bloqueo", "patrones", "patrones_falso"):
            d[k] = getattr(a, k) or []
        d["opciones"] = [_opcion_dict(o) for o in a.opciones]
        d["ambitos"] = [_ambito_dict(x) for x in sorted(a.ambitos, key=lambda x: (AMBITOS.index(x.tipo_ambito), -x.prioridad, x.codigo_ambito))]
    else:
        d["opciones_min"] = [{"codigo": o.codigo, "etiqueta": o.etiqueta} for o in a.opciones if o.activo]
        d["ambitos_resumen"] = sorted({f"{x.tipo_ambito}:{x.codigo_ambito}" for x in a.ambitos})[:12]
    return d


def listar(db: Session, user: Usuario, q: str | None = None, dominio: str | None = None, origen: str | None = None) -> dict:
    exigir(user, "clasificacion.ver")
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
    exigir(user, "clasificacion.ver")
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
CAMPOS = ("etiqueta", "descripcion", "unidad", "dominio", "activo", "usado_clasificacion", "orden", "informativo", "valor_defecto", "control")
COMPORTAMIENTO = ("seccion", "alias", "derivacion", "bloqueo", "patrones", "patrones_falso", "texto_aduana")


def guardar(db: Session, user: Usuario, atributo_id: int | None, datos: dict) -> dict:
    """Crea o edita un atributo con todo su comportamiento (sección, alias,
    derivación, bloqueos, patrones de detección y texto aduanero), validado: lo
    que no es válido no se guarda y el mensaje dice qué y dónde."""
    from app.modulos.clasificacion import validacion_config as v

    exigir(user, "clasificacion.configurar")
    if atributo_id:
        a = db.get(AtributoDef, atributo_id)
        if not a:
            raise ErrorNegocio("The attribute does not exist.", 404, "no_encontrado")
    else:
        cod = (datos.get("codigo") or "").strip()
        tipo = datos.get("tipo_dato") or "text"
        if tipo not in TIPOS_DATO:
            raise ErrorNegocio(f"Data type {tipo} is not valid.", 422, "validacion")
        if tipo == "composition" and cod and not cod.startswith("comp."):
            cod = f"comp.{cod}"  # una parte de la composición vive en comp.<parte>
        if tipo != "composition" and cod.startswith("comp."):
            raise ErrorNegocio("Only a composition part has a code that starts with comp.", 422, "validacion")
        if not cod or cod in canonicos(db):
            raise ErrorNegocio("Give the attribute a code that is not in use (nor an alias of another one).", 422, "validacion")
        a = AtributoDef(codigo=cod, tipo_dato=tipo, origen="USUARIO", multiple=tipo == "multi_select", de_composicion=tipo == "composition",
                        seccion="composicion" if tipo == "composition" else "caracteristicas",
                        orden=(db.scalar(select(func.max(AtributoDef.orden))) or 0) + 10)
    if datos.get("dominio") and datos["dominio"] != "CORE" and not db.scalar(
            select(DominioClasificacion.id).where(DominioClasificacion.codigo == datos["dominio"])):
        raise ErrorNegocio(f"Domain {datos['dominio']} does not exist.", 422, "validacion")
    for k in CAMPOS:
        if k in datos and datos[k] is not None:
            setattr(a, k, datos[k])
    if not (a.etiqueta or "").strip():
        raise ErrorNegocio("The label is required.", 422, "validacion")
    if datos.get("seccion") is not None:
        if datos["seccion"] not in v.SECCIONES:
            raise ErrorNegocio(f"The section must be one of {', '.join(v.SECCIONES)}.", 422, "validacion")
        a.seccion = datos["seccion"]
    if a.tipo_dato == "boolean" and a.valor_defecto not in (None, "", "true", "false"):
        raise ErrorNegocio("The default of a yes/no box is true or false.", 422, "validacion")
    db.add(a)
    db.flush()
    ctx = v.Contexto(db)
    donde = a.codigo
    if "alias" in datos:
        a.alias = v.alias(ctx, a, datos["alias"], donde)
    if "derivacion" in datos:
        a.derivacion = v.derivacion(ctx, a, datos["derivacion"], f"{donde} (derivation)")
    if "bloqueo" in datos:
        if datos["bloqueo"] and a.tipo_dato != "boolean":
            raise ErrorNegocio("Blocks on the attribute are for yes/no boxes; for a list, block each option.", 422, "validacion")
        a.bloqueo = v.bloqueos(ctx, datos["bloqueo"], f"{donde} (blocks)")
    for k in ("patrones", "patrones_falso"):
        if k in datos:
            if datos[k] and a.tipo_dato != "boolean":
                raise ErrorNegocio("Patterns on the attribute are for yes/no boxes; for a list, give each option its patterns.",
                                   422, "validacion")
            setattr(a, k, v.patrones(ctx, datos[k], f"{donde} ({k})"))
    if "texto_aduana" in datos:
        if datos["texto_aduana"] and a.tipo_dato != "boolean":
            raise ErrorNegocio("The customs text of a list goes on each option.", 422, "validacion")
        a.texto_aduana = v.textos_aduana(ctx, datos["texto_aduana"], f"{donde} (customs text)")
    db.flush()
    cambios = {k: datos[k] for k in (*CAMPOS, *COMPORTAMIENTO) if k in datos}
    registrar(db, user, "aranceles", a.id, "atributo", {"codigo": a.codigo, "cambios": cambios})
    return _dict(a, True)


def guardar_opcion(db: Session, user: Usuario, atributo_id: int, opcion_id: int | None, datos: dict) -> dict:
    """Crea o edita una opción con su comportamiento (bloqueos, implicaciones,
    patrones de detección y texto aduanero), validado."""
    from app.modulos.clasificacion import validacion_config as v

    exigir(user, "clasificacion.configurar")
    a = db.get(AtributoDef, atributo_id)
    if not a or a.tipo_dato not in ("select", "multi_select"):
        raise ErrorNegocio("The attribute does not exist or does not have options.", 404, "no_encontrado")
    if opcion_id:
        o = db.get(AtributoOpcion, opcion_id)
        if not o or o.atributo_id != a.id:
            raise ErrorNegocio("The option does not exist.", 404, "no_encontrado")
    else:
        cod = (datos.get("codigo") or "").strip()
        if not cod or any(x.codigo.lower() == cod.lower() for x in a.opciones):
            raise ErrorNegocio("Give the option a code that is not in use.", 422, "validacion")
        o = AtributoOpcion(atributo=a, codigo=cod, orden=max([x.orden for x in a.opciones] or [0]) + 10)
    for k in ("etiqueta", "alias", "terminos", "orden", "activo"):
        if k in datos and datos[k] is not None:
            setattr(o, k, datos[k])
    if not (o.etiqueta or "").strip():
        raise ErrorNegocio("The label is required.", 422, "validacion")
    db.add(o)
    db.flush()
    ctx = v.Contexto(db)
    donde = f"{a.codigo} = {o.codigo}"
    if "bloqueo" in datos:
        o.bloqueo = v.bloqueos(ctx, datos["bloqueo"], f"{donde} (blocks)")
    if "implica" in datos:
        o.implica = v.implica(ctx, a, datos["implica"], f"{donde} (implies)")
    if "patrones" in datos:
        o.patrones = v.patrones(ctx, datos["patrones"], f"{donde} (patterns)")
    if "texto_aduana" in datos:
        o.texto_aduana = v.textos_aduana(ctx, datos["texto_aduana"], f"{donde} (customs text)")
    db.flush()
    registrar(db, user, "aranceles", a.id, "opcion", {"codigo": a.codigo, "opcion": o.codigo,
                                                      "cambios": {k: datos[k] for k in datos if k != "codigo"}})
    return _dict(a, True)


def guardar_ambito(db: Session, user: Usuario, atributo_id: int, ambito_id: int | None, datos: dict) -> dict:
    exigir(user, "clasificacion.configurar")
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
        from app.modulos.clasificacion import validacion_config as v

        tipo = (datos.get("tipo_ambito") or "").upper()
        cod = (datos.get("codigo_ambito") or "").strip()
        if tipo not in AMBITOS or not cod:
            raise ErrorNegocio("Choose the scope type and its code.", 422, "validacion")
        cod = v.ambito(db, tipo, cod)
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
    if "condicion" in datos:
        from app.modulos.clasificacion import validacion_config as v

        x.condicion = v.condiciones(v.Contexto(db), datos["condicion"], f"{a.codigo} (scope condition)")
    db.add(x)
    db.flush()
    return _dict(a, True)
