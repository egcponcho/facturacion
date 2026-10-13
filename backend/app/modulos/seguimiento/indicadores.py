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

from app.core import dinero
from app.core.empresa import configuracion_actual, regla
from app.core.errores import ErrorNegocio
from app.modelos import (
    AprobacionOC,
    Embarque,
    Factura,
    FacturaLinea,
    Historial,
    OrdenCompra,
    PackingList,
    PLLinea,
    PosicionOC,
    Producto,
    Proveedor,
    RecepcionLinea,
    Rol,
    Usuario,
)
from app.modulos.acceso.permisos import exigir, proveedor_filtro, sociedad_filtro, tiene
from app.modulos.comun.historial import registrar
from app.modulos.seguimiento import metricas

MODULOS = {"resumen": "Summary", "compras": "Purchasing", "facturacion": "Invoicing and packing", "logistica": "Logistics",
           "productos": "Products and classification"}
PERIODOS = (7, 30, 90, 365)
# Cuántos períodos iguales y seguidos se grafican para ver la tendencia
TRAMOS = {7: 8, 30: 6, 90: 4, 365: 3}


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


def _pct(n: int, m: int) -> dict:
    """Porcentaje con su base («n de m»): sin base, sin valor."""
    return {"valor": round(100 * n / m, 1) if m else None, "base": {"n": n, "m": m}}


def _en_moneda_base(por_moneda: dict) -> dict:
    """Importe en la moneda de la empresa y, aparte, las demás monedas (nunca sumadas)."""
    base = _moneda_base()
    return {"valor": dinero.numero(dinero.redondear(por_moneda.get(base, dinero.CERO), base)), "moneda": base,
            "otras": metricas.otras_monedas(por_moneda, base)}


# ---- Compras ------------------------------------------------------------------------------
def oc_en_aprobacion(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(OrdenCompra).where(OrdenCompra.estado == "EN_APROBACION", *_oc(user)))


def oc_aprobadas(db, user, desde, hasta):
    a, b = _rango(desde, hasta)
    return db.scalar(select(func.count()).select_from(OrdenCompra).where(
        OrdenCompra.aprobada_en >= a, OrdenCompra.aprobada_en < b, *_oc(user)))


