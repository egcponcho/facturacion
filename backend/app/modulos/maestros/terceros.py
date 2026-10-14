"""Terceros de los datos maestros: la identidad fiscal (nombre, razón social,
identificación y país), las direcciones y los medios de contacto de cada
proveedor y transportista viven en su tercero (tercero_id).
"""
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modelos import Tercero, TerceroRol


def _codigo_libre(db: Session, base: str, propio_id: int | None = None) -> str:
    base = re.sub(r"[^A-Z0-9._\-]", "", (base or "").upper())[:26] or "T"
    codigo, n = base, 1
    while (x := db.scalar(select(Tercero.id).where(Tercero.codigo == codigo))) and x != propio_id:
        n += 1
        codigo = f"{base}-{n}"
    return codigo


def asegurar(db: Session, obj, rol: str) -> Tercero:
    """El tercero de un proveedor o transportista (se crea si no tiene) con su rol."""
    t = db.get(Tercero, obj.tercero_id) if obj.tercero_id else None
    if t is None and getattr(obj, "id_fiscal", None):
        t = db.scalar(select(Tercero).where(func.upper(Tercero.id_fiscal) == obj.id_fiscal.upper(),
                                            or_(Tercero.pais == obj.pais, Tercero.pais.is_(None) & (obj.pais is None))))
    if t is None:
        t = Tercero(codigo=_codigo_libre(db, obj.codigo), nombre=obj.nombre, activo=True)
        db.add(t)
    t.nombre = obj.nombre
    for k in ("razon_social", "id_fiscal", "pais"):
        if getattr(obj, k, None):
            setattr(t, k, getattr(obj, k))
    if not t.tiene_rol(rol):
        t.roles.append(TerceroRol(rol=rol))
    db.flush()
    obj.tercero_id = t.id
    return t
