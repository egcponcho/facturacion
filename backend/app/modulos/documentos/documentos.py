"""Documentos de comercio exterior en PDF: factura comercial, packing list y
reportes. Los mismos datos alimentan la versión en Excel (exportar.py).

La factura comercial y la lista de empaque llevan lo que piden las aduanas de
Centroamérica (CAUCA/RECAUCA y la DUCA): datos del exportador, importador y
consignatario con su identificación fiscal; países de origen, procedencia y
destino; incoterm, moneda y condiciones de pago; medio de transporte, puertos
y documento de transporte; descripción comercial, partida arancelaria (SAC),
cantidad, unidad, precio unitario y total; bultos, marcas y pesos bruto y
neto; total en letras y la declaración firmada.
"""
import io
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import Pais, Proveedor, Puerto
from app.modulos.acceso.preferencias import fecha_hora_txt, fecha_txt
from app.modulos.documentos.idioma_doc import L
from app.modulos.documentos.partes import partes
from app.modulos.facturacion.cantidades import cbm_caja, cubierto, inner_de, nombre_factura, numeracion, totales_pl
from app.modulos.productos.productos import sin_marca

TINTA = colors.HexColor("#1f2430")
TENUE = colors.HexColor("#5b6475")
ACENTO_FABRICA = "#5b3fd1"


def _propios(entidad: str, extra: dict | None) -> list[tuple[str, str]]:
    """Campos propios con valor, como (etiqueta, texto) para los documentos."""
    from app.core.campos_propios import definiciones

    res = []
    for c in definiciones(entidad):
        v = (extra or {}).get(c["clave"])
        if v in (None, ""):
            continue
        res.append((c["etiqueta"], (L("Yes") if v else L("No")) if c["tipo"] == "bool"
                    else _fecha(date.fromisoformat(v)) if c["tipo"] == "fecha" else _num(v, 2) if c["tipo"] == "numero" else str(v)))
    return res


def _empresa(seccion: str) -> dict:
    """Marca o documentos de la empresa (Configuración → Empresa)."""
    from app.core.empresa import configuracion_actual
    from app.modulos.empresa.organizacion import DOCUMENTOS, MARCA

    base = {"marca": MARCA, "documentos": DOCUMENTOS}[seccion]
    return {**base, **(configuracion_actual().get(seccion) or {})}


def _acento_hex() -> str:
    return _empresa("marca")["color"] or ACENTO_FABRICA


def _acento():
    return colors.HexColor(_acento_hex())


def _papel():
    """Tamaño del papel de los PDF: carta o A4."""
    return A4 if _empresa("documentos")["papel"] == "A4" else letter


def declaracion(clave: str, fabrica: str) -> str:
    """Declaración legal del documento: la de la empresa o la de fábrica (traducida)."""
    return _empresa("documentos")[clave] or fabrica


def _declaracion(clave: str, fabrica: str) -> str:
    """La declaración para el PDF (la propia, escapada y con sus saltos de línea)."""
    propia = _empresa("documentos")[clave]
    return _esc(propia).replace(chr(10), "<br/>") if propia else fabrica
LINEA = colors.HexColor("#d9dce3")
FONDO = colors.HexColor("#f3f1fb")
FONDO_2 = colors.HexColor("#f7f8fa")

from app.core import listas

# Montos y números en letras: modulos/documentos/letras.py (reglas de cada idioma)
from app.modulos.documentos.letras import (
    cantidad_en_letras,
    monto_en_letras,  # noqa: E402
)
from app.modulos.maestros.unidades import texto as unidad_txt


# ---- Datos comunes -------------------------------------------------------------
def _pais(db: Session, codigo: str | None) -> str | None:
    if not codigo:
        return None
    p = db.scalar(select(Pais).where(Pais.codigo == codigo))
    return f"{p.nombre} ({codigo})" if p else codigo


def _puerto(db: Session, codigo: str | None) -> str | None:
    if not codigo:
        return None
    p = db.scalar(select(Puerto).where(Puerto.codigo == codigo))
    return f"{p.nombre} ({codigo})" if p else codigo


def _exportador(db: Session, prov: Proveedor) -> dict:
    return {"codigo": prov.codigo, "nombre": prov.razon_social or prov.nombre, "comercial": prov.nombre,
            "id_fiscal": prov.id_fiscal, "direccion": prov.direccion, "pais": _pais(db, prov.pais),
            "contacto": prov.contacto, "correos": prov.correos, "telefono": prov.telefono}


def _transporte(db: Session, pls: list) -> dict:
    """Embarque(s) de los packing lists: modo, transportista, documento,
    puertos, fechas y contenedores con su sello."""
    embarques = {}
    unidades = []
    for pl in pls:
        if pl.unidad:
            e = pl.unidad.embarque
            embarques[e.id] = e
            u = pl.unidad
            txt = f"{u.numero or u.etiqueta} ({u.tipo})" + (L(" seal {0}", u.sello) if u.sello else "")
            if txt not in unidades:
                unidades.append(txt)
    if not embarques:
        return {}
    e = next(iter(embarques.values()))
    return {
        "embarque": ", ".join(x.codigo for x in embarques.values()),
        "modo": L(listas.nombre("modo_transporte", e.tipo_transporte)), "transportista": e.transportista,
        "documento": ", ".join(x.documento_numero for x in embarques.values() if x.documento_numero) or None,
        "puerto_origen": _puerto(db, e.puerto_origen), "puerto_destino": _puerto(db, e.puerto_destino),
        "etd": e.salida_real or e.etd, "eta": e.arribo_real or e.eta, "unidades": unidades,
    }


def _fecha(v) -> str:
    if not v:
        return "—"
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v)
        except ValueError:
            return v
    if isinstance(v, datetime):
        v = v.date()
    # Formato de fecha del usuario (preferencias del perfil)
    return fecha_txt(v) if isinstance(v, date) else str(v)


