"""Plantillas de caja: medidas y peso de los empaques que se repiten.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import PlantillaCaja, Usuario
from app.modulos.acceso.permisos import exigir, proveedor_filtro, proveedores_de, un_proveedor


def _plantilla_dict(t: PlantillaCaja) -> dict:
    return {c: getattr(t, c) for c in (
        "id", "proveedor_id", "nombre", "cantidad_por_caja", "unidad", "largo", "ancho", "alto",
        "tara", "tipo_empaque_id", "activa")} | {"tipo_empaque": t.tipo_empaque.nombre if t.tipo_empaque else None}


def listar_plantillas(db: Session, user: Usuario, proveedor_id: int | None, incluir_inactivas: bool) -> list[dict]:
    prov = un_proveedor(proveedor_filtro(user, proveedor_id))
    if not prov:
        return []
    consulta = select(PlantillaCaja).where(PlantillaCaja.proveedor_id == prov).order_by(PlantillaCaja.nombre)
    if not incluir_inactivas:
        consulta = consulta.where(PlantillaCaja.activa.is_(True))
    return [_plantilla_dict(t) for t in db.scalars(consulta).all()]


def _validar_tipo(db: Session, tipo_id):
    from app.modelos import TipoEmpaque

    if tipo_id and not db.get(TipoEmpaque, tipo_id):
        raise ErrorNegocio("The packaging type does not exist.", 404, "no_encontrado")


def crear_plantilla(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "plantilla.editar")
    prov = un_proveedor(proveedor_filtro(user, datos.proveedor_id))
    if not prov:
        raise ErrorNegocio("Choose the template's supplier.", 422, "validacion")
    _validar_tipo(db, datos.tipo_empaque_id)
    nombre = datos.nombre.strip()
    if db.scalar(select(PlantillaCaja.id).where(PlantillaCaja.proveedor_id == prov, PlantillaCaja.nombre == nombre)):
        raise ErrorNegocio(f"A template named “{nombre}” already exists.", 409, "duplicado")
    from app.modulos.maestros.unidades import exigir_cantidad, validar

    unidad = validar(datos.unidad)
    exigir_cantidad(datos.cantidad_por_caja, unidad)
    t = PlantillaCaja(**{**datos.model_dump(exclude={"proveedor_id"}), "nombre": nombre, "proveedor_id": prov, "unidad": unidad})
    db.add(t)
    db.flush()
    return _plantilla_dict(t)


def actualizar_plantilla(db: Session, user: Usuario, plantilla_id: int, datos) -> dict:
    """Editar una plantilla no cambia las cajas ya creadas: cada caja guarda sus valores."""
    exigir(user, "plantilla.editar")
    t = db.get(PlantillaCaja, plantilla_id)
    permitidos = proveedores_de(user)
    if not t or (permitidos is not None and t.proveedor_id not in permitidos):
        raise ErrorNegocio("The template does not exist.", 404, "no_encontrado")
    campos = datos.model_dump(exclude_unset=True)
    from app.modulos.maestros.unidades import exigir_cantidad, validar

    if campos.get("unidad") is not None:
        campos["unidad"] = validar(campos["unidad"])
    if campos.get("cantidad_por_caja") is not None or campos.get("unidad"):
        exigir_cantidad(campos.get("cantidad_por_caja", t.cantidad_por_caja), campos.get("unidad") or t.unidad)
    if "nombre" in campos:
        campos["nombre"] = (campos["nombre"] or "").strip()
        if not campos["nombre"]:
            raise ErrorNegocio("The name is required.", 422, "validacion")
        otra = db.scalar(select(PlantillaCaja.id).where(
            PlantillaCaja.proveedor_id == t.proveedor_id, PlantillaCaja.nombre == campos["nombre"],
            PlantillaCaja.id != t.id))
        if otra:
            raise ErrorNegocio(f"A template named “{campos['nombre']}” already exists.", 409, "duplicado")
    _validar_tipo(db, campos.get("tipo_empaque_id"))
    for k, v in campos.items():
        setattr(t, k, v)
    return _plantilla_dict(t)
