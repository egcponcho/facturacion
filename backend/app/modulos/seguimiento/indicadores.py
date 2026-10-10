"""Indicadores de cada módulo (tableros).

Cada indicador dice qué mide (fórmula), de dónde sale el dato (fuente), si es
una foto de hoy o cuenta lo que pasó en el período elegido, en qué se expresa
y qué permiso hace falta para verlo. Se calcula siempre con el alcance de datos
del usuario (sus proveedores, sociedades y transportistas): un proveedor ve sus
propios números, nunca los de la empresa completa.

Qué indicadores ve cada persona y en qué orden: los que eligió; si no eligió,
los que la administración dejó para su rol; si tampoco, todos los que su rol
puede ver.
"""
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.empresa import configuracion_actual
from app.core.errores import ErrorNegocio
from app.modelos import (
    Embarque,
    Factura,
    FacturaLinea,
    OrdenCompra,
    PackingList,
    PLLinea,
    PosicionOC,
    Producto,
    RecepcionLinea,
    Rol,
    Usuario,
)
from app.modulos.acceso.permisos import exigir, proveedor_filtro, sociedad_filtro, tiene
from app.modulos.comun.historial import registrar

MODULOS = {"compras": "Purchasing", "facturacion": "Invoicing and packing", "logistica": "Logistics",
           "productos": "Products and classification"}
PERIODOS = (7, 30, 90, 365)


@dataclass(frozen=True)
class Indicador:
    clave: str
    modulo: str
    titulo: str
    formula: str
    fuente: str
    momento: str  # "hoy" (foto del estado actual) | "periodo" (lo ocurrido en el período elegido)
    formato: str  # numero | moneda | porcentaje | dias
    permiso: str
    calcular: Callable
    ruta: str | None = None  # la lista que lo explica
    mejor: str = ""  # "alto" | "bajo": qué dirección es buena (para leer la variación)
    grupo: str | None = None  # dato reservado (acceso/visibilidad.py): un rol que no lo ve no ve el indicador


# ---- Alcance de datos -------------------------------------------------------------------
def _oc(user: Usuario) -> list:
    prov = proveedor_filtro(user)
    return ([OrdenCompra.proveedor_id.in_(prov)] if prov is not None else []) + sociedad_filtro(user, OrdenCompra.sociedad)


def _fact(user: Usuario) -> list:
    prov = proveedor_filtro(user)
    return ([Factura.proveedor_id.in_(prov)] if prov is not None else []) + sociedad_filtro(user, Factura.sociedad)


def _emb(db: Session, user: Usuario) -> list:
    from app.modulos.transporte.transporte import condiciones_alcance

    return condiciones_alcance(db, user)


def _prod(user: Usuario) -> list:
    prov = proveedor_filtro(user)
    return [Producto.proveedor_id.in_(prov)] if prov is not None else []


def _rango(desde: date, hasta: date) -> tuple[datetime, datetime]:
    return datetime.combine(desde, datetime.min.time()), datetime.combine(hasta + timedelta(days=1), datetime.min.time())


def _moneda_base() -> str | None:
    from app.modulos.compras.ordenes import moneda_base

    return moneda_base()


def _promedio(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 1) if valores else None


def _dias(a, b) -> float:
    return (b - a).total_seconds() / 86400 if isinstance(a, datetime) else float((b - a).days)


# ---- Compras ------------------------------------------------------------------------------
def oc_en_aprobacion(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(OrdenCompra).where(OrdenCompra.estado == "EN_APROBACION", *_oc(user)))


def oc_aprobadas(db, user, desde, hasta):
    a, b = _rango(desde, hasta)
    return db.scalar(select(func.count()).select_from(OrdenCompra).where(
        OrdenCompra.aprobada_en >= a, OrdenCompra.aprobada_en < b, *_oc(user)))


def dias_aprobacion(db, user, desde, hasta):
    a, b = _rango(desde, hasta)
    filas = db.execute(select(OrdenCompra.enviada_en, OrdenCompra.aprobada_en).where(
        OrdenCompra.aprobada_en >= a, OrdenCompra.aprobada_en < b, OrdenCompra.enviada_en.is_not(None), *_oc(user))).all()
    return _promedio([max(_dias(e, ap), 0) for e, ap in filas])


