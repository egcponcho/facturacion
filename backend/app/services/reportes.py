"""Reportes de seguimiento en PDF y Excel, con los mismos filtros que el
tablero en pantalla: órdenes de compra (con el detalle por SKU), embarques
(con sus unidades de carga) y facturación/packing lists."""
from sqlalchemy.orm import Session

from ..models import Usuario
from . import documentos, exportar
from . import seguimiento as seg

TODO = 100_000
NOMBRES_FILTRO = {
    "q": "Búsqueda", "oc_id": "OC", "marca": "Marca", "grupo": "Grupo", "estilo": "Estilo", "color": "Color",
    "talla": "Talla", "sku": "SKU", "almacen": "Almacén", "contenedor": "Contenedor", "documento": "BL / AWB",
    "etapa": "Etapa", "riesgo": "Llegada a tienda", "embarque_id": "Embarque", "estado": "Estado",
    "modo": "Modo", "liberacion_comercial": "Lib. comercial", "liberacion_logistica": "Lib. logística",
    "proveedor": "Proveedor", "sociedad": "Sociedad", "centro": "Centro", "xf_vencida": "XF vencida",
    "eta_desde": "ETA desde", "eta_hasta": "ETA hasta", "fecha_xf_desde": "XF desde", "fecha_xf_hasta": "XF hasta",
    "fecha_tienda_desde": "En tienda desde", "fecha_tienda_hasta": "En tienda hasta", "estado_factura": "Factura",
    "estado_pl": "PL", "con_pendientes": "Con pendientes",
}
RIESGOS = {"ATRASO": "Llega tarde", "JUSTO": "Justo", "A_TIEMPO": "A tiempo"}
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
            v = v.strftime("%d/%m/%Y")
        partes.append(f"{NOMBRES_FILTRO.get(k, k)}: {'sí' if v is True else v}")
    return "Filtros: " + " · ".join(partes) if partes else "Sin filtros"


def _holgura(h) -> str:
    if h is None:
        return "—"
    return f"{-h} d tarde" if h < 0 else f"{h} d de margen"


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
    indicadores = [("Órdenes de compra", f"{k['ocs']:,}"), ("Liberadas", f"{k['liberadas']:,}"),
                   ("Sin liberar", f"{k['sin_liberar']:,}"), ("XF vencida sin facturar", f"{k['xf_vencida']:,}"),
                   ("Llegan tarde a tienda", f"{k['atraso']:,}")]
    columnas = [("OC", 1.3, False), ("Proveedor", 1.4, False), ("Soc. · centro", 1.1, False),
                ("Destino", 0.8, False), ("Lib. com.", 0.6, False), ("Lib. log.", 0.6, False),
                ("Estado", 1.6, False), ("Total", 0.8, True), ("Por facturar", 0.9, True), ("% fact.", 0.7, True),
                ("XF", 0.9, False), ("En tienda", 0.9, False), ("Vs. tienda", 1.1, False), ("Embarques", 1.4, False)]
    filas = [[o["oc"], o["proveedor"], f"{o['sociedad']} · {o['centro']}", o["centro_destino"] or "—",
              o["liberacion_comercial"] or "C", o["liberacion_logistica"], ESTADOS_OC[o["estado"]], o["total"],
              o["por_facturar"], o["avance"], _fecha(o["fecha_xf"]), _fecha(o["fecha_tienda"]), _holgura(o["holgura"]),
              ", ".join(o["embarques"]) or "—"] for o in r["items"]]
    hojas = None
    if formato == "xlsx":
        det = seg.seguimiento(db, user, proveedor_id, filtros, "oc:asc", 1, TODO)["items"]
        hojas = [{"titulo": "Detalle por SKU", "columnas": [
            ("OC", 1.3, False), ("Pos.", 0.5, False), ("SKU", 1.3, False), ("Marca", 0.8, False),
            ("Grupo", 0.8, False), ("Estilo", 1, False), ("Color", 1.2, False), ("Talla", 0.5, False),
            ("Almacén", 0.7, False), ("Cantidad", 0.8, True), ("UM", 0.5, False), ("Etapa", 1.6, False),
            ("Factura", 1.3, False), ("PL", 0.7, False), ("Contenedor / guía", 1.3, False), ("BL / AWB", 1.3, False),
            ("ETA", 0.9, False), ("En tienda", 0.9, False), ("Vs. tienda", 1.1, False)],
            "filas": [[f["oc"], f["posicion"], f["sku"], f["marca"], f["grupo"], f["estilo"], f["color"], f["talla"],
                       f["almacen"], f["cantidad"], f["unidad"], ETAPAS[f["etapa"]], f["factura"], f["pl"],
                       f["contenedor"], f["documento"], _fecha(f["arribo_real"] or f["eta"]),
                       _fecha(f["fecha_tienda"]), _holgura(f["holgura"])] for f in det]}]
    return _salida(formato, "Seguimiento de órdenes de compra",
                   "Liberaciones, avance de facturación y llegada frente a la fecha en tienda.",
                   filtros, indicadores, columnas, filas, hojas)


