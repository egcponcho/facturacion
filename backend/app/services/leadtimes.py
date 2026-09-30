"""Lead times por origen: cuánto tarda cada etapa, de la OC al ingreso en bodega.

Cada OC pasa por hitos con fecha: creación, liberación comercial, liberación
logística, recolección, salida (inicio del tránsito), arribo al puerto destino,
entrega en bodega e ingreso. Con ellos se calcula:

- El promedio de días de cada etapa por país de origen.
- Si la liberación logística llegó a tiempo: debe darse cierto número de días
  antes de la XF según la región de origen (Asia 21, el resto 15).
- Si la mercancía llega temprano o tarde. La fecha en tienda no se compara con
  el arribo al puerto: después del puerto falta llevarla a la bodega, darle
  ingreso y reexportarla a la tienda. Por eso la fecha límite de arribo al
  puerto es la fecha en tienda menos esos días estándar de su región. La
  reexportación aún no se registra en el sistema; solo se reserva su tiempo.
"""
from datetime import date, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Embarque,
    Factura,
    FacturaLinea,
    OrdenCompra,
    PackingList,
    Pais,
    PLLinea,
    PosicionOC,
    RegionLeadTime,
    UnidadCarga,
    Usuario,
)
from .common import proveedor_filtro

# Región por defecto si no hay ninguna configurada
POR_DEFECTO = {"codigo": "OTROS", "nombre": "Other origins", "dias_liberacion": 15, "dias_transito": 10,
               "dias_puerto_bodega": 3, "dias_ingreso": 2, "dias_reexportacion": 5}

# Etapas del lead time, en orden: de un hito al siguiente
ETAPAS = [
    ("comercial", "Commercial release", "creada", "lib_comercial"),
    ("logistica", "Logistics release", "lib_comercial", "lib_logistica"),
    ("despacho", "Production and pickup", "lib_logistica", "recoleccion"),
    ("salida", "Pickup to departure", "recoleccion", "salida"),
    ("transito", "Transit to port", "salida", "arribo"),
    ("puerto", "Port to warehouse", "arribo", "entrega"),
    ("ingreso", "Warehouse entry", "entrega", "ingreso"),
]
HITOS = [
    ("creada", "PO created"), ("lib_comercial", "Commercial release"), ("lib_logistica", "Logistics release"),
    ("recoleccion", "Pickup"), ("salida", "Departure"), ("arribo", "Port arrival"),
    ("entrega", "At warehouse"), ("ingreso", "Warehouse entry"), ("tienda", "In store"),
]


class Estandares:
    """Estándares de la región de cada país de origen (con caché por consulta)."""

    def __init__(self, db: Session):
        regiones = {r.codigo: r for r in db.scalars(select(RegionLeadTime).where(RegionLeadTime.activo))}
        self.regiones = {c: _dict(r) for c, r in regiones.items()}
        pred = next((r for r in regiones.values() if r.predeterminada), None)
        self.defecto = _dict(pred) if pred else POR_DEFECTO
        self.pais_region = {p.codigo: p.region for p in db.scalars(select(Pais))}
        self.nombres = {p.codigo: p.nombre for p in db.scalars(select(Pais))}

    def de(self, pais: str | None) -> dict:
        return self.regiones.get(self.pais_region.get(pais or "") or "", self.defecto)


def _dict(r: RegionLeadTime) -> dict:
    return {"codigo": r.codigo, "nombre": r.nombre, "dias_liberacion": r.dias_liberacion,
            "dias_transito": r.dias_transito, "dias_puerto_bodega": r.dias_puerto_bodega,
            "dias_ingreso": r.dias_ingreso, "dias_reexportacion": r.dias_reexportacion}


def dias_post_arribo(est: dict) -> int:
    """Días que necesita la mercancía después del puerto para estar en tienda."""
    return est["dias_puerto_bodega"] + est["dias_ingreso"] + est["dias_reexportacion"]


def limite_puerto(fecha_tienda: date | None, est: dict) -> date | None:
    """Última fecha de arribo al puerto destino para llegar a tiempo a tienda."""
    return fecha_tienda - timedelta(days=dias_post_arribo(est)) if fecha_tienda else None


def arribo_estimado(fecha_xf: date | None, est: dict, hoy: date) -> date | None:
    """Sin embarque todavía: la XF (o hoy si ya pasó) más el tránsito estándar."""
    if not fecha_xf:
        return None
    return max(fecha_xf, hoy) + timedelta(days=est["dias_transito"])


def _dia(x) -> date | None:
    return x.date() if hasattr(x, "date") and callable(x.date) else x


def _min(*fechas):
    fs = [f for f in fechas if f]
    return min(fs) if fs else None


