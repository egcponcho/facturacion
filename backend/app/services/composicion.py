"""Lectura de composiciones (fibras y materiales) para el motor de clasificación.

Es la capa «ficha → hechos» de los materiales: lee lo que la gente escribe de
verdad (sinónimos comerciales, errores de dedo, números sin %, etiquetas como
«shell:» o «lining:») y devuelve la fibra predominante del tejido exterior
(Nota 2 de la Sección XI), el material predominante del corte o la suela
(Nota 4 del capítulo 64) o la clase de material de un artículo. No sabe nada
de categorías: los atributos dicen de qué parte y con qué lectura se derivan
(AtributoDef.derivacion).

tests/test_composicion.py fija el resultado esperado (casos de referencia
en tests/paridad).
"""
import math
import re
import unicodedata
from functools import lru_cache

A = re.ASCII  # \b y \d como en JavaScript (solo ASCII)


def norm(s) -> str:
    """Minúsculas y sin tildes."""
    t = unicodedata.normalize("NFD", "" if s is None else str(s).lower())
    return "".join(ch for ch in t if not ("̀" <= ch <= "ͯ"))


def digitos(s) -> str:
    return "".join(ch for ch in ("" if s is None else str(s)) if ch.isdigit())


def redondear(x: float, n: int = 0) -> float:
    """Math.round de JavaScript (la mitad sube)."""
    f = 10 ** n
    return math.floor(x * f + 0.5) / f


def num_txt(x) -> str:
    """Un número como lo escribe JavaScript (100, 60.5)."""
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x)


def _lista(grupos):
    return [(g, alts, re.compile(r"\b(" + "|".join(alts) + r")\b", A)) for g, alts in grupos]


FIBRAS = _lista([
    ("lana", "lana wool merino cachemira? cashmere alpaca mohair angora wo".split()),
    ("seda", "seda silk".split()),
    ("algodon", "algodon cotton co".split()),
    ("vegetal", "lino linen canamo hemp yute jute ramio ramie li".split()),
    ("sintetica", ("poliester polyester rpet nylon nilon poliamida polyamide acrilico acrylic elastano elastane spandex lycra elastodieno "
                   "polipropileno polypropylene aramida aramid olefina olefin polietileno polyethylene pes pa pl ea el pan pp").split()),
    ("artificial", "viscosa viscose rayon modal lyocell tencel acetato acetate triacetato cupro cv cmd".split()),
    ("cuero", "cuero leather piel gamuza suede nubuck nobuck".split()),
])
MATERIALES = _lista([
    ("plastico", ["cuero sintetico", "piel sintetica", "synthetic leather", "faux leather", "pu leather", "vegan leather", "leatherette",
                  *"sinteticos? synthetics? pu tpu tpr kpu pvc vinilo vinyl caucho rubber goma hule latex eva plasticos? plastics? tr phylon poliuretano polyurethane silicona silicone crepe policarbonato polycarbonate tritan abs".split()]),
    ("cuero", "cuero leather piel suede gamuza nubuck nobuck napa nappa charol patent ante carnaza".split()),
    ("textil", ("textil textile tela fabric mesh malla canvas lona nylon poliester polyester rpet poliamida polyamide acrilico acrylic elastano "
                "elastane spandex lycra viscosa viscose rayon modal tencel lino linen seda silk knit flyknit tejido jersey microfibra microfiber "
                "neopreno neoprene lana wool merino algodon cotton fieltro felt corduroy pana denim mezclilla cordura ripstop fleece polar terry "
                "felpa oxford polipropileno polypropylene satin saten elastico lyocell elastano").split()),
    ("otro", ("madera wood corcho cork metal metalico acero steel inoxidable stainless aluminio aluminum aluminium hierro iron zinc bronce brass "
              "laton titanio titanium yute jute papel paper carton cardboard cartulina kraft vidrio glass cristal paja straw palma rafia mdf "
              "arce maple bambu bamboo pino alambre wire cromo").split()),
])
CLASES_MAT = _lista([
    ("plastico", ["cuero sintetico", "piel sintetica", "synthetic leather", "faux leather", "pu leather", "vegan leather",
                  *"sinteticos? synthetics? pu tpu tpr pvc vinilo vinyl caucho rubber goma hule latex eva plasticos? plastics? poliuretano polyurethane silicona silicone policarbonato polycarbonate tritan abs".split()]),
    ("cuero", "cuero leather piel suede gamuza nubuck nobuck napa nappa charol patent ante carnaza".split()),
    ("metal", "metal metalic[oa] acero steel inoxidable stainless aluminio aluminum aluminium hierro iron zinc bronce brass laton titanio titanium alambre wire cromo".split()),
    ("madera", "madera wood mdf arce maple bambu bamboo pino corcho cork".split()),
    ("papel", "papel paper carton cartulina cardboard kraft".split()),
    ("vidrio", "vidrio glass cristal".split()),
    ("paja", "paja straw palma rafia".split()),
    ("textil", ("textil textile tela fabric mesh malla canvas lona nylon poliester polyester rpet poliamida polyamide acrilico acrylic elastano "
                "elastane spandex lycra viscosa viscose rayon modal tencel lino linen seda silk knit tejido jersey microfibra neopreno lana wool "
                "algodon cotton fieltro felt denim mezclilla cordura ripstop fleece polar felpa polipropileno polypropylene satin saten elastico yute jute").split()),
])
RELLENO = _lista([("relleno", "plumon pluma plumas down feathers? goose duck".split())])

