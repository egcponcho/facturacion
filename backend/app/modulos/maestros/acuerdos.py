"""Acuerdos comerciales vigentes para los países destino.

Referencia para saber, según el país de origen del producto, a qué destinos
entra con preferencia arancelaria y qué prueba de origen (CO) se pide. Es una
base de consulta: se edita en Master data → Trade agreements. La lista de
ejemplo es de la demostración (data/demo/acuerdos_demo.json), no de una
fuente oficial.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import AcuerdoComercial


def acuerdos_contexto(db: Session) -> list[dict]:
    return [{"codigo": x.codigo, "nombre": x.nombre, "origenes": [p.codigo for p in x.origenes],
             "destinos": [p.codigo for p in x.destinos],
             "prueba": x.prueba, "nota": x.nota}
            for x in db.scalars(select(AcuerdoComercial).where(AcuerdoComercial.activo.is_(True))
                                .order_by(AcuerdoComercial.codigo))]
