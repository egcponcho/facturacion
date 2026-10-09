"""Proveedores con acceso al sistema (administración).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Proveedor, Usuario
from app.modulos.acceso.permisos import exigir, proveedores_de


def listar_proveedores(db: Session, user: Usuario) -> list[dict]:
    consulta = select(Proveedor).order_by(Proveedor.nombre)
    permitidos = proveedores_de(user)
    if permitidos is not None:  # solo los de su alcance
        consulta = consulta.where(Proveedor.id.in_(permitidos))
    return [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "activo": p.activo, "pais": p.pais,
             "razon_social": p.razon_social, "marcas": [m.nombre for m in getattr(p, "marcas", [])]}
            for p in db.scalars(consulta).all()]


def crear_proveedor(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "admin")
    codigo = datos.codigo.strip().upper()
    if db.scalar(select(Proveedor.id).where(Proveedor.codigo == codigo)):
        raise ErrorNegocio(f"Supplier {codigo} already exists.", 409, "duplicado")
    p = Proveedor(codigo=codigo, nombre=datos.nombre.strip(), activo=datos.activo)
    db.add(p)
    db.flush()
    return {"id": p.id}


def actualizar_proveedor(db: Session, user: Usuario, proveedor_id: int, datos) -> dict:
    exigir(user, "admin")
    p = db.get(Proveedor, proveedor_id)
    if not p:
        raise ErrorNegocio("The supplier does not exist.", 404, "no_encontrado")
    for k, v in datos.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    return {"ok": True}
