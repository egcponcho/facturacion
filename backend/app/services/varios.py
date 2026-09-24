from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Alerta,
    Embarque,
    Factura,
    PackingList,
    PlantillaCaja,
    Proveedor,
    Usuario,
    ahora,
)
from ..security import hash_password
from .common import (
    EDITABLE_PL,
    ErrorNegocio,
    es_interno,
    exigir,
    proveedor_filtro,
)
from .facturas import listar_facturas
from .ordenes import listar_ordenes


# ---- Inicio -----------------------------------------------------------------
def inicio(db: Session, user: Usuario, proveedor_id: int | None = None) -> dict:
    prov = proveedor_filtro(user, proveedor_id)
    tarjetas = []

    def tarjeta(clave, titulo, valor, ruta, query=None, tono="normal", ayuda=None):
        tarjetas.append({"clave": clave, "titulo": titulo, "valor": valor, "ruta": ruta,
                         "query": query or {}, "tono": tono if valor else "neutro", "ayuda": ayuda})

    def contar_facturas(*condiciones):
        consulta = select(func.count(Factura.id)).where(*condiciones)
        if prov:
            consulta = consulta.where(Factura.proveedor_id == prov)
        return db.scalar(consulta) or 0

    ocs = listar_ordenes(db, user, proveedor_id=prov, solo_disponible=True, size=1)["total"]
    tarjeta("ocs", "OCs con saldo por facturar", ocs, "/ordenes", {"solo_disponible": "1"})
    tarjeta("borradores", "Facturas en borrador", contar_facturas(Factura.estado == "BORRADOR"),
            "/facturas", {"estado": "BORRADOR"})
    tarjeta("correccion", "Facturas en corrección", contar_facturas(Factura.estado == "EN_CORRECCION"),
            "/facturas", {"estado": "EN_CORRECCION"}, "alerta")

    pl_incompletos = select(func.count(PackingList.id)).join(Factura).where(
        PackingList.estado.in_(EDITABLE_PL), Factura.estado != "CANCELADA")
    if prov:
        pl_incompletos = pl_incompletos.where(Factura.proveedor_id == prov)
    tarjeta("pl", "Packing lists sin finalizar", db.scalar(pl_incompletos) or 0,
            "/facturas", {"vista": "pl_incompletos"})

    limite = ahora() - timedelta(days=settings.DIAS_ALERTA_BORRADOR)
    tarjeta("antiguos", f"Borradores con más de {settings.DIAS_ALERTA_BORRADOR} días",
            contar_facturas(Factura.estado == "BORRADOR", Factura.creado_en < limite),
            "/facturas", {"vista": "borradores_antiguos"}, "alerta",
            "Siguen reservando cantidades de las OCs.")

    if es_interno(user):
        listas = listar_facturas(db, user, proveedor_id=prov, vista="lista_transporte", size=1)["total"]
        tarjeta("listas", "Facturas listas para asignar a transporte", listas,
                "/facturas", {"vista": "lista_transporte"}, "exito")
        sin_unidad = select(func.count(PackingList.id)).join(Factura).where(
            PackingList.estado == "FINALIZADO", PackingList.unidad_carga_id.is_(None))
        if prov:
            sin_unidad = sin_unidad.where(Factura.proveedor_id == prov)
        tarjeta("sin_unidad", "PL finalizados sin unidad de carga", db.scalar(sin_unidad) or 0,
                "/facturas", {"vista": "pl_sin_unidad"})
        tentativas = select(func.count(PackingList.id)).join(Factura).where(
            PackingList.asignacion == "TENTATIVA", PackingList.estado != "CANCELADO")
        if prov:
            tentativas = tentativas.where(Factura.proveedor_id == prov)
        tarjeta("tentativas", "Asignaciones tentativas por confirmar", db.scalar(tentativas) or 0,
                "/transporte", {"estado": "PLANIFICADO"}, "alerta")
        transito = db.scalar(select(func.count(Embarque.id)).where(Embarque.estado == "EN_TRANSITO")) or 0
        tarjeta("transito", "Embarques en tránsito", transito, "/transporte", {"estado": "EN_TRANSITO"})
    return {"tarjetas": tarjetas, "alertas": listar_alertas(db, user, prov) if es_interno(user) else []}


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
    return {"id": u.id, "email": u.email, "nombre": u.nombre, "rol": u.rol, "activo": u.activo,
            "proveedor_id": u.proveedor_id, "proveedor": u.proveedor.nombre if u.proveedor else None}


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
    u = Usuario(email=email, nombre=datos.nombre.strip(), rol=datos.rol,
                proveedor_id=datos.proveedor_id if datos.rol == "proveedor" else None,
                password_hash=hash_password(datos.password), activo=True)
    db.add(u)
    db.flush()
    return {"id": u.id}


def actualizar_usuario(db: Session, user: Usuario, usuario_id: int, datos) -> dict:
    exigir(user, "admin")
    u = db.get(Usuario, usuario_id)
    if not u:
        raise ErrorNegocio("El usuario no existe.", 404, "no_encontrado")
    campos = datos.model_dump(exclude_unset=True)
    if "password" in campos:
        pw = campos.pop("password")
        if pw:
            u.password_hash = hash_password(pw)
    for k, v in campos.items():
        setattr(u, k, v)
    if u.rol == "proveedor" and not u.proveedor_id:
        raise ErrorNegocio("Un usuario proveedor debe tener proveedor asignado.", 422, "validacion")
    if u.rol != "proveedor":
        u.proveedor_id = None
    return {"ok": True}