def _hitos_por_oc(db: Session, oc_ids: list[int]) -> dict[int, dict]:
    """Primera fecha de cada hito de transporte de cada OC (su primer envío)."""
    out: dict[int, dict] = {}
    if not oc_ids:
        return out
    filas = db.execute(
        select(PosicionOC.oc_id, Factura.fecha, PackingList.recolectado_en, UnidadCarga.embarque_id)
        .join(FacturaLinea, FacturaLinea.posicion_oc_id == PosicionOC.id)
        .join(Factura, Factura.id == FacturaLinea.factura_id)
        .outerjoin(PLLinea, PLLinea.factura_linea_id == FacturaLinea.id)
        .outerjoin(PackingList, (PackingList.id == PLLinea.pl_id) & (PackingList.estado != "CANCELADO"))
        .outerjoin(UnidadCarga, UnidadCarga.id == PackingList.unidad_carga_id)
        .where(PosicionOC.oc_id.in_(oc_ids), Factura.estado != "CANCELADA")
    ).all()
    emb_ids = {e for *_, e in filas if e}
    embarques = {e.id: e for e in db.scalars(select(Embarque).where(Embarque.id.in_(emb_ids)))} if emb_ids else {}
    for oc_id, f_fecha, recolectado, emb_id in filas:
        h = out.setdefault(oc_id, {"facturada": None, "recoleccion": None, "salida": None, "arribo": None,
                                   "entrega": None, "ingreso": None, "etd": None, "eta": None, "embarques": set()})
        h["facturada"] = _min(h["facturada"], f_fecha)
        h["recoleccion"] = _min(h["recoleccion"], recolectado)
        e = embarques.get(emb_id)
        if not e:
            continue
        h["embarques"].add(e.codigo)
        ev = {}
        for x in e.eventos:
            ev.setdefault(x.tipo, _dia(x.fecha))
        h["recoleccion"] = _min(h["recoleccion"], ev.get("RECOLECCION"))
        h["salida"] = _min(h["salida"], e.salida_real or ev.get("SALIDA"))
        h["arribo"] = _min(h["arribo"], e.arribo_real or ev.get("ARRIBO"))
        h["entrega"] = _min(h["entrega"], ev.get("ENTREGA"))
        h["ingreso"] = _min(h["ingreso"], ev.get("RECEPCION"))
        h["etd"] = _min(h["etd"], e.etd)
        h["eta"] = _min(h["eta"], e.eta)
    return out


def _estado(real: date | None, meta: date | None, estimada: date | None, hoy: date) -> tuple[int | None, str]:
    """Días de diferencia contra la meta (positivo = tarde) y el estado del hito."""
    if real:
        if not meta:
            return None, "hecho"
        d = (real - meta).days
        return d, "tarde" if d > 0 else "a_tiempo"
    if meta and meta < hoy and not estimada:
        return (hoy - meta).days, "vencido"
    if estimada and meta:
        d = (estimada - meta).days
        return d, "riesgo" if d > 0 else "en_plan"
    return None, "pendiente"


def _riesgo(holgura: int | None) -> str | None:
    if holgura is None:
        return None
    return "ATRASO" if holgura < 0 else "JUSTO" if holgura < 7 else "A_TIEMPO"


