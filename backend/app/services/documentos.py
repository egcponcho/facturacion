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
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Pais, Proveedor, Puerto
from .cantidades import cbm_caja, cubierto, nombre_factura, numeracion, totales_pl
from .partes import partes

TINTA = colors.HexColor("#1f2430")
TENUE = colors.HexColor("#5b6475")
ACENTO = colors.HexColor("#5b3fd1")
LINEA = colors.HexColor("#d9dce3")
FONDO = colors.HexColor("#f3f1fb")
FONDO_2 = colors.HexColor("#f7f8fa")

MODOS = {"MARITIMO": "Marítimo", "AEREO": "Aéreo", "TERRESTRE": "Terrestre"}
UNIDADES = {"PAR": "Pares", "UN": "Unidades", "CJ": "Cajas prepack"}


# ---- Montos en letras ---------------------------------------------------------
_UNIDADES = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE",
             "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE",
             "VEINTIUN", "VEINTIDÓS", "VEINTITRÉS", "VEINTICUATRO", "VEINTICINCO", "VEINTISÉIS", "VEINTISIETE",
             "VEINTIOCHO", "VEINTINUEVE"]
_DECENAS = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_CENTENAS = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS",
             "OCHOCIENTOS", "NOVECIENTOS"]
MONEDAS = {"USD": ("DÓLAR", "DÓLARES"), "EUR": ("EURO", "EUROS"), "GTQ": ("QUETZAL", "QUETZALES"),
           "CRC": ("COLÓN", "COLONES"), "HNL": ("LEMPIRA", "LEMPIRAS"), "NIO": ("CÓRDOBA", "CÓRDOBAS"),
           "PAB": ("BALBOA", "BALBOAS")}


def _cientos(n: int) -> str:
    if n == 100:
        return "CIEN"
    c, r = divmod(n, 100)
    partes_ = [_CENTENAS[c]] if c else []
    if r < 30:
        partes_.append(_UNIDADES[r])
    else:
        d, u = divmod(r, 10)
        partes_.append(_DECENAS[d] + (f" Y {_UNIDADES[u]}" if u else ""))
    return " ".join(p for p in partes_ if p)


def numero_en_letras(n: int) -> str:
    if n == 0:
        return "CERO"
    grupos = []
    for divisor, singular, plural in ((10**9, "MIL MILLONES", "MIL MILLONES"), (10**6, "UN MILLÓN", "MILLONES"),
                                      (10**3, "MIL", "MIL")):
        q, n = divmod(n, divisor)
        if q:
            if divisor == 10**3:
                grupos.append("MIL" if q == 1 else f"{_cientos(q)} MIL")
            elif divisor == 10**6:
                grupos.append(singular if q == 1 else f"{numero_en_letras(q)} {plural}")
            else:
                grupos.append(f"{numero_en_letras(q)} {plural}")
    if n:
        grupos.append(_cientos(n))
    return " ".join(grupos)


def monto_en_letras(valor: float, moneda: str) -> str:
    entero = int(round(valor * 100)) // 100
    centavos = int(round(valor * 100)) % 100
    sing, plur = MONEDAS.get(moneda, (moneda, moneda))
    texto = numero_en_letras(entero)
    return f"{texto} {sing if entero == 1 else plur} CON {centavos:02d}/100"


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
            txt = f"{u.numero or u.etiqueta} ({u.tipo})" + (f" sello {u.sello}" if u.sello else "")
            if txt not in unidades:
                unidades.append(txt)
    if not embarques:
        return {}
    e = next(iter(embarques.values()))
    return {
        "embarque": ", ".join(x.codigo for x in embarques.values()),
        "modo": MODOS.get(e.tipo_transporte, e.tipo_transporte), "transportista": e.transportista,
        "documento": ", ".join(x.documento_numero for x in embarques.values() if x.documento_numero) or None,
        "puerto_origen": _puerto(db, e.puerto_origen), "puerto_destino": _puerto(db, e.puerto_destino),
        "etd": e.salida_real or e.etd, "eta": e.arribo_real or e.eta, "unidades": unidades,
    }


def _fecha(v) -> str:
    if not v:
        return "—"
    if isinstance(v, datetime):
        v = v.date()
    return v.strftime("%d/%m/%Y") if isinstance(v, date) else str(v)


def _num(v, d: int = 0) -> str:
    if v is None or v == "":
        return "—"
    return f"{v:,.{d}f}"


