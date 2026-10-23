"""La sección de empaque de la familia: las reglas que eligen la receta de
empaque de sus productos. Se ven aquí y se cambian en las reglas de empaque
(una regla puede ir a toda la empresa, una familia, un producto o un artículo)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modelos import RecetaEmpaque, ReglaEmpaque
from app.modulos.catalogo.secciones import SeccionFamilia, registrar_seccion_familia


def _leer(db: Session, familia_id: int) -> dict:
    filas = db.execute(select(ReglaEmpaque, RecetaEmpaque).join(RecetaEmpaque, RecetaEmpaque.id == ReglaEmpaque.receta_id)
                       .where(ReglaEmpaque.grupo_id == familia_id, ReglaEmpaque.eliminada_en.is_(None))
                       .order_by(ReglaEmpaque.orden, ReglaEmpaque.id)).all()
    return {"reglas": [{"id": r.id, "receta_id": c.id, "receta": c.nombre, "receta_codigo": c.codigo, "destino": r.destino,
                        "condiciones": r.condiciones or [], "activa": r.activa, "vigente_desde": r.vigente_desde,
                        "vigente_hasta": r.vigente_hasta, "motivo": r.motivo} for r, c in filas]}


def _usos(db: Session) -> dict[int, dict[str, int]]:
    res: dict[int, dict[str, int]] = {}
    for clave, cond in (("reglas_empaque", ReglaEmpaque.eliminada_en.is_(None)),
                        ("reglas_empaque_bajas", ReglaEmpaque.eliminada_en.is_not(None))):
        for gid, n in db.execute(select(ReglaEmpaque.grupo_id, func.count()).where(cond, ReglaEmpaque.grupo_id.is_not(None))
                                 .group_by(ReglaEmpaque.grupo_id)):
            res.setdefault(gid, {})[clave] = n
    return res


registrar_seccion_familia(SeccionFamilia(
    clave="empaque", nombre="Packing", orden=50, leer=_leer, usos=_usos,
    permisos_ver=("catalogos.ver", "oc.empaque")))
