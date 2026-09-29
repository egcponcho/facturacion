"""Seguimiento de mercancía: dónde está cada SKU, desde la OC hasta la bodega.

Una fila por cantidad en una misma etapa: el saldo de la OC por facturar, lo
facturado sin packing list, lo que está en un PL y, si ya tiene contenedor,
en qué embarque va. Con la fecha requerida en tienda se calcula la holgura
(días entre la llegada y la fecha en tienda) para ver a tiempo lo que se atrasa.
"""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Embarque, Factura, FacturaLinea, OrdenCompra, PLLinea, PosicionOC, Usuario
from .cantidades import facturado_por_posicion, nombre_factura
from .common import proveedor_filtro

ETAPAS = [
    ("PEND_LIBERACION", "Pending release"),
    ("POR_FACTURAR", "To invoice"),
    ("FACTURADO", "Invoiced, no packing list"),
    ("EN_PL", "In packing list"),
    ("CONTENEDOR", "Assigned to container"),
    ("EN_TRANSITO", "In transit"),
    ("ARRIBADO", "Arrived"),
    ("ENTREGADO", "Delivered"),
    ("RECIBIDO", "Received"),
]
ORDEN = {"almacen", "grupo", "documento", "marca", "estilo", "color", "talla", "oc", "cantidad", "etapa", "fecha_xf", "fecha_tienda", "eta",
         "holgura", "embarque", "contenedor", "recolectado_en", "proveedor"}


def _riesgo(holgura: int | None) -> str | None:
    if holgura is None:
        return None
    if holgura < 0:
        return "ATRASO"
    if holgura < 7:
        return "JUSTO"
    return "A_TIEMPO"


def _base(p: PosicionOC, oc: OrdenCompra, hoy: date) -> dict:
    return {
        "marca": p.marca, "estilo": p.estilo, "color": p.color, "talla": p.talla, "sku": p.codigo_sap,
        "oc_id": oc.id, "oc": oc.numero, "posicion": p.posicion, "almacen": p.almacen, "grupo": p.grupo,
        "proveedor": oc.proveedor.nombre, "documento": None, "sociedad": oc.sociedad, "centro": oc.centro,
        "liberacion_comercial": oc.liberacion_comercial, "liberacion_logistica": oc.liberacion_logistica,
        "transportista": None, "puerto_origen": None, "puerto_destino": None,
        "unidad": p.unidad, "tipo_empaque": p.tipo_empaque, "centro_destino": oc.centro_destino,
        "fecha_xf": oc.fecha_xf, "fecha_tienda": oc.fecha_tienda,
        "dias_tienda": (oc.fecha_tienda - hoy).days if oc.fecha_tienda else None,
        "factura_id": None, "factura": None, "pl_id": None, "pl": None, "contenedor": None, "unidad_id": None, "modo": None,
        "embarque_id": None, "embarque": None, "estado_embarque": None, "asignacion": None,
        "etd": None, "eta": None, "salida_real": None, "arribo_real": None, "recolectado_en": None,
        "atraso_recoleccion": None, "holgura": None, "riesgo": None,
    }