def _por_unidad_txt(por_unidad: dict, campo: str | None = None) -> str:
    partes_ = []
    for u, v in por_unidad.items():
        n = v[campo] if campo else v
        if n:
            partes_.append(f"{_num(n)} {UNIDADES.get(u, u).lower()}")
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
            "color": l.color, "talla": l.talla, "descripcion": l.descripcion_comercial or l.descripcion,
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
    rangos = numeracion(pl)
    total_cajas = sum(g.num_cajas for g in pl.grupos)
    grupos = []
    from .packing import etiqueta_caja

    for g in pl.grupos:
        d, h = rangos[g.id]
        cbm = cbm_caja(g)
        et = etiqueta_caja(g)
        items = []
        for it in g.items:
            fl = it.pl_linea.factura_linea
            items.append({"oc": fl.oc_numero, "posicion": fl.posicion, "sku": fl.codigo_sap, "upc": fl.upc,
                          "marca": fl.marca,
                          "estilo": fl.estilo, "color": fl.color, "talla": fl.talla, "unidad": fl.unidad,
                          "por_caja": it.cantidad_por_caja, "total": it.cantidad_por_caja * g.num_cajas,
                          "partida": fl.partida_arancelaria})
        grupos.append({
            "rango": str(d) if d == h else f"{d}-{h}", "num_cajas": g.num_cajas, "items": items,
            "medidas": f"{_num(g.largo)} x {_num(g.ancho)} x {_num(g.alto)}" if g.largo else "—",
            "neto_caja": g.peso_neto_caja, "bruto_caja": g.peso_bruto_caja,
            "neto_total": round(g.peso_neto_caja * g.num_cajas, 2) if g.peso_neto_caja else None,
            "bruto_total": round(g.peso_bruto_caja * g.num_cajas, 2) if g.peso_bruto_caja else None,
            "cbm": round(cbm * g.num_cajas, 4) if cbm else None,
            "pallet": g.pallet.numero if g.pallet else None,
            "etiqueta": "Estándar" if et["tipo"] == "ESTANDAR" else "Consolidada",
            "ocs": et["ocs"], "centro_destino": et["centro_destino"],
            "largo": g.largo, "ancho": g.ancho, "alto": g.alto,
        })
    sin_caja = [{"oc": pll.factura_linea.oc_numero, "sku": pll.factura_linea.codigo_sap,
                 "estilo": pll.factura_linea.estilo, "talla": pll.factura_linea.talla,
                 "cantidad": pll.cantidad - cubierto(pll), "unidad": pll.factura_linea.unidad}
                for pll in pl.lineas if pll.cantidad - cubierto(pll) > 0]
    t = totales_pl(pl)
    pallets = []
    for pa in sorted(pl.pallets, key=lambda x: x.numero):
        cajas = sum(g.num_cajas for g in pl.grupos if g.pallet is pa)
        pallets.append({"numero": pa.numero, "cajas": cajas, "medidas": f"{_num(pa.largo)} x {_num(pa.ancho)} x {_num(pa.alto)}",
                        "tara": pa.peso_tara, "cbm": round(pa.largo * pa.ancho * pa.alto / 1_000_000, 3)})
    return {
        **base, "tipo": "pl", "numero_pl": pl.numero, "oficial": pl.estado == "FINALIZADO", "estado": pl.estado,
        "transporte": _transporte(db, [pl]), "grupos": grupos, "sin_caja": sin_caja, "pallets": pallets,
        "total_cajas": total_cajas,
        "totales_pl": {**t, "por_unidad_txt": _por_unidad_txt(t["por_unidad"], "cantidad")},
        "total_bultos_letras": numero_en_letras(total_cajas) + (" BULTO" if total_cajas == 1 else " BULTOS"),
    }


