"""Una sola lógica para todos los niveles:
disponible = cantidad del nivel de arriba - lo asignado en documentos activos."""
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modelos import Factura, FacturaLinea, GrupoCajas, GrupoCajasItem, PackingList, PLLinea, cant
from app.modulos.empaque import empaques


def nombre_factura(f: Factura) -> str:
    return f.numero or f"Draft #{f.id}"


# ---- OC -> factura ----------------------------------------------------------
def facturado_por_posicion(db: Session, posicion_ids) -> dict[int, int]:
    ids = list(set(posicion_ids))
    if not ids:
        return {}
    filas = db.execute(
        select(FacturaLinea.posicion_oc_id, func.sum(FacturaLinea.cantidad))
        .join(Factura, Factura.id == FacturaLinea.factura_id)
        .where(Factura.estado != "CANCELADA", FacturaLinea.posicion_oc_id.in_(ids))
        .group_by(FacturaLinea.posicion_oc_id)
    ).all()
    return {pid: cant(total or 0) for pid, total in filas}


def facturas_por_posicion(db: Session, posicion_ids) -> dict[int, list[dict]]:
    ids = list(set(posicion_ids))
    res: dict[int, list[dict]] = defaultdict(list)
    if not ids:
        return res
    filas = db.execute(
        select(FacturaLinea.posicion_oc_id, FacturaLinea.cantidad, Factura)
        .join(Factura, Factura.id == FacturaLinea.factura_id)
        .where(Factura.estado != "CANCELADA", FacturaLinea.posicion_oc_id.in_(ids))
        .order_by(Factura.id)
    ).all()
    for pid, cantidad, f in filas:
        res[pid].append(
            {"id": f.id, "nombre": nombre_factura(f), "estado": f.estado, "cantidad": cantidad}
        )
    return res


# ---- factura -> PL ----------------------------------------------------------
def asignado_por_linea(db: Session, linea_ids) -> dict[int, int]:
    ids = list(set(linea_ids))
    if not ids:
        return {}
    filas = db.execute(
        select(PLLinea.factura_linea_id, func.sum(PLLinea.cantidad))
        .join(PackingList, PackingList.id == PLLinea.pl_id)
        .where(PackingList.estado != "CANCELADO", PLLinea.factura_linea_id.in_(ids))
        .group_by(PLLinea.factura_linea_id)
    ).all()
    return {lid: cant(total or 0) for lid, total in filas}


def pl_lineas_activas(db: Session, linea_ids) -> list[PLLinea]:
    ids = list(set(linea_ids))
    if not ids:
        return []
    return list(
        db.scalars(
            select(PLLinea)
            .join(PackingList, PackingList.id == PLLinea.pl_id)
            .where(PackingList.estado != "CANCELADO", PLLinea.factura_linea_id.in_(ids))
            .order_by(PackingList.id.desc(), PLLinea.id.desc())
        ).all()
    )


# ---- PL -> cajas ------------------------------------------------------------
def cubierto(pl_linea: PLLinea) -> int:
    """Cantidad de la parte que ya está dentro de cajas."""
    return sum(it.cantidad_por_caja * it.grupo.num_cajas for it in pl_linea.items)


def sin_caja(pl_linea: PLLinea) -> int:
    return pl_linea.cantidad - cubierto(pl_linea)


def cubierto_por_ids(db: Session, pl_linea_ids) -> dict[int, int]:
    ids = list(set(pl_linea_ids))
    if not ids:
        return {}
    filas = db.execute(
        select(
            GrupoCajasItem.pl_linea_id,
            func.sum(GrupoCajasItem.cantidad_por_caja * GrupoCajas.num_cajas),
        )
        .join(GrupoCajas, GrupoCajas.id == GrupoCajasItem.grupo_id)
        .where(GrupoCajasItem.pl_linea_id.in_(ids))
        .group_by(GrupoCajasItem.pl_linea_id)
    ).all()
    return {lid: cant(total or 0) for lid, total in filas}


def numeracion(pl: PackingList) -> dict[int, tuple[int, int]]:
    """Rangos de numeración (desde, hasta) por nodo, dentro de su tipo de empaque."""
    return empaques.numeracion(pl)


def cbm_caja(g: GrupoCajas) -> float | None:
    return empaques.volumen(g)


def totales_pl(pl: PackingList) -> dict:
    """Totales desde la estructura física (ver empaques): bultos, soportes,
    pesos acumulados de abajo hacia arriba y volumen exterior."""
    t = empaques.totales(pl)
    por_unidad: dict[str, dict] = {}
    for pll in pl.lineas:
        u = pll.factura_linea.unidad
        d = por_unidad.setdefault(u, {"cantidad": 0, "en_cajas": 0, "sin_caja": 0})
        c = cubierto(pll)
        d["cantidad"] += pll.cantidad
        d["en_cajas"] += c
        d["sin_caja"] += pll.cantidad - c
    return {
        "cajas": t["bultos"],
        "peso_neto": t["peso_neto"],
        "peso_bruto": t["peso_bruto"],
        "cbm": t["cbm"],
        "pallets": t["soportes"],
        "sin_peso": t["sin_peso"],
        "por_tipo": t["por_tipo"],
        "por_unidad": por_unidad,
    }


def inner_de(linea) -> int | None:
    """Unidades por inner pack de una posición o línea de factura (solo sólidos)."""
    return linea.inner_pack if linea.tipo_empaque != "PREPACK" and linea.inner_pack else None


def error_en_linea(linea, cantidad) -> str | None:
    """Por qué la cantidad no vale para la línea (posición o línea de factura):
    entera si su unidad se cuenta, hasta 3 decimales si se mide, y en inner
    packs enteros cuando la línea los tiene."""
    from app.modulos.maestros.unidades import error_cantidad

    if (msg := error_cantidad(cantidad, getattr(linea, "unidad", None))):
        return msg
    n = inner_de(linea)
    if n and cantidad % n:
        return (f"{cantidad} is not a multiple of the inner pack ({n}): quantities move in whole inner packs "
                f"of {n}.")
    return None
