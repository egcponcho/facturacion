"""Usuarios: alta y cambios (datos, rol, proveedor y estado).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.core.seguridad import hash_password
from app.modelos import Proveedor, Rol, Usuario
from app.modulos.acceso.autenticacion import exigir_politica, password_temporal, revocar_sesiones, validar_telefono
from app.modulos.acceso.permisos import alcance, exigir
from app.modulos.acceso.roles import crear_roles_fabrica, sin_administrador
from app.modulos.comun.normalizar import nombre as nombre_fmt
from app.modulos.comun.normalizar import texto as texto_fmt


def _rol_elegido(db: Session, rol_id: int | None, tipo: str | None = None) -> Rol:
    if rol_id:
        r = db.get(Rol, rol_id)
        if not r or not r.activo:
            raise ErrorNegocio("Choose an active role.", 422, "validacion")
        return r
    if not tipo:
        raise ErrorNegocio("Choose a role.", 422, "validacion")
    return crear_roles_fabrica(db)[tipo]


def _proveedor_elegido(db: Session, proveedor_id: int | None) -> int | None:
    if not proveedor_id:
        return None
    p = db.get(Proveedor, proveedor_id)
    if not p or not p.activo:
        raise ErrorNegocio("Choose an active supplier.", 422, "validacion")
    return p.id


def _usuario_dict(u: Usuario) -> dict:
    from app.modulos.acceso.autenticacion import _ahora

    return {"id": u.id, "email": u.email, "nombre": u.nombre, "rol": u.rol, "activo": u.activo,
            "rol_id": u.rol_id, "rol_nombre": u.rol_ref.nombre if u.rol_ref else None,
            "proveedor_id": u.proveedor_id, "proveedor": u.proveedor.nombre if u.proveedor else None,
            "telefono": u.telefono, "dos_pasos": u.dos_pasos, "ultimo_acceso": u.ultimo_acceso,
            "cargo": u.cargo, "area": u.area, "empresa": u.empresa, "foto": u.foto, "clave_temporal": bool(u.clave_temporal),
            "bloqueado": bool(u.bloqueado_hasta and u.bloqueado_hasta > _ahora())}


def listar_usuarios(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "admin")
    return [_usuario_dict(u) for u in db.scalars(select(Usuario).order_by(Usuario.nombre)).all()]


def crear_usuario(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "admin")
    email = datos.email.strip().lower()
    if db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise ErrorNegocio("A user with that email already exists.", 409, "duplicado")
    rol = _rol_elegido(db, datos.rol_id, datos.rol)
    prov = _proveedor_elegido(db, datos.proveedor_id)
    if datos.rol == "proveedor" and not prov:
        raise ErrorNegocio("A supplier user must have a supplier assigned.", 422, "validacion")
    # Sin contraseña, se genera una temporal: el usuario la cambia en su primer ingreso
    temporal = not datos.password
    clave = password_temporal() if temporal else datos.password
    if not temporal:
        exigir_politica(clave, email)
    u = Usuario(email=email, nombre=nombre_fmt(datos.nombre), rol=alcance(rol.permisos, prov), rol_id=rol.id,
                proveedor_id=prov, password_hash=hash_password(clave), activo=True, clave_temporal=True,
                telefono=validar_telefono(datos.telefono), dos_pasos=datos.dos_pasos,
                cargo=texto_fmt(datos.cargo) or None, area=texto_fmt(datos.area) or None, empresa=texto_fmt(datos.empresa) or None)
    db.add(u)
    db.flush()
    return {"id": u.id, "password_temporal": clave if temporal else None}


def actualizar_usuario(db: Session, user: Usuario, usuario_id: int, datos) -> dict:
    exigir(user, "admin")
    u = db.get(Usuario, usuario_id)
    if not u:
        raise ErrorNegocio("The user does not exist.", 404, "no_encontrado")
    campos = datos.model_dump(exclude_unset=True)
    revocar = False
    temporal = None
    if campos.pop("generar_clave", None):
        campos["password"], temporal = None, password_temporal()
        u.password_hash = hash_password(temporal)
        u.clave_temporal = True
        u.bloqueado_hasta, u.intentos_fallidos = None, 0
        revocar = True
    if "password" in campos:
        pw = campos.pop("password")
        if pw:
            exigir_politica(pw, u.email)
            u.password_hash = hash_password(pw)
            # La clave puesta por la administración es temporal: se cambia al entrar
            u.clave_temporal = True
            u.bloqueado_hasta, u.intentos_fallidos = None, 0
            revocar = True
    for k in ("cargo", "area", "empresa"):
        if k in campos:
            campos[k] = texto_fmt(campos[k]) or None
    if "email" in campos:
        nuevo = (campos.pop("email") or "").strip().lower()
        if nuevo and nuevo != u.email:
            if db.scalar(select(Usuario.id).where(Usuario.email == nuevo)):
                raise ErrorNegocio("A user with that email already exists.", 409, "duplicado")
            u.email = nuevo
    if "telefono" in campos:
        campos["telefono"] = validar_telefono(campos["telefono"])
        revocar = revocar or campos["telefono"] != u.telefono
    if "rol_id" in campos or "rol" in campos:
        rol = _rol_elegido(db, campos.pop("rol_id", None), campos.pop("rol", None))
        campos["rol_id"] = rol.id
    if "proveedor_id" in campos:
        campos["proveedor_id"] = _proveedor_elegido(db, campos["proveedor_id"])
    if campos.get("activo") is False or campos.get("dos_pasos") is False:
        revocar = True
    if revocar:
        # Contraseña, celular o acceso cambiaron: se cierran sus sesiones abiertas
        revocar_sesiones(db, u.id)
    for k, v in campos.items():
        setattr(u, k, v)
    db.flush()
    db.refresh(u)
    u.rol = alcance(u.rol_ref.permisos if u.rol_ref else [], u.proveedor_id)
    sin_administrador(db)
    return {"ok": True, "password_temporal": temporal}