def filas_seguimiento(db: Session, user: Usuario, proveedor_id: int | None = None) -> list[dict]:
    prov = proveedor_filtro(user, proveedor_id)
    hoy = date.today()
    consulta = select(PosicionOC).join(OrdenCompra)
    if prov:
        consulta = consulta.where(OrdenCompra.proveedor_id == prov)
    posiciones = list(db.scalars(consulta).all())
    facturado = facturado_por_posicion(db, [p.id for p in posiciones])
    filas = []
    for p in posiciones:
        saldo = p.cantidad - facturado.get(p.id, 0)
        if saldo > 0:
            filas.append({**_base(p, p.oc, hoy), "cantidad": saldo,
                          "etapa": "POR_FACTURAR" if p.oc.liberada else "PEND_LIBERACION"})

    consulta = select(FacturaLinea).join(Factura).where(Factura.estado != "CANCELADA")
    if prov:
        consulta = consulta.where(Factura.proveedor_id == prov)
    for fl in db.scalars(consulta).all():
        p = fl.posicion_oc
        oc = p.oc
        f = fl.factura
        en_pl = 0
        for pll in db.scalars(select(PLLinea).where(PLLinea.factura_linea_id == fl.id)).all():
            pl = pll.pl
            if pl.estado == "CANCELADO":
                continue
            en_pl += pll.cantidad
            fila = {**_base(p, oc, hoy), "cantidad": pll.cantidad, "factura_id": f.id,
                    "factura": nombre_factura(f), "pl_id": pl.id, "pl": pl.numero, "etapa": "EN_PL",
                    "recolectado_en": pl.recolectado_en}
            if pl.recolectado_en and oc.fecha_xf:
                fila["atraso_recoleccion"] = (pl.recolectado_en - oc.fecha_xf).days
            u = pl.unidad
            if u:
                e = u.embarque
                fila.update(contenedor=u.numero or u.etiqueta, unidad_id=u.id, modo=e.tipo_transporte,
                            embarque_id=e.id, embarque=e.codigo,
                            documento=e.documento_numero, transportista=e.transportista,
                            puerto_origen=e.puerto_origen, puerto_destino=e.puerto_destino,
                            estado_embarque=e.estado, asignacion=pl.asignacion, etd=e.etd, eta=e.eta,
                            salida_real=e.salida_real, arribo_real=e.arribo_real,
                            etapa="CONTENEDOR" if e.estado == "PLANIFICADO" else e.estado)
                llegada = e.arribo_real or e.eta
                if oc.fecha_tienda and llegada:
                    fila["holgura"] = (oc.fecha_tienda - llegada).days
            elif oc.fecha_tienda:
                # Sin embarque aún: la holgura es lo que queda hasta la fecha en tienda
                fila["holgura"] = (oc.fecha_tienda - hoy).days
            fila["riesgo"] = _riesgo(fila["holgura"])
            filas.append(fila)
        resto = fl.cantidad - en_pl
        if resto > 0:
            fila = {**_base(p, oc, hoy), "cantidad": resto, "factura_id": f.id, "factura": nombre_factura(f),
                    "etapa": "FACTURADO"}
            if oc.fecha_tienda:
                fila["holgura"] = (oc.fecha_tienda - hoy).days
                fila["riesgo"] = _riesgo(fila["holgura"])
            filas.append(fila)
    return filas


# Filtros exactos de la vista (valor igual) y rangos de fechas (desde/hasta)
FILTROS_EXACTOS = ("oc_id", "marca", "estilo", "color", "talla", "almacen", "grupo", "sku", "contenedor", "documento",
                   "etapa", "riesgo", "embarque_id", "proveedor", "sociedad", "centro", "liberacion_comercial",
                   "liberacion_logistica")
RANGOS = ("eta", "fecha_xf", "fecha_tienda")


def _valores(todas: list[dict], campo: str) -> list:
    return sorted({f[campo] for f in todas if f[campo]}, key=str)


def _opciones(todas: list[dict]) -> dict:
    embarques = sorted({(f["embarque_id"], f["embarque"]) for f in todas if f["embarque_id"]})
    return {
        "marcas": _valores(todas, "marca"),
        "estilos": _valores(todas, "estilo"),
        "colores": _valores(todas, "color"),
        "almacenes": _valores(todas, "almacen"),
        "grupos": _valores(todas, "grupo"),
        "skus": _valores(todas, "sku"),
        "contenedores": _valores(todas, "contenedor"),
        "documentos": _valores(todas, "documento"),
        "proveedores": _valores(todas, "proveedor"),
        "sociedades": _valores(todas, "sociedad"),
        "centros": _valores(todas, "centro"),
        "tallas": sorted({f["talla"] for f in todas if f["talla"]}, key=lambda t: (not t.isdigit(), t.zfill(4))),
        "embarques": [{"id": i, "codigo": c} for i, c in embarques],
    }


