"""Organizaciones de la plataforma.

Quien administra la plataforma (`usuarios.plataforma`) da de alta
organizaciones (con sus datos de partida y su primer administrador), las
suspende o reactiva y entra a cualquiera para darle soporte: su sesión pasa a
trabajar en esa organización y todo lo que hace queda en su bitácora.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import organizacion
from app.core.errores import ErrorNegocio
from app.modelos import Organizacion, SesionUsuario, Usuario
from app.modulos.comun.historial import registrar


def exigir_plataforma(user: Usuario) -> None:
    if not user.plataforma:
        raise ErrorNegocio("Only the platform administration can do this.", 403, "sin_permiso")


def _dict(o: Organizacion, usuarios: int) -> dict:
    return {"id": o.id, "codigo": o.codigo, "nombre": o.nombre, "pais": o.pais, "activa": o.activa,
            "creada_en": o.creada_en, "usuarios": usuarios}


def listar(db: Session, user: Usuario) -> list[dict]:
    exigir_plataforma(user)
    with organizacion.todas(db):
        cuentas = dict(db.execute(select(Usuario.organizacion_id, func.count()).group_by(Usuario.organizacion_id)).all())
    return [_dict(o, cuentas.get(o.id, 0)) for o in db.scalars(select(Organizacion).order_by(Organizacion.nombre))]


def crear(db: Session, user: Usuario, datos) -> dict:
    """Organización nueva con sus datos de partida y su primer administrador
    (con contraseña temporal: la cambia en su primer ingreso)."""
    from app.core.seguridad import hash_password
    from app.instalacion.base_organizacion import sembrar
    from app.modulos.acceso.autenticacion import password_temporal, validar_telefono
    from app.modulos.acceso.roles import crear_roles_fabrica

    exigir_plataforma(user)
    codigo = re.sub(r"[^A-Z0-9_-]", "", (datos.codigo or "").strip().upper())[:20]
    nombre = (datos.nombre or "").strip()[:200]
    email = (datos.admin_email or "").strip().lower()
    if not codigo or not nombre:
        raise ErrorNegocio("The organization needs a code and a name.", 422, "validacion")
    if db.scalar(select(Organizacion.id).where(func.upper(Organizacion.codigo) == codigo)):
        raise ErrorNegocio(f"Organization {codigo} already exists.", 409, "duplicado")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ErrorNegocio("Enter the email of the organization's first administrator.", 422, "validacion")
    from app.modulos.acceso.usuarios import correo_usado

    if correo_usado(db, email):
        raise ErrorNegocio("A user with that email already exists.", 409, "duplicado")
    telefono = validar_telefono(datos.admin_telefono) if datos.admin_telefono else None
    o = Organizacion(codigo=codigo, nombre=nombre, pais=(datos.pais or "").upper()[:2] or None, configuracion={}, activa=True)
    db.add(o)
    db.flush()
    clave = password_temporal()
    with organizacion.trabajando_en(db, o.id):
        sembrar(db)
        rol = crear_roles_fabrica(db)["admin"]
        admin = Usuario(email=email, nombre=(datos.admin_nombre or "Administrator").strip()[:200], rol="admin",
                        rol_id=rol.id, password_hash=hash_password(clave), activo=True, clave_temporal=True,
                        telefono=telefono, dos_pasos=True)
        db.add(admin)
        db.flush()
        registrar(db, user, "organizacion", o.id, "creada", {"codigo": codigo, "nombre": nombre, "administrador": email})
    return {**_dict(o, 1), "admin_email": email, "password_temporal": clave}


def actualizar(db: Session, user: Usuario, organizacion_id: int, datos) -> dict:
    exigir_plataforma(user)
    o = db.get(Organizacion, organizacion_id)
    if not o:
        raise ErrorNegocio("The organization does not exist.", 404, "no_encontrado")
    campos = datos.model_dump(exclude_unset=True)
    if campos.get("activa") is False and o.id == user.organizacion_id:
        raise ErrorNegocio("You cannot suspend your own organization.", 422, "validacion")
    cambios = {}
    for k in ("nombre", "activa"):
        if k in campos and campos[k] is not None and getattr(o, k) != campos[k]:
            cambios[k] = {"antes": getattr(o, k), "despues": campos[k]}
            setattr(o, k, campos[k])
    if cambios:
        with organizacion.trabajando_en(db, o.id):
            registrar(db, user, "organizacion", o.id, "actualizada", cambios)
    return _dict(o, 0)


def entrar(db: Session, user: Usuario, token: str, organizacion_id: int | None) -> dict:
    """La sesión de quien administra la plataforma pasa a trabajar en otra
    organización (o vuelve a la suya con None)."""
    from app.modulos.acceso.autenticacion import _hash

    exigir_plataforma(user)
    destino = organizacion_id or user.organizacion_id
    o = db.get(Organizacion, destino)
    if not o:
        raise ErrorNegocio("The organization does not exist.", 404, "no_encontrado")
    s = db.scalar(select(SesionUsuario).where(SesionUsuario.token_hash == _hash(token)))
    s.organizacion_id = None if destino == user.organizacion_id else destino
    with organizacion.trabajando_en(db, destino):
        registrar(db, user, "organizacion", destino, "entrada_plataforma", {"usuario": user.email})
    return {"id": o.id, "nombre": o.nombre}
