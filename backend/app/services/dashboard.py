"""Tablero de inicio: lo esencial de cada rol en una sola consulta.

- Proveedor: qué le falta facturar, empacar y finalizar, y dónde va su carga.
- Equipo interno: qué está listo para embarcar, qué falta confirmar, cómo van
  los contenedores y cada proveedor.
"""
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..empresa import regla
from ..models import (
    Embarque,
    Factura,
    OrdenCompra,
    PosicionOC,
    Producto,
    Proveedor,
    UnidadCarga,
    Usuario,
    ahora,
)
from .cantidades import cubierto_por_ids, facturado_por_posicion, nombre_factura, totales_pl
from .common import EDITABLE_FACTURA, EDITABLE_PL, es_interno, proveedor_filtro
from .facturas import _lista_para_transporte, resumen_distribucion, validar_factura
from .packing import validar_pl
from .transporte import resumen_unidad
from . import visibilidad
from .varios import listar_alertas

ETAPAS = ("por_facturar", "sin_pl", "sin_caja", "empacado", "embarcado")
ESTADOS_EN_CAMINO = ("PLANIFICADO", "EN_TRANSITO", "ARRIBADO")


def _meses(n: int) -> list[str]:
    hoy = date.today().replace(day=1)
    res = []
    for _ in range(n):
        res.append(hoy.strftime("%Y-%m"))
        hoy = (hoy - timedelta(days=1)).replace(day=1)
    return list(reversed(res))


def _saldo_ocs(db: Session, prov: int | None) -> dict:
    """Saldo por facturar de las OCs liberadas: cantidades por unidad de
    medida (nunca se suman pares con unidades) y valor por moneda."""
    consulta = (
        select(PosicionOC.id, PosicionOC.unidad, PosicionOC.cantidad, PosicionOC.precio,
               OrdenCompra.moneda, OrdenCompra.proveedor_id, OrdenCompra.id)
        .join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id)
        .where(OrdenCompra.liberada.is_(True), PosicionOC.bloqueada.is_(False))
    )
    if prov:
        consulta = consulta.where(OrdenCompra.proveedor_id == prov)
    filas = db.execute(consulta).all()
    facturado = facturado_por_posicion(db, [f[0] for f in filas])
    por_unidad: dict[str, int] = defaultdict(int)
    valor: dict[str, float] = defaultdict(float)
    por_proveedor: dict[int, float] = defaultdict(float)
    ocs = set()
    for pid, unidad, cantidad, precio, moneda, prov_id, oc_id in filas:
        saldo = max(cantidad - facturado.get(pid, 0), 0)
        if saldo:
            por_unidad[unidad] += saldo
            if precio is not None and moneda:  # sin precio el valor queda pendiente
                valor[moneda] += saldo * precio
                por_proveedor[prov_id] += saldo * precio
            ocs.add(oc_id)
    return {"por_unidad": dict(por_unidad), "valor": dict(valor), "ocs": len(ocs),
            "por_proveedor": dict(por_proveedor)}


def _moneda_principal(valor: dict[str, float]) -> tuple[str, float]:
    if not valor:
        return "USD", 0.0
    moneda = max(valor, key=valor.get)
    return moneda, round(valor[moneda], 2)


def _flujo(db: Session, facturas: list[Factura], saldo: dict) -> dict:
    """Dónde está la mercancía, por unidad de medida: por facturar, facturada
    sin packing list, en PL sin caja, empacada y ya embarcada."""
    flujo: dict[str, dict] = {}

    def etapa(unidad: str) -> dict:
        return flujo.setdefault(unidad, {e: 0 for e in ETAPAS})

    for unidad, c in saldo["por_unidad"].items():
        etapa(unidad)["por_facturar"] += c
    lineas = {l.id: l for f in facturas for l in f.lineas}
    plls = [pll for f in facturas for pl in f.packing_lists if pl.estado != "CANCELADO" for pll in pl.lineas]
    cubierto = cubierto_por_ids(db, [p.id for p in plls])
    en_pl: dict[int, int] = defaultdict(int)
    for pll in plls:
        en_pl[pll.factura_linea_id] += pll.cantidad
        unidad = pll.factura_linea.unidad
        u = pll.pl.unidad
        if u and pll.pl.asignacion == "CONFIRMADA" and u.embarque.estado != "PLANIFICADO":
            etapa(unidad)["embarcado"] += pll.cantidad
        else:
            c = cubierto.get(pll.id, 0)
            etapa(unidad)["empacado"] += c
            etapa(unidad)["sin_caja"] += pll.cantidad - c
    for lid, l in lineas.items():
        etapa(l.unidad)["sin_pl"] += max(l.cantidad - en_pl.get(lid, 0), 0)
    return flujo