def _facturado_por_posicion():
    return (select(FacturaLinea.posicion_oc_id.label("pid"), func.sum(FacturaLinea.cantidad).label("cant"))
            .join(Factura, Factura.id == FacturaLinea.factura_id).where(Factura.estado != "CANCELADA")
            .group_by(FacturaLinea.posicion_oc_id).subquery())


def saldo_por_facturar(db, user, desde, hasta):
    base = _moneda_base()
    fac = _facturado_por_posicion()
    pendiente = (PosicionOC.cantidad - func.coalesce(fac.c.cant, 0)) * PosicionOC.precio
    total = db.scalar(select(func.sum(pendiente)).select_from(PosicionOC)
                      .join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id).outerjoin(fac, fac.c.pid == PosicionOC.id)
                      .where(OrdenCompra.estado == "APROBADA", OrdenCompra.moneda == base, PosicionOC.precio.is_not(None),
                             PosicionOC.cantidad > func.coalesce(fac.c.cant, 0), *_oc(user)))
    return round(float(total or 0), 2)


def oc_atrasadas(db, user, desde, hasta):
    fac = _facturado_por_posicion()
    con_saldo = (select(PosicionOC.oc_id).outerjoin(fac, fac.c.pid == PosicionOC.id)
                 .where(PosicionOC.cantidad > func.coalesce(fac.c.cant, 0)))
    return db.scalar(select(func.count()).select_from(OrdenCompra).where(
        OrdenCompra.estado == "APROBADA", OrdenCompra.fecha_xf < date.today(), OrdenCompra.id.in_(con_saldo), *_oc(user)))


# ---- Facturación y empaque -------------------------------------------------------------------
def facturas_finalizadas(db, user, desde, hasta):
    a, b = _rango(desde, hasta)
    return db.scalar(select(func.count()).select_from(Factura).where(
        Factura.finalizado_en >= a, Factura.finalizado_en < b, Factura.estado != "CANCELADA", *_fact(user)))


def facturas_abiertas(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(Factura).where(
        Factura.estado.in_(("BORRADOR", "EN_CORRECCION")), *_fact(user)))


def importe_facturado(db, user, desde, hasta):
    a, b = _rango(desde, hasta)
    total = db.scalar(select(func.sum(FacturaLinea.cantidad * FacturaLinea.precio_unitario))
                      .join(Factura, Factura.id == FacturaLinea.factura_id)
                      .where(Factura.finalizado_en >= a, Factura.finalizado_en < b, Factura.estado != "CANCELADA",
                             Factura.moneda == _moneda_base(), *_fact(user)))
    return round(float(total or 0), 2)


def pls_pendientes(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(PackingList).join(Factura, Factura.id == PackingList.factura_id)
                     .where(PackingList.estado.in_(("BORRADOR", "EN_CORRECCION")), Factura.estado != "CANCELADA", *_fact(user)))


# ---- Logística ---------------------------------------------------------------------------------
def embarques_en_transito(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(Embarque).where(Embarque.estado == "EN_TRANSITO", *_emb(db, user)))


def arribos(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(Embarque).where(
        Embarque.arribo_real >= desde, Embarque.arribo_real <= hasta, Embarque.estado != "CANCELADO", *_emb(db, user)))


def puntualidad(db, user, desde, hasta):
    filas = db.execute(select(Embarque.arribo_real, Embarque.eta).where(
        Embarque.arribo_real >= desde, Embarque.arribo_real <= hasta, Embarque.eta.is_not(None),
        Embarque.estado != "CANCELADO", *_emb(db, user))).all()
    return round(100 * sum(1 for r, e in filas if r <= e) / len(filas), 1) if filas else None


