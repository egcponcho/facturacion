"""Utilidades para escribir las familias del motor a partir de las Notas Explicativas.

Cada familia se escribe en Python (un módulo por familia) con estas piezas y
`construir.py` la vuelca a `app/data/motor/familias/<archivo>.json`, que es la
semilla que carga el sistema. Así los mapas por fibra o por materia se arman
leyendo el texto del árbol oficial vigente y cada código se valida contra él:
una regla nunca apunta a una subpartida que no existe.
"""
import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ARBOL = json.loads((RAIZ / "app/data/oficial/sac_oficial.json").read_text(encoding="utf-8"))
TEXTO = {x["codigo"]: x["descripcion"] for x in ARBOL}
SALIDA = RAIZ / "app/data/motor/familias"


def norm(s: str) -> str:
    t = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(ch for ch in t if not ("̀" <= ch <= "ͯ"))


def existe(codigo: str) -> bool:
    c = "".join(ch for ch in str(codigo) if ch.isdigit())
    if len(c) in (2, 3, 4, 5):  # capítulo, partida o grupo de subpartidas
        return any(k.startswith(c) for k in TEXTO)
    return c in TEXTO


def subpartidas(prefijo: str) -> list[str]:
    """Las subpartidas (6 dígitos) del árbol vigente que empiezan con el prefijo."""
    p = "".join(ch for ch in prefijo if ch.isdigit())
    return sorted(k for k in TEXTO if len(k) == 6 and k.startswith(p))


def ultimo(codigo: str) -> str:
    """El último tramo del texto oficial de un código (lo que lo distingue de sus hermanos)."""
    return norm(TEXTO[codigo].split(" — ")[-1])


# ---- Mapas por fibra (Nota 2 de la Sección XI) ----------------------------------------------
FIBRAS = ("lana", "algodon", "sintetica", "artificial", "seda", "vegetal", "otra", "cuero")


def _hay(t: str, *palabras) -> bool:
    return any(p in t for p in palabras)


def por_fibra(prefijo: str, excluir: tuple = ()) -> dict:
    """fibra → subpartida, leyendo «De algodón», «De fibras sintéticas o artificiales»,
    «De lana o pelo fino», «De las demás materias textiles»… en el texto oficial.
    Lo que no tiene subpartida propia va a «las demás materias textiles»."""
    cods = [c for c in subpartidas(prefijo) if c not in excluir]
    demas = (next((c for c in cods if "demas materias" in ultimo(c)), None)
             or next((c for c in cods if _hay(ultimo(c), "los demas", "las demas")), None))
    mapa = {}
    for f in FIBRAS:
        elegido = None
        for c in cods:
            t = ultimo(c)
            if f == "lana" and _hay(t, "de lana", "pelo fino") and "cachemira" not in t:
                elegido = elegido or c
            elif f == "algodon" and "algodon" in t:
                elegido = elegido or c
            elif f == "sintetica" and "sintetic" in t:
                elegido = elegido or c
            elif f == "artificial" and "artificial" in t:
                elegido = elegido or c
            elif f == "seda" and "seda" in t:
                elegido = elegido or c
        mapa[f] = elegido or demas
    if not demas:
        raise ValueError(f"{prefijo}: no «demás» subheading to fall back on: {cods}")
    mapa[""] = prefijo  # sin fibra todavía: la partida (la regla queda pendiente de la fibra)
    return mapa


# ---- Piezas -------------------------------------------------------------------------------
def cond(campo: str, valor, operador: str | None = None, negado: bool = False, grupo: int = 1) -> dict:
    if operador is None:
        operador = "IN" if isinstance(valor, list) else "EQUAL"
    return {"grupo": grupo, "campo": campo, "operador": operador, "valor": valor, "negado": negado}


def si(**kw) -> list[dict]:
    """Condiciones Y: campo=valor (lista = «uno de»). Un nombre que termina en _no niega."""
    out = []
    for k, v in kw.items():
        neg = k.endswith("_no")
        campo = k[:-3] if neg else k
        campo = campo.replace("__", ".")
        if v is None:
            out.append(cond(campo, None, "EXISTS", negado=not neg))
        else:
            out.append(cond(campo, v, negado=neg))
    return out


def regla(codigo: str, categoria: str, condiciones: list, codigos: list | None = None, efecto: str = "", *, por: str | None = None,
          mapa: dict | None = None, prioridad: int | None = None, tipo: str = "RESTRICT", mensaje: str | None = None,
          revision: bool = False) -> dict:
    accion = {"tipo": tipo}
    if codigos:
        accion["codigos"] = list(codigos)
    if por:
        accion["por"], accion["mapa"] = por, dict(mapa or {})
    if mensaje:
        accion["mensaje"] = mensaje
    r = {"codigo": codigo, "categoria": categoria, "condiciones": condiciones, "accion": accion, "efecto": efecto}
    if prioridad is not None:
        r["prioridad"] = prioridad
    if revision:
        r["requiere_revision"] = True
    return r


