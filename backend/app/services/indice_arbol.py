"""Índice de palabras del texto oficial del árbol arancelario: el motor único
(/clasificacion/sesion) lo usa para proponer candidatos de cualquier dominio.
Solo propone códigos que existen en la versión vigente; nunca confirma uno.

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
import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import plano
from ..models import DominioClasificacion, NodoArancel

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


def prefijo(t: str) -> str:
    """La parte de una palabra que se compara con el texto oficial: sin su
    terminación (taladro → talad, para taladros / taladradoras; perforar →
    perfor, para perforadoras). Las palabras cortas se comparan enteras."""
    if len(t) >= 9:
        return t[:-3]
    if len(t) >= 6:
        return t[:-2]
    return t


def alcance(terminos: list[str], df: dict, sinonimos: dict | None = None) -> dict[str, set]:
    """Para cada término, las palabras del texto oficial que cuentan como él:
    las que empiezan con su prefijo o con el de una palabra equivalente
    (sinónimos de búsqueda, p. ej. drill → taladro). Un término cuenta una
    sola vez aunque coincida por varias vías."""
    out = {}
    for t in terminos:
        variantes = {t, *((sinonimos or {}).get(t) or [])}
        ws = set(variantes) & set(df)
        for v in variantes:
            p = prefijo(v)
            if len(p) >= 4:
                ws |= {w for w in df if w.startswith(p)}
        out[t] = ws
    return out


def sinonimos_busqueda(db: Session) -> dict[str, list[str]]:
    """Palabra (en cualquier idioma) → palabras equivalentes del texto oficial."""
    from ..models import SinonimoBusqueda

    out: dict[str, list[str]] = {}
    for x in db.scalars(select(SinonimoBusqueda).where(SinonimoBusqueda.activo.is_(True))):
        for k in palabras(x.palabra):
            out.setdefault(k, [])
            out[k] += [w for w in palabras(x.equivale) if w not in out[k]]
    return out


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


def dominios_ficha(db: Session) -> list[dict]:
    """Dominios activos que ofrece la ficha dinámica (todos: salen de la configuración)."""
    return [{"codigo": d.codigo, "nombre": d.nombre, "descripcion": d.descripcion}
            for d in db.scalars(select(DominioClasificacion).where(DominioClasificacion.activo.is_(True), DominioClasificacion.estado != "BORRADOR")
                                .order_by(DominioClasificacion.orden))]

