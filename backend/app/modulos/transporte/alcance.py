"""Qué embarques ve cada usuario: los de los centros de sus sociedades y de
sus transportistas (sin límite si su rol no los acota)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Centro, Embarque, Sociedad, Usuario
from app.modulos.acceso.permisos import sociedades_de, transportistas_de


def centros_de(db: Session, user: Usuario) -> set[str] | None:
    """Centros de las sociedades del usuario (None: sin límite)."""
    soc = sociedades_de(user)
    if not soc:
        return None
    return {c for (c,) in db.execute(select(Centro.codigo).join(Sociedad, Sociedad.id == Centro.sociedad_id)
                                     .where(Sociedad.codigo.in_(soc)))}


def en_alcance(db: Session, user: Usuario, e: Embarque) -> bool:
    centros, transportistas = centros_de(db, user), transportistas_de(user)
    return not ((centros is not None and e.centro not in centros)
                or (transportistas is not None and e.transportista_id not in transportistas))


def condiciones_alcance(db: Session, user: Usuario) -> list:
    """Condiciones SQL que limitan los embarques al alcance del usuario."""
    cond = []
    centros, transportistas = centros_de(db, user), transportistas_de(user)
    if centros is not None:
        cond.append(Embarque.centro.in_(centros))
    if transportistas is not None:
        cond.append(Embarque.transportista_id.in_(transportistas))
    return cond
