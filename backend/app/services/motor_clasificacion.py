"""Motor de clasificación en el servidor, gobernado por datos.

Un solo motor para cualquier producto:

    producto → dominio/categoría → atributos + ámbitos → reglas → árbol oficial
    → candidatos → preguntas discriminantes → HS6 → SAC regional
    → clasificación por país → regulaciones + impuestos

Todo lo que decide sale de la base:
- Atributos y ámbitos (AtributoDef/AtributoAmbito, con su condición) deciden
  qué se pregunta.
- Reglas (ReglaClasificacion/CondicionRegla) deciden qué candidatos quedan,
  suben o salen, qué se pregunta, cuándo se exige revisión y qué código
  nacional se elige. Condiciones: dentro de un grupo todas (Y); entre grupos
  basta una (O). Si falta un dato, la condición queda «pendiente» y ese
  atributo se pregunta primero (es el que discrimina).
- Las reglas del sistema (paquete 02) gobiernan el comportamiento base:
  apagarlas cambia lo que hace el motor (BUILTIN por familia).
- El árbol oficial (NodoArancel) es la única fuente de códigos; el texto solo
  genera candidatos y nunca confirma solo.
"""
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    AtributoDef,
    ControlCapitulo,
    DominioClasificacion,
    IncisoNacional,
    NodoArancel,
    PaisArancel,
    ReglaClasificacion,
    VersionDataset,
)
from .arbol import VERSION_SAC, formato

OPERADORES = ("EQUAL", "NOT_EQUAL", "IN", "GT", "GTE", "LT", "LTE", "BETWEEN", "EXISTS")
ACCIONES = ("RESTRICT", "EXCLUDE", "BOOST", "ASK", "REVIEW", "BUILTIN")
# Qué hace cada tipo de regla si no trae acción explícita
ACCION_TIPO = {"HARD_CONSTRAINT": "RESTRICT", "SOFT_SIGNAL": "BOOST", "QUESTION_GATE": "ASK", "REVIEW_GATE": "REVIEW"}
FAMILIAS_BASE = {"ACTIVE_CHAPTERS", "TEXT_CANDIDATES", "NEXT_BEST_QUESTION", "AMBIGUITY", "FAMILY_NOT_LEGAL", "LEGAL_PRIORITY"}


# ---- Evaluación de condiciones -------------------------------------------------
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
    """True/False, o None si falta el dato (la condición queda pendiente)."""
    if op == "EXISTS":
        r = not _vacio(valor_hecho)
        return (not r) if negado else r
    if _vacio(valor_hecho):
        if op == "IN" and isinstance(valor, list) and "" in valor:
            return not negado  # la lista admite «sin dato» explícitamente
        return None
    vals = valor_hecho if isinstance(valor_hecho, list) else [valor_hecho]
    if op == "EQUAL":
        r = any(_igual(x, valor) for x in vals)
    elif op == "NOT_EQUAL":
        r = not any(_igual(x, valor) for x in vals)
    elif op == "IN":
        lista = valor if isinstance(valor, list) else [valor]
        r = any(_igual(x, y) for x in vals for y in lista)
    else:
        a, b, c = _num(vals[0]), _num(valor), _num(valor_hasta)
        if a is None or b is None:
            return None
        r = {"GT": a > b, "GTE": a >= b, "LT": a < b, "LTE": a <= b}.get(op)
        if op == "BETWEEN":
            r = c is not None and b <= a <= c
    return (not r) if negado else bool(r)


def evaluar(condiciones, hechos: dict) -> tuple[bool | None, set]:
    """Grupos O de condiciones Y. Devuelve el resultado y los campos que faltan."""
    if not condiciones:
        return True, set()
    grupos: dict[int, list] = {}
    for c in condiciones:
        g = (c.get("grupo") if isinstance(c, dict) else c.grupo) or 1
        grupos.setdefault(int(g), []).append(c)
    faltan, algun_pendiente = set(), False
    for conds in grupos.values():
        res_grupo = True
        for c in conds:
            d = c if isinstance(c, dict) else {"campo": c.campo, "operador": c.operador, "valor": c.valor,
                                               "valor_hasta": c.valor_hasta, "negado": c.negado}
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
    """Condición de un ámbito de atributo: lista de alternativas {atributo: valor}
    (formato del motor) o lista de condiciones {campo, operador, valor, grupo}."""
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