def _filtrar(todas: list[dict], filtros: dict) -> list[dict]:
    """Los mismos filtros para los tres tableros de mercancía, contenedores y OCs."""
    filas = todas
    for campo in FILTROS_EXACTOS:
        if campo in filtros:
            valor = filtros[campo]
            filas = [f for f in filas if str(f[campo]) == str(valor)]
    for campo in RANGOS:
        desde, hasta = filtros.get(f"{campo}_desde"), filtros.get(f"{campo}_hasta")
        if desde:
            filas = [f for f in filas if f[campo] and f[campo] >= desde]
        if hasta:
            filas = [f for f in filas if f[campo] and f[campo] <= hasta]
    if filtros.get("q"):
        t = filtros["q"].strip().lower()
        filas = [f for f in filas if any(t in str(f[k] or "").lower()
                                         for k in ("sku", "oc", "factura", "contenedor", "embarque", "estilo", "pl",
                                                   "documento", "color"))]
    return filas


def seguimiento(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
                orden: str | None = None, page: int = 1, size: int = 25) -> dict:
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    todas = filas_seguimiento(db, user, proveedor_id)
    opciones = _opciones(todas)
    filas = _filtrar(todas, filtros)

    # Resumen: cantidades por etapa y por marca, separadas por unidad de medida
    por_etapa = {k: {} for k, _ in ETAPAS}
    por_marca: dict[str, dict] = {}
    for f in filas:
        por_etapa[f["etapa"]][f["unidad"]] = por_etapa[f["etapa"]].get(f["unidad"], 0) + f["cantidad"]
        clave_m = (f["marca"] or "No brand", f["unidad"])
        m = por_marca.setdefault(clave_m, {"marca": clave_m[0], "unidad": f["unidad"], "atraso": 0, "total": 0,
                                           "etapas": {}})
        m["total"] += f["cantidad"]
        m["etapas"][f["etapa"]] = m["etapas"].get(f["etapa"], 0) + f["cantidad"]
        m["atraso"] += f["riesgo"] == "ATRASO"

    col, _, direccion = (orden or "").partition(":")
    if col in ORDEN:
        indice = {k: i for i, (k, _) in enumerate(ETAPAS)}
        clave = (lambda f: indice[f["etapa"]]) if col == "etapa" else (lambda f: (f[col] is None, f[col] or 0))
        filas = sorted(filas, key=clave, reverse=direccion == "desc")
    total = len(filas)
    return {
        "items": filas[(page - 1) * size: page * size],
        "total": total,
        "page": page,
        "size": size,
        "etapas": [{"clave": k, "nombre": n, "por_unidad": por_etapa[k]} for k, n in ETAPAS],
        "por_marca": sorted(por_marca.values(), key=lambda m: (m["marca"], m["unidad"])),
        "opciones": opciones,
    }


def _por_unidad(filas: list[dict]) -> dict:
    r: dict[str, int] = {}
    for f in filas:
        r[f["unidad"]] = r.get(f["unidad"], 0) + f["cantidad"]
    return r


def _peor_riesgo(filas: list[dict]) -> str | None:
    for r in ("ATRASO", "JUSTO", "A_TIEMPO"):
        if any(f["riesgo"] == r for f in filas):
            return r
    return None


def _ordenar(items: list[dict], orden: str | None, permitidos: set) -> list[dict]:
    col, _, direccion = (orden or "").partition(":")
    if col not in permitidos:
        return items
    return sorted(items, key=lambda x: (x[col] is None, x[col] if x[col] is not None else 0),
                  reverse=direccion == "desc")


# ---- Tablero de embarques ------------------------------------------------------
# Un renglón por embarque (su BL/AWB/carta de porte), que se abre en sus
# unidades de carga (contenedores, guías aéreas o camiones) y cada unidad en
# lo que lleva por orden de compra.
ESTADOS_EMB = [("PLANIFICADO", "Planned"), ("EN_TRANSITO", "In transit"), ("ARRIBADO", "Arrived"),
               ("ENTREGADO", "Delivered"), ("RECIBIDO", "Received")]