def dias_aprobacion(db, user, desde, hasta):
    """Desde el primer envío hasta la aprobación final, solo de las OC que
    pasaron por pasos de aprobación (las aprobadas al instante no cuentan)."""
    a, b = _rango(desde, hasta)
    primer_envio = (select(func.min(Historial.fecha)).where(Historial.entidad == "orden", Historial.entidad_id == OrdenCompra.id,
                                                            Historial.accion == "enviada").scalar_subquery())
    con_pasos = select(AprobacionOC.id).where(AprobacionOC.oc_id == OrdenCompra.id).exists()
    filas = db.execute(select(func.coalesce(primer_envio, OrdenCompra.enviada_en), OrdenCompra.aprobada_en).where(
        OrdenCompra.aprobada_en >= a, OrdenCompra.aprobada_en < b, OrdenCompra.enviada_en.is_not(None), con_pasos,
        *_oc(user))).all()
    dias = sorted(max(_dias(_como_dt(e), ap), 0) for e, ap in filas)
    return {"valor": _promedio(dias), "base": {"n": len(dias), "m": len(dias)},
            "mediana": round(dias[len(dias) // 2], 1) if dias else None}


def _como_dt(v):
    return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))


def saldo_por_facturar(db, user, desde, hasta):
    s = metricas.saldo_por_facturar(db, user, proveedor_filtro(user))
    return {**_en_moneda_base(s["valor"]), "ocs": s["ocs"]}


def oc_atrasadas(db, user, desde, hasta):
    return metricas.oc_xf_vencida(db, user, proveedor_filtro(user))


def cumplimiento_xf(db, user, desde, hasta):
    """Recogidas en el período a tiempo frente a la XF original de su OC (más
    la tolerancia de la empresa), por lista de empaque recogida."""
    tolerancia = regla("DIAS_TOLERANCIA_XF") or 0
    filas = db.execute(
        select(PackingList.recolectado_en, OrdenCompra.fecha_xf_original, OrdenCompra.fecha_xf, Proveedor.nombre)
        .join(Factura, Factura.id == PackingList.factura_id).join(Proveedor, Proveedor.id == Factura.proveedor_id)
        .join(FacturaLinea, FacturaLinea.factura_id == Factura.id)
        .join(PosicionOC, PosicionOC.id == FacturaLinea.posicion_oc_id).join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id)
        .where(PackingList.estado != "CANCELADO", PackingList.recolectado_en >= desde, PackingList.recolectado_en <= hasta,
               OrdenCompra.estado.in_(metricas.OC_EN_SEGUIMIENTO), *_fact(user))
        .distinct()
    ).all()
    por_proveedor: dict[str, list] = {}
    n = m = 0
    for recogida, xf_original, xf, nombre in filas:
        meta = xf_original or xf
        if not meta:
            continue
        a_tiempo = (recogida - meta).days <= tolerancia
        n += a_tiempo
        m += 1
        por_proveedor.setdefault(nombre, [0, 0])
        por_proveedor[nombre][0] += a_tiempo
        por_proveedor[nombre][1] += 1
    res = _pct(n, m)
    res["desglose"] = [{"etiqueta": nombre, "valor": round(100 * a / t, 1), "base": {"n": a, "m": t}}
                       for nombre, (a, t) in sorted(por_proveedor.items(), key=lambda x: x[1][0] / x[1][1])][:5]
    return res


# ---- Facturación y empaque -------------------------------------------------------------------
def facturas_finalizadas(db, user, desde, hasta):
    return metricas.facturado(db, user, proveedor_filtro(user), desde, hasta)["facturas"]


def facturas_abiertas(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(Factura).where(
        Factura.estado.in_(("BORRADOR", "EN_CORRECCION")), *_fact(user)))


def importe_facturado(db, user, desde, hasta):
    f = metricas.facturado(db, user, proveedor_filtro(user), desde, hasta)
    return {**_en_moneda_base(f["por_moneda"]), "base": {"n": f["facturas"], "m": f["facturas"]}}


def pls_pendientes(db, user, desde, hasta):
    return db.scalar(select(func.count()).select_from(PackingList).join(Factura, Factura.id == PackingList.factura_id)
                     .where(PackingList.estado.in_(("BORRADOR", "EN_CORRECCION")), Factura.estado != "CANCELADA", *_fact(user)))


# ---- Logística ---------------------------------------------------------------------------------
def embarques_en_transito(db, user, desde, hasta):
    return metricas.embarques_en_transito(db, user, None)["n"]


def arribos(db, user, desde, hasta):
    return metricas.arribos(db, user, None, desde, hasta)["n"]


def puntualidad(db, user, desde, hasta):
    """Contra la ETA comprometida al salir (la ETA puede moverse en ruta) más
    la tolerancia de la empresa."""
    tolerancia = regla("DIAS_TOLERANCIA_ARRIBO") or 0
    meta = func.coalesce(Embarque.eta_comprometida, Embarque.eta)
    filas = db.execute(select(Embarque.arribo_real, meta).where(
        Embarque.arribo_real >= desde, Embarque.arribo_real <= hasta, meta.is_not(None),
        Embarque.estado != "CANCELADO", *_emb(db, user))).all()
    return _pct(sum(1 for r, e in filas if (r - metricas._como_fecha(e)).days <= tolerancia), len(filas))


