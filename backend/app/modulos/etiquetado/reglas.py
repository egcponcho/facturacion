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

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

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
# Operadores y evaluación de las condiciones: comunes a todas las reglas
from app.modulos.comun.condiciones import (  # noqa: E402
    LISTAS,
    MAX_CONDICIONES,
    MAX_PATRON,
    MAX_TEXTO_PATRON,
    MAX_VALORES,
    NUMERICOS,
    OPERADORES,
    OPERADORES_SIMPLES,
    SIN_VALOR,
    _numero,
    _patron_cumple,
    _texto,
    _vacio,
    cumple_condicion,
    limpiar,
    validar_patron,
)

__all__ = ["LISTAS", "MAX_CONDICIONES", "MAX_PATRON", "MAX_TEXTO_PATRON", "MAX_VALORES", "NUMERICOS", "OPERADORES",
           "OPERADORES_SIMPLES", "SIN_VALOR", "_numero", "_patron_cumple", "_texto", "_vacio", "cumple_condicion",
           "validar_patron"]


# ---- Validación de una regla -----------------------------------------------------------------
def validar_condiciones(db: Session, condiciones) -> list[dict]:
    """Las condiciones limpias o 422: campo del catálogo, operador de la lista y
    un valor del tipo que el operador necesita."""
    from app.modulos.etiquetado import campos

    def familia(campo, op, valor):
        if op == "en_familia" and not db.scalar(select(FamiliaEtiquetado.id).where(FamiliaEtiquetado.codigo == valor.upper())):
            return f"There is no labeling family {valor}."
        return None

    if condiciones in (None, ""):
        return []
    validos = {c.clave for c in campos.catalogo(db)} - {"organizacion.logo"}
    return limpiar(condiciones, validos, familia)


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
    """La categoría de etiquetado de un artículo (grupos/arbol.py: la puesta a
    mano en su producto o la primera que se reconoce por sus condiciones)."""
    from app.modulos.grupos import arbol

    return arbol.categoria_de(db, a, valores, cache)


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
                # Los datos del artículo, si no vinieron (matriz, ficha del producto)
                from app.modulos.etiquetado import campos

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
        return (p.nombre or p.codigo_generico) if p else None
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