def _num(v, d: int = 0) -> str:
    if v is None or v == "":
        return "—"
    if d == 0 and isinstance(v, float) and v != int(v):  # cantidad medida: hasta 3 decimales
        return f"{v:,.3f}".rstrip("0")
    return f"{v:,.{d}f}"


def _por_unidad_txt(por_unidad: dict, campo: str | None = None) -> str:
    partes_ = []
    for u, v in por_unidad.items():
        n = v[campo] if campo else v
        if n:
            partes_.append(f"{_num(n)} {L(unidad_txt(u, 2)).lower()}")
    return ", ".join(partes_) or "—"


def datos_factura(db: Session, f) -> dict:
    p = partes(db, f.sociedad, f.centro, f.centro_destino)
    pls = [pl for pl in f.packing_lists if pl.estado != "CANCELADO"]
    ocs = sorted({l.posicion_oc.oc for l in f.lineas}, key=lambda o: o.numero)
    lineas = []
    importe = 0.0
    por_unidad: dict[str, int] = {}
    for l in f.lineas:
        total = round(l.cantidad * l.precio_unitario, 2)
        importe += total
        por_unidad[l.unidad] = por_unidad.get(l.unidad, 0) + l.cantidad
        lineas.append({
            "oc": l.oc_numero, "posicion": l.posicion, "sku": l.codigo_sap, "upc": l.upc, "marca": l.marca, "estilo": l.estilo,
            "color": l.color, "talla": l.talla, "descripcion": sin_marca(l.descripcion_comercial or l.descripcion, l.marca),
            "partida": l.partida_arancelaria, "origen": l.pais_origen, "cantidad": l.cantidad, "unidad": l.unidad,
            "precio": l.precio_unitario, "total": total, "motivo_precio": l.motivo_precio, "prepack": l.prepack if l.tipo_empaque == "PREPACK" else None,
        })
    bultos = neto = bruto = cbm = 0
    pallets = 0
    for pl in pls:
        t = totales_pl(pl)
        bultos += t["cajas"]
        neto += t["peso_neto"]
        bruto += t["peso_bruto"]
        cbm += t["cbm"]
        pallets += t["pallets"]
    importe = round(importe, 2)
    return {
        "tipo": "factura", "numero": nombre_factura(f), "fecha": f.fecha, "oficial": f.estado == "FINALIZADA",
        "estado": f.estado, "moneda": f.moneda, "incoterm": f.incoterm, "condiciones": f.condiciones,
        "observaciones": f.observaciones, "exportador": _exportador(db, f.proveedor),
        "propios": _propios("facturas", f.extra),
        "importador": p["facturar_a"], "consignatario": p["notify"], "destino": p["destino"],
        "ocs": [o.numero for o in ocs],
        "pais_origen": ", ".join(sorted({x for x in (_pais(db, l.pais_origen) for l in f.lineas) if x})) or "—",
        "pais_procedencia": ", ".join(sorted({x for x in (_pais(db, o.pais_procedencia) for o in ocs) if x})) or "—",
        "pais_destino": p["destino"]["pais"] if p.get("destino") else p["notify"]["pais"],
        "puerto_embarque": ", ".join(sorted({x for x in (_puerto(db, o.puerto_despacho) for o in ocs) if x})) or None,
        "transporte": _transporte(db, pls), "lineas": lineas,
        "totales": {"por_unidad": por_unidad, "importe": importe, "bultos": bultos, "peso_neto": round(neto, 2),
                    "peso_bruto": round(bruto, 2), "cbm": round(cbm, 3), "pallets": pallets},
        "total_letras": monto_en_letras(importe, f.moneda),
        "pls": [pl.numero for pl in pls],
    }