def dias_transito(db, user, desde, hasta):
    filas = db.execute(select(Embarque.salida_real, Embarque.arribo_real).where(
        Embarque.arribo_real >= desde, Embarque.arribo_real <= hasta, Embarque.salida_real.is_not(None),
        Embarque.estado != "CANCELADO", *_emb(db, user))).all()
    return _promedio([max(_dias(s, r), 0) for s, r in filas])


def recepcion_con_diferencias(db, user, desde, hasta):
    a, b = _rango(desde, hasta)
    filas = db.execute(select(PLLinea.cantidad, RecepcionLinea.cantidad_recibida, RecepcionLinea.cantidad_danada)
                       .join(PLLinea, PLLinea.id == RecepcionLinea.pl_linea_id)
                       .join(FacturaLinea, FacturaLinea.id == PLLinea.factura_linea_id)
                       .join(Factura, Factura.id == FacturaLinea.factura_id)
                       .where(RecepcionLinea.fecha >= a, RecepcionLinea.fecha < b, *_fact(user))).all()
    if not filas:
        return None
    return round(100 * sum(1 for esp, rec, dan in filas if abs(float(esp) - float(rec)) > 1e-9 or float(dan or 0) > 0) / len(filas), 1)


# ---- Productos y clasificación --------------------------------------------------------------------
def fichas_en_revision(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(Producto).where(Producto.estado == "revision", *_prod(user)))


def fichas_devueltas(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(Producto).where(Producto.estado == "observado", *_prod(user)))


def fichas_aprobadas(db, user, desde, hasta):
    a, b = _rango(desde, hasta)
    return db.scalar(select(func.count()).select_from(Producto).where(
        Producto.revisado_en >= a, Producto.revisado_en < b, Producto.estado.in_(("aprobado", "corregido")), *_prod(user)))


def sin_clasificar(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(Producto).where(
        Producto.estado.in_(("borrador", "sugerida")), *_prod(user)))


