"""Edición exclusiva: una persona edita un documento y las demás lo ven en
solo lectura.

- Al abrir un documento editable, la pantalla pide el permiso de edición
  (`tomar`) y lo renueva cada 30 s. Si se cierra la pestaña o se pierde la
  conexión, vence solo a los VIGENCIA segundos.
- Quien llega mientras otro edita recibe 423 `en_edicion` con quién y desde
  cuándo, y el detalle del documento le llega con `puede.editar = False`.
- El servidor rechaza al guardar cualquier cambio de un documento (o de sus
  partes: líneas, cajas, unidades, eventos…) que otra persona tiene tomado.
  La verificación es central (antes de cada flush), así ninguna ruta se
  salta la regla.
- Un administrador puede liberar el permiso de otro; queda en el historial.
"""
from contextvars import ContextVar
from datetime import timedelta

from sqlalchemy import delete, event, inspect, select, tuple_
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Archivo,
    Edicion,
    Embarque,
    EventoEmbarque,
    Factura,
    FacturaLinea,
    GrupoCajas,
    GrupoCajasItem,
    OrdenCompra,
    PackingList,
    PartidaPais,
    PLLinea,
    PosicionOC,
    Producto,
    ProductoDocumento,
    ProductoFoto,
    UnidadCarga,
    Usuario,
    ahora,
)
from app.modulos.acceso.permisos import permisos_de
from app.modulos.comun.historial import registrar

VIGENCIA = 120  # segundos sin renovar para que el permiso venza

ENTIDADES = {"factura": Factura, "packing_list": PackingList, "embarque": Embarque, "producto": Producto,
             "orden": OrdenCompra}

# Para cada tabla: a qué documento pertenece (entidad y cómo obtener su id)
_RAIZ = {
    Factura: ("factura", lambda db, o: o.id),
    FacturaLinea: ("factura", lambda db, o: o.factura_id),
    Archivo: ("factura", lambda db, o: o.factura_id),
    PackingList: ("packing_list", lambda db, o: o.id),
    PLLinea: ("packing_list", lambda db, o: o.pl_id),
    GrupoCajas: ("packing_list", lambda db, o: o.pl_id),
    GrupoCajasItem: ("packing_list", lambda db, o: (db.get(GrupoCajas, o.grupo_id) or GrupoCajas()).pl_id),
    Embarque: ("embarque", lambda db, o: o.id),
    UnidadCarga: ("embarque", lambda db, o: o.embarque_id),
    EventoEmbarque: ("embarque", lambda db, o: o.embarque_id),
    Producto: ("producto", lambda db, o: o.id),
    PartidaPais: ("producto", lambda db, o: o.producto_id),
    ProductoFoto: ("producto", lambda db, o: o.producto_id),
    ProductoDocumento: ("producto", lambda db, o: o.producto_id),
    OrdenCompra: ("orden", lambda db, o: o.id),
    PosicionOC: ("orden", lambda db, o: o.oc_id),
}
# Cambios que no son edición del documento (los hace el sistema al tocar otro)
_NO_CUENTAN = {"version", "actualizado_en"}

# Usuario de la petición en curso (lo fija la dependencia de la ruta). Sin
# usuario (semilla, migraciones, tareas internas) no se verifica.
_usuario: ContextVar[int | None] = ContextVar("usuario_edicion", default=None)


def usar_usuario(usuario_id: int | None) -> None:
    _usuario.set(usuario_id)


def _vigente(db: Session, entidad: str, entidad_id: int) -> Edicion | None:
    e = db.scalar(select(Edicion).where(Edicion.entidad == entidad, Edicion.entidad_id == entidad_id))
    return e if e and e.vence > ahora() else None


def _info(e: Edicion) -> dict:
    return {"usuario_id": e.usuario_id, "usuario": e.usuario.nombre if e.usuario else None,
            "desde": e.desde.isoformat(), "vence": e.vence.isoformat()}


def _error(e: Edicion) -> ErrorNegocio:
    nombre = e.usuario.nombre if e.usuario else "Another user"
    return ErrorNegocio(f"{nombre} is editing this document. You can see it in read-only mode until they finish.",
                        423, "en_edicion", _info(e))