def datos_pl(db: Session, pl) -> dict:
    f = pl.factura
    base = datos_factura(db, f)
    from app.modulos.empaque import empaques

    empaques.recalcular(pl) if pl.estado != "FINALIZADO" else None
    rangos = numeracion(pl)
    # El documento lista los bultos (cajas) con su contenido completo, aunque
    # vaya dentro de inner packs, y aparte los soportes (pallets) que los llevan
    bultos = [g for g in empaques._orden_arbol(pl) if empaques.cuenta_como(g) == "BULTO"]
    total_cajas = sum(g.num_cajas for g in bultos)
    from app.modulos.empaque.packing import destinos_pl

    destinos = [f"{x['centro_destino']} · {x['nombre'] or ''}" + (f" ({x['pais']})" if x["pais"] else "")
                for x in destinos_pl(db, pl) if x["centro_destino"]]
    grupos = []
    from app.modulos.empaque.packing import etiqueta_caja

    for g in bultos:
        cbm = cbm_caja(g)
        et = etiqueta_caja(g, pl)
        items = []
        for pll, n in empaques.contenido(pl, g):
            fl = pll.factura_linea
            items.append({"oc": fl.oc_numero, "posicion": fl.posicion, "sku": fl.codigo_sap, "upc": fl.upc,
                          "marca": fl.marca, "descripcion": sin_marca(fl.descripcion_comercial or fl.descripcion, fl.marca),
                          "estilo": fl.estilo, "color": fl.color, "talla": fl.talla, "unidad": fl.unidad,
                          "por_caja": n, "total": n * g.num_cajas,
                          "partida": fl.partida_arancelaria, "inner_pack": inner_de(fl),
                          "inners": n // inner_de(fl) if inner_de(fl) else None})
        soporte = next((a for a in empaques.ancestros(g) if empaques.cuenta_como(a) == "SOPORTE"), None)
        grupos.append({
            "rango": empaques.rango_txt(pl, g, rangos), "num_cajas": g.num_cajas, "items": items,
            "tipo": empaques.nombre_tipo(g),
            "interior": ", ".join(f"{empaques.por_padre(g, h):g} × {empaques.nombre_tipo(h)}"
                                  for h in empaques.hijos(pl, g)) or None,
            "medidas": f"{_num(g.largo)} x {_num(g.ancho)} x {_num(g.alto)}" if g.largo else "—",
            "neto_caja": g.peso_neto_caja, "bruto_caja": g.peso_bruto_caja, "tara_caja": (
                round(g.peso_bruto_caja - g.peso_neto_caja, 3) if g.peso_bruto_caja is not None else None),
            "neto_total": round(g.peso_neto_caja * g.num_cajas, 2) if g.peso_neto_caja else None,
            "bruto_total": round(g.peso_bruto_caja * g.num_cajas, 2) if g.peso_bruto_caja else None,
            # Lo que va sobre un soporte ocupa el volumen del soporte
            "cbm": round(cbm * g.num_cajas, 4) if cbm and not soporte else None,
            "pallet": empaques.rango_txt(pl, soporte, rangos) if soporte else None,
            "etiqueta": L("Standard") if et["tipo"] == "ESTANDAR" else L("Consolidated"),
            "ocs": et["ocs"], "centro_destino": et["centro_destino"],
            "largo": g.largo, "ancho": g.ancho, "alto": g.alto,
        })
    sin_caja = [{"oc": pll.factura_linea.oc_numero, "sku": pll.factura_linea.codigo_sap,
                 "estilo": pll.factura_linea.estilo, "talla": pll.factura_linea.talla,
                 "cantidad": pll.cantidad - cubierto(pll), "unidad": pll.factura_linea.unidad}
                for pll in pl.lineas if pll.cantidad - cubierto(pll) > 0]
    t = totales_pl(pl)
    pallets = []
    for pa in empaques._orden_arbol(pl):
        if empaques.cuenta_como(pa) != "SOPORTE":
            continue
        dentro = [h for h in empaques.descendientes(pl, pa) if empaques.cuenta_como(h) == "BULTO"]
        cbm_pa = cbm_caja(pa)
        pallets.append({"numero": empaques.rango_txt(pl, pa, rangos), "tipo": empaques.nombre_tipo(pa),
                        "unidades": pa.num_cajas, "cajas": sum(h.num_cajas for h in dentro),
                        "medidas": f"{_num(pa.largo)} x {_num(pa.ancho)} x {_num(pa.alto)}" if pa.largo else "—",
                        "tara": pa.tara or 0, "bruto": round((pa.peso_bruto_caja or 0) * pa.num_cajas, 2),
                        "cbm": round(cbm_pa * pa.num_cajas, 3) if cbm_pa else None})
    return {
        **base, "tipo": "pl", "numero_pl": pl.numero, "oficial": pl.estado == "FINALIZADO", "estado": pl.estado,
        "transporte": _transporte(db, [pl]), "grupos": grupos, "sin_caja": sin_caja, "pallets": pallets,
        "total_cajas": total_cajas,
        "totales_pl": {**t, "por_unidad_txt": _por_unidad_txt(t["por_unidad"], "cantidad")},
        "total_bultos_letras": cantidad_en_letras(total_cajas) + " " + (L("PACKAGE") if total_cajas == 1 else L("PACKAGES")),
        "destinos": destinos,
    }


# ---- Estructura PDF -------------------------------------------------------------
def _estilos():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8, leading=10, textColor=TINTA)
    return {
        "base": base,
        "chico": ParagraphStyle("chico", parent=base, fontSize=7, leading=8.6, textColor=TENUE),
        "etiqueta": ParagraphStyle("etq", parent=base, fontName="Helvetica-Bold", fontSize=6.5, leading=8,
                                   textColor=_acento()),
        "negrita": ParagraphStyle("neg", parent=base, fontName="Helvetica-Bold"),
        "titulo": ParagraphStyle("tit", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18),
        "der": ParagraphStyle("der", parent=base, alignment=TA_RIGHT),
        "celda": ParagraphStyle("celda", parent=base, fontSize=7.2, leading=8.8),
        "celda_der": ParagraphStyle("celdad", parent=base, fontSize=7.2, leading=8.8, alignment=TA_RIGHT),
        "cab": ParagraphStyle("cab", parent=base, fontName="Helvetica-Bold", fontSize=6.6, leading=8, textColor=TENUE),
        "cab_der": ParagraphStyle("cabd", parent=base, fontName="Helvetica-Bold", fontSize=6.6, leading=8,
                                  textColor=TENUE, alignment=TA_RIGHT),
    }


def _esc(v) -> str:
    return (str(v) if v not in (None, "") else "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class _Lienzo(rl_canvas.Canvas):
    """Pie con "Page X of Y" y marca de agua de borrador."""

    def __init__(self, *a, pie="", borrador=False, **kw):
        super().__init__(*a, **kw)
        self._paginas = []
        self._pie = pie
        self._borrador = borrador

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado in self._paginas:
            self.__dict__.update(estado)
            self._decorar(total)
            super().showPage()
        super().save()

    def _decorar(self, total):
        ancho, alto = self._pagesize
        self.setStrokeColor(LINEA)
        self.setLineWidth(0.5)
        self.line(14 * mm, 11 * mm, ancho - 14 * mm, 11 * mm)
        self.setFont("Helvetica", 6.8)
        self.setFillColor(TENUE)
        self.drawString(14 * mm, 7.5 * mm, self._pie)
        self.drawRightString(ancho - 14 * mm, 7.5 * mm, L("Page {0} of {1}", self._pageNumber, total))
        if self._borrador:
            self.saveState()
            self.setFont("Helvetica-Bold", 54)
            self.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.08))
            self.translate(ancho / 2, alto / 2)
            self.rotate(35)
            self.drawCentredString(0, 0, L("DRAFT · NOT OFFICIAL"))
            self.restoreState()


