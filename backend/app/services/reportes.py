"""Reportes de seguimiento en PDF y Excel, con los mismos filtros que el
tablero en pantalla: órdenes de compra (con el detalle por SKU), embarques
(con sus unidades de carga) y facturación/packing lists."""
from sqlalchemy.orm import Session

from ..models import Usuario
from . import documentos, exportar
from . import seguimiento as seg

TODO = 100_000
NOMBRES_FILTRO = {
    "q": "Search", "oc_id": "PO", "marca": "Brand", "grupo": "Group", "estilo": "Style", "color": "Color",
    "talla": "Size", "sku": "SKU", "almacen": "Storage loc.", "contenedor": "Container", "documento": "BL / AWB",
    "etapa": "Stage", "riesgo": "Store arrival", "embarque_id": "Shipment", "estado": "Status",
    "modo": "Mode", "liberacion_comercial": "Comm. release", "liberacion_logistica": "Log. release",
    "proveedor": "Supplier", "sociedad": "Company", "centro": "Plant", "xf_vencida": "XF overdue",
    "eta_desde": "ETA from", "eta_hasta": "ETA to", "fecha_xf_desde": "XF from", "fecha_xf_hasta": "XF to",
    "fecha_tienda_desde": "In store from", "fecha_tienda_hasta": "In store to", "estado_factura": "Invoice",
    "estado_pl": "PL", "con_pendientes": "With pending items",
}
RIESGOS = {"ATRASO": "Late", "JUSTO": "Tight", "A_TIEMPO": "On time"}
ETAPAS = dict(seg.ETAPAS)
ETAPAS_DOC = dict(seg.ETAPAS_DOC)
ESTADOS_OC = dict(seg.ESTADOS_OC)
ESTADOS_EMB = dict(seg.ESTADOS_EMB)


def _filtros_txt(filtros: dict) -> str:
    partes = []
    for k, v in filtros.items():
        if v in (None, "", False):
            continue
        if k == "riesgo":
            v = RIESGOS.get(v, v)
        elif k == "etapa":
            v = ETAPAS.get(v) or ETAPAS_DOC.get(v) or v
        elif k.endswith(("_desde", "_hasta")) and hasattr(v, "strftime"):
            v = v.strftime("%m/%d/%Y")
        partes.append(f"{NOMBRES_FILTRO.get(k, k)}: {'yes' if v is True else v}")
    return "Filters: " + " · ".join(partes) if partes else "No filters"


def _holgura(h) -> str:
    if h is None:
        return "—"
    return f"{-h} d late" if h < 0 else f"{h} d margin"


def _cant(por_unidad: dict) -> str:
    return documentos._por_unidad_txt(por_unidad)


def _salida(formato, titulo, subtitulo, filtros, indicadores, columnas, filas, hojas=None) -> bytes:
    texto = _filtros_txt(filtros)
    if formato == "pdf":
        return documentos.pdf_reporte(titulo, subtitulo, texto, indicadores, columnas,
                                      [[documentos._num(v, 0 if float(v).is_integer() else 2) if isinstance(v, (int, float)) else v for v in f]
                                       for f in filas])
    return exportar.exportar_reporte(titulo, subtitulo, texto, indicadores, columnas, filas, hojas)


def _fecha(v):
    return documentos._fecha(v) if v else "—"


def reporte_ordenes(db: Session, user: Usuario, proveedor_id, filtros: dict, orden, formato: str) -> bytes:
    r = seg.ordenes(db, user, proveedor_id, filtros, orden, 1, TODO)
    k = r["kpis"]
    indicadores = [("Purchase orders", f"{k['ocs']:,}"), ("Released", f"{k['liberadas']:,}"),
                   ("Not released", f"{k['sin_liberar']:,}"), ("XF overdue, not invoiced", f"{k['xf_vencida']:,}"),
                   ("Late to store", f"{k['atraso']:,}")]
    columnas = [("PO", 1.3, False), ("Supplier", 1.4, False), ("Co. · plant", 1.1, False),
                ("Destination", 0.8, False), ("Comm. rel.", 0.6, False), ("Log. rel.", 0.6, False),
                ("Status", 1.6, False), ("Total", 0.8, True), ("To invoice", 0.9, True), ("% inv.", 0.7, True),
                ("XF", 0.9, False), ("In store", 0.9, False), ("Vs. store", 1.1, False), ("Shipments", 1.4, False)]
    filas = [[o["oc"], o["proveedor"], f"{o['sociedad']} · {o['centro']}", o["centro_destino"] or "—",
              o["liberacion_comercial"] or "C", o["liberacion_logistica"], ESTADOS_OC[o["estado"]], o["total"],
              o["por_facturar"], o["avance"], _fecha(o["fecha_xf"]), _fecha(o["fecha_tienda"]), _holgura(o["holgura"]),
              ", ".join(o["embarques"]) or "—"] for o in r["items"]]
    hojas = None
    if formato == "xlsx":
        det = seg.seguimiento(db, user, proveedor_id, filtros, "oc:asc", 1, TODO)["items"]
        hojas = [{"titulo": "Detail by SKU", "columnas": [
            ("PO", 1.3, False), ("Line", 0.5, False), ("SKU", 1.3, False), ("Brand", 0.8, False),
            ("Group", 0.8, False), ("Style", 1, False), ("Color", 1.2, False), ("Size", 0.5, False),
            ("Storage loc.", 0.7, False), ("Quantity", 0.8, True), ("UoM", 0.5, False), ("Stage", 1.6, False),
            ("Invoice", 1.3, False), ("PL", 0.7, False), ("Container / AWB", 1.3, False), ("BL / AWB", 1.3, False),
            ("ETA", 0.9, False), ("In store", 0.9, False), ("Vs. store", 1.1, False)],
            "filas": [[f["oc"], f["posicion"], f["sku"], f["marca"], f["grupo"], f["estilo"], f["color"], f["talla"],
                       f["almacen"], f["cantidad"], f["unidad"], ETAPAS[f["etapa"]], f["factura"], f["pl"],
                       f["contenedor"], f["documento"], _fecha(f["arribo_real"] or f["eta"]),
                       _fecha(f["fecha_tienda"]), _holgura(f["holgura"])] for f in det]}]
    return _salida(formato, "Purchase order tracking",
                   "Releases, invoicing progress and arrival against the in-store date.",
                   filtros, indicadores, columnas, filas, hojas)


