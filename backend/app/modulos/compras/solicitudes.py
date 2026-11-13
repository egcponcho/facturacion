"""Solicitudes de compra: lo que piden las áreas antes de la orden de compra.

Ciclo:
    PENDIENTE  ─aprobar→  APROBADA  ─convertir→  CONVERTIDA (enlazada a su OC)
        │  └─rechazar→  RECHAZADA  ─editar→  PENDIENTE (se vuelve a enviar)
        └─cancelar→  CANCELADA (también desde RECHAZADA o APROBADA)

- Quien tiene «solicitud.crear» crea y corrige solicitudes; quien tiene
  «solicitud.aprobar» las aprueba, rechaza (con comentario) y las convierte.
- Convertir junta una o varias solicitudes aprobadas en una OC en borrador del
  proveedor elegido (el asistente de la OC sigue desde ahí). Las líneas pasan
  con su código, cantidad, unidad y precio estimado.
- El total estimado va en la moneda de la solicitud (por omisión, la de la
  empresa).
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import dinero, numeracion
from app.core.empresa import configuracion_actual
from app.core.errores import ErrorNegocio
from app.modelos import Moneda, Proveedor, SolicitudCompra, SolicitudLinea, Usuario, ahora
from app.modulos.acceso.permisos import exigir, exigir_alguno, tiene
from app.modulos.compras import flujo_oc
from app.modulos.comun.historial import registrar

VISTAS = ("por_aprobar", "aprobadas", "todas")
EDITABLES = ("PENDIENTE", "RECHAZADA")
CANCELABLES = ("PENDIENTE", "RECHAZADA", "APROBADA")
LIMITE = 1000


# ---- Lectura -------------------------------------------------------------------

def _total(s: SolicitudCompra):
    return dinero.total(((ln.cantidad, ln.precio_estimado) for ln in s.lineas if ln.precio_estimado is not None), s.moneda)


def _fila(s: SolicitudCompra, con_lineas: bool = False) -> dict:
    fila = {
        "id": s.id, "numero": s.numero, "area": s.area, "centro": s.centro, "fecha": s.fecha,
        "fecha_requerida": s.fecha_requerida, "prioridad": s.prioridad, "estado": s.estado,
        "solicitante": s.solicitante.nombre if s.solicitante else None, "solicitante_id": s.solicitante_id,
        "proveedor": {"id": s.proveedor.id, "codigo": s.proveedor.codigo, "nombre": s.proveedor.nombre} if s.proveedor else None,
        "moneda": s.moneda, "articulos": len(s.lineas), "estimado": dinero.numero(_total(s)),
        "oc": {"id": s.oc.id, "numero": s.oc.numero} if s.oc else None,
    }
    if con_lineas:
        fila.update({
            "motivo": s.motivo, "comentario_revision": s.comentario_revision, "revisada_en": s.revisada_en,
            "lineas": [{"id": ln.id, "codigo_articulo": ln.codigo_articulo, "descripcion": ln.descripcion,
                        "cantidad": dinero.numero(dinero.decimal(ln.cantidad)), "unidad": ln.unidad,
                        "precio_estimado": dinero.numero(dinero.decimal(ln.precio_estimado)) if ln.precio_estimado is not None else None}
                       for ln in s.lineas],
        })
    return fila


def _en_vista(s: SolicitudCompra, vista: str) -> bool:
    return {"por_aprobar": s.estado == "PENDIENTE", "aprobadas": s.estado == "APROBADA"}.get(vista, True)


def _consulta():
    return select(SolicitudCompra).options(selectinload(SolicitudCompra.lineas), selectinload(SolicitudCompra.solicitante),
                                           selectinload(SolicitudCompra.proveedor), selectinload(SolicitudCompra.oc))


def lista(db: Session, user: Usuario, vista: str = "por_aprobar") -> dict:
    exigir(user, "solicitud.ver")
    vista = vista if vista in VISTAS else "por_aprobar"
    todas = db.scalars(_consulta().order_by(SolicitudCompra.fecha.desc(), SolicitudCompra.id.desc()).limit(LIMITE)).all()
    return {
        "items": [_fila(s) for s in todas if _en_vista(s, vista)],
        "cuentas": {v: sum(1 for s in todas if _en_vista(s, v)) for v in VISTAS},
        "truncado": len(todas) == LIMITE,
    }


def _cargar(db: Session, solicitud_id: int, bloquear: bool = False) -> SolicitudCompra:
    consulta = _consulta().where(SolicitudCompra.id == solicitud_id)
    s = db.scalar(consulta.with_for_update() if bloquear else consulta)
    if s is None:
        raise ErrorNegocio("Document not found.", 404, "no_encontrado")
    return s


def detalle(db: Session, user: Usuario, solicitud_id: int) -> dict:
    exigir(user, "solicitud.ver")
    s = _cargar(db, solicitud_id)
    fila = _fila(s, con_lineas=True)
    fila["puede"] = {
        "editar": s.estado in EDITABLES and tiene(user, "solicitud.crear"),
        "aprobar": s.estado == "PENDIENTE" and tiene(user, "solicitud.aprobar"),
        "convertir": s.estado == "APROBADA" and tiene(user, "solicitud.aprobar") and tiene(user, "oc.editar"),
        "cancelar": s.estado in CANCELABLES and (tiene(user, "solicitud.aprobar") or s.solicitante_id == user.id),
    }
    return fila


# ---- Crear y editar -------------------------------------------------------------

def _moneda_base(db: Session) -> str | None:
    propia = (configuracion_actual().get("preferencias") or {}).get("moneda")
    return propia or db.scalar(select(Moneda.codigo).where(Moneda.activo.is_(True)).order_by(Moneda.orden, Moneda.codigo).limit(1))


def _numero_siguiente(db: Session) -> str:
    serie = numeracion.asegurar_serie(
        db, "solicitud", "SC", "Purchase requests", "SC-", 4,
        inicial=lambda: numeracion.mayor_sufijo(db.scalars(select(SolicitudCompra.numero)), "SC-") + 1)
    while True:
        n = numeracion.siguiente(db, serie)
        if not db.scalar(select(SolicitudCompra.id).where(SolicitudCompra.numero == n)):
            return n


def _aplicar(db: Session, s: SolicitudCompra, datos: dict) -> None:
    area = (datos.get("area") or "").strip()
    lineas = [x for x in (datos.get("lineas") or []) if (x.get("descripcion") or x.get("codigo_articulo"))]
    errores = []
    if not area:
        errores.append({"campo": "area", "mensaje": "Say which area requests it."})
    if not lineas:
        errores.append({"campo": "lineas", "mensaje": "Add at least one item."})
    for i, x in enumerate(lineas):
        if not x.get("cantidad") or float(x["cantidad"]) <= 0:
            errores.append({"campo": f"lineas.{i}.cantidad", "mensaje": "The quantity must be greater than zero."})
    if errores:
        raise ErrorNegocio("Check the request.", 422, "validacion", errores)
    prov_id = datos.get("proveedor_id")
    if prov_id and not db.get(Proveedor, int(prov_id)):
        raise ErrorNegocio("The supplier does not exist.", 422, "validacion")
    s.area = area[:80]
    s.centro = (datos.get("centro") or "").strip().upper() or None
    s.prioridad = "URGENTE" if datos.get("prioridad") == "URGENTE" else "NORMAL"
    s.fecha_requerida = datos.get("fecha_requerida") or None
    s.proveedor_id = int(prov_id) if prov_id else None
    s.moneda = (datos.get("moneda") or "").strip().upper() or s.moneda or _moneda_base(db)
    s.motivo = (datos.get("motivo") or "").strip()[:500] or None
    s.lineas = [SolicitudLinea(
        codigo_articulo=(x.get("codigo_articulo") or "").strip().upper()[:40] or None,
        descripcion=((x.get("descripcion") or x.get("codigo_articulo") or "").strip())[:300],
        cantidad=x["cantidad"], unidad=(x.get("unidad") or "").strip().upper() or None,
        precio_estimado=x.get("precio_estimado") if x.get("precio_estimado") not in (None, "") else None,
    ) for x in lineas[:200]]


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    """Crea la solicitud y la deja pendiente de aprobación."""
    exigir(user, "solicitud.crear")
    s = SolicitudCompra(numero=_numero_siguiente(db), fecha=date.today(), estado="PENDIENTE", solicitante_id=user.id)
    _aplicar(db, s, datos)
    db.add(s)
    db.flush()
    registrar(db, user, "solicitud", s.id, "crear", {"numero": s.numero})
    return detalle(db, user, s.id)


def editar(db: Session, user: Usuario, solicitud_id: int, datos: dict) -> dict:
    """Corrige una solicitud pendiente o rechazada; una rechazada vuelve a pendiente."""
    exigir(user, "solicitud.crear")
    s = _cargar(db, solicitud_id, bloquear=True)
    if s.estado not in EDITABLES:
        raise ErrorNegocio("Only a pending or rejected request can be edited.", 409, "estado_invalido")
    _aplicar(db, s, datos)
    if s.estado == "RECHAZADA":
        s.estado, s.comentario_revision = "PENDIENTE", None
    s.actualizado_en = ahora()
    registrar(db, user, "solicitud", s.id, "editar_cabecera", None)
    return detalle(db, user, s.id)


# ---- Aprobación ------------------------------------------------------------------

def _revisar(db: Session, user: Usuario, solicitud_id: int, estado: str, comentario: str | None) -> dict:
    exigir(user, "solicitud.aprobar")
    s = _cargar(db, solicitud_id, bloquear=True)
    if s.estado != "PENDIENTE":
        raise ErrorNegocio("Only a pending request can be approved or rejected.", 409, "estado_invalido")
    comentario = (comentario or "").strip()[:500] or None
    if estado == "RECHAZADA" and not comentario:
        raise ErrorNegocio("Say why it is rejected.", 422, "validacion", [{"campo": "comentario", "mensaje": "Say why it is rejected."}])
    s.estado, s.comentario_revision, s.revisada_por, s.revisada_en = estado, comentario, user.id, ahora()
    registrar(db, user, "solicitud", s.id, "aprobar" if estado == "APROBADA" else "rechazar", {"comentario": comentario})
    return detalle(db, user, s.id)


def aprobar(db: Session, user: Usuario, solicitud_id: int, comentario: str | None) -> dict:
    return _revisar(db, user, solicitud_id, "APROBADA", comentario)


def rechazar(db: Session, user: Usuario, solicitud_id: int, comentario: str | None) -> dict:
    return _revisar(db, user, solicitud_id, "RECHAZADA", comentario)


def cancelar(db: Session, user: Usuario, solicitud_id: int) -> dict:
    """La cancela quien aprueba o quien la pidió."""
    exigir_alguno(user, "solicitud.aprobar", "solicitud.crear")
    s = _cargar(db, solicitud_id, bloquear=True)
    if not tiene(user, "solicitud.aprobar") and s.solicitante_id != user.id:
        raise ErrorNegocio("You do not have permission for this action.", 403, "sin_permiso")
    if s.estado not in CANCELABLES:
        raise ErrorNegocio("This request can no longer be cancelled.", 409, "estado_invalido")
    s.estado, s.actualizado_en = "CANCELADA", ahora()
    registrar(db, user, "solicitud", s.id, "cancelar", None)
    return detalle(db, user, s.id)


# ---- Convertir en OC ---------------------------------------------------------------

def convertir(db: Session, user: Usuario, solicitud_ids: list[int], proveedor_id: int, numero_oc: str) -> dict:
    """Junta las solicitudes aprobadas en una OC en borrador del proveedor (el
    asistente de la OC sigue desde ahí) y las deja convertidas y enlazadas."""
    exigir(user, "solicitud.aprobar")
    exigir(user, "oc.editar")
    prov = db.get(Proveedor, proveedor_id)
    if prov is None:
        raise ErrorNegocio("The supplier does not exist.", 422, "validacion")
    solicitudes = [_cargar(db, i, bloquear=True) for i in dict.fromkeys(solicitud_ids)]
    if not solicitudes or any(s.estado != "APROBADA" for s in solicitudes):
        raise ErrorNegocio("Only approved requests can be converted into a PO.", 409, "estado_invalido")
    monedas = {s.moneda for s in solicitudes if s.moneda}
    centros = {s.centro for s in solicitudes if s.centro}
    cabecera = {"proveedor": prov.codigo, "oc": numero_oc.strip(), "fecha_oc": date.today().isoformat(),
                "notas": "; ".join(f"{s.numero}: {s.area}" for s in solicitudes)[:2000]}
    if len(monedas) == 1:
        cabecera["moneda"] = monedas.pop()
    if len(centros) == 1:
        cabecera["centro_destino"] = centros.pop()
    oc_id = flujo_oc.crear_borrador(db, user, cabecera)["oc"]["id"]
    lineas = [{"codigo_articulo": ln.codigo_articulo or "", "cantidad": dinero.numero(dinero.decimal(ln.cantidad)),
               "unidad": ln.unidad, "precio": dinero.numero(dinero.decimal(ln.precio_estimado)) if ln.precio_estimado is not None else None,
               "fecha_entrega": s.fecha_requerida.isoformat() if s.fecha_requerida else None}
              for s in solicitudes for ln in s.lineas]
    flujo_oc.guardar_borrador(db, user, oc_id, {"lineas": lineas})
    for s in solicitudes:
        s.estado, s.oc_id, s.actualizado_en = "CONVERTIDA", oc_id, ahora()
        registrar(db, user, "solicitud", s.id, "convertir", {"oc": numero_oc})
    return {"oc_id": oc_id, "numero": numero_oc.strip()}