HOY = "hoy"
PERIODO = "periodo"
CATALOGO = [
    Indicador("oc_en_aprobacion", "compras", "POs pending approval", "Count of purchase orders in the state Pending approval.",
              "Purchase orders", HOY, "numero", "oc.ver", oc_en_aprobacion, "/ordenes?estado=EN_APROBACION&solo_disponible=0", "bajo"),
    Indicador("oc_aprobadas", "compras", "POs approved", "Count of purchase orders whose approval date falls in the period.",
              "Purchase orders (approval date)", PERIODO, "numero", "oc.ver", oc_aprobadas, "/ordenes?estado=APROBADA&solo_disponible=0", "alto"),
    Indicador("dias_aprobacion", "compras", "Days to approve", "Average days between sending a PO and its final approval, for the POs approved in the period.",
              "Purchase orders (sent and approval dates)", PERIODO, "dias", "oc.ver", dias_aprobacion, None, "bajo"),
    Indicador("saldo_por_facturar", "compras", "Balance to invoice", "Sum of (ordered − invoiced quantity) × unit price of the lines of approved POs in the base currency; cancelled invoices do not count.",
              "Purchase order lines and invoice lines", HOY, "moneda", "oc.ver", saldo_por_facturar, "/ordenes", "", "precios"),
    Indicador("oc_atrasadas", "compras", "POs past their ship date", "Count of approved POs whose ship date (XF) has passed and that still have quantity to invoice.",
              "Purchase orders and invoice lines", HOY, "numero", "oc.ver", oc_atrasadas, "/seguimiento", "bajo"),
    Indicador("facturas_finalizadas", "facturacion", "Invoices finalized", "Count of invoices finalized in the period (cancelled ones excluded).",
              "Invoices (finalization date)", PERIODO, "numero", "factura.ver", facturas_finalizadas, "/facturas?estado=FINALIZADA", "alto"),
    Indicador("importe_facturado", "facturacion", "Amount invoiced", "Sum of quantity × invoice unit price of the invoices finalized in the period, in the base currency.",
              "Invoice lines (finalization date)", PERIODO, "moneda", "factura.ver", importe_facturado, "/facturas?estado=FINALIZADA", "alto",
              "precios"),
    Indicador("facturas_abiertas", "facturacion", "Invoices in progress", "Count of invoices in draft or under correction.",
              "Invoices", HOY, "numero", "factura.ver", facturas_abiertas, "/facturas?vista=editables", ""),
    Indicador("pls_pendientes", "facturacion", "Packing lists in progress", "Count of packing lists in draft or under correction of invoices that are not cancelled.",
              "Packing lists", HOY, "numero", "factura.ver", pls_pendientes, "/facturas?vista=pl_incompletos", "bajo"),
    Indicador("embarques_en_transito", "logistica", "Shipments in transit", "Count of shipments in the state In transit.",
              "Shipments", HOY, "numero", "transporte.gestionar", embarques_en_transito, "/transporte?estado=EN_TRANSITO", ""),
    Indicador("arribos", "logistica", "Arrivals", "Count of shipments whose actual arrival date falls in the period (called off ones excluded).",
              "Shipments (actual arrival)", PERIODO, "numero", "transporte.gestionar", arribos, "/transporte", "alto"),
    Indicador("puntualidad", "logistica", "On-time arrivals", "Shipments that arrived on or before their ETA ÷ shipments with an ETA that arrived in the period × 100.",
              "Shipments (ETA and actual arrival)", PERIODO, "porcentaje", "transporte.gestionar", puntualidad, "/seguimiento?vista=embarques", "alto"),
    Indicador("dias_transito", "logistica", "Days in transit", "Average days between actual departure and actual arrival of the shipments that arrived in the period.",
              "Shipments (actual departure and arrival)", PERIODO, "dias", "transporte.gestionar", dias_transito, "/seguimiento?vista=leadtimes", "bajo"),
    Indicador("recepcion_con_diferencias", "logistica", "Receipts with differences", "Packing list lines received in the period with a quantity different from the packed one or with damaged units ÷ lines received × 100.",
              "Warehouse receipts and packing list lines", PERIODO, "porcentaje", "transporte.gestionar", recepcion_con_diferencias, None, "bajo"),
    Indicador("fichas_en_revision", "productos", "Sheets in review", "Count of technical sheets waiting for review.",
              "Products (technical sheet)", HOY, "numero", "producto.ver", fichas_en_revision, "/productos?estado=revision", "bajo"),
    Indicador("fichas_devueltas", "productos", "Sheets returned", "Count of technical sheets returned to be corrected.",
              "Products (technical sheet)", HOY, "numero", "producto.ver", fichas_devueltas, "/productos?estado=observado", "bajo"),
    Indicador("fichas_aprobadas", "productos", "Sheets approved", "Count of technical sheets approved (or corrected and approved) whose review date falls in the period.",
              "Products (review date)", PERIODO, "numero", "producto.ver", fichas_aprobadas, "/productos", "alto"),
    Indicador("sin_clasificar", "productos", "Products not classified", "Count of products whose sheet is still in draft (complete or not) and has no approved HS code.",
              "Products (technical sheet)", HOY, "numero", "producto.ver", sin_clasificar, "/productos?estado=borrador", "bajo"),
]
POR_CLAVE = {i.clave: i for i in CATALOGO}


# ---- Qué ve cada persona -------------------------------------------------------------------------
def _del_modulo(user: Usuario, modulo: str) -> list[Indicador]:
    from app.modulos.acceso import visibilidad

    return [i for i in CATALOGO if i.modulo == modulo and tiene(user, i.permiso) and not (i.grupo and visibilidad.oculto(i.grupo))]


def modulos(user: Usuario) -> list[dict]:
    return [{"clave": k, "titulo": v} for k, v in MODULOS.items() if _del_modulo(user, k)]


def _de_rol(rol_id: int | None, modulo: str) -> list[str] | None:
    return ((configuracion_actual().get("indicadores_rol") or {}).get(str(rol_id)) or {}).get(modulo)


def elegidos(user: Usuario, modulo: str) -> tuple[list[str], str]:
    posibles = [i.clave for i in _del_modulo(user, modulo)]
    propios = ((user.preferencias or {}).get("indicadores") or {}).get(modulo)
    if propios is not None:
        return [c for c in propios if c in posibles], "usuario"
    del_rol = _de_rol(user.rol_id, modulo)
    if del_rol is not None:
        return [c for c in del_rol if c in posibles], "rol"
    return posibles, "sistema"


