"""Ruta genérica de clasificación: para productos fuera de la ficha de ropa,
calzado y accesorios (químicos, materias primas y cualquier otro).

Sigue las reglas del sistema (paquete 02):
- R-SYS-001: solo capítulos activos y habilitados para clasificar; los de
  «solo manual» no generan candidatos automáticos.
- R-SYS-003: el nombre y la descripción generan candidatos, nunca confirman.
- R-SYS-004: preguntar solo lo que distingue a los candidatos o es obligatorio.
- R-SYS-005: si quedan varios candidatos plausibles, revisión del especialista.
- R-SYS-009: el dominio (químicos, materias primas…) ordena, no obliga ni
  excluye un capítulo.

Los candidatos salen del texto oficial del árbol arancelario (NodoArancel) de
la versión vigente; el resultado siempre queda como sugerencia.
"""
import math
import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import plano
from ..models import AtributoDef, ControlCapitulo, DominioClasificacion, NodoArancel, Usuario, VersionDataset
from .arbol import VERSION_SAC, formato
from .atributos import _dict as atributo_dict
from .common import exigir

VACIAS = set("""de del la el los las y o en con sin para por que su sus sus un una uno al a e lo se otros otras demas los las
the and or of for with without in on to from by an as other others its their this that are is be not""".split())


def raiz(p: str) -> str:
    """Raíz simple (plural español o inglés) para comparar palabras."""
    if len(p) > 5 and p.endswith("es"):
        return p[:-2]
    if len(p) > 4 and p.endswith("s"):
        return p[:-1]
    return p


def palabras(texto: str) -> list[str]:
    return [raiz(p) for p in re.split(r"[^a-z0-9]+", plano(texto or "")) if len(p) >= 3 and p not in VACIAS and not p.isdigit()]


@lru_cache(maxsize=4)
def _indice(version_id: int, _marca: int) -> tuple:
    """Subpartidas e incisos de la versión con sus palabras (en memoria)."""
    from ..db import SessionLocal

    with SessionLocal() as db:
        filas = db.execute(select(NodoArancel.codigo_norm, NodoArancel.nivel, NodoArancel.descripcion, NodoArancel.dai)
                           .where(NodoArancel.version_id == version_id, NodoArancel.nivel.in_(("SUBPARTIDA", "INCISO")))).all()
    nodos = [(c, n, d, dai, set(palabras(d))) for c, n, d, dai in filas]
    df: dict[str, int] = {}
    for *_, ps in nodos:
        for p in ps:
            df[p] = df.get(p, 0) + 1
    return nodos, df


