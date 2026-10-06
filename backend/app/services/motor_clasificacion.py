"""Motor de clasificación arancelaria: el único del sistema.

Todo producto (calzado, ropa, accesorios, químicos o una categoría creada
desde la configuración) se clasifica con `clasificar_producto`, la misma
función para la ficha, la sesión de clasificación, el guardado, la aprobación
y el lote:

    ficha natural → versión vigente → normalización y hechos derivados (ficha.py)
    → categoría + atributos + ámbitos → reglas (legales / sistema / propias)
    → árbol oficial vigente → candidatos → HS6 → SAC regional
    → código nacional por país (versión y vigencia del país)
    → alertas, preguntas, descripciones y evidencia reproducible

Precedencia de reglas (determinista):
- Capas: LEGAL (LEGAL_NOTE, NATIONAL_TARIFF) es un límite duro: lo que
  restringe o excluye no lo puede deshacer ninguna otra regla. SISTEMA
  (INTERNAL_ENGINE, SHEET_RULES, LEARNED) y PROPIA (MANUAL) compiten por prioridad.
- Prioridad: mayor número = mayor precedencia. Se evalúan de mayor a menor;
  a igual prioridad, SISTEMA antes que PROPIA y luego el código de la regla.
- RESTRICT: deja solo los códigos de la regla (intersección con lo vigente).
  Si eso dejaría vacío el conjunto, la regla queda «superada» por la de mayor
  precedencia (o «bloqueada por la ley» si choca con una legal): no se aplica
  y la evidencia dice por qué.
- EXCLUDE: quita códigos; si quitaría todos, queda superada.
- BOOST: suma puntos a códigos permitidos; nunca agrega uno restringido.
- ASK: pregunta atributos. REVIEW: exige revisión. WARN: alerta sin bloquear.
- requiere_revision en la regla: si se aplica, la clasificación queda para revisión.
- Un código de una regla siempre se valida contra el árbol de la versión.

El historial solo refuerza (BOOST) códigos que las reglas permiten; nunca se salta el motor.
"""
import copy
import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    CategoriaProducto,
    ControlCapitulo,
    DominioClasificacion,
    IncisoNacional,
    NodoArancel,
    HistorialClasificacion,
    PaisArancel,
    Marca,
    Producto,
    ReglaClasificacion,
    VersionDataset,
)
from .arbol import formato

OPERADORES = ("EQUAL", "NOT_EQUAL", "IN", "GT", "GTE", "LT", "LTE", "BETWEEN", "EXISTS")
ACCIONES = ("RESTRICT", "EXCLUDE", "BOOST", "ASK", "REVIEW", "WARN", "BUILTIN")
ACCION_TIPO = {"HARD_CONSTRAINT": "RESTRICT", "SOFT_SIGNAL": "BOOST", "QUESTION_GATE": "ASK", "REVIEW_GATE": "REVIEW"}
FAMILIAS_BASE = {"ACTIVE_CHAPTERS", "TEXT_CANDIDATES", "NEXT_BEST_QUESTION", "AMBIGUITY", "FAMILY_NOT_LEGAL", "LEGAL_PRIORITY"}
CAPA = {"LEGAL_NOTE": "LEGAL", "NATIONAL_TARIFF": "LEGAL", "INTERNAL_ENGINE": "SISTEMA", "SHEET_RULES": "SISTEMA", "CLASSIFIER": "SISTEMA", "LEARNED": "SISTEMA",
        "MANUAL": "PROPIA"}
CAPA_ORDEN = {"LEGAL": 0, "SISTEMA": 1, "PROPIA": 2}


# ---- Condiciones -------------------------------------------------------------------
def _datos_producto(db: Session, entrada: dict) -> dict:
    """Atributos que no son de la ficha sino del registro del producto (nombre,
    países de destino): se toman de ahí para no pedirlos dos veces."""
    nombre = (entrada.get("nombre") or entrada.get("estilo") or "").strip()
    paises = entrada.get("destinos") or [p.iso for p in db.scalars(select(PaisArancel).where(PaisArancel.activo.is_(True)).order_by(PaisArancel.orden))]
    out = {"destination_country": paises}
    if nombre:
        out["product_name"] = nombre
    return out