def _construir(historia: list, tamano, pie: str, borrador: bool) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=tamano, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm,
                            bottomMargin=16 * mm, title=pie)
    doc.build(historia, canvasmaker=lambda *a, **kw: _Lienzo(*a, pie=pie, borrador=borrador, **kw))
    return buf.getvalue()


def _cabecera(e, d: dict, ancho: float, titulo: str, subtitulo: str, datos: list[tuple[str, str]]) -> Table:
    """Emisor a la izquierda; título, número y fecha en un recuadro a la derecha."""
    exp = d["exportador"]
    izq = [Paragraph(_esc(exp["nombre"]), e["titulo"]),
           Paragraph(_esc(exp["direccion"]) + (f" · {_esc(exp['pais'])}" if exp.get("pais") else ""), e["chico"]),
           Paragraph(L("Tax ID: {0} · {1} · {2}", _esc(exp['id_fiscal']), _esc(exp['correos']), _esc(exp['telefono'])),
                     e["chico"])]
    filas = [[Paragraph(titulo, ParagraphStyle("t", parent=e["negrita"], fontSize=11, leading=13, textColor=_acento()))],
             [Paragraph(subtitulo, e["chico"])]]
    for k, v in datos:
        filas.append([Paragraph(f"<font color='#5b6475'>{k}</font>  <b>{_esc(v)}</b>", e["base"])])
    der = Table(filas, colWidths=[ancho * 0.36])
    der.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, _acento()), ("BACKGROUND", (0, 0), (-1, -1), FONDO),
                             ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 2),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    t = Table([[izq, der]], colWidths=[ancho * 0.64, ancho * 0.36])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _parte(e, titulo: str, p: dict | None) -> list:
    if not p:
        return [Paragraph(titulo, e["etiqueta"]), Paragraph("—", e["base"])]
    nombre = p.get("razon_social") or p.get("nombre")
    lineas = [Paragraph(titulo, e["etiqueta"]),
              Paragraph(f"<b>{_esc(p.get('codigo'))} · {_esc(nombre)}</b>", e["base"])]
    if p.get("id_fiscal"):
        lineas.append(Paragraph(L("Tax ID (NIT / RUC): {0}", _esc(p['id_fiscal'])), e["chico"]))
    lineas.append(Paragraph(_esc(p.get("direccion")) + (f" · {_esc(p['pais'])}" if p.get("pais") else ""), e["chico"]))
    if p.get("puerto"):
        lineas.append(Paragraph(L("Port of arrival: {0}", _esc(p.get('puerto_nombre') or p['puerto'])), e["chico"]))
    contacto = (p.get("contactos") or [None])[0]
    if contacto:
        lineas.append(Paragraph(L("Contact: {0} · {1}", _esc(contacto['nombre']), _esc(contacto['correos']))
                                + (f" · {_esc(contacto['telefono'])}" if contacto.get("telefono") else ""), e["chico"]))
    elif p.get("correos"):
        lineas.append(Paragraph(_esc(p["correos"]), e["chico"]))
    return lineas


def _bloque_partes(e, d: dict, ancho: float) -> Table:
    exp = d["exportador"]
    exportador = {"codigo": exp["codigo"], "razon_social": exp["nombre"], "id_fiscal": exp["id_fiscal"],
                  "direccion": exp["direccion"], "pais": exp["pais"],
                  "contactos": [{"nombre": exp["contacto"], "correos": exp["correos"], "telefono": exp["telefono"]}]
                  if exp.get("contacto") else []}
    t = Table([[_parte(e, L("EXPORTER / SELLER"), exportador), _parte(e, L("IMPORTER / BILL TO"), d["importador"]),
                _parte(e, L("CONSIGNEE / NOTIFY PARTY"), d["consignatario"])]], colWidths=[ancho / 3] * 3)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, LINEA),
                           ("INNERGRID", (0, 0), (-1, -1), 0.5, LINEA), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _rejilla(e, pares: list[tuple[str, str]], ancho: float, columnas: int = 4) -> Table:
    celdas = [[Paragraph(k.upper(), e["etiqueta"]), Paragraph(_esc(v), e["base"])] for k, v in pares]
    while len(celdas) % columnas:
        celdas.append("")
    filas = [celdas[i:i + columnas] for i in range(0, len(celdas), columnas)]
    t = Table(filas, colWidths=[ancho / columnas] * columnas)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), 0.5, LINEA),
                           ("INNERGRID", (0, 0), (-1, -1), 0.5, LINEA), ("BACKGROUND", (0, 0), (-1, -1), FONDO_2),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _tabla(e, encabezados: list[tuple[str, float, bool]], filas: list[list], ancho: float,
           pie: list | None = None) -> Table:
    """Tabla de detalle: encabezado que se repite en cada página, filas cebra."""
    total_rel = sum(w for _, w, _ in encabezados)
    anchos = [ancho * w / total_rel for _, w, _ in encabezados]
    datos = [[Paragraph(t, e["cab_der"] if der else e["cab"]) for t, _, der in encabezados]]
    for f in filas:
        datos.append([Paragraph(_esc(v) if not isinstance(v, Paragraph) else v, e["celda_der"] if der else e["celda"])
                      if not isinstance(v, Paragraph) else v for v, (_, _, der) in zip(f, encabezados)])
    if pie:
        datos.append([Paragraph(f"<b>{_esc(v)}</b>" if v not in (None, "") else "", e["celda_der"] if der else e["celda"])
                      for v, (_, _, der) in zip(pie, encabezados)])
    t = Table(datos, colWidths=anchos, repeatRows=1)
    estilo = [("LINEBELOW", (0, 0), (-1, 0), 0.8, _acento()), ("BACKGROUND", (0, 0), (-1, 0), FONDO),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
              ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2.5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINEA)]
    for i in range(2, len(datos) - (1 if pie else 0), 2):
        estilo.append(("BACKGROUND", (0, i), (-1, i), FONDO_2))
    if pie:
        estilo += [("LINEABOVE", (0, -1), (-1, -1), 0.8, TINTA), ("BACKGROUND", (0, -1), (-1, -1), FONDO)]
    t.setStyle(TableStyle(estilo))
    return t