def reporte_embarques(db: Session, user: Usuario, proveedor_id, filtros: dict, orden, formato: str) -> bytes:
    r = seg.embarques(db, user, proveedor_id, filtros, orden, 1, TODO)
    k = r["kpis"]
    indicadores = [("Embarques", f"{k['embarques']:,}"), ("Unidades de carga", f"{k['unidades']:,}"),
                   ("En tránsito", f"{k['en_camino']:,}"), ("Llegan en 7 días", f"{k['llegan_7_dias']:,}"),
                   ("Llegan tarde a tienda", f"{k['atrasados']:,}")]
    columnas = [("Embarque", 1.1, False), ("BL / AWB / CP", 1.4, False), ("Modo", 0.8, False),
                ("Modalidad", 0.85, False), ("Transportista", 1.3, False), ("Ruta", 1.3, False),
                ("Estado", 0.9, False), ("Salida", 0.9, False), ("Llegada", 0.9, False), ("Vs. tienda", 1.1, False),
                ("Unidades", 0.7, True), ("OCs", 0.5, True), ("Contenido", 1.5, False)]
    filas = [[e["embarque"], e["documento"] or "Pendiente", seg.MODOS.get(e["modo"], e["modo"]), e["modalidad"] or "—",
              e["transportista"] or "—", f"{e['puerto_origen'] or '—'} → {e['puerto_destino'] or '—'}",
              ESTADOS_EMB.get(e["estado"], e["estado"]), _fecha(e["etd"]), _fecha(e["eta"]), _holgura(e["holgura"]),
              e["unidades"], e["ocs"], _cant(e["por_unidad"])] for e in r["items"]]
    hojas = None
    if formato == "xlsx":
        hojas = [{"titulo": "Unidades de carga", "columnas": [
            ("Embarque", 1.1, False), ("BL / AWB / CP", 1.4, False), ("Unidad", 1.3, False), ("Tipo", 1.3, False),
            ("Modalidad", 0.7, False), ("Sello", 1, False), ("OCs", 0.5, True), ("Marcas", 1, False),
            ("Facturas", 1.6, False), ("Vs. tienda", 1.1, False), ("Contenido", 1.5, False)],
            "filas": [[e["embarque"], e["documento"], u["contenedor"], u["tipo_nombre"], u["modalidad"], u["sello"],
                       u["ocs"], ", ".join(u["marcas"]), ", ".join(u["facturas"]), _holgura(u["holgura"]),
                       _cant(u["por_unidad"])] for e in r["items"] for u in e["detalle_unidades"]]}]
    return _salida(formato, "Seguimiento de embarques", "Documentos de transporte, unidades de carga y llegadas.",
                   filtros, indicadores, columnas, filas, hojas)


def reporte_documentos(db: Session, user: Usuario, proveedor_id, filtros: dict, orden, formato: str) -> bytes:
    r = seg.seguimiento_documentos(db, user, proveedor_id, filtros, orden, 1, TODO)
    k = r["kpis"]
    importe = " · ".join(f"{m} {v:,.2f}" for m, v in k["importe"].items()) or "—"
    indicadores = [("Facturas", f"{k['facturas']:,}"), ("Packing lists", f"{k['pls']:,}"),
                   ("Listos para embarcar", f"{k['listos']:,}"), ("Con pendientes", f"{k['con_pendientes']:,}"),
                   ("Importe", importe)]
    columnas = [("Factura", 1.3, False), ("Fecha", 0.8, False), ("Proveedor", 1.2, False), ("Centro", 0.6, False),
                ("OCs", 1.3, False), ("Estado factura", 1, False), ("PL", 0.6, False), ("Estado PL", 0.9, False),
                ("Etapa", 1.5, False), ("% empacado", 0.7, True), ("Cajas", 0.6, True), ("Peso bruto kg", 0.8, True),
                ("m³", 0.6, True), ("Contenedor", 1.1, False), ("Embarque", 0.9, False), ("ETA", 0.8, False),
                ("Importe", 1, True)]
    filas = [[f["factura"], _fecha(f["fecha"]), f["proveedor"], f["centro"], ", ".join(f["ocs"]), f["estado_factura"],
              f["pl"] or "—", f["estado_pl"] or "—", ETAPAS_DOC[f["etapa"]], f["avance"], f["cajas"],
              f["peso_bruto"], f["cbm"], f["contenedor"] or "—", f["embarque"] or "—", _fecha(f["eta"]),
              f["importe"]] for f in r["items"]]
    return _salida(formato, "Seguimiento de facturación y packing lists",
                   "En qué paso va cada factura y packing list, qué le falta y si ya tiene contenedor.",
                   filtros, indicadores, columnas, filas)


REPORTES = {"ordenes": reporte_ordenes, "embarques": reporte_embarques, "documentos": reporte_documentos}