def _cubetas(desde: date, hasta: date) -> tuple[str, list[tuple[date, date, str]]]:
    """Agrupa el periodo según su largo: por día (hasta 2 semanas), por
    semana (hasta ~3 meses) o por mes."""
    dias = (hasta - desde).days + 1
    out = []
    if dias <= 14:
        d = desde
        while d <= hasta:
            out.append((d, d, d.strftime("%b %d")))
            d += timedelta(days=1)
        return "dia", out
    if dias <= 95:
        d = desde - timedelta(days=desde.weekday())
        while d <= hasta:
            fin = d + timedelta(days=6)
            out.append((max(d, desde), min(fin, hasta), f"{max(d, desde):%b %d}"))
            d = fin + timedelta(days=1)
        return "semana", out
    d = desde.replace(day=1)
    fmt = "%b" if desde.year == hasta.year else "%b %y"
    while d <= hasta:
        sig = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        out.append((max(d, desde), min(sig - timedelta(days=1), hasta), d.strftime(fmt)))
        d = sig
    return "mes", out


def _fecha_factura(f: Factura) -> date | None:
    return f.fecha or (f.finalizado_en.date() if f.finalizado_en else None)


def _serie_facturado(facturas: list[Factura], moneda: str, desde: date, hasta: date, marcas: set | None) -> dict:
    """Valor facturado (facturas finalizadas) en el periodo, agrupado según su largo."""
    grano, cubetas = _cubetas(desde, hasta)
    serie = [{"etiqueta": e, "desde": a, "hasta": b, "importe": 0.0, "facturas": 0} for a, b, e in cubetas]
    for f in facturas:
        if f.estado != "FINALIZADA" or f.moneda != moneda:
            continue
        fecha = _fecha_factura(f)
        if not fecha or fecha < desde or fecha > hasta:
            continue
        lineas = [l for l in f.lineas if not marcas or (l.marca or "") in marcas]
        if not lineas:
            continue
        c = next((x for x in serie if x["desde"] <= fecha <= x["hasta"]), None)
        if c:
            c["importe"] += sum(l.cantidad * l.precio_unitario for l in lineas)
            c["facturas"] += 1
    for x in serie:
        x["importe"] = round(x["importe"], 2)
    return {"grano": grano, "serie": serie}


def _visibles(indicadores: list[dict]) -> list[dict]:
    """Sin los indicadores de datos que el rol no ve (importes, riesgo frente a
    la fecha en tienda)."""
    return [k for k in indicadores
            if not (k.get("formato") == "moneda" and visibilidad.oculto("precios"))
            and not (k.get("clave") == "riesgo" and visibilidad.oculto("fechas_internas"))]


