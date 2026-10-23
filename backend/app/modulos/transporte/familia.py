"""La sección de logística de la familia: los días que sus productos necesitan
además del transporte (inspección, etiquetado, permisos), que se suman a la
fecha estimada en tienda. Vacío: los de la familia que la contiene."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import FamiliaLogistica, Usuario
from app.modulos.catalogo import servicio as catalogo
from app.modulos.catalogo.secciones import SeccionFamilia, registrar_seccion_familia
from app.modulos.comun.historial import registrar

MAX_DIAS = 365


def dias_extra(db: Session) -> dict[int, int]:
    """{nodo del árbol: días extra efectivos}: los suyos o los de la familia más cercana que los tenga."""
    propios = dict(db.execute(select(FamiliaLogistica.familia_id, FamiliaLogistica.dias_extra)
                              .where(FamiliaLogistica.dias_extra.is_not(None))).all())
    return {fid: next((propios[x] for x in reversed(f.ruta_ids) if x in propios), 0)
            for fid, f in catalogo.familias(db).items()}


def _leer(db: Session, familia_id: int) -> dict:
    fila = db.get(FamiliaLogistica, familia_id)
    return {"dias_extra": fila.dias_extra if fila else None, "efectivos": dias_extra(db).get(familia_id, 0)}


def _guardar(db: Session, user: Usuario, familia_id: int, datos: dict) -> dict:
    if catalogo.nodo(db, familia_id) is None:
        raise ErrorNegocio("The family does not exist.", 404, "no_encontrado")
    v = datos.get("dias_extra")
    if v in (None, ""):
        v = None
    else:
        try:
            v = int(v)
        except (TypeError, ValueError):
            v = -1
        if not 0 <= v <= MAX_DIAS:
            raise ErrorNegocio("Check the extra days.", 422, "validacion",
                               [{"campo": "dias_extra", "mensaje": f"Write a whole number from 0 to {MAX_DIAS}."}])
    fila = db.get(FamiliaLogistica, familia_id)
    antes = fila.dias_extra if fila else None
    if fila is None:
        fila = FamiliaLogistica(familia_id=familia_id)
        db.add(fila)
    fila.dias_extra = v
    db.flush()
    if antes != v:
        registrar(db, user, "grupo_producto", familia_id, "logistica", {"dias_extra": [antes, v]})
    return _leer(db, familia_id)


registrar_seccion_familia(SeccionFamilia(
    clave="logistica", nombre="Logistics", orden=30, leer=_leer, guardar=_guardar,
    permisos_ver=("catalogos.ver", "transporte.gestionar"), permisos_editar=("catalogos.editar",)))