MAT_STOP = set((
    "shell body cuerpo exterior forro lining relleno fill filling upper sole suela outsole insole plantilla midsole entresuela and with the con "
    "del los las por para sin recycled reciclado reciclada organic organico organica virgin main trim trims rib ribete principal capa layer fabric "
    "material materials materiales total other others demas parte partes superficie surface interior bonded laminado laminated coated recubierto "
    "without full grain flor split top bottom excluding contar refuerzos adornos accessories accesorios hood capucha pocket pocketing bolsillo "
    "bolsillos contrast contraste panel paneles power goose duck down plumon pluma plumas feather feathers fiber fibra fibras blend mezcla mix approx "
    "aprox aproximadamente weight peso gsm denier oz yarn hilo thread face back backing soporte membrane membrana dryvent futurelight goretex gore "
    "insulation aislante padding guata primaloft thermoball heatseeker vibram ortholite cushion foam espuma molded moldeado injected inyectado "
    "vulcanized vulcanizado cemented stitched cosido parts one outer inner lined unlined logo logos print estampado bci grs rcs eco otros otras resto rest").split())
MAT_AMBIGUAS = {
    "microfibra": "Microfiber can be textile or synthetic (PU): say which", "microfiber": "Microfiber can be textile or synthetic (PU): say which",
    "microfibre": "Microfiber can be textile or synthetic (PU): say which",
    "neopreno": "Neoprene: counts as textile if the fabric faces out; if the rubber is exposed, as rubber or plastics",
    "neoprene": "Neoprene: counts as textile if the fabric faces out; if the rubber is exposed, as rubber or plastics",
}
# Términos comerciales y a qué material equivalen para el SAC (las frases largas primero)
SINONIMOS_BASE = {
    "synthetic suede": "pu", "faux suede": "pu", "micro suede": "pu", "microsuede": "pu", "gamuza sintetica": "pu", "ante sintetico": "pu",
    "synthetic leather": "pu", "faux leather": "pu", "vegan leather": "pu", "pu leather": "pu", "cuero sintetico": "pu", "piel sintetica": "pu",
    "bonded leather": "pu", "leatherette": "pu", "pleather": "pu", "polyurethane leather": "pu", "simil cuero": "pu", "similcuero": "pu", "cuerina": "pu", "ecocuero": "pu",
    "coated fabric": "pvc", "pu coated": "pu", "tpu film": "tpu", "rubber sole": "rubber", "gum rubber": "rubber", "crepe rubber": "rubber",
    "full grain leather": "leather", "full grain": "leather", "top grain leather": "leather", "top grain": "leather", "split leather": "leather", "grain leather": "leather",
    "cowhide": "leather", "cow leather": "leather", "calfskin": "leather", "goatskin": "leather", "sheepskin": "leather", "pigskin": "leather", "lambskin": "leather",
    "vaqueta": "cuero", "becerro": "cuero", "carnaza": "cuero", "nobuk": "nubuck", "nubuk": "nubuck", "oiled leather": "leather", "waxed leather": "leather",
    "phylon": "eva", "ip eva": "eva", "md": "eva", "tpe": "tpr", "kraton": "tpr",
    "twill": "textile", "oxford": "textile", "taslan": "textile", "tricot": "textile", "sherpa": "polyester", "corduroy": "textile", "pana": "textil",
    "terry": "textile", "french terry": "textile", "velour": "textile", "velvet": "textile", "terciopelo": "textil", "chenille": "textile", "suedette": "textile",
    "flyknit": "knit", "primeknit": "knit", "engineered mesh": "mesh", "air mesh": "mesh", "spacer mesh": "mesh", "lycra": "elastane", "dralon": "acrylic",
    "tencel": "lyocell", "lyocell": "viscose", "cupro": "viscose", "bamboo viscose": "viscose", "recycled polyester": "polyester", "rpet": "polyester",
}

