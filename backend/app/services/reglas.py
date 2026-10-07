"""Reglas de clasificación en datos (ReglaClasificacion, CondicionRegla).

- Reglas del sistema: hojas Classification_Rules y Rule_Conditions del paquete
  del motor dinámico (02). Describen cómo decide el motor (solo capítulos
  habilitados, la nota legal manda sobre la similitud de texto, preguntar solo
  lo que discrimina, revisión si queda ambigüedad…).
- Selección nacional (NATIONAL_SELECT): las condiciones del producto que eligen
  un código nacional dentro de su subpartida. Antes vivían en el propio código
  (IncisoNacional.cond/prio); ahora son reglas que se pueden revisar, apagar y
  priorizar sin tocar el dato oficial.
- Reglas de las familias (SHEET_RULES): reglas de sistema por categoría,
  sembradas desde data/motor/familias y escritas con las Notas Explicativas
  del SA (cada efecto dice qué nota la respalda; tests/test_familias_notas.py
  fija sus casos). Ámbito CATEGORY, condiciones sobre atributos y hechos
  derivados de la composición, y RESTRICT al código (o mapa fibra →
  subpartida). Se editan, apagan y priorizan como cualquier regla.
"""
import hashlib
import json

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import CondicionRegla, DominioClasificacion, IncisoNacional, ReglaClasificacion, Usuario
from .common import ErrorNegocio, exigir, filtro_texto, registrar
from .meta import cond_texto
from .oficial import _si, _txt

TIPOS = ("HARD_CONSTRAINT", "SOFT_SIGNAL", "QUESTION_GATE", "REVIEW_GATE", "NATIONAL_SELECT")
AMBITOS = ("SYSTEM", "DOMAIN", "CHAPTER", "HEADING", "SUBHEADING", "CATEGORY", "NATIONAL_CODE")
OPERADORES = ("EQUAL", "NOT_EQUAL", "IN", "GT", "GTE", "LT", "LTE", "BETWEEN", "EXISTS")
# Operadores que entiende el motor de la ficha para elegir el código nacional
OPERADORES_NACIONAL = {"EQUAL", "IN", "LTE", "GT"}


def _valor(v):
    """Valor de la hoja: Yes/No → sí/no; números como número; lo demás, texto."""
    t = _txt(v)
    if t is None:
        return None
    if t.lower() in ("yes", "no", "true", "false"):
        return t.lower() in ("yes", "true")
    try:
        return int(t) if t.lstrip("-").isdigit() else float(t)
    except ValueError:
        return t