# ---- Sesión de clasificación -----------------------------------------------------
@dataclass
class Candidato:
    codigo: str
    puntaje: float = 0.0
    terminos: set = field(default_factory=set)
    origen: set = field(default_factory=set)  # texto | regla:R-… | dominio
    incisos: list = field(default_factory=list)


def _accion(r: ReglaClasificacion) -> dict:
    """Las reglas del motor base (paquete 02, sin acción) gobiernan por familia
    (BUILTIN); las demás hacen lo que dice su acción o lo propio de su tipo."""
    a = dict(r.accion or {})
    if not a and r.tipo_fuente == "INTERNAL_ENGINE":
        a["tipo"] = "BUILTIN"
    a.setdefault("tipo", ACCION_TIPO.get(r.tipo_regla, "BUILTIN"))
    if a["tipo"] in ("RESTRICT", "EXCLUDE", "BOOST") and not a.get("codigos") and r.tipo_ambito in ("CHAPTER", "HEADING", "SUBHEADING"):
        a["codigos"] = [r.codigo_ambito]
    return a


@lru_cache(maxsize=4)
def _por_codigo(version_id: int, marca: int) -> dict:
    """Código → (nivel, descripción, DAI) de la versión (en memoria, como el índice de texto)."""
    from .generico import _indice

    return {c: (n, d, dai) for c, n, d, dai, _ in _indice(version_id, marca)[0]}


def _aplica_a_producto(r: ReglaClasificacion, hechos: dict) -> bool:
    if r.tipo_ambito == "DOMAIN":
        return (hechos.get("dominio") or "") == r.codigo_ambito
    if r.tipo_ambito == "CATEGORY":
        return (hechos.get("categoria") or "") == r.codigo_ambito
    return True