def _resumen_periodo(db: Session, facturas: list[Factura], moneda: str, desde: date, hasta: date,
                     prov: int | None, marcas: set | None, interno: bool) -> list[dict]:
    """Lo que pasó en el periodo elegido (por defecto, el mes en curso)."""
    fin = [f for f in facturas if f.estado == "FINALIZADA" and (_fecha_factura(f) or date.min) >= desde
           and (_fecha_factura(f) or date.max) <= hasta]
    importe = sum(l.cantidad * l.precio_unitario for f in fin if f.moneda == moneda for l in f.lineas
                  if not marcas or (l.marca or "") in marcas)
    pls = [pl for f in facturas for pl in f.packing_lists if pl.estado == "FINALIZADO" and pl.actualizado_en
           and desde <= pl.actualizado_en.date() <= hasta]
    llegadas = db.scalars(select(Embarque).where(Embarque.eta >= desde, Embarque.eta <= hasta)).all()
    if prov:
        llegadas = [e for e in llegadas if any(pl.factura.proveedor_id == prov for u in e.unidades for pl in u.packing_lists)]
    out = [
        {"clave": "facturado", "titulo": "Invoiced", "valor": round(importe, 2), "formato": "moneda", "moneda": moneda,
         "detalle": f"{len(fin)} finalized invoices"},
        {"clave": "pls", "titulo": "Packing lists finalized", "valor": len(pls),
         "detalle": f"{sum(totales_pl(pl)['cajas'] for pl in pls):,} cartons"},
        {"clave": "llegadas", "titulo": "Shipments arriving", "valor": len(llegadas),
         "detalle": f"{sum(1 for e in llegadas if e.estado in ('ARRIBADO', 'ENTREGADO', 'RECIBIDO'))} already arrived"},
    ]
    q = select(Producto).where(Producto.revisado_en.is_not(None))
    if prov:
        q = q.where(Producto.proveedor_id == prov)
    aprobados = [p for p in db.scalars(q) if desde <= p.revisado_en.date() <= hasta]
    out.append({"clave": "clasificados", "titulo": "Products classified", "valor": len(aprobados),
                "detalle": "HS codes approved" if interno else "technical sheets approved"})
    return out


def _facturado_por_mes(facturas: list[Factura], moneda: str) -> list[dict]:
    meses = _meses(6)
    res = {m: {"mes": m, "importe": 0.0, "facturas": 0} for m in meses}
    for f in facturas:
        if f.estado != "FINALIZADA" or f.moneda != moneda:
            continue
        fecha = f.fecha or (f.finalizado_en.date() if f.finalizado_en else None)
        clave = fecha.strftime("%Y-%m") if fecha else None
        if clave in res:
            res[clave]["importe"] += sum(l.cantidad * l.precio_unitario for l in f.lineas)
            res[clave]["facturas"] += 1
    for r in res.values():
        r["importe"] = round(r["importe"], 2)
    return list(res.values())


def _envios(db: Session, prov: int | None) -> list[dict]:
    consulta = select(Embarque).where(Embarque.estado.in_(ESTADOS_EN_CAMINO))
    res = []
    for e in db.scalars(consulta).all():
        pls = [pl for u in e.unidades for pl in u.packing_lists
               if pl.estado != "CANCELADO" and (not prov or pl.factura.proveedor_id == prov)]
        if prov and not pls:
            continue
        res.append({
            "id": e.id,
            "codigo": e.codigo,
            "estado": e.estado,
            "tipo_transporte": e.tipo_transporte,
            "documento": e.documento_numero,
            "origen": e.puerto_origen,
            "destino": e.puerto_destino,
            "etd": e.etd,
            "eta": e.eta,
            "unidades": [u.numero or u.etiqueta for u in e.unidades],
            "facturas": sorted({nombre_factura(pl.factura) for pl in pls}),
            "factura_ids": sorted({pl.factura_id for pl in pls}),
            "packing_lists": len(pls),
            "tentativos": sum(1 for pl in pls if pl.asignacion == "TENTATIVA"),
            "cajas": sum(totales_pl(pl)["cajas"] for pl in pls),
        })
    orden = {"EN_TRANSITO": 0, "ARRIBADO": 1, "PLANIFICADO": 2}
    res.sort(key=lambda x: (orden[x["estado"]], x["eta"] or date.max))
    return res[:8]


