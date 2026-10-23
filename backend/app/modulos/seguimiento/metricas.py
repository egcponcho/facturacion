"""Métricas compartidas: una sola definición de cada concepto para Inicio,
Indicadores, Seguimiento y Reportes (docs/AUDITORIA_KPIS.md §5.1).

Reglas que valen para todas:
- Los importes nunca se suman entre monedas: se devuelven por moneda y la
  pantalla muestra la principal y las demás aparte.
- Las cantidades nunca se suman entre unidades de medida.
- Solo cuentan los documentos vigentes: OC aprobadas (las cerradas siguen en
  el seguimiento de lo ya facturado, pero su saldo deja de estar disponible),
  facturas finalizadas para lo facturado, y nada cancelado o anulado.
- Siempre con el alcance de datos del usuario (proveedores, sociedades,
  centros y transportistas).
"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core import dinero
from app.modelos import Embarque, Factura, FacturaLinea, OrdenCompra, PackingList, PosicionOC, UnidadCarga, Usuario
from app.modulos.acceso.permisos import sociedad_filtro
from app.modulos.catalogo import servicio as catalogo

# OC cuyo saldo se puede facturar / OC que siguen en el seguimiento
OC_CON_SALDO = ("APROBADA",)
OC_EN_SEGUIMIENTO = ("APROBADA", "CERRADA")
EMBARQUE_FINAL = ("RECIBIDO", "CANCELADO")


def moneda_principal(valores: dict) -> str | None:
    """La moneda de la empresa si está entre los importes; si no, la de mayor importe."""
    from app.modulos.compras.ordenes import moneda_base

    base = moneda_base()
    if not valores:
        return base
    if base in valores:
        return base
    return max(valores, key=lambda m: valores[m])


def otras_monedas(valores: dict, principal: str | None) -> list[dict]:
    """Importes de las demás monedas, para mostrarlos junto a la principal."""
    return [{"moneda": m, "valor": dinero.numero(dinero.redondear(v, m))}
            for m, v in sorted(valores.items()) if m != principal and v]


def _facturado_por_posicion():
    """Cantidad facturada por posición: facturas no canceladas (un borrador ya
    reserva la cantidad, por eso cuenta para el saldo disponible)."""
    return (select(FacturaLinea.posicion_oc_id.label("pid"), func.sum(FacturaLinea.cantidad).label("cant"))
            .join(Factura, Factura.id == FacturaLinea.factura_id).where(Factura.estado != "CANCELADA")
            .group_by(FacturaLinea.posicion_oc_id).subquery())


def _alcance_oc(user: Usuario, prov) -> list:
    cond = list(sociedad_filtro(user, OrdenCompra.sociedad))
    if prov:
        cond.append(OrdenCompra.proveedor_id.in_(prov))
    return cond


# ---- Compras ---------------------------------------------------------------------------------
def saldo_por_facturar(db: Session, user: Usuario, prov) -> dict:
    """Saldo por facturar de las OC aprobadas (posiciones no bloqueadas):
    cantidad por unidad de medida, valor por moneda (sin precio, el valor
    queda pendiente), OC con saldo por moneda y valor por proveedor y moneda."""
    fac = _facturado_por_posicion()
    saldo = PosicionOC.cantidad - func.coalesce(fac.c.cant, 0)
    filas = db.execute(
        select(PosicionOC.unidad, saldo, PosicionOC.precio, OrdenCompra.moneda, OrdenCompra.proveedor_id, OrdenCompra.id)
        .join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id).outerjoin(fac, fac.c.pid == PosicionOC.id)
        .where(OrdenCompra.estado.in_(OC_CON_SALDO), PosicionOC.bloqueada.is_(False),
               PosicionOC.cantidad > func.coalesce(fac.c.cant, 0), *_alcance_oc(user, prov))
    ).all()
    por_unidad: dict[str, float] = defaultdict(float)
    valor: dict[str, object] = defaultdict(lambda: dinero.CERO)
    por_proveedor: dict[int, dict] = defaultdict(lambda: defaultdict(lambda: dinero.CERO))
    ocs: set = set()
    sin_precio = 0
    for unidad, s, precio, moneda, prov_id, oc_id in filas:
        por_unidad[unidad] += float(s)
        ocs.add(oc_id)
        if precio is None or not moneda:
            sin_precio += 1
            continue
        imp = dinero.importe(s, precio, moneda)
        valor[moneda] += imp
        por_proveedor[prov_id][moneda] += imp
    return {"por_unidad": {u: dinero.numero(dinero.decimal(c)) for u, c in por_unidad.items()},
            "valor": dict(valor), "ocs": len(ocs), "lineas_sin_precio": sin_precio,
            "por_proveedor": {p: dict(v) for p, v in por_proveedor.items()}}


def oc_xf_vencida(db: Session, user: Usuario, prov, hoy: date | None = None) -> int:
    """OC aprobadas con la XF pasada y cantidad aún sin facturar (liberada o no)."""
    hoy = hoy or date.today()
    fac = _facturado_por_posicion()
    con_saldo = (select(PosicionOC.oc_id).outerjoin(fac, fac.c.pid == PosicionOC.id)
                 .where(PosicionOC.cantidad > func.coalesce(fac.c.cant, 0)))
    return db.scalar(select(func.count()).select_from(OrdenCompra).where(
        OrdenCompra.estado.in_(OC_CON_SALDO), OrdenCompra.fecha_xf < hoy, OrdenCompra.id.in_(con_saldo),
        *_alcance_oc(user, prov))) or 0


# ---- Seguimiento (sobre las filas de seguimiento ya calculadas) -------------------------------
def oc_llegada_tarde(filas: list[dict]) -> set:
    """OC con mercancía que llegará (o llegó) a puerto después del límite y
    que aún no se recibe en bodega."""
    return {f["oc_id"] for f in filas if f["riesgo"] == "ATRASO" and f["etapa"] != "RECIBIDO"}


ETAPAS_SALDO = ("POR_FACTURAR", "PEND_LIBERACION")


def oc_xf_en_rango(filas: list[dict], desde: date | None, hasta: date | None) -> set:
    """OC con saldo por facturar cuya XF cae en el rango (sin límite si es None)."""
    return {f["oc_id"] for f in filas if f["etapa"] in ETAPAS_SALDO and f["fecha_xf"]
            and (desde is None or f["fecha_xf"] >= desde) and (hasta is None or f["fecha_xf"] <= hasta)}


# ---- Facturación -----------------------------------------------------------------------------
def fecha_devengo():
    """Fecha en que una factura cuenta como facturada: su fecha de documento o,
    si no tiene, el día en que se finalizó."""
    return func.coalesce(Factura.fecha, func.date(Factura.finalizado_en))


def facturado(db: Session, user: Usuario, prov, desde: date, hasta: date, marcas: set | None = None) -> dict:
    """Facturas FINALIZADAS con fecha de devengo en el período: importe por
    moneda (líneas redondeadas como el documento), facturas y detalle por
    factura (para series). Una factura reabierta deja de contar hasta que se
    vuelve a finalizar."""
    f_dev = fecha_devengo()
    cond = [Factura.estado == "FINALIZADA", f_dev >= desde, f_dev <= hasta, *sociedad_filtro(user, Factura.sociedad)]
    if prov:
        cond.append(Factura.proveedor_id.in_(prov))
    filas = db.execute(
        select(Factura.id, Factura.moneda, f_dev, FacturaLinea.cantidad, FacturaLinea.precio_unitario, FacturaLinea.atributos)
        .join(FacturaLinea, FacturaLinea.factura_id == Factura.id).where(*cond)
    ).all()
    por_factura: dict[int, dict] = {}
    for fid, moneda, fecha, cant, precio, atributos in filas:
        # La marca de la línea: el atributo del producto que apunta al catálogo de marcas (su foto)
        if marcas and (catalogo.marca(db, atributos) or "") not in marcas:
            continue
        x = por_factura.setdefault(fid, {"id": fid, "moneda": moneda, "fecha": _como_fecha(fecha), "importe": dinero.CERO})
        x["importe"] += dinero.importe(cant, precio, moneda)
    por_moneda: dict[str, object] = defaultdict(lambda: dinero.CERO)
    for x in por_factura.values():
        por_moneda[x["moneda"]] += x["importe"]
    return {"por_moneda": dict(por_moneda), "facturas": len(por_factura), "detalle": list(por_factura.values())}


def _como_fecha(v) -> date | None:
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    return date.fromisoformat(str(v)[:10])


def marcas_facturadas(db: Session, user: Usuario, prov, desde: date, hasta: date) -> list[str]:
    f_dev = fecha_devengo()
    cond = [Factura.estado == "FINALIZADA", f_dev >= desde, f_dev <= hasta, FacturaLinea.atributos.is_not(None),
            *sociedad_filtro(user, Factura.sociedad)]
    if prov:
        cond.append(Factura.proveedor_id.in_(prov))
    return sorted({m for (a,) in db.execute(select(FacturaLinea.atributos).join(Factura).where(*cond)).all()
                   if (m := catalogo.marca(db, a))})


def facturas_terminadas():
    """Facturas cuya mercancía ya se recibió por completo (todas sus listas de
    empaque en unidades de embarques recibidos): ya no son trabajo pendiente."""
    pendiente = (select(PackingList.id).outerjoin(UnidadCarga, UnidadCarga.id == PackingList.unidad_carga_id)
                 .outerjoin(Embarque, Embarque.id == UnidadCarga.embarque_id)
                 .where(PackingList.factura_id == Factura.id, PackingList.estado != "CANCELADO",
                        (PackingList.unidad_carga_id.is_(None)) | (Embarque.estado != "RECIBIDO")))
    con_pl = select(PackingList.id).where(PackingList.factura_id == Factura.id, PackingList.estado != "CANCELADO")
    return (Factura.estado == "FINALIZADA") & exists(con_pl) & ~exists(pendiente)


# ---- Logística -------------------------------------------------------------------------------
def _alcance_embarques(db: Session, user: Usuario, prov) -> list:
    from app.modulos.transporte.transporte import condiciones_alcance

    cond = list(condiciones_alcance(db, user))
    if prov:
        # Un proveedor (o el proveedor elegido) ve los embarques que llevan sus listas de empaque
        suyos = (select(UnidadCarga.embarque_id).join(PackingList, PackingList.unidad_carga_id == UnidadCarga.id)
                 .join(Factura, Factura.id == PackingList.factura_id)
                 .where(Factura.proveedor_id.in_(prov), PackingList.estado != "CANCELADO"))
        cond.append(Embarque.id.in_(suyos))
    return cond


def embarques(db: Session, user: Usuario, prov, *condiciones):
    """Consulta de embarques con el alcance del usuario (y del proveedor elegido)."""
    return select(Embarque).where(*_alcance_embarques(db, user, prov), *condiciones)


def embarques_en_transito(db: Session, user: Usuario, prov) -> dict:
    """Embarques EN_TRANSITO (contados en la base, sin tope) y la próxima ETA."""
    cond = _alcance_embarques(db, user, prov)
    n = db.scalar(select(func.count()).select_from(Embarque).where(Embarque.estado == "EN_TRANSITO", *cond)) or 0
    proxima = db.scalar(select(func.min(Embarque.eta)).where(Embarque.estado == "EN_TRANSITO", Embarque.eta >= date.today(), *cond))
    return {"n": n, "proxima": proxima}


def unidades_por_recibir(db: Session, user: Usuario, prov) -> int:
    """Contenedores con carga de embarques que ya llegaron y que todavía no se
    recibieron completos en bodega."""
    from app.modelos import PackingList, UnidadCarga

    con_carga = select(PackingList.id).where(PackingList.unidad_carga_id == UnidadCarga.id,
                                             PackingList.estado != "CANCELADO").exists()
    return db.scalar(select(func.count(UnidadCarga.id)).join(Embarque, Embarque.id == UnidadCarga.embarque_id).where(
        Embarque.estado.in_(("ARRIBADO", "ENTREGADO")), UnidadCarga.recepcion_estado != "RECIBIDA", con_carga,
        *_alcance_embarques(db, user, prov))) or 0


def embarques_que_salen(db: Session, user: Usuario, prov, desde: date, hasta: date) -> int:
    return db.scalar(select(func.count()).select_from(Embarque).where(
        Embarque.estado == "PLANIFICADO", Embarque.etd >= desde, Embarque.etd <= hasta,
        *_alcance_embarques(db, user, prov))) or 0


def arribos(db: Session, user: Usuario, prov, desde: date, hasta: date) -> dict:
    """Embarques con arribo real en el período (sin los cancelados)."""
    cond = [Embarque.arribo_real >= desde, Embarque.arribo_real <= hasta, Embarque.estado != "CANCELADO",
            *_alcance_embarques(db, user, prov)]
    return {"n": db.scalar(select(func.count()).select_from(Embarque).where(*cond)) or 0}


def llegadas_previstas(db: Session, user: Usuario, prov, desde: date, hasta: date) -> int:
    """Embarques en camino (salieron y no han arribado) con ETA en el rango."""
    return db.scalar(select(func.count()).select_from(Embarque).where(
        Embarque.estado == "EN_TRANSITO", Embarque.eta >= desde, Embarque.eta <= hasta,
        *_alcance_embarques(db, user, prov))) or 0


def semana(hoy: date | None = None) -> tuple[date, date]:
    hoy = hoy or date.today()
    return hoy, hoy + timedelta(days=7)