# ---- Estructura PDF -------------------------------------------------------------
def _estilos():
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=8, leading=10, textColor=TINTA)
    return {
        "base": base,
        "chico": ParagraphStyle("chico", parent=base, fontSize=7, leading=8.6, textColor=TENUE),
        "etiqueta": ParagraphStyle("etq", parent=base, fontName="Helvetica-Bold", fontSize=6.5, leading=8,
                                   textColor=ACENTO),
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
    """Pie con "Página X de Y" y marca de agua de borrador."""

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
        self.drawRightString(ancho - 14 * mm, 7.5 * mm, f"Página {self._pageNumber} de {total}")
        if self._borrador:
            self.saveState()
            self.setFont("Helvetica-Bold", 54)
            self.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.08))
            self.translate(ancho / 2, alto / 2)
            self.rotate(35)
            self.drawCentredString(0, 0, "BORRADOR · NO OFICIAL")
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
           Paragraph(f"ID fiscal: {_esc(exp['id_fiscal'])} · {_esc(exp['correos'])} · {_esc(exp['telefono'])}",
                     e["chico"])]
    filas = [[Paragraph(titulo, ParagraphStyle("t", parent=e["negrita"], fontSize=11, leading=13, textColor=ACENTO))],
             [Paragraph(subtitulo, e["chico"])]]
    for k, v in datos:
        filas.append([Paragraph(f"<font color='#5b6475'>{k}</font>  <b>{_esc(v)}</b>", e["base"])])
    der = Table(filas, colWidths=[ancho * 0.36])
    der.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, ACENTO), ("BACKGROUND", (0, 0), (-1, -1), FONDO),
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
        lineas.append(Paragraph(f"NIT / RUC: {_esc(p['id_fiscal'])}", e["chico"]))
    lineas.append(Paragraph(_esc(p.get("direccion")) + (f" · {_esc(p['pais'])}" if p.get("pais") else ""), e["chico"]))
    if p.get("puerto"):
        lineas.append(Paragraph(f"Puerto de llegada: {_esc(p.get('puerto_nombre') or p['puerto'])}", e["chico"]))
    contacto = (p.get("contactos") or [None])[0]
    if contacto:
        lineas.append(Paragraph(f"Contacto: {_esc(contacto['nombre'])} · {_esc(contacto['correos'])}"
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
    t = Table([[_parte(e, "EXPORTADOR / VENDEDOR", exportador), _parte(e, "IMPORTADOR / FACTURAR A", d["importador"]),
                _parte(e, "CONSIGNATARIO / NOTIFY PARTY", d["consignatario"])]], colWidths=[ancho / 3] * 3)
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
    estilo = [("LINEBELOW", (0, 0), (-1, 0), 0.8, ACENTO), ("BACKGROUND", (0, 0), (-1, 0), FONDO),
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
                                                Paragraph("Nombre, cargo y firma del exportador", e["chico"])]]],
              colWidths=[ancho * 0.6, ancho * 0.4])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return KeepTogether([Spacer(1, 8), t])


# ---- Factura comercial -----------------------------------------------------------
def pdf_factura(d: dict) -> bytes:
    e = _estilos()
    ancho = letter[0] - 28 * mm
    tr = d["transporte"] or {}
    h = [
        _cabecera(e, d, ancho, "FACTURA COMERCIAL", "Commercial invoice", [
            ("N.º", d["numero"]), ("Fecha", _fecha(d["fecha"])), ("OC", ", ".join(d["ocs"])),
            ("Estado", "Oficial" if d["oficial"] else "Borrador")]),
        Spacer(1, 6), _bloque_partes(e, d, ancho), Spacer(1, 5),
        _rejilla(e, [
            ("Incoterm", d["incoterm"]), ("Moneda", d["moneda"]), ("Condiciones de pago", d["condiciones"]),
            ("Medio de transporte", tr.get("modo")),
            ("País de origen", d["pais_origen"]), ("País de procedencia", d["pais_procedencia"]),
            ("País de destino", d["pais_destino"]), ("Centro de destino",
                                                     f"{d['destino']['codigo']} · {d['destino']['nombre'] or ''}"
                                                     if d.get("destino") else None),
            ("Puerto de embarque", tr.get("puerto_origen") or d["puerto_embarque"]),
            ("Puerto de destino", tr.get("puerto_destino") or d["consignatario"].get("puerto_nombre")),
            ("Transportista", tr.get("transportista")), ("BL / AWB / CP", tr.get("documento")),
        ], ancho),
        Spacer(1, 7),
    ]
    filas = []
    for l in d["lineas"]:
        desc = f"<b>{_esc(l['marca'])} {_esc(l['estilo'])}</b> · {_esc(l['color'])} · talla {_esc(l['talla'])}<br/>" \
               f"<font color='#5b6475'>{_esc(l['descripcion'])}</font>"
        if l["prepack"]:
            desc += f"<br/><font color='#5b3fd1'>Prepack {_esc(l['prepack'])}</font>"
        filas.append([f"{l['oc']}/{l['posicion']}", l["sku"], Paragraph(desc, e["celda"]), l["partida"], l["origen"],
                      _num(l["cantidad"]), l["unidad"], _num(l["precio"], 2), _num(l["total"], 2)])
    t = d["totales"]
    h.append(_tabla(e, [("OC / pos.", 1.75, False), ("Código", 1.45, False), ("Descripción comercial", 4.0, False),
                        ("Partida SAC", 1.2, False), ("Origen", 0.7, False), ("Cantidad", 0.9, True),
                        ("UM", 0.5, False), ("Precio unit.", 1.1, True), ("Total", 1.3, True)],
                    filas, ancho, pie=["", "", f"{len(d['lineas'])} líneas", "", "", _num(sum(l['cantidad'] for l in d['lineas'])),
                                       "", "Total", f"{d['moneda']} {_num(t['importe'], 2)}"]))
    resumen = _rejilla(e, [
        ("Cantidad total", _por_unidad_txt(t["por_unidad"])), ("Bultos", f"{_num(t['bultos'])} cajas"
                                                                + (f" en {t['pallets']} pallets" if t["pallets"] else "")),
        ("Peso neto", f"{_num(t['peso_neto'], 2)} kg"), ("Peso bruto", f"{_num(t['peso_bruto'], 2)} kg"),
        ("Volumen", f"{_num(t['cbm'], 3)} m³"), ("Packing lists", ", ".join(d["pls"]) or "—"),
        ("Valor total " + (d["incoterm"] or ""), f"{d['moneda']} {_num(t['importe'], 2)}"),
        ("Contenedores / guías", ", ".join(tr.get("unidades", [])) or "—"),
    ], ancho)
    h += [Spacer(1, 6), KeepTogether([resumen, Spacer(1, 4),
                                      Paragraph(f"<b>SON:</b> {_esc(d['total_letras'])}", e["base"])])]
    if d.get("observaciones"):
        h += [Spacer(1, 4), Paragraph(f"<b>Observaciones:</b> {_esc(d['observaciones'])}", e["chico"])]
    h.append(_firma(e, ancho, "Declaramos bajo juramento que la información de esta factura es verdadera y correcta, "
                               "que el valor corresponde al precio realmente pagado o por pagar por las mercancías y "
                               "que el origen declarado es el correcto."))
    return _construir(h, letter, f"Factura comercial {d['numero']} · {d['exportador']['nombre']}", not d["oficial"])


