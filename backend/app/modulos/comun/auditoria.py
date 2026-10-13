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
from app.modulos.comun import tabla

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


# Filtro por columna de la bitácora (app/modulos/comun/tabla.py): la fecha, por
# día; el usuario, por su nombre
COLUMNAS = {"fecha": func.date(Historial.fecha), "usuario": Usuario.nombre, "entidad": Historial.entidad,
            "entidad_id": Historial.entidad_id, "accion": Historial.accion, "motivo": Historial.motivo}
ORDEN = {"fecha": Historial.fecha, "usuario": Usuario.nombre, "entidad": Historial.entidad,
         "entidad_id": Historial.entidad_id, "accion": Historial.accion, "motivo": Historial.motivo}


def _consulta(user: Usuario, entidad: str | None, entidad_id: int | None, usuario_id: int | None,
              accion: str | None, desde: date | None, hasta: date | None):
    """Cambios con los filtros de la pantalla (sin los filtros por columna ni el orden)."""
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
    return select(Historial).outerjoin(Usuario, Usuario.id == Historial.usuario_id).where(*cond)


def valores(db: Session, user: Usuario, columna: str, buscar: str | None, filtros_columna: dict,
            entidad: str | None = None, entidad_id: int | None = None, usuario_id: int | None = None,
            accion: str | None = None, desde: date | None = None, hasta: date | None = None) -> list[dict]:
    """Valores únicos de una columna de la bitácora, con cuántos cambios tienen cada uno, bajo los demás filtros."""
    expr = tabla.columna_valida(COLUMNAS, columna)
    consulta = tabla.aplicar(_consulta(user, entidad, entidad_id, usuario_id, accion, desde, hasta), COLUMNAS,
                             filtros_columna, excepto=columna)
    return tabla.valores(db, consulta, expr, buscar, contar=Historial.id)


def consultar(db: Session, user: Usuario, entidad: str | None = None, entidad_id: int | None = None,
              usuario_id: int | None = None, accion: str | None = None, desde: date | None = None,
              hasta: date | None = None, page: int = 1, size: int = 50, orden: str | None = None,
              filtros_columna: dict | None = None) -> dict:
    consulta = tabla.aplicar(_consulta(user, entidad, entidad_id, usuario_id, accion, desde, hasta), COLUMNAS,
                             filtros_columna or {})
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    col, _, direccion = (orden or "").partition(":")
    expr = ORDEN.get(col)
    if expr is not None:
        consulta = consulta.order_by(expr.desc().nullslast() if direccion == "desc" else expr.asc().nullslast(), Historial.id.desc())
    else:
        consulta = consulta.order_by(Historial.fecha.desc(), Historial.id.desc())
    filas = db.scalars(consulta.offset((page - 1) * size).limit(size)).all()
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
