"""Árbol arancelario oficial versionado (NodoArancel).

La versión regional SAC-2025-V6 se arma desde los datos SIECA del repositorio
(ACI, VII Enmienda, versión 6 de agosto 2025): capítulos (control de
capítulos), partidas y subpartidas (sac_oficial.json) e incisos de 10 dígitos
con su DAI (aci_incisos.json) de los 96 capítulos, no solo de los que hoy usa
el motor. Se guarda el checksum de los archivos fuente en la versión.
"""
import hashlib
import re
from pathlib import Path

from sqlalchemy import func, insert, or_, select
from sqlalchemy.orm import Session

from ..models import ControlCapitulo, IncisoNacional, NodoArancel, NotaSAC, PaisArancel, Usuario, VersionDataset, ahora
from .common import ErrorNegocio, exigir, filtro_texto

DATOS = Path(__file__).resolve().parent.parent / "data"
VERSION_SAC = "SAC-2025-V6"
NIVELES = {2: "CAPITULO", 4: "PARTIDA", 6: "SUBPARTIDA", 8: "INCISO", 10: "INCISO", 12: "INCISO"}
NOMBRE_NIVEL = {"CAPITULO": "Chapter", "PARTIDA": "Heading", "SUBPARTIDA": "Subheading", "INCISO": "Tariff line"}


def digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def formato(c: str) -> str:
    """64 · 6404 · 6404.19 · 6404.19.90 · 6404.19.90.00 (y más pares de dígitos)."""
    c = digitos(c)
    if len(c) <= 4:
        return c
    return ".".join([c[:4]] + [c[i:i + 2] for i in range(4, len(c), 2)])


def _leer(nombre: str):
    import json

    return json.loads((DATOS / nombre).read_text(encoding="utf-8"))


def checksum(*nombres: str) -> str:
    h = hashlib.sha256()
    for n in nombres:
        h.update((DATOS / n).read_bytes())
    return h.hexdigest()


def cargar_sac(db: Session, version: str = VERSION_SAC) -> int:
    """Carga el árbol regional de la versión (si aún no está cargado)."""
    v = db.scalar(select(VersionDataset).where(VersionDataset.codigo == version))
    if not v:
        raise ErrorNegocio(f"Version {version} does not exist. Load the official catalogs first.", 422, "validacion")
    if db.scalar(select(func.count()).select_from(NodoArancel).where(NodoArancel.version_id == v.id)):
        return 0
    base = {"version_id": v.id, "nomenclatura": "SAC", "pais": None, "fuente_id": v.fuente_id,
            "vigente_desde": v.vigente_desde, "estado": "PUBLICADO", "activo": True}
    total = 0

    def ids_de(largo: int) -> dict[str, int]:
        return dict(db.execute(select(NodoArancel.codigo_norm, NodoArancel.id).where(
            NodoArancel.version_id == v.id, func.length(NodoArancel.codigo_norm) == largo)).all())

    caps = {c.capitulo: c.titulo for c in db.scalars(select(ControlCapitulo))}
    filas = [{**base, "nivel": "CAPITULO", "codigo": c, "codigo_norm": c, "padre_id": None, "descripcion": t,
              "texto_propio": t[:400]} for c, t in sorted(caps.items())]
    db.execute(insert(NodoArancel), filas)
    total += len(filas)
    sac = _leer("sac_oficial.json")
    for largo, padre_largo in ((4, 2), (6, 4)):
        padres = ids_de(padre_largo) or ids_de(2)
        filas = []
        for x in sac:
            c = digitos(x["codigo"])
            if len(c) != largo:
                continue
            p = padres.get(c[:padre_largo]) or ids_de(2).get(c[:2])
            propio = x["descripcion"].split(" — ")[-1]
            filas.append({**base, "nivel": NIVELES[largo], "codigo": formato(c), "codigo_norm": c, "padre_id": p,
                          "descripcion": x["descripcion"], "texto_propio": propio[:400]})
        if filas:
            db.execute(insert(NodoArancel), filas)
            total += len(filas)
    seis, cuatro, dos = ids_de(6), ids_de(4), ids_de(2)
    filas = []
    for x in _leer("aci_incisos.json"):
        c = digitos(x["codigo"])
        p = seis.get(c[:6]) or cuatro.get(c[:4]) or dos.get(c[:2])
        filas.append({**base, "nivel": "INCISO", "codigo": formato(c), "codigo_norm": c, "padre_id": p,
                      "descripcion": x["descripcion"], "texto_propio": (x.get("propio") or x["descripcion"])[:400],
                      "dai": x.get("dai_txt")})
    db.execute(insert(NodoArancel), filas)
    total += len(filas)
    # Hijos directos de cada nodo (para mostrar el árbol sin contar en cada consulta)
    cuentas = dict(db.execute(select(NodoArancel.padre_id, func.count()).where(
        NodoArancel.version_id == v.id, NodoArancel.padre_id.is_not(None)).group_by(NodoArancel.padre_id)).all())
    for nid, n in cuentas.items():
        db.execute(NodoArancel.__table__.update().where(NodoArancel.id == nid).values(hojas=n))
    v.checksum = checksum("sac_oficial.json", "aci_incisos.json")
    v.importado_en = ahora()
    db.flush()
    return total


