"""Validación de la configuración del motor (atributos, opciones, ámbitos,
categorías y reglas) antes de guardarla, venga de la pantalla o de un paquete.

Una configuración inválida nunca llega al motor: un patrón que no compila, una
condición sobre un campo que no existe, una derivación desde una parte de la
composición que no está, una implicación a una opción que no existe… se
rechazan con un mensaje que dice qué y dónde. Así una familia nueva se arma
solo con configuración y sin errores escondidos.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import AtributoDef, CategoriaProducto, DominioClasificacion
from .common import ErrorNegocio

OPERADORES = ("EQUAL", "NOT_EQUAL", "IN", "GT", "GTE", "LT", "LTE", "BETWEEN", "EXISTS")
SECCIONES = ("producto", "caracteristicas", "composicion", "nacional", "derivado")
MODOS_DERIVACION = ("constante", "valor", "fibra", "material", "clase")
LECTURAS = ("superficie", "contacto")
# Dónde busca un patrón de detección (además de comp.<parte>)
FUENTES_TEXTO = ("estilo", "todo", "tallas", "uso", "uso_comp")
# Campos del producto (no de la ficha) que una condición puede leer
CAMPOS_PRODUCTO = ("categoria", "dominio", "origen", "product_name")
CLAVES_PATRON = {"re", "en", "prioridad", "cuando", "y", "y_en", "no", "defecto", "nombre"}
CLAVES_TEXTO = {"frase", "nombre", "comercial", "orden", "cuando"}
CLAVES_PLANTILLA = {"nombre", "comercial", "material", "si", "clase", "requiere", "como", "si_falta"}


def error(msg: str):
    raise ErrorNegocio(msg, 422, "configuracion_invalida")


class Contexto:
    """Lo que existe en la configuración, para validar referencias."""

    def __init__(self, db: Session):
        self.db = db
        self.attrs = {a.codigo: a for a in db.scalars(select(AtributoDef))}
        self.canon = dict((x, a.codigo) for a in self.attrs.values() for x in (a.alias or []))
        self.canon.update({k: k for k in self.attrs})

    def atributo(self, codigo: str, donde: str) -> AtributoDef:
        real = self.canon.get(str(codigo or "").strip())
        if not real:
            error(f"{donde}: {codigo} is not an attribute.")
        return self.attrs[real]

    def campo(self, campo: str, donde: str) -> str:
        campo = str(campo or "").strip()
        if campo in CAMPOS_PRODUCTO:
            return campo
        return self.atributo(campo, donde).codigo

    def partes(self) -> set[str]:
        return {k[5:] for k in self.attrs if k.startswith("comp.")}


def condiciones(ctx: Contexto, conds, donde: str) -> list | None:
    """Condiciones {campo, operador, valor, valor_hasta, negado, grupo}: dentro
    de un grupo todas; entre grupos basta una. Cada campo debe existir y cada
    valor de una lista de selección debe ser una de sus opciones."""
    if not conds:
        return None
    if not isinstance(conds, list):
        error(f"{donde}: the conditions must be a list.")
    out = []
    for c in conds:
        if not isinstance(c, dict):
            error(f"{donde}: each condition is {{field, operator, value}}.")
        op = str(c.get("operador") or "EQUAL").upper()
        if op not in OPERADORES:
            error(f"{donde}: operator {op} is not valid ({', '.join(OPERADORES)}).")
        campo = ctx.campo(c.get("campo"), donde)
        valor = c.get("valor")
        if op == "IN" and not isinstance(valor, list):
            error(f"{donde}: «one of» needs a list of values.")
        if op in ("GT", "GTE", "LT", "LTE", "BETWEEN"):
            for v in (valor, c.get("valor_hasta")) if op == "BETWEEN" else (valor,):
                try:
                    float(v)
                except (TypeError, ValueError):
                    error(f"{donde}: {campo} {op} needs a number.")
        a = ctx.attrs.get(campo)
        validas = {o.codigo for o in a.opciones} if a is not None and a.tipo_dato in ("select", "multi_select") else set()
        if validas and op in ("EQUAL", "NOT_EQUAL", "IN"):
            for v in valor if isinstance(valor, list) else [valor]:
                if v not in ("", None) and str(v) not in validas:
                    error(f"{donde}: {v} is not an option of {campo} ({', '.join(sorted(validas)[:12])}).")
        out.append({"grupo": int(c.get("grupo") or 1), "campo": campo, "operador": op, "valor": valor,
                    "valor_hasta": c.get("valor_hasta"), "negado": bool(c.get("negado"))})
    return out


def _regex(r, donde: str) -> str:
    if not isinstance(r, str) or not r.strip():
        error(f"{donde}: the pattern is empty.")
    try:
        re.compile(r, re.ASCII)
    except re.error as e:
        error(f"{donde}: the pattern {r!r} is not valid ({e}).")
    return r


def patrones(ctx: Contexto, lista, donde: str) -> list:
    """Patrones de detección: {re, en, prioridad, cuando, y, y_en, no, defecto, nombre}."""
    if not lista:
        return []
    if not isinstance(lista, list):
        error(f"{donde}: the patterns must be a list.")
    partes = ctx.partes()
    out = []
    for i, p in enumerate(lista, start=1):
        d = f"{donde}, pattern {i}"
        if not isinstance(p, dict):
            error(f"{d}: each pattern is an object.")
        extra = set(p) - CLAVES_PATRON
        if extra:
            error(f"{d}: unknown keys {', '.join(sorted(extra))}.")
        if not p.get("defecto") and not p.get("re") and not p.get("cuando"):
            error(f"{d}: give a pattern (re), a condition (cuando) or mark it as the default.")
        if p.get("re"):
            _regex(p["re"], d)
        for k in ("en", "y_en"):
            if p.get(k) and p[k] not in FUENTES_TEXTO and not (p[k].startswith("comp.") and p[k][5:] in partes):
                error(f"{d}: «{k}» must be one of {', '.join(FUENTES_TEXTO)} or a composition part (comp.<part>).")
        for k in ("y", "no"):
            if p.get(k) is not None:
                if not isinstance(p[k], list):
                    error(f"{d}: «{k}» is a list of patterns.")
                for r in p[k]:
                    _regex(r, d)
        if p.get("prioridad") is not None and not isinstance(p["prioridad"], int):
            error(f"{d}: the priority is a whole number.")
        q = dict(p)
        if p.get("cuando"):
            q["cuando"] = condiciones(ctx, p["cuando"], d)
        out.append(q)
    return out


def textos_aduana(ctx: Contexto, t, donde: str):
    """Texto de la descripción aduanera: {frase, nombre, comercial, orden, cuando}
    o una lista de alternativas (va la primera cuya condición se cumple)."""
    if t in (None, {}, []):
        return None
    lista = t if isinstance(t, list) else [t]
    out = []
    for i, x in enumerate(lista, start=1):
        d = f"{donde}, customs text {i}"
        if not isinstance(x, dict):
            error(f"{d}: each text is an object.")
        extra = set(x) - CLAVES_TEXTO
        if extra:
            error(f"{d}: unknown keys {', '.join(sorted(extra))}.")
        if not any(str(x.get(k) or "").strip() for k in ("frase", "nombre", "comercial")):
            error(f"{d}: give a phrase, a name or a commercial name.")
        if any(len(str(x.get(k) or "")) > 200 for k in ("frase", "nombre", "comercial")):
            error(f"{d}: a text has at most 200 characters.")
        q = {k: v for k, v in x.items() if v not in (None, "")}
        if "orden" in q and not isinstance(q["orden"], int):
            error(f"{d}: the order is a whole number.")
        if x.get("cuando"):
            q["cuando"] = condiciones(ctx, x["cuando"], d)
        out.append(q)
    return out if isinstance(t, list) else out[0]


def _opcion_valida(a: AtributoDef, v, donde: str):
    if a.tipo_dato == "boolean":
        if not isinstance(v, bool):
            error(f"{donde}: {a.codigo} is yes/no (true or false).")
    elif a.tipo_dato in ("select", "multi_select"):
        if str(v) not in {o.codigo for o in a.opciones}:
            error(f"{donde}: {v} is not an option of {a.codigo}.")


def derivacion(ctx: Contexto, a: AtributoDef, d, donde: str) -> dict | None:
    """El valor que fijan los datos: constante, el valor de otro atributo
    (con un mapa) o lo que se lee de una parte de la composición (fibra,
    material o clase de material, con un mapa a las opciones)."""
    if not d:
        return None
    if not isinstance(d, dict):
        error(f"{donde}: the derivation is an object.")
    modo = d.get("modo")
    if modo not in MODOS_DERIVACION:
        error(f"{donde}: the derivation mode must be one of {', '.join(MODOS_DERIVACION)}.")
    q = dict(d)
    if modo == "constante":
        if "valor" not in d:
            error(f"{donde}: a constant derivation needs its value.")
        _opcion_valida(a, d["valor"], donde)
    elif modo == "valor":
        origen = ctx.atributo(d.get("desde"), f"{donde} (from)")
        if origen.codigo == a.codigo:
            error(f"{donde}: an attribute cannot be derived from itself.")
        q["desde"] = origen.codigo
        if not isinstance(d.get("mapa"), dict) or not d["mapa"]:
            error(f"{donde}: a derivation from another attribute needs a map (its value → this value).")
    else:
        parte = str(d.get("parte") or "")
        if parte not in ctx.partes():
            error(f"{donde}: {parte or '(empty)'} is not a composition part (comp.<part>).")
        if d.get("lectura") and d["lectura"] not in LECTURAS:
            error(f"{donde}: the reading must be {' or '.join(LECTURAS)}.")
        if d.get("mapa") is not None and not isinstance(d["mapa"], dict):
            error(f"{donde}: the map is an object (material → option).")
    if isinstance(d.get("mapa"), dict) and a.tipo_dato in ("select", "boolean"):
        for v in d["mapa"].values():
            _opcion_valida(a, v, f"{donde} (map)")
    if d.get("cuando"):
        q["cuando"] = condiciones(ctx, d["cuando"], f"{donde} (when)")
    return q


def bloqueos(ctx: Contexto, lista, donde: str) -> list:
    """Combinaciones imposibles: [{condiciones, mensaje}]."""
    if not lista:
        return []
    if not isinstance(lista, list):
        error(f"{donde}: the blocks must be a list.")
    out = []
    for i, b in enumerate(lista, start=1):
        d = f"{donde}, block {i}"
        if not isinstance(b, dict) or not b.get("condiciones"):
            error(f"{d}: a block needs the conditions that make it impossible.")
        if not str(b.get("mensaje") or "").strip():
            error(f"{d}: say why it is not possible (message).")
        out.append({"condiciones": condiciones(ctx, b["condiciones"], d), "mensaje": str(b["mensaje"]).strip()[:300]})
    return out


def implica(ctx: Contexto, a: AtributoDef, imp, donde: str) -> dict | None:
    """Lo que elegir una opción completa: {atributo: valor}."""
    if not imp:
        return None
    if not isinstance(imp, dict):
        error(f"{donde}: «implies» is an object (attribute → value).")
    out = {}
    for k, v in imp.items():
        b = ctx.atributo(k, donde)
        if b.codigo == a.codigo:
            error(f"{donde}: an option cannot imply its own attribute.")
        _opcion_valida(b, v, donde)
        out[b.codigo] = v
    return out


def alias(ctx: Contexto, a: AtributoDef, lista, donde: str) -> list | None:
    if not lista:
        return None
    if not isinstance(lista, list):
        error(f"{donde}: the aliases are a list of codes.")
    out = []
    for x in lista:
        x = str(x or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", x):
            error(f"{donde}: {x or '(empty)'} is not a valid code.")
        if x in ctx.attrs and x != a.codigo:
            error(f"{donde}: {x} is already an attribute.")
        if ctx.canon.get(x, a.codigo) != a.codigo:
            error(f"{donde}: {x} is already an alias of {ctx.canon[x]}.")
        if x != a.codigo and x not in out:
            out.append(x)
    return out or None


def ambito(db: Session, tipo: str, cod: str) -> str:
    """El código de un ámbito validado: la categoría o el dominio existen; un
    capítulo, partida o subpartida tienen sus dígitos."""
    cod = str(cod or "").strip()
    if tipo == "SYSTEM":
        return "ALL"
    if tipo == "CATEGORY":
        real = db.scalar(select(CategoriaProducto.codigo).where(func.lower(CategoriaProducto.codigo) == cod.lower()))
        if not real:
            error(f"Category {cod or '(empty)'} does not exist.")
        return real
    if tipo == "DOMAIN":
        cod = cod.upper()
        if not db.scalar(select(DominioClasificacion.id).where(DominioClasificacion.codigo == cod)):
            error(f"Domain {cod or '(empty)'} does not exist.")
        return cod
    largos = {"CHAPTER": 2, "HEADING": 4, "SUBHEADING": 6}
    if tipo in largos:
        dig = "".join(ch for ch in cod if ch.isdigit())
        if len(dig) != largos[tipo]:
            error(f"The scope code must have {largos[tipo]} digits.")
        return dig
    return cod


def plantilla(ctx: Contexto, p, donde: str) -> dict | None:
    """Plantilla de la descripción aduanera de una categoría: nombre, comercial,
    material (con {atributo} o {clase}), alternativas «si», partes «clase»,
    «requiere», «como» (valor → palabra) y «si_falta»."""
    if not p:
        return None
    if not isinstance(p, dict):
        error(f"{donde}: the customs template is an object.")
    extra = set(p) - CLAVES_PLANTILLA
    if extra:
        error(f"{donde}: unknown keys {', '.join(sorted(extra))}.")
    for k in re.findall(r"\{(\w+)\}", str(p.get("material") or "")):
        if k != "clase":
            ctx.atributo(k, f"{donde} (material)")
    for parte in p.get("clase") or []:
        if parte not in ctx.partes():
            error(f"{donde}: {parte} is not a composition part.")
    for k in p.get("requiere") or []:
        ctx.atributo(k, f"{donde} (requires)")
    for k in p.get("como") or {}:
        ctx.atributo(k, f"{donde} (as)")
    q = dict(p)
    if p.get("si"):
        q["si"] = [{**x, "cuando": condiciones(ctx, x.get("cuando"), f"{donde} (if)")} for x in p["si"]]
    return q