def candidatos(db: Session, user: Usuario, texto: str, dominio: str | None = None, respuestas: dict | None = None,
               limite: int = 8) -> dict:
    exigir(user, "producto.ver")
    v = db.scalar(select(VersionDataset).where(VersionDataset.codigo == VERSION_SAC))
    if not v:
        return {"candidatos": [], "preguntas": [], "confianza": "low", "revision": True, "reglas": []}
    # Texto del producto y de las respuestas (las opciones aportan sus sinónimos)
    respuestas = respuestas or {}
    attrs = {a.codigo: a for a in db.scalars(select(AtributoDef).options(selectinload(AtributoDef.opciones), selectinload(AtributoDef.ambitos))
                                            .where(AtributoDef.origen != "MOTOR", AtributoDef.activo.is_(True)))}
    extra = []
    for k, val in respuestas.items():
        a = attrs.get(k)
        if not a or val in (None, "", [], False):
            continue
        for x in (val if isinstance(val, list) else [val]):
            o = next((o for o in a.opciones if o.codigo == x), None)
            extra.append(f"{o.etiqueta} {o.alias or ''}" if o else str(x))
    terminos = list(dict.fromkeys(palabras(f"{texto} {' '.join(extra)}")))
    caps = {c.capitulo: c for c in db.scalars(select(ControlCapitulo))}
    habilitados = {k for k, c in caps.items() if c.activo and c.clasificacion and not c.archivado and not c.solo_manual}
    peso_dom: dict[str, float] = {}
    if dominio:
        d = db.scalar(select(DominioClasificacion).where(DominioClasificacion.codigo == dominio))
        for dc in (d.capitulos if d else []):
            if dc.habilitado:
                peso_dom[dc.capitulo] = 1.5 if dc.relevancia == "PRIMARY" else 1.2
    nodos, df = _indice(v.id, int((v.importado_en.timestamp() if v.importado_en else 0)))
    total = max(len(nodos), 1)
    idf = {t: math.log(1 + total / (1 + df.get(t, 0))) for t in terminos}
    por_sub: dict[str, dict] = {}
    if terminos:
        for cod, nivel, desc, dai, ps in nodos:
            if cod[:2] not in habilitados:
                continue
            hechos = [t for t in terminos if t in ps or (len(t) >= 5 and any(p.startswith(t) for p in ps))]
            if not hechos:
                continue
            puntos = sum(idf[t] for t in hechos) * peso_dom.get(cod[:2], 1.0)
            sub = cod[:6]
            x = por_sub.setdefault(sub, {"codigo": sub, "puntaje": 0.0, "terminos": set(), "incisos": []})
            if puntos > x["puntaje"]:
                x["puntaje"] = puntos
            x["terminos"].update(hechos)
            if nivel == "INCISO":
                x["incisos"].append({"codigo": cod, "codigo_txt": formato(cod), "descripcion": desc.split(" — ")[-1], "dai": dai,
                                     "puntaje": round(puntos, 2)})
    lista = sorted(por_sub.values(), key=lambda x: -x["puntaje"])[:limite]
    textos = dict(db.execute(select(NodoArancel.codigo_norm, NodoArancel.descripcion).where(
        NodoArancel.version_id == v.id, NodoArancel.codigo_norm.in_([x["codigo"] for x in lista]))).all()) if lista else {}
    out = []
    for x in lista:
        cap = caps.get(x["codigo"][:2])
        out.append({"codigo": x["codigo"], "codigo_txt": formato(x["codigo"]), "descripcion": textos.get(x["codigo"], ""),
                    "capitulo": x["codigo"][:2], "titulo_capitulo": cap.titulo if cap else "", "puntaje": round(x["puntaje"], 2),
                    "terminos": sorted(x["terminos"]), "dominio": peso_dom.get(x["codigo"][:2]) is not None,
                    "incisos": sorted(x["incisos"], key=lambda i: (-i["puntaje"], i["codigo"]))[:6]})
    # Confianza: nunca alta por texto; media si el primero se distingue claramente
    confianza = "low"
    if len(out) == 1 or (len(out) > 1 and out[0]["puntaje"] >= 1.5 * out[1]["puntaje"] and len(out[0]["terminos"]) >= 2):
        confianza = "medium"
    return {"candidatos": out, "terminos": terminos, "confianza": confianza, "revision": True,
            "preguntas": preguntas(attrs, dominio, [c["codigo"] for c in out], respuestas),
            "reglas": ["R-SYS-001", "R-SYS-003", "R-SYS-004", "R-SYS-005", "R-SYS-009"]}


def preguntas(attrs: dict, dominio: str | None, codigos: list[str], respuestas: dict) -> list[dict]:
    """Atributos a pedir: los obligatorios y los que aplican al dominio o a los
    capítulos/partidas de los candidatos; primero los que más distinguen."""
    caps = {c[:2] for c in codigos}
    partidas = {c[:4] for c in codigos}
    subs = set(codigos)
    out = []
    for a in attrs.values():
        mejor = None
        for x in a.ambitos:
            if not x.activo or x.modo == "HIDE":
                continue
            toca = ((x.tipo_ambito == "SYSTEM") or (x.tipo_ambito == "DOMAIN" and x.codigo_ambito == dominio)
                    or (x.tipo_ambito == "CHAPTER" and x.codigo_ambito in caps) or (x.tipo_ambito == "HEADING" and x.codigo_ambito in partidas)
                    or (x.tipo_ambito == "SUBHEADING" and x.codigo_ambito in subs))
            if not toca:
                continue
            # Lo propio de los candidatos distingue más que lo general
            extra = {"SUBHEADING": 300, "HEADING": 200, "CHAPTER": 100}.get(x.tipo_ambito, 0)
            clave = (x.modo == "REQUIRE", x.prioridad + extra)
            if not mejor or clave > mejor[0]:
                mejor = (clave, x)
        if mejor:
            d = atributo_dict(a, True)
            out.append({**d, "modo": mejor[1].modo, "prioridad": mejor[0][1], "nota_ambito": mejor[1].nota,
                        "respondida": respuestas.get(a.codigo) not in (None, "", [])})
    return sorted(out, key=lambda d: (d["modo"] != "REQUIRE", -d["prioridad"], d["orden"]))


def dominios_ficha(db: Session) -> list[dict]:
    """Dominios que la ficha genérica ofrece (químicos, materias primas…), más «otro»."""
    return [{"codigo": d.codigo, "nombre": d.nombre, "descripcion": d.descripcion}
            for d in db.scalars(select(DominioClasificacion).where(DominioClasificacion.activo.is_(True)).order_by(DominioClasificacion.orden))
            if d.codigo not in ("APPAREL", "FOOTWEAR", "ACCESSORIES_MERCH")]

