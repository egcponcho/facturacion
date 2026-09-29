from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Alerta,
    PlantillaCaja,
    Proveedor,
    Usuario,
)
from ..security import hash_password
from .acceso import exigir_politica, revocar_sesiones, validar_telefono
from .common import (
    ErrorNegocio,
    exigir,
    proveedor_filtro,
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
        raise ErrorNegocio("La alerta no existe.", 404, "no_encontrado")
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
        raise ErrorNegocio("El peso bruto no puede ser menor que el neto.", 422, "validacion")


def crear_plantilla(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "plantilla.editar")
    prov = proveedor_filtro(user, datos.proveedor_id)
    if not prov:
        raise ErrorNegocio("Elige el proveedor de la plantilla.", 422, "validacion")
    _validar_pesos(datos.peso_neto, datos.peso_bruto)
    nombre = datos.nombre.strip()
    if db.scalar(select(PlantillaCaja.id).where(PlantillaCaja.proveedor_id == prov, PlantillaCaja.nombre == nombre)):
        raise ErrorNegocio(f"Ya existe una plantilla llamada “{nombre}”.", 409, "duplicado")
    t = PlantillaCaja(**{**datos.model_dump(exclude={"proveedor_id"}), "nombre": nombre, "proveedor_id": prov})
    db.add(t)
    db.flush()
    return _plantilla_dict(t)


def actualizar_plantilla(db: Session, user: Usuario, plantilla_id: int, datos) -> dict:
    """Editar una plantilla no cambia las cajas ya creadas: cada caja guarda sus valores."""
    exigir(user, "plantilla.editar")
    t = db.get(PlantillaCaja, plantilla_id)
    if not t or (user.rol == "proveedor" and t.proveedor_id != user.proveedor_id):
        raise ErrorNegocio("La plantilla no existe.", 404, "no_encontrado")
    campos = datos.model_dump(exclude_unset=True)
    if "nombre" in campos:
        campos["nombre"] = (campos["nombre"] or "").strip()
        if not campos["nombre"]:
            raise ErrorNegocio("El nombre es obligatorio.", 422, "validacion")
        otra = db.scalar(select(PlantillaCaja.id).where(
            PlantillaCaja.proveedor_id == t.proveedor_id, PlantillaCaja.nombre == campos["nombre"],
            PlantillaCaja.id != t.id))
        if otra:
            raise ErrorNegocio(f"Ya existe una plantilla llamada “{campos['nombre']}”.", 409, "duplicado")
    for k, v in campos.items():
        setattr(t, k, v)
    _validar_pesos(t.peso_neto, t.peso_bruto)
    return _plantilla_dict(t)


# ---- Administración ---------------------------------------------------------
def listar_proveedores(db: Session, user: Usuario) -> list[dict]:
    consulta = select(Proveedor).order_by(Proveedor.nombre)
    if user.rol == "proveedor":
        consulta = consulta.where(Proveedor.id == user.proveedor_id)
    return [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "activo": p.activo}
            for p in db.scalars(consulta).all()]


def crear_proveedor(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "admin")
    codigo = datos.codigo.strip().upper()
    if db.scalar(select(Proveedor.id).where(Proveedor.codigo == codigo)):
        raise ErrorNegocio(f"Ya existe el proveedor {codigo}.", 409, "duplicado")
    p = Proveedor(codigo=codigo, nombre=datos.nombre.strip(), activo=datos.activo)
    db.add(p)
    db.flush()
    return {"id": p.id}


def actualizar_proveedor(db: Session, user: Usuario, proveedor_id: int, datos) -> dict:
    exigir(user, "admin")
    p = db.get(Proveedor, proveedor_id)
    if not p:
        raise ErrorNegocio("El proveedor no existe.", 404, "no_encontrado")
    for k, v in datos.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    return {"ok": True}


def _usuario_dict(u: Usuario) -> dict:
    from .acceso import _ahora

    return {"id": u.id, "email": u.email, "nombre": u.nombre, "rol": u.rol, "activo": u.activo,
            "proveedor_id": u.proveedor_id, "proveedor": u.proveedor.nombre if u.proveedor else None,
            "telefono": u.telefono, "dos_pasos": u.dos_pasos, "ultimo_acceso": u.ultimo_acceso,
            "bloqueado": bool(u.bloqueado_hasta and u.bloqueado_hasta > _ahora())}


def listar_usuarios(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "admin")
    return [_usuario_dict(u) for u in db.scalars(select(Usuario).order_by(Usuario.nombre)).all()]


def crear_usuario(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "admin")
    email = datos.email.strip().lower()
    if db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise ErrorNegocio("Ya existe un usuario con ese correo.", 409, "duplicado")
    if datos.rol == "proveedor" and not datos.proveedor_id:
        raise ErrorNegocio("Un usuario proveedor debe tener proveedor asignado.", 422, "validacion")
    exigir_politica(datos.password, email)
    u = Usuario(email=email, nombre=datos.nombre.strip(), rol=datos.rol,
                proveedor_id=datos.proveedor_id if datos.rol == "proveedor" else None,
                password_hash=hash_password(datos.password), activo=True,
                telefono=validar_telefono(datos.telefono), dos_pasos=datos.dos_pasos)
    db.add(u)
    db.flush()
    return {"id": u.id}


def actualizar_usuario(db: Session, user: Usuario, usuario_id: int, datos) -> dict:
    exigir(user, "admin")
    u = db.get(Usuario, usuario_id)
    if not u:
        raise ErrorNegocio("El usuario no existe.", 404, "no_encontrado")
    campos = datos.model_dump(exclude_unset=True)
    revocar = False
    if "password" in campos:
        pw = campos.pop("password")
        if pw:
            exigir_politica(pw, u.email)
            u.password_hash = hash_password(pw)
            u.bloqueado_hasta, u.intentos_fallidos = None, 0
            revocar = True
    if "telefono" in campos:
        campos["telefono"] = validar_telefono(campos["telefono"])
        revocar = revocar or campos["telefono"] != u.telefono
    if campos.get("activo") is False or campos.get("dos_pasos") is False:
        revocar = True
    if revocar:
        # Contraseña, celular o acceso cambiaron: se cierran sus sesiones abiertas
        revocar_sesiones(db, u.id)
    for k, v in campos.items():
        setattr(u, k, v)
    if u.rol == "proveedor" and not u.proveedor_id:
        raise ErrorNegocio("Un usuario proveedor debe tener proveedor asignado.", 422, "validacion")
    if u.rol != "proveedor":
        u.proveedor_id = None
    return {"ok": True}
