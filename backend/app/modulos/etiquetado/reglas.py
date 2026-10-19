"""Qué diseño lleva cada registro (tabla usos_diseno).

La regla, tal como se le explica al usuario: manda lo más cercano al
artículo; dentro de eso, si una excepción coincide se usa la excepción; lo
que se pidió para una OC concreta manda sobre todo.

Para un registro y un tipo de etiqueta:

1. Excepción de la OC: si el registro viene de una OC y hay un uso para esa
   OC (en el nivel más específico que tenga uno), gana.
2. Si no, se recorren los niveles de lo más específico a lo más general
   (artículo: SKU, producto, familia y sus familias superiores, grupo, toda
   la empresa; bulto: tipo de empaque, toda la empresa; documento: toda la
   empresa). En la primera celda que tenga algo aplicable: la excepción que
   coincida (centro destino, país destino, sociedad, proveedor, condición, en
   ese orden); si ninguna, su diseño normal; si la celda solo tiene
   excepciones y ninguna coincide, se sigue al nivel siguiente.
3. Si nada aplica, el registro queda sin diseño de ese tipo.

No hay prioridades numéricas ni empates: una celda tiene un solo diseño
normal y dos excepciones iguales en la misma celda no se pueden guardar
(usos.py). El origen del trabajo no decide nada: el mismo artículo lleva el
mismo diseño venga de una OC, de una lista de empaque o de una selección; la
OC solo aporta datos y sus excepciones.

Las condiciones son declarativas ({campo, op, valor}) con operadores de una
lista cerrada: nunca se evalúa código escrito por un usuario.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    CategoriaEtiquetado,
    Centro,
    FamiliaEtiquetado,
    OrdenCompra,
    PlantillaEtiqueta,
    Producto,
    TipoEmpaque,
    TipoEtiqueta,
    UsoDiseno,
)
from app.modelos.etiquetado import ALCANCES_DE, NIVELES_DE

# Excepciones de una celda, en el orden en que se revisan (OC va antes, aparte)
ORDEN_CONTEXTO = ("CENTRO_DESTINO", "PAIS_DESTINO", "SOCIEDAD", "PROVEEDOR", "CONDICION")
OPERADORES = ("existe", "vacio", "igual", "distinto", "en", "no_en", "contiene", "no_contiene", "empieza", "termina",
              "mayor", "mayor_igual", "menor", "menor_igual", "entre", "en_familia", "coincide")
# Los que la interfaz ofrece a primera vista (los demás quedan en «Avanzado»)
OPERADORES_SIMPLES = ("igual", "distinto", "en", "no_en", "contiene", "vacio", "existe", "mayor", "menor")
SIN_VALOR = {"existe", "vacio"}
NUMERICOS = {"mayor", "mayor_igual", "menor", "menor_igual", "entre"}
LISTAS = {"en", "no_en"}
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
class Sujeto:
    """Lo que el motor necesita de un registro: qué se etiqueta, su artículo
    (y con él producto, familia y grupo), su OC (destino, sociedad,
    proveedor), el tipo de empaque de un bulto y sus valores (condiciones)."""
    sujeto: str  # ARTICULO | BULTO | DOCUMENTO
    articulo: Articulo | None = None
    oc: OrdenCompra | None = None
    tipo_empaque_id: int | None = None
    valores: dict = field(default_factory=dict)
    proveedor_id: int | None = None


@dataclass
class Eleccion:
    """El diseño de un tipo de etiqueta para un registro y por qué."""
    tipo: TipoEtiqueta
    uso: UsoDiseno | None = None
    porque: dict = field(default_factory=dict)  # clase (oc, excepcion, normal, sin_diseno), nivel, destino, contexto…

    @property
    def plantilla(self) -> PlantillaEtiqueta | None:
        return self.uso.plantilla if self.uso and (self.uso.accion or "USAR") == "USAR" else None

    @property
    def no_lleva(self) -> bool:
        """Una regla dice que este tipo de etiqueta no va en este registro."""
        return bool(self.uso and self.uso.accion == "NO_LLEVA")

    @property
    def alcance(self) -> str:
        """Dónde va: lo que dice la regla o, si no dice, lo del tipo."""
        return (self.uso.alcance if self.uso and self.uso.alcance else None) or alcance_tipo(self.tipo)

    @property
    def cantidad(self) -> str:
        """UNA, POR_UNIDAD o MANUAL: lo que dice la regla o, si no dice, lo del tipo."""
        return (self.uso.cantidad if self.uso and self.uso.cantidad else None) or cantidad_tipo(self.tipo)

    @property
    def motivo(self) -> str:
        """Por qué, en una frase (en inglés; la interfaz la traduce o arma la suya con `porque`)."""
        p = self.porque
        if p.get("clase") == "sin_diseno":
            return f"No design of {self.tipo.nombre} applies."
        if self.no_lleva:
            return f"A rule says {self.tipo.nombre} does not go here" + (f" ({self.uso.motivo})." if self.uso.motivo else ".")
        if p.get("clase") == "elegida":
            return "Chosen by the user for this job."
        donde = {"GENERAL": "Whole company", "FAMILIA": "Labeling family {0}", "CATEGORIA": "Category {0}",
                 "PRODUCTO": "Product {0}", "SKU": "Item {0}", "TIPO_EMPAQUE": "Package type {0}"}[p["nivel"]]
        donde = donde.replace("{0}", str(p.get("destino") or ""))
        if p["clase"] == "oc":
            return f"Exception of PO {p.get('oc')}: {self.uso.motivo or ''}".strip().rstrip(":")
        if p["clase"] == "excepcion":
            return f"{donde}, exception: {p.get('contexto_texto')}" + (f" ({self.uso.motivo})" if self.uso.motivo else "")
        return f"{donde}."

    def dict(self) -> dict:
        p = self.plantilla
        return {"tipo_etiqueta_id": self.tipo.id, "tipo": self.tipo.nombre, "uso_id": self.uso.id if self.uso else None,
                "plantilla_id": p.id if p else None, "plantilla": p.nombre if p else None,
                "version_id": p.version_vigente_id if p else None, "aprobada": bool(p and p.version_vigente_id),
                "porque": self.porque, "motivo": self.motivo, "no_lleva": self.no_lleva, "alcance": self.alcance,
                "cantidad": self.cantidad}


@dataclass
class _Celda:
    normal: UsoDiseno | None = None
    excepciones: list = field(default_factory=list)
    de_oc: dict = field(default_factory=dict)  # oc_id → [usos]


def alcance_tipo(t: TipoEtiqueta) -> str:
    """Dónde va un tipo por defecto: el suyo o, sin uno, lo de antes (la línea o el documento de
    origen; cada variante si sale una por artículo; cada empaque si es de bulto)."""
    if t.alcance and t.alcance in ALCANCES_DE.get(t.sujeto, ()):
        return t.alcance
    if t.sujeto == "ARTICULO":
        return "ARTICULO" if t.cantidad == "POR_ARTICULO" else "LINEA"
    return "DOCUMENTO" if t.sujeto == "DOCUMENTO" else "EMPAQUE"


def cantidad_tipo(t: TipoEtiqueta) -> str:
    return {"POR_UNIDAD": "POR_UNIDAD", "MANUAL": "MANUAL"}.get(t.cantidad, "UNA")


def categoria_de(db: Session, a: Articulo | None, valores: dict, cache: dict | None = None) -> CategoriaEtiquetado | None:
    """La categoría de etiquetado de un artículo, como en la clasificación: la
    puesta a mano en su producto (si es de su familia o de una familia
    superior) o, si no, la primera que se reconoce por sus condiciones,
    empezando por la familia más específica y en el orden de cada familia.
    Una categoría sin condiciones solo se pone a mano."""
    if a is None or a.familia_efectiva is None:
        return None
    familias = [f.id for f in reversed(a.familia_efectiva.ruta())]
    clave = ("cats", tuple(familias))
    if cache is None or clave not in cache:
        cats = list(db.scalars(select(CategoriaEtiquetado).where(CategoriaEtiquetado.familia_id.in_(familias),
                                                                   CategoriaEtiquetado.activa.is_(True))))
        cats.sort(key=lambda c: (familias.index(c.familia_id), c.orden, c.id))
        if cache is None:
            cache = {}
        cache[clave] = cats
    cats = cache[clave]
    manual = a.producto.categoria_etiquetado_id if a.producto is not None else None
    if manual:
        return next((c for c in cats if c.id == manual), None)
    return next((c for c in cats if c.condiciones and all(cumple_condicion(x, valores) for x in c.condiciones)), None)


def celda_de(tipo_id: int, nivel: str, destino_id: int | None) -> str:
    return f"{tipo_id}:{nivel}:{destino_id or 0}"


def vigente(u: UsoDiseno, hoy: date) -> bool:
    return not ((u.vigente_desde and hoy < u.vigente_desde) or (u.vigente_hasta and hoy > u.vigente_hasta))


class Resolvedor:
    """Los usos de diseño cargados una vez para resolver muchos registros.

    `cambios` simula una configuración distinta sin guardarla: usos nuevos o
    editados (sin id o con el id del que reemplazan) y `quitar` (ids dados de
    baja). Lo usan la simulación de una celda y la prueba de una excepción."""

    def __init__(self, db: Session, tipos: list[TipoEtiqueta] | None = None, hoy: date | None = None,
                 cambios: list[UsoDiseno] | None = None, quitar: set[int] | None = None):
        from app.core.empresa import hoy as hoy_empresa

        self.db = db
        self.hoy = hoy or hoy_empresa()
        self.tipos = tipos if tipos is not None else list(db.scalars(
            select(TipoEtiqueta).where(TipoEtiqueta.activo.is_(True)).order_by(TipoEtiqueta.orden, TipoEtiqueta.id)))
        ids = [t.id for t in self.tipos]
        # Las reglas con un diseño activo y las que dicen que la etiqueta no va
        c = (select(UsoDiseno).outerjoin(PlantillaEtiqueta, PlantillaEtiqueta.id == UsoDiseno.plantilla_id)
             .where(UsoDiseno.eliminado_en.is_(None), UsoDiseno.tipo_etiqueta_id.in_(ids),
                    or_(UsoDiseno.accion == "NO_LLEVA", PlantillaEtiqueta.estado == "ACTIVA"))
             .options(selectinload(UsoDiseno.plantilla)))
        reemplazados = {u.id for u in cambios or [] if u.id}
        quitar = set(quitar or set()) | reemplazados
        usos = [u for u in db.scalars(c) if u.id not in quitar] if ids else []
        usos += [u for u in cambios or [] if u.tipo_etiqueta_id in ids and (u.accion == "NO_LLEVA" or (
                 u.plantilla is not None and u.plantilla.estado == "ACTIVA"))]
        self.celdas: dict[tuple, _Celda] = {}
        for u in usos:
            x = self.celdas.setdefault((u.tipo_etiqueta_id, u.nivel, u.destino_id), _Celda())
            if u.contexto_tipo == "NINGUNO":
                x.normal = u
            elif u.contexto_tipo == "OC":
                x.de_oc.setdefault(u.oc_id, []).append(u)
            else:
                x.excepciones.append(u)
        # Dentro de una celda: por clase de excepción; en la misma clase, la de mayor prioridad y luego la más antigua
        for x in self.celdas.values():
            x.excepciones.sort(key=lambda u: (ORDEN_CONTEXTO.index(u.contexto_tipo), -(u.prioridad or 0), u.id or 0))
            for lista in x.de_oc.values():
                lista.sort(key=lambda u: (-(u.prioridad or 0), u.id or 0))
        self._paises: dict | None = None
        self._nombres: dict = {}
        self._cache: dict = {}
        self._categorias: dict = {}

    def categoria(self, s: Sujeto) -> CategoriaEtiquetado | None:
        a = s.articulo
        if a is None:
            return None
        if a.id not in self._categorias:
            valores = s.valores
            if not any(k.startswith("articulo.") for k in valores):
                from app.modulos.etiquetado import campos  # los datos del artículo, si no vinieron (matriz, ficha del producto)

                valores = {**campos.valores_articulo(a), **valores}
            self._categorias[a.id] = categoria_de(self.db, a, valores, self._cache)
        return self._categorias[a.id]

    # ---- Datos del registro -----------------------------------------------------------------
    def _pais_de_centro(self, codigo: str | None) -> str | None:
        if not codigo:
            return None
        if self._paises is None:
            self._paises = dict(self.db.execute(select(Centro.codigo, Centro.pais)).all())
        return self._paises.get(codigo)

    def contexto(self, s: Sujeto) -> dict:
        """Los valores con los que se comparan las excepciones de destino, sociedad y proveedor."""
        oc = s.oc
        prov = s.proveedor_id or (oc.proveedor_id if oc else None) or (s.articulo.proveedor_id if s.articulo else None)
        return {"CENTRO_DESTINO": oc.centro_destino if oc else None,
                "PAIS_DESTINO": self._pais_de_centro(oc.centro_destino) if oc else None,
                "SOCIEDAD": oc.sociedad if oc else None, "PROVEEDOR": str(prov) if prov else None}

    def escalones(self, s: Sujeto) -> list[tuple[str, int | None]]:
        """Los niveles del registro, de lo más específico a lo más general."""
        res: list[tuple[str, int | None]] = []
        a = s.articulo
        for nivel in NIVELES_DE[s.sujeto]:
            if nivel == "SKU" and a is not None:
                res.append(("SKU", a.id))
            elif nivel == "PRODUCTO" and a is not None and a.producto_id:
                res.append(("PRODUCTO", a.producto_id))
            elif nivel == "CATEGORIA" and a is not None:
                cat = self.categoria(s)
                if cat is not None:
                    res.append(("CATEGORIA", cat.id))
            elif nivel == "FAMILIA" and a is not None and a.familia_efectiva is not None:
                res += [("FAMILIA", f.id) for f in reversed(a.familia_efectiva.ruta())]
            elif nivel == "TIPO_EMPAQUE" and s.tipo_empaque_id:
                res.append(("TIPO_EMPAQUE", s.tipo_empaque_id))
            elif nivel == "GENERAL":
                res.append(("GENERAL", None))
        return res

    def coincide(self, u: UsoDiseno, s: Sujeto, ctx: dict) -> bool:
        if not vigente(u, self.hoy):
            return False
        if u.contexto_tipo in ("CENTRO_DESTINO", "PAIS_DESTINO", "SOCIEDAD", "PROVEEDOR"):
            real = ctx.get(u.contexto_tipo)
            if real is None or str(real).upper() not in {str(v).upper() for v in u.contexto_valores or []}:
                return False
        return all(cumple_condicion(c, s.valores) for c in u.condiciones or [])

    # ---- Elección --------------------------------------------------------------------------------
    def _empate(self, gana: UsoDiseno, candidatos: list, s: Sujeto, ctx: dict) -> list[dict]:
        """Otras excepciones del mismo peso (misma celda y tipo) que también aplican con otro diseño: gana la
        más antigua, pero la configuración es ambigua (p. ej. dos excepciones por condiciones que se cumplen a
        la vez) y se avisa. Las que se cruzan siempre (mismos valores y condiciones) ya no se pueden guardar."""
        return [{"uso_id": u.id, "plantilla": u.plantilla.nombre if u.plantilla else None, "contexto_texto": texto_contexto(u)}
                for u in candidatos if u is not gana and u.contexto_tipo == gana.contexto_tipo
                and (u.prioridad or 0) == (gana.prioridad or 0) and (u.plantilla_id, u.accion) != (gana.plantilla_id, gana.accion)
                and self.coincide(u, s, ctx)]

    def elegir(self, s: Sujeto, tipo: TipoEtiqueta) -> Eleccion:
        """El diseño (o «no lleva»), dónde va y cuántas, con la evidencia: la regla que ganó y la categoría del artículo."""
        e = self._elegir(s, tipo)
        cat = self.categoria(s) if s.sujeto == "ARTICULO" else None
        if cat is not None:
            e.porque["categoria"] = cat.nombre
            e.porque["categoria_id"] = cat.id
        if e.no_lleva:
            e.porque["no_lleva"] = True
        return e

    def _elegir(self, s: Sujeto, tipo: TipoEtiqueta) -> Eleccion:
        escalones = self.escalones(s)
        ctx = self.contexto(s)
        if s.oc is not None:
            for nivel, sid in escalones:
                x = self.celdas.get((tipo.id, nivel, sid))
                candidatos = x.de_oc.get(s.oc.id, []) if x else []
                for u in candidatos:
                    if self.coincide(u, s, ctx):
                        return Eleccion(tipo, u, {"clase": "oc", "nivel": nivel, "destino": self.nombre(nivel, sid),
                                                  "oc": s.oc.numero, "motivo": u.motivo,
                                                  "empate": self._empate(u, candidatos, s, ctx)})
        for nivel, sid in escalones:
            x = self.celdas.get((tipo.id, nivel, sid))
            if x is None:
                continue
            for u in x.excepciones:
                if self.coincide(u, s, ctx):
                    return Eleccion(tipo, u, {"clase": "excepcion", "nivel": nivel, "destino": self.nombre(nivel, sid),
                                              "contexto_tipo": u.contexto_tipo, "contexto_valores": u.contexto_valores or [],
                                              "contexto_texto": texto_contexto(u), "motivo": u.motivo,
                                              "empate": self._empate(u, x.excepciones, s, ctx)})
            if x.normal is not None:
                return Eleccion(tipo, x.normal, {"clase": "normal", "nivel": nivel, "destino": self.nombre(nivel, sid)})
        return Eleccion(tipo, None, {"clase": "sin_diseno"})

    def tipos_de(self, sujeto: str) -> list[TipoEtiqueta]:
        return [t for t in self.tipos if t.sujeto == sujeto]

    # ---- Nombres ---------------------------------------------------------------------------------
    def nombre(self, nivel: str, destino_id: int | None) -> str | None:
        """Lo que se lee del destino de un nivel (familia, producto, SKU…)."""
        if destino_id is None:
            return None
        clave = (nivel, destino_id)
        if clave not in self._nombres:
            self._nombres[clave] = nombre_destino(self.db, nivel, destino_id)
        return self._nombres[clave]


def nombre_destino(db: Session, nivel: str, destino_id: int | None) -> str | None:
    if destino_id is None:
        return None
    if nivel == "FAMILIA":
        f = db.get(FamiliaEtiquetado, destino_id)
        return f.nombre if f else None
    if nivel == "CATEGORIA":
        c = db.get(CategoriaEtiquetado, destino_id)
        return c.nombre if c else None
    if nivel == "PRODUCTO":
        p = db.get(Producto, destino_id)
        return " · ".join(x for x in (p.nombre or p.estilo, p.color) if x) if p else None
    if nivel == "SKU":
        a = db.get(Articulo, destino_id)
        return a.sku if a else None
    if nivel == "TIPO_EMPAQUE":
        e = db.get(TipoEmpaque, destino_id)
        return e.nombre if e else None
    return None


def texto_contexto(u: UsoDiseno) -> str:
    """La excepción en una frase corta (en inglés; la interfaz arma la suya con los datos)."""
    valores = ", ".join(str(v) for v in u.contexto_valores or [])
    return {"CENTRO_DESTINO": f"destination plant {valores}", "PAIS_DESTINO": f"destination country {valores}",
            "SOCIEDAD": f"company {valores}", "PROVEEDOR": f"supplier {valores}",
            "CONDICION": "conditions" if u.condiciones else "temporary", "OC": "purchase order"}.get(u.contexto_tipo, "")