def _tareas(db: Session, user: Usuario, facturas: list[Factura], distribucion: dict, prov: int | None = None) -> list[dict]:
    """Próximos pasos concretos, ordenados por lo que destraba más trabajo."""
    tareas = []
    limite = ahora() - timedelta(days=regla("DIAS_ALERTA_BORRADOR"))
    for f in facturas:
        nombre = nombre_factura(f)
        r = distribucion[f.id]
        if f.estado in EDITABLE_FACTURA:
            pendientes = validar_factura(db, f)
            sin_pl = r["facturado"] - r["asignado"]
            if f.estado == "EN_CORRECCION":
                tareas.append({"prioridad": 0, "tipo": "correccion", "titulo": f"Correct {nombre}",
                               "detalle": "It was reopened by the internal team.",
                               "ruta": f"/facturas/{f.id}", "accion": "Open"})
            elif pendientes:
                tareas.append({"prioridad": 2, "tipo": "datos", "titulo": f"Complete {nombre}",
                               "detalle": f"{len(pendientes)} items missing to finalize it.",
                               "ruta": f"/facturas/{f.id}", "accion": "Complete"})
            if sin_pl > 0 and f.lineas:
                tareas.append({"prioridad": 1, "tipo": "empacar", "titulo": f"Pack {nombre}",
                               "detalle": f"{sin_pl:,} without packing list.",
                               "ruta": f"/facturas/{f.id}?tab=pl", "accion": "Pack"})
            if not pendientes and f.estado == "BORRADOR" and not sin_pl:
                tareas.append({"prioridad": 3, "tipo": "finalizar", "titulo": f"Finalize {nombre}",
                               "detalle": "Everything is complete.", "ruta": f"/facturas/{f.id}",
                               "accion": "Finalize"})
            if f.estado == "BORRADOR" and f.creado_en < limite:
                tareas.append({"prioridad": 4, "tipo": "antiguo", "titulo": f"{nombre} has been in draft for days",
                               "detalle": "It keeps reserving PO quantities.",
                               "ruta": f"/facturas/{f.id}", "accion": "Review"})
        for pl in f.packing_lists:
            if pl.estado not in EDITABLE_PL or f.estado == "CANCELADA":
                continue
            errores = validar_pl(pl)
            sin_caja = [e for e in errores if e.get("codigo") == "sin_caja"]
            if sin_caja:
                detalle = sin_caja[0]["mensaje"]
            elif errores:
                detalle = f"{len(errores)} carton details to complete."
            else:
                detalle = "Ready to finalize."
            tareas.append({"prioridad": 1 if sin_caja else 2, "tipo": "pl",
                           "titulo": f"{pl.numero} of {nombre}", "detalle": detalle,
                           "ruta": f"/packing-lists/{pl.id}",
                           "accion": "Pack" if sin_caja else ("Complete" if errores else "Finalize")})
    if es_interno(user):
        for f in facturas:
            r = distribucion[f.id]
            if f.estado == "FINALIZADA" and r["pls"] and r["pls_confirmados"] < r["pls"]:
                sin_unidad = sum(1 for pl in f.packing_lists if pl.estado == "FINALIZADO" and not pl.unidad_carga_id)
                if sin_unidad:
                    tareas.append({"prioridad": 1, "tipo": "embarcar", "titulo": f"Ship {nombre_factura(f)}",
                                   "detalle": f"{sin_unidad} finalized PLs without container ({f.proveedor.nombre}).",
                                   "ruta": "/transporte", "accion": "Assign"})
    tareas += _tareas_productos(db, user, prov)
    tareas.sort(key=lambda t: t["prioridad"])
    return tareas[:12]


def _tareas_productos(db: Session, user: Usuario, prov: int | None) -> list[dict]:
    """Fichas técnicas: el equipo interno aprueba; el proveedor completa y corrige."""
    q = select(Producto.estado, func.count()).group_by(Producto.estado)
    if prov:
        q = q.where(Producto.proveedor_id == prov)
    n = dict(db.execute(q).all())
    out = []
    if es_interno(user):
        if n.get("revision"):
            out.append({"prioridad": 2, "tipo": "clasificar", "titulo": f"Review {n['revision']} technical sheet" + ("s" if n["revision"] > 1 else ""),
                        "detalle": "Sent to review with a suggested HS code: approve or return them.",
                        "ruta": "/productos?estado=revision", "accion": "Review"})
    else:
        if n.get("observado"):
            out.append({"prioridad": 0, "tipo": "correccion", "titulo": f"Correct {n['observado']} technical sheet" + ("s" if n["observado"] > 1 else ""),
                        "detalle": "Customs returned them with notes.", "ruta": "/productos?estado=observado",
                        "accion": "Correct"})
        if n.get("borrador"):
            out.append({"prioridad": 3, "tipo": "clasificar", "titulo": f"Complete {n['borrador']} technical sheet" + ("s" if n["borrador"] > 1 else ""),
                        "detalle": "Products without the data customs needs to classify them.",
                        "ruta": "/productos?estado=borrador", "accion": "Complete"})
        if n.get("sugerida"):
            out.append({"prioridad": 2, "tipo": "clasificar", "titulo": f"Send {n['sugerida']} technical sheet" + ("s" if n["sugerida"] > 1 else "") + " to review",
                        "detalle": "Complete drafts: nobody reviews them until you send them.",
                        "ruta": "/productos?estado=sugerida", "accion": "Send"})
    return out