def _limpiar(user: Usuario, modulo: str, claves) -> list[str]:
    if modulo not in MODULOS:
        raise ErrorNegocio("Unknown module.", 404, "no_encontrado")
    if not isinstance(claves, list):
        raise ErrorNegocio("Choose the indicators.", 422, "validacion")
    validas = {i.clave for i in CATALOGO if i.modulo == modulo}
    if set(claves) - validas:
        raise ErrorNegocio("Unknown indicator.", 422, "validacion")
    return list(dict.fromkeys(claves))


def guardar_propios(db: Session, user: Usuario, modulo: str, claves) -> dict:
    """Los indicadores de la persona, en su orden (null: vuelve a los de su rol)."""
    from app.modulos.acceso.preferencias import usar

    pref = dict(user.preferencias or {})
    todos = dict(pref.get("indicadores") or {})
    if claves is None:
        todos.pop(modulo, None)
    else:
        todos[modulo] = _limpiar(user, modulo, claves)
    pref["indicadores"] = todos
    user.preferencias = pref
    usar(user)
    return {"elegidos": elegidos(user, modulo)[0]}


def guardar_de_rol(db: Session, user: Usuario, modulo: str, rol_id: int, claves) -> dict:
    """Los indicadores de un rol (administración): los ve quien no eligió los suyos."""
    from app.modulos.empresa.organizacion import actual

    exigir(user, "admin")
    if not db.get(Rol, rol_id):
        raise ErrorNegocio("The role does not exist.", 404, "no_encontrado")
    org = actual(db)
    conf = dict(org.configuracion or {})
    por_rol = {k: dict(v) for k, v in (conf.get("indicadores_rol") or {}).items()}
    del_rol = por_rol.setdefault(str(rol_id), {})
    if claves is None:
        del_rol.pop(modulo, None)
    else:
        del_rol[modulo] = _limpiar(user, modulo, claves)
    conf["indicadores_rol"] = {k: v for k, v in por_rol.items() if v}
    org.configuracion = conf
    registrar(db, user, "organizacion", org.id, "indicadores_rol", {"rol_id": rol_id, "modulo": modulo, "claves": claves})
    db.flush()
    return {"ok": True}


# ---- Tablero ---------------------------------------------------------------------------------------
def tablero(db: Session, user: Usuario, modulo: str, dias: int = 30) -> dict:
    if modulo not in MODULOS:
        raise ErrorNegocio("Unknown module.", 404, "no_encontrado")
    disponibles = _del_modulo(user, modulo)
    if not disponibles:
        raise ErrorNegocio("You do not have access to these indicators.", 403, "sin_permiso")
    dias = dias if dias in PERIODOS else 30
    hasta = date.today()
    desde = hasta - timedelta(days=dias - 1)
    antes_hasta = desde - timedelta(days=1)
    antes_desde = antes_hasta - timedelta(days=dias - 1)
    claves, origen = elegidos(user, modulo)
    res = []
    for clave in claves:
        i = POR_CLAVE[clave]
        valor = i.calcular(db, user, desde, hasta)
        anterior = i.calcular(db, user, antes_desde, antes_hasta) if i.momento == PERIODO else None
        res.append({"clave": i.clave, "valor": valor, "anterior": anterior, "ruta": i.ruta})
    return {
        "modulo": modulo, "titulo": MODULOS[modulo], "modulos": modulos(user),
        "periodo": {"dias": dias, "desde": desde, "hasta": hasta, "anterior_desde": antes_desde, "anterior_hasta": antes_hasta},
        "moneda_base": _moneda_base(), "origen": origen, "elegidos": claves,
        "catalogo": [{"clave": i.clave, "titulo": i.titulo, "formula": i.formula, "fuente": i.fuente, "momento": i.momento,
                      "formato": i.formato, "mejor": i.mejor} for i in disponibles],
        "indicadores": res,
    }