def dias_transito(db, user, desde, hasta):
    filas = db.execute(select(Embarque.arribo_real, Embarque.salida_real, Embarque.tipo_transporte).where(
        Embarque.arribo_real >= desde, Embarque.arribo_real <= hasta, Embarque.salida_real.is_not(None),
        Embarque.estado != "CANCELADO", *_emb(db, user))).all()
    por_modo: dict[str, list] = {}
    for r, s, modo in filas:
        por_modo.setdefault(modo or "—", []).append(max(_dias(s, r), 0))
    return {"valor": _promedio([d for v in por_modo.values() for d in v]),
            "desglose": [{"etiqueta": m, "valor": _promedio(v), "base": {"n": len(v), "m": len(v)}} for m, v in sorted(por_modo.items())]}


def recepcion_con_diferencias(db, user, desde, hasta):
    """Cada línea de lista de empaque tiene una sola recepción (pl_linea_id único)."""
    a, b = _rango(desde, hasta)
    filas = db.execute(select(PLLinea.cantidad, RecepcionLinea.cantidad_recibida, RecepcionLinea.cantidad_danada)
                       .join(PLLinea, PLLinea.id == RecepcionLinea.pl_linea_id)
                       .join(FacturaLinea, FacturaLinea.id == PLLinea.factura_linea_id)
                       .join(Factura, Factura.id == FacturaLinea.factura_id)
                       .where(RecepcionLinea.fecha >= a, RecepcionLinea.fecha < b, *_fact(user))).all()
    return _pct(sum(1 for esp, rec, dan in filas if abs(float(esp) - float(rec)) > 1e-9 or float(dan or 0) > 0), len(filas))


# ---- Lead times (analizados una vez por petición) ------------------------------------------------
def _lead_times(db: Session, user: Usuario) -> list[dict]:
    """Análisis de lead time de cada OC vigente del alcance del usuario; se
    calcula una sola vez por petición aunque varios indicadores y tramos lo usen."""
    from app.modulos.transporte.leadtimes import ETAPAS, leadtimes

    cache = db.info.setdefault("indicadores_lt", {})
    if user.id not in cache:
        items = leadtimes(db, user, size=1_000_000)["items"]
        for i in items:
            h = {x["clave"]: x["fecha"] for x in i["hitos"]}
            i["_ingreso"] = h.get("ingreso") if len(i["duraciones"]) == len(ETAPAS) else None
            i["_lib"] = h.get("lib_logistica")
        cache[user.id] = items
    return cache[user.id]


def lead_time_prom(db, user, desde, hasta):
    """OC que ingresaron a bodega en el período con todos sus hitos; las que
    tienen fechas incoherentes (una etapa negativa) se cuentan aparte."""
    from app.modulos.transporte.leadtimes import ETAPAS

    ingresadas = [i for i in _lead_times(db, user) if i["_ingreso"] and desde <= i["_ingreso"] <= hasta]
    completas = [sum(i["duraciones"].values()) for i in ingresadas if len(i["duraciones"]) == len(ETAPAS)]
    return {"valor": _promedio(completas), "base": {"n": len(completas), "m": len(ingresadas)}}


def lib_a_tiempo(db, user, desde, hasta):
    lib = [i["lib_a_tiempo"] for i in _lead_times(db, user)
           if i["_lib"] and desde <= i["_lib"] <= hasta and i["lib_a_tiempo"] is not None]
    return _pct(sum(1 for x in lib if x), len(lib))


