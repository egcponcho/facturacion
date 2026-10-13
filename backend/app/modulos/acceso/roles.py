"""Roles: los de fábrica, los sugeridos y los que crea la empresa.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Rol, Usuario
from app.modulos.acceso import visibilidad
from app.modulos.acceso.permisos import (
    alcance,
    catalogo_permisos,
    exigir,
    permisos_de,
    permisos_fabrica,
    permisos_validos,
)
from app.modulos.comun.historial import registrar

# Los roles son libres: nombre, descripción y los permisos que se marquen. Qué
# datos ve cada usuario no depende del rol sino de si tiene un proveedor
# asignado (ve solo lo suyo) o no (equipo interno). Estos tres se crean al
# inicio como punto de partida y se pueden editar o borrar como cualquier otro.
ROLES_FABRICA = [
    ("Administrator", "admin", "Everything, including users, roles and suppliers."),
    ("Internal team", "interno", "Imports team: classifies, approves and manages shipments and master data."),
    ("Supplier", "proveedor", "Works on its own POs, invoices, packing lists and technical sheets."),
]


# Roles sugeridos para repartir la clasificación: se crean una vez como punto
# de partida (no son de sistema; se editan o borran como cualquier otro)
ROLES_SUGERIDOS = [
    ("Classification specialist", "Configures product families, attributes and rules; reviews, approves and returns technical sheets.",
     ["oc.ver", "producto.ver", "producto.ficha", "producto.clasificar", "aranceles.ver", "clasificacion.ver",
      "clasificacion.configurar", "seguimiento.ver"]),
    ("Buyer", "Creates items and fills their technical sheets; sends them to review.",
     ["oc.ver", "producto.ver", "producto.ficha", "producto.crear", "seguimiento.ver"]),
]


def crear_roles_sugeridos(db: Session) -> None:
    for nombre, desc, permisos in ROLES_SUGERIDOS:
        if not db.scalar(select(Rol.id).where(func.lower(Rol.nombre) == nombre.lower())):
            db.add(Rol(nombre=nombre, tipo="interno", descripcion=desc, permisos=permisos, sistema=False))
    db.flush()


def crear_roles_fabrica(db: Session) -> dict[str, Rol]:
    """Los roles iniciales con sus permisos por defecto (si faltan)."""
    res = {}
    for nombre, tipo, desc in ROLES_FABRICA:
        r = db.scalar(select(Rol).where(Rol.sistema.is_(True), Rol.tipo == tipo))
        if not r:
            r = Rol(nombre=nombre, tipo=tipo, descripcion=desc, permisos=permisos_fabrica(tipo), sistema=True,
                    datos_ocultos=list(visibilidad.DEFECTO_POR_TIPO.get(tipo, [])))
            db.add(r)
            db.flush()
        res[tipo] = r
    return res


def _rol_dict(r: Rol, usuarios: int) -> dict:
    return {"id": r.id, "nombre": r.nombre, "descripcion": r.descripcion, "activo": r.activo,
            "permisos": permisos_validos(r.permisos), "usuarios": usuarios,
            "datos_ocultos": visibilidad.validos(r.datos_ocultos),
            "inicio_oculto": visibilidad.paneles_validos(r.inicio_oculto)}


def _admins_activos(db: Session) -> int:
    """Usuarios activos que pueden administrar: nunca debe quedar ninguno."""
    return sum(1 for u in db.scalars(select(Usuario).where(Usuario.activo.is_(True))).all()
               if not u.proveedor_id and "admin" in permisos_de(u))


def sin_administrador(db: Session) -> None:
    db.flush()
    db.expire_all()
    if not _admins_activos(db):
        raise ErrorNegocio("At least one active user must keep the administration permission.", 422, "validacion")


def _recalcular_alcance(db: Session, r: Rol) -> None:
    for u in db.scalars(select(Usuario).where(Usuario.rol_id == r.id)).all():
        u.rol = alcance(r.permisos, u.proveedor_id)


def listar_roles(db: Session, user: Usuario) -> dict:
    exigir(user, "admin")
    crear_roles_fabrica(db)
    cuenta = dict(db.execute(select(Usuario.rol_id, func.count()).group_by(Usuario.rol_id)).all())
    roles = db.scalars(select(Rol).order_by(Rol.nombre)).all()
    return {"roles": [_rol_dict(r, cuenta.get(r.id, 0)) for r in roles], "catalogo": catalogo_permisos(),
            "datos": visibilidad.catalogo(),
            "paneles": [{"clave": k, "etiqueta": v} for k, v in visibilidad.PANELES_INICIO.items()]}


def guardar_rol(db: Session, user: Usuario, datos, rol_id: int | None = None) -> dict:
    exigir(user, "admin")
    campos = datos.model_dump(exclude_unset=True)
    r = db.get(Rol, rol_id) if rol_id else Rol(sistema=False, tipo="rol")
    if rol_id and not r:
        raise ErrorNegocio("The role does not exist.", 404, "no_encontrado")
    if "nombre" in campos:
        campos["nombre"] = (campos["nombre"] or "").strip()
        if not campos["nombre"]:
            raise ErrorNegocio("The role needs a name.", 422, "validacion")
        otro = db.scalar(select(Rol.id).where(func.lower(Rol.nombre) == campos["nombre"].lower()))
        if otro and otro != rol_id:
            raise ErrorNegocio(f"A role named “{campos['nombre']}” already exists.", 409, "duplicado")
    if "descripcion" in campos:
        campos["descripcion"] = (campos["descripcion"] or "").strip() or None
    if "permisos" in campos:
        campos["permisos"] = permisos_validos(campos["permisos"])
    if "datos_ocultos" in campos:
        if r.tipo == "admin" and campos["datos_ocultos"]:
            raise ErrorNegocio("The administrator role always sees all data.", 422, "validacion")
        campos["datos_ocultos"] = visibilidad.validos(campos["datos_ocultos"])
    if "inicio_oculto" in campos:
        campos["inicio_oculto"] = visibilidad.paneles_validos(campos["inicio_oculto"])
    for k, v in campos.items():
        setattr(r, k, v)
    if not r.nombre:
        raise ErrorNegocio("The role needs a name.", 422, "validacion")
    if not rol_id:
        db.add(r)
    db.flush()
    _recalcular_alcance(db, r)
    sin_administrador(db)
    registrar(db, user, "rol", r.id, "guardado", {"nombre": r.nombre, "permisos": r.permisos,
                                                   "datos_ocultos": r.datos_ocultos})
    return _rol_dict(r, db.scalar(select(func.count()).where(Usuario.rol_id == r.id)) or 0)


def borrar_rol(db: Session, user: Usuario, rol_id: int) -> None:
    exigir(user, "admin")
    r = db.get(Rol, rol_id)
    if not r:
        raise ErrorNegocio("The role does not exist.", 404, "no_encontrado")
    if db.scalar(select(func.count()).where(Usuario.rol_id == r.id)):
        raise ErrorNegocio("The role has users: assign them another role first.", 422, "en_uso")
    registrar(db, user, "rol", r.id, "borrado", {"nombre": r.nombre, "permisos": r.permisos})
    db.delete(r)
