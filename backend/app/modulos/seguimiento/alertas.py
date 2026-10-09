"""Alertas: lista y resolución.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Alerta, Usuario
from app.modulos.acceso.permisos import exigir, proveedor_filtro
from app.modulos.comun.historial import registrar


def listar_alertas(db: Session, user: Usuario, proveedor_id: int | None = None) -> list[dict]:
    exigir(user, "alertas.ver")
    consulta = select(Alerta).where(Alerta.resuelta.is_(False)).order_by(Alerta.creada_en.desc()).limit(50)
    prov = proveedor_filtro(user, proveedor_id)
    if prov:
        consulta = consulta.where(Alerta.proveedor_id.in_(prov))
    return [{"id": a.id, "tipo": a.tipo, "mensaje": a.mensaje, "creada_en": a.creada_en}
            for a in db.scalars(consulta).all()]


def resolver_alerta(db: Session, user: Usuario, alerta_id: int) -> dict:
    exigir(user, "alertas.ver")
    a = db.get(Alerta, alerta_id)
    prov = proveedor_filtro(user)
    if not a or (prov and a.proveedor_id not in prov):
        raise ErrorNegocio("The alert does not exist.", 404, "no_encontrado")
    a.resuelta = True
    registrar(db, user, "alerta", a.id, "resolver", {"tipo": a.tipo, "mensaje": a.mensaje})
    return {"ok": True}
