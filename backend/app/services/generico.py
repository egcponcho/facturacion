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
import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import plano
from ..models import DominioClasificacion, NodoArancel, Usuario
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
    """Compatibilidad: la ruta genérica usa el motor único (motor_clasificacion)."""
    from .motor_clasificacion import clasificar

    exigir(user, "producto.ver")
    r = clasificar(db, texto, dominio, None, respuestas, paises=False, limite=limite)
    return {**r, "reglas": [t["regla"] for t in r["reglas"]]}


def dominios_ficha(db: Session) -> list[dict]:
    """Dominios que la ficha genérica ofrece (químicos, materias primas…), más «otro»."""
    return [{"codigo": d.codigo, "nombre": d.nombre, "descripcion": d.descripcion}
            for d in db.scalars(select(DominioClasificacion).where(DominioClasificacion.activo.is_(True)).order_by(DominioClasificacion.orden))
            if d.codigo not in ("APPAREL", "FOOTWEAR", "ACCESSORIES_MERCH")]