# Vocabulario para corregir errores de dedo (en el orden de las listas)
_VOCAB: list[str] = []
for _g, _alts, _ in FIBRAS + MATERIALES:
    for _w in _alts:
        if re.fullmatch(r"[a-z]{4,}", _w):
            if _w not in _VOCAB:
                _VOCAB.append(_w)
        _m = re.fullmatch(r"([a-z]{4,})(s|es)\?", _w)
        if _m and _m.group(1) not in _VOCAB:
            _VOCAB.append(_m.group(1))
_CONOCIDAS = [re.compile("(" + "|".join(alts) + ")", A) for _, alts, _ in FIBRAS + MATERIALES]


def _conocida(w: str) -> bool:
    return any(r.fullmatch(w) for r in _CONOCIDAS)


def _lev(a: str, b: str, lim: int) -> int:
    if abs(len(a) - len(b)) > lim:
        return lim + 1
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i]
        minimo = i
        for j in range(1, len(b) + 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if a[i - 1] == b[j - 1] else 1)))
            minimo = min(minimo, cur[j])
        if minimo > lim:
            return lim + 1
        prev = cur
    return prev[len(b)]


_RE_PCT_SUELTO = re.compile(r"(^|[^\d.,a-z])(\d{1,3}(?:[.,]\d+)?)(?![\d.,]*\s*(?:%|fill|g|gr|gsm|oz|den|d|mm|cm)\b)", A)


@lru_cache(maxsize=64)
def _res_extra(extra: tuple) -> tuple:
    return tuple(re.compile("(" + w + ")", A) for w in extra)


def palabras_clase(texto) -> list[str]:
    """Las palabras de una clase de material configurada (separadas por espacio o
    coma), normalizadas; cada una puede ser un patrón simple (p. ej. «porcelanas?»)."""
    return [w for w in re.split(r"[\s,;]+", norm(texto or "")) if w]


@lru_cache(maxsize=4096)
def _prep(raw: str, sinonimos: tuple, extra: tuple = ()) -> dict:
    s = re.sub(r"\s+", " ", re.sub(r"[/+&]", " , ", norm(raw)))
    cambios, desconocidas, ambiguas = [], [], []
    for k, v in sinonimos:
        r = re.compile("(^|[^a-z])" + re.escape(k) + "(?![a-z])")
        if r.search(s):
            s = r.sub(lambda m, v=v: m.group(1) + v, s)
            cambios.append({"de": k, "a": v, "aprendido": True})

    conocidas_extra = _res_extra(extra)

    def palabra(m):
        w = m.group(0)
        if w in MAT_STOP or _conocida(w) or any(r.fullmatch(w) for r in conocidas_extra):
            if w in MAT_AMBIGUAS:
                ambiguas.append(w)
            return w
        if len(w) >= 4:
            lim = 2 if len(w) >= 7 else 1
            mejor, bd, empate = None, lim + 1, False
            for v in _VOCAB:
                d = _lev(w, v, lim)
                if d < bd:
                    bd, mejor, empate = d, v, False
                elif d == bd and mejor and v != mejor:
                    empate = True
            if mejor and bd <= lim and not empate:
                cambios.append({"de": w, "a": mejor})
                return mejor
        desconocidas.append(w)
        return w

    s = re.sub(r"[a-z]{3,}", palabra, s)
    if "%" not in s:
        nums = [float(m.group(2).replace(",", ".")) for m in _RE_PCT_SUELTO.finditer(s)]
        if nums and abs(sum(nums) - 100) <= 1 and all(n <= 100 for n in nums):
            s = _RE_PCT_SUELTO.sub(lambda m: m.group(1) + m.group(2) + "%", s)
            cambios.append({"pct": True})
    return {"s": s, "cambios": cambios, "desconocidas": list(dict.fromkeys(desconocidas)), "ambiguas": list(dict.fromkeys(ambiguas))}


