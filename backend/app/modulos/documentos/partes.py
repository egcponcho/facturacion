"""Partes de un documento: a quién se factura y a quién se notifica.

La OC ya trae la sociedad compradora (a la que se factura) y el centro que
recibe (notify party). Con el centro de destino se sabe a qué país llega la
mercancía al final. Los datos y contactos salen de Mantenimiento.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Centro, Contacto, Pais, Puerto, Sociedad


def _contactos(db: Session, **filtro) -> list[dict]:
    col, valor = next(iter(filtro.items()))
    return [{"nombre": c.nombre, "cargo": c.cargo, "rol": c.rol, "correos": c.correos, "telefono": c.telefono}
            for c in db.scalars(select(Contacto).where(getattr(Contacto, col) == valor, Contacto.activo)
                                .order_by(Contacto.rol, Contacto.nombre))]


def _pais(db: Session, codigo: str | None) -> str | None:
    if not codigo:
        return None
    p = db.scalar(select(Pais).where(Pais.codigo == codigo))
    return p.nombre if p else codigo


def partes(db: Session, sociedad: str | None, centro: str | None, centro_destino: str | None = None) -> dict:
    soc = db.scalar(select(Sociedad).where(Sociedad.codigo == sociedad)) if sociedad else None
    cen = db.scalar(select(Centro).where(Centro.codigo == centro)) if centro else None
    dest = db.scalar(select(Centro).where(Centro.codigo == centro_destino)) if centro_destino else None
    puerto = db.scalar(select(Puerto).where(Puerto.codigo == cen.puerto)) if cen and cen.puerto else None
    return {
        "facturar_a": {
            "codigo": sociedad, "nombre": soc.nombre if soc else None,
            "razon_social": soc.razon_social if soc else None, "id_fiscal": soc.id_fiscal if soc else None,
            "direccion": soc.direccion if soc else None, "pais": _pais(db, soc.pais) if soc else None,
            "correos": soc.correos if soc else None,
            "contactos": _contactos(db, sociedad_id=soc.id) if soc else [],
        },
        "notify": {
            "codigo": centro, "nombre": cen.nombre if cen else None, "direccion": cen.direccion if cen else None,
            "pais": _pais(db, cen.pais) if cen else None, "correos": cen.correos if cen else None,
            "puerto": cen.puerto if cen else None, "puerto_nombre": puerto.nombre if puerto else None,
            "contactos": _contactos(db, centro_id=cen.id) if cen else [],
        },
        "destino": {
            "codigo": centro_destino, "nombre": dest.nombre if dest else None,
            "pais": _pais(db, dest.pais) if dest else None,
        } if centro_destino else None,
    }