def _firma(e, ancho: float, texto: str) -> KeepTogether:
    t = Table([[Paragraph(texto, e["chico"]), [Spacer(1, 16), Paragraph("_" * 42, e["base"]),
                                                Paragraph(L("Name, title and signature of the exporter"), e["chico"])]]],
              colWidths=[ancho * 0.6, ancho * 0.4])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return KeepTogether([Spacer(1, 8), t])


# ---- Factura comercial -----------------------------------------------------------
def pdf_factura(d: dict) -> bytes:
    e = _estilos()
    ancho = _papel()[0] - 28 * mm
    tr = d["transporte"] or {}
    h = [
        _cabecera(e, d, ancho, L("COMMERCIAL INVOICE"), L("Customs invoice · original"), [
            (L("No."), d["numero"]), (L("Date"), _fecha(d["fecha"])),
            (L("Status"), L("Official") if d["oficial"] else L("Draft"))]),
        Spacer(1, 6), _bloque_partes(e, d, ancho), Spacer(1, 5),
        _rejilla(e, [
            (L("Incoterm"), d["incoterm"]), (L("Currency"), d["moneda"]), (L("Payment terms"), d["condiciones"]),
            (L("Mode of transport"), tr.get("modo")),
            (L("Country of origin"), d["pais_origen"]), (L("Country of shipment"), d["pais_procedencia"]),
            (L("Country of destination"), d["pais_destino"]), (L("Carrier"), tr.get("transportista")),
            (L("Port of loading"), tr.get("puerto_origen") or d["puerto_embarque"]),
            (L("Port of discharge"), tr.get("puerto_destino") or d["consignatario"].get("puerto_nombre")),
            (L("B/L / AWB / waybill"), tr.get("documento")), (L("Packing lists"), ", ".join(d["pls"]) or "—"),
            *d.get("propios", []),
        ], ancho),
        Spacer(1, 7),
    ]
    filas = []
    for l in d["lineas"]:
        desc = f"<b>{_esc(l['descripcion'] or '')}</b><br/>" \
               f"<font color='#5b6475'>{_esc(l['estilo'])}{' · ' + _esc(l['color']) if l['color'] else ''}" \
               f"{L(' · size ') + _esc(l['talla']) if l['talla'] else ''}</font>"
        if l["prepack"]:
            desc += f"<br/><font color='{_acento_hex()}'>" + L("Prepack {0}", _esc(l['prepack'])) + "</font>"
        filas.append([f"{l['oc']}/{l['posicion']}", l["sku"], l["marca"] or "—", Paragraph(desc, e["celda"]), l["partida"], l["origen"],
                      _num(l["cantidad"]), l["unidad"], _num(l["precio"], 2), _num(l["total"], 2)])
    t = d["totales"]
    h.append(_tabla(e, [(L("PO / line"), 1.75, False), (L("Item code"), 1.45, False), (L("Brand"), 0.9, False), (L("Customs description"), 3.1, False),
                        (L("HS code (SAC)"), 1.2, False), (L("Origin"), 0.7, False), (L("Quantity"), 0.9, True),
                        (L("UoM"), 0.5, False), (L("Unit price"), 1.1, True), (L("Amount"), 1.3, True)],
                    filas, ancho, pie=["", "", "", L("{0} lines", len(d['lineas'])), "", "", _num(sum(l['cantidad'] for l in d['lineas'])),
                                       "", L("Total"), f"{d['moneda']} {_num(t['importe'], 2)}"]))
    resumen = _rejilla(e, [
        (L("Total quantity"), _por_unidad_txt(t["por_unidad"])), (L("Packages"), L("{0} cartons", _num(t['bultos']))
                                                                  + (L(" on {0} pallets", t['pallets']) if t["pallets"] else "")),
        (L("Net weight"), L("{0} kg", _num(t['peso_neto'], 2))), (L("Gross weight"), L("{0} kg", _num(t['peso_bruto'], 2))),
        (L("Volume"), f"{_num(t['cbm'], 3)} m³"), (L("Containers / AWB"), ", ".join(tr.get("unidades", [])) or "—"),
        (L("Total value ") + (d["incoterm"] or ""), f"{d['moneda']} {_num(t['importe'], 2)}"),
        (L("Purchase orders"), L("{0} (see lines)", len(d['ocs']))),
    ], ancho)
    h += [Spacer(1, 6), KeepTogether([resumen, Spacer(1, 4),
                                      Paragraph(L("<b>SAY:</b> {0}", _esc(d['total_letras'])), e["base"])])]
    if d.get("observaciones"):
        h += [Spacer(1, 4), Paragraph(L("<b>Remarks:</b> {0}", _esc(d['observaciones'])), e["chico"])]
    h.append(_firma(e, ancho, _declaracion("declaracion_factura", L(
        "We declare under oath that the information in this invoice is true and correct, that the value is the price "
        "actually paid or payable for the goods and that the declared origin is correct."))))
    return _construir(h, _papel(), L("Commercial invoice {0} · {1}", d['numero'], d['exportador']['nombre']), not d["oficial"])