def oc_en_riesgo(db, user, desde, hasta):
    """Misma definición que Inicio y Seguimiento (metricas.oc_llegada_tarde)."""
    from app.modulos.seguimiento.seguimiento import filas_seguimiento

    return len(metricas.oc_llegada_tarde(filas_seguimiento(db, user)))


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
    Indicador("dias_aprobacion", "compras", "Days to approve", "Average days from the first time a PO was sent to its final approval, for the POs approved in the period that went through approval steps (POs approved instantly, without steps, do not count). The median is also shown.",
              "Purchase orders (approval date) and change log (first send)", PERIODO, "dias", "oc.ver", dias_aprobacion, None, "bajo"),
    Indicador("saldo_por_facturar", "compras", "Balance to invoice", "Sum of (ordered − invoiced quantity) × unit price of the lines (not blocked) of approved POs. Invoices count from draft (they reserve the quantity); cancelled ones do not. Shown in the company currency, with the other currencies apart (never added together).",
              "Purchase order lines and invoice lines", HOY, "moneda", "oc.ver", saldo_por_facturar, "/ordenes", "", "precios"),
    Indicador("oc_atrasadas", "compras", "POs past their ship date", "Count of approved POs whose ship date (XF) has passed and that still have quantity to invoice (released or not).",
              "Purchase orders and invoice lines", HOY, "numero", "oc.ver", oc_atrasadas, "/seguimiento?vista=ordenes&xf_vencida=1", "bajo"),
    Indicador("cumplimiento_xf", "compras", "Pickups on time", "Packing lists picked up in the period on or before the original ship date (XF) of their PO, plus the company tolerance ÷ packing lists picked up × 100. The original XF keeps a moved date from hiding the delay. The suppliers with the lowest rate are listed.",
              "Packing lists (pickup date) and purchase orders (original XF)", PERIODO, "porcentaje", "factura.ver", cumplimiento_xf, "/seguimiento?vista=leadtimes", "alto"),
    Indicador("facturas_finalizadas", "facturacion", "Invoices finalized", "Count of invoices in the state Finalized whose date (or finalization day, if it has no date) falls in the period. A reopened invoice stops counting until it is finalized again.",
              "Invoices (document date)", PERIODO, "numero", "factura.ver", facturas_finalizadas, "/facturas?estado=FINALIZADA", "alto"),
    Indicador("importe_facturado", "facturacion", "Amount invoiced", "Sum of the lines (quantity × unit price, rounded like the document) of the invoices in the state Finalized whose date falls in the period. Shown in the company currency, with the other currencies apart.",
              "Invoice lines (document date)", PERIODO, "moneda", "factura.ver", importe_facturado, "/facturas?estado=FINALIZADA", "alto",
              "precios"),
    Indicador("facturas_abiertas", "facturacion", "Invoices in progress", "Count of invoices in draft or under correction.",
              "Invoices", HOY, "numero", "factura.ver", facturas_abiertas, "/facturas?vista=editables", ""),
    Indicador("pls_pendientes", "facturacion", "Packing lists in progress", "Count of packing lists in draft or under correction of invoices that are not cancelled.",
              "Packing lists", HOY, "numero", "factura.ver", pls_pendientes, "/facturas?vista=pl_incompletos", "bajo"),
    Indicador("embarques_en_transito", "logistica", "Shipments in transit", "Count of shipments in the state In transit, within your companies and carriers.",
              "Shipments", HOY, "numero", "transporte.gestionar", embarques_en_transito, "/transporte?estado=EN_TRANSITO", ""),
    Indicador("arribos", "logistica", "Arrivals", "Count of shipments whose actual arrival date falls in the period (called off ones excluded).",
              "Shipments (actual arrival)", PERIODO, "numero", "transporte.gestionar", arribos, "/transporte", "alto"),
    Indicador("puntualidad", "logistica", "On-time arrivals", "Shipments that arrived in the period on or before the ETA committed at departure (plus the company tolerance) ÷ shipments that arrived × 100. Updating the ETA en route does not change the committed one.",
              "Shipments (committed ETA and actual arrival)", PERIODO, "porcentaje", "transporte.gestionar", puntualidad, "/seguimiento?vista=embarques", "alto"),
    Indicador("dias_transito", "logistica", "Days in transit", "Average days between actual departure and actual arrival of the shipments that arrived in the period, with the average per transport mode.",
              "Shipments (actual departure and arrival)", PERIODO, "dias", "transporte.gestionar", dias_transito, "/seguimiento?vista=leadtimes", "bajo"),
    Indicador("recepcion_con_diferencias", "logistica", "Receipts with differences", "Packing list lines received in the period with a quantity different from the packed one or with damaged units ÷ lines received × 100 (each line is received once).",
              "Warehouse receipts and packing list lines", PERIODO, "porcentaje", "transporte.gestionar", recepcion_con_diferencias, None, "bajo"),
    Indicador("lead_time_prom", "logistica", "Average lead time", "Average days from PO creation to warehouse entry, for the approved or closed POs that entered the warehouse in the period with every milestone recorded. The POs left out for incomplete or inconsistent dates are shown as the base (n of m).",
              "Purchase orders and shipment events (lead time milestones)", PERIODO, "dias", "seguimiento.ver", lead_time_prom, "/seguimiento?vista=leadtimes", "bajo"),
    Indicador("lib_a_tiempo", "logistica", "Logistics release on time", "Approved or closed POs released by logistics in the period on or before their target date ÷ POs released in the period × 100. The target comes from the lead time of each PO.",
              "Purchase orders (logistics release) and lead time rules", PERIODO, "porcentaje", "seguimiento.ver", lib_a_tiempo, "/seguimiento?vista=leadtimes", "alto"),
    Indicador("oc_en_riesgo", "logistica", "POs arriving late", "Count of approved or closed POs with goods not yet received whose (estimated or actual) port arrival is after the port deadline of their in-store date. Same definition as Home and Tracking.",
              "Purchase orders, shipments and lead time rules", HOY, "numero", "seguimiento.ver", oc_en_riesgo, "/seguimiento?riesgo=ATRASO", "bajo"),
    Indicador("fichas_en_revision", "productos", "Sheets in review", "Count of technical sheets waiting for review.",
              "Products (technical sheet)", HOY, "numero", "producto.ver", fichas_en_revision, "/productos?estado=revision", "bajo"),
    Indicador("fichas_devueltas", "productos", "Sheets returned", "Count of technical sheets returned to be corrected.",
              "Products (technical sheet)", HOY, "numero", "producto.ver", fichas_devueltas, "/productos?estado=observado", "bajo"),
    Indicador("fichas_aprobadas", "productos", "Sheets approved", "Count of technical sheets approved (or corrected and approved) whose review date falls in the period.",
              "Products (review date)", PERIODO, "numero", "producto.ver", fichas_aprobadas, "/productos", "alto"),
    Indicador("sin_clasificar", "productos", "Sheets not sent to review", "Count of products whose technical sheet is still a draft (complete or not): nobody reviews them until they are sent. Sheets in review or returned are counted apart.",
              "Products (technical sheet)", HOY, "numero", "producto.ver", sin_clasificar, "/productos?estado=borrador", "bajo"),
]
POR_CLAVE = {i.clave: i for i in CATALOGO}
# Resumen: los indicadores que dicen cómo va la operación de punta a punta
# (dinero, puntualidad, tiempo de ciclo y calidad). El resto queda para elegir.
PRINCIPALES = ["importe_facturado", "saldo_por_facturar", "lead_time_prom", "puntualidad", "lib_a_tiempo",
               "oc_en_riesgo", "recepcion_con_diferencias", "dias_aprobacion"]


