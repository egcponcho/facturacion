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
    PlanLeadTime,
    Puerto,
    PosicionOC,
    GrupoArticulo,
    RegionLeadTime,
    UnidadCarga,
    Usuario,
)
from ..config import settings
from . import pasos_leadtime as pasos_svc
from .common import proveedor_filtro

# Etapas medidas del lead time, en orden: de un hito al siguiente
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

# Tramos entre los hitos que el sistema mide. Cada paso configurable de un
# plan pertenece a uno; la duración del tramo sale de sus pasos.
TRAMOS = [
    ("liberacion", "Logistics release to XF"),
    ("transito", "XF to port arrival"),
    ("puerto", "Port to warehouse"),
    ("ingreso", "Warehouse entry"),
    ("tienda", "Entry to store"),
]
DESPUES_ARRIBO = ["puerto", "ingreso", "tienda"]
# Plan de respaldo si no hay ninguno configurado
PASOS_DEFECTO = [
    {"codigo": "LIB", "nombre": "Logistics release", "tramo": "liberacion", "dias": 15},
    {"codigo": "TRANS", "nombre": "Transit", "tramo": "transito", "dias": 10},
    {"codigo": "BOD", "nombre": "Port to warehouse", "tramo": "puerto", "dias": 3},
    {"codigo": "ING", "nombre": "Warehouse entry", "tramo": "ingreso", "dias": 2},
    {"codigo": "REEX", "nombre": "Re-export to store", "tramo": "tienda", "dias": 5},
]
# Peso de cada condición para elegir el plan más específico
PESOS = {"proveedor_id": 16, "puerto": 8, "pais": 4, "modo": 2, "region": 1}
CAMPOS_DIAS = {"liberacion": "dias_liberacion", "transito": "dias_transito", "puerto": "dias_puerto_bodega",
               "ingreso": "dias_ingreso", "tienda": "dias_reexportacion"}


def sumar(fecha: date, dias: int, habiles: bool = False, signo: int = 1) -> date:
    """Suma (o resta) días naturales o hábiles (lunes a viernes)."""
    if not habiles:
        return fecha + timedelta(days=signo * dias)
    d, n = fecha, dias
    while n > 0:
        d += timedelta(days=signo)
        if d.weekday() < 5:
            n -= 1
    return d


def _deps(pasos: list[dict]) -> dict[str, str | None]:
    """De qué paso arranca cada uno: el indicado, el anterior (por defecto) o
    ninguno (INICIO: en paralelo desde el inicio del tramo)."""
    out, previo = {}, None
    for p in pasos:
        d = p.get("depende") or previo
        out[p["codigo"]] = None if d == "INICIO" else d
        previo = p["codigo"]
    return out


def _tramo(fecha: date, pasos: list[dict], signo: int) -> date:
    if not pasos:
        return fecha
    deps = _deps(pasos)
    if signo > 0:  # cada paso arranca cuando termina el que lo precede; el tramo acaba con el último
        fin: dict[str, date] = {}
        for p in pasos:
            arranque = fin.get(deps[p["codigo"]], fecha) if deps[p["codigo"]] else fecha
            fin[p["codigo"]] = sumar(arranque, int(p.get("dias") or 0), bool(p.get("habiles")), 1)
        return max(fin.values())
    # Hacia atrás: cada paso debe terminar antes de que arranque cualquiera que dependa de él
    ini: dict[str, date] = {}
    for p in reversed(pasos):
        hijos = [ini[q] for q, d in deps.items() if d == p["codigo"] and q in ini]
        ini[p["codigo"]] = sumar(min(hijos) if hijos else fecha, int(p.get("dias") or 0), bool(p.get("habiles")), -1)
    return min(ini.values())


def pasos_de(est: dict, tramo: str) -> list[dict]:
    modo = est.get("modo")
    return [p for p in est["pasos"] if p.get("tramo") == tramo and (not p.get("modo") or p["modo"] == modo)]


def mover(fecha: date | None, est: dict, tramos: list[str], signo: int = 1) -> date | None:
    """Recorre los tramos dados desde una fecha, hacia adelante o hacia atrás.
    Los días extra del tipo de producto se suman al tramo a tienda."""
    if not fecha:
        return None
    for t in (tramos if signo > 0 else list(reversed(tramos))):
        if signo < 0 and t == "tienda" and est.get("dias_extra"):
            fecha -= timedelta(days=est["dias_extra"])
        fecha = _tramo(fecha, pasos_de(est, t), signo)
        if signo > 0 and t == "tienda" and est.get("dias_extra"):
            fecha += timedelta(days=est["dias_extra"])
    return fecha