ORDEN_EMB = {"embarque", "documento", "estado", "etd", "eta", "holgura", "ocs", "unidades", "modo"}
MODOS = {"MARITIMO": "Ocean", "AEREO": "Air", "TERRESTRE": "Road"}


def embarques(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
              orden: str | None = None, page: int = 1, size: int = 25) -> dict:
    from .transporte import _tipo, modalidad_embarque

    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    todas = filas_seguimiento(db, user, proveedor_id)
    filas = [f for f in _filtrar(todas, filtros) if f["embarque_id"]]
    if filtros.get("estado"):
        filas = [f for f in filas if f["estado_embarque"] == filtros["estado"]]
    if filtros.get("modo"):
        filas = [f for f in filas if f["modo"] == filtros["modo"]]
    por_emb: dict[int, list] = {}
    for f in filas:
        por_emb.setdefault(f["embarque_id"], []).append(f)
    hoy = date.today()
    items = []
    for emb_id, fs in por_emb.items():
        e = db.get(Embarque, emb_id)
        llegada = e.arribo_real or e.eta
        holguras = [f["holgura"] for f in fs if f["holgura"] is not None]
        unidades = []
        for u in sorted(e.unidades, key=lambda x: x.id):
            nombre = u.numero or u.etiqueta
            uf = [f for f in fs if f["unidad_id"] == u.id]
            if not uf:
                continue
            t = _tipo(db, u.tipo)
            uh = [f["holgura"] for f in uf if f["holgura"] is not None]
            unidades.append({
                "unidad_id": u.id, "contenedor": nombre, "tipo": u.tipo, "tipo_nombre": t.nombre if t else u.tipo,
                "modalidad": t.modalidad if t else None, "sello": u.sello, "ocs": len({f["oc"] for f in uf}),
                "marcas": sorted({f["marca"] for f in uf if f["marca"]}), "por_unidad": _por_unidad(uf),
                "holgura": min(uh) if uh else None, "riesgo": _peor_riesgo(uf),
                "facturas": sorted({f["factura"] for f in uf if f["factura"]}),
            })
        items.append({
            "embarque_id": e.id, "embarque": e.codigo, "documento": e.documento_numero, "estado": e.estado,
            "modo": e.tipo_transporte, "modalidad": modalidad_embarque(e), "transportista": e.transportista,
            "puerto_origen": e.puerto_origen, "puerto_destino": e.puerto_destino, "centro": e.centro,
            "etd": e.salida_real or e.etd, "eta": llegada, "arribado": bool(e.arribo_real),
            "dias_eta": (llegada - hoy).days if llegada else None,
            "holgura": min(holguras) if holguras else None, "riesgo": _peor_riesgo(fs),
            "marcas": sorted({f["marca"] for f in fs if f["marca"]}), "ocs": len({f["oc"] for f in fs}),
            "proveedores": sorted({f["proveedor"] for f in fs}), "unidades": len(unidades),
            "detalle_unidades": unidades, "por_unidad": _por_unidad(fs),
        })
    por_estado = {k: 0 for k, _ in ESTADOS_EMB}
    for it in items:
        por_estado[it["estado"]] = por_estado.get(it["estado"], 0) + 1
    semanas = []
    for n in range(8):
        ini = hoy + timedelta(days=7 * n)
        fin = ini + timedelta(days=6)
        semanas.append({"desde": ini, "hasta": fin, "embarques": sum(
            1 for it in items if it["eta"] and not it["arribado"] and ini <= it["eta"] <= fin)})
    kpis = {
        "embarques": len(items),
        "unidades": sum(it["unidades"] for it in items),
        "en_camino": sum(1 for it in items if it["estado"] == "EN_TRANSITO"),
        "llegan_7_dias": sum(1 for it in items if not it["arribado"] and it["dias_eta"] is not None
                             and 0 <= it["dias_eta"] <= 7),
        "atrasados": sum(1 for it in items if it["riesgo"] == "ATRASO"),
        "por_modo": {m: sum(1 for it in items if it["modo"] == m) for m in MODOS},
        "por_unidad": _por_unidad(filas),
    }
    items = _ordenar(sorted(items, key=lambda x: (x["eta"] is None, x["eta"] or hoy)), orden, ORDEN_EMB)
    return {
        "items": items[(page - 1) * size: page * size], "total": len(items), "page": page, "size": size,
        "kpis": kpis, "por_estado": [{"clave": k, "nombre": n, "total": por_estado[k]} for k, n in ESTADOS_EMB],
        "llegadas": semanas, "opciones": _opciones(todas),
    }