# ---- Qué ve cada persona -------------------------------------------------------------------------
def _del_modulo(user: Usuario, modulo: str) -> list[Indicador]:
    from app.modulos.acceso import visibilidad

    visibles = [i for i in CATALOGO if tiene(user, i.permiso) and not (i.grupo and visibilidad.oculto(i.grupo))]
    if modulo == "resumen":
        return sorted(visibles, key=lambda i: PRINCIPALES.index(i.clave) if i.clave in PRINCIPALES else len(PRINCIPALES))
    return [i for i in visibles if i.modulo == modulo]


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
    if modulo == "resumen":
        return [c for c in posibles if c in PRINCIPALES], "sistema"
    return posibles, "sistema"


def _limpiar(user: Usuario, modulo: str, claves) -> list[str]:
    if modulo not in MODULOS:
        raise ErrorNegocio("Unknown module.", 404, "no_encontrado")
    if not isinstance(claves, list):
        raise ErrorNegocio("Choose the indicators.", 422, "validacion")
    validas = {i.clave for i in CATALOGO if i.modulo == modulo or modulo == "resumen"}
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


def _resultado(r) -> dict:
    """Lo que devuelve un indicador: un número o un dict con `valor` y, si
    aplica, `moneda` y `otras` (importes de otras monedas, nunca sumados),
    `base` (n de m de un porcentaje o promedio) y `desglose` (filas de detalle)."""
    return dict(r) if isinstance(r, dict) else {"valor": r}