def _resumen(est: dict, ref: date | None = None) -> dict:
    """Días naturales de cada tramo (para mostrar y comparar)."""
    ref = ref or date.today()
    return {campo: (mover(ref, {**est, "dias_extra": 0}, [t]) - ref).days for t, campo in CAMPOS_DIAS.items()}


class Estandares:
    """Elige el plan de lead time de cada OC (con caché por consulta)."""

    def __init__(self, db: Session):
        regiones = {r.codigo: r for r in db.scalars(select(RegionLeadTime).where(RegionLeadTime.activo))}
        self.regiones = {c: {"codigo": c, "nombre": r.nombre} for c, r in regiones.items()}
        pred = next((r for r in regiones.values() if r.predeterminada), None)
        self.region_defecto = {"codigo": pred.codigo, "nombre": pred.nombre} if pred else \
            {"codigo": "OTROS", "nombre": "Other origins"}
        self.planes = [{"codigo": p.codigo, "nombre": p.nombre, "region": p.region, "pais": p.pais, "puerto": p.puerto,
                        "proveedor_id": p.proveedor_id, "modo": p.modo, "pasos": pasos_svc.cargar(p.pasos)}
                       for p in db.scalars(select(PlanLeadTime).where(PlanLeadTime.activo).order_by(PlanLeadTime.codigo))]
        self.pais_region = {p.codigo: p.region for p in db.scalars(select(Pais))}
        self.nombres = {p.codigo: p.nombre for p in db.scalars(select(Pais))}
        self.puerto_modo = {p.codigo: p.tipo for p in db.scalars(select(Puerto))}
        self.extra_grupo = {g.codigo: g.dias_extra or 0 for g in db.scalars(select(GrupoArticulo))}
        self._cache: dict = {}
        sin = {"codigo": "DEFAULT", "nombre": "Default", "pasos": PASOS_DEFECTO}
        self.defecto = next((p for p in self.planes if not any(p[k] for k in PESOS)), sin)

    def plan(self, region, pais, puerto, proveedor_id, modo) -> dict:
        datos = {"region": region, "pais": pais, "puerto": puerto, "proveedor_id": proveedor_id, "modo": modo}
        mejor, puntos = self.defecto, -1
        for p in self.planes:
            if any(p[k] and p[k] != datos[k] for k in PESOS):
                continue
            pts = sum(w for k, w in PESOS.items() if p[k])
            if pts > puntos:
                mejor, puntos = p, pts
        return mejor

    def de(self, pais: str | None, grupos=None, proveedor_id: int | None = None, puerto: str | None = None,
           modo: str | None = None) -> dict:
        """Plan que aplica a la OC más los días extra del tipo de producto
        (el mayor de los grupos dados)."""
        if isinstance(grupos, str):
            grupos = [grupos]
        extra = max([self.extra_grupo.get(g, 0) for g in (grupos or []) if g] or [0])
        modo = modo or self.puerto_modo.get(puerto or "")
        clave = (pais, extra, proveedor_id, puerto, modo)
        if clave not in self._cache:
            cod_region = self.pais_region.get(pais or "")
            region = self.regiones.get(cod_region or "", self.region_defecto)
            plan = self.plan(cod_region, pais, puerto, proveedor_id, modo)
            est = {**region, "plan": plan["codigo"], "plan_nombre": plan["nombre"], "pasos": plan["pasos"],
                   "modo": modo, "dias_extra": extra}
            self._cache[clave] = {**est, **_resumen(est)}
        return self._cache[clave]

    def de_oc(self, oc: OrdenCompra, grupos=None, modo: str | None = None) -> dict:
        return self.de(oc.pais_origen, grupos, oc.proveedor_id, oc.puerto_despacho, modo)

    def resumen_planes(self) -> list[dict]:
        out = []
        for p in self.planes or [self.defecto]:
            est = {"pasos": p["pasos"], "modo": p.get("modo")}
            out.append({"codigo": p["codigo"], "nombre": p["nombre"], "pasos": len(p["pasos"]), **_resumen(est)})
        return out


def dias_post_arribo(est: dict) -> int:
    """Días naturales que necesita la mercancía después del puerto para estar en tienda."""
    hoy = date.today()
    return (mover(hoy, est, DESPUES_ARRIBO) - hoy).days


