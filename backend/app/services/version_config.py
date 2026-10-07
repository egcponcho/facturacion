"""Versión de la configuración del motor de clasificación.

Cada cambio guardado en la configuración (atributos, opciones, ámbitos,
categorías, clases de material, vocabulario, palabras clave, dominios y
reglas) sube un contador en la base, en la misma transacción. Con él:

- cada proceso del servidor guarda un solo catálogo en memoria y lo vuelve a
  leer en cuanto otro proceso (u otro servidor) cambia la configuración: basta
  leer una fila por petición;
- la evidencia de cada clasificación dice con qué versión de la configuración
  se hizo.

Una sesión con cambios sin confirmar nunca deja su catálogo en la memoria
compartida: si la transacción se deshace, nadie lo ve.
"""
from sqlalchemy import event, insert, select, update
from sqlalchemy.orm import Session

from ..models import Meta

CLAVE = "config.version"
MODELOS = {"AtributoDef", "AtributoOpcion", "AtributoAmbito", "CategoriaProducto", "PalabraClave", "SinonimoMaterial",
           "ClaseMaterial", "SinonimoBusqueda", "DominioClasificacion", "DominioCapitulo", "ReglaClasificacion", "CondicionRegla"}


def actual(db: Session) -> int:
    v = db.scalar(select(Meta.valor).where(Meta.clave == CLAVE))
    return int(v) if v and v.isdigit() else 0


def con_cambios(db: Session) -> bool:
    """La sesión cambió la configuración y aún no lo confirma."""
    return bool(db.info.get("config_sucia"))


@event.listens_for(Session, "after_flush")
def _subir(sesion, _contexto) -> None:
    if not any(type(o).__name__ in MODELOS for o in (*sesion.new, *sesion.dirty, *sesion.deleted)):
        return
    sesion.info.pop("catalogo", None)
    if sesion.info.get("config_sucia"):
        return  # una sola subida por transacción
    con = sesion.connection()
    v = con.execute(select(Meta.valor).where(Meta.clave == CLAVE)).scalar()
    if v is None:
        con.execute(insert(Meta).values(clave=CLAVE, valor="1"))
    else:
        con.execute(update(Meta).where(Meta.clave == CLAVE).values(valor=str(int(v or 0) + 1)))
    sesion.info["config_sucia"] = True


@event.listens_for(Session, "after_commit")
def _confirmada(sesion) -> None:
    sesion.info.pop("config_sucia", None)


@event.listens_for(Session, "after_rollback")
def _deshecha(sesion) -> None:
    if sesion.info.pop("config_sucia", None):
        sesion.info.pop("catalogo", None)