# ---- Consulta --------------------------------------------------------------------
def _version(db: Session, codigo: str | None) -> VersionDataset:
    v = db.scalar(select(VersionDataset).where(VersionDataset.codigo == (codigo or VERSION_SAC)))
    if not v:
        raise ErrorNegocio("The tariff version does not exist.", 404, "no_encontrado")
    return v


def _fila(n: NodoArancel, caps: dict | None = None) -> dict:
    d = {"id": n.id, "nivel": n.nivel, "codigo": n.codigo, "codigo_norm": n.codigo_norm, "descripcion": n.descripcion,
         "texto": n.texto_propio or n.descripcion, "dai": n.dai, "hijos": n.hojas, "padre_id": n.padre_id,
         "activo": n.activo, "estado": n.estado}
    if caps is not None:
        c = caps.get(n.codigo_norm[:2])
        d["capitulo_habilitado"] = bool(c and c.activo and c.clasificacion)
    return d


def hijos(db: Session, user: Usuario, padre_id: int | None, version: str | None = None) -> dict:
    exigir(user, "producto.ver")
    v = _version(db, version)
    caps = {c.capitulo: c for c in db.scalars(select(ControlCapitulo))}
    q = select(NodoArancel).where(NodoArancel.version_id == v.id)
    q = q.where(NodoArancel.padre_id == padre_id) if padre_id else q.where(NodoArancel.nivel == "CAPITULO")
    return {"version": v.codigo, "items": [_fila(n, caps) for n in db.scalars(q.order_by(NodoArancel.codigo_norm))]}


def _ancestros(db: Session, n: NodoArancel) -> list[NodoArancel]:
    out, p = [], n.padre_id
    while p:
        x = db.get(NodoArancel, p)
        if not x:
            break
        out.append(x)
        p = x.padre_id
    return list(reversed(out))


def buscar(db: Session, user: Usuario, q: str, version: str | None = None, limite: int = 60) -> dict:
    """Búsqueda inteligente: por código (con o sin puntos; varios códigos
    pegados) o por palabras del texto oficial en cualquier orden."""
    exigir(user, "producto.ver")
    v = _version(db, version)
    q = (q or "").strip()
    if not q:
        return {"items": [], "total": 0}
    consulta = select(NodoArancel).where(NodoArancel.version_id == v.id)
    terminos = [t for t in re.split(r"[\s,;|]+", q) if t]
    if all(re.fullmatch(r"[\d.\-]+", t) for t in terminos):
        consulta = consulta.where(or_(*[NodoArancel.codigo_norm.startswith(digitos(t)) for t in terminos if digitos(t)]))
    else:
        consulta = consulta.where(filtro_texto(q, lambda p: [NodoArancel.descripcion.ilike(p), NodoArancel.codigo.ilike(p)]))
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    nodos = list(db.scalars(consulta.order_by(func.length(NodoArancel.codigo_norm), NodoArancel.codigo_norm).limit(limite)))
    caps = {c.capitulo: c for c in db.scalars(select(ControlCapitulo))}
    return {"total": total, "items": [{**_fila(n, caps), "ruta": [a.codigo for a in _ancestros(db, n)]} for n in nodos]}