def explosion_unidad(db: Session, user: Usuario, unidad_id: int, proveedor_id: int | None = None,
                     filtros: dict | None = None) -> dict:
    """Todo lo que viaja en una unidad de carga, agrupado por orden de compra."""
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    filas = [f for f in _filtrar(filas_seguimiento(db, user, proveedor_id), filtros) if f["unidad_id"] == unidad_id]
    ocs: dict[int, dict] = {}
    for f in filas:
        o = ocs.setdefault(f["oc_id"], {
            "oc_id": f["oc_id"], "oc": f["oc"], "proveedor": f["proveedor"], "sociedad": f["sociedad"],
            "centro": f["centro"], "centro_destino": f["centro_destino"], "fecha_tienda": f["fecha_tienda"],
            "fecha_xf": f["fecha_xf"], "lineas": []})
        o["lineas"].append({k: f[k] for k in ("posicion", "sku", "marca", "grupo", "estilo", "color", "talla",
                                              "almacen", "cantidad", "unidad", "tipo_empaque", "factura",
                                              "factura_id", "pl", "pl_id", "holgura", "riesgo")})
    res = []
    for o in ocs.values():
        o["lineas"].sort(key=lambda x: str(x["posicion"]).zfill(6))
        o["por_unidad"] = _por_unidad(o["lineas"])
        holguras = [x["holgura"] for x in o["lineas"] if x["holgura"] is not None]
        o["holgura"] = min(holguras) if holguras else None
        o["riesgo"] = _peor_riesgo(o["lineas"])
        res.append(o)
    return {"unidad_id": unidad_id, "ocs": sorted(res, key=lambda x: x["oc"]), "por_unidad": _por_unidad(filas)}


# ---- Tablero de órdenes de compra -------------------------------------------
ESTADOS_OC = [
    ("SIN_COMERCIAL", "No commercial release (P)"),
    ("SIN_LOGISTICA", "No logistics release (304)"),
    ("POR_FACTURAR", "Released, not invoiced"),
    ("PARCIAL", "Partly invoiced"),
    ("FACTURADA", "Invoiced, in progress"),
    ("EN_CAMINO", "On the way"),
    ("RECIBIDA", "Received"),
]
GRUPO_ETAPA = {"PEND_LIBERACION": "por_facturar", "POR_FACTURAR": "por_facturar", "FACTURADO": "facturado",
               "EN_PL": "facturado", "CONTENEDOR": "en_contenedor", "EN_TRANSITO": "en_camino",
               "ARRIBADO": "en_camino", "ENTREGADO": "en_camino", "RECIBIDO": "recibido"}
ORDEN_OCS = {"oc", "proveedor", "estado", "fecha_xf", "fecha_tienda", "avance", "total", "por_facturar",
             "holgura", "centro"}


def _estado_oc(o: dict) -> str:
    if o["liberacion_comercial"] != "C":
        return "SIN_COMERCIAL"
    if o["liberacion_logistica"] not in ("300", "301"):
        return "SIN_LOGISTICA"
    c = o["cantidades"]
    if c["recibido"] == o["total"]:
        return "RECIBIDA"
    if c["por_facturar"] == o["total"]:
        return "POR_FACTURAR"
    if c["por_facturar"] > 0:
        return "PARCIAL"
    if c["en_camino"] + c["recibido"] == o["total"]:
        return "EN_CAMINO"
    return "FACTURADA"


