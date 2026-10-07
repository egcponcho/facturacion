"""Acuerdos comerciales vigentes para los países destino.

Referencia para saber, según el país de origen del producto, a qué destinos
entra con preferencia arancelaria y qué prueba de origen (CO) se pide. Es una
base de consulta: se edita en Master data → Trade agreements. La lista de
ejemplo es de la demostración (data/demo/acuerdos_demo.json), no de una
fuente oficial.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AcuerdoComercial

def _lista(txt: str | None) -> list[str]:
    return [x.strip().upper() for x in (txt or "").split(",") if x.strip()]


def acuerdos_contexto(db: Session) -> list[dict]:
    return [{"codigo": x.codigo, "nombre": x.nombre, "origenes": _lista(x.origenes), "destinos": _lista(x.destinos),
             "prueba": x.prueba, "nota": x.nota}
            for x in db.scalars(select(AcuerdoComercial).where(AcuerdoComercial.activo.is_(True))
                                .order_by(AcuerdoComercial.codigo))]


def acuerdos_para(db: Session, origen: str | None, destinos: list[str]) -> dict[str, list[dict]]:
    """Por país destino, los acuerdos que cubren el origen dado."""
    origen = (origen or "").upper()
    res: dict[str, list[dict]] = {d: [] for d in destinos}
    for a in acuerdos_contexto(db):
        if origen in a["origenes"]:
            for d in destinos:
                if d in a["destinos"]:
                    res[d].append(a)
    return res