def nodo(db: Session, user: Usuario, nodo_id: int) -> dict:
    """Detalle: ruta, hijos, notas legales del capítulo y códigos nacionales por país."""
    exigir(user, "producto.ver")
    n = db.get(NodoArancel, nodo_id)
    if not n:
        raise ErrorNegocio("The tariff node does not exist.", 404, "no_encontrado")
    caps = {c.capitulo: c for c in db.scalars(select(ControlCapitulo))}
    cap = caps.get(n.codigo_norm[:2])
    hijos_ = list(db.scalars(select(NodoArancel).where(NodoArancel.padre_id == n.id).order_by(NodoArancel.codigo_norm)))
    notas = [{"id": x.id, "ambito": x.ambito, "codigo": x.codigo, "numero": x.numero, "texto": x.texto}
             for x in db.scalars(select(NotaSAC).where(NotaSAC.activo.is_(True)).order_by(NotaSAC.id))
             if x.ambito != "reglas" and n.codigo_norm[:2] in (x.capitulos or [])
             and (x.ambito != "explicativa" or n.codigo_norm.startswith(digitos(x.codigo)))][:40]
    nacionales: dict[str, list] = {}
    if len(n.codigo_norm) >= 6:
        pref = n.codigo_norm
        for x in db.scalars(select(IncisoNacional).where(IncisoNacional.sub6 == pref[:6], IncisoNacional.activo.is_(True))
                            .order_by(IncisoNacional.pais, IncisoNacional.codigo)):
            if digitos(x.codigo).startswith(pref) or len(pref) == 6:
                nacionales.setdefault(x.pais, []).append({"codigo": formato(x.codigo), "descripcion": x.descripcion,
                                                          "dai": x.dai, "fuente": x.fuente})
    v = db.get(VersionDataset, n.version_id)
    return {
        **_fila(n, caps), "nombre_nivel": NOMBRE_NIVEL.get(n.nivel, n.nivel),
        "ruta": [_fila(a) for a in _ancestros(db, n)],
        "hijos_lista": [_fila(h, caps) for h in hijos_],
        "capitulo": {"capitulo": cap.capitulo, "titulo": cap.titulo, "activo": cap.activo, "clasificacion": cap.clasificacion,
                     "candidato_auto": cap.candidato_auto, "solo_manual": cap.solo_manual} if cap else None,
        "version": {"codigo": v.codigo, "etiqueta": v.etiqueta, "estado": v.estado,
                    "fuente": v.fuente.codigo if v.fuente else None, "checksum": v.checksum} if v else None,
        "notas": notas,
        "paises": [{"iso": p.iso, "nombre": p.nombre, "codigos": nacionales.get(p.iso, [])}
                   for p in db.scalars(select(PaisArancel).where(PaisArancel.activo.is_(True)).order_by(PaisArancel.orden))],
    }


def resumen(db: Session, user: Usuario, version: str | None = None) -> dict:
    exigir(user, "producto.ver")
    v = _version(db, version)
    por = dict(db.execute(select(NodoArancel.nivel, func.count()).where(NodoArancel.version_id == v.id)
                          .group_by(NodoArancel.nivel)).all())
    return {"version": v.codigo, "etiqueta": v.etiqueta, "checksum": v.checksum, "importado_en": v.importado_en,
            "niveles": por, "versiones": [{"codigo": x.codigo, "etiqueta": x.etiqueta} for x in db.scalars(
                select(VersionDataset).where(VersionDataset.id.in_(select(NodoArancel.version_id).distinct())))]}