class Lector:
    """Lector de composiciones con los sinónimos aprendidos de la empresa
    (SinonimoMaterial) además de los comerciales de base, y las clases de
    material configuradas (ClaseMaterial): una clase nueva (cerámica, vidrio
    templado…) o más palabras para una que ya existe."""

    def __init__(self, sinonimos: list[dict] | None = None, clases: list[dict] | None = None):
        d = dict(SINONIMOS_BASE)
        for x in sinonimos or []:
            k = norm(x.get("palabra")).strip()
            if k and x.get("equivale"):
                d[k] = x["equivale"]
        self.sinonimos = tuple(d.items())
        grupos = {g: list(alts) for g, alts, _ in CLASES_MAT}
        extra = []
        for c in clases or []:
            ws = palabras_clase(c.get("palabras"))
            if c.get("codigo") and ws:
                grupos.setdefault(c["codigo"], []).extend(w for w in ws if w not in grupos.get(c["codigo"], []))
                extra += ws
        self.clases = _lista(list(grupos.items())) if extra else CLASES_MAT
        self.extra = tuple(sorted(set(extra)))
        # Palabras de las clases configuradas, para reconocerlas como material en las filas
        self.extra_lista = _lista([(c["codigo"], palabras_clase(c.get("palabras"))) for c in clases or []
                                   if c.get("codigo") and palabras_clase(c.get("palabras"))])

    def prep(self, raw) -> dict:
        return _prep("" if raw is None else str(raw), self.sinonimos, self.extra)

    # ---- Fibras (tejido exterior) y materiales (calzado, artículos) ----
    def parse_comp(self, raw) -> dict | None:
        s = self.prep(raw)["s"].strip()
        if not s:
            return None
        s = _RE_LABELS.sub(r"\n\1:", s)
        segs = []
        for p in [x.strip() for x in re.split(r"[\n;|]+", s) if x.strip()]:
            m = re.match(r"^([a-z][a-z ]{1,20}?)\s*:\s*(.*)$", p)
            body = m.group(2) if m else p
            segs.append({"label": m.group(1).strip() if m else "", "body": body, "fibras": _coincidencias(body, FIBRAS)})
        seg = (next((x for x in segs if _LBL_MAIN.match(x["label"]) and (x["fibras"] or "%" in x["body"])), None)
               or next((x for x in segs if not _LBL_SEC.match(x["label"]) and (x["fibras"] or "%" in x["body"])), None)
               or next((x for x in segs if x["fibras"]), None))
        if not seg:
            return None
        pesos = pesos_de(seg["body"], FIBRAS)
        pred = fibra_pred(pesos)
        if not pred:
            return None
        return {"pesos": pesos, "pred": pred, "segmento": seg["label"], "uso_segmento": len(segs) > 1}

    def parse_mat(self, raw, modo: str = "superficie") -> dict | None:
        """Material predominante de una parte. Modo «superficie» (por defecto): el
        de mayor superficie exterior; sin porcentajes y con varios materiales, es
        mixto. Modo «contacto»: la parte que toca el suelo (caucho o plástico, cuero
        u otro). Se aceptan los nombres anteriores «corte» y «suela»."""
        contacto = modo in ("contacto", "suela")
        s = self.prep(raw)["s"].strip()
        if not s:
            return None
        if "%" not in s:
            gs = list(dict.fromkeys(m["g"] for m in _coincidencias(s, MATERIALES)))
            if len(gs) > 1 and not contacto:
                return {"pesos": {}, "pred": None, "mixto": True, "grupos": gs}
        pesos = pesos_de(s, MATERIALES)
        g, mejor = None, -1
        for k, v in pesos.items():
            if k != "otra" and v > mejor:
                mejor, g = v, k
        if not g:
            return {"pesos": pesos, "pred": None}
        cat = g
        if contacto:
            cat = "caucho" if g == "plastico" else "cuero" if g == "cuero" else "otro"
        return {"pesos": pesos, "pred": cat, "pct": mejor, "mixto": len([k for k in pesos if k != "otra"]) > 1}

    def clase_mat(self, raw) -> dict | None:
        if raw is None or not str(raw).strip():
            return None
        t = self.prep(raw)["s"]
        pesos = pesos_de(t, self.clases)
        pred, mejor = None, -1
        for k, n in pesos.items():
            if k != "otra" and n > mejor:
                mejor, pred = n, k
        if not pred:
            return None
        return {"pred": pred, "pesos": pesos, "corrugado": bool(re.search(r"\bcorrugad|corrugated", t, A)),
                "aluminio": bool(re.search(r"\b(aluminio|aluminum|aluminium)\b", t, A))}

    def clase_texto(self, txt) -> dict | None:
        """Clase de un material escrito (una fila), para mostrarla junto al campo."""
        t = self.prep(txt or "")["s"]
        if not t.strip():
            return None
        pesos = pesos_de(t, self.clases)
        clase, mejor = None, -1
        for k, n in pesos.items():
            if k != "otra" and n > mejor:
                mejor, clase = n, k
        if not clase:
            return None
        sint = clase == "plastico" and not re.search(r"\b(caucho|rubber|goma|hule|latex|eva|tpr)\b", t, A)
        return {"clase": clase, "sintetico": sint}

    def material_derivado(self, raw, mapa: dict, paja: bool = False, metal: bool = False) -> str | None:
        """Material de una parte llevado a las opciones de un atributo (matDerivado)."""
        if raw is None or not str(raw).strip():
            return None
        t = self.prep(raw)["s"]
        if paja and re.search(r"\b(paja|straw)\b", t, A):
            return "paja"
        if metal and _METAL.search(t) and not re.search(r"\b(cuero|leather|nylon|poliester|polyester|plastic|plastico|pvc|silicon)", t, A):
            return "metal"
        pm = self.parse_mat(raw)
        if not pm or not pm["pred"]:
            return None
        v = mapa.get(pm["pred"])
        return v if isinstance(v, str) and v else None

    def filas(self, txt) -> list[dict]:
        """Composición en filas material | % (para mostrarla y editarla)."""
        t = str(txt or "").strip()
        if not t:
            return []
        seg = (segmentos(t) or [t])[0]
        pares = pares_de(self.prep(seg)["s"], FIBRAS + MATERIALES + RELLENO + self.extra_lista)
        if not pares:
            return [{"m": t, "pct": ""}]
        if len(pares) == 1 and pares[0].get("implicito"):
            return [{"m": bonito(pares[0]["w"]), "pct": "100"}]
        return [{"m": bonito(p["w"]) if p["w"] else "Other", "pct": "" if p.get("implicito") else num_txt(redondear(p["pct"], 1))} for p in pares]