def opcion(codigo: str, etiqueta: str, *, re_: str | None = None, en: str = "todo", prioridad: int = 10, texto: dict | list | None = None,
           implica: dict | None = None, bloqueo: list | None = None, terminos: str | None = None, patrones: list | None = None,
           defecto: bool = False) -> dict:
    o = {"codigo": codigo, "etiqueta": etiqueta}
    pats = list(patrones or [])
    if re_:
        pats.append({"re": re_, "en": en, "prioridad": prioridad})
    if defecto:
        pats.append({"defecto": True, "prioridad": 99})
    if pats:
        o["patrones"] = pats
    if texto:
        o["texto_aduana"] = texto
    if implica:
        o["implica"] = implica
    if bloqueo:
        o["bloqueo"] = bloqueo
    if terminos:
        o["terminos"] = terminos
    return o


def bloqueo(mensaje: str, **kw) -> dict:
    return {"condiciones": si(**kw), "mensaje": mensaje}


def ambitos(categorias, modo: str = "SHOW", condicion: list | None = None, prioridad: int = 500) -> list[dict]:
    return [{"tipo_ambito": "CATEGORY", "codigo_ambito": c, "modo": modo, "condicion": condicion, "prioridad": prioridad} for c in categorias]


def atributo(codigo: str, etiqueta: str, tipo: str = "select", opciones: list | None = None, ambitos_: list | None = None, *,
             seccion: str = "caracteristicas", ayuda: str | None = None, derivacion: dict | None = None, defecto=None,
             patrones: list | None = None, texto: dict | list | None = None, orden: int = 0, control: str | None = None,
             informativo: bool = False, unidad: str | None = None, bloqueo_: list | None = None) -> dict:
    a = {"codigo": codigo, "etiqueta": etiqueta, "tipo_dato": tipo, "seccion": seccion, "orden": orden,
         "opciones": [dict(o, orden=o.get("orden", (i + 1) * 10)) for i, o in enumerate(opciones or [])],
         "ambitos": ambitos_ or []}
    for k, v in (("ayuda", ayuda), ("derivacion", derivacion), ("valor_defecto", defecto), ("patrones", patrones),
                 ("texto_aduana", texto), ("control", control), ("unidad", unidad), ("bloqueo", bloqueo_)):
        if v is not None:
            a[k] = v
    if informativo:
        a["informativo"] = True
    return a


def categoria(codigo: str, nombre: str, *, corto: str, aduana: str, grupo: str, dominio: str, capitulos: list, re_: str,
              prioridad: int = 40, alias: str = "", plantilla: dict | None = None, terminos: str | None = None, orden: int = 0) -> dict:
    c = {"codigo": codigo, "nombre": nombre, "nombre_corto": corto, "nombre_aduana": aduana, "grupo": grupo, "familia": codigo,
         "dominio": dominio, "capitulos": capitulos, "alias": alias, "orden": orden,
         "patrones": [{"re": re_, "prioridad": prioridad}]}
    if plantilla:
        c["plantilla_aduana"] = plantilla
    if terminos:
        c["terminos"] = terminos
    return c


def caso(categoria_: str, codigo: str, **hechos) -> dict:
    return {"hechos": {"categoria": categoria_, **{k.replace("__", "."): v for k, v in hechos.items()}}, "codigo": codigo}


# ---- Validación y escritura -----------------------------------------------------------------
def validar(fam: dict, atributos_comunes: dict) -> None:
    attrs = {a["codigo"]: a for a in fam.get("atributos", [])} | atributos_comunes
    cats = {c["codigo"] for c in fam["categorias"]}
    errores = []
    for r in fam["reglas"]:
        if r["categoria"] not in cats:
            errores.append(f"{r['codigo']}: category {r['categoria']} is not in the family")
        a = r["accion"]
        for c in a.get("codigos") or []:
            if not existe(c):
                errores.append(f"{r['codigo']}: code {c} is not in the official tree")
        for k, c in (a.get("mapa") or {}).items():
            if c and not existe(c):
                errores.append(f"{r['codigo']}: map {k} → {c} is not in the official tree")
        for c in r["condiciones"]:
            at = attrs.get(c["campo"])
            if c["campo"] in ("categoria", "dominio"):
                continue
            if not at:
                errores.append(f"{r['codigo']}: field {c['campo']} is not an attribute")
                continue
            if at["tipo_dato"] in ("select", "multi_select") and c["operador"] in ("EQUAL", "IN"):
                vals = c["valor"] if isinstance(c["valor"], list) else [c["valor"]]
                validas = {o["codigo"] for o in at["opciones"]}
                for v in vals:
                    if v not in validas and v != "":
                        errores.append(f"{r['codigo']}: {c['campo']}={v} is not an option ({sorted(validas)})")
    for x in fam.get("casos", []):
        if not existe(x["codigo"]):
            errores.append(f"case {x}: code is not in the official tree")
    for c in fam["categorias"]:
        try:
            re.compile(c["patrones"][0]["re"])
        except re.error as e:
            errores.append(f"category {c['codigo']}: bad pattern ({e})")
    if errores:
        raise SystemExit("\n".join(errores))


def escribir(nombre: str, datos: dict) -> Path:
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / f"{nombre}.json"
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return ruta


def partidas(desde: str, hasta: str) -> list[str]:
    """Las partidas (4 dígitos) del árbol vigente entre dos, inclusive."""
    return sorted({k[:4] for k in TEXTO if len(k) >= 4 and desde <= k[:4] <= hasta})