# ---- Packing list ----------------------------------------------------------------
def pdf_pl(d: dict) -> bytes:
    e = _estilos()
    tam = landscape(_papel())
    ancho = tam[0] - 28 * mm
    tr = d["transporte"] or {}
    tp = d["totales_pl"]
    h = [
        _cabecera(e, d, ancho, L("PACKING LIST"), L("Detailed carton list"), [
            (L("No."), f"{d['numero']} · {d['numero_pl']}"), (L("Date"), _fecha(d["fecha"])),
            (L("Invoice"), d["numero"]), (L("Status"), L("Official") if d["oficial"] else L("Draft"))]),
        Spacer(1, 6), _bloque_partes(e, d, ancho), Spacer(1, 5),
        _rejilla(e, [
            (L("Mode of transport"), tr.get("modo")),
            (L("Carrier"), tr.get("transportista")), (L("B/L / AWB / waybill"), tr.get("documento")),
            (L("Container / AWB"), ", ".join(tr.get("unidades", [])) or "—"),
            (L("Port of loading"), tr.get("puerto_origen") or d["puerto_embarque"]),
            (L("Port of discharge"), tr.get("puerto_destino")), (L("Country of origin"), d["pais_origen"]),
            (L("Country of destination"), d["pais_destino"]),
            # El destino final solo en la cabecera si todo el PL va a un mismo destino
            (L("Final destination"), d["destinos"][0] if len(d["destinos"]) == 1 else L("Per carton (see lines)")),
            (L("ETD / ETA"), f"{_fecha(tr.get('etd'))} / {_fecha(tr.get('eta'))}"),
        ], ancho, columnas=5),
        Spacer(1, 7),
    ]
    filas = []
    for g in d["grupos"]:
        for i, it in enumerate(g["items"]):
            primera = i == 0
            filas.append([
                g["rango"] if primera else "", _num(g["num_cajas"]) if primera else "",
                f"{it['oc']}/{it['posicion']}", it["sku"], it["marca"] or "—",
                Paragraph(f"{_esc(it['descripcion'] or '')}<br/><font color='#5b6475'>{_esc(it['estilo'])}"
                          f"{' · ' + _esc(it['color']) if it['color'] else ''}</font>", e["celda"]),
                it["talla"], _num(it["inners"]) if it["inners"] else "—", _num(it["inner_pack"]) if it["inner_pack"] else "—",
                _num(it["por_caja"]), _num(it["total"]), it["unidad"],
                g["medidas"] if primera else "", _num(g["neto_caja"], 2) if primera else "",
                _num(g["bruto_caja"], 2) if primera else "", _num(g["neto_total"], 2) if primera else "",
                _num(g["bruto_total"], 2) if primera else "", _num(g["cbm"], 3) if primera else "",
                (g["pallet"] or "—") if primera else "",
                (g["etiqueta"] + (f" → {g['centro_destino']}" if g["centro_destino"] else "")) if primera else "",
            ])
    h.append(_tabla(e, [
        (L("Cartons"), 0.75, False), (L("Qty"), 0.45, True), (L("PO / line"), 1.1, False), (L("Item code"), 1.15, False),
        (L("Brand"), 0.7, False), (L("Customs description · style"), 2.0, False), (L("Size"), 0.45, False),
        (L("Inner packs / ctn"), 0.6, True), (L("Per inner pack"), 0.6, True), (L("Total / ctn"), 0.6, True), (L("Total"), 0.65, True),
        (L("UoM"), 0.45, False), (L("Dimensions cm"), 1.05, False), (L("Net/ctn"), 0.75, True), (L("Gross/ctn"), 0.85, True),
        (L("Net total"), 0.75, True), (L("Gross total"), 0.8, True), ("m³", 0.6, True), (L("Pallet"), 0.5, False),
        (L("Label → dest."), 1.0, False)],
        filas, ancho, pie=[L("Total"), _num(d["total_cajas"]), "", "", "", "", "", "", "", "", "", "", "", "", "",
                           _num(tp["peso_neto"], 2), _num(tp["peso_bruto"], 2), _num(tp["cbm"], 3), "", ""]))
    if d["pallets"]:
        h += [Spacer(1, 6), Paragraph(L("PALLETS"), e["etiqueta"]),
              _tabla(e, [(L("Pallet"), 1, False), (L("Cartons"), 1, True), (L("Dimensions cm"), 2, False), (L("Tare kg"), 1, True),
                         (L("Gross kg"), 1, True), ("m³", 1, True)],
                     [[p["numero"], _num(p["cajas"]), p["medidas"], _num(p["tara"], 1), _num(p["bruto"], 2),
                       _num(p["cbm"], 3) if p["cbm"] else "—"] for p in d["pallets"]], ancho * 0.6)]
    if d["sin_caja"]:
        h += [Spacer(1, 6), Paragraph(L("NOT YET PACKED"), e["etiqueta"]),
              _tabla(e, [(L("PO"), 1, False), (L("Item code"), 1.4, False), (L("Style"), 1.4, False), (L("Size"), 0.6, False),
                         (L("Quantity"), 0.8, True), (L("UoM"), 0.5, False)],
                     [[x["oc"], x["sku"], x["estilo"], x["talla"], _num(x["cantidad"]), x["unidad"]] for x in d["sin_caja"]],
                     ancho * 0.6)]
    consig = d["consignatario"]
    marcas = (L("<b>{0}</b><br/>{1}<br/>Invoice {2} · PO per carton label<br/>Carton no. __ of {3} · Made in {4}", _esc(consig.get('nombre')), _esc(consig.get('direccion')), _esc(d['numero']), d['total_cajas'], _esc(d['pais_origen'])))
    resumen = _rejilla(e, [
        (L("Total packages"), L("{0} cartons", _num(d['total_cajas'])) + (L(" on {0} pallets", _num(tp['pallets'])) if tp["pallets"] else "")),
        (L("Quantity"), tp["por_unidad_txt"]), (L("Net weight"), L("{0} kg", _num(tp['peso_neto'], 2))),
        (L("Gross weight"), L("{0} kg", _num(tp['peso_bruto'], 2))), (L("Volume"), f"{_num(tp['cbm'], 3)} m³"),
    ], ancho, columnas=5)
    marca_t = Table([[Paragraph(L("SHIPPING MARKS"), e["etiqueta"])], [Paragraph(marcas, e["base"])]],
                    colWidths=[ancho * 0.5], hAlign="LEFT")
    marca_t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, TINTA), ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
    h += [Spacer(1, 7), KeepTogether([resumen, Spacer(1, 4),
                                      Paragraph(L("<b>TOTAL PACKAGES:</b> {0}", _esc(d['total_bultos_letras'])), e["base"]),
                                      Spacer(1, 6), marca_t])]
    h.append(_firma(e, ancho, _declaracion("declaracion_packing", L(
        "We declare that the contents, numbering, dimensions and weights of the packages correspond to the goods "
        "shipped. Every unit or pair carries its individual label; inner packs carry an inner pack label with the "
        "product and the quantity inside."))))
    return _construir(h, tam, L("Packing list {0} {1} · {2}", d['numero'], d['numero_pl'], d['exportador']['nombre']),
                      not d["oficial"])