def clasificar(db: Session, texto: str = "", dominio: str | None = None, categoria: str | None = None,
               respuestas: dict | None = None, paises: bool = True, limite: int = 8) -> dict:
    from .generico import _indice, palabras
    from .nacional import requisitos

    import math

    respuestas = {k: v for k, v in (respuestas or {}).items() if not _vacio(v)}
    hechos = {**respuestas, "dominio": dominio or "", "categoria": categoria or ""}
    v = db.scalar(select(VersionDataset).where(VersionDataset.codigo == VERSION_SAC))
    if not v:
        return {"candidatos": [], "preguntas": [], "hs6": None, "confianza": "low", "revision": True, "reglas": [], "paises": []}
    # Las reglas de categoría solo se cargan para la categoría del producto
    reglas = list(db.scalars(select(ReglaClasificacion).options(selectinload(ReglaClasificacion.condiciones))
                             .where(ReglaClasificacion.activo.is_(True), ReglaClasificacion.tipo_regla != "NATIONAL_SELECT",
                                    or_(ReglaClasificacion.tipo_ambito != "CATEGORY", ReglaClasificacion.codigo_ambito == (categoria or "")))
                             .order_by(ReglaClasificacion.prioridad.desc(), ReglaClasificacion.codigo)))
    base = {r.familia for r in reglas if _accion(r)["tipo"] == "BUILTIN" and r.familia in FAMILIAS_BASE}
    traza: list[dict] = []
    for f in sorted(base):
        cod = next(r.codigo for r in reglas if r.familia == f)
        traza.append({"regla": cod, "resultado": True, "efecto": f"BUILTIN {f}"})

    # Universo de capítulos (R-SYS-001) y dominio (R-SYS-009: ordena; si se apaga, filtra)
    caps = {c.capitulo: c for c in db.scalars(select(ControlCapitulo))}
    habilitados = ({k for k, c in caps.items() if c.activo and c.clasificacion and not c.archivado and not c.solo_manual}
                   if "ACTIVE_CHAPTERS" in base else set(caps))
    peso_dom: dict[str, float] = {}
    if dominio:
        d = db.scalar(select(DominioClasificacion).where(DominioClasificacion.codigo == dominio))
        for dc in (d.capitulos if d else []):
            if dc.habilitado:
                peso_dom[dc.capitulo] = 1.5 if dc.relevancia == "PRIMARY" else 1.2
        if "FAMILY_NOT_LEGAL" not in base and peso_dom:
            habilitados &= set(peso_dom)

    # 1. Candidatos por texto (R-SYS-003): nunca confirman solos
    attrs = {a.codigo: a for a in db.scalars(select(AtributoDef).options(selectinload(AtributoDef.opciones), selectinload(AtributoDef.ambitos))
                                            .where(AtributoDef.activo.is_(True)))}
    extra = []
    for k, val in respuestas.items():
        a = attrs.get(k)
        if not a:
            continue
        for x in (val if isinstance(val, list) else [val]):
            o = next((o for o in a.opciones if o.codigo == x), None)
            if o:
                extra.append(f"{o.etiqueta} {o.alias or ''}")
            elif isinstance(x, str) and a.tipo_dato in ("text", "composition"):
                extra.append(x)
    terminos = list(dict.fromkeys(palabras(f"{texto} {' '.join(extra)}")))
    marca = int(v.importado_en.timestamp() if v.importado_en else 0)
    nodos, df = _indice(v.id, marca)
    por_cod = _por_codigo(v.id, marca)
    cands: dict[str, Candidato] = {}
    if "TEXT_CANDIDATES" in base and terminos:
        total = max(len(nodos), 1)
        idf = {t: math.log(1 + total / (1 + df.get(t, 0))) for t in terminos}
        # Palabras del vocabulario que cuenta cada término (exacta, o que empiezan con él si tiene 5+ letras)
        alcance = {t: {t} | ({w for w in df if w.startswith(t)} if len(t) >= 5 else set()) for t in terminos}
        for cod, nivel, _desc, _dai, ps in nodos:
            if cod[:2] not in habilitados:
                continue
            hechos_t = [t for t in terminos if not ps.isdisjoint(alcance[t])]
            if not hechos_t:
                continue
            puntos = sum(idf[t] for t in hechos_t) * peso_dom.get(cod[:2], 1.0)
            c = cands.setdefault(cod[:6], Candidato(cod[:6]))
            c.puntaje = max(c.puntaje, puntos)
            c.terminos.update(hechos_t)
            c.origen.add("texto")

    def agregar(codigo: str, puntos: float, origen: str):
        """Una regla puede traer candidatos que el texto no encontró (subpartidas bajo el código)."""
        subs = sorted({x[:6] for x in por_cod if x.startswith(codigo)}) or ([codigo[:6]] if len(codigo) >= 6 else [])
        for s in subs[:30]:
            if s[:2] not in habilitados:
                continue
            c = cands.setdefault(s, Candidato(s))
            c.puntaje += puntos
            c.origen.add(origen)

    # 2. Reglas: de mayor a menor prioridad
    pendientes: dict[str, set] = {}  # regla → atributos que faltan (discriminantes)
    preguntar: dict[str, int] = {}
    revision_por: list[str] = []
    restringido = False
    for r in reglas:
        a = _accion(r)
        if a["tipo"] == "BUILTIN" or not _aplica_a_producto(r, hechos):
            continue
        res, faltan = evaluar(r.condiciones, hechos)
        codigos = [c for c in (a.get("codigos") or []) if c]
        if r.tipo_ambito in ("CHAPTER", "HEADING", "SUBHEADING") and a["tipo"] in ("ASK", "REVIEW"):
            # Ámbito de código: solo cuenta si hay candidatos bajo ese código
            if not any(c.startswith(r.codigo_ambito) for c in cands):
                continue
        if res is None:
            pendientes[r.codigo] = faltan
            traza.append({"regla": r.codigo, "resultado": None, "efecto": "pending", "faltan": sorted(faltan)})
            continue
        if res is False:
            traza.append({"regla": r.codigo, "resultado": False, "efecto": "no"})
            continue
        efecto = a["tipo"]
        if a.get("por") and isinstance(a.get("mapa"), dict):
            # Subpartida según un hecho (p. ej. la fibra predominante): mapa valor → código
            val = hechos.get(a["por"])
            elegido = a["mapa"].get("" if _vacio(val) else str(val))
            if _vacio(val):
                pendientes.setdefault(r.codigo, set()).add(a["por"])  # ese dato es el que discrimina
            if not elegido:
                traza.append({"regla": r.codigo, "resultado": None, "efecto": "pending", "faltan": [a["por"]]})
                continue
            codigos = [elegido]
        if efecto == "RESTRICT" and codigos:
            for c in codigos:
                agregar(c, float(a.get("peso") or 10), f"regla:{r.codigo}")
            for k in [k for k in cands if not any((len(c) <= 6 and k.startswith(c)) or c.startswith(k) for c in codigos)]:
                del cands[k]
            restringido = True
        elif efecto == "EXCLUDE" and codigos:
            for k in [k for k in cands if any(len(c) <= 6 and k.startswith(c) for c in codigos)]:
                del cands[k]
        elif efecto == "BOOST" and codigos:
            for c in codigos:
                agregar(c, float(a.get("peso") or 5), f"regla:{r.codigo}")
        elif efecto == "ASK":
            for at in a.get("atributos") or []:
                preguntar[at] = max(preguntar.get(at, 0), r.prioridad)
        elif efecto == "REVIEW":
            revision_por.append(a.get("mensaje") or r.efecto or r.codigo)
        traza.append({"regla": r.codigo, "resultado": True, "efecto": efecto, "codigos": codigos, "mensaje": a.get("mensaje")})

    # 3. Ranking y resultado
    lista = sorted(cands.values(), key=lambda c: (-c.puntaje, c.codigo))
    lineas_de: dict[str, list] = {}
    for k in sorted(k for k in por_cod if len(k) > 6 and k[:6] in cands):
        lineas_de.setdefault(k[:6], []).append(k)
    for c in lista:
        c.incisos = [{"codigo": k, "codigo_txt": formato(k), "descripcion": por_cod[k][1].split(" — ")[-1], "dai": por_cod[k][2]}
                     for k in lineas_de.get(c.codigo, [])]
    hs6 = lista[0].codigo if lista else None
    por_regla = bool(lista and any(o.startswith("regla:") for o in lista[0].origen))
    if restringido and len(lista) == 1:
        confianza = "high"
    elif len(lista) == 1 or (len(lista) > 1 and lista[0].puntaje >= 1.5 * lista[1].puntaje):
        confianza = "medium"
    else:
        confianza = "low"
    revision = bool(revision_por)
    if "AMBIGUITY" in base and len(lista) > 1 and lista[1].puntaje >= 0.67 * lista[0].puntaje:
        revision = True
        revision_por.append("Several plausible candidates remain.")
    if "TEXT_CANDIDATES" in base and lista and not por_regla:
        revision = True  # el texto nunca confirma solo

    # 4. Preguntas: ámbitos (con su condición), compuertas y lo que discrimina primero
    codigos = [c.codigo for c in lista]
    discriminan = set().union(*pendientes.values()) if pendientes else set()
    preguntas = _preguntas(attrs, hechos, codigos, preguntar, discriminan if "NEXT_BEST_QUESTION" in base else set())

    # 5. SAC regional y 6. clasificación por país
    sac = None
    if hs6:
        lineas = [k for k in por_cod if k.startswith(hs6) and len(k) > 6]
        sac = lineas[0] if len(lineas) == 1 else None
    out_paises = _paises(db, hs6, sac, hechos, requisitos) if paises and hs6 else []
    nombres = dict(db.execute(select(NodoArancel.codigo_norm, NodoArancel.descripcion).where(
        NodoArancel.version_id == v.id, NodoArancel.codigo_norm.in_(codigos[:limite]))).all()) if codigos else {}
    return {
        "hs6": hs6, "hs6_txt": formato(hs6) if hs6 else None, "sac": sac, "sac_txt": formato(sac) if sac else None,
        "version": v.codigo, "confianza": confianza, "revision": revision, "revision_por": revision_por, "terminos": terminos,
        "candidatos": [{"codigo": c.codigo, "codigo_txt": formato(c.codigo), "descripcion": nombres.get(c.codigo, ""), "capitulo": c.codigo[:2],
                        "titulo_capitulo": caps[c.codigo[:2]].titulo if c.codigo[:2] in caps else "", "puntaje": round(c.puntaje, 2),
                        "terminos": sorted(c.terminos), "origen": sorted(c.origen), "dominio": c.codigo[:2] in peso_dom,
                        "incisos": c.incisos[:6]} for c in lista[:limite]],
        "preguntas": preguntas, "reglas": traza, "paises": out_paises,
    }