# ---- Utilidades de lectura -----------------------------------------------------------
_RE_LABELS = re.compile(r"\b(tela exterior|tela principal|parte superior|shell|exterior|outer|outside|body|cuerpo|principal|main|face|self|lining|forro|"
                        r"relleno|fill|filling|insulation|aislante|padding|guata|trim|ribete|rib|pocketing|pocket|bolsillos?|hood|capucha|contrast|"
                        r"contraste|paneles|panel|upper|outsole|sole|suela)\s*[:=]", A)
_LBL_MAIN = re.compile(r"^(shell|exterior|outer|outside|body|cuerpo|principal|main|face|self|tela exterior|tela principal)$")
_LBL_SEC = re.compile(r"^(lining|forro|relleno|fill|filling|insulation|aislante|padding|guata|trim|ribete|rib|pocket|pocketing|bolsillo|bolsillos|"
                      r"hood|capucha|contrast|contraste|panel|paneles)$")
_METAL = re.compile(r"\b(metal|metalic[oa]|acero|steel|inoxidable|stainless|aluminio|aluminum|aluminium|hierro|iron|zinc|bronce|brass|laton|titanio|titanium)\b", A)
FAM_ORDEN = ["seda", "lana", "algodon", "vegetal", "manmade"]


def _coincidencias(txt: str, lista) -> list[dict]:
    out = []
    for g, _, r in lista:
        for m in r.finditer(txt):
            out.append({"g": g, "i": m.start(), "e": m.end(), "w": m.group(0)})
    out.sort(key=lambda x: (x["i"], -(x["e"] - x["i"])))
    res, fin = [], -1
    for x in out:
        if x["i"] < fin:
            continue
        res.append(x)
        fin = x["e"]
    return res