# ---- Reportes ----------------------------------------------------------------------
def _logo_empresa(alto: float):
    """Logo de la empresa para los reportes (o None si no tiene o no lo quiere)."""
    import base64

    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image

    from app.core.empresa import configuracion_actual

    logo = (configuracion_actual().get("empresa") or {}).get("logo")
    if not logo or not _empresa("documentos")["logo_en_reportes"] or "," not in logo:
        return None
    try:
        datos = io.BytesIO(base64.b64decode(logo.split(",", 1)[1]))
        ancho_px, alto_px = ImageReader(datos).getSize()
        datos.seek(0)
        return Image(datos, width=alto * ancho_px / alto_px, height=alto)
    except Exception:  # una imagen que no se puede leer no impide el reporte
        return None


def pdf_reporte(titulo: str, subtitulo: str, filtros: str, indicadores: list[tuple[str, str]],
                columnas: list[tuple[str, float, bool]], filas: list[list]) -> bytes:
    from app.modulos.acceso import visibilidad

    indicadores, columnas, filas, _ = visibilidad.reporte(indicadores, columnas, filas)
    from app.modulos.documentos import idioma_doc

    titulo, subtitulo, indicadores, columnas, filas, _ = idioma_doc.reporte(titulo, subtitulo, indicadores, columnas, filas)
    e = _estilos()
    tam = landscape(_papel())
    ancho = tam[0] - 28 * mm
    izquierda = [Paragraph(titulo, e["titulo"]), Paragraph(subtitulo, e["chico"])]
    logo = _logo_empresa(alto=12 * mm)
    if logo:
        izquierda = Table([[logo, izquierda]], colWidths=[logo.drawWidth + 4 * mm, None])
        izquierda.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    cab = Table([[izquierda,
                  Paragraph(L("Generated {0}", fecha_hora_txt(datetime.now())) + f"<br/>{_esc(filtros) if filtros else L('No filters')}",
                            ParagraphStyle("f", parent=e["chico"], alignment=TA_RIGHT))]],
                colWidths=[ancho * 0.6, ancho * 0.4])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, _acento()),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    h = [cab, Spacer(1, 6)]
    if indicadores:
        h += [_rejilla(e, indicadores, ancho, columnas=min(len(indicadores), 5)), Spacer(1, 7)]
    h.append(_tabla(e, columnas, filas, ancho))
    return _construir(h, tam, titulo, False)


# ---- Ficha técnica del producto -------------------------------------------------------
# Las etiquetas salen del catálogo (productos.etiquetas_ficha): ningún nombre fijo de una familia
ESTADO_PARTIDA = {"ok": "Confirmed", "historial": "Suggested by history", "elegir": "To choose", "pendiente": "No official data",
                  "invalido": "Invalid"}
INTERNOS_FICHA = ("comp", "descManual", "comManual", "uso", "tallas", "desc", "descCom", "sacDesc")


def _legible(k: str) -> str:
    return k.replace("_", " ").replace(".", " ").strip().capitalize()


def _valor_ficha(v, k: str = "", et: dict | None = None) -> str:
    ops = ((et or {}).get("valores") or {}).get(k) or {}
    if isinstance(v, list):
        return ", ".join(str(ops.get(x, x)) for x in v)
    if isinstance(v, bool):
        return L("Yes") if v else L("No")
    return str(ops.get(v, v))


def _fmt_partida(c) -> str:
    d = "".join(ch for ch in str(c or "") if ch.isdigit())
    if len(d) <= 4:
        return d or "—"
    return ".".join([d[:4]] + [d[i:i + 2] for i in range(4, len(d), 2)])


