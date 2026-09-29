"""Seguimiento de mercancía: dónde está cada SKU, desde la OC hasta la bodega.

Una fila por cantidad en una misma etapa: el saldo de la OC por facturar, lo
facturado sin packing list, lo que está en un PL y, si ya tiene contenedor,
en qué embarque va. Con la fecha requerida en tienda se calcula la holgura
(días entre la llegada y la fecha en tienda) para ver a tiempo lo que se atrasa.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Factura, FacturaLinea, OrdenCompra, PLLinea, PosicionOC, Usuario
from .cantidades import facturado_por_posicion, nombre_factura
from .common import proveedor_filtro

ETAPAS = [
    ("PEND_LIBERACION", "Pendiente de liberación"),
    ("POR_FACTURAR", "Por facturar"),
    ("FACTURADO", "Facturado sin packing list"),
    ("EN_PL", "En packing list"),
    ("CONTENEDOR", "Asignado a contenedor"),
    ("EN_TRANSITO", "En tránsito"),
    ("ARRIBADO", "Arribado"),
    ("ENTREGADO", "Entregado"),
    ("RECIBIDO", "Recibido"),
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
        "proveedor": oc.proveedor.nombre, "documento": None,
        "unidad": p.unidad, "tipo_empaque": p.tipo_empaque, "centro_destino": oc.centro_destino,
        "fecha_xf": oc.fecha_xf, "fecha_tienda": oc.fecha_tienda,
        "dias_tienda": (oc.fecha_tienda - hoy).days if oc.fecha_tienda else None,
        "factura_id": None, "factura": None, "pl_id": None, "pl": None, "contenedor": None,
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
                fila.update(contenedor=u.numero or u.etiqueta, embarque_id=e.id, embarque=e.codigo,
                            documento=e.documento_numero,
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
FILTROS_EXACTOS = ("marca", "estilo", "color", "talla", "almacen", "grupo", "sku", "contenedor", "documento",
                   "etapa", "riesgo", "embarque_id")
RANGOS = ("eta", "fecha_xf", "fecha_tienda")


def _valores(todas: list[dict], campo: str) -> list:
    return sorted({f[campo] for f in todas if f[campo]}, key=str)


def seguimiento(db: Session, user: Usuario, proveedor_id: int | None = None, filtros: dict | None = None,
                orden: str | None = None, page: int = 1, size: int = 25) -> dict:
    filtros = {k: v for k, v in (filtros or {}).items() if v not in (None, "")}
    todas = filas_seguimiento(db, user, proveedor_id)
    opciones = {
        "marcas": _valores(todas, "marca"),
        "estilos": _valores(todas, "estilo"),
        "colores": _valores(todas, "color"),
        "almacenes": _valores(todas, "almacen"),
        "grupos": _valores(todas, "grupo"),
        "skus": _valores(todas, "sku"),
        "contenedores": _valores(todas, "contenedor"),
        "documentos": _valores(todas, "documento"),
        "tallas": sorted({f["talla"] for f in todas if f["talla"]}, key=lambda t: (not t.isdigit(), t.zfill(4))),
        "embarques": sorted({(f["embarque_id"], f["embarque"]) for f in todas if f["embarque_id"]}),
    }
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

    # Resumen: cantidades por etapa y por marca, separadas por unidad de medida
    por_etapa = {k: {} for k, _ in ETAPAS}
    por_marca: dict[str, dict] = {}
    for f in filas:
        por_etapa[f["etapa"]][f["unidad"]] = por_etapa[f["etapa"]].get(f["unidad"], 0) + f["cantidad"]
        clave_m = (f["marca"] or "Sin marca", f["unidad"])
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
        "opciones": {**opciones, "embarques": [{"id": i, "codigo": c} for i, c in opciones["embarques"]]},
    }


# ---- Seguimiento de facturación y empaque ------------------------------------
# Una fila por packing list (o por factura que aún no tiene PL): en qué paso
# del documento va, qué le falta y si ya tiene contenedor.
ETAPAS_DOC = [
    ("FACTURA_ABIERTA", "Factura sin packing list"),
    ("EMPACANDO", "Empacando"),
    ("POR_FINALIZAR_PL", "Empacado, por finalizar"),
    ("POR_FINALIZAR_FACTURA", "PL listo, factura abierta"),
    ("LISTO_EMBARQUE", "Listo para embarcar"),
    ("TENTATIVO", "Tentativo en contenedor"),
    ("EN_CONTENEDOR", "Confirmado en contenedor"),
    ("EN_CAMINO", "En camino"),
    ("RECIBIDO", "Recibido"),
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
        "opciones": {**opciones, "embarques": [{"id": i, "codigo": c} for i, c in opciones["embarques"]]},
    }
