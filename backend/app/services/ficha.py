"""Ficha técnica → hechos: la capa que normaliza lo que la persona escribe y
deriva lo que el motor de clasificación necesita, gobernada por datos.

Todo sale del catálogo de atributos (AtributoDef, AtributoOpcion,
AtributoAmbito) y de las categorías (CategoriaProducto); no hay nada
específico de una categoría en el código:

- Ámbitos: dónde se pregunta cada atributo (SYSTEM, DOMAIN, CATEGORY, CHAPTER,
  HEADING, SUBHEADING), con condición y modo SHOW / REQUIRE / HIDE. Se elige
  un solo ámbito, de forma determinista: entre los que aplican (condición
  cumplida) gana el más específico (CATEGORY > DOMAIN > SUBHEADING > HEADING
  > CHAPTER > SYSTEM); a igual especificidad, la mayor prioridad; a igual
  prioridad, HIDE > REQUIRE > SHOW y después el id. HIDE oculta de verdad.
- Derivaciones (AtributoDef.derivacion): el valor que fijan la composición
  (fibra predominante, material del corte, de la suela, clase de material),
  una constante o el valor de otro atributo. Mandan sobre lo marcado a mano.
- Bloqueos (AtributoOpcion.bloqueo, AtributoDef.bloqueo para casillas): las
  combinaciones imposibles, con condición y mensaje; la opción se quita y se
  avisa por qué.
- Implicaciones (AtributoOpcion.implica): elegir una opción completa otras
  respuestas vacías.
- Detección (patrones de categorías y opciones): lo que se deduce del nombre,
  el uso, las tallas o la composición, sin pisar lo que la persona eligió.
- usado_clasificacion = False: el dato se recoge pero no llega a las reglas.

Antes esta lógica vivía en el navegador (motor.js: ATTRS, normalizar,
estadoAttr, detectar); tests/test_ficha.py prueba la paridad.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .composicion import Lector, norm, resumen_mat
from .motor_clasificacion import condicion as _condicion, evaluar

A = re.ASCII
ESPECIFICIDAD = {"CATEGORY": (4, 0), "DOMAIN": (3, 0), "SUBHEADING": (2, 2), "HEADING": (2, 1), "CHAPTER": (2, 0), "SYSTEM": (0, 0)}
MODO_ORDEN = {"HIDE": 2, "REQUIRE": 1, "SHOW": 0}
SECCIONES = ("producto", "caracteristicas", "composicion", "nacional", "derivado")
PARTE_TXT = {"corte": "of the upper", "suela": "of the sole", "exterior": "of the outer fabric", "material": "of the material"}


@dataclass
class Opcion:
    codigo: str
    etiqueta: str
    orden: int = 0
    activo: bool = True
    bloqueo: list = field(default_factory=list)
    implica: dict | None = None
    patrones: list = field(default_factory=list)


@dataclass
class Ambito:
    tipo: str
    codigo: str
    modo: str = "SHOW"
    prioridad: int = 500
    condicion: list | None = None
    nota: str | None = None
    id: int = 0


@dataclass
class Atributo:
    codigo: str
    etiqueta: str
    tipo_dato: str = "text"
    seccion: str = "caracteristicas"
    ayuda: str | None = None
    informativo: bool = False
    usado_clasificacion: bool = True
    valor_defecto: str | None = None
    derivacion: dict | None = None
    bloqueo: list = field(default_factory=list)
    patrones: list = field(default_factory=list)
    patrones_falso: list = field(default_factory=list)
    opciones: list[Opcion] = field(default_factory=list)
    ambitos: list[Ambito] = field(default_factory=list)
    orden: int = 0
    unidad: str | None = None
    control: str | None = None
    dominio: str | None = None
    origen: str = "USUARIO"

    def opcion(self, v) -> Opcion | None:
        return next((o for o in self.opciones if o.codigo == v), None)

    @property
    def booleano(self) -> bool:
        return self.tipo_dato == "boolean"


@dataclass
class Categoria:
    codigo: str
    nombre: str
    dominio: str | None = None
    grupo: str | None = None
    familia: str | None = None
    nombre_corto: str | None = None
    nombre_aduana: str | None = None
    alias: str | None = None
    patrones: list = field(default_factory=list)
    capitulos: list = field(default_factory=list)
    orden: int = 0
    activo: bool = True


class Catalogo:
    """Foto del catálogo (atributos y categorías) para una clasificación o un lote."""

    def __init__(self, atributos: list[Atributo], categorias: list[Categoria], sinonimos: list[dict] | None = None,
                 palabras: list[dict] | None = None):
        orden = lambda a: (a.seccion != "derivado", a.orden, a.codigo)  # noqa: E731 - los hechos derivados primero
        self.atributos = sorted(atributos, key=orden)
        self.por_codigo = {a.codigo: a for a in self.atributos}
        self.categorias = {c.codigo: c for c in categorias}
        self.lector = Lector(sinonimos)
        self.palabras = palabras or []

    # ---- Construcción --------------------------------------------------------------------
    @classmethod
    def desde_db(cls, db) -> "Catalogo":
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from ..models import AtributoDef, CategoriaProducto, PalabraClave, SinonimoMaterial

        attrs = []
        for a in db.scalars(select(AtributoDef).options(selectinload(AtributoDef.opciones), selectinload(AtributoDef.ambitos))
                            .where(AtributoDef.activo.is_(True))):
            attrs.append(Atributo(
                codigo=a.codigo, etiqueta=a.etiqueta, tipo_dato=a.tipo_dato, seccion=a.seccion or "caracteristicas", ayuda=a.descripcion,
                informativo=a.informativo, usado_clasificacion=a.usado_clasificacion, valor_defecto=a.valor_defecto, derivacion=a.derivacion,
                bloqueo=a.bloqueo or [], patrones=a.patrones or [], patrones_falso=a.patrones_falso or [], orden=a.orden, unidad=a.unidad,
                control=a.control, dominio=a.dominio, origen=a.origen,
                opciones=[Opcion(o.codigo, o.etiqueta, o.orden, o.activo, o.bloqueo or [], o.implica, o.patrones or []) for o in a.opciones],
                ambitos=[Ambito(x.tipo_ambito, x.codigo_ambito, x.modo, x.prioridad, x.condicion, x.nota, x.id) for x in a.ambitos if x.activo]))
        cats = [Categoria(c.codigo, c.nombre, c.dominio, c.grupo, c.familia, c.nombre_corto, c.nombre_aduana, c.alias, c.patrones or [],
                          c.capitulos or [], c.orden, c.activo) for c in db.scalars(select(CategoriaProducto))]
        sin = [{"palabra": x.palabra, "equivale": x.equivale} for x in db.scalars(select(SinonimoMaterial))]
        pal = [{"frase": x.frase, "tipo": x.tipo, "marca": x.marca, **(x.atributos or {})} for x in db.scalars(select(PalabraClave))]
        return cls(attrs, cats, sin, pal)

    @classmethod
    def desde_json(cls, ruta: Path | None = None) -> "Catalogo":
        """El catálogo de la ficha tal como se siembra (pruebas sin base)."""
        d = json.loads((ruta or DATOS_ATRIBUTOS).read_text(encoding="utf-8"))
        attrs = []
        for a in d["atributos"]:
            attrs.append(Atributo(
                codigo=a["codigo"], etiqueta=a["etiqueta"], tipo_dato=a["tipo_dato"], seccion=a.get("seccion") or "caracteristicas",
                ayuda=a.get("ayuda"), informativo=bool(a.get("informativo")), valor_defecto=a.get("valor_defecto"), derivacion=a.get("derivacion"),
                bloqueo=a.get("bloqueo") or [], patrones=a.get("patrones") or [], patrones_falso=a.get("patrones_falso") or [],
                orden=a.get("orden", 0), unidad=a.get("unidad"), control=a.get("control"), origen="MOTOR",
                opciones=[Opcion(o["codigo"], o["etiqueta"], o.get("orden", 0), True, o.get("bloqueo") or [], o.get("implica"), o.get("patrones") or [])
                          for o in a.get("opciones") or []],
                ambitos=[Ambito(x["tipo_ambito"], x["codigo_ambito"], x.get("modo") or "SHOW", x.get("prioridad", 500), x.get("condicion"))
                         for x in a.get("ambitos") or []]))
        cats = [Categoria(c["codigo"], c["nombre"], c.get("dominio"), c.get("grupo"), c.get("familia"), c.get("nombre_corto"), c.get("nombre_aduana"),
                          c.get("alias"), c.get("patrones") or [], c.get("capitulos") or [], c.get("orden", 0)) for c in d["categorias"]]
        return cls(attrs, cats)

    # ---- Ámbitos ---------------------------------------------------------------------------
    def ambito(self, a: Atributo, s: dict, codigos: list[str] | None = None) -> Ambito | None:
        """El ámbito que gobierna el atributo para este producto, o None si no aplica."""
        cat, dom = s.get("categoria") or "", s.get("dominio") or ""
        codigos = codigos or []
        mejor, clave_mejor = None, None
        for x in a.ambitos:
            t = x.tipo
            toca = (t == "SYSTEM" or (t == "DOMAIN" and x.codigo == dom) or (t == "CATEGORY" and x.codigo == cat)
                    or (t == "CHAPTER" and any(c.startswith(x.codigo) for c in codigos) and len(x.codigo) == 2)
                    or (t == "HEADING" and any(c.startswith(x.codigo) for c in codigos))
                    or (t == "SUBHEADING" and any(c.startswith(x.codigo) for c in codigos)))
            if not toca or not _cumple(x.condicion, s):
                continue
            k = (ESPECIFICIDAD.get(t, (0, 0)), x.prioridad, MODO_ORDEN.get(x.modo, 0), -x.id)
            if clave_mejor is None or k > clave_mejor:
                mejor, clave_mejor = x, k
        return mejor

    def aplica(self, a: Atributo, s: dict, codigos=None) -> bool:
        x = self.ambito(a, s, codigos)
        return bool(x) and x.modo != "HIDE"

    # ---- Derivaciones ------------------------------------------------------------------------
    def derivar(self, a: Atributo, s: dict):
        """Valor que fijan los datos (composición, categoría u otro atributo), o None."""
        d = a.derivacion
        if not d:
            return None
        if d.get("cuando") and not _cumple(d["cuando"], s):
            return None
        modo = d.get("modo")
        if modo == "constante":
            return d.get("valor")
        if modo == "valor":
            v = s.get(d.get("desde"))
            mapa = d.get("mapa") or {}
            return mapa.get(str(v)) if not _vacio(v) and str(v) in mapa else mapa.get("*")
        txt = self._texto_parte(d, s)
        if not txt:
            return None
        L = self.lector
        if modo == "fibra":
            pc = L.parse_comp(txt)
            return pc["pred"]["grupo"] if pc else None
        if modo == "material":
            mapa = d.get("mapa")
            if mapa is None and not d.get("paja") and not d.get("metal"):
                pm = L.parse_mat(txt, d.get("lectura") or "corte")
                return pm["pred"] if pm and pm["pred"] else None
            return L.material_derivado(txt, mapa or {}, paja=bool(d.get("paja")), metal=bool(d.get("metal")))
        if modo == "clase":
            c = L.clase_mat(txt)
            if not c:
                return None
            mapa = d.get("mapa") or {}
            for bandera in ("aluminio", "corrugado"):
                if c.get(bandera) and f"{c['pred']}+{bandera}" in mapa:
                    return mapa[f"{c['pred']}+{bandera}"]
            return mapa.get(c["pred"]) or mapa.get("*")
        return None

    def _texto_parte(self, d: dict, s: dict) -> str:
        txt = s.get(f"comp.{d['parte']}") if d.get("parte") else None
        if txt and str(txt).strip():
            return str(txt)
        for r in d.get("respaldo") or []:
            if r == "texto%":
                t = s.get("_texto") or ""
                if "%" in t:
                    return t
            elif s.get(r) and str(s[r]).strip():
                return str(s[r])
        return ""

    def motivo_derivado(self, a: Atributo, s: dict) -> str:
        d = a.derivacion or {}
        if d.get("modo") in ("constante", "valor"):
            return "categoria"
        return "composicion"

    def _texto_motivo(self, a: Atributo, s: dict) -> str:
        d = a.derivacion or {}
        parte = d.get("parte")
        if not parte:
            return ""
        txt = s.get(f"comp.{parte}") or ""
        pm = self.lector.parse_mat(txt, "suela" if d.get("lectura") == "suela" else "corte") if str(txt).strip() else None
        extra = f" ({resumen_mat(pm)})" if pm and pm.get("pred") else ""
        return f"Taken from the composition {PARTE_TXT.get(parte, '')}{extra}. If it is wrong, fix the composition."

    # ---- Bloqueos ----------------------------------------------------------------------------------
    def bloqueo_opcion(self, a: Atributo, o: Opcion | None, s: dict) -> str | None:
        if o is None:
            return "invalid option"
        for b in o.bloqueo:
            if _cumple(b.get("condiciones"), s):
                return b.get("mensaje") or "Not available"
        if not o.activo:
            return "Option disabled in the attribute catalog."
        return None

    def bloqueo_casilla(self, a: Atributo, s: dict) -> str | None:
        for b in a.bloqueo:
            if _cumple(b.get("condiciones"), s):
                return b.get("mensaje") or "Not available"
        return None

    def opciones_validas(self, a: Atributo, s: dict) -> list[Opcion]:
        fx = self.derivar(a, s) if self.aplica(a, s) else None
        return [o for o in a.opciones if (fx is None or o.codigo == fx) and not self.bloqueo_opcion(a, o, s)]

    # ---- Normalización ----------------------------------------------------------------------------
    def hechos_base(self, ficha: dict, categoria: str | None, dominio: str | None = None, texto: str = "") -> dict:
        """La ficha llevada a un diccionario plano de hechos (comp.<parte> para la composición)."""
        s = {k: v for k, v in (ficha or {}).items() if k != "comp" and not isinstance(v, dict)}
        for p, v in ((ficha or {}).get("comp") or {}).items():
            s[f"comp.{p}"] = v
        cat = self.categorias.get(categoria or "")
        s["categoria"] = categoria or ""
        s["dominio"] = dominio or (cat.dominio if cat else "") or ""
        s["_texto"] = texto or ""
        for a in self.atributos:
            if a.booleano and a.valor_defecto in ("false", "true") and s.get(a.codigo) is None:
                s[a.codigo] = a.valor_defecto == "true"
        return s

    def normalizar(self, s: dict) -> list[dict]:
        """Aplica derivaciones y bloqueos hasta que se estabiliza (como lo
        hacía la ficha): devuelve los avisos {campo, texto}."""
        avisos: list[dict] = []

        def avisar(campo, texto):
            if not any(x["texto"] == texto for x in avisos):
                avisos.append({"campo": campo, "texto": texto})

        for _ in range(3):
            for a in self.atributos:
                if a.tipo_dato == "composition" or not self.aplica(a, s):
                    continue
                fx = self.derivar(a, s)
                if fx is not None and s.get(a.codigo) != fx:
                    if s.get(a.codigo) and a.seccion == "composicion":
                        avisar(a.codigo, f'{a.etiqueta}: changed from "{_lbl(a, s[a.codigo])}" to "{_lbl(a, fx)}". {self._texto_motivo(a, s)}')
                    s[a.codigo] = fx
                v = s.get(a.codigo)
                if a.booleano:
                    r = self.bloqueo_casilla(a, s) if v else None
                    if r:
                        s[a.codigo] = False
                        avisar(a.codigo, f'Unchecked "{a.etiqueta}": {r}')
                elif a.tipo_dato in ("select", "multi_select") and not _vacio(v):
                    vs = v if isinstance(v, list) else [v]
                    quitar = []
                    for x in vs:
                        o = a.opcion(x)
                        r = self.bloqueo_opcion(a, o, s)
                        if r:
                            quitar.append(x)
                            avisar(a.codigo, f'Removed "{o.etiqueta if o else x}": {r}')
                    if quitar:
                        s[a.codigo] = [x for x in vs if x not in quitar] if isinstance(v, list) else ""
        for a in self.atributos:
            if a.tipo_dato != "select" or a.informativo or a.seccion not in ("caracteristicas",) or not _vacio(s.get(a.codigo)):
                continue
            if not self.aplica(a, s):
                continue
            validas = [o for o in a.opciones if not self.bloqueo_opcion(a, o, s)]
            if len(validas) == 1:
                s[a.codigo] = validas[0].codigo
        return avisos

    def aplicar_implica(self, s: dict, campo: str, valor) -> list[str]:
        """Completa lo que implica una respuesta, sin pisar lo que ya es válido."""
        a = self.por_codigo.get(campo)
        o = a.opcion(valor) if a else None
        cambiados = []
        for k, val in ((o.implica or {}) if o else {}).items():
            b = self.por_codigo.get(k)
            actual = s.get(k)
            invalido = False
            if b and not b.booleano and not _vacio(actual):
                invalido = bool(self.bloqueo_opcion(b, b.opcion(actual), s))
            if not _vacio(actual) and actual is not False and not invalido:
                continue
            if b and not b.booleano:
                ob = b.opcion(val)
                if ob and self.bloqueo_opcion(b, ob, {**s, k: val}):
                    continue
            if s.get(k) != val:
                s[k] = val
                cambiados.append(k)
        return cambiados

    # ---- Qué se pregunta ------------------------------------------------------------------------
    def estado(self, a: Atributo, s: dict, codigos=None) -> str:
        """preguntar | definido | oculto (para la sección de características)."""
        if a.seccion == "derivado":
            return "oculto"
        if not self.aplica(a, s, codigos):
            return "oculto"
        if a.booleano:
            if a.seccion != "caracteristicas":
                return "oculto"
            return "oculto" if self.bloqueo_casilla(a, s) else "preguntar"
        if self.derivar(a, s) is not None:
            return "definido"
        if a.seccion != "caracteristicas":
            return "oculto"
        if a.tipo_dato in ("select", "multi_select"):
            ops = self.opciones_validas(a, s)
            if not ops:
                return "oculto"
            if len(ops) == 1 and not a.informativo:
                return "definido"
        return "preguntar"


    # ---- Detección por texto ------------------------------------------------------------------
    def _palabra(self, texto: str, marca: str | None) -> dict | None:
        """Palabra clave aprendida (PalabraClave): la frase más larga que aparece en el nombre."""
        t = " " + re.sub(r"[^a-z0-9]+", " ", norm(texto)).strip() + " "
        hits = []
        for p in self.palabras:
            if not p.get("frase") or not p.get("tipo"):
                continue
            if p.get("marca") and norm(p["marca"]).strip() != norm(marca or "").strip():
                continue
            f = re.sub(r"[^a-z0-9]+", " ", norm(p["frase"])).strip()
            if f and f" {f} " in t:
                hits.append(p)
        return max(hits, key=lambda p: len(p["frase"]), default=None)

    def _categoria_texto(self, s: str) -> str | None:
        pats = sorted(((p.get("prioridad", 999), c.orden, c.codigo, p) for c in self.categorias.values() if c.activo for p in c.patrones),
                      key=lambda x: x[:3])
        for _, _, cod, p in pats:
            if p.get("re") and re.search(p["re"], s, A):
                return cod
        return None

    def _candidatos_attr(self, cat: str) -> list[Atributo]:
        """Atributos que pueden aplicar a la categoría (con cualquier condición) y los nacionales."""
        dom = self.categorias[cat].dominio if cat in self.categorias else None
        out = []
        for a in self.atributos:
            if a.seccion == "derivado" or a.tipo_dato == "composition":
                continue
            if a.seccion == "nacional" or any(x.tipo == "SYSTEM" or (x.tipo == "CATEGORY" and x.codigo == cat) or (x.tipo == "DOMAIN" and x.codigo == dom)
                                               for x in a.ambitos):
                out.append(a)
        return out

    @staticmethod
    def _coincide(p: dict, textos: dict, d: dict) -> bool:
        if p.get("cuando") and not _cumple(p["cuando"], d):
            return False
        t = textos.get(p.get("en") or "estilo", "")
        if p.get("defecto") or not p.get("re"):  # por defecto, o solo por condición
            return not any(re.search(n, t, A) for n in p.get("no") or [])
        if not re.search(p["re"], t, A):
            return False
        ty = textos.get(p.get("y_en") or p.get("en") or "estilo", "")
        if any(not re.search(y, ty, A) for y in p.get("y") or []):
            return False
        return not any(re.search(n, t, A) for n in p.get("no") or [])

    def _detectar(self, texto: str, comp: dict, tallas: str, uso: str, cat_forzada: str | None) -> tuple[dict, set]:
        s = norm(texto)
        comp_txt = norm(" ".join(str(v) for v in (comp or {}).values()))
        textos = {"estilo": s, "todo": f"{s} {comp_txt}", "tallas": norm(tallas or ""), "uso": norm(f"{texto} {uso or ''}"),
                  "uso_comp": norm(f"{texto} {uso or ''} {comp_txt}"), "comp.suela": norm((comp or {}).get("suela") or "")}
        d: dict = {}
        defecto: set = set()
        cat = cat_forzada or self._categoria_texto(s)
        if cat:
            d["categoria"] = cat
        if not cat:
            return d, defecto
        # Dos pasadas: las condiciones de un patrón ven lo detectado en la primera
        previo: dict = {}
        for _ in range(2):
            d, defecto = {"categoria": cat}, set()
            self._detectar_attrs(self._candidatos_attr(cat), textos, d, defecto, previo)
            previo = dict(d)
        # Lo que implica lo detectado completa lo que no se detectó
        for a in list(self._candidatos_attr(cat)):
            o = a.opcion(d.get(a.codigo)) if not a.booleano else None
            for k, v in ((o.implica or {}) if o else {}).items():
                if k not in d:
                    d[k] = v
                    defecto.add(k)
        return d, defecto

    def _detectar_attrs(self, attrs, textos: dict, d: dict, defecto: set, previo: dict) -> None:
        for a in attrs:
            ctx = {**previo, **d}
            if a.booleano:
                if any(self._coincide(p, textos, ctx) for p in a.patrones):
                    d[a.codigo] = True
                elif any(self._coincide(p, textos, ctx) for p in a.patrones_falso):
                    d[a.codigo] = False
                continue
            mejor = None
            for o in a.opciones:
                for p in o.patrones:
                    if not p.get("defecto") and self._coincide(p, textos, ctx) and (mejor is None or p.get("prioridad", 999) < mejor[0]):
                        mejor = (p.get("prioridad", 999), o.codigo)
            if mejor:
                d[a.codigo] = mejor[1]
                continue
            for o in a.opciones:
                if any(p.get("defecto") and self._coincide(p, textos, ctx) for p in o.patrones):
                    d[a.codigo] = o.codigo
                    defecto.add(a.codigo)
                    break

    def detectar(self, ficha: dict, estilo: str = "", nombre: str = "", uso: str = "", tallas: str = "", marca: str | None = None,
                 categoria: str | None = None) -> dict:
        """Lo que se deduce del nombre del estilo, el uso, las tallas y la
        composición: la categoría (si no se eligió) y las respuestas.
        Devuelve {campo: valor} más _palabra si vino de una palabra clave."""
        texto = " ".join(x for x in (estilo, nombre) if str(x or "").strip())
        comp = (ficha or {}).get("comp") or {}
        h = self._palabra(texto, marca)
        d, defecto = self._detectar(texto, comp, tallas, uso, categoria or (h or {}).get("tipo"))
        if h:
            for k, v in h.items():
                if k in ("frase", "tipo", "marca", "id") or v in (None, ""):
                    continue
                if k not in d or k in defecto:
                    d[k] = v
            a = self.por_codigo.get("estiloCalz")
            if h.get("estiloCalz") and a:
                o = a.opcion(d.get("estiloCalz"))
                for k, v in ((o.implica or {}) if o else {}).items():
                    if (k not in d or k in defecto) and k not in h:
                        d[k] = v
                if d.get("estiloCalz") != "tenis":
                    d.pop("disenio", None)
            d["_palabra"] = h["frase"]
        if uso and str(uso).strip():
            if not d.get("categoria"):
                cabeza = re.split(r"\b(para|que|donde|con el que|for|to|used|sirve|se usa|which|that)\b", norm(uso))[0]
                dc = self._detectar(cabeza, {}, "", "", None)[0] if cabeza.strip() else {}
                du = dc if dc.get("categoria") else self._detectar(uso, {}, "", "", None)[0]
                if du.get("categoria"):
                    d["categoria"] = du["categoria"]
            d2, _ = self._detectar(f"{texto} {uso}", comp, tallas, uso, d.get("categoria"))
            for k, v in d2.items():
                if k not in d:
                    d[k] = v
            if d.get("categoria") == "calzado" and d.get("disenio") == "casual" and d2.get("disenio") == "entrenamiento":
                d["disenio"] = "entrenamiento"
        # Los datos nacionales se deducen al final, con lo ya detectado
        if d.get("categoria"):
            nac = [a for a in self._candidatos_attr(d["categoria"]) if a.seccion == "nacional" or a.codigo == "edadNac"]
            comp_txt = norm(" ".join(str(v) for v in comp.values()))
            s0 = norm(texto)
            textos = {"estilo": s0, "todo": f"{s0} {comp_txt}", "tallas": norm(tallas or ""), "uso": norm(f"{texto} {uso or ''}"),
                      "uso_comp": norm(f"{texto} {uso or ''} {comp_txt}"), "comp.suela": norm(comp.get("suela") or "")}
            base = {k: v for k, v in d.items() if k not in {a.codigo for a in nac}}
            nuevo: dict = {}
            self._detectar_attrs(nac, textos, nuevo, set(), base)
            for a in nac:
                if a.codigo in nuevo:
                    d[a.codigo] = nuevo[a.codigo]
                else:
                    d.pop(a.codigo, None)
        return d


def _vacio(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _cumple(cond, s: dict) -> bool:
    """Condiciones de ámbito o de bloqueo: solo cuentan si se cumplen (pendiente = no)."""
    if not cond:
        return True
    if all(isinstance(c, dict) and "campo" in c for c in cond):
        return evaluar(cond, s)[0] is True
    # Formato antiguo: lista de alternativas {atributo: valor}
    for alt in cond:
        if all(_condicion("IN" if isinstance(v, list) else "EQUAL", s.get(k), v) is True for k, v in (alt or {}).items()):
            return True
    return False


def _lbl(a: Atributo, v) -> str:
    if a.booleano:
        return "Yes" if v else "No"
    o = a.opcion(v)
    return o.etiqueta if o else str(v)


DATOS_ATRIBUTOS = Path(__file__).resolve().parent.parent / "data" / "motor_atributos.json"
__all__ = ["Catalogo", "Atributo", "Opcion", "Ambito", "Categoria", "norm"]