def pares_de(body: str, lista) -> list[dict]:
    pcts = list(re.finditer(r"(\d+(?:[.,]\d+)?)\s*%", body, A))
    if not pcts:
        f = _coincidencias(body, lista)
        return [{"pct": 100, "g": f[0]["g"], "w": f[0]["w"], "implicito": True}] if f else []
    antes = bool(_coincidencias(body[:pcts[0].start()], lista))
    pares = []
    for i, m in enumerate(pcts):
        val = float(m.group(1).replace(",", "."))
        if antes:
            ini = pcts[i - 1].end() if i > 0 else 0
            fs = _coincidencias(body[ini:m.start()], lista)
            f = fs[-1] if fs else None
        else:
            fin = pcts[i + 1].start() if i + 1 < len(pcts) else len(body)
            fs = _coincidencias(body[m.end():fin], lista)
            f = fs[0] if fs else None
        pares.append({"pct": val, "g": f["g"] if f else "otra", "w": f["w"] if f else ""})
    return pares


def pesos_de(body: str, lista) -> dict:
    pesos: dict[str, float] = {}
    for p in pares_de(body, lista):
        pesos[p["g"]] = pesos.get(p["g"], 0) + p["pct"]
    return pesos


def fibra_pred(p: dict) -> dict | None:
    tex = {"seda": p.get("seda", 0), "lana": p.get("lana", 0), "algodon": p.get("algodon", 0), "vegetal": p.get("vegetal", 0),
           "manmade": p.get("sintetica", 0) + p.get("artificial", 0)}
    total = sum(tex.values())
    cuero, otra = p.get("cuero", 0), p.get("otra", 0)
    if cuero > 0 and cuero >= total and cuero >= otra:
        return {"grupo": "cuero", "familia": "cuero", "pct": cuero}
    if total == 0:
        return {"grupo": "otra", "familia": "otra", "pct": otra} if otra else None
    mejor = None
    for k in FAM_ORDEN:
        if tex[k] > 0 and (not mejor or tex[k] >= tex[mejor]):
            mejor = k
    if otra > tex[mejor]:
        return {"grupo": "otra", "familia": "otra", "pct": otra}
    grupo = mejor
    if mejor == "manmade":
        grupo = "sintetica" if p.get("sintetica", 0) >= p.get("artificial", 0) else "artificial"
    empate = any(k != mejor and tex[k] == tex[mejor] and tex[k] > 0 for k in FAM_ORDEN)
    mezcla = mejor == "manmade" and p.get("sintetica", 0) > 0 and p.get("artificial", 0) > 0
    return {"grupo": grupo, "familia": mejor, "pct": redondear(tex[mejor], 2), "empate": empate, "mezcla_mm": mezcla}


def segmentos(raw) -> list[str]:
    out = []
    for p in re.split(r"[\n;|]+", _RE_LABELS.sub(r"\n\1:", norm(raw))):
        p = p.strip()
        if not p:
            continue
        m = re.match(r"^([a-z][a-z ]{1,20}?)\s*:\s*(.*)$", p)
        out.append(m.group(2) if m else p)
    return out


MAT_LBL = {"plastico": "rubber or plastics", "cuero": "leather", "textil": "textile", "otro": "other material", "otra": "unidentified", "caucho": "rubber or plastics"}


def resumen_mat(pm: dict) -> str:
    items = sorted([(k, v) for k, v in (pm.get("pesos") or {}).items() if k != "otra"], key=lambda x: -x[1])
    return ", ".join(f"{MAT_LBL.get(k, k)} {num_txt(redondear(v, 1))}%" for k, v in items)


