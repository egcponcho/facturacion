"""Bitácora general: quién hizo qué, cuándo y sobre qué registro.

Cada módulo deja sus cambios en `historial` (`historial.registrar`); aquí se
consultan todos juntos, con filtros, para la administración. Las pantallas de
cada documento (factura, embarque, producto, OC) muestran solo su parte.
"""
from datetime import date, datetime, time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modelos import Historial, Usuario
from app.modulos.acceso.permisos import exigir

# Nombre legible de cada entidad que deja rastro
ENTIDADES = {
    "orden": "Purchase order", "factura": "Invoice", "packing_list": "Packing list", "embarque": "Shipment",
    "unidad": "Load unit", "producto": "Product", "usuario": "User", "rol": "Role", "proveedores": "Supplier",
    "organizacion": "Company settings", "alerta": "Alert", "plantilla_caja": "Packing template",
    "aranceles": "Tariff schedule", "clasificacion": "Classification engine", "conocimiento": "Classification engine",
    "flujo": "Classification workflow", "traduccion": "Translations", "genericos": "Generic items", "prepacks": "Prepacks",
    "importacion_oc": "PO import", "perfil_importacion": "Import profile",
}


def _nombre(entidad: str) -> str:
    """Nombre de la entidad (los catálogos de datos maestros usan su título)."""
    from app.modulos.maestros.catalogos import CATALOGOS

    return ENTIDADES.get(entidad) or CATALOGOS.get(entidad, {}).get("titulo") or entidad


def consultar(db: Session, user: Usuario, entidad: str | None = None, entidad_id: int | None = None,
              usuario_id: int | None = None, accion: str | None = None, desde: date | None = None,
              hasta: date | None = None, page: int = 1, size: int = 50) -> dict:
    exigir(user, "admin")
    cond = []
    if entidad:
        cond.append(Historial.entidad == entidad)
    if entidad_id is not None:
        cond.append(Historial.entidad_id == entidad_id)
    if usuario_id:
        cond.append(Historial.usuario_id == usuario_id)
    if accion:
        cond.append(or_(Historial.accion.ilike(f"%{accion}%"), Historial.motivo.ilike(f"%{accion}%")))
    if desde:
        cond.append(Historial.fecha >= datetime.combine(desde, time.min))
    if hasta:
        cond.append(Historial.fecha <= datetime.combine(hasta, time.max))
    total = db.scalar(select(func.count()).select_from(Historial).where(*cond)) or 0
    filas = db.scalars(select(Historial).where(*cond).order_by(Historial.fecha.desc(), Historial.id.desc())
                       .offset((page - 1) * size).limit(size)).all()
    return {
        "total": total, "page": page, "size": size,
        "items": [{"id": h.id, "fecha": h.fecha, "entidad": h.entidad, "entidad_txt": _nombre(h.entidad),
                   "entidad_id": h.entidad_id, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
                   "usuario_id": h.usuario_id, "usuario": h.usuario.nombre if h.usuario else None}
                  for h in filas],
    }


def opciones(db: Session, user: Usuario) -> dict:
    """Entidades con registros y usuarios que aparecen, para los filtros."""
    exigir(user, "admin")
    entidades = sorted(e for (e,) in db.execute(select(Historial.entidad).distinct()))
    usuarios = db.execute(select(Usuario.id, Usuario.nombre).where(
        Usuario.id.in_(select(Historial.usuario_id).distinct())).order_by(Usuario.nombre)).all()
    return {"entidades": [{"valor": e, "texto": _nombre(e)} for e in entidades],
            "usuarios": [{"valor": i, "texto": n} for i, n in usuarios]}