def _vacio(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _igual(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        verdad = {"true", "yes", "si", "sí", "1"}
        return (str(a).lower() in verdad if not isinstance(a, bool) else a) == (str(b).lower() in verdad if not isinstance(b, bool) else b)
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def condicion(op: str, valor_hecho, valor, valor_hasta=None, negado: bool = False) -> bool | None:
    """True/False, o None si falta el dato (la condición queda pendiente).
    Una lista IN que incluye "" admite explícitamente «sin dato»."""
    if op == "EXISTS":
        r = not _vacio(valor_hecho)
        return (not r) if negado else r
    if _vacio(valor_hecho):
        if op == "IN" and isinstance(valor, list) and "" in valor:
            return not negado
        return None
    vals = valor_hecho if isinstance(valor_hecho, list) else [valor_hecho]
    if op == "EQUAL":
        r = any(_igual(x, valor) for x in vals)
    elif op == "NOT_EQUAL":
        r = not any(_igual(x, valor) for x in vals)
    elif op == "IN":
        lista = valor if isinstance(valor, list) else [valor]
        r = any(_igual(x, y) for x in vals for y in lista if y != "")
    else:
        a, b, c = _num(vals[0]), _num(valor), _num(valor_hasta)
        if a is None or b is None:
            return None
        r = {"GT": a > b, "GTE": a >= b, "LT": a < b, "LTE": a <= b}.get(op)
        if op == "BETWEEN":
            r = c is not None and b <= a <= c
    return (not r) if negado else bool(r)


def _cond_d(c) -> dict:
    return c if isinstance(c, dict) else {"grupo": c.grupo, "campo": c.campo, "operador": c.operador, "valor": c.valor,
                                          "valor_hasta": c.valor_hasta, "negado": c.negado}


def evaluar(condiciones, hechos: dict) -> tuple[bool | None, set]:
    """Grupos O de condiciones Y. Devuelve el resultado y los campos que faltan."""
    if not condiciones:
        return True, set()
    grupos: dict[int, list] = {}
    for c in condiciones:
        d = _cond_d(c)
        grupos.setdefault(int(d.get("grupo") or 1), []).append(d)
    faltan, algun_pendiente = set(), False
    for conds in grupos.values():
        res_grupo = True
        for d in conds:
            r = condicion(d.get("operador") or "EQUAL", hechos.get(d["campo"]), d.get("valor"), d.get("valor_hasta"), bool(d.get("negado")))
            if r is False:
                res_grupo = False
                break
            if r is None:
                res_grupo = None
                faltan.add(d["campo"])
        if res_grupo is True:
            return True, set()
        if res_grupo is None:
            algun_pendiente = True
    return (None if algun_pendiente else False), faltan


def condicion_ambito(cond, hechos: dict) -> tuple[bool | None, set]:
    """Condición de un ámbito: lista de condiciones {campo, operador, valor, grupo}
    o el formato antiguo (lista de alternativas {atributo: valor})."""
    if not cond:
        return True, set()
    if all(isinstance(c, dict) and "campo" in c for c in cond):
        return evaluar(cond, hechos)
    faltan, pendiente = set(), False
    for alt in cond:
        res = True
        for k, v in (alt or {}).items():
            r = condicion("IN" if isinstance(v, list) else "EQUAL", hechos.get(k), v)
            if r is False:
                res = False
                break
            if r is None:
                res, pendiente = None, True
                faltan.add(k)
        if res is True:
            return True, set()
    return (None if pendiente else False), faltan


# ---- Versiones ---------------------------------------------------------------------
def resolver_version_vigente(db: Session, ambito: str = "REGIONAL", fecha: date | None = None) -> VersionDataset | None:
    """La versión vigente de un arancel (REGIONAL o el ISO de un país) en una
    fecha: publicada (o dinámica, para fuentes que se consultan en línea) y
    dentro de su vigencia. Si hay varias, la que empezó más tarde."""
    fecha = fecha or date.today()
    vs = [v for v in db.scalars(select(VersionDataset).where(VersionDataset.ambito == ambito.upper(),
                                                           VersionDataset.estado.in_(("PUBLICADA", "DINAMICA"))))
          if (not v.vigente_desde or v.vigente_desde <= fecha) and (not v.vigente_hasta or v.vigente_hasta >= fecha)]
    if not vs:
        return None
    return max(vs, key=lambda v: (v.estado == "PUBLICADA", v.vigente_desde or date.min, v.id))


def version_regional(db: Session, fecha: date | None = None, version_id: int | None = None) -> VersionDataset | None:
    if version_id:
        return db.get(VersionDataset, version_id)
    return resolver_version_vigente(db, "REGIONAL", fecha)


@lru_cache(maxsize=4)
def _por_codigo(version_id: int, marca: int) -> dict:
    """Código → (nivel, descripción, DAI) de la versión (en memoria)."""
    from .generico import _indice

    return {c: (n, d, dai) for c, n, d, dai, _ in _indice(version_id, marca)[0]}


@lru_cache(maxsize=4)
def _arbol(version_id: int, marca: int) -> dict:
    """Todos los códigos de la versión (capítulo, partida, subpartida, inciso): para validar."""
    from ..db import SessionLocal

    with SessionLocal() as db:
        return {c: (n, d) for c, n, d in db.execute(select(NodoArancel.codigo_norm, NodoArancel.nivel, NodoArancel.descripcion)
                                                    .where(NodoArancel.version_id == version_id, NodoArancel.pais.is_(None)))}


def _marca(v: VersionDataset) -> int:
    return int(v.importado_en.timestamp()) if v.importado_en else 0


def codigo_existe(db: Session, codigo: str, version: VersionDataset | None = None) -> bool:
    """El código (capítulo, partida, subpartida o línea SAC) existe en el árbol de la versión."""
    version = version or version_regional(db)
    cod = "".join(ch for ch in str(codigo or "") if ch.isdigit())
    return bool(version and cod and cod in _arbol(version.id, _marca(version)))


# ---- Reglas: foto y firma para la evidencia ------------------------------------------
def foto_regla(r: ReglaClasificacion) -> dict:
    return {"codigo": r.codigo, "revision": r.revision or 1, "tipo_regla": r.tipo_regla, "tipo_fuente": r.tipo_fuente,
            "capa": CAPA.get(r.tipo_fuente, "PROPIA"), "tipo_ambito": r.tipo_ambito, "codigo_ambito": r.codigo_ambito,
            "prioridad": r.prioridad, "requiere_revision": r.requiere_revision, "efecto": r.efecto, "nota_id": r.nota_id,
            "accion": {k: v for k, v in (r.accion or {}).items() if k != "firma"},
            "condiciones": [{k: v for k, v in _cond_d(c).items() if k in ("grupo", "campo", "operador", "valor", "valor_hasta", "negado")}
                            for c in r.condiciones]}


def firma_regla(foto: dict) -> str:
    return hashlib.sha1(json.dumps(foto, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def _accion(r: ReglaClasificacion) -> dict:
    a = dict(r.accion or {})
    if not a and r.tipo_fuente == "INTERNAL_ENGINE":
        a["tipo"] = "BUILTIN"
    a.setdefault("tipo", ACCION_TIPO.get(r.tipo_regla, "BUILTIN"))
    if a["tipo"] in ("RESTRICT", "EXCLUDE", "BOOST") and not a.get("codigos") and r.tipo_ambito in ("CHAPTER", "HEADING", "SUBHEADING"):
        a["codigos"] = [r.codigo_ambito]
    return a


def _aplica_a_producto(r: ReglaClasificacion, hechos: dict) -> bool:
    if r.tipo_ambito == "DOMAIN":
        return (hechos.get("dominio") or "") == r.codigo_ambito
    if r.tipo_ambito == "CATEGORY":
        return (hechos.get("categoria") or "") == r.codigo_ambito
    return True


def _clave_precedencia(r: ReglaClasificacion):
    capa = CAPA.get(r.tipo_fuente, "PROPIA")
    return (CAPA_ORDEN[capa] != 0, -(r.prioridad or 0), CAPA_ORDEN[capa], r.codigo)


@dataclass
class Candidato:
    codigo: str
    puntaje: float = 0.0
    terminos: set = field(default_factory=set)
    origen: set = field(default_factory=set)


# ---- El motor -------------------------------------------------------------------------
def clasificar_producto(db: Session, entrada: dict, *, catalogo=None, paises: bool = True, limite: int = 8) -> dict:
    """Clasifica un producto a partir de su ficha natural. `entrada`:
    categoria, dominio, ficha ({atributo: valor, comp: {parte: texto}}),
    estilo, nombre, uso, tallas, marca, proveedor, origen, texto (búsqueda
    libre), tocados (lo que eligió la persona: la detección no lo pisa),
    autos (lo que se llenó solo antes), cambio ({campo, valor}: completa lo
    que implica), detectar (por defecto sí), codigo_final (el HS6/SAC que se
    quiere aprobar: se verifica), partidas ({iso: {codigo, manual}}),
    producto_id, alertas_ok, fecha, version_id (para reproducir)."""
    from .ficha import catalogo as catalogo_db

    hoy = entrada.get("fecha") or date.today()
    if isinstance(hoy, str):
        hoy = date.fromisoformat(hoy[:10])
    v = version_regional(db, hoy, entrada.get("version_id"))
    cat = catalogo or catalogo_db(db)
    ficha = copy.deepcopy(entrada.get("ficha") or {})
    ficha.setdefault("comp", {})
    texto_det = " ".join(x for x in (entrada.get("estilo"), entrada.get("nombre")) if str(x or "").strip())
    tocados = set(entrada.get("tocados") or [])
    autos_previos = set(entrada.get("autos") or [])

    # 1. Categoría y detección por texto (sin pisar lo que eligió la persona)
    categoria = entrada.get("categoria") or None
    autos: set = set()
    detectado: dict = {}
    if entrada.get("detectar", True) and (texto_det or entrada.get("uso") or ficha.get("comp")):
        detectado = cat.detectar(ficha, entrada.get("estilo") or "", entrada.get("nombre") or "", entrada.get("uso") or "",
                                 entrada.get("tallas") or "", entrada.get("marca"), categoria)
        if not categoria and detectado.get("categoria"):
            categoria = detectado["categoria"]
            autos.add("categoria")
        for k, val in detectado.items():
            a = cat.por_codigo.get(k)
            if not a or k in tocados:
                continue
            if _vacio(ficha.get(k)) or ficha.get(k) is False or k in autos_previos:
                ficha[k] = val
                autos.add(k)
        for k in autos_previos - set(detectado) - tocados:
            a = cat.por_codigo.get(k)
            if a and k in ficha:
                ficha[k] = False if a.booleano else ""
    cobj = cat.categorias.get(categoria or "")
    dominio = entrada.get("dominio") or (cobj.dominio if cobj else None)

    # 2. Normalización y hechos derivados
    s = cat.hechos_base(ficha, categoria, dominio, texto_det)
    if entrada.get("cambio"):
        c = entrada["cambio"]
        s[c["campo"]] = c.get("valor")
        for k in cat.aplicar_implica(s, c["campo"], c.get("valor")):
            autos.add(k)
    del_registro = _datos_producto(db, entrada)
    for k, val in del_registro.items():  # lo que ya dice el registro del producto
        if k in cat.por_codigo and _vacio(s.get(k)):
            s[k] = val
    avisos = cat.normalizar(s)
    for a in cat.atributos:  # la ficha guardada lleva lo normalizado (no los hechos derivados)
        if a.seccion == "derivado" or a.tipo_dato == "composition":
            continue
        if a.booleano and s.get(a.codigo) is False and ficha.get(a.codigo) is not False and not cat.aplica(a, s):
            continue  # el «no» por defecto de una casilla que no aplica no se guarda
        if a.codigo in s and not _vacio(s[a.codigo]):
            ficha[a.codigo] = s[a.codigo]
        elif a.codigo in ficha and not (a.booleano and ficha[a.codigo] is False):
            ficha.pop(a.codigo, None)
    hechos = {k: val for k, val in s.items() if not k.startswith("_")}
    for a in cat.atributos:
        if not a.usado_clasificacion and a.codigo in hechos:
            hechos[a.codigo] = None  # se recoge, pero no altera la clasificación
    if entrada.get("origen"):
        hechos["origen"] = entrada["origen"]

    if not v:
        return _sin_version(categoria, ficha, hechos, avisos)

    # 3. Reglas
    marca_v = _marca(v)
    por_cod = _por_codigo(v.id, marca_v)
    reglas = list(db.scalars(select(ReglaClasificacion).options(selectinload(ReglaClasificacion.condiciones))
                             .where(ReglaClasificacion.activo.is_(True), ReglaClasificacion.tipo_regla != "NATIONAL_SELECT",
                                    or_(ReglaClasificacion.tipo_ambito != "CATEGORY", ReglaClasificacion.codigo_ambito == (categoria or "")))))
    reglas.sort(key=_clave_precedencia)
    base = {r.familia for r in reglas if _accion(r)["tipo"] == "BUILTIN" and r.familia in FAMILIAS_BASE}
    caps = {c.capitulo: c for c in db.scalars(select(ControlCapitulo))}
    habilitados = ({k for k, c in caps.items() if c.activo and c.clasificacion and not c.archivado and not c.solo_manual}
                   if "ACTIVE_CHAPTERS" in base else set(caps))
    auto_caps = {k for k in habilitados if caps[k].candidato_auto} if "ACTIVE_CHAPTERS" in base else set(caps)
    peso_dom: dict[str, float] = {}
    dom = db.scalar(select(DominioClasificacion).where(DominioClasificacion.codigo == dominio)) if dominio else None
    for dc in (dom.capitulos if dom else []):
        if dc.habilitado:
            peso_dom[dc.capitulo] = 1.5 if dc.relevancia == "PRIMARY" else 1.2
    if dom and "FAMILY_NOT_LEGAL" not in base and peso_dom:
        habilitados &= set(peso_dom)
    universo = {c for c in por_cod if len(c) == 6 and c[:2] in habilitados}

    def expandir(codigo: str) -> set:
        cod = "".join(ch for ch in str(codigo) if ch.isdigit())
        if len(cod) >= 6:
            return {cod[:6]} & universo
        return {c for c in universo if c.startswith(cod)}

    traza: list[dict] = []
    permitidos: set | None = None
    limite_legal: set | None = None
    boosts: dict[str, list] = {}
    preguntar: dict[str, int] = {}
    revision_por: list[str] = []
    alertas: list[dict] = []
    pendientes: dict[str, set] = {}
    decisiva = None
    for f in sorted(base):
        r = next(r for r in reglas if r.familia == f)
        foto = foto_regla(r)
        traza.append({"regla": r.codigo, "revision": r.revision or 1, "firma": firma_regla(foto), "foto": foto, "capa": CAPA.get(r.tipo_fuente, "PROPIA"),
                      "tipo_fuente": r.tipo_fuente, "prioridad": r.prioridad, "resultado": True, "efecto": f"BUILTIN {f}", "aplicada": True})
    for r in reglas:
        a = _accion(r)
        if a["tipo"] == "BUILTIN" or not _aplica_a_producto(r, hechos):
            continue
        capa = CAPA.get(r.tipo_fuente, "PROPIA")
        foto = foto_regla(r)
        fila = {"regla": r.codigo, "revision": r.revision or 1, "firma": firma_regla(foto), "capa": capa, "tipo_fuente": r.tipo_fuente,
                "prioridad": r.prioridad, "efecto": a["tipo"]}
        res, faltan = evaluar(r.condiciones, hechos)
        if res is None:
            pendientes[r.codigo] = faltan
            traza.append({**fila, "resultado": None, "faltan": sorted(faltan), "aplicada": False})
            continue
        if res is False:
            traza.append({**fila, "resultado": False, "aplicada": False})
            continue
        codigos = [c for c in (a.get("codigos") or []) if c]
        if a.get("por") and isinstance(a.get("mapa"), dict):
            val = hechos.get(a["por"])
            elegido = a["mapa"].get("" if _vacio(val) else str(val))
            if _vacio(val):
                pendientes.setdefault(r.codigo, set()).add(a["por"])
            if not elegido:
                traza.append({**fila, "resultado": None, "faltan": [a["por"]], "aplicada": False})
                continue
            codigos = [elegido]
        efecto, motivo, aplicada = a["tipo"], None, True
        if efecto in ("RESTRICT", "EXCLUDE"):
            conj = set().union(*(expandir(c) for c in codigos)) if codigos else set()
            vigente = permitidos if permitidos is not None else universo
            nuevo = (vigente & conj) if efecto == "RESTRICT" else (vigente - conj)
            if capa == "LEGAL":
                limite_legal = nuevo if limite_legal is None else (limite_legal & nuevo)
                if not nuevo:
                    revision_por.append(f"Legal rules {r.codigo} conflict: no code satisfies them.")
            if not nuevo and capa != "LEGAL":
                aplicada = False
                choca_ley = limite_legal is not None and not (conj & limite_legal) if efecto == "RESTRICT" else False
                motivo = "blocked_by_legal" if choca_ley else f"overridden_by:{decisiva or 'higher precedence'}"
            else:
                permitidos = nuevo
                if efecto == "RESTRICT":
                    decisiva = decisiva or r.codigo
        elif efecto == "BOOST":
            for c in codigos:
                for x in expandir(c):
                    boosts.setdefault(x, []).append((float(a.get("peso") or 5), f"regla:{r.codigo}"))
        elif efecto == "ASK":
            for at in a.get("atributos") or []:
                preguntar[at] = max(preguntar.get(at, 0), r.prioridad)
        elif efecto == "REVIEW":
            revision_por.append(a.get("mensaje") or r.efecto or r.codigo)
        elif efecto == "WARN":
            alertas.append({"nivel": "aviso", "origen": "regla", "msg": a.get("mensaje") or r.efecto or r.codigo, "regla": r.codigo})
        if aplicada and r.requiere_revision:
            revision_por.append(r.efecto or f"Rule {r.codigo} requires review.")
        traza.append({**fila, "resultado": True, "codigos": codigos, "mensaje": a.get("mensaje"), "aplicada": aplicada, "motivo": motivo,
                      "foto": foto})

    # 4. Candidatos: texto, dominio, reglas e historial (el historial solo refuerza)
    cands: dict[str, Candidato] = {}
    terminos = _terminos(cat, entrada, ficha, hechos)
    zona = permitidos if permitidos is not None else universo
    if "TEXT_CANDIDATES" in base and terminos:
        from .generico import _indice

        nodos, df = _indice(v.id, marca_v)
        total = max(len(nodos), 1)
        idf = {t: math.log(1 + total / (1 + df.get(t, 0))) for t in terminos}
        alcance = {t: {t} | ({w for w in df if w.startswith(t)} if len(t) >= 5 else set()) for t in terminos}
        for cod, _nivel, _d, _dai, ps in nodos:
            if cod[:6] not in zona:
                continue
            hit = [t for t in terminos if not ps.isdisjoint(alcance[t])]
            if not hit:
                continue
            c = cands.setdefault(cod[:6], Candidato(cod[:6]))
            c.puntaje = max(c.puntaje, sum(idf[t] for t in hit) * peso_dom.get(cod[:2], 1.0))
            c.terminos.update(hit)
            c.origen.add("texto")
    if permitidos is not None:
        for x in permitidos:
            c = cands.setdefault(x, Candidato(x))
            c.puntaje += 10 / max(len(permitidos), 1)
            c.origen.add(f"regla:{decisiva}" if decisiva else "regla")
    for x, lst in boosts.items():
        if x in zona:
            c = cands.setdefault(x, Candidato(x))
            for p, o in lst:
                c.puntaje += p
                c.origen.add(o)
    perfil = _perfil(categoria, hechos, traza)
    historial = _historial(db, entrada, categoria, perfil)
    for x, n in historial["tally"].items():
        if x in zona:
            c = cands.setdefault(x, Candidato(x))
            c.puntaje += min(3.0 * n, 9.0)
            c.origen.add("historial")

    lista = sorted(cands.values(), key=lambda c: (-c.puntaje, c.codigo))
    manual = bool(dom and dom.modo == "MANUAL")
    hs6 = lista[0].codigo if lista else None
    auto_ok = bool(hs6 and hs6[:2] in auto_caps and not manual)
    por_regla = bool(lista and any(o.startswith("regla") for o in lista[0].origen))
    if permitidos is not None and len(permitidos) == 1:
        confianza = "high"
    elif len(lista) == 1 or (len(lista) > 1 and lista[0].puntaje >= 1.5 * lista[1].puntaje):
        confianza = "medium"
    else:
        confianza = "low"
    if historial["mismo"] and hs6 and historial["mismo"]["codigo"][:6] == hs6 and confianza == "medium":
        confianza = "high"
    if "AMBIGUITY" in base and len(lista) > 1 and lista[1].puntaje >= 0.67 * lista[0].puntaje and not (permitidos and len(permitidos) == 1):
        revision_por.append("Several plausible candidates remain.")
    if "TEXT_CANDIDATES" in base and lista and not por_regla and "historial" not in lista[0].origen:
        revision_por.append("The text never confirms a code by itself: a specialist reviews it.")
    if hs6 and not auto_ok:
        revision_por.append(f"Chapter {hs6[:2]} cannot be chosen automatically: choose the code by hand." if not manual
                            else f"Domain {dominio} is classified by hand.")

    # 5. Verificación del código que se quiere aprobar (o del sugerido)
    final = "".join(ch for ch in str(entrada.get("codigo_final") or "") if ch.isdigit())
    alertas += _verificar_codigo(final or hs6, v, cobj, caps, permitidos, limite_legal, traza)

    # 6. Preguntas: ámbitos, compuertas y lo que discrimina primero
    codigos_c = [c.codigo for c in lista]
    discriminan = set().union(*pendientes.values()) if pendientes and "NEXT_BEST_QUESTION" in base else set()
    usados = {c.campo for r in reglas for c in r.condiciones}
    campos, preguntas, faltantes = _campos(cat, s, ficha, codigos_c, preguntar, discriminan, autos, usados)
    for c in campos:
        c["del_registro"] = c["codigo"] in del_registro  # se toma del producto (nombre, destinos): no se pregunta
    comps = [c for c in campos if c["tipo_dato"] == "composition"]
    if comps:
        hist = _historial_composicion(db, categoria, entrada.get("producto_id"))
        for c in comps:
            c["composicion"] = cat.analizar_parte(cat.por_codigo[c["codigo"]], s, texto_det, hist, entrada.get("marca"), entrada.get("estilo"))

    # 7. SAC regional y 8. clasificación por país
    elegido = final[:6] if len(final) >= 6 else hs6
    sac = final if len(final) in (8, 10) else None
    lineas_sac = sorted(k for k in por_cod if elegido and k.startswith(elegido) and len(k) > 6)
    if not sac and len(lineas_sac) == 1:
        sac = lineas_sac[0]
    out_paises = _paises(db, elegido, sac, hechos, hoy, entrada.get("partidas") or {}, cat, categoria) if paises and elegido else []
    for p in out_paises:
        for k in p["faltan"]:
            if k in cat.por_codigo and not any(q["codigo"] == k for q in preguntas):
                preguntas.append({**_campo(cat, cat.por_codigo[k], s, ficha, "preguntar", None, False, autos), "nacional": True})

    # 9. Alertas de los datos (composición, detección, catálogo, historial)
    alertas += _alertas_datos(db, cat, s, ficha, detectado, tocados, entrada, cobj, historial, elegido)
    for x in alertas:
        x["clave"] = _clave_alerta(x["msg"])  # para marcarla como revisada
    vivas = [x for x in alertas if x["nivel"] == "error" or x["clave"] not in set(entrada.get("alertas_ok") or [])]
    datos = [x for x in vivas if x.get("origen") != "codigo"]
    if any(x["nivel"] == "error" for x in datos):
        confianza = "low"
    elif any(x["nivel"] == "aviso" for x in datos) and confianza == "high":
        confianza = "medium"

    # 10. Razones, alternativas y descripciones
    razones = _razones(traza, historial, hs6, lista)
    alternativas = [{"codigo": c.codigo, "codigo_txt": formato(c.codigo), "cuando": _desc(por_cod, c.codigo)} for c in lista[1:limite]]
    for t in traza:
        for alt in ((t.get("foto") or {}).get("accion") or {}).get("alternativas") or []:
            if alt.get("codigo") and alt["codigo"] != hs6 and not any(x["codigo"] == alt["codigo"] for x in alternativas):
                alternativas.append({**alt, "codigo_txt": formato(alt["codigo"])})
    from .descripciones import descripcion_aduana, descripcion_comercial

    desc = {"aduana": descripcion_aduana(cat, s, cobj), "comercial": descripcion_comercial(cat, s, cobj, entrada.get("marca"))}
    revision = bool(revision_por) or confianza == "low"
    nombres = {c: _desc(por_cod, c) for c in codigos_c[:limite]}
    if hs6 and hs6 not in nombres:
        nombres[hs6] = _desc(por_cod, hs6)
    oficiales = dict(nombres)
    from . import overrides

    for k, ov in overrides.vigentes(db, "NODO", list(nombres), hoy).items():  # descripción propia (capa custom)
        if ov.get("descripcion") and k in nombres:
            nombres[k] = ov["descripcion"]
    if not (entrada.get("origen") or entrada.get("sin_origen")):
        faltantes.append({"campo": "origen", "etiqueta": "Country of origin"})
    completa = not faltantes and bool(hs6) and len(hs6) == 6 and bool(entrada.get("origen") or entrada.get("sin_origen"))
    candidatos = [{"codigo": c.codigo, "codigo_txt": formato(c.codigo), "descripcion": nombres.get(c.codigo, ""), "capitulo": c.codigo[:2],
                   "titulo_capitulo": caps[c.codigo[:2]].titulo if c.codigo[:2] in caps else "", "puntaje": round(c.puntaje, 2),
                   "terminos": sorted(c.terminos), "origen": sorted(c.origen), "dominio": c.codigo[:2] in peso_dom,
                   "automatico": c.codigo[:2] in auto_caps and not manual,
                   "incisos": [{"codigo": k, "codigo_txt": formato(k), "descripcion": por_cod[k][1].split(" — ")[-1], "dai": por_cod[k][2]}
                               for k in lineas_sac_de(por_cod, c.codigo)][:6]} for c in lista[:limite]]
    evidencia = {
        "version": {"id": v.id, "codigo": v.codigo, "etiqueta": v.etiqueta, "ambito": v.ambito},
        "fecha": hoy.isoformat(), "categoria": categoria, "dominio": dominio,
        "entrada": {"ficha": ficha, "estilo": entrada.get("estilo"), "nombre": entrada.get("nombre"), "uso": entrada.get("uso"),
                    "tallas": entrada.get("tallas"), "origen": entrada.get("origen"), "texto": entrada.get("texto")},
        "hechos": {k: val for k, val in hechos.items() if not _vacio(val)},
        "reglas": [t for t in traza if t.get("resultado") is not False or t.get("capa") == "LEGAL"],
        "reglas_evaluadas": len(traza), "perfil": perfil, "historial": historial["evidencia"],
        "notas": _notas(db, traza), "overrides": [o for p in out_paises for o in p.get("overrides", [])],
    }
    return {
        "version": evidencia["version"], "categoria": _cat_dict(cobj, categoria), "dominio": dominio,
        "ficha": ficha, "autos": sorted(autos), "avisos": avisos, "detectado": detectado, "hechos": evidencia["hechos"],
        "campos": campos, "preguntas": preguntas, "faltantes": faltantes, "completa": completa,
        "clasificacion": {"hs6": {"codigo": hs6, "codigo_txt": formato(hs6) if hs6 else None, "descripcion": nombres.get(hs6, "") if hs6 else "",
                                 "descripcion_oficial": oficiales.get(hs6, "") if hs6 else "",
                                  "automatico": auto_ok},
                          "sac": {"codigo": sac, "codigo_txt": formato(sac) if sac else None,
                                  "opciones": [{"codigo": k, "codigo_txt": formato(k), "descripcion": _desc(por_cod, k)} for k in lineas_sac][:20]},
                          "paises": out_paises},
        "confianza": confianza, "requiere_revision": revision, "revision_por": revision_por, "razones": razones,
        "alternativas": alternativas, "candidatos": candidatos, "alertas": vivas, "descripciones": desc, "perfil": perfil,
        "parecidos": historial["parecidos"], "etiquetas": _etiquetas(cat, s, cobj),
        "evidencia": evidencia, "terminos": terminos,
        # Forma corta (sesión de clasificación y pruebas)
        "hs6": hs6, "hs6_txt": formato(hs6) if hs6 else None, "sac": sac, "sac_txt": formato(sac) if sac else None,
        "revision": revision, "reglas": traza, "paises": out_paises,
    }


def clasificar(db: Session, texto: str = "", dominio: str | None = None, categoria: str | None = None,
               respuestas: dict | None = None, paises: bool = True, limite: int = 8) -> dict:
    """Sesión de clasificación por texto libre y respuestas (el mismo motor)."""
    return clasificar_producto(db, {"texto": texto, "dominio": dominio, "categoria": categoria, "ficha": dict(respuestas or {}),
                                    "detectar": False, "sin_origen": True}, paises=paises, limite=limite)


def lineas_sac_de(por_cod: dict, hs6: str) -> list[str]:
    return sorted(k for k in por_cod if k.startswith(hs6) and len(k) > 6)


def _desc(por_cod: dict, cod: str) -> str:
    x = por_cod.get(cod)
    return x[1].split(" — ")[-1] if x else ""


def _cat_dict(c, codigo):
    if not c:
        return {"codigo": codigo, "nombre": codigo} if codigo else None
    return {"codigo": c.codigo, "nombre": c.nombre, "nombre_corto": c.nombre_corto, "dominio": c.dominio, "familia": c.familia,
            "capitulos": c.capitulos}


def _sin_version(categoria, ficha, hechos, avisos) -> dict:
    vacio = {"hs6": None, "sac": None, "paises": []}
    return {"version": None, "categoria": {"codigo": categoria} if categoria else None, "ficha": ficha, "autos": [], "avisos": avisos,
            "hechos": hechos, "campos": [], "preguntas": [], "faltantes": ["No tariff version is in force"], "completa": False,
            "clasificacion": vacio, "confianza": "low", "requiere_revision": True, "revision_por": ["No tariff version is in force."],
            "razones": [], "alternativas": [], "candidatos": [], "alertas": [], "descripciones": {"aduana": "", "comercial": ""},
            "evidencia": {}, "hs6": None, "sac": None, "revision": True, "reglas": [], "paises": []}


def _terminos(cat, entrada, ficha, hechos) -> list[str]:
    from .generico import palabras

    extra = []
    for k, val in ficha.items():
        a = cat.por_codigo.get(k)
        if not a or not a.usado_clasificacion or a.tipo_dato == "composition":
            continue
        for x in (val if isinstance(val, list) else [val]):
            o = a.opcion(x) if not isinstance(x, bool) else None
            if o:
                extra.append(o.etiqueta)
            elif isinstance(x, str) and a.tipo_dato == "text":
                extra.append(x)
    return list(dict.fromkeys(palabras(f"{entrada.get('texto') or ''} {' '.join(extra)}")))


def _perfil(categoria, hechos, traza) -> str:
    """Lo que decidió la clasificación: la categoría y los hechos que leyeron las reglas aplicadas."""
    usados = sorted({c["campo"] for t in traza if t.get("aplicada") and t.get("foto") for c in t["foto"]["condiciones"]}
                    | {t["foto"]["accion"]["por"] for t in traza if t.get("aplicada") and t.get("foto") and t["foto"]["accion"].get("por")})
    return "|".join([categoria or "?"] + [f"{k}={hechos.get(k)}" for k in usados if not _vacio(hechos.get(k)) and k != "categoria"])[:200]


def _etiquetas(cat, s: dict, cobj) -> list[str]:
    """Palabras que describen el producto, para ordenar las notas legales de
    apoyo por relevancia (las notas llevan las mismas claves)."""
    out = set()
    if cobj:
        out.update(x for x in (cobj.codigo, cobj.familia, cobj.dominio) if x)
    for k, v in s.items():
        if k.startswith("_") or v in (None, "", False, [], {}):
            continue
        if k.startswith("comp."):
            out.add(k[5:])
            out.add("composicion")
            c = cat.lector.clase_texto(v) if isinstance(v, str) else None
            if c:
                out.add(c["clase"])
            continue
        out.add(k)
        if isinstance(v, str):
            out.add(v)
    if s.get("genero") == "U":
        out.add("unisex")
    return sorted(out)


def _historial_composicion(db: Session, categoria, pid) -> list[dict]:
    """Composiciones de los productos de la misma categoría (para sugerir materiales)."""
    if not categoria:
        return []
    q = (select(Producto.id, Producto.estilo, Producto.color, Producto.ficha, Producto.marca_id).where(Producto.tipo == categoria)
         .order_by(Producto.id.desc()).limit(400))
    marcas = {m.id: m.nombre for m in db.scalars(select(Marca))}
    return [{"estilo": x.estilo, "color": x.color, "marca": marcas.get(x.marca_id), "comp": (x.ficha or {}).get("comp") or {}}
            for x in db.execute(q) if x.id != pid]


def _historial(db: Session, entrada: dict, categoria, perfil: str) -> dict:
    """Clasificaciones aprobadas parecidas: el mismo estilo/genérico y el mismo perfil."""
    from .productos import APROBADOS

    out = {"tally": {}, "mismo": None, "evidencia": [], "mismo_estilo": [], "parecidos": []}
    if not categoria:
        return out
    pid = entrada.get("producto_id")
    q = select(Producto.id, Producto.estilo, Producto.color, Producto.codigo_generico, Producto.codigo, Producto.perfil, Producto.tipo,
               Producto.nombre, Producto.descripcion_aduana, Producto.sac_codigo).where(
        Producto.estado.in_(APROBADOS), Producto.codigo.is_not(None))
    for x in db.execute(q.where(or_(Producto.perfil == perfil, Producto.estilo == (entrada.get("estilo") or "\0"),
                                    Producto.codigo_generico == (entrada.get("generico") or "\0")))):
        if x.id == pid:
            continue
        cod = x.codigo[:6]
        mismo_est = (entrada.get("estilo") and x.estilo == entrada.get("estilo")) or (entrada.get("generico") and x.codigo_generico == entrada.get("generico"))
        if (x.perfil == perfil and x.tipo == categoria) or mismo_est:
            c = x.sac_codigo or x.codigo
            out["parecidos"].append({"id": x.id, "estilo": x.estilo, "color": x.color, "generico": x.codigo_generico, "codigo": c,
                                     "codigo_txt": formato(c), "descripcion": x.nombre or x.descripcion_aduana, "mismo_estilo": bool(mismo_est)})
        if x.perfil == perfil and x.tipo == categoria:
            out["tally"][cod] = out["tally"].get(cod, 0) + 1
        if (entrada.get("estilo") and x.estilo == entrada.get("estilo")) or (entrada.get("generico") and x.codigo_generico == entrada.get("generico")):
            out["mismo_estilo"].append({"id": x.id, "codigo": x.codigo, "color": x.color, "tipo": x.tipo})
            if x.tipo == categoria and not out["mismo"]:
                out["mismo"] = {"id": x.id, "codigo": x.codigo, "estilo": x.estilo}
                out["tally"][cod] = out["tally"].get(cod, 0) + 2
    out["evidencia"] = [{"codigo": k, "productos": n} for k, n in sorted(out["tally"].items(), key=lambda kv: -kv[1])]
    out["parecidos"] = sorted(out["parecidos"], key=lambda x: not x["mismo_estilo"])[:5]
    return out


def _razones(traza, historial, hs6, lista) -> list[str]:
    out = []
    for t in traza:
        if t.get("aplicada") and t.get("foto") and t["efecto"] in ("RESTRICT", "EXCLUDE", "BOOST"):
            ef = t["foto"].get("efecto")
            out.append(f"{t['regla']}: {ef}" if ef else f"{t['regla']} → {', '.join(formato(c) for c in t.get('codigos') or [])}")
        elif t.get("resultado") is True and not t.get("aplicada") and t.get("motivo"):
            out.append(f"{t['regla']} was not applied ({'it contradicts a legal restriction' if t['motivo'] == 'blocked_by_legal' else 'a rule with higher precedence decides'}).")
    if hs6 and historial["tally"].get(hs6):
        out.append(f"Your approved history supports {formato(hs6)} ({historial['tally'][hs6]} matching classifications).")
    if lista and lista[0].terminos and not any(o.startswith("regla") for o in lista[0].origen):
        out.append(f"Candidate from the official tariff text ({', '.join(sorted(lista[0].terminos))}).")
    return out[:30]


def _notas(db: Session, traza) -> list[dict]:
    """Notas legales que fundamentan las reglas aplicadas (evidencia, no lógica)."""
    from ..models import NotaSAC

    ids = {t["foto"]["nota_id"] for t in traza if t.get("aplicada") and t.get("foto") and t["foto"].get("nota_id")}
    if not ids:
        return []
    return [{"id": n.id, "ambito": n.ambito, "codigo": n.codigo, "numero": n.numero, "texto": n.texto[:600],
             "tipo_fuente": n.tipo_fuente, "oficial": n.oficial}
            for n in db.scalars(select(NotaSAC).where(NotaSAC.id.in_(ids)))]


def _verificar_codigo(cod, v, cobj, caps, permitidos, limite_legal, traza) -> list[dict]:
    """Un código que no existe en la versión, de un capítulo que no corresponde a
    la categoría o que contradice una regla aplicada es un error."""
    out = []
    if not cod:
        return out
    arbol = _arbol(v.id, _marca(v))
    if cod not in arbol:
        out.append({"nivel": "error", "origen": "codigo", "msg": f"Code {formato(cod)} does not exist in tariff version {v.codigo}."})
        return out
    if cobj and cobj.capitulos and cod[:2] not in cobj.capitulos:
        tit = caps[cod[:2]].titulo if cod[:2] in caps else ""
        out.append({"nivel": "error", "origen": "codigo",
                    "msg": f'Code {formato(cod)} is in chapter {cod[:2]}{f" ({tit})" if tit else ""}, which does not match "{cobj.nombre_corto or cobj.nombre}".'})
    if len(cod) >= 6:
        if limite_legal is not None and cod[:6] not in limite_legal:
            out.append({"nivel": "error", "origen": "codigo", "msg": f"Code {formato(cod)} contradicts a legal restriction for this product."})
        elif permitidos is not None and cod[:6] not in permitidos:
            reglas = [t["regla"] for t in traza if t.get("aplicada") and t.get("efecto") in ("RESTRICT", "EXCLUDE")]
            out.append({"nivel": "error", "origen": "codigo",
                        "msg": f"Code {formato(cod)} contradicts rule {', '.join(reglas) or 'of the engine'}, which allows {', '.join(formato(c) for c in sorted(permitidos)[:6])}."})
    c = caps.get(cod[:2])
    if c and not (c.activo and c.clasificacion and not c.archivado):
        out.append({"nivel": "error", "origen": "capitulo", "msg": f"Chapter {cod[:2]} ({c.titulo}) is not enabled for classification."})
    elif c and c.solo_manual:
        out.append({"nivel": "aviso", "origen": "capitulo", "msg": f"Chapter {cod[:2]} is manual only: confirm the code with the legal notes."})
    return out


# ---- Campos para la ficha (el frontend solo los dibuja) --------------------------------------
def _campo(cat, a, s, ficha, estado, amb, discrimina, autos) -> dict:
    val = s.get(a.codigo)
    deriv = cat.derivar(a, s) if a.derivacion else None
    ops = []
    for o in a.opciones:
        msg = cat.bloqueo_opcion(a, o, s)
        if deriv is not None and o.codigo != deriv:
            msg = msg or "Defined by the data"
        ops.append({"codigo": o.codigo, "etiqueta": o.etiqueta, "bloqueada": bool(msg), "motivo": msg})
    return {"codigo": a.codigo, "etiqueta": a.etiqueta, "tipo_dato": a.tipo_dato, "seccion": a.seccion, "ayuda": a.ayuda, "unidad": a.unidad,
            "control": a.control or ("lista" if len(a.opciones) > 6 else "botones"), "informativo": a.informativo,
            "modo": amb.modo if amb else "SHOW", "nota_ambito": amb.nota if amb else None, "estado": estado,
            "valor": val, "derivado": deriv is not None, "motivo_derivado": cat.motivo_derivado(a, s) if deriv is not None else None,
            "auto": a.codigo in autos, "discrimina": discrimina, "opciones": ops, "orden": a.orden,
            "bloqueo_casilla": cat.bloqueo_casilla(a, s) if a.booleano else None,
            "respondida": not _vacio(val) and not (a.booleano and val is False and a.valor_defecto is None)}


def _campos(cat, s, ficha, codigos, forzadas, discriminan, autos, usados=frozenset()):
    campos, preguntas, faltantes = [], [], []
    for a in cat.atributos:
        amb = cat.ambito(a, s, codigos)
        aplica = bool(amb) and amb.modo != "HIDE"
        if a.codigo in forzadas or a.codigo in discriminan:
            aplica = aplica or a.seccion != "derivado"
        if not aplica:
            continue
        if a.tipo_dato == "composition":
            e = "preguntar"
        elif a.codigo in forzadas or (a.codigo in discriminan and _vacio(s.get(a.codigo))):
            e = "preguntar"
        else:
            e = cat.estado(a, s, codigos)
            if e == "oculto" and a.seccion in ("producto", "caracteristicas") and not amb:
                continue
        d = _campo(cat, a, s, ficha, e, amb, a.codigo in discriminan, autos)
        # Lo que decide el código o es obligatorio va arriba; los datos oficiales
        # opcionales que ninguna regla usa, en «más datos»
        d["principal"] = not (a.origen == "OFICIAL" and d["modo"] != "REQUIRE" and not d["discrimina"] and a.codigo not in usados)
        campos.append(d)
        requerido = (amb and amb.modo == "REQUIRE") or a.codigo in discriminan
        if requerido and _vacio(s.get(a.codigo)) and a.seccion != "derivado":
            faltantes.append({"campo": a.codigo, "etiqueta": a.etiqueta})
        if a.tipo_dato == "composition" and requerido and s.get(a.codigo):
            from .composicion import total_filas

            tot = total_filas(cat.lector.filas(s[a.codigo]))
            if abs(tot - 100) > 0.05:
                faltantes.append({"campo": a.codigo, "etiqueta": f"{a.etiqueta} adds up to {tot:g}%"})
        if e == "preguntar" and a.seccion in ("caracteristicas", "producto", "nacional", "composicion"):
            preguntas.append(d)
    preguntas.sort(key=lambda d: (d["respondida"], not d["discrimina"], d["modo"] != "REQUIRE", d["orden"]))
    return campos, preguntas, faltantes


# ---- Alertas de los datos ----------------------------------------------------------------------
def _cond_txt(cond: dict | None, cat) -> str:
    """Condición de una línea nacional en palabras (etiquetas del catálogo)."""
    out = []
    for k, v in (cond or {}).items():
        a = cat.por_codigo.get(k) if cat else None
        txt = []
        for x in v if isinstance(v, list) else [v]:
            o = a.opcion(x) if a and isinstance(x, str) else None
            txt.append(o.etiqueta if o else ("Yes" if x is True else "No" if x is False else str(x)))
        out.append(f"{a.etiqueta if a else k}: {' / '.join(txt)}")
    return "; ".join(out)


def _clave_alerta(msg: str) -> str:
    h = 5381
    for ch in str(msg):
        h = ((h << 5) + h + ord(ch)) & 0xFFFFFFFF
    return _b36(h)


def _b36(n: int) -> str:
    dig = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = dig[r] + out
        if not n:
            return out


def _alertas_datos(db, cat, s, ficha, detectado, tocados, entrada, cobj, historial, elegido) -> list[dict]:
    import re

    from .composicion import MAT_AMBIGUAS, pesos_de, FIBRAS, MAT_CALZ, segmentos

    out: list[dict] = []

    def add(nivel, msg, origen="datos"):
        if not any(x["msg"] == msg for x in out):
            out.append({"nivel": nivel, "origen": origen, "msg": msg})

    L = cat.lector
    for a in cat.atributos:
        if a.tipo_dato != "composition" or not cat.aplica(a, s):
            continue
        txt = s.get(a.codigo)
        if not txt or not str(txt).strip():
            continue
        parte = a.codigo.split(".", 1)[1]
        es_mat = parte in ("corte", "suela", "material") or (cobj and cobj.familia in ("bolso", "gorra"))
        pr = L.prep(txt)
        for seg in segmentos(txt):
            pcts = [float(m.group(1).replace(",", ".")) for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*%", seg)]
            if pcts:
                tot = math.floor(sum(pcts) * 10 + 0.5) / 10
                if tot > 100.5:
                    add("error", f"{a.etiqueta}: the percentages add up to {tot:g}%.")
                elif tot < 99.5:
                    add("aviso", f"{a.etiqueta}: the percentages add up to {tot:g}%, not 100%.")
            if parte not in ("relleno", "plantilla"):
                o2 = pesos_de(seg, MAT_CALZ).get("otra", 0)
                otra = o2 if es_mat else min(pesos_de(seg, FIBRAS).get("otra", 0), o2)
                if otra and not pr["desconocidas"]:
                    add("aviso", f"{a.etiqueta}: {otra:g}% has no recognizable material.")
        if parte not in ("relleno", "plantilla") and pr["desconocidas"]:
            raras = '", "'.join(pr["desconocidas"])
            add("aviso", f'{a.etiqueta}: I do not recognize "{raras}". Tell me what it is with the list under the composition.', "material")
        for w in pr["ambiguas"]:
            add("aviso", f"{a.etiqueta}: {MAT_AMBIGUAS[w]}.")
        fz = [c for c in pr["cambios"] if c.get("de") and not c.get("aprendido")]
        if fz:
            leidos = ", ".join(f'"{c["de"]}" as {c["a"]}' for c in fz)
            add("info", f"{a.etiqueta}: I read {leidos}.")
        if any(c.get("pct") for c in pr["cambios"]):
            add("info", f"{a.etiqueta}: numbers without % were taken as percentages ({pr['s'].strip()}).")
        if parte in ("corte", "exterior", "material") and es_mat:
            pm = L.parse_mat(txt, "corte")
            if pm and pm.get("mixto") and not pm.get("pred"):
                add("aviso", f"{a.etiqueta}: mixes {' and '.join(pm['grupos'])} without percentages. Enter them by surface to know which governs.")
    # Lo que el nombre sugiere frente a lo que se eligió
    if detectado.get("categoria") and s.get("categoria") and detectado["categoria"] != s["categoria"]:
        dc = cat.categorias.get(detectado["categoria"])
        if dc and cobj and dc.familia != cobj.familia:
            add("aviso", f'The style looks like "{dc.nombre_corto or dc.nombre}", but the chosen category is "{cobj.nombre_corto or cobj.nombre}".')
    for k, val in detectado.items():
        a = cat.por_codigo.get(k)
        if not a or a.booleano or k not in tocados or _vacio(s.get(k)) or s.get(k) == val or not cat.aplica(a, s):
            continue
        o, oe = a.opcion(val), a.opcion(s.get(k))
        if o and oe:
            add("aviso", f'The style suggests "{o.etiqueta.lower()}" ({a.etiqueta.lower()}), but "{oe.etiqueta.lower()}" was chosen.')
    # Catálogos (marca y proveedor)
    from ..models import Marca, Proveedor
    from .composicion import norm as _n

    if entrada.get("marca"):
        m = next((x for x in db.scalars(select(Marca)) if _n(x.nombre).strip() == _n(entrada["marca"]).strip()), None)
        if m and m.activa is False:
            add("info", f"Brand {m.nombre} is marked as inactive.")
        if entrada.get("proveedor"):
            p = next((x for x in db.scalars(select(Proveedor)) if _n(x.nombre).strip() == _n(entrada["proveedor"]).strip()), None)
            if p and p.marcas and not any(_n(x.nombre).strip() == _n(entrada["marca"]).strip() for x in p.marcas):
                add("aviso", f"Supplier {p.nombre} does not have the brand {entrada['marca']}.")
    # El mismo estilo ya clasificado con otro código u otra categoría
    for x in historial["mismo_estilo"]:
        if elegido and x["codigo"][:6] != elegido[:6]:
            color = f" (color {x['color']})" if x.get("color") else ""
            add("aviso", f"The same style is already classified as {formato(x['codigo'])}{color}. "
                "Colors of one style usually share the same code; check which is right.", "codigo")
            break
    for x in historial["mismo_estilo"]:
        if x["tipo"] and s.get("categoria") and x["tipo"] != s["categoria"]:
            add("aviso", f'The style is recorded in another product as "{x["tipo"]}".')
            break
    return out


# ---- Clasificación por país --------------------------------------------------------------------
def _paises(db: Session, hs6: str, sac: str | None, hechos: dict, hoy: date, manuales: dict, cat=None, categoria=None) -> list[dict]:
    """Cada país por separado, con la versión vigente de su arancel. Las líneas
    salen solo de la capa oficial (fuente y versión); las reglas del motor
    eligen entre ellas y, si aún queda más de una, el historial de la empresa
    solo puede ordenarlas. Un código que no es una línea oficial vigente no se
    acepta; nunca se recorta ni se completa un código."""
    from . import overrides
    from .nacional import requisitos

    out = []
    base = sac or hs6
    for p in db.scalars(select(PaisArancel).where(PaisArancel.activo.is_(True)).order_by(PaisArancel.orden)):
        vp = version_lineas(db, p, hoy)
        lineas = _lineas(db, p.iso, hs6, vp)
        lineas = [x for x in lineas if (not x.vigente_desde or x.vigente_desde <= hoy) and (not x.vigente_hasta or x.vigente_hasta >= hoy)]
        ovs = overrides.vigentes(db, "INCISO", [x.id for x in lineas], hoy)
        aplicados = []
        vivas_l = []
        for x in lineas:
            ov = ovs.get(str(x.id)) or {}
            if ov:
                aplicados.append({"tipo": "INCISO", "objetivo": x.id, "codigo": x.codigo, "campos": ov})
            if str(ov.get("activo", "true")).lower() == "false":
                continue
            vivas_l.append((x, ov))
        lineas_ok = [x for x, _ in vivas_l if x.codigo.startswith(base)] or [x for x, _ in vivas_l]
        desc_ov = {x.id: ov.get("descripcion") for x, ov in vivas_l if ov.get("descripcion")}
        vivos, pendientes, faltan = [], [], set()
        for x in lineas_ok:
            # Una regla de selección apagada no elige: la línea queda sin condiciones
            res, f = evaluar(x.regla.condiciones, hechos) if x.regla and x.regla.activo else (True, set())
            if res is True:
                vivos.append(x)
            elif res is None:
                pendientes.append(x)
                faltan |= f
        vivos.sort(key=lambda x: (-(x.prio or 0), -len(x.cond or {})))
        mejor = vivos[0] if vivos else None
        empate = mejor and len([x for x in vivos if (x.prio or 0) == (mejor.prio or 0) and len(x.cond or {}) == len(mejor.cond or {})]) > 1
        man = manuales.get(p.iso) or {}
        mcod = "".join(ch for ch in str(man.get("codigo") or "") if ch.isdigit())  # la línea que eligió la persona
        error = None
        x = None
        historial = None
        if mcod:
            x = next((y for y in lineas if y.codigo == mcod), None)
            if not mcod.startswith(hs6):
                estado, codigo, error = "invalido", None, f"{mcod} does not belong to subheading {formato(hs6)}."
            elif x:
                estado, codigo = "ok", mcod
            else:
                estado, codigo = "invalido", None
                error = (f"{formato(mcod)} is not an official national line of {p.nombre} in force"
                         + (f" (version {vp.codigo})." if vp else ". Official national tariff data not available."))
        elif mejor and not empate and not (pendientes and len(mejor.cond or {}) == 0):
            estado, codigo, x = "ok", mejor.codigo, mejor
        elif lineas_ok:
            # Varias líneas oficiales posibles: el historial de la empresa solo puede ordenarlas
            candidatas = vivos if empate else vivos + pendientes
            historial = _preferencia_historial(db, p.iso, candidatas, hechos, categoria)
            if historial:
                estado, x = "historial", historial["linea"]
                codigo = x.codigo
            else:
                estado, codigo = "elegir", None
        else:
            estado, codigo = "pendiente", None
            error = (f"Official national tariff data not available for {p.nombre}" + (f" (version {vp.codigo})." if vp else ".")
                     if not lineas else None)
        req = requisitos(db, p.iso, codigo or base, x.dai if x else None, hoy)
        out.append({"pais": p.iso, "nombre": p.nombre, "estado": estado, "codigo": codigo, "codigo_txt": formato(codigo) if codigo else None,
                    "dai": x.dai if x else None, "inciso_id": x.id if x else None, "regla": x.regla.codigo if x and x.regla else None,
                    "descripcion": (desc_ov.get(x.id) or x.descripcion) if x else None, "fuente": x.fuente if x else None,
                    "fuente_oficial": x.fuente_id if x else None,
                    "version": {"id": vp.id, "codigo": vp.codigo} if vp else None, "longitudes": p.longitudes_validas(), "digitos": p.digitos,
                    "error": error, "manual": bool(mcod) and not (mejor and not empate and mcod == mejor.codigo),
                    "sugerido": mejor.codigo if mejor and not empate else None,
                    "historial": {k: v for k, v in historial.items() if k != "linea"} if historial else None,
                    "sin_datos_oficiales": not lineas,
                    "opciones": [{"codigo": y.codigo, "cond": y.cond, "cond_txt": _cond_txt(y.cond, cat), "descripcion": desc_ov.get(y.id) or y.descripcion,
                                  "dai": y.dai, "inciso_id": y.id}
                                 for y in (vivos + pendientes + [z for z in lineas_ok if z not in vivos and z not in pendientes])][:12],
                    "faltan": sorted(faltan), "impuestos": req["impuestos"], "regulaciones": req["regulaciones"],
                    "requisitos_estado": req.get("estado"), "overrides": aplicados})
    return out


def version_lineas(db: Session, p: PaisArancel, hoy: date | None = None) -> VersionDataset | None:
    """Versión de la que salen las líneas nacionales del país: su arancel
    nacional vigente si tiene líneas cargadas; si el país aplica tal cual las
    líneas del SAC regional a 10 dígitos (nivel_base SAC10), la versión
    regional vigente. Nunca se mezclan versiones."""
    vp = resolver_version_vigente(db, p.iso, hoy)
    if vp and db.scalar(select(IncisoNacional.id).where(IncisoNacional.pais == p.iso, IncisoNacional.version_id == vp.id).limit(1)):
        return vp
    if p.nivel_base == "SAC10":
        return resolver_version_vigente(db, "REGIONAL", hoy) or vp
    return vp


def _lineas(db: Session, iso: str, hs6: str, vp) -> list[IncisoNacional]:
    """Líneas oficiales del país para la subpartida, solo de la versión que
    aplica (nunca de otra versión ni sin fuente)."""
    if not vp:
        return []
    q = select(IncisoNacional).options(selectinload(IncisoNacional.regla)).where(
        IncisoNacional.pais == iso, IncisoNacional.sub6 == hs6, IncisoNacional.activo.is_(True),
        IncisoNacional.version_id == vp.id, IncisoNacional.fuente == "oficial")
    return list(db.scalars(q.order_by(IncisoNacional.codigo)))


def _preferencia_historial(db: Session, iso: str, candidatas: list, hechos: dict, categoria) -> dict | None:
    """Entre líneas oficiales que el motor dejó empatadas, la que más usó la
    empresa con productos como este (mismas condiciones). Es una señal
    histórica: no la hace correcta ni crea nada."""
    if len(candidatas) < 2:
        return None
    por_codigo = {y.codigo: y for y in candidatas}
    filas = db.scalars(select(HistorialClasificacion).where(HistorialClasificacion.pais == iso,
                                                            HistorialClasificacion.codigo.in_(list(por_codigo)))).all()
    puntos: dict = {}
    for h in filas:
        cond = h.condiciones or {}
        if categoria and h.categoria and h.categoria != categoria:
            continue
        if any(hechos.get(k) not in (v if isinstance(v, list) else [v]) for k, v in cond.items()):
            continue
        puntos[h.codigo] = puntos.get(h.codigo, 0) + (h.conteo or 1) * (1 + len(cond))
    if not puntos:
        return None
    orden = sorted(puntos.items(), key=lambda kv: -kv[1])
    if len(orden) > 1 and orden[0][1] == orden[1][1]:
        return None
    total = sum(puntos.values())
    cod = orden[0][0]
    return {"linea": por_codigo[cod], "codigo": cod, "historical_confidence": round(orden[0][1] / total, 2), "registros": len(filas)}


# ---- Validación de códigos de reglas ---------------------------------------------------
def codigos_invalidos(db: Session, codigos) -> list[str]:
    v = version_regional(db)
    if not v:
        return []
    arbol = _arbol(v.id, _marca(v))
    return [c for c in codigos if "".join(ch for ch in str(c) if ch.isdigit()) not in arbol]


__all__ = ["clasificar_producto", "clasificar", "resolver_version_vigente", "codigo_existe", "condicion", "evaluar", "condicion_ambito",
           "CategoriaProducto"]