def _atencion(db: Session, user: Usuario, prov: int | None, seg: list[dict], en_proceso: list, pls_abiertos: list,
              sin_unidad: list, atrasadas: set) -> list[dict]:
    """«¿Qué necesita mi atención hoy?»: cada indicador abre la lista ya
    filtrada. Primero lo que bloquea el siguiente paso, luego lo que vence o
    llega pronto. Solo aparece lo que tiene algo pendiente."""
    from .common import tiene
    from .productos import ids_bloquean_facturas

    hoy = date.today()
    semana = hoy + timedelta(days=7)
    interno = es_interno(user)
    out = []

    def item(clave, titulo, valor, detalle, ruta, query=None, tono="alerta"):
        if valor:
            out.append({"clave": clave, "titulo": titulo, "valor": valor, "detalle": detalle, "ruta": ruta,
                        "query": query or {}, "tono": tono})

    if tiene(user, "producto.ver"):
        item("bloquean", "Products blocking invoices", len(ids_bloquean_facturas(db, prov)),
             "Without an approved HS code, their invoices cannot be finalized.", "/productos", {"estado": "bloquean"}, "error")
        estados = dict(db.execute(select(Producto.estado, func.count()).where(*([Producto.proveedor_id == prov] if prov else []))
                                  .group_by(Producto.estado)).all())
        if interno:
            item("clasificar", "Products to classify", estados.get("revision", 0), "Sent to review with a suggested HS code.",
                 "/productos", {"estado": "revision"})
        else:
            item("devueltos", "Technical sheets returned", estados.get("observado", 0), "Customs returned them with notes.",
                 "/productos", {"estado": "observado"}, "error")
    item("facturas", "Invoices to finalize", len(en_proceso), "Drafts and invoices under correction.", "/facturas",
         {"vista": "editables"}, "info")
    pesos = sum(1 for pl in pls_abiertos if any(e.get("codigo") in ("sin_peso", "peso_estimado") for e in validar_pl(pl)))
    item("pl_incompletos", "Packing lists incomplete", len(pls_abiertos),
         f"{pesos} with weights to confirm." if pesos else "Cartons to pack or finalize.", "/facturas", {"vista": "pl_incompletos"})
    xf_semana = {f["oc"] for f in seg if f["etapa"] == "POR_FACTURAR" and f["fecha_xf"] and hoy <= f["fecha_xf"] <= semana}
    item("xf_proxima", "POs with XF this week", len(xf_semana), "With quantities still to invoice.", "/seguimiento",
         {"vista": "ordenes", "etapa": "POR_FACTURAR", "fecha_xf_desde": hoy.isoformat(), "fecha_xf_hasta": semana.isoformat()})
    xf_vencida = {f["oc"] for f in seg if f["etapa"] == "POR_FACTURAR" and f["fecha_xf"] and f["fecha_xf"] < hoy}
    item("xf_vencida", "POs past XF", len(xf_vencida), "The XF date passed and there is quantity to invoice.", "/seguimiento",
         {"vista": "ordenes", "xf_vencida": "1"}, "error")
    if interno or tiene(user, "transporte.gestionar"):
        item("sin_contenedor", "Packing lists without load unit", len(sin_unidad), "Finalized and waiting for a container.",
             "/transporte", {"estado": "PLANIFICADO"})
        salen = db.scalar(select(func.count()).select_from(Embarque).where(Embarque.estado == "PLANIFICADO", Embarque.etd >= hoy,
                                                                           Embarque.etd <= semana)) or 0
        item("salen", "Shipments departing this week", salen, "Planned with ETD in the next 7 days.", "/transporte",
             {"estado": "PLANIFICADO"}, "info")
    item("riesgo", "POs at risk of arriving late", len(atrasadas), "They arrive after the in-store date.", "/seguimiento",
         {"riesgo": "ATRASO"}, "error")
    llegan = {f["embarque"] for f in seg if f.get("embarque") and f.get("eta") and f["etapa"] in ("CONTENEDOR", "EN_TRANSITO")
              and hoy <= f["eta"] <= semana}
    item("llegan", "Arrivals this week", len(llegan), "Shipments with ETA in the next 7 days.", "/seguimiento",
         {"vista": "embarques", "eta_desde": hoy.isoformat(), "eta_hasta": semana.isoformat()}, "info")
    # Solo lo que el rol puede abrir
    permiso = {"/productos": "producto.ver", "/facturas": "oc.ver", "/seguimiento": "seguimiento.ver", "/transporte": "transporte.gestionar"}
    out = [x for x in out if tiene(user, permiso[x["ruta"]])]
    orden = {"error": 0, "alerta": 1, "info": 2}
    return sorted(out, key=lambda x: orden[x["tono"]])


