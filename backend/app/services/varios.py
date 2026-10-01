from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Alerta,
    PlantillaCaja,
    Proveedor,
    Rol,
    Usuario,
)
from ..security import hash_password
from .acceso import exigir_politica, password_temporal, revocar_sesiones, validar_telefono
from .normalizar import nombre as nombre_fmt
from .normalizar import texto as texto_fmt
from .common import (
    ErrorNegocio,
    alcance,
    catalogo_permisos,
    exigir,
    permisos_de,
    permisos_fabrica,
    permisos_validos,
    proveedor_filtro,
    registrar,
)


# ---- Alertas ----------------------------------------------------------------
def listar_alertas(db: Session, user: Usuario, proveedor_id: int | None = None) -> list[dict]:
    exigir(user, "alertas.ver")
    consulta = select(Alerta).where(Alerta.resuelta.is_(False)).order_by(Alerta.creada_en.desc()).limit(50)
    if proveedor_id:
        consulta = consulta.where(Alerta.proveedor_id == proveedor_id)
    return [{"id": a.id, "tipo": a.tipo, "mensaje": a.mensaje, "creada_en": a.creada_en}
            for a in db.scalars(consulta).all()]


def resolver_alerta(db: Session, user: Usuario, alerta_id: int) -> dict:
    exigir(user, "alertas.ver")
    a = db.get(Alerta, alerta_id)
    if not a:
        raise ErrorNegocio("The alert does not exist.", 404, "no_encontrado")
    a.resuelta = True
    return {"ok": True}


# ---- Plantillas -------------------------------------------------------------
def _plantilla_dict(t: PlantillaCaja) -> dict:
    return {c: getattr(t, c) for c in (
        "id", "proveedor_id", "nombre", "cantidad_por_caja", "unidad", "largo", "ancho", "alto",
        "peso_neto", "peso_bruto", "tara", "activa")}


def listar_plantillas(db: Session, user: Usuario, proveedor_id: int | None, incluir_inactivas: bool) -> list[dict]:
    prov = proveedor_filtro(user, proveedor_id)
    if not prov:
        return []
    consulta = select(PlantillaCaja).where(PlantillaCaja.proveedor_id == prov).order_by(PlantillaCaja.nombre)
    if not incluir_inactivas:
        consulta = consulta.where(PlantillaCaja.activa.is_(True))
    return [_plantilla_dict(t) for t in db.scalars(consulta).all()]


def _validar_pesos(neto, bruto):
    if neto is not None and bruto is not None and bruto < neto:
        raise ErrorNegocio("Gross weight cannot be less than net weight.", 422, "validacion")


def crear_plantilla(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "plantilla.editar")
    prov = proveedor_filtro(user, datos.proveedor_id)
    if not prov:
        raise ErrorNegocio("Choose the template's supplier.", 422, "validacion")
    _validar_pesos(datos.peso_neto, datos.peso_bruto)
    nombre = datos.nombre.strip()
    if db.scalar(select(PlantillaCaja.id).where(PlantillaCaja.proveedor_id == prov, PlantillaCaja.nombre == nombre)):
        raise ErrorNegocio(f"A template named “{nombre}” already exists.", 409, "duplicado")
    t = PlantillaCaja(**{**datos.model_dump(exclude={"proveedor_id"}), "nombre": nombre, "proveedor_id": prov})
    db.add(t)
    db.flush()
    return _plantilla_dict(t)