def analizar_oc(oc: OrdenCompra, h: dict | None, est: dict, hoy: date) -> dict:
    """Hitos de la OC con su meta, fecha real o estimada y si va temprano o tarde."""
    h = h or {}
    xf, tienda = oc.fecha_xf, oc.fecha_tienda
    lim_arribo = limite_puerto(tienda, est)
    real = {"creada": oc.fecha, "lib_comercial": oc.fecha_lib_comercial, "lib_logistica": oc.fecha_lib_logistica,
            "recoleccion": h.get("recoleccion"), "salida": h.get("salida"), "arribo": h.get("arribo"),
            "entrega": h.get("entrega"), "ingreso": h.get("ingreso"), "tienda": None}
    meta = {
        "lib_logistica": xf - timedelta(days=est["dias_liberacion"]) if xf else None,
        "recoleccion": xf,
        "salida": lim_arribo - timedelta(days=est["dias_transito"]) if lim_arribo else None,
        "arribo": lim_arribo,
        "entrega": lim_arribo + timedelta(days=est["dias_puerto_bodega"]) if lim_arribo else None,
        "ingreso": (lim_arribo + timedelta(days=est["dias_puerto_bodega"] + est["dias_ingreso"])) if lim_arribo else None,
        "tienda": tienda,
    }
    # Estimados de lo que falta, encadenados desde el arribo
    est_fecha: dict[str, date | None] = {}
    if not real["salida"]:
        est_fecha["salida"] = h.get("etd")
    salio = real["salida"] or h.get("etd")
    arribo = (real["arribo"] or h.get("eta") or (salio + timedelta(days=est["dias_transito"]) if salio else None)
              or arribo_estimado(xf, est, hoy))
    if not real["arribo"]:
        est_fecha["arribo"] = arribo
    entrega = real["entrega"] or (arribo + timedelta(days=est["dias_puerto_bodega"]) if arribo else None)
    if not real["entrega"]:
        est_fecha["entrega"] = entrega
    ingreso = real["ingreso"] or (entrega + timedelta(days=est["dias_ingreso"]) if entrega else None)
    if not real["ingreso"]:
        est_fecha["ingreso"] = ingreso
    est_fecha["tienda"] = ingreso + timedelta(days=est["dias_reexportacion"]) if ingreso else None
    hitos = []
    for clave, nombre in HITOS:
        estimada = est_fecha.get(clave)
        dif, estado = _estado(real[clave], meta.get(clave), estimada, hoy)
        hitos.append({"clave": clave, "nombre": nombre, "meta": meta.get(clave), "fecha": real[clave],
                      "estimada": estimada, "dif": dif, "estado": estado})
    holgura = (lim_arribo - arribo).days if lim_arribo and arribo else None
    lib = real["lib_logistica"]
    tienda_est = est_fecha["tienda"]
    return {
        "tienda_estimada": tienda_est,
        "dias_vs_tienda": (tienda_est - tienda).days if tienda_est and tienda else None,
        "hitos": hitos, "limite_puerto": lim_arribo, "arribo": arribo, "arribo_real": bool(real["arribo"]),
        "holgura": holgura, "riesgo": _riesgo(holgura),
        "lib_dias_antes_xf": (xf - lib).days if xf and lib else None,
        "lib_a_tiempo": (lib <= meta["lib_logistica"]) if lib and meta["lib_logistica"] else None,
        "lib_vencida": bool(not lib and meta["lib_logistica"] and meta["lib_logistica"] < hoy),
        "recoleccion_vs_xf": (real["recoleccion"] - xf).days if real["recoleccion"] and xf else None,
        "duraciones": {k: (real[b] - real[a]).days for k, _, a, b in ETAPAS
                       if real[a] and real[b] and (real[b] - real[a]).days >= 0},
        "embarques": sorted(h.get("embarques", [])),
    }


def _prom(valores: list) -> float | None:
    return round(mean(valores), 1) if valores else None


def _lista(v) -> list[str]:
    return [x for x in str(v or "").split(",") if x]


def tiendas_estimadas(db: Session, ocs: list[OrdenCompra]) -> dict[int, dict]:
    """Fecha estimada en tienda de cada OC con los lead times de su origen."""
    hoy = date.today()
    ests = Estandares(db)
    hitos = _hitos_por_oc(db, [o.id for o in ocs])
    out = {}
    for o in ocs:
        a = analizar_oc(o, hitos.get(o.id), ests.de(o.pais_origen), hoy)
        out[o.id] = {"tienda_estimada": a["tienda_estimada"], "dias_vs_tienda": a["dias_vs_tienda"],
                     "arribo_estimado": a["arribo"], "riesgo": a["riesgo"]}
    return out