def ordenes(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
            orden: str | None = None, page: int = 1, size: int = 25) -> dict:
    """Seguimiento de las OCs: liberaciones, cuánto está por facturar, en
    contenedor, en camino y recibido, con la holgura a la fecha en tienda."""
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    todas = filas_seguimiento(db, user, proveedor_id)
    filas = _filtrar(todas, filtros)
    hoy = date.today()
    por_oc: dict[int, dict] = {}
    for f in filas:
        o = por_oc.setdefault(f["oc_id"], {
            "oc_id": f["oc_id"], "oc": f["oc"], "proveedor": f["proveedor"], "sociedad": f["sociedad"],
            "centro": f["centro"], "centro_destino": f["centro_destino"],
            "liberacion_comercial": f["liberacion_comercial"], "liberacion_logistica": f["liberacion_logistica"],
            "fecha_xf": f["fecha_xf"], "fecha_tienda": f["fecha_tienda"], "dias_tienda": f["dias_tienda"],
            "marcas": set(), "unidades": set(), "embarques": set(), "total": 0, "holguras": [],
            "cantidades": {"por_facturar": 0, "facturado": 0, "en_contenedor": 0, "en_camino": 0, "recibido": 0}})
        o["total"] += f["cantidad"]
        o["cantidades"][GRUPO_ETAPA[f["etapa"]]] += f["cantidad"]
        if f["marca"]:
            o["marcas"].add(f["marca"])
        o["unidades"].add(f["unidad"])
        if f["embarque"]:
            o["embarques"].add(f["embarque"])
        if f["holgura"] is not None:
            o["holguras"].append(f["holgura"])
    items = []
    for o in por_oc.values():
        o["estado"] = _estado_oc(o)
        o["por_facturar"] = o["cantidades"]["por_facturar"]
        o["avance"] = round((o["total"] - o["por_facturar"]) * 100 / o["total"], 1) if o["total"] else 0
        o["holgura"] = min(o.pop("holguras")) if o["holguras"] else None
        o["riesgo"] = _riesgo(o["holgura"])
        o["xf_vencida"] = bool(o["fecha_xf"] and o["fecha_xf"] < hoy and o["por_facturar"] > 0)
        o["marcas"] = sorted(o["marcas"])
        o["unidades"] = sorted(o["unidades"])
        o["embarques"] = sorted(o["embarques"])
        items.append(o)
    for campo in ("estado", "liberacion_comercial", "liberacion_logistica", "sociedad", "centro", "proveedor"):
        if campo in filtros:
            items = [o for o in items if str(o[campo]) == str(filtros[campo])]
    if filtros.get("xf_vencida") in ("1", "true", True):
        items = [o for o in items if o["xf_vencida"]]
    resumen = {k: 0 for k, _ in ESTADOS_OC}
    for o in items:
        resumen[o["estado"]] += 1
    kpis = {
        "ocs": len(items),
        "liberadas": sum(1 for o in items if o["estado"] not in ("SIN_COMERCIAL", "SIN_LOGISTICA")),
        "sin_liberar": sum(1 for o in items if o["estado"] in ("SIN_COMERCIAL", "SIN_LOGISTICA")),
        "xf_vencida": sum(1 for o in items if o["xf_vencida"]),
        "atraso": sum(1 for o in items if o["riesgo"] == "ATRASO"),
        "avance": round(sum(o["total"] - o["por_facturar"] for o in items) * 100 / (sum(o["total"] for o in items) or 1), 1),
    }
    items = _ordenar(sorted(items, key=lambda x: x["oc"]), orden or "fecha_xf:asc", ORDEN_OCS)
    return {
        "items": items[(page - 1) * size: page * size], "total": len(items), "page": page, "size": size,
        "kpis": kpis, "estados": [{"clave": k, "nombre": n, "total": resumen[k]} for k, n in ESTADOS_OC],
        "opciones": _opciones(todas),
    }