_MAT_NOMBRE = {"algodon": "Cotton", "cotton": "Cotton", "poliester": "Polyester", "polyester": "Polyester", "rpet": "Recycled polyester", "nylon": "Nylon",
               "nilon": "Nylon", "poliamida": "Polyamide", "polyamide": "Polyamide", "elastano": "Elastane", "elastane": "Elastane", "spandex": "Elastane",
               "lycra": "Elastane", "viscosa": "Viscose", "viscose": "Viscose", "rayon": "Rayon", "modal": "Modal", "lyocell": "Lyocell", "tencel": "Lyocell",
               "lana": "Wool", "wool": "Wool", "merino": "Merino wool", "acrilico": "Acrylic", "acrylic": "Acrylic", "lino": "Linen", "linen": "Linen",
               "seda": "Silk", "silk": "Silk", "cuero": "Leather", "leather": "Leather", "piel": "Leather", "gamuza": "Suede", "suede": "Suede",
               "nubuck": "Nubuck", "nobuck": "Nubuck", "charol": "Patent leather", "patent": "Patent leather", "lona": "Canvas", "canvas": "Canvas",
               "malla": "Mesh", "mesh": "Mesh", "textil": "Textile", "textile": "Textile", "tela": "Textile", "sintetico": "Synthetic",
               "synthetic": "Synthetic", "pu": "PU", "tpu": "TPU", "tpr": "TPR", "pvc": "PVC", "eva": "EVA", "caucho": "Rubber", "rubber": "Rubber",
               "goma": "Rubber", "hule": "Rubber", "latex": "Latex", "corcho": "Cork", "cork": "Cork", "neopreno": "Neoprene", "neoprene": "Neoprene",
               "plumon": "Down", "pluma": "Feather", "down": "Down", "feather": "Feather", "acero": "Stainless steel", "inoxidable": "Stainless steel",
               "stainless": "Stainless steel", "aluminio": "Aluminum", "aluminum": "Aluminum", "plastico": "Plastic", "plastic": "Plastic",
               "silicona": "Silicone", "metal": "Metal", "laton": "Brass", "zinc": "Zinc", "madera": "Wood", "wood": "Wood", "mdf": "MDF",
               "papel": "Paper", "paper": "Paper", "carton": "Cardboard", "cartulina": "Card stock", "vidrio": "Glass", "paja": "Straw",
               "polipropileno": "Polypropylene", "satin": "Satin", "cordura": "Cordura", "fleece": "Polyester"}


def bonito(w: str) -> str:
    k = norm(w).strip()
    return _MAT_NOMBRE.get(k) or (w[:1].upper() + w[1:] if w else "")


def total_filas(filas: list[dict]) -> float:
    tot = 0.0
    for r in filas:
        try:
            tot += float(str(r.get("pct")).replace(",", "."))
        except ValueError:
            pass
    return redondear(tot, 1)


# ---- Lo que se muestra de una parte en la ficha ------------------------------------------
CLASE_LBL = {"cuero": "Leather", "textil": "Textile", "plastico": "Rubber or plastics", "metal": "Metal", "madera": "Wood or cork", "papel": "Paper",
             "vidrio": "Glass", "paja": "Straw"}
# Para enseñar una palabra que no se reconoce: a qué material equivale
MAT_EQUIV = [("cuero", "Natural leather (hide, suede, nubuck)"), ("sintetico", "Synthetic: rubber or plastics (PU, PVC, TPU)"), ("caucho", "Rubber or EVA"),
             ("textil", "Textile (fabric, canvas, mesh)"), ("algodon", "Cotton"), ("poliester", "Polyester"), ("nylon", "Nylon or polyamide"),
             ("elastano", "Elastane or spandex"), ("acrilico", "Acrylic"), ("viscosa", "Viscose or rayon"), ("lana", "Wool"), ("seda", "Silk"),
             ("lino", "Linen or other vegetable fiber"), ("metal", "Metal"), ("madera", "Wood, cork or other material")]


def etiqueta_clase(c: dict | None) -> dict | None:
    if not c:
        return None
    return {"clase": c["clase"], "lbl": "Synthetic (plastics)" if c["sintetico"] else CLASE_LBL.get(c["clase"], c["clase"])}