# ---- Metas de la empresa ---------------------------------------------------------------------------
def metas() -> dict:
    """Meta de cada indicador que la empresa fijó (Configuración → Indicadores)."""
    return dict((configuracion_actual().get("metas_indicadores") or {}))


def guardar_metas(db: Session, user: Usuario, valores) -> dict:
    """Metas por indicador (administración): un número o null para quitarla.
    La fórmula no cambia; solo contra qué se compara el valor."""
    from app.modulos.empresa.organizacion import actual

    exigir(user, "admin")
    if not isinstance(valores, dict) or set(valores) - set(POR_CLAVE):
        raise ErrorNegocio("Unknown indicator.", 422, "validacion")
    org = actual(db)
    conf = dict(org.configuracion or {})
    nuevas = dict(conf.get("metas_indicadores") or {})
    for clave, v in valores.items():
        if v is None or v == "":
            nuevas.pop(clave, None)
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or \
                (POR_CLAVE[clave].formato == "porcentaje" and v > 100):
            raise ErrorNegocio(f"{POR_CLAVE[clave].titulo}: enter a valid target.", 422, "validacion")
        nuevas[clave] = v
    conf["metas_indicadores"] = nuevas
    org.configuracion = conf
    registrar(db, user, "organizacion", org.id, "metas_indicadores", {"metas": nuevas})
    db.flush()
    return {"metas": nuevas}


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
    # Tramos iguales y seguidos que terminan hoy: el último es el período
    # elegido y el penúltimo, el anterior con el que se compara
    tramos = [(hasta - timedelta(days=dias * (k + 1) - 1), hasta - timedelta(days=dias * k))
              for k in reversed(range(TRAMOS[dias]))]
    res = []
    objetivos = metas()
    for clave in claves:
        i = POR_CLAVE[clave]
        if i.momento == PERIODO:
            calc = [_resultado(i.calcular(db, user, a, b)) for a, b in tramos]
            serie = [{"desde": a, "hasta": b, "valor": r["valor"], "base": r.get("base")} for (a, b), r in zip(tramos, calc, strict=True)]
            actual, anterior = calc[-1], calc[-2]["valor"]
        else:
            actual, serie, anterior = _resultado(i.calcular(db, user, desde, hasta)), None, None
        res.append({"clave": i.clave, "anterior": anterior, "serie": serie, "ruta": i.ruta, "meta": objetivos.get(i.clave), **actual})
    return {
        "modulo": modulo, "titulo": MODULOS[modulo], "modulos": modulos(user),
        "periodo": {"dias": dias, "desde": desde, "hasta": hasta, "anterior_desde": antes_desde, "anterior_hasta": antes_hasta},
        "moneda_base": _moneda_base(), "origen": origen, "elegidos": claves,
        "catalogo": [{"clave": i.clave, "titulo": i.titulo, "formula": i.formula, "fuente": i.fuente, "momento": i.momento,
                      "formato": i.formato, "mejor": i.mejor} for i in disponibles],
        "indicadores": res,
    }