# ---- Seguimiento de facturación y empaque ------------------------------------
# Una fila por packing list (o por factura que aún no tiene PL): en qué paso
# del documento va, qué le falta y si ya tiene contenedor.
ETAPAS_DOC = [
    ("FACTURA_ABIERTA", "Invoice without packing list"),
    ("EMPACANDO", "Packing"),
    ("POR_FINALIZAR_PL", "Packed, to finalize"),
    ("POR_FINALIZAR_FACTURA", "PL ready, invoice open"),
    ("LISTO_EMBARQUE", "Ready to ship"),
    ("TENTATIVO", "Tentative in container"),
    ("EN_CONTENEDOR", "Confirmed in container"),
    ("EN_CAMINO", "On the way"),
    ("RECIBIDO", "Received"),
]
ORDEN_DOC = {"factura", "fecha", "proveedor", "estado_factura", "estado_pl", "etapa", "avance", "cajas",
             "peso_bruto", "cbm", "embarque", "dias", "pendientes", "centro", "actualizado"}


def _etapa_doc(f, pl, avance: float) -> str:
    if pl is None:
        return "FACTURA_ABIERTA"
    if pl.unidad:
        e = pl.unidad.embarque
        if e.estado == "RECIBIDO":
            return "RECIBIDO"
        if e.estado != "PLANIFICADO":
            return "EN_CAMINO"
        return "EN_CONTENEDOR" if pl.asignacion == "CONFIRMADA" else "TENTATIVO"
    if pl.estado != "FINALIZADO":
        return "EMPACANDO" if avance < 100 else "POR_FINALIZAR_PL"
    return "LISTO_EMBARQUE" if f.estado == "FINALIZADA" else "POR_FINALIZAR_FACTURA"