def reporte_embarques(db: Session, user: Usuario, proveedor_id, filtros: dict, orden, formato: str) -> bytes:
    r = seg.embarques(db, user, proveedor_id, filtros, orden, 1, TODO)
    k = r["kpis"]
    indicadores = [("Shipments", f"{k['embarques']:,}"), ("Load units", f"{k['unidades']:,}"),
                   ("In transit", f"{k['en_camino']:,}"), ("Arriving in 7 days", f"{k['llegan_7_dias']:,}"),
                   ("Late to store", f"{k['atrasados']:,}")]
    columnas = [("Shipment", 1.1, False), ("BL / AWB / waybill", 1.4, False), ("Mode", 0.8, False),
                ("Service", 0.85, False), ("Carrier", 1.3, False), ("Route", 1.3, False),
                ("Status", 0.9, False), ("Departure", 0.9, False), ("Arrival", 0.9, False), ("Vs. store", 1.1, False),
                ("Units", 0.7, True), ("POs", 0.5, True), ("Contents", 1.5, False)]
    filas = [[e["embarque"], e["documento"] or "Pending", seg.MODOS.get(e["modo"], e["modo"]), e["modalidad"] or "—",
              e["transportista"] or "—", f"{e['puerto_origen'] or '—'} → {e['puerto_destino'] or '—'}",
              ESTADOS_EMB.get(e["estado"], e["estado"]), _fecha(e["etd"]), _fecha(e["eta"]), _holgura(e["holgura"]),
              e["unidades"], e["ocs"], _cant(e["por_unidad"])] for e in r["items"]]
    hojas = None
    if formato == "xlsx":
        hojas = [{"titulo": "Load units", "columnas": [
            ("Shipment", 1.1, False), ("BL / AWB / waybill", 1.4, False), ("Unit", 1.3, False), ("Type", 1.3, False),
            ("Service", 0.7, False), ("Seal", 1, False), ("POs", 0.5, True), ("Brands", 1, False),
            ("Invoices", 1.6, False), ("Vs. store", 1.1, False), ("Contents", 1.5, False)],
            "filas": [[e["embarque"], e["documento"], u["contenedor"], u["tipo_nombre"], u["modalidad"], u["sello"],
                       u["ocs"], ", ".join(u["marcas"]), ", ".join(u["facturas"]), _holgura(u["holgura"]),
                       _cant(u["por_unidad"])] for e in r["items"] for u in e["detalle_unidades"]]}]
    return _salida(formato, "Shipment tracking", "Transport documents, load units and arrivals.",
                   filtros, indicadores, columnas, filas, hojas)


def reporte_documentos(db: Session, user: Usuario, proveedor_id, filtros: dict, orden, formato: str) -> bytes:
    r = seg.seguimiento_documentos(db, user, proveedor_id, filtros, orden, 1, TODO)
    k = r["kpis"]
    importe = " · ".join(f"{m} {v:,.2f}" for m, v in k["importe"].items()) or "—"
    indicadores = [("Invoices", f"{k['facturas']:,}"), ("Packing lists", f"{k['pls']:,}"),
                   ("Ready to ship", f"{k['listos']:,}"), ("With pending items", f"{k['con_pendientes']:,}"),
                   ("Amount", importe)]
    columnas = [("Invoice", 1.3, False), ("Date", 0.8, False), ("Supplier", 1.2, False), ("Plant", 0.6, False),
                ("POs", 1.3, False), ("Invoice status", 1, False), ("PL", 0.6, False), ("PL status", 0.9, False),
                ("Stage", 1.5, False), ("% packed", 0.7, True), ("Cartons", 0.6, True), ("Gross weight kg", 0.8, True),
                ("m³", 0.6, True), ("Container", 1.1, False), ("Shipment", 0.9, False), ("ETA", 0.8, False),
                ("Amount", 1, True)]
    filas = [[f["factura"], _fecha(f["fecha"]), f["proveedor"], f["centro"], ", ".join(f["ocs"]), f["estado_factura"],
              f["pl"] or "—", f["estado_pl"] or "—", ETAPAS_DOC[f["etapa"]], f["avance"], f["cajas"],
              f["peso_bruto"], f["cbm"], f["contenedor"] or "—", f["embarque"] or "—", _fecha(f["eta"]),
              f["importe"]] for f in r["items"]]
    return _salida(formato, "Invoicing and packing list tracking",
                   "Which step each invoice and packing list is at, what is missing and whether it has a container.",
                   filtros, indicadores, columnas, filas)


REPORTES = {"ordenes": reporte_ordenes, "embarques": reporte_embarques, "documentos": reporte_documentos}
