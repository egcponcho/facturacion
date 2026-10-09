"""Rutas de consulta de los lead times.
"""
from fastapi import APIRouter

from app.core.api import Db, User
from app.modulos.acceso.permisos import exigir

router = APIRouter()


@router.get("/leadtimes/ambitos")
def leadtimes_ambitos(db: Db, user: User):
    """Regiones, países y puertos (con su país y región) para elegir un ámbito."""
    from sqlalchemy import select

    from app.modelos import Pais, Puerto, RegionLeadTime
    from app.modulos.transporte import reglas_lt

    exigir(user, "catalogos.ver")
    paises = {p.codigo: p for p in db.scalars(select(Pais).order_by(Pais.nombre))}
    return {
        "regiones": [{"valor": r.codigo, "texto": r.nombre} for r in db.scalars(select(RegionLeadTime).order_by(RegionLeadTime.nombre))],
        "paises": [{"valor": p.codigo, "texto": p.nombre, "region": p.region, "sub": p.codigo} for p in paises.values()],
        "puertos": [{"valor": p.codigo, "texto": p.nombre, "pais": p.pais,
                     "sub": f"{p.codigo} · {paises[p.pais].nombre if p.pais in paises else p.pais}"}
                    for p in db.scalars(select(Puerto).order_by(Puerto.nombre))],
        "pasos": list(reglas_lt.catalogo(db).values()),
        "hitos": [{"valor": h, "texto": t} for h, t in reglas_lt.HITOS],
    }


@router.get("/leadtimes/efectivo")
def leadtimes_efectivo(db: Db, user: User, region: str | None = None, pais: str | None = None,
                       puerto: str | None = None, sin_regla: int | None = None, modo: str | None = None):
    """Lead time efectivo de un ámbito tras aplicar la herencia, con la procedencia de cada paso."""
    from app.modulos.transporte import reglas_lt

    exigir(user, "catalogos.ver")
    return reglas_lt.efectivo(db, region or None, pais or None, puerto or None, sin_regla, modo=modo or None)