# ---- Carga desde el paquete oficial -------------------------------------------------
def importar_hojas(db: Session, hojas: dict, cuenta, error) -> None:
    from .atributos import _codigo_ambito, _condiciones_hoja
    from .validacion_config import Contexto

    dominios = {d.codigo for d in db.scalars(select(DominioClasificacion))}
    for f in hojas.get("Classification_Rules", []):
        cod = _txt(f.get("rule_id"))
        tipo = (_txt(f.get("rule_type")) or "").upper()
        amb = (_txt(f.get("scope_type")) or "SYSTEM").upper()
        if not cod or tipo not in TIPOS or amb not in AMBITOS:
            error("Classification_Rules", f["_fila"], f"Rule ID, a rule type ({', '.join(TIPOS)}) and a scope type are required.")
            continue
        codigo_ambito = (_txt(f.get("scope_code")) or "ALL")
        if amb != "NATIONAL_CODE":
            codigo_ambito, problema = _codigo_ambito(db, amb, codigo_ambito, dominios)
            if problema:
                error("Classification_Rules", f["_fila"], problema)
                continue
        x = db.scalar(select(ReglaClasificacion).where(ReglaClasificacion.codigo == cod))
        nuevo = x is None
        x = x or ReglaClasificacion(codigo=cod)
        x.tipo_ambito, x.codigo_ambito = amb, codigo_ambito
        x.tipo_regla, x.prioridad = tipo, int(f.get("priority") or 0)
        x.tipo_fuente = (_txt(f.get("source_type")) or "INTERNAL_ENGINE").upper()
        x.familia, x.efecto = _txt(f.get("rule_family")), _txt(f.get("rationale_effect"))
        x.activo = _si(f.get("active")) if f.get("active") is not None else True
        x.requiere_revision = _si(f.get("requires_review"))
        db.add(x)
        # Acción (opcional): qué hace la regla (Action), con qué códigos (Codes), o un código por el valor
        # de un atributo (By attribute + Code map JSON), o qué pregunta (Ask attributes). Validada como en pantalla.
        if any(_txt(f.get(k)) for k in ("action", "codes", "by_attribute", "code_map_json", "ask_attributes", "message")):
            from .atributos import json_celda

            try:
                with db.begin_nested():
                    accion = {"tipo": _txt(f.get("action")), "mensaje": _txt(f.get("message")),
                              "codigos": [c.strip() for c in str(_txt(f.get("codes")) or "").replace(";", ",").split(",") if c.strip()],
                              "por": _txt(f.get("by_attribute")), "mapa": json_celda(f.get("code_map_json"), "Code map JSON"),
                              "atributos": [c.strip() for c in str(_txt(f.get("ask_attributes")) or "").replace(";", ",").split(",") if c.strip()]}
                    _forma(x, {"accion": {k: v for k, v in accion.items() if v not in (None, "", [])}})
                    db.flush()
            except ErrorNegocio as e:
                error("Classification_Rules", f["_fila"], f"{cod}: {e}")
                continue
        cuenta("Classification_Rules", nuevo)
    db.flush()
    # Las condiciones de cada regla se reemplazan completas (la hoja es la verdad). Un campo es un
    # atributo de la ficha (por su código o un alias, que se resuelve) o un campo del producto; las
    # reglas internas del motor (INTERNAL_ENGINE) describen campos del sistema y no se validan.
    ctx = Contexto(db)
    por_regla: dict[str, list] = {}
    for f in hojas.get("Rule_Conditions", []):
        por_regla.setdefault(_txt(f.get("rule_id")) or "", []).append(f)
    for cod, filas in por_regla.items():
        r = db.scalar(select(ReglaClasificacion).where(ReglaClasificacion.codigo == cod))
        if not r:
            for f in filas:
                error("Rule_Conditions", f["_fila"], f"Rule {cod or '(empty)'} does not exist.")
            continue
        conds = _condiciones_hoja(filas, "Rule_Conditions", error, None if r.tipo_fuente == "INTERNAL_ENGINE" else ctx)
        if conds is None:
            continue
        nuevas = [CondicionRegla(**c) for c in conds]
        creadas = not r.condiciones
        firma = lambda cs: [(c.grupo, c.campo, c.operador, c.valor, c.valor_hasta, bool(c.negado)) for c in cs]  # noqa: E731
        if firma(nuevas) != firma(r.condiciones):  # iguales: no se reemplazan (sin cambios falsos en la previa)
            r.condiciones = nuevas
        for _ in nuevas:
            cuenta("Rule_Conditions", creadas)
    db.flush()


# ---- Consulta -----------------------------------------------------------------------
def _cond_dict(c: CondicionRegla) -> dict:
    return {"id": c.id, "grupo": c.grupo, "campo": c.campo, "operador": c.operador, "valor": c.valor,
            "valor_hasta": c.valor_hasta, "negado": c.negado}


def _dict(r: ReglaClasificacion) -> dict:
    d = {c: getattr(r, c) for c in ("id", "codigo", "tipo_ambito", "codigo_ambito", "pais", "tipo_regla", "prioridad",
                                     "tipo_fuente", "familia", "efecto", "accion", "activo", "requiere_revision", "actualizado_en", "revision", "nota_id")}
    d["capa"] = {"LEGAL_NOTE": "LEGAL", "NATIONAL_TARIFF": "LEGAL", "MANUAL": "PROPIA"}.get(r.tipo_fuente, "SISTEMA")
    d["editable_completa"] = r.tipo_regla != "NATIONAL_SELECT" and r.tipo_fuente != "INTERNAL_ENGINE"
    d["condiciones"] = [_cond_dict(c) for c in r.condiciones]
    if r.inciso:
        x = r.inciso
        d["inciso"] = {"id": x.id, "codigo": x.codigo, "descripcion": x.descripcion, "dai": x.dai, "fuente": x.fuente, "activo": x.activo}
        from sqlalchemy.orm import object_session

        d["cond_txt"] = cond_texto(object_session(r), r.cond())
    return d