def _verificar_acceso(db: Session, user: Usuario, entidad: str, entidad_id: int) -> None:
    """Solo pide el permiso quien puede ver el documento."""
    if entidad == "factura":
        from app.modulos.facturacion.facturas import cargar_factura
        cargar_factura(db, user, entidad_id)
    elif entidad == "packing_list":
        from app.modulos.empaque.packing import cargar_pl
        cargar_pl(db, user, entidad_id)
    elif entidad == "embarque":
        from app.modulos.transporte.transporte import _embarque
        _embarque(db, user, entidad_id)
    elif entidad == "producto":
        from app.modulos.productos.productos import _producto
        _producto(db, user, entidad_id)
    elif entidad == "orden":
        from app.modulos.acceso.permisos import asegurar_proveedor
        oc = db.get(OrdenCompra, entidad_id)
        if not oc:
            raise ErrorNegocio("The purchase order does not exist.", 404, "no_encontrado")
        asegurar_proveedor(user, oc.proveedor_id)
    else:
        raise ErrorNegocio("Unknown document type.", 404, "no_encontrado")


def estado(db: Session, user: Usuario, entidad: str, entidad_id: int) -> dict:
    _verificar_acceso(db, user, entidad, entidad_id)
    e = _vigente(db, entidad, entidad_id)
    return {"editando": _info(e) if e else None, "propio": bool(e and e.usuario_id == user.id)}


def ajeno(db: Session, user: Usuario, entidad: str, entidad_id: int) -> dict | None:
    """Quién edita el documento, si es otra persona (para el detalle)."""
    e = _vigente(db, entidad, entidad_id)
    return _info(e) if e and e.usuario_id != user.id else None


def tomar(db: Session, user: Usuario, entidad: str, entidad_id: int) -> dict:
    """Toma o renueva el permiso de edición."""
    _verificar_acceso(db, user, entidad, entidad_id)
    e = db.scalar(select(Edicion).where(Edicion.entidad == entidad, Edicion.entidad_id == entidad_id).with_for_update())
    momento = ahora()
    if e and e.vence > momento and e.usuario_id != user.id:
        raise _error(e)
    if e is None:
        e = Edicion(entidad=entidad, entidad_id=entidad_id, usuario_id=user.id, desde=momento)
        db.add(e)
    elif e.usuario_id != user.id or e.vence <= momento:
        e.usuario_id, e.desde = user.id, momento
    e.vence = momento + timedelta(seconds=VIGENCIA)
    db.flush()
    return {"propio": True, "desde": e.desde, "vence": e.vence, "vigencia": VIGENCIA}


def liberar(db: Session, user: Usuario, entidad: str, entidad_id: int, forzar: bool = False) -> dict:
    e = db.scalar(select(Edicion).where(Edicion.entidad == entidad, Edicion.entidad_id == entidad_id))
    if not e:
        return {"liberado": False}
    if e.usuario_id != user.id:
        if not forzar:
            return {"liberado": False}
        if "admin" not in permisos_de(user):
            raise ErrorNegocio("Only an administrator can release someone else's editing.", 403, "sin_permiso")
        if e.vence > ahora():
            registrar(db, user, entidad, entidad_id, "liberar_edicion",
                      detalle={"usuario_id": e.usuario_id, "usuario": e.usuario.nombre if e.usuario else None},
                      factura_id=entidad_id if entidad == "factura" else None)
    db.delete(e)
    db.flush()
    return {"liberado": True}


def liberar_de_usuario(db: Session, usuario_id: int) -> None:
    db.execute(delete(Edicion).where(Edicion.usuario_id == usuario_id))


def _tocados(db: Session, session: Session) -> set[tuple[str, int]]:
    tocados = set()
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        raiz = _RAIZ.get(type(obj))
        if not raiz:
            continue
        if obj in session.dirty:
            cambios = {a.key for a in inspect(obj).attrs if a.history.has_changes()}
            if not cambios - _NO_CUENTAN:
                continue
        entidad, id_de = raiz
        try:
            entidad_id = id_de(db, obj)
        except Exception:
            entidad_id = None
        if entidad_id:
            tocados.add((entidad, entidad_id))
    return tocados


@event.listens_for(Session, "before_flush")
def _verificar_al_guardar(session: Session, _ctx, _instancias) -> None:
    usuario_id = _usuario.get()
    if not usuario_id:
        return
    tocados = _tocados(session, session)
    if not tocados:
        return
    with session.no_autoflush:
        e = session.scalar(select(Edicion).where(
            tuple_(Edicion.entidad, Edicion.entidad_id).in_(list(tocados)),
            Edicion.usuario_id != usuario_id, Edicion.vence > ahora()))
    if e:
        raise _error(e)