def _preguntas(attrs: dict, hechos: dict, codigos: list[str], forzadas: dict, discriminan: set) -> list[dict]:
    from .atributos import _dict as atributo_dict

    caps, partidas, subs = {c[:2] for c in codigos}, {c[:4] for c in codigos}, set(codigos)
    out = []
    for a in attrs.values():
        if a.codigo in ("destination_country",):
            continue
        mejor = None
        for x in a.ambitos:
            if not x.activo or x.modo == "HIDE":
                continue
            toca = ((x.tipo_ambito == "SYSTEM") or (x.tipo_ambito == "DOMAIN" and x.codigo_ambito == hechos.get("dominio"))
                    or (x.tipo_ambito == "CATEGORY" and x.codigo_ambito == hechos.get("categoria"))
                    or (x.tipo_ambito == "CHAPTER" and x.codigo_ambito in caps) or (x.tipo_ambito == "HEADING" and x.codigo_ambito in partidas)
                    or (x.tipo_ambito == "SUBHEADING" and x.codigo_ambito in subs))
            if not toca:
                continue
            res, _ = condicion_ambito(x.condicion, hechos)
            if res is not True:
                continue  # la dependencia no se cumple (o falta su dato): todavía no se pregunta
            extra = {"SUBHEADING": 300, "HEADING": 200, "CHAPTER": 100}.get(x.tipo_ambito, 0)
            clave = (x.modo == "REQUIRE", x.prioridad + extra)
            if not mejor or clave > mejor[0]:
                mejor = (clave, x)
        if a.codigo in forzadas and not mejor:
            mejor = ((True, forzadas[a.codigo]), None)
        if not mejor and a.codigo in discriminan:
            mejor = ((False, 0), None)
        if mejor:
            d = atributo_dict(a, True)
            out.append({**d, "modo": mejor[1].modo if mejor[1] else "REQUIRE", "prioridad": mejor[0][1],
                        "nota_ambito": mejor[1].nota if mejor[1] else None, "discrimina": a.codigo in discriminan,
                        "respondida": not _vacio(hechos.get(a.codigo))})
    return sorted(out, key=lambda d: (d["respondida"], not d["discrimina"], d["modo"] != "REQUIRE", -d["prioridad"], d["orden"]))