def _fuente(db: Session, r: ReglaClasificacion, datos: dict) -> None:
    """Una regla propia puede declararse LEGAL (fundada en una nota legal, que se
    referencia): entonces es un límite que ninguna otra regla puede violar."""
    from ..models import NotaSAC

    if datos.get("tipo_fuente") in ("MANUAL", "LEGAL_NOTE"):
        r.tipo_fuente = datos["tipo_fuente"]
    if datos.get("nota_id") is not None:
        r.nota_id = datos["nota_id"] or None
    nota = db.get(NotaSAC, r.nota_id) if r.nota_id else None
    if r.nota_id and not nota:
        raise ErrorNegocio("The legal note does not exist.", 422, "validacion")
    if r.tipo_fuente == "LEGAL_NOTE" and not r.nota_id:
        raise ErrorNegocio("A legal rule must reference the legal note that supports it.", 422, "validacion")
    # Solo el texto oficial publicado es ley: una guía o un resumen no fundan una regla legal
    if r.tipo_fuente == "LEGAL_NOTE" and not nota.oficial:
        raise ErrorNegocio("A legal rule must cite an official legal text, not internal guidance or a classifier summary.",
                           422, "nota_no_oficial")


def _firma_completa(r: ReglaClasificacion) -> str:
    from .motor_clasificacion import firma_regla, foto_regla

    return firma_regla({**foto_regla(r), "revision": 0, "activo": r.activo})


def listar(db: Session, user: Usuario, q: str | None = None, tipo: str | None = None, pais: str | None = None,
           page: int = 1, size: int = 50, fuente: str | None = None) -> dict:
    exigir(user, "clasificacion.ver")
    consulta = select(ReglaClasificacion).options(selectinload(ReglaClasificacion.inciso))
    if tipo:
        consulta = consulta.where(ReglaClasificacion.tipo_regla == tipo)
    if pais:
        consulta = consulta.where(ReglaClasificacion.pais == pais.upper())
    if fuente:
        consulta = consulta.where(ReglaClasificacion.tipo_fuente == fuente.upper()) if not fuente.startswith("-") else \
            consulta.where(ReglaClasificacion.tipo_fuente != fuente[1:].upper())
    if q:
        digitos = "".join(ch for ch in q if ch.isdigit())
        consulta = consulta.where(or_(
            filtro_texto(q, lambda p: [ReglaClasificacion.codigo.ilike(p), ReglaClasificacion.familia.ilike(p),
                                       ReglaClasificacion.efecto.ilike(p), ReglaClasificacion.codigo_ambito.ilike(p),
                                       ReglaClasificacion.condiciones.any(CondicionRegla.campo.ilike(p))]),
            *([ReglaClasificacion.inciso.has(IncisoNacional.codigo.startswith(digitos))] if len(digitos) >= 4 else [])))
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    filas = db.scalars(consulta.order_by(ReglaClasificacion.tipo_regla != "HARD_CONSTRAINT", -ReglaClasificacion.prioridad,
                                         ReglaClasificacion.pais, ReglaClasificacion.codigo_ambito, ReglaClasificacion.codigo)
                       .offset((page - 1) * size).limit(size)).all()
    por_tipo = dict(db.execute(select(ReglaClasificacion.tipo_regla, func.count()).where(ReglaClasificacion.tipo_fuente != "SHEET_RULES")
                               .group_by(ReglaClasificacion.tipo_regla)).all())
    por_tipo["SHEET_RULES"] = db.scalar(select(func.count()).select_from(ReglaClasificacion).where(ReglaClasificacion.tipo_fuente == "SHEET_RULES")) or 0
    return {"items": [_dict(r) for r in filas], "total": total, "page": page, "size": size, "por_tipo": por_tipo}


# ---- Edición ------------------------------------------------------------------------
ACCIONES = ("RESTRICT", "EXCLUDE", "BOOST", "ASK", "REVIEW", "WARN")
TIPOS_PROPIOS = ("HARD_CONSTRAINT", "SOFT_SIGNAL", "QUESTION_GATE", "REVIEW_GATE")
ACCION_DE = {"HARD_CONSTRAINT": ("RESTRICT", "EXCLUDE"), "SOFT_SIGNAL": ("BOOST",), "QUESTION_GATE": ("ASK",), "REVIEW_GATE": ("REVIEW", "WARN")}