def actualizar_plantilla(db: Session, user: Usuario, plantilla_id: int, datos) -> dict:
    """Editar una plantilla no cambia las cajas ya creadas: cada caja guarda sus valores."""
    exigir(user, "plantilla.editar")
    t = db.get(PlantillaCaja, plantilla_id)
    if not t or (user.rol == "proveedor" and t.proveedor_id != user.proveedor_id):
        raise ErrorNegocio("The template does not exist.", 404, "no_encontrado")
    campos = datos.model_dump(exclude_unset=True)
    if "nombre" in campos:
        campos["nombre"] = (campos["nombre"] or "").strip()
        if not campos["nombre"]:
            raise ErrorNegocio("The name is required.", 422, "validacion")
        otra = db.scalar(select(PlantillaCaja.id).where(
            PlantillaCaja.proveedor_id == t.proveedor_id, PlantillaCaja.nombre == campos["nombre"],
            PlantillaCaja.id != t.id))
        if otra:
            raise ErrorNegocio(f"A template named “{campos['nombre']}” already exists.", 409, "duplicado")
    for k, v in campos.items():
        setattr(t, k, v)
    _validar_pesos(t.peso_neto, t.peso_bruto)
    return _plantilla_dict(t)


# ---- Administración ---------------------------------------------------------
def listar_proveedores(db: Session, user: Usuario) -> list[dict]:
    consulta = select(Proveedor).order_by(Proveedor.nombre)
    if user.rol == "proveedor":
        consulta = consulta.where(Proveedor.id == user.proveedor_id)
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


# ---- Roles --------------------------------------------------------------------
# Los roles son libres: nombre, descripción y los permisos que se marquen. Qué
# datos ve cada usuario no depende del rol sino de si tiene un proveedor
# asignado (ve solo lo suyo) o no (equipo interno). Estos tres se crean al
# inicio como punto de partida y se pueden editar o borrar como cualquier otro.
ROLES_FABRICA = [
    ("Administrator", "admin", "Everything, including users, roles and suppliers."),
    ("Internal team", "interno", "Imports team: classifies, approves and manages shipments and master data."),
    ("Supplier", "proveedor", "Works on its own POs, invoices, packing lists and technical sheets."),
]


def crear_roles_fabrica(db: Session) -> dict[str, Rol]:
    """Los roles iniciales con sus permisos por defecto (si faltan)."""
    res = {}
    for nombre, tipo, desc in ROLES_FABRICA:
        r = db.scalar(select(Rol).where(Rol.sistema.is_(True), Rol.tipo == tipo))
        if not r:
            r = Rol(nombre=nombre, tipo=tipo, descripcion=desc, permisos=permisos_fabrica(tipo), sistema=True)
            db.add(r)
            db.flush()
        res[tipo] = r
    return res


def _rol_dict(r: Rol, usuarios: int) -> dict:
    return {"id": r.id, "nombre": r.nombre, "descripcion": r.descripcion, "activo": r.activo,
            "permisos": permisos_validos(r.permisos), "usuarios": usuarios}


def _admins_activos(db: Session) -> int:
    """Usuarios activos que pueden administrar: nunca debe quedar ninguno."""
    return sum(1 for u in db.scalars(select(Usuario).where(Usuario.activo.is_(True))).all()
               if not u.proveedor_id and "admin" in permisos_de(u))


def _sin_administrador(db: Session) -> None:
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
    return {"roles": [_rol_dict(r, cuenta.get(r.id, 0)) for r in roles], "catalogo": catalogo_permisos()}


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
    for k, v in campos.items():
        setattr(r, k, v)
    if not r.nombre:
        raise ErrorNegocio("The role needs a name.", 422, "validacion")
    if not rol_id:
        db.add(r)
    db.flush()
    _recalcular_alcance(db, r)
    _sin_administrador(db)
    registrar(db, user, "rol", r.id, "guardado", {"nombre": r.nombre, "permisos": r.permisos})
    return _rol_dict(r, db.scalar(select(func.count()).where(Usuario.rol_id == r.id)) or 0)


def borrar_rol(db: Session, user: Usuario, rol_id: int) -> None:
    exigir(user, "admin")
    r = db.get(Rol, rol_id)
    if not r:
        raise ErrorNegocio("The role does not exist.", 404, "no_encontrado")
    if db.scalar(select(func.count()).where(Usuario.rol_id == r.id)):
        raise ErrorNegocio("The role has users: assign them another role first.", 422, "en_uso")
    db.delete(r)


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
    from .acceso import _ahora

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
    _sin_administrador(db)
    return {"ok": True, "password_temporal": temporal}