def _contenedores(db: Session) -> list[dict]:
    unidades = db.scalars(
        select(UnidadCarga).join(Embarque).where(Embarque.estado == "PLANIFICADO")
        .order_by(Embarque.etd.nullslast(), UnidadCarga.id)
    ).all()
    res = []
    for u in unidades[:8]:
        r = resumen_unidad(u)
        r["embarque"] = u.embarque.codigo
        r["etd"] = u.embarque.etd
        res.append(r)
    return res


def _por_proveedor(db: Session, facturas: list[Factura], distribucion: dict, saldo: dict) -> list[dict]:
    filas = {p.id: {"id": p.id, "nombre": p.nombre, "por_facturar": None if visibilidad.oculto("precios") else round(saldo["por_proveedor"].get(p.id, 0), 2),
                    "en_proceso": 0, "pl_abiertos": 0, "listas": 0, "en_camino": 0}
             for p in db.scalars(select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.nombre))}
    for f in facturas:
        fila = filas.get(f.proveedor_id)
        if not fila:
            continue
        r = distribucion[f.id]
        fila["en_proceso"] += f.estado in EDITABLE_FACTURA
        fila["pl_abiertos"] += sum(1 for pl in f.packing_lists if pl.estado in EDITABLE_PL)
        fila["listas"] += _lista_para_transporte(f, r) and r["pls_confirmados"] < r["pls"]
        fila["en_camino"] += sum(1 for pl in f.packing_lists
                                 if pl.estado != "CANCELADO" and pl.unidad
                                 and pl.unidad.embarque.estado in ("EN_TRANSITO", "ARRIBADO"))
    return list(filas.values())