def db_de(r: ReglaClasificacion):
    from sqlalchemy.orm import object_session

    from ..db import SessionLocal

    return object_session(r) or SessionLocal()


def _forma(r: ReglaClasificacion, datos: dict) -> None:
    """Ámbito, tipo y acción de una regla propia, validados."""
    for k in ("tipo_ambito", "codigo_ambito", "tipo_regla"):
        if datos.get(k):
            setattr(r, k, str(datos[k]).strip().upper() if k != "codigo_ambito" or r.tipo_ambito != "CATEGORY" else str(datos[k]).strip())
    if r.tipo_ambito not in AMBITOS or r.tipo_ambito == "NATIONAL_CODE":
        raise ErrorNegocio("Choose a scope: system, domain, category, chapter, heading or subheading.", 422, "validacion")
    if r.tipo_regla not in TIPOS_PROPIOS:
        raise ErrorNegocio("Choose a rule type: hard constraint, signal, question gate or review gate.", 422, "validacion")
    from . import validacion_config as v

    r.codigo_ambito = v.ambito(db_de(r), r.tipo_ambito, r.codigo_ambito)  # la categoría o el dominio existen; los dígitos cuadran
    if datos.get("accion") is not None:
        a = dict(datos["accion"])
        a["tipo"] = (a.get("tipo") or ACCION_DE[r.tipo_regla][0]).upper()
        if a["tipo"] not in ACCION_DE[r.tipo_regla]:
            raise ErrorNegocio(f"A {r.tipo_regla} rule can only {', '.join(ACCION_DE[r.tipo_regla])}.", 422, "validacion")
        a["codigos"] = ["".join(ch for ch in str(c) if ch.isdigit()) for c in (a.get("codigos") or []) if str(c).strip()]
        if any(len(c) < 2 for c in a["codigos"]):
            raise ErrorNegocio("Codes must have at least 2 digits.", 422, "validacion")
        if a.get("mapa") is not None:
            # Código según el valor de un hecho (p. ej. subpartida por fibra predominante)
            if not isinstance(a["mapa"], dict) or not (a.get("por") or "").strip():
                raise ErrorNegocio("A code map needs the field it depends on and a code for each value.", 422, "validacion")
            a["mapa"] = {str(k): "".join(ch for ch in str(v) if ch.isdigit()) for k, v in a["mapa"].items() if str(v).strip()}
            a["codigos"] = sorted(set(a["codigos"]) | set(a["mapa"].values()))
        if a["tipo"] in ("RESTRICT", "EXCLUDE", "BOOST") and not a["codigos"] and r.tipo_ambito not in ("CHAPTER", "HEADING", "SUBHEADING"):
            raise ErrorNegocio("Say which codes the rule restricts, excludes or raises.", 422, "validacion")
        # Nunca una regla hacia un código que no existe en el árbol de la versión vigente. Una partida
        # con una sola subpartida (3910 → 3910.00) se escribe como esa subpartida
        from .motor_clasificacion import codigo_existe, codigos_invalidos

        sesion = db_de(r)
        a["codigos"] = [c + "00" if len(c) == 4 and not codigo_existe(sesion, c) and codigo_existe(sesion, c + "00") else c for c in a["codigos"]]
        if a.get("mapa"):
            a["mapa"] = {k: (c + "00" if len(c) == 4 and not codigo_existe(sesion, c) and codigo_existe(sesion, c + "00") else c)
                         for k, c in a["mapa"].items()}

        malos = codigos_invalidos(db_de(r), a["codigos"])
        if malos:
            raise ErrorNegocio(f"These codes do not exist in the tariff in force: {', '.join(malos)}.", 422, "codigo_inexistente")
        if a["tipo"] == "ASK" and not a.get("atributos"):
            raise ErrorNegocio("Say which attributes the rule asks.", 422, "validacion")
        ctx = v.Contexto(db_de(r))
        if a.get("atributos"):
            a["atributos"] = [ctx.atributo(x, "The rule asks").codigo for x in a["atributos"]]
        if a.get("por"):
            a["por"] = ctx.campo(a["por"], "The code map depends on")
        r.accion = {k: v for k, v in a.items() if v not in (None, "", [])}
    if not r.accion:
        raise ErrorNegocio("The rule needs an action.", 422, "validacion")


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    """Regla propia (custom): ámbito, condiciones (grupos Y, entre grupos O),
    acción y prioridad. Se versiona en la bitácora y se apaga, no se borra."""
    exigir(user, "clasificacion.configurar")
    n = (db.scalar(select(func.count()).select_from(ReglaClasificacion).where(ReglaClasificacion.codigo.like("R-USR-%"))) or 0) + 1
    r = ReglaClasificacion(codigo=f"R-USR-{n:04d}", tipo_fuente="MANUAL", familia=(datos.get("familia") or "CUSTOM")[:30],
                           prioridad=int(datos.get("prioridad") or 500), efecto=datos.get("efecto"),
                           requiere_revision=bool(datos.get("requiere_revision")), activo=True,
                           tipo_ambito="SYSTEM", codigo_ambito="ALL", tipo_regla="HARD_CONSTRAINT")
    db.add(r)
    _forma(r, {"tipo_ambito": "SYSTEM", "codigo_ambito": "ALL", **datos})
    _fuente(db, r, datos)
    db.flush()
    d = guardar(db, user, r.id, {"condiciones": datos.get("condiciones") or []})
    r.revision = d["revision"] = 1  # la regla nace en su primera revisión
    return d



