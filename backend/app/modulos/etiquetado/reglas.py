"""Motor de reglas de etiquetado: qué diseño se usa para cada registro.

Una regla (tabla asignaciones_etiqueta) se cumple para un registro si:

1. está activa, su diseño está activo y es de la modalidad pedida;
2. hoy está dentro de su vigencia;
3. su destino coincide (toda la organización, la familia del artículo o una
   de sus familias superiores, el producto, el artículo, la OC; REGLA no
   tiene destino);
4. su contexto coincide (modalidad, origen, unidad, tipo de empaque);
5. todas sus condiciones se cumplen sobre los valores del registro.

Las condiciones son declarativas ({campo, op, valor}) con operadores de una
lista cerrada: nunca se evalúa código escrito por un usuario.

Entre las reglas que se cumplen y tienen un diseño con versión aprobada gana
la de mayor prioridad. Si en la prioridad más alta hay diseños distintos:
el que eligió el usuario para ese registro; si no, el de la única regla
marcada como predeterminada; si no, es un conflicto y el registro no se
genera hasta resolverlo (nunca se elige un diseño al azar).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import Articulo, AsignacionEtiqueta, FamiliaEtiquetado, OrdenCompra, PlantillaEtiqueta
from app.modelos.etiquetado import MODALIDADES, ORIGENES_TRABAJO, UNIDADES

# Prioridad que toma una regla nueva según su destino (la del más específico, mayor)
PRIORIDAD = {"OC": 500, "ARTICULO": 400, "PRODUCTO": 300, "FAMILIA": 200, "GENERAL": 100, "REGLA": 250}
# Modalidades que admite cada destino: una OC no tiene artículo y un artículo no tiene OC
MODALIDADES_DE = {"GENERAL": set(MODALIDADES), "REGLA": set(MODALIDADES), "FAMILIA": {"ARTICULO", "OC_ARTICULO"},
                  "PRODUCTO": {"ARTICULO", "OC_ARTICULO"}, "ARTICULO": {"ARTICULO", "OC_ARTICULO"},
                  "OC": {"OC", "OC_ARTICULO"}}
DESTINO = {"FAMILIA": "familia_id", "PRODUCTO": "producto_id", "ARTICULO": "articulo_id", "OC": "oc_id"}
OPERADORES = ("existe", "vacio", "igual", "distinto", "en", "no_en", "contiene", "no_contiene", "empieza", "termina",
              "mayor", "mayor_igual", "menor", "menor_igual", "entre", "en_familia", "coincide")
SIN_VALOR = {"existe", "vacio"}
NUMERICOS = {"mayor", "mayor_igual", "menor", "menor_igual", "entre"}
LISTAS = {"en", "no_en"}
CONTEXTO = {"modalidades": MODALIDADES, "origenes": ORIGENES_TRABAJO, "unidades": UNIDADES}
MAX_CONDICIONES = 20
MAX_VALORES = 200
# Patrones («coincide»): cortos, sin construcciones que hacen que el motor de
# expresiones regulares retroceda sin fin (repeticiones anidadas, alternativas
# repetidas, referencias atrás, búsquedas hacia delante o atrás) y contra un
# texto acotado. Así ninguna regla ni condición de un diseño puede dejar el
# servidor calculando (ReDoS).
MAX_PATRON = 100
MAX_TEXTO_PATRON = 200


# ---- Validación de una regla -----------------------------------------------------------------
def validar_condiciones(db: Session, condiciones) -> list[dict]:
    """Las condiciones limpias o 422: campo del catálogo, operador de la lista y
    un valor del tipo que el operador necesita."""
    from app.modulos.etiquetado import campos

    if condiciones in (None, ""):
        return []
    if not isinstance(condiciones, list) or len(condiciones) > MAX_CONDICIONES:
        raise ErrorNegocio(f"Up to {MAX_CONDICIONES} conditions per rule.", 422, "validacion")
    validos = {c.clave for c in campos.catalogo(db)} - {"organizacion.logo"}
    errores, limpio = [], []
    for i, c in enumerate(condiciones):
        donde = f"condiciones.{i}"
        if not isinstance(c, dict):
            errores.append({"campo": donde, "mensaje": "Each condition needs a field, an operator and a value."})
            continue
        campo, op, valor = c.get("campo"), c.get("op"), c.get("valor")
        if campo not in validos:
            errores.append({"campo": donde, "mensaje": f"Unknown field: {campo}."})
            continue
        if op not in OPERADORES:
            errores.append({"campo": donde, "mensaje": f"Unknown operator: {op}."})
            continue
        if op in SIN_VALOR:
            valor = None
        elif op in LISTAS:
            if isinstance(valor, str):
                valor = [x.strip() for x in valor.split(",") if x.strip()]
            if not isinstance(valor, list) or not valor or len(valor) > MAX_VALORES:
                errores.append({"campo": donde, "mensaje": f"Write between 1 and {MAX_VALORES} values."})
                continue
            valor = [str(x)[:100] for x in valor]
        elif op == "entre":
            if not isinstance(valor, list) or len(valor) != 2 or not all(_numero(x) is not None for x in valor):
                errores.append({"campo": donde, "mensaje": "Write the two numbers of the range."})
                continue
            valor = sorted(_numero(x) for x in valor)
        elif op in NUMERICOS:
            if _numero(valor) is None:
                errores.append({"campo": donde, "mensaje": "Write a number."})
                continue
            valor = _numero(valor)
        else:
            if valor in (None, "") or isinstance(valor, (list, dict)):
                errores.append({"campo": donde, "mensaje": "Write the value to compare."})
                continue
            valor = str(valor)[:200]
            if op == "coincide":
                motivo = validar_patron(valor)
                if motivo:
                    errores.append({"campo": donde, "mensaje": motivo})
                    continue
            if op == "en_familia" and not db.scalar(select(FamiliaEtiquetado.id).where(FamiliaEtiquetado.codigo == valor.upper())):
                errores.append({"campo": donde, "mensaje": f"There is no labeling family {valor}."})
                continue
        limpio.append({"campo": campo, "op": op, "valor": valor})
    if errores:
        raise ErrorNegocio("Check the rule conditions.", 422, "validacion", errores)
    return limpio


def validar_patron(patron: str) -> str | None:
    """Por qué el patrón no se acepta (o None si es seguro)."""
    try:
        from re import _constants as k
        from re import _parser as analizador
    except ImportError:  # Python < 3.11
        import sre_constants as k
        import sre_parse as analizador
    if len(patron) > MAX_PATRON:
        return f"The pattern is too long (at most {MAX_PATRON} characters)."
    try:
        arbol = analizador.parse(patron)
    except (re.error, RecursionError, OverflowError):
        return "The pattern is not valid."
    prohibidos = {k.GROUPREF, k.GROUPREF_EXISTS, k.ASSERT, k.ASSERT_NOT}
    repeticiones = {k.MAX_REPEAT, k.MIN_REPEAT, getattr(k, "POSSESSIVE_REPEAT", k.MAX_REPEAT)}

    def hijos(op, av):
        if op in repeticiones:
            return [av[2]]
        if op == k.SUBPATTERN:
            return [av[-1]]
        if op == k.BRANCH:
            return list(av[1])
        if op == getattr(k, "ATOMIC_GROUP", None):
            return [av]
        return []

    def revisar(sub, dentro_de_repeticion: bool) -> str | None:
        for op, av in sub:
            if op in prohibidos:
                return "The pattern cannot use back-references or look-ahead/look-behind."
            if op in repeticiones and dentro_de_repeticion:
                return "The pattern cannot repeat a group that already repeats, like (a+)+: use a single repetition."
            if op == k.BRANCH and dentro_de_repeticion:
                return "The pattern cannot repeat alternatives, like (a|b)+: use a character class, like [ab]+."
            repite = op in repeticiones and av[1] > 1
            for h in hijos(op, av):
                motivo = revisar(h, dentro_de_repeticion or repite)
                if motivo:
                    return motivo
        return None

    return revisar(arbol, False)


def _patron_cumple(patron: str, texto: str) -> bool:
    """«coincide» acotado: un patrón inseguro guardado antes de esta validación
    no se evalúa, y el texto se mira solo hasta MAX_TEXTO_PATRON caracteres."""
    if len(texto) > MAX_TEXTO_PATRON or validar_patron(patron):
        return False
    try:
        return re.fullmatch(patron, texto, flags=re.IGNORECASE) is not None
    except re.error:
        return False


def validar_contexto(contexto) -> dict:
    if contexto in (None, ""):
        return {}
    if not isinstance(contexto, dict):
        raise ErrorNegocio("Check the rule context.", 422, "validacion")
    limpio = {}
    for k, v in contexto.items():
        if k == "tipos_empaque":
            if not isinstance(v, list) or len(v) > MAX_VALORES:
                raise ErrorNegocio("Check the package types of the rule.", 422, "validacion")
            if v:
                limpio[k] = sorted({str(x).strip().upper()[:20] for x in v if str(x).strip()})
            continue
        if k not in CONTEXTO:
            raise ErrorNegocio(f"Unknown context: {k}.", 422, "validacion")
        if not isinstance(v, list) or any(x not in CONTEXTO[k] for x in v):
            raise ErrorNegocio(f"Unknown values in the context {k}.", 422, "validacion")
        if v:
            limpio[k] = sorted(set(v))
    return limpio


# ---- Evaluación ----------------------------------------------------------------------------
def _numero(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _vacio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v)


def _texto(v) -> str:
    return "" if v is None else str(v).strip().lower()


def cumple_condicion(c: dict, valores: dict) -> bool:
    v = valores.get(c["campo"])
    op, esperado = c["op"], c.get("valor")
    if op == "existe":
        return not _vacio(v)
    if op == "vacio":
        return _vacio(v)
    if op in NUMERICOS:
        n = _numero(v)
        if n is None:
            return False
        if op == "entre":
            return esperado[0] <= n <= esperado[1]
        return {"mayor": n > esperado, "mayor_igual": n >= esperado, "menor": n < esperado, "menor_igual": n <= esperado}[op]
    if op == "en_familia":
        return _texto(esperado) in [x.strip().lower() for x in str(v or "").split("/")]
    if isinstance(v, list):  # una colección: contiene / en sobre sus valores
        textos = {_texto(x) for x in v}
        if op in ("contiene", "igual"):
            return _texto(esperado) in textos
        if op in ("no_contiene", "distinto"):
            return _texto(esperado) not in textos
        if op == "en":
            return bool(textos & {_texto(x) for x in esperado})
        if op == "no_en":
            return not textos & {_texto(x) for x in esperado}
        return False
    s = _texto(v)
    if op == "igual":
        n, m = _numero(v), _numero(esperado)
        return (n == m) if n is not None and m is not None else s == _texto(esperado)
    if op == "distinto":
        return not cumple_condicion({**c, "op": "igual"}, valores)
    if op == "en":
        return s in {_texto(x) for x in esperado}
    if op == "no_en":
        return s not in {_texto(x) for x in esperado}
    if op == "contiene":
        return _texto(esperado) in s
    if op == "no_contiene":
        return _texto(esperado) not in s
    if op == "empieza":
        return s.startswith(_texto(esperado))
    if op == "termina":
        return s.endswith(_texto(esperado))
    if op == "coincide":
        return _patron_cumple(str(esperado), "" if v is None else str(v))
    return False


@dataclass
class Registro:
    """Lo que el motor sabe de un registro: su artículo, su OC, sus valores y
    el contexto del trabajo (modalidad, origen, unidad, tipo de empaque)."""
    modalidad: str
    articulo: Articulo | None = None
    oc: OrdenCompra | None = None
    valores: dict = field(default_factory=dict)
    origen: str | None = None
    unidad: str | None = None
    tipo_empaque: str | None = None


@dataclass
class Evaluacion:
    regla: AsignacionEtiqueta
    resultado: str  # aplica | inactiva | otra_modalidad | fuera_de_vigencia | destino_distinto | contexto_distinto | condiciones
    detalle: list = field(default_factory=list)  # una entrada por condición: {campo, op, valor, real, cumple}

    @property
    def aplica(self) -> bool:
        return self.resultado == "aplica"


def _familias(articulo: Articulo | None) -> set[int]:
    f = articulo.familia_efectiva if articulo is not None else None
    return {x.id for x in f.ruta()} if f else set()


def evaluar(r: AsignacionEtiqueta, reg: Registro, hoy: date) -> Evaluacion:
    p = r.plantilla
    if not r.activa or p is None or p.estado != "ACTIVA":
        return Evaluacion(r, "inactiva")
    if p.modalidad != reg.modalidad or reg.modalidad not in MODALIDADES_DE.get(r.ambito, set()):
        return Evaluacion(r, "otra_modalidad")
    if (r.vigente_desde and hoy < r.vigente_desde) or (r.vigente_hasta and hoy > r.vigente_hasta):
        return Evaluacion(r, "fuera_de_vigencia")
    a, oc = reg.articulo, reg.oc
    destino = {"GENERAL": True, "REGLA": True,
               "FAMILIA": r.familia_id in _familias(a),
               "PRODUCTO": a is not None and a.producto_id is not None and a.producto_id == r.producto_id,
               "ARTICULO": a is not None and a.id == r.articulo_id,
               "OC": oc is not None and oc.id == r.oc_id}[r.ambito]
    if not destino:
        return Evaluacion(r, "destino_distinto")
    ctx = r.contexto or {}
    actual = {"modalidades": reg.modalidad, "origenes": reg.origen, "unidades": reg.unidad,
              "tipos_empaque": (reg.tipo_empaque or "").upper() or None}
    for k, permitidos in ctx.items():
        if permitidos and actual.get(k) not in permitidos:
            return Evaluacion(r, "contexto_distinto", [{"contexto": k, "real": actual.get(k), "valor": permitidos, "cumple": False}])
    detalle = []
    for c in r.condiciones or []:
        detalle.append({"campo": c["campo"], "op": c["op"], "valor": c.get("valor"), "real": _resumen(reg.valores.get(c["campo"])),
                        "cumple": cumple_condicion(c, reg.valores)})
    return Evaluacion(r, "aplica" if all(d["cumple"] for d in detalle) else "condiciones", detalle)


def _resumen(v):
    """El valor real de una condición, corto (una colección se muestra por su tamaño)."""
    if isinstance(v, list):
        return f"[{len(v)}]"
    return v


@dataclass
class Eleccion:
    plantilla: PlantillaEtiqueta | None = None
    nivel: str | None = None  # destino de la regla elegida (GENERAL, FAMILIA, …, REGLA) o ELEGIDA
    motivo: str | None = None
    regla: AsignacionEtiqueta | None = None
    candidatas: list[PlantillaEtiqueta] = field(default_factory=list)  # conflicto: hay que elegir
    sin_aprobar: list[PlantillaEtiqueta] = field(default_factory=list)  # se cumplen pero sin versión aprobada
    avisos: list[str] = field(default_factory=list)
    evaluaciones: list[Evaluacion] = field(default_factory=list)
    conflicto: list[AsignacionEtiqueta] = field(default_factory=list)  # las reglas empatadas

    @property
    def ambigua(self) -> bool:
        return self.plantilla is None and len(self.candidatas) > 1

    def dict(self, explicar: bool = False) -> dict:
        p = self.plantilla
        r = self.regla
        res = {"plantilla_id": p.id if p else None, "plantilla": p.nombre if p else None,
               "familia": p.familia.nombre if p and p.familia else None,
               "version_id": p.version_vigente_id if p else None, "version": p.vigente.numero if p and p.vigente else None,
               "nivel": self.nivel, "motivo": self.motivo, "ambigua": self.ambigua,
               "regla_id": r.id if r else None, "regla": regla_nombre(r) if r else None, "prioridad": r.prioridad if r else None,
               "candidatas": [{"plantilla_id": c.id, "plantilla": c.nombre, "version": c.vigente.numero if c.vigente else None}
                              for c in self.candidatas],
               "conflicto": [{"regla_id": x.id, "regla": regla_nombre(x), "prioridad": x.prioridad,
                              "plantilla_id": x.plantilla_id, "plantilla": x.plantilla.nombre} for x in self.conflicto],
               "sin_aprobar": [{"plantilla_id": c.id, "plantilla": c.nombre} for c in self.sin_aprobar],
               "avisos": self.avisos}
        if explicar:
            res["explicacion"] = [{"regla_id": e.regla.id, "regla": regla_nombre(e.regla), "ambito": e.regla.ambito,
                                   "prioridad": e.regla.prioridad, "plantilla_id": e.regla.plantilla_id,
                                   "plantilla": e.regla.plantilla.nombre if e.regla.plantilla else None,
                                   "predeterminada": e.regla.predeterminada, "resultado": e.resultado,
                                   "elegida": bool(self.regla is not None and e.regla is self.regla),
                                   "aprobada": bool(e.regla.plantilla and e.regla.plantilla.version_vigente_id),
                                   "detalle": e.detalle}
                                  for e in sorted(self.evaluaciones, key=lambda x: (-x.regla.prioridad, x.regla.id or 0))]
        return res


def regla_nombre(r: AsignacionEtiqueta) -> str:
    return r.nombre or f"{r.ambito.capitalize()} · {r.plantilla.nombre if r.plantilla else ''}"


class Motor:
    """Las reglas de una modalidad cargadas una vez para resolver muchos registros."""

    def __init__(self, db: Session, modalidad: str, hoy: date | None = None, extra: list[AsignacionEtiqueta] | None = None):
        self.db = db
        self.modalidad = modalidad
        self.hoy = hoy or date.today()
        self.reglas = list(db.scalars(
            select(AsignacionEtiqueta).join(PlantillaEtiqueta).where(PlantillaEtiqueta.modalidad == modalidad)
            .options(selectinload(AsignacionEtiqueta.plantilla)).order_by(AsignacionEtiqueta.prioridad.desc(), AsignacionEtiqueta.id)))
        self.reglas += extra or []

    def resolver(self, reg: Registro, elegida_id: int | None = None) -> Eleccion:
        res = Eleccion()
        res.evaluaciones = [evaluar(r, reg, self.hoy) for r in self.reglas]
        cumplen = [e.regla for e in res.evaluaciones if e.aplica]
        res.sin_aprobar = list({r.plantilla_id: r.plantilla for r in cumplen if not r.plantilla.version_vigente_id}.values())
        aprobadas = [r for r in cumplen if r.plantilla.version_vigente_id]
        if aprobadas:
            tope = max(r.prioridad for r in aprobadas)
            empate = [r for r in aprobadas if r.prioridad == tope]
            distintas = {r.plantilla_id for r in empate}
            if elegida_id and elegida_id in distintas and len(distintas) > 1:
                res.regla = next(r for r in empate if r.plantilla_id == elegida_id)
                res.plantilla, res.nivel = res.regla.plantilla, res.regla.ambito
                res.motivo = "Chosen by the user among the designs of the same priority."
            elif len(distintas) == 1:
                res.regla = empate[0]
                res.plantilla, res.nivel = res.regla.plantilla, res.regla.ambito
                res.motivo = _motivo(res.regla, reg, False)
            else:
                pred = [r for r in empate if r.predeterminada]
                if len({r.plantilla_id for r in pred}) == 1:
                    res.regla = pred[0]
                    res.plantilla, res.nivel = res.regla.plantilla, res.regla.ambito
                    res.motivo = _motivo(res.regla, reg, True)
                else:
                    res.conflicto = empate
                    res.candidatas = list({r.plantilla_id: r.plantilla for r in empate}.values())
                    res.nivel = empate[0].ambito
                    res.motivo = "Several designs apply with the same priority: choose one."
        a = reg.articulo
        familia = a.familia_efectiva if a is not None else None
        if res.plantilla and familia and res.plantilla.familia_id and res.plantilla.familia_id not in _familias(a):
            res.avisos.append("The design was made for another labeling family.")
        if a is not None and familia is None:
            res.avisos.append("The item has no labeling family.")
        return res


def _motivo(r: AsignacionEtiqueta, reg: Registro, por_predeterminada: bool) -> str:
    """Por qué se eligió el diseño, en frases completas (cada una con su traducción)."""
    d = por_predeterminada
    if r.ambito == "REGLA" or r.condiciones or r.contexto:
        nombre = regla_nombre(r)
        return (f"Rule «{nombre}» (priority {r.prioridad}), default among several." if d
                else f"Rule «{nombre}» (priority {r.prioridad}).")
    a, oc = reg.articulo, reg.oc
    if r.ambito == "OC":
        return f"Exception assigned to PO {oc.numero}, default among several." if d else f"Exception assigned to PO {oc.numero}."
    if r.ambito == "ARTICULO":
        return f"Assigned to the item {a.sku}, default among several." if d else f"Assigned to the item {a.sku}."
    if r.ambito == "PRODUCTO":
        return (f"Assigned to the product {a.estilo} (all its variants), default among several." if d
                else f"Assigned to the product {a.estilo} (all its variants).")
    if r.ambito == "FAMILIA":
        ruta = a.familia_efectiva.ruta() if a is not None and a.familia_efectiva else []
        nombre = next((f.nombre for f in ruta if f.id == r.familia_id), "")
        return f"Design of the labeling family {nombre}, default among several." if d else f"Design of the labeling family {nombre}."
    return "General design of the organization, default among several." if d else "General design of the organization."


def resolver(db: Session, modalidad: str, articulo: Articulo | None = None, oc: OrdenCompra | None = None,
             elegida_id: int | None = None, valores: dict | None = None, **contexto) -> Eleccion:
    """Una sola resolución (para muchas, usar Motor)."""
    return Motor(db, modalidad).resolver(Registro(modalidad, articulo, oc, valores or {}, **contexto), elegida_id)


# ---- Conflictos de configuración ----------------------------------------------------------------
def _disjuntas_condiciones(a: list, b: list) -> bool:
    """True si es seguro que las condiciones no se cumplen a la vez (igual/en sobre el mismo campo sin valores comunes)."""
    def conjunto(c):
        if c["op"] == "igual":
            return {_texto(c["valor"])}
        if c["op"] == "en":
            return {_texto(x) for x in c["valor"]}
        return None
    for ca in a:
        for cb in b:
            if ca["campo"] == cb["campo"]:
                x, y = conjunto(ca), conjunto(cb)
                if x is not None and y is not None and not x & y:
                    return True
                if {ca["op"], cb["op"]} == {"existe", "vacio"}:
                    return True
    return False


def _disjuntos_destinos(db: Session, a: AsignacionEtiqueta, b: AsignacionEtiqueta) -> bool:
    if a.ambito in ("GENERAL", "REGLA") or b.ambito in ("GENERAL", "REGLA"):
        return False
    if a.ambito == b.ambito:
        if a.ambito == "FAMILIA":
            fa, fb = db.get(FamiliaEtiquetado, a.familia_id), db.get(FamiliaEtiquetado, b.familia_id)
            return fa not in fb.ruta() and fb not in fa.ruta()
        return getattr(a, DESTINO[a.ambito]) != getattr(b, DESTINO[b.ambito])
    tipos = {a.ambito, b.ambito}
    if tipos == {"ARTICULO", "PRODUCTO"}:
        art = a if a.ambito == "ARTICULO" else b
        prod = b if art is a else a
        x = db.get(Articulo, art.articulo_id)
        return x is None or x.producto_id != prod.producto_id
    if tipos == {"ARTICULO", "FAMILIA"}:
        art = a if a.ambito == "ARTICULO" else b
        fam = b if art is a else a
        x = db.get(Articulo, art.articulo_id)
        return x is None or fam.familia_id not in _familias(x)
    return False  # OC con artículo, producto o familia: una OC puede tenerlos


def _disjuntas_vigencias(a: AsignacionEtiqueta, b: AsignacionEtiqueta) -> bool:
    return bool((a.vigente_hasta and b.vigente_desde and a.vigente_hasta < b.vigente_desde)
                or (b.vigente_hasta and a.vigente_desde and b.vigente_hasta < a.vigente_desde))


def _disjuntos_contextos(a: dict, b: dict) -> bool:
    return any(k in b and a[k] and b[k] and not set(a[k]) & set(b[k]) for k in a)


def conflictos(db: Session, solo: AsignacionEtiqueta | None = None) -> list[dict]:
    """Pares de reglas activas de la misma modalidad y prioridad, con diseños
    distintos, que pueden cumplirse para el mismo registro. Si una sola es la
    predeterminada, el empate se resuelve (aviso); si no, es un conflicto."""
    reglas = list(db.scalars(select(AsignacionEtiqueta).join(PlantillaEtiqueta).where(
        AsignacionEtiqueta.activa.is_(True), PlantillaEtiqueta.estado == "ACTIVA")
        .options(selectinload(AsignacionEtiqueta.plantilla)).order_by(AsignacionEtiqueta.id)))
    res = []
    for i, a in enumerate(reglas):
        for b in reglas[i + 1:]:
            if solo is not None and solo.id not in (a.id, b.id):
                continue
            if a.plantilla_id == b.plantilla_id or a.prioridad != b.prioridad or a.plantilla.modalidad != b.plantilla.modalidad:
                continue
            if (_disjuntas_vigencias(a, b) or _disjuntos_contextos(a.contexto or {}, b.contexto or {})
                    or _disjuntas_condiciones(a.condiciones or [], b.condiciones or []) or _disjuntos_destinos(db, a, b)):
                continue
            resuelto = a.predeterminada != b.predeterminada
            res.append({"nivel": "advertencia" if resuelto else "error", "modalidad": a.plantilla.modalidad,
                        "prioridad": a.prioridad,
                        "reglas": [{"id": x.id, "nombre": regla_nombre(x), "plantilla": x.plantilla.nombre,
                                    "predeterminada": x.predeterminada} for x in (a, b)],
                        "mensaje": ("Same priority and they can apply to the same record: the default one wins."
                                    if resuelto else
                                    "Same priority and they can apply to the same record with different designs: "
                                    "change a priority, a condition or mark one as default.")})
    return res