def dashboard(db: Session, user: Usuario, proveedor_id: int | None = None, desde: date | None = None,
              hasta: date | None = None, marcas: str | None = None) -> dict:
    prov = proveedor_filtro(user, proveedor_id)
    hoy = date.today()
    desde = desde or hoy.replace(day=1)
    hasta = hasta or hoy
    if hasta < desde:
        desde, hasta = hasta, desde
    filtro_marcas = {m.strip() for m in (marcas or "").split(",") if m.strip()} or None
    interno = es_interno(user)

    consulta = select(Factura).where(Factura.estado != "CANCELADA").order_by(Factura.actualizado_en.desc())
    if prov:
        consulta = consulta.where(Factura.proveedor_id == prov)
    facturas = list(db.scalars(consulta).all())
    distribucion = resumen_distribucion(db, [f.id for f in facturas])
    saldo = _saldo_ocs(db, prov)
    moneda, por_facturar = _moneda_principal(saldo["valor"])
    envios = _envios(db, prov)

    en_proceso = [f for f in facturas if f.estado in EDITABLE_FACTURA]
    pls_abiertos = [pl for f in facturas for pl in f.packing_lists if pl.estado in EDITABLE_PL]
    en_camino = [e for e in envios if e["estado"] in ("EN_TRANSITO", "ARRIBADO")]
    proximo = min((e["eta"] for e in en_camino if e["eta"]), default=None)

    listas = [f for f in facturas if _lista_para_transporte(f, distribucion[f.id])
              and distribucion[f.id]["pls_confirmados"] < distribucion[f.id]["pls"]]

    kpis = [
        {"clave": "por_facturar", "titulo": "To invoice", "valor": por_facturar, "formato": "moneda",
         "moneda": moneda, "detalle": f"on {saldo['ocs']} POs", "ruta": "/ordenes", "tono": "normal"},
        {"clave": "en_proceso", "titulo": "Invoices in progress", "valor": len(en_proceso),
         "detalle": f"{sum(1 for f in en_proceso if f.estado == 'EN_CORRECCION')} under correction",
         "ruta": "/facturas", "query": {"vista": "editables"}, "tono": "normal"},
        {"clave": "pl_abiertos", "titulo": "Open packing lists", "valor": len(pls_abiertos),
         "detalle": "to pack or finalize", "ruta": "/facturas", "query": {"vista": "pl_incompletos"},
         "tono": "alerta" if pls_abiertos else "normal"},
    ]
    if interno:
        sin_unidad = [pl for f in facturas for pl in f.packing_lists
                      if pl.estado == "FINALIZADO" and not pl.unidad_carga_id]
        kpis += [
            {"clave": "listas", "titulo": "Ready to ship", "valor": len(listas),
             "detalle": f"{len(sin_unidad)} PLs without container", "ruta": "/facturas",
             "query": {"vista": "lista_transporte"}, "tono": "exito" if listas else "normal"},
            {"clave": "sin_contenedor", "titulo": "Finalized without container", "valor": len(sin_unidad),
             "detalle": "packing lists to load", "ruta": "/transporte", "query": {"estado": "PLANIFICADO"},
             "tono": "alerta" if sin_unidad else "normal"},
        ]
    kpis.append({"clave": "en_camino", "titulo": "Shipments on the way", "valor": len(en_camino),
                 "formato": "numero", "detalle": f"next arrival {proximo:%b %d}" if proximo else "no upcoming arrivals",
                 "fecha": proximo, "ruta": "/transporte" if interno else "/facturas",
                 "query": {"estado": "EN_TRANSITO"} if interno else {}, "tono": "normal"})

    from .seguimiento import filas_seguimiento

    seg = filas_seguimiento(db, user, prov)
    atrasadas = {f["oc"] for f in seg if f["riesgo"] == "ATRASO"}
    pendientes_lib = {f["oc"] for f in seg if f["etapa"] == "PEND_LIBERACION"}
    kpis.append({"clave": "riesgo", "titulo": "POs at risk of delay", "valor": len(atrasadas),
                 "detalle": "arrive after the in-store date", "ruta": "/seguimiento",
                 "query": {"riesgo": "ATRASO"}, "tono": "alerta" if atrasadas else "exito"})
    sin_unidad = [pl for f in facturas for pl in f.packing_lists if pl.estado == "FINALIZADO" and not pl.unidad_carga_id]
    atencion = _atencion(db, user, prov, seg, en_proceso, pls_abiertos, sin_unidad, atrasadas)
    tareas = _tareas(db, user, facturas, distribucion, prov)
    if pendientes_lib:
        tareas.insert(0, {"prioridad": 1, "tipo": "liberacion",
                          "titulo": f"{len(pendientes_lib)} POs not released",
                          "detalle": "No commercial release (P) or logistics at 304: they cannot be invoiced.",
                          "ruta": "/ordenes?liberacion=304&solo_disponible=0", "accion": "View"})
    resumen = _resumen_periodo(db, facturas, moneda, desde, hasta, prov, filtro_marcas, interno)
    return {
        "rol": user.rol,
        "moneda": moneda,
        "kpis": _visibles(kpis),
        "atencion": _visibles(atencion),
        "tareas": tareas[:12],
        "flujo": _flujo(db, facturas, saldo),
        "facturado_mes": _facturado_por_mes(facturas, moneda),
        "periodo": {"desde": desde, "hasta": hasta,
                    "resumen": _visibles(resumen),
                    "facturado": _serie_facturado(facturas, moneda, desde, hasta, filtro_marcas),
                    "marcas": sorted({l.marca for f in facturas for l in f.lineas if l.marca})},
        "envios": envios,
        "contenedores": _contenedores(db) if interno else [],
        "proveedores": _por_proveedor(db, facturas, distribucion, saldo) if interno and not prov else [],
        "alertas": listar_alertas(db, user, prov) if interno else [],
    }