def guardar(db: Session, user: Usuario, regla_id: int, datos: dict) -> dict:
    """Activa/desactiva, cambia prioridad, efecto y revisión, y reemplaza las
    condiciones. Las condiciones de una línea oficial cambiadas por la empresa
    quedan como regla propia (MANUAL)."""
    exigir(user, "clasificacion.configurar")
    r = db.get(ReglaClasificacion, regla_id)
    if not r:
        raise ErrorNegocio("The rule does not exist.", 404, "no_encontrado")
    antes = _firma_completa(r)
    for k in ("prioridad", "efecto", "requiere_revision", "activo", "nota_id"):
        if datos.get(k) is not None:
            setattr(r, k, datos[k] or None if k == "nota_id" else datos[k])
    # Ámbito, tipo y acción solo en reglas propias (las del paquete y las nacionales conservan su forma)
    if r.tipo_regla != "NATIONAL_SELECT" and r.tipo_fuente != "INTERNAL_ENGINE":
        _forma(r, datos)
        if r.tipo_fuente in ("MANUAL", "LEGAL_NOTE"):
            _fuente(db, r, datos)
    if datos.get("condiciones") is not None:
        from . import validacion_config as v

        ctx = v.Contexto(db)
        nuevas = []
        for c in datos["condiciones"]:
            op = (c.get("operador") or "EQUAL").upper()
            campo = (c.get("campo") or "").strip()
            if not campo or op not in OPERADORES:
                raise ErrorNegocio(f"Each condition needs a field and an operator ({', '.join(OPERADORES)}).", 422, "validacion")
            if r.tipo_fuente != "INTERNAL_ENGINE":  # un campo que no existe dejaría la regla pendiente para siempre
                campo = ctx.campo(campo, f"Rule {r.codigo}")
            if r.tipo_regla == "NATIONAL_SELECT" and (op not in OPERADORES_NACIONAL or (op in ("LTE", "GT")) != (campo == "valorCIF")):
                raise ErrorNegocio("National selection rules use equal or one of for product attributes, and up to / over for the CIF value.",
                                   422, "validacion")
            if op == "IN" and not isinstance(c.get("valor"), list):
                raise ErrorNegocio("The one of operator needs a list of values.", 422, "validacion")
            nuevas.append(CondicionRegla(grupo=int(c.get("grupo") or 1), campo=campo, operador=op, valor=c.get("valor"),
                                         valor_hasta=c.get("valor_hasta"), negado=bool(c.get("negado"))))
        if r.tipo_regla == "NATIONAL_SELECT" and len({c.grupo for c in nuevas}) > 1:
            raise ErrorNegocio("A national selection rule has a single group of conditions.", 422, "validacion")
        clave = lambda cs: sorted((c.campo, c.operador, json.dumps(c.valor, sort_keys=True)) for c in cs)  # noqa: E731
        if r.tipo_regla == "NATIONAL_SELECT" and clave(nuevas) != clave(r.condiciones):
            r.tipo_fuente = "MANUAL"  # la empresa cambió cómo se elige la línea: ya no es la lectura del texto oficial
        r.condiciones = nuevas
    # Apagar la regla nacional solo deja de usar esas condiciones: la línea oficial no se toca
    db.flush()
    if _firma_completa(r) != antes:
        r.revision = (r.revision or 1) + 1  # la evidencia guarda la revisión y una foto de la regla
    registrar(db, user, "aranceles", r.id, "regla", {"codigo": r.codigo, "cambios": {k: datos[k] for k in datos if k != "condiciones"},
                                                       "condiciones": len(r.condiciones)})
    return _dict(r)