def leadtimes(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
              orden: str | None = None, page: int = 1, size: int = 25) -> dict:
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    hoy = date.today()
    ests = Estandares(db)
    q = select(OrdenCompra)
    prov = proveedor_filtro(user, proveedor_id)
    if prov:
        q = q.where(OrdenCompra.proveedor_id == prov)
    if filtros.get("desde"):
        q = q.where(OrdenCompra.fecha >= date.fromisoformat(filtros["desde"]))
    if filtros.get("hasta"):
        q = q.where(OrdenCompra.fecha <= date.fromisoformat(filtros["hasta"]))
    ocs = list(db.scalars(q.order_by(OrdenCompra.fecha_xf, OrdenCompra.numero)))
    todas_origen = sorted({o.pais_origen for o in ocs if o.pais_origen})
    todas_prov = sorted({o.proveedor.nombre for o in ocs})
    if filtros.get("origen"):
        ocs = [o for o in ocs if o.pais_origen in _lista(filtros["origen"])]
    if filtros.get("region"):
        ocs = [o for o in ocs if ests.de(o.pais_origen)["codigo"] in _lista(filtros["region"])]
    if filtros.get("proveedor"):
        ocs = [o for o in ocs if o.proveedor.nombre in _lista(filtros["proveedor"])]
    hitos = _hitos_por_oc(db, [o.id for o in ocs])
    items = []
    for o in ocs:
        est = ests.de(o.pais_origen)
        a = analizar_oc(o, hitos.get(o.id), est, hoy)
        items.append({"oc_id": o.id, "oc": o.numero, "proveedor": o.proveedor.nombre, "origen": o.pais_origen,
                      "origen_nombre": ests.nombres.get(o.pais_origen or "", o.pais_origen),
                      "region": est["codigo"], "region_nombre": est["nombre"], "dias_liberacion": est["dias_liberacion"],
                      "fecha": o.fecha, "fecha_xf": o.fecha_xf, "fecha_tienda": o.fecha_tienda,
                      "liberacion_comercial": o.liberacion_comercial, "liberacion_logistica": o.liberacion_logistica,
                      **a})
    # Promedios por país de origen
    grupos: dict[str, list] = {}
    for it in items:
        grupos.setdefault(it["origen"] or "—", []).append(it)
    origenes = []
    for origen, its in sorted(grupos.items()):
        est = ests.de(origen)
        etapas = {}
        for k, *_ in ETAPAS:
            vals = [i["duraciones"][k] for i in its if k in i["duraciones"]]
            etapas[k] = {"prom": _prom(vals), "n": len(vals)}
        con_lib = [i for i in its if i["lib_a_tiempo"] is not None]
        completas = [sum(i["duraciones"][k] for k, *_ in ETAPAS) for i in its if len(i["duraciones"]) == len(ETAPAS)]
        origenes.append({
            "origen": origen, "nombre": ests.nombres.get(origen, origen), "region": est["codigo"],
            "region_nombre": est["nombre"], "ocs": len(its), "etapas": etapas,
            "total_prom": _prom(completas), "completas": len(completas),
            "lib": {"meta": est["dias_liberacion"], "a_tiempo": sum(1 for i in con_lib if i["lib_a_tiempo"]),
                    "total": len(con_lib), "vencidas": sum(1 for i in its if i["lib_vencida"]),
                    "pct": round(sum(1 for i in con_lib if i["lib_a_tiempo"]) * 100 / len(con_lib)) if con_lib else None,
                    "dias_antes_xf": _prom([i["lib_dias_antes_xf"] for i in con_lib])},
            "recoleccion_vs_xf": _prom([i["recoleccion_vs_xf"] for i in its if i["recoleccion_vs_xf"] is not None]),
            "holgura": _prom([i["holgura"] for i in its if i["holgura"] is not None]),
            "tarde": sum(1 for i in its if i["riesgo"] == "ATRASO"),
        })
    con_lib = [i for i in items if i["lib_a_tiempo"] is not None]
    completas = [sum(i["duraciones"].values()) for i in items if len(i["duraciones"]) == len(ETAPAS)]
    kpis = {
        "ocs": len(items),
        "lib_pct": round(sum(1 for i in con_lib if i["lib_a_tiempo"]) * 100 / len(con_lib)) if con_lib else None,
        "lib_total": len(con_lib),
        "lib_vencidas": sum(1 for i in items if i["lib_vencida"]),
        "total_prom": _prom(completas),
        "transito_prom": _prom([i["duraciones"]["transito"] for i in items if "transito" in i["duraciones"]]),
        "tarde": sum(1 for i in items if i["riesgo"] == "ATRASO"),
        "justo": sum(1 for i in items if i["riesgo"] == "JUSTO"),
    }
    # Filtros sobre el resultado de cada OC
    if filtros.get("riesgo"):
        items = [i for i in items if i["riesgo"] in _lista(filtros["riesgo"])]
    if filtros.get("lib") == "vencida":
        items = [i for i in items if i["lib_vencida"]]
    elif filtros.get("lib") == "tarde":
        items = [i for i in items if i["lib_a_tiempo"] is False]
    col, _, d = (orden or "fecha_xf:asc").partition(":")
    if col in {"oc", "proveedor", "origen", "fecha_xf", "fecha_tienda", "holgura", "limite_puerto", "arribo",
               "tienda_estimada", "dias_vs_tienda"}:
        items.sort(key=lambda i: (i[col] is None, i[col] if i[col] is not None else 0), reverse=d == "desc")
        if d == "desc":  # los vacíos siempre al final
            items.sort(key=lambda i: i[col] is None)
    return {
        "items": items[(page - 1) * size: page * size], "total": len(items), "page": page, "size": size,
        "kpis": kpis, "origenes": origenes,
        "etapas": [{"clave": k, "nombre": n, "desde": a, "hasta": b} for k, n, a, b in ETAPAS],
        "regiones": list(ests.regiones.values()) or [ests.defecto],
        "opciones": {"origenes": [{"valor": c, "texto": f"{c} · {ests.nombres.get(c, c)}"} for c in todas_origen],
                     "regiones": [{"valor": r["codigo"], "texto": r["nombre"]} for r in ests.regiones.values()],
                     "proveedores": todas_prov},
    }