def secciones_ficha(d: dict) -> dict:
    """Contenido de la ficha técnica ya en texto (lo usan el PDF, el Excel y la
    vista de versiones anteriores)."""
    estado = d.get("estado_txt") or d.get("estado")
    codigo = d.get("codigo") or d.get("sugerido")
    clasif = [(L("HS code (SAC)"), codigo or L("Not classified")), (L("Status"), estado or "—"),
              (L("Confidence"), d.get("confianza") or "—"),
              (L("Reviewed by"), f"{d.get('revisado_por') or '—'}" + (f" · {_fecha(d['revisado_en'])}" if d.get("revisado_en") else ""))]
    et = d.get("etiquetas") or {}
    orden_paises = et.get("paises") or []
    partidas = []
    for pais, x in sorted((d.get("partidas") or {}).items(),
                          key=lambda kv: (orden_paises.index(kv[0]) if kv[0] in orden_paises else 999, kv[0])):
        x = x if isinstance(x, dict) else {"codigo": x}
        partidas.append([pais, _fmt_partida(x.get("codigo")), f"{x['dai']}%" if x.get("dai") not in (None, "") else "—",
                         L(ESTADO_PARTIDA.get(x.get("estado"), x.get("estado") or "—")),
                         L("By hand") if x.get("manual") else (x.get("fuente") or "—").capitalize()])
    f = d.get("ficha") or {}
    an = d.get("analisis") or {}
    datos = [(L("Product type"), an.get("tipo_txt") or (et.get("tipos") or {}).get(d.get("tipo"), d.get("tipo")) or "—"),
             (L("Country of origin"), d.get("pais_origen") or "—"),
             (L("Generic code"), d.get("codigo_generico") or "—"), (L("Group"), d.get("grupo") or "—")]
    for k, lbl in (("uso", L("Use")), ("tallas", L("Sizes"))):
        if f.get(k):
            datos.append((lbl, str(f[k])))
    if an.get("atributos"):
        datos += [(str(a[0]), str(a[1])) for a in an["atributos"] if len(a) == 2]
    else:
        campos = et.get("campos") or {}
        datos += [(campos.get(k) or _legible(k), _valor_ficha(v, k, et)) for k, v in f.items()
                  if k not in INTERNOS_FICHA and v not in (None, "", [], {}) and not isinstance(v, dict)]
    comp = f.get("comp") or {}
    partes = et.get("partes") or {}
    composicion = [[partes.get(k) or _legible(k), v] for k, v in comp.items() if v] if isinstance(comp, dict) else []
    tallas = [[a["sku"], a["upc"] or "—", a["talla"], a["unidad"], a["descripcion"] or "—"]
              for a in d.get("articulos") or [] if a["tipo"] == "SOLIDO"]
    return {"clasificacion": clasif, "descripcion": d.get("descripcion_aduana") or "",
            "descripcion_comercial": d.get("descripcion_comercial") or "",
            "razones": [str(r) for r in (an.get("razones") or [])[:8]], "partidas": partidas, "datos": datos,
            "composicion": composicion, "tallas": tallas}


def pdf_ficha_producto(d: dict) -> bytes:
    """Ficha técnica con el veredicto de clasificación y los códigos por país."""
    e = _estilos()
    tam = _papel()
    ancho = tam[0] - 28 * mm
    estado = d.get("estado_txt") or d.get("estado")
    cab = Table([[[Paragraph(_esc(f"{d['estilo']} · {d['color']}"), e["titulo"]),
                   Paragraph(_esc(d.get("nombre")), e["base"]),
                   Paragraph(f"{_esc(d.get('proveedor'))} · {_esc(d.get('marca_nombre') or d.get('marca'))}", e["chico"])],
                  [Paragraph(L("TECHNICAL SHEET"), ParagraphStyle("t", parent=e["negrita"], fontSize=11, leading=13,
                                                               textColor=_acento(), alignment=TA_RIGHT)),
                   Paragraph(L("Version {0} · {1}", d.get('version_ficha') or 1, _esc(estado)),
                             ParagraphStyle("s", parent=e["base"], alignment=TA_RIGHT)),
                   Paragraph(L("Generated {0}", fecha_hora_txt(datetime.now())),
                             ParagraphStyle("f", parent=e["chico"], alignment=TA_RIGHT))]]],
                colWidths=[ancho * 0.62, ancho * 0.38])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, _acento()),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    h = [cab, Spacer(1, 8)]

    x = secciones_ficha(d)
    h += [Paragraph(L("CLASSIFICATION"), e["etiqueta"]), Spacer(1, 2), _rejilla(e, x["clasificacion"], ancho), Spacer(1, 4)]
    if x["descripcion"]:
        h += [Paragraph(L("<b>Customs description:</b> {0}", _esc(x['descripcion'])), e["base"]), Spacer(1, 4)]
    for r in x["razones"]:
        h.append(Paragraph(f"• {_esc(r)}", e["chico"]))
    if d.get("observaciones"):
        h += [Spacer(1, 3), Paragraph(L("<b>Notes to the supplier:</b> {0}", _esc(d['observaciones'])), e["base"])]
    h.append(Spacer(1, 8))
    if x["partidas"]:
        h += [Paragraph(L("NATIONAL TARIFF CODES BY DESTINATION"), e["etiqueta"]), Spacer(1, 2),
              _tabla(e, [(L("Country"), 0.8, False), (L("Code"), 1.6, False), (L("Duty (DAI)"), 0.8, True),
                         (L("Status"), 0.8, False), (L("Source"), 0.8, False)], x["partidas"], ancho), Spacer(1, 8)]
    h += [Paragraph(L("PRODUCT DATA"), e["etiqueta"]), Spacer(1, 2), _rejilla(e, x["datos"], ancho), Spacer(1, 8)]
    if x["composicion"]:
        h += [Paragraph(L("COMPOSITION"), e["etiqueta"]), Spacer(1, 2),
              _tabla(e, [(L("Part"), 1, False), (L("Materials"), 3, False)], x["composicion"], ancho), Spacer(1, 8)]
    if x["tallas"]:
        h += [Paragraph(L("SIZES"), e["etiqueta"]), Spacer(1, 2),
              _tabla(e, [(L("SKU"), 1.4, False), (L("UPC"), 1.4, False), (L("Size"), 0.7, False), (L("Unit"), 0.6, False),
                         (L("Description"), 2.4, False)], x["tallas"], ancho)]
    return _construir(h, tam, L("Technical sheet {0} {1} · {2}", d['estilo'], d['color'], d.get('proveedor') or ''),
                      d.get("estado") not in ("aprobado", "corregido"))