def limite_puerto(fecha_tienda: date | None, est: dict) -> date | None:
    """Última fecha de arribo al puerto destino para llegar a tiempo a tienda."""
    return mover(fecha_tienda, est, DESPUES_ARRIBO, -1)


def arribo_estimado(fecha_xf: date | None, est: dict, hoy: date) -> date | None:
    """Sin embarque todavía: la XF (o hoy si ya pasó) más el tránsito del plan."""
    if not fecha_xf:
        return None
    return mover(max(fecha_xf, hoy), est, ["transito"])


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
    """En tiempo, en riesgo (holgura menor al margen) o atrasado (holgura negativa)."""
    if holgura is None:
        return None
    return "ATRASO" if holgura < 0 else "JUSTO" if holgura < settings.DIAS_MARGEN_RIESGO else "A_TIEMPO"


def estado_tiempo(tienda_estimada: date | None, fecha_tienda: date | None) -> dict:
    """Estado frente a la fecha requerida en tienda; sin una de las dos fechas
    queda pendiente (no se inventa un resultado)."""
    if not tienda_estimada or not fecha_tienda:
        return {"estado": None, "holgura": None}
    holgura = (fecha_tienda - tienda_estimada).days
    return {"estado": _riesgo(holgura), "holgura": holgura}


def analizar_oc(oc: OrdenCompra, h: dict | None, est: dict, hoy: date) -> dict:
    """Hitos de la OC con su meta, fecha real o estimada y si va temprano o tarde."""
    h = h or {}
    xf, tienda = oc.fecha_xf, oc.fecha_tienda
    lim_arribo = limite_puerto(tienda, est)
    real = {"creada": oc.fecha, "lib_comercial": oc.fecha_lib_comercial, "lib_logistica": oc.fecha_lib_logistica,
            "recoleccion": h.get("recoleccion"), "salida": h.get("salida"), "arribo": h.get("arribo"),
            "entrega": h.get("entrega"), "ingreso": h.get("ingreso"), "tienda": None}
    meta = {
        "lib_logistica": mover(xf, est, ["liberacion"], -1),
        "recoleccion": xf,
        "salida": mover(lim_arribo, est, ["transito"], -1),
        "arribo": lim_arribo,
        "entrega": mover(lim_arribo, est, ["puerto"]),
        "ingreso": mover(lim_arribo, est, ["puerto", "ingreso"]),
        "tienda": tienda,
    }
    # Estimados de lo que falta, encadenados desde el arribo
    est_fecha: dict[str, date | None] = {}
    if not real["salida"]:
        est_fecha["salida"] = h.get("etd")
    salio = real["salida"] or h.get("etd")
    arribo = (real["arribo"] or h.get("eta") or mover(salio, est, ["transito"])
              or arribo_estimado(xf, est, hoy))
    if not real["arribo"]:
        est_fecha["arribo"] = arribo
    entrega = real["entrega"] or mover(arribo, est, ["puerto"])
    if not real["entrega"]:
        est_fecha["entrega"] = entrega
    ingreso = real["ingreso"] or mover(entrega, est, ["ingreso"])
    if not real["ingreso"]:
        est_fecha["ingreso"] = ingreso
    est_fecha["tienda"] = mover(ingreso, est, ["tienda"])
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
        a = analizar_oc(o, hitos.get(o.id), ests.de_oc(o, [x.grupo for x in o.posiciones]), hoy)
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
        est = ests.de_oc(o, [x.grupo for x in o.posiciones])
        a = analizar_oc(o, hitos.get(o.id), est, hoy)
        items.append({"oc_id": o.id, "oc": o.numero, "proveedor": o.proveedor.nombre, "origen": o.pais_origen,
                      "origen_nombre": ests.nombres.get(o.pais_origen or "", o.pais_origen),
                      "region": est["codigo"], "region_nombre": est["nombre"], "dias_liberacion": est["dias_liberacion"],
                      "plan": est["plan"], "plan_nombre": est["plan_nombre"],
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
        "regiones": ests.resumen_planes(),
        "opciones": {"origenes": [{"valor": c, "texto": f"{c} · {ests.nombres.get(c, c)}"} for c in todas_origen],
                     "regiones": [{"valor": r["codigo"], "texto": r["nombre"]} for r in ests.regiones.values()],
                     "proveedores": todas_prov},
    }