def seguimiento_documentos(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
                           orden: str | None = None, page: int = 1, size: int = 25) -> dict:
    from .common import EDITABLE_PL
    from .facturas import validar_factura
    from .packing import validar_pl
    from .cantidades import totales_pl

    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    prov = proveedor_filtro(user, proveedor_id)
    consulta = select(Factura).where(Factura.estado != "CANCELADA").order_by(Factura.id)
    if prov:
        consulta = consulta.where(Factura.proveedor_id == prov)
    hoy = date.today()
    filas = []
    for f in db.scalars(consulta).all():
        ocs = sorted({l.oc_numero for l in f.lineas})
        importe = round(sum(l.cantidad * l.precio_unitario for l in f.lineas), 2)
        base = {
            "factura_id": f.id, "factura": nombre_factura(f), "fecha": f.fecha, "proveedor": f.proveedor.nombre,
            "sociedad": f.sociedad, "centro": f.centro, "centro_destino": f.centro_destino, "ocs": ocs,
            "estado_factura": f.estado, "importe": importe, "moneda": f.moneda,
            "dias": (hoy - f.creado_en.date()).days if f.creado_en else None,
            "pendientes_factura": len(validar_factura(db, f)) if f.estado in ("BORRADOR", "EN_CORRECCION") else 0,
        }
        pls = [pl for pl in f.packing_lists if pl.estado != "CANCELADO"]
        for pl in pls or [None]:
            fila = {**base, "pl_id": None, "pl": None, "estado_pl": None, "avance": 0, "cajas": 0, "pallets": 0,
                    "peso_bruto": 0, "cbm": 0, "pendientes": 0, "contenedor": None, "embarque_id": None,
                    "embarque": None, "estado_embarque": None, "asignacion": None, "recolectado_en": None,
                    "eta": None, "actualizado": f.actualizado_en}
            avance = 0.0
            if pl:
                t = totales_pl(pl)
                total = sum(u["cantidad"] for u in t["por_unidad"].values())
                avance = round(sum(u["en_cajas"] for u in t["por_unidad"].values()) * 100 / total, 1) if total else 0
                fila.update(pl_id=pl.id, pl=pl.numero, estado_pl=pl.estado, avance=avance, cajas=t["cajas"],
                            pallets=t["pallets"], peso_bruto=t["peso_bruto"], cbm=t["cbm"],
                            pendientes=len(validar_pl(pl)) if pl.estado in EDITABLE_PL else 0,
                            recolectado_en=pl.recolectado_en, asignacion=pl.asignacion,
                            actualizado=max(pl.actualizado_en, f.actualizado_en))
                if pl.unidad:
                    e = pl.unidad.embarque
                    fila.update(contenedor=pl.unidad.numero or pl.unidad.etiqueta, embarque_id=e.id,
                                embarque=e.codigo, estado_embarque=e.estado, eta=e.arribo_real or e.eta)
            fila["etapa"] = _etapa_doc(f, pl, avance)
            filas.append(fila)

    opciones = {
        "proveedores": _valores(filas, "proveedor"),
        "sociedades": _valores(filas, "sociedad"),
        "centros": _valores(filas, "centro"),
        "embarques": sorted({(f["embarque_id"], f["embarque"]) for f in filas if f["embarque_id"]}),
    }
    for campo in ("etapa", "estado_factura", "estado_pl", "sociedad", "centro", "embarque_id", "proveedor"):
        if campo in filtros:
            filas = [f for f in filas if str(f[campo]) == str(filtros[campo])]
    if filtros.get("con_pendientes") in ("1", "true", True):
        filas = [f for f in filas if f["pendientes"] or f["pendientes_factura"]]
    if filtros.get("q"):
        t = filtros["q"].strip().lower()
        filas = [f for f in filas if t in f["factura"].lower() or t in (f["pl"] or "").lower()
                 or any(t in oc for oc in f["ocs"]) or t in (f["contenedor"] or "").lower()]
    resumen = {k: 0 for k, _ in ETAPAS_DOC}
    for f in filas:
        resumen[f["etapa"]] += 1
    facturas = {f["factura_id"]: f for f in filas}.values()
    kpis = {
        "facturas": len(facturas),
        "facturas_abiertas": sum(1 for f in facturas if f["estado_factura"] in ("BORRADOR", "EN_CORRECCION")),
        "pls": sum(1 for f in filas if f["pl_id"]),
        "empacando": resumen["EMPACANDO"] + resumen["POR_FINALIZAR_PL"],
        "listos": resumen["LISTO_EMBARQUE"],
        "con_pendientes": sum(1 for f in filas if f["pendientes"] or f["pendientes_factura"]),
        "cajas": sum(f["cajas"] for f in filas), "pallets": sum(f["pallets"] for f in filas),
        "peso_bruto": round(sum(f["peso_bruto"] for f in filas), 1), "cbm": round(sum(f["cbm"] for f in filas), 2),
        "importe": {m: round(sum(f["importe"] for f in facturas if f["moneda"] == m), 2)
                    for m in {f["moneda"] for f in facturas}},
    }

    col, _, direccion = (orden or "").partition(":")
    if col in ORDEN_DOC:
        indice = {k: i for i, (k, _) in enumerate(ETAPAS_DOC)}
        clave = (lambda f: indice[f["etapa"]]) if col == "etapa" else (lambda f: (f[col] is None, f[col] or 0))
        filas = sorted(filas, key=clave, reverse=direccion == "desc")
    total = len(filas)
    return {
        "items": filas[(page - 1) * size: page * size],
        "total": total, "page": page, "size": size,
        "etapas": [{"clave": k, "nombre": n, "total": resumen[k]} for k, n in ETAPAS_DOC],
        "kpis": kpis,
        "opciones": {**opciones, "embarques": [{"id": i, "codigo": c} for i, c in opciones["embarques"]]},
    }
