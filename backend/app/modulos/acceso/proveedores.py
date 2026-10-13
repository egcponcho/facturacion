"""Proveedores del alcance de cada usuario. El maestro de proveedores se
mantiene solo en Datos maestros (maestros/catalogos.py), con su validación,
sus responsables y su historial."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Proveedor, Usuario
from app.modulos.acceso.permisos import proveedores_de


def listar_proveedores(db: Session, user: Usuario) -> list[dict]:
    consulta = select(Proveedor).order_by(Proveedor.nombre)
    permitidos = proveedores_de(user)
    if permitidos is not None:  # solo los de su alcance
        consulta = consulta.where(Proveedor.id.in_(permitidos))
    return [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "activo": p.activo, "pais": p.pais,
             "razon_social": p.razon_social, "marcas": [m.nombre for m in getattr(p, "marcas", [])]}
            for p in db.scalars(consulta).all()]