# ---- Reglas de las familias (sembradas desde data/motor/familias) -------------------
PREFIJOS_BASE = ("R-NE-", "R-MJS-", "R-TEC-")  # las de la base (las dos últimas, del catálogo anterior)
PRIORIDAD_MOTOR = 900  # antes que las propias (800): una regla propia posterior manda sobre ellas


def _firma_motor(condiciones: list, accion: dict) -> str:
    conds = [{k: c.get(k) for k in ("grupo", "campo", "operador", "valor", "valor_hasta", "negado")} | {"grupo": c.get("grupo") or 1,
                                                                                                        "negado": bool(c.get("negado"))}
             for c in condiciones]
    a = {k: v for k, v in (accion or {}).items() if k != "firma"}
    return hashlib.sha1(json.dumps([conds, a], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def cargar_reglas_ficha(db: Session) -> dict:
    """Siembra o pone al día las reglas de las familias. Una regla que alguien
    editó (su firma ya no coincide) no se pisa; las que la semilla ya no trae
    se apagan si nadie las tocó."""
    from .semilla_familias import semilla

    existentes = {r.codigo: r for r in db.scalars(select(ReglaClasificacion).where(ReglaClasificacion.tipo_fuente == "SHEET_RULES"))}
    n = {"nuevas": 0, "actualizadas": 0, "editadas": 0, "retiradas": 0}
    vistas = set()
    for d in semilla()["reglas"]:
        vistas.add(d["codigo"])
        conds = [{"grupo": 1, **c} for c in d["condiciones"]]
        accion = dict(d["accion"])
        firma = _firma_motor(conds, accion)
        prioridad = d.get("prioridad", PRIORIDAD_MOTOR)
        r = existentes.get(d["codigo"])
        if r:
            actual = [_cond_dict(c) for c in r.condiciones]
            if (r.accion or {}).get("firma") != _firma_motor(actual, r.accion or {}):
                n["editadas"] += 1  # alguien la cambió: se respeta
                continue
            if (r.accion or {}).get("firma") == firma and r.efecto == d.get("efecto") and r.prioridad == prioridad:
                continue
            n["actualizadas"] += 1
        else:
            r = ReglaClasificacion(codigo=d["codigo"], tipo_fuente="SHEET_RULES", activo=True)
            db.add(r)
            n["nuevas"] += 1
        tipo = accion.get("tipo") or "RESTRICT"
        r.tipo_regla = {"REVIEW": "REVIEW_GATE", "ASK": "QUESTION_GATE", "BOOST": "SOFT_SIGNAL"}.get(tipo, "HARD_CONSTRAINT")
        r.tipo_ambito, r.codigo_ambito = "CATEGORY", d["categoria"]
        r.familia, r.prioridad, r.efecto = f"NE_{d['familia'].upper()}"[:30], prioridad, d.get("efecto")
        r.requiere_revision = bool(d.get("requiere_revision"))
        r.accion = {**accion, "firma": firma}
        r.condiciones = [CondicionRegla(grupo=c["grupo"], campo=c["campo"], operador=c["operador"], valor=c.get("valor"),
                                        valor_hasta=c.get("valor_hasta"), negado=bool(c.get("negado"))) for c in conds]
    for cod, r in existentes.items():
        # Solo se retiran reglas de la base (sus prefijos); las de un paquete o de la empresa nunca
        if cod not in vistas and cod.startswith(PREFIJOS_BASE) and r.activo and (r.accion or {}).get("firma") == _firma_motor([_cond_dict(c) for c in r.condiciones], r.accion or {}):
            r.activo = False
            n["retiradas"] += 1
    db.flush()
    return n