def _paises(db: Session, hs6: str, sac: str | None, hechos: dict, requisitos) -> list[dict]:
    """Cada país por separado: se elige una línea nacional existente con las
    reglas de selección (nunca se recorta un código)."""
    out = []
    base = sac or hs6
    for p in db.scalars(select(PaisArancel).where(PaisArancel.activo.is_(True)).order_by(PaisArancel.orden)):
        lineas = list(db.scalars(select(IncisoNacional).options(selectinload(IncisoNacional.regla)).where(
            IncisoNacional.pais == p.iso, IncisoNacional.sub6 == hs6, IncisoNacional.activo.is_(True))))
        lineas = [x for x in lineas if x.codigo.startswith(base)] or lineas
        vivos, pendientes, faltan = [], [], set()
        for x in lineas:
            res, f = evaluar(x.regla.condiciones, hechos) if x.regla else (True, set())
            if res is True:
                vivos.append(x)
            elif res is None:
                pendientes.append(x)
                faltan |= f
        vivos.sort(key=lambda x: (-(x.prio or 0), -len(x.cond or {})))
        mejor = vivos[0] if vivos else None
        empate = mejor and len([x for x in vivos if (x.prio or 0) == (mejor.prio or 0) and len(x.cond or {}) == len(mejor.cond or {})]) > 1
        if mejor and not empate and not (pendientes and len(mejor.cond or {}) == 0):
            estado, codigo = "ok", mejor.codigo
        elif lineas:
            estado, codigo = "elegir", None
        elif sac and len(sac) in p.longitudes_validas():
            estado, codigo = "sac", sac  # el país usa la línea SAC regional tal cual
        else:
            estado, codigo = "pendiente", None
        x = mejor if estado == "ok" else None
        req = requisitos(db, p.iso, codigo or base, x.dai if x else None)
        out.append({"pais": p.iso, "nombre": p.nombre, "estado": estado, "codigo": codigo, "codigo_txt": formato(codigo) if codigo else None,
                    "dai": x.dai if x else None, "inciso_id": x.id if x else None, "regla": x.regla.codigo if x and x.regla else None,
                    "opciones": [{"codigo": y.codigo, "cond": y.cond, "descripcion": y.descripcion} for y in (vivos + pendientes)][:10],
                    "faltan": sorted(faltan), "impuestos": req["impuestos"], "regulaciones": req["regulaciones"]})
    return out