# ---- Packing list ----------------------------------------------------------------
def pdf_pl(d: dict) -> bytes:
    e = _estilos()
    tam = landscape(letter)
    ancho = tam[0] - 28 * mm
    tr = d["transporte"] or {}
    tp = d["totales_pl"]
    h = [
        _cabecera(e, d, ancho, "LISTA DE EMPAQUE", "Packing list", [
            ("N.º", f"{d['numero']} · {d['numero_pl']}"), ("Fecha", _fecha(d["fecha"])),
            ("Factura", d["numero"]), ("Estado", "Oficial" if d["oficial"] else "Borrador")]),
        Spacer(1, 6), _bloque_partes(e, d, ancho), Spacer(1, 5),
        _rejilla(e, [
            ("OC", ", ".join(d["ocs"])), ("Medio de transporte", tr.get("modo")),
            ("Transportista", tr.get("transportista")), ("BL / AWB / CP", tr.get("documento")),
            ("Contenedor / guía", ", ".join(tr.get("unidades", [])) or "—"),
            ("Puerto de embarque", tr.get("puerto_origen") or d["puerto_embarque"]),
            ("Puerto de destino", tr.get("puerto_destino")), ("País de origen", d["pais_origen"]),
            ("País de destino", d["pais_destino"]), ("ETD / ETA", f"{_fecha(tr.get('etd'))} / {_fecha(tr.get('eta'))}"),
        ], ancho, columnas=5),
        Spacer(1, 7),
    ]
    filas = []
    for g in d["grupos"]:
        for i, it in enumerate(g["items"]):
            primera = i == 0
            filas.append([
                g["rango"] if primera else "", _num(g["num_cajas"]) if primera else "",
                f"{it['oc']}/{it['posicion']}", it["sku"], f"{it['marca'] or ''} {it['estilo']} · {it['color']}",
                it["talla"], _num(it["por_caja"]), _num(it["total"]), it["unidad"],
                g["medidas"] if primera else "", _num(g["neto_caja"], 2) if primera else "",
                _num(g["bruto_caja"], 2) if primera else "", _num(g["neto_total"], 2) if primera else "",
                _num(g["bruto_total"], 2) if primera else "", _num(g["cbm"], 3) if primera else "",
                (f"P{g['pallet']}" if g["pallet"] else "—") if primera else "", g["etiqueta"] if primera else "",
            ])
    h.append(_tabla(e, [
        ("Cajas", 0.8, False), ("N.º", 0.5, True), ("OC / pos.", 1.2, False), ("Código", 1.3, False),
        ("Marca · estilo · color", 2.3, False), ("Talla", 0.55, False), ("Por caja", 0.7, True), ("Total", 0.7, True),
        ("UM", 0.45, False), ("Medidas cm", 1.2, False), ("Neto caja", 0.8, True), ("Bruto caja", 0.8, True),
        ("Neto total", 0.8, True), ("Bruto total", 0.8, True), ("m³", 0.65, True), ("Pallet", 0.5, False),
        ("Etiqueta", 0.85, False)],
        filas, ancho, pie=["Total", _num(d["total_cajas"]), "", "", "", "", "", "", "", "", "", "",
                           _num(tp["peso_neto"], 2), _num(tp["peso_bruto"], 2), _num(tp["cbm"], 3), "", ""]))
    if d["pallets"]:
        h += [Spacer(1, 6), Paragraph("PALLETS", e["etiqueta"]),
              _tabla(e, [("Pallet", 1, False), ("Cajas", 1, True), ("Medidas cm", 2, False), ("Tara kg", 1, True),
                         ("m³", 1, True)],
                     [[f"P{p['numero']}", _num(p["cajas"]), p["medidas"], _num(p["tara"], 1), _num(p["cbm"], 3)]
                      for p in d["pallets"]], ancho * 0.5)]
    if d["sin_caja"]:
        h += [Spacer(1, 6), Paragraph("PENDIENTE DE EMPACAR", e["etiqueta"]),
              _tabla(e, [("OC", 1, False), ("Código", 1.4, False), ("Estilo", 1.4, False), ("Talla", 0.6, False),
                         ("Cantidad", 0.8, True), ("UM", 0.5, False)],
                     [[x["oc"], x["sku"], x["estilo"], x["talla"], _num(x["cantidad"]), x["unidad"]] for x in d["sin_caja"]],
                     ancho * 0.6)]
    consig = d["consignatario"]
    marcas = (f"<b>{_esc(consig.get('nombre'))}</b><br/>{_esc(consig.get('direccion'))}<br/>"
              f"OC {_esc(', '.join(d['ocs']))} · Factura {_esc(d['numero'])}<br/>Caja N.º __ de {d['total_cajas']} · "
              f"Hecho en {_esc(d['pais_origen'])}")
    resumen = _rejilla(e, [
        ("Total de bultos", f"{_num(d['total_cajas'])} cajas" + (f" en {len(d['pallets'])} pallets" if d["pallets"] else "")),
        ("Cantidad", tp["por_unidad_txt"]), ("Peso neto", f"{_num(tp['peso_neto'], 2)} kg"),
        ("Peso bruto", f"{_num(tp['peso_bruto'], 2)} kg"), ("Volumen", f"{_num(tp['cbm'], 3)} m³"),
    ], ancho, columnas=5)
    marca_t = Table([[Paragraph("MARCAS DE EMBARQUE (SHIPPING MARKS)", e["etiqueta"])], [Paragraph(marcas, e["base"])]],
                    colWidths=[ancho * 0.5], hAlign="LEFT")
    marca_t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, TINTA), ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
    h += [Spacer(1, 7), KeepTogether([resumen, Spacer(1, 4),
                                      Paragraph(f"<b>TOTAL DE BULTOS:</b> {_esc(d['total_bultos_letras'])}", e["base"]),
                                      Spacer(1, 6), marca_t])]
    h.append(_firma(e, ancho, "Declaramos que el contenido, la numeración, las medidas y los pesos de los bultos "
                               "corresponden a la mercancía despachada."))
    return _construir(h, tam, f"Lista de empaque {d['numero']} {d['numero_pl']} · {d['exportador']['nombre']}",
                      not d["oficial"])


# ---- Reportes ----------------------------------------------------------------------
def pdf_reporte(titulo: str, subtitulo: str, filtros: str, indicadores: list[tuple[str, str]],
                columnas: list[tuple[str, float, bool]], filas: list[list]) -> bytes:
    e = _estilos()
    tam = landscape(letter)
    ancho = tam[0] - 28 * mm
    cab = Table([[[Paragraph(titulo, e["titulo"]), Paragraph(subtitulo, e["chico"])],
                  Paragraph(f"Generado el {datetime.now():%d/%m/%Y %H:%M}<br/>{_esc(filtros) if filtros else 'Sin filtros'}",
                            ParagraphStyle("f", parent=e["chico"], alignment=TA_RIGHT))]],
                colWidths=[ancho * 0.6, ancho * 0.4])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, ACENTO),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    h = [cab, Spacer(1, 6)]
    if indicadores:
        h += [_rejilla(e, indicadores, ancho, columnas=min(len(indicadores), 5)), Spacer(1, 7)]
    h.append(_tabla(e, columnas, filas, ancho))
    return _construir(h, tam, titulo, False)
