"""Tablero de inicio: lo esencial de cada rol en una sola consulta.

- Proveedor: qué le falta facturar, empacar y finalizar, y dónde va su carga.
- Equipo interno: qué está listo para embarcar, qué falta confirmar, cómo van
  los contenedores y cada proveedor.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import dinero
from app.core.empresa import regla
from app.modelos import Alerta, Embarque, Factura, PackingList, Producto, Proveedor, UnidadCarga, Usuario, ahora
from app.modulos.acceso import visibilidad
from app.modulos.acceso.permisos import es_interno, proveedor_filtro, sociedad_filtro, tiene
from app.modulos.empaque.packing import validar_pl
from app.modulos.facturacion.cantidades import cubierto_por_ids, nombre_factura, totales_pl
from app.modulos.facturacion.estados import EDITABLE_FACTURA, EDITABLE_PL
from app.modulos.facturacion.facturas import _lista_para_transporte, resumen_distribucion, validar_factura
from app.modulos.seguimiento import metricas
from app.modulos.seguimiento.alertas import listar_alertas
from app.modulos.transporte.transporte import resumen_unidad

ETAPAS = ("por_facturar", "sin_pl", "sin_caja", "empacado", "embarcado")
ESTADOS_EN_CAMINO = ("PLANIFICADO", "EN_TRANSITO", "ARRIBADO")


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
        if u and pll.pl.asignacion == "CONFIRMADA" and u.embarque.estado not in ("PLANIFICADO", "CANCELADO"):
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


def _serie_facturado(fact: dict, moneda: str | None, desde: date, hasta: date) -> dict:
    """Valor facturado (facturas finalizadas) en la moneda principal, agrupado
    según el largo del periodo; los montos en otras monedas van aparte."""
    grano, cubetas = _cubetas(desde, hasta)
    serie = [{"etiqueta": e, "desde": a, "hasta": b, "importe": dinero.CERO, "facturas": 0} for a, b, e in cubetas]
    for f in fact["detalle"]:
        if f["moneda"] != moneda or not f["fecha"]:
            continue
        c = next((x for x in serie if x["desde"] <= f["fecha"] <= x["hasta"]), None)
        if c:
            c["importe"] += f["importe"]
            c["facturas"] += 1
    for x in serie:
        x["importe"] = dinero.numero(dinero.redondear(x["importe"], moneda))
    return {"grano": grano, "moneda": moneda, "serie": serie,
            "otras": metricas.otras_monedas(fact["por_moneda"], moneda)}


def _visibles(indicadores: list[dict]) -> list[dict]:
    """Sin los indicadores de datos que el rol no ve (importes, riesgo frente a
    la fecha en tienda)."""
    return [k for k in indicadores
            if not (k.get("formato") == "moneda" and visibilidad.oculto("precios"))
            and not (k.get("clave") == "riesgo" and visibilidad.oculto("fechas_internas"))]


def _resumen_periodo(db: Session, user: Usuario, prov, fact: dict, moneda: str | None, desde: date, hasta: date) -> list[dict]:
    """Lo que pasó en el periodo elegido (por defecto, el mes en curso)."""
    pls = db.execute(
        select(PackingList).join(Factura, Factura.id == PackingList.factura_id)
        .where(PackingList.estado == "FINALIZADO", PackingList.finalizado_en >= datetime.combine(desde, time.min),
               PackingList.finalizado_en < datetime.combine(hasta + timedelta(days=1), time.min),
               *sociedad_filtro(user, Factura.sociedad), *([Factura.proveedor_id.in_(prov)] if prov else []))
    ).scalars().all()
    arribos = metricas.arribos(db, user, prov, desde, hasta)["n"]
    previstas = metricas.llegadas_previstas(db, user, prov, max(desde, date.today()), hasta) if hasta >= date.today() else 0
    valor = fact["por_moneda"].get(moneda, dinero.CERO)
    return [
        {"clave": "facturado", "titulo": "Invoiced", "valor": dinero.numero(dinero.redondear(valor, moneda)),
         "formato": "moneda", "moneda": moneda, "otras": metricas.otras_monedas(fact["por_moneda"], moneda),
         "detalle": f"{fact['facturas']} finalized invoices"},
        {"clave": "pls", "titulo": "Packing lists finalized", "valor": len(pls),
         "detalle": f"{sum(totales_pl(pl)['cajas'] for pl in pls):,} cartons"},
        {"clave": "arribos", "titulo": "Shipments arrived", "valor": arribos,
         "detalle": f"{previstas} more expected in the period" if previstas else "actual arrival in the period"},
    ]


def _envios(db: Session, user: Usuario, prov: frozenset | None) -> list[dict]:
    """Los próximos embarques (hasta 8) dentro del alcance del usuario."""
    consulta = metricas.embarques(db, user, prov, Embarque.estado.in_(ESTADOS_EN_CAMINO))
    res = []
    for e in db.scalars(consulta).all():
        pls = [pl for u in e.unidades for pl in u.packing_lists
               if pl.estado != "CANCELADO" and (not prov or pl.factura.proveedor_id in prov)]
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
            "cajas": sum(totales_pl(pl)["cajas"] for pl in pls),
        })
    orden = {"EN_TRANSITO": 0, "ARRIBADO": 1, "PLANIFICADO": 2}
    res.sort(key=lambda x: (orden[x["estado"]], x["eta"] or date.max))
    return res[:8]


def _tareas(db: Session, user: Usuario, facturas: list[Factura], distribucion: dict, prov: frozenset | None = None) -> list[dict]:
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


def _tareas_productos(db: Session, user: Usuario, prov: frozenset | None) -> list[dict]:
    """Fichas técnicas: el equipo interno aprueba; el proveedor completa y corrige."""
    q = select(Producto.estado, func.count()).group_by(Producto.estado)
    if prov:
        q = q.where(Producto.proveedor_id.in_(prov))
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


def _atencion(db: Session, user: Usuario, prov: frozenset | None, seg: list[dict], tarde: set, sin_unidad: list,
              franja: set) -> list[dict]:
    """«¿Qué necesita mi atención hoy?»: cada indicador abre la lista ya
    filtrada. Primero lo que bloquea el siguiente paso, luego lo que vence o
    llega pronto. Solo aparece lo que tiene algo pendiente y lo que no está ya
    en la franja de indicadores (`franja`)."""
    from app.modulos.acceso.permisos import tiene
    from app.modulos.productos.productos import ids_bloquean_facturas

    hoy, semana = metricas.semana()
    interno = es_interno(user)
    out = []

    def item(clave, titulo, valor, detalle, ruta, query=None, tono="alerta"):
        if valor and clave not in franja:
            out.append({"clave": clave, "titulo": titulo, "valor": valor, "detalle": detalle, "ruta": ruta,
                        "query": query or {}, "tono": tono})

    if tiene(user, "producto.ver"):
        item("bloquean", "Products blocking invoices", len(ids_bloquean_facturas(db, prov)),
             "Without an approved HS code, their invoices cannot be finalized.", "/productos", {"estado": "bloquean"}, "error")
        estados = dict(db.execute(select(Producto.estado, func.count()).where(*([Producto.proveedor_id.in_(prov)] if prov else []))
                                  .group_by(Producto.estado)).all())
        if interno:
            item("clasificar", "Products to classify", estados.get("revision", 0), "Sent to review with a suggested HS code.",
                 "/productos", {"estado": "revision"})
        else:
            item("devueltos", "Technical sheets returned", estados.get("observado", 0), "Customs returned them with notes.",
                 "/productos", {"estado": "observado"}, "error")
    xf_semana = metricas.oc_xf_en_rango(seg, hoy, semana)
    item("xf_proxima", "POs with XF this week", len(xf_semana), "With quantities still to invoice.", "/seguimiento",
         {"vista": "ordenes", "fecha_xf_desde": hoy.isoformat(), "fecha_xf_hasta": semana.isoformat(),
          "etapa": "POR_FACTURAR,PEND_LIBERACION"})
    xf_vencida = metricas.oc_xf_en_rango(seg, None, hoy - timedelta(days=1))
    item("xf_vencida", "POs past XF", len(xf_vencida), "The XF date passed and there is quantity to invoice.", "/seguimiento",
         {"vista": "ordenes", "xf_vencida": "1"}, "error")
    if interno or tiene(user, "transporte.gestionar"):
        item("sin_contenedor", "Packing lists without load unit", len(sin_unidad), "Finalized and waiting for a container.",
             "/transporte", {"estado": "PLANIFICADO"})
        item("salen", "Shipments departing this week", metricas.embarques_que_salen(db, user, prov, hoy, semana),
             "Planned with ETD in the next 7 days.", "/transporte", {"estado": "PLANIFICADO"}, "info")
    item("llegan", "Arrivals this week", metricas.llegadas_previstas(db, user, prov, hoy, semana),
         "In transit with ETA in the next 7 days.", "/seguimiento",
         {"vista": "embarques", "estado": "EN_TRANSITO", "eta_desde": hoy.isoformat(), "eta_hasta": semana.isoformat()}, "info")
    item("riesgo", "POs arriving late", len(tarde), "Port arrival after the port deadline.", "/seguimiento",
         {"riesgo": "ATRASO"}, "error")
    if interno and tiene(user, "recepcion.registrar"):
        item("por_recibir", "Load units to receive", metricas.unidades_por_recibir(db, user, prov),
             "Arrived and not yet counted at the warehouse.", "/transporte", {"estado": "ARRIBADO,ENTREGADO"})
    if interno and tiene(user, "alertas.ver"):
        diferencias = db.scalar(select(func.count(Alerta.id)).where(
            Alerta.tipo == "recepcion_diferencia", Alerta.resuelta.is_(False),
            *([Alerta.proveedor_id.in_(prov)] if prov else []))) or 0
        item("diferencias", "Receipt differences to claim", diferencias,
             "Short, over or damaged goods in received load units.", "/", {}, "error")
        if out and out[-1]["clave"] == "diferencias":
            out[-1]["hash"] = "#alertas"
    # Solo lo que el rol puede abrir
    permiso = {"/productos": "producto.ver", "/facturas": "oc.ver", "/seguimiento": "seguimiento.ver", "/transporte": "transporte.gestionar",
               "/": "alertas.ver"}
    out = [x for x in out if tiene(user, permiso[x["ruta"]])]
    orden = {"error": 0, "alerta": 1, "info": 2}
    return sorted(out, key=lambda x: orden[x["tono"]])


def _contenedores(db: Session, user: Usuario) -> list[dict]:
    """Unidades de carga de embarques planificados (las primeras 8), dentro del
    alcance del usuario; el llenado es el mayor entre volumen y peso."""
    planificados = metricas.embarques(db, user, None, Embarque.estado == "PLANIFICADO").with_only_columns(Embarque.id)
    unidades = db.scalars(
        select(UnidadCarga).join(Embarque).where(Embarque.id.in_(planificados))
        .order_by(Embarque.etd.nullslast(), UnidadCarga.id).limit(8)
    ).all()
    res = []
    for u in unidades:
        r = resumen_unidad(u)
        r["pct"] = max(x for x in (r.get("pct_cbm"), r.get("pct_kg"), 0) if x is not None)
        r["embarque"] = u.embarque.codigo
        r["etd"] = u.embarque.etd
        res.append(r)
    return res


def _por_proveedor(db: Session, facturas: list[Factura], distribucion: dict, saldo: dict) -> list[dict]:
    """Una fila por proveedor activo: saldo por facturar por moneda (nunca
    sumado entre monedas) y sus documentos en curso."""
    oculto = visibilidad.oculto("precios")
    principal = metricas.moneda_principal({m: v for d in saldo["por_proveedor"].values() for m, v in d.items()})

    def montos(prov_id):
        por_moneda = saldo["por_proveedor"].get(prov_id, {})
        return [{"moneda": m, "valor": dinero.numero(dinero.redondear(v, m))}
                for m, v in sorted(por_moneda.items(), key=lambda x: (x[0] != principal, x[0])) if v]

    filas = {p.id: {"id": p.id, "nombre": p.nombre, "por_facturar": None if oculto else montos(p.id),
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

    # Solo el trabajo en curso: sin canceladas ni las ya recibidas por completo
    # (la historia completa no crece la carga de esta pantalla)
    consulta = (select(Factura).where(Factura.estado != "CANCELADA", ~metricas.facturas_terminadas())
                .order_by(Factura.actualizado_en.desc()))
    if prov:
        consulta = consulta.where(Factura.proveedor_id.in_(prov))
    consulta = consulta.where(*sociedad_filtro(user, Factura.sociedad))
    facturas = list(db.scalars(consulta).all())
    distribucion = resumen_distribucion(db, [f.id for f in facturas])
    saldo = metricas.saldo_por_facturar(db, user, prov)
    moneda = metricas.moneda_principal(saldo["valor"])
    envios = _envios(db, user, prov)
    transito = metricas.embarques_en_transito(db, user, prov)

    en_proceso = [f for f in facturas if f.estado in EDITABLE_FACTURA]
    pls_abiertos = [pl for f in facturas for pl in f.packing_lists if pl.estado in EDITABLE_PL]
    sin_unidad = [pl for f in facturas for pl in f.packing_lists if pl.estado == "FINALIZADO" and not pl.unidad_carga_id]
    listas = [f for f in facturas if _lista_para_transporte(f, distribucion[f.id])
              and distribucion[f.id]["pls_confirmados"] < distribucion[f.id]["pls"]]

    sin_precio = saldo["lineas_sin_precio"]
    kpis = [
        {"clave": "por_facturar", "titulo": "To invoice", "formato": "moneda", "moneda": moneda,
         "valor": dinero.numero(dinero.redondear(saldo["valor"].get(moneda, dinero.CERO), moneda)),
         "otras": metricas.otras_monedas(saldo["valor"], moneda),
         "detalle": f"on {saldo['ocs']} POs" + (f" · {sin_precio} lines without price" if sin_precio else ""),
         "ruta": "/ordenes", "tono": "normal"},
        {"clave": "en_proceso", "titulo": "Documents in progress", "valor": len(en_proceso) + len(pls_abiertos),
         "detalle": f"{len(en_proceso)} invoices · {len(pls_abiertos)} packing lists",
         "ruta": "/facturas", "query": {"vista": "editables"}, "tono": "alerta" if pls_abiertos else "normal"},
    ]
    if interno:
        kpis.append({"clave": "listas", "titulo": "Invoices ready to ship", "valor": len(listas),
                     "detalle": f"{len(sin_unidad)} PLs without container", "ruta": "/facturas",
                     "query": {"vista": "lista_transporte"}, "tono": "alerta" if sin_unidad else "normal"})
    proximo = transito["proxima"]
    kpis.append({"clave": "en_camino", "titulo": "Shipments in transit", "valor": transito["n"],
                 "formato": "numero", "detalle": f"next arrival {proximo:%b %d}" if proximo else "no upcoming arrivals",
                 "fecha": proximo, "ruta": "/transporte" if interno else "/seguimiento",
                 "query": {"estado": "EN_TRANSITO"} if interno else {"vista": "embarques", "estado": "EN_TRANSITO"},
                 "tono": "normal"})

    from app.modulos.seguimiento.seguimiento import filas_seguimiento

    seg = filas_seguimiento(db, user, prov)
    tarde = metricas.oc_llegada_tarde(seg)
    pendientes_lib = {f["oc_id"] for f in seg if f["etapa"] == "PEND_LIBERACION"}
    kpis.append({"clave": "riesgo", "titulo": "POs arriving late", "valor": len(tarde),
                 "detalle": "port arrival after the port deadline", "ruta": "/seguimiento",
                 "query": {"riesgo": "ATRASO"}, "tono": "alerta" if tarde else "exito"})
    franja = {k["clave"] for k in _visibles(kpis)}
    # Lo que ya está en la franja no se repite en «Necesita su atención»
    franja_atencion = {"riesgo"} & franja | ({"sin_contenedor"} if "listas" in franja else set())
    atencion = _atencion(db, user, prov, seg, tarde, sin_unidad, franja_atencion)
    tareas = _tareas(db, user, facturas, distribucion, prov)
    if pendientes_lib:
        tareas.insert(0, {"prioridad": 1, "tipo": "liberacion",
                          "titulo": f"{len(pendientes_lib)} POs not released",
                          "detalle": "Commercial or logistics release pending: they cannot be invoiced.",
                          "ruta": "/ordenes?liberada=0&solo_disponible=0", "accion": "View"})
    fact = metricas.facturado(db, user, prov, desde, hasta, filtro_marcas)
    moneda_fact = metricas.moneda_principal(fact["por_moneda"]) if fact["por_moneda"] else moneda
    return {
        "rol": user.rol,
        "moneda": moneda,
        "kpis": _visibles(kpis),
        "atencion": _visibles(atencion),
        "tareas": tareas[:12],
        "tareas_total": len(tareas),
        "flujo": _flujo(db, facturas, saldo),
        "periodo": {"desde": desde, "hasta": hasta,
                    "resumen": _visibles(_resumen_periodo(db, user, prov, fact, moneda_fact, desde, hasta)),
                    "facturado": _serie_facturado(fact, moneda_fact, desde, hasta),
                    "marcas": metricas.marcas_facturadas(db, user, prov, desde, hasta)},
        "envios": envios,
        "contenedores": _contenedores(db, user) if interno else [],
        "proveedores": _por_proveedor(db, facturas, distribucion, saldo) if interno and not prov else [],
        "alertas": listar_alertas(db, user, prov) if interno and tiene(user, "alertas.ver") else [],
    }
