"""Factura comercial, packing list y reportes en Excel, con la misma estructura
que el PDF (documentos.py): cabecera, partes, condiciones, detalle, totales,
total en letras y declaración. Listos para imprimir en una página de ancho."""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .documentos import _fecha, _por_unidad_txt

ACENTO = "5B3FD1"
TENUE = "5B6475"
_FONDO = PatternFill("solid", fgColor="F3F1FB")
_FONDO_2 = PatternFill("solid", fgColor="F7F8FA")
_LINEA = Side(style="thin", color="D9DCE3")
_FUERTE = Side(style="medium", color=ACENTO)
_ARRIBA = Alignment(vertical="top", wrap_text=True)
_MONEDA = "#,##0.00"
_ENTERO = "#,##0"


class _Hoja:
    """Escribe de arriba abajo sobre una hoja de `columnas` columnas."""

    def __init__(self, ws, anchos: list[float]):
        self.ws = ws
        self.n = len(anchos)
        self.fila = 1
        for i, a in enumerate(anchos, start=1):
            ws.column_dimensions[get_column_letter(i)].width = a
        ws.sheet_view.showGridLines = False

    def celda(self, fila, col, valor=None, negrita=False, color=None, tam=None, formato=None, fondo=None,
              alinear=None):
        c = self.ws.cell(row=fila, column=col, value=valor)
        c.font = Font(bold=negrita, color=color, size=tam or 9)
        c.alignment = alinear or _ARRIBA
        if formato:
            c.number_format = formato
        if fondo:
            c.fill = fondo
        return c

    def unir(self, fila, c1, c2, filas=1):
        if c2 > c1 or filas > 1:
            self.ws.merge_cells(start_row=fila, start_column=c1, end_row=fila + filas - 1, end_column=c2)

    def marco(self, f1, f2, c1, c2, fondo=None, borde=_LINEA):
        for r in range(f1, f2 + 1):
            for c in range(c1, c2 + 1):
                x = self.ws.cell(row=r, column=c)
                x.border = Border(left=borde if c == c1 else None, right=borde if c == c2 else None,
                                  top=borde if r == f1 else None, bottom=borde if r == f2 else None)
                if fondo:
                    x.fill = fondo

    def espacio(self, n=1):
        self.fila += n

    def cabecera(self, d: dict, titulo: str, subtitulo: str, datos: list[tuple[str, str]]):
        """Exportador a la izquierda; título, número y fecha a la derecha."""
        exp = d["exportador"]
        corte = max(2, self.n - 3)
        self.celda(1, 1, exp["nombre"], negrita=True, tam=15)
        self.unir(1, 1, corte)
        self.celda(2, 1, " · ".join(x for x in (exp.get("direccion"), exp.get("pais")) if x), color=TENUE, tam=8)
        self.unir(2, 1, corte)
        self.celda(3, 1, " · ".join(x for x in (f"ID fiscal: {exp['id_fiscal']}" if exp.get("id_fiscal") else None,
                                                  exp.get("correos"), exp.get("telefono")) if x), color=TENUE, tam=8)
        self.unir(3, 1, corte)
        self.celda(1, corte + 1, titulo, negrita=True, color=ACENTO, tam=13)
        self.unir(1, corte + 1, self.n)
        self.celda(2, corte + 1, subtitulo, color=TENUE, tam=8)
        self.unir(2, corte + 1, self.n)
        fila = 3
        for k, v in datos:
            self.celda(fila, corte + 1, k, color=TENUE, tam=8)
            self.celda(fila, corte + 2, v, negrita=True)
            self.unir(fila, corte + 2, self.n)
            fila += 1
        self.marco(1, fila - 1, corte + 1, self.n, _FONDO, Side(style="thin", color=ACENTO))
        self.fila = fila + 1

    def partes(self, d: dict):
        """Exportador, importador y consignatario en tres bloques."""
        exp = d["exportador"]
        bloques = [
            ("EXPORTADOR / VENDEDOR", [f"{exp['codigo']} · {exp['nombre']}", f"NIT / RUC: {exp['id_fiscal'] or '—'}",
                                       " · ".join(x for x in (exp.get("direccion"), exp.get("pais")) if x),
                                       " · ".join(x for x in (exp.get("contacto"), exp.get("correos"),
                                                               exp.get("telefono")) if x)]),
            ("IMPORTADOR / FACTURAR A", _lineas_parte(d["importador"])),
            ("CONSIGNATARIO / NOTIFY PARTY", _lineas_parte(d["consignatario"])),
        ]
        tercio = self.n // 3
        rangos = [(1, tercio), (tercio + 1, 2 * tercio), (2 * tercio + 1, self.n)]
        f = self.fila
        alto = max(len(b[1]) for b in bloques)
        for (titulo, lineas), (c1, c2) in zip(bloques, rangos):
            self.celda(f, c1, titulo, negrita=True, color=ACENTO, tam=7)
            self.unir(f, c1, c2)
            for i in range(alto):
                v = lineas[i] if i < len(lineas) else None
                self.celda(f + 1 + i, c1, v, negrita=i == 0, color=None if i == 0 else TENUE, tam=9 if i == 0 else 8)
                self.unir(f + 1 + i, c1, c2)
            self.marco(f, f + alto, c1, c2)
        for i in range(alto):
            largo = max(len(b[1][i]) if i < len(b[1]) else 0 for b in bloques)
            if largo > 38:
                self.ws.row_dimensions[f + 1 + i].height = 24
        self.fila = f + alto + 2

    def rejilla(self, pares: list[tuple[str, str]], columnas: int = 4):
        """Pares etiqueta/valor en `columnas` bloques por fila."""
        ancho = self.n // columnas
        for i in range(0, len(pares), columnas):
            f = self.fila
            for j, (k, v) in enumerate(pares[i:i + columnas]):
                c1 = 1 + j * ancho
                c2 = self.n if j == columnas - 1 else c1 + ancho - 1
                self.celda(f, c1, k.upper(), negrita=True, color=ACENTO, tam=7)
                self.unir(f, c1, c2)
                self.celda(f + 1, c1, v if v not in (None, "") else "—")
                self.unir(f + 1, c1, c2)
                self.marco(f, f + 1, c1, c2, _FONDO_2)
            self.fila += 2
        self.fila += 1

    def tabla(self, encabezados: list[tuple[str, str | None]], filas: list[list], pie: list | None = None,
              texto: set[int] = frozenset()):
        """Detalle con encabezado fijo, filas cebra y fila de totales.
        `encabezados`: (título, formato numérico o None). `texto`: columnas
        (desde 0) que van como texto para no perder ceros a la izquierda."""
        f = self.fila
        for i, (t, fmt) in enumerate(encabezados, start=1):
            c = self.celda(f, i, t, negrita=True, color=TENUE, tam=8, fondo=_FONDO,
                           alinear=Alignment(wrap_text=True, vertical="center",
                                             horizontal="right" if fmt else "left"))
            c.border = Border(bottom=_FUERTE)
        self.ws.row_dimensions[f].height = 26
        inicio = f + 1
        for n, valores in enumerate(filas):
            r = inicio + n
            for i, (v, (_, fmt)) in enumerate(zip(valores, encabezados), start=1):
                c = self.celda(r, i, v, formato=fmt if fmt else ("@" if (i - 1) in texto else None),
                               fondo=_FONDO_2 if n % 2 else None)
                c.border = Border(bottom=_LINEA)
        r = inicio + len(filas)
        if pie:
            for i, (v, (_, fmt)) in enumerate(zip(pie, encabezados), start=1):
                c = self.celda(r, i, v, negrita=True, formato=fmt, fondo=_FONDO)
                c.border = Border(top=Side(style="medium", color="1F2430"))
            r += 1
        self.fila = r + 1
        return f

    def parrafo(self, texto: str, negrita=False, color=None, tam=None, alto=None, hasta=None):
        self.celda(self.fila, 1, texto, negrita=negrita, color=color, tam=tam)
        self.unir(self.fila, 1, hasta or self.n)
        if alto:
            self.ws.row_dimensions[self.fila].height = alto
        self.fila += 1

    def firma(self, texto: str):
        self.espacio()
        mitad = max(2, int(self.n * 0.6))
        self.celda(self.fila, 1, texto, color=TENUE, tam=8)
        self.unir(self.fila, 1, mitad, filas=2)
        self.ws.row_dimensions[self.fila].height = 24
        for col in range(mitad + 2, self.n + 1):
            self.ws.cell(row=self.fila + 1, column=col).border = Border(bottom=Side(style="thin", color="1F2430"))
        self.celda(self.fila + 2, mitad + 2, "Nombre, cargo y firma del exportador", color=TENUE, tam=8)
        self.unir(self.fila + 2, mitad + 2, self.n)
        self.fila += 4

    def imprimir(self, titulo_filas: int | None, horizontal: bool, pie: str, borrador: bool):
        ws = self.ws
        ws.page_setup.orientation = "landscape" if horizontal else "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.horizontalCentered = True
        ws.page_margins.left = ws.page_margins.right = 0.4
        ws.page_margins.top = 0.5
        ws.page_margins.bottom = 0.6
        if titulo_filas:
            ws.print_title_rows = f"{titulo_filas}:{titulo_filas}"
        ws.oddFooter.left.text = pie + ("  ·  BORRADOR, NO OFICIAL" if borrador else "")
        ws.oddFooter.left.size = 7
        ws.oddFooter.right.text = "Página &P de &N"
        ws.oddFooter.right.size = 7


def _lineas_parte(p: dict | None) -> list[str]:
    if not p:
        return ["—"]
    lineas = [f"{p.get('codigo') or ''} · {p.get('razon_social') or p.get('nombre') or ''}"]
    if p.get("id_fiscal"):
        lineas.append(f"NIT / RUC: {p['id_fiscal']}")
    lineas.append(" · ".join(x for x in (p.get("direccion"), p.get("pais")) if x) or "—")
    if p.get("puerto"):
        lineas.append(f"Puerto de llegada: {p.get('puerto_nombre') or p['puerto']}")
    c = (p.get("contactos") or [None])[0]
    if c:
        lineas.append(" · ".join(x for x in (c.get("nombre"), c.get("correos"), c.get("telefono")) if x))
    elif p.get("correos"):
        lineas.append(p["correos"])
    return lineas


def _guardar(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _hoja_titulo(texto: str) -> str:
    for ch in "[]:*?/\\":
        texto = texto.replace(ch, "-")
    return texto[:31] or "Hoja"


def exportar_factura(d: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = _hoja_titulo(f"Factura {d['numero']}")
    h = _Hoja(ws, [13, 7, 14, 15, 16, 10, 7, 30, 9, 11, 10, 7, 12, 14])
    tr = d["transporte"] or {}
    h.cabecera(d, "FACTURA COMERCIAL", "Commercial invoice", [
        ("N.º", d["numero"]), ("Fecha", _fecha(d["fecha"])), ("OC", ", ".join(d["ocs"])),
        ("Estado", "Oficial" if d["oficial"] else "Borrador")])
    h.partes(d)
    destino = d.get("destino")
    h.rejilla([
        ("Incoterm", d["incoterm"]), ("Moneda", d["moneda"]), ("Condiciones de pago", d["condiciones"]),
        ("Medio de transporte", tr.get("modo")),
        ("País de origen", d["pais_origen"]), ("País de procedencia", d["pais_procedencia"]),
        ("País de destino", d["pais_destino"]),
        ("Centro de destino", f"{destino['codigo']} · {destino['nombre'] or ''}" if destino else None),
        ("Puerto de embarque", tr.get("puerto_origen") or d["puerto_embarque"]),
        ("Puerto de destino", tr.get("puerto_destino") or d["consignatario"].get("puerto_nombre")),
        ("Transportista", tr.get("transportista")), ("BL / AWB / CP", tr.get("documento")),
    ])
    t = d["totales"]
    filas = [[l["oc"], l["posicion"], l["sku"], l["upc"], l["marca"], l["estilo"], l["talla"],
              f"{l['descripcion'] or ''} · {l['color'] or ''}" + (f" · prepack {l['prepack']}" if l["prepack"] else ""),
              l["origen"], l["partida"], l["cantidad"], l["unidad"], l["precio"], l["total"]] for l in d["lineas"]]
    fila_cab = h.tabla(
        [("OC", None), ("Pos.", None), ("Código", None), ("UPC", None), ("Marca", None), ("Estilo", None),
         ("Talla", None), ("Descripción comercial · color", None), ("Origen", None), ("Partida SAC", None),
         ("Cantidad", _ENTERO), ("UM", None), ("Precio unit.", "#,##0.0000"), (f"Total {d['moneda']}", _MONEDA)],
        filas, pie=["Total", None, f"{len(filas)} líneas", None, None, None, None, None, None, None,
                    sum(l["cantidad"] for l in d["lineas"]), None, None, t["importe"]],
        texto={0, 1, 2, 3, 9})
    h.rejilla([
        ("Cantidad total", _por_unidad_txt(t["por_unidad"])),
        ("Bultos", f"{t['bultos']:,} cajas" + (f" en {t['pallets']} pallets" if t["pallets"] else "")),
        ("Peso neto", f"{t['peso_neto']:,.2f} kg"), ("Peso bruto", f"{t['peso_bruto']:,.2f} kg"),
        ("Volumen", f"{t['cbm']:,.3f} m³"), ("Packing lists", ", ".join(d["pls"]) or "—"),
        ("Valor total " + (d["incoterm"] or ""), f"{d['moneda']} {t['importe']:,.2f}"),
        ("Contenedores / guías", ", ".join(tr.get("unidades", [])) or "—"),
    ])
    h.parrafo(f"SON: {d['total_letras']}", negrita=True)
    if d.get("observaciones"):
        h.parrafo(f"Observaciones: {d['observaciones']}", color=TENUE, tam=8)
    h.firma("Declaramos bajo juramento que la información de esta factura es verdadera y correcta, que el valor "
            "corresponde al precio realmente pagado o por pagar por las mercancías y que el origen declarado es el "
            "correcto.")
    h.imprimir(fila_cab, False, f"Factura comercial {d['numero']} · {d['exportador']['nombre']}", not d["oficial"])
    ws.freeze_panes = None
    return _guardar(wb)


def exportar_pl(d: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = _hoja_titulo(f"{d['numero']} {d['numero_pl']}")
    h = _Hoja(ws, [8, 6, 12, 6, 14, 15, 14, 10, 6, 8, 8, 6, 8, 8, 8, 9, 9, 10, 10, 8, 7, 11, 16])
    tr = d["transporte"] or {}
    tp = d["totales_pl"]
    h.cabecera(d, "LISTA DE EMPAQUE", "Packing list", [
        ("N.º", f"{d['numero']} · {d['numero_pl']}"), ("Fecha", _fecha(d["fecha"])), ("Factura", d["numero"]),
        ("Estado", "Oficial" if d["oficial"] else "Borrador")])
    h.partes(d)
    h.rejilla([
        ("OC", ", ".join(d["ocs"])), ("Medio de transporte", tr.get("modo")),
        ("Transportista", tr.get("transportista")), ("BL / AWB / CP", tr.get("documento")),
        ("Contenedor / guía", ", ".join(tr.get("unidades", [])) or "—"),
        ("Puerto de embarque", tr.get("puerto_origen") or d["puerto_embarque"]),
        ("Puerto de destino", tr.get("puerto_destino")), ("País de origen", d["pais_origen"]),
        ("País de destino", d["pais_destino"]), ("ETD / ETA", f"{_fecha(tr.get('etd'))} / {_fecha(tr.get('eta'))}"),
    ], columnas=5)
    filas = []
    for g in d["grupos"]:
        for i, it in enumerate(g["items"]):
            p = i == 0
            filas.append([
                g["rango"] if p else None, g["num_cajas"] if p else None, it["oc"], it["posicion"], it["sku"],
                it["upc"], f"{it['marca'] or ''} {it['estilo']}".strip(), it["color"], it["talla"], it["por_caja"],
                it["total"], it["unidad"], g["largo"] if p else None, g["ancho"] if p else None,
                g["alto"] if p else None, g["neto_caja"] if p else None, g["bruto_caja"] if p else None,
                g["neto_total"] if p else None, g["bruto_total"] if p else None, g["cbm"] if p else None,
                (g["pallet"] if g["pallet"] else None) if p else None, g["etiqueta"] if p else None,
                (", ".join(g["ocs"]) + (f" → {g['centro_destino']}" if g["centro_destino"] else "")) if p else None,
            ])
    fila_cab = h.tabla(
        [("Cajas", None), ("N.º", _ENTERO), ("OC", None), ("Pos.", None), ("Código", None), ("UPC", None),
         ("Marca · estilo", None), ("Color", None), ("Talla", None), ("Por caja", _ENTERO), ("Total", _ENTERO),
         ("UM", None), ("Largo cm", "0.0"), ("Ancho cm", "0.0"), ("Alto cm", "0.0"), ("Neto caja kg", "0.00"),
         ("Bruto caja kg", "0.00"), ("Neto total kg", _MONEDA), ("Bruto total kg", _MONEDA), ("m³", "0.000"),
         ("Pallet", None), ("Etiqueta", None), ("OCs de la caja", None)],
        filas, pie=["Total", d["total_cajas"], None, None, None, None, None, None, None, None,
                    sum(it["total"] for g in d["grupos"] for it in g["items"]), None, None, None, None, None, None,
                    tp["peso_neto"], tp["peso_bruto"], tp["cbm"], None, None, None],
        texto={0, 2, 3, 4, 5})
    if d["pallets"]:
        h.parrafo("PALLETS", negrita=True, color=ACENTO, tam=8)
        h.tabla([("Pallet", None), ("Cajas", _ENTERO), ("Medidas cm", None), ("Tara kg", "0.0"), ("m³", "0.000")],
                [[f"P{p['numero']}", p["cajas"], p["medidas"], p["tara"], p["cbm"]] for p in d["pallets"]])
    if d["sin_caja"]:
        h.parrafo("PENDIENTE DE EMPACAR", negrita=True, color=ACENTO, tam=8)
        h.tabla([("OC", None), ("Código", None), ("Estilo", None), ("Talla", None), ("Cantidad", _ENTERO),
                 ("UM", None)],
                [[x["oc"], x["sku"], x["estilo"], x["talla"], x["cantidad"], x["unidad"]] for x in d["sin_caja"]],
                texto={0, 1})
    h.rejilla([
        ("Total de bultos", f"{d['total_cajas']:,} cajas" + (f" en {len(d['pallets'])} pallets" if d["pallets"] else "")),
        ("Cantidad", tp["por_unidad_txt"]), ("Peso neto", f"{tp['peso_neto']:,.2f} kg"),
        ("Peso bruto", f"{tp['peso_bruto']:,.2f} kg"), ("Volumen", f"{tp['cbm']:,.3f} m³"),
    ], columnas=5)
    h.parrafo(f"TOTAL DE BULTOS: {d['total_bultos_letras']}", negrita=True)
    consig = d["consignatario"]
    h.espacio()
    mitad = h.n // 2
    inicio = h.fila
    h.parrafo("MARCAS DE EMBARQUE (SHIPPING MARKS)", negrita=True, color=ACENTO, tam=7, hasta=mitad)
    for i, linea in enumerate((consig.get("nombre"), consig.get("direccion"),
                               f"OC {', '.join(d['ocs'])} · Factura {d['numero']}",
                               f"Caja N.º __ de {d['total_cajas']} · Hecho en {d['pais_origen']}")):
        h.parrafo(linea, negrita=i == 0, hasta=mitad)
    h.marco(inicio, h.fila - 1, 1, mitad)
    h.firma("Declaramos que el contenido, la numeración, las medidas y los pesos de los bultos corresponden a la "
            "mercancía despachada.")
    h.imprimir(fila_cab, True, f"Lista de empaque {d['numero']} {d['numero_pl']} · {d['exportador']['nombre']}",
               not d["oficial"])
    return _guardar(wb)


def exportar_reporte(titulo: str, subtitulo: str, filtros: str, indicadores: list[tuple[str, str]],
                     columnas: list[tuple[str, float, bool]], filas: list[list], hojas: list[dict] | None = None) -> bytes:
    """Reporte tabular: título, filtros aplicados, indicadores y detalle con
    filtros de Excel. `hojas` agrega hojas de detalle adicionales con
    {"titulo", "columnas", "filas"}."""
    wb = Workbook()
    ws = wb.active
    ws.title = _hoja_titulo(titulo)
    _hoja_reporte(ws, titulo, subtitulo, filtros, indicadores, columnas, filas)
    for x in hojas or []:
        _hoja_reporte(wb.create_sheet(_hoja_titulo(x["titulo"])), x["titulo"], subtitulo, filtros, [],
                      x["columnas"], x["filas"])
    return _guardar(wb)


def _hoja_reporte(ws, titulo, subtitulo, filtros, indicadores, columnas, filas):
    h = _Hoja(ws, [max(8, min(40, w * 9)) for _, w, _ in columnas])
    h.celda(1, 1, titulo, negrita=True, tam=15)
    h.unir(1, 1, h.n)
    h.celda(2, 1, subtitulo, color=TENUE, tam=8)
    h.unir(2, 1, h.n)
    h.celda(3, 1, f"Generado el {datetime.now():%d/%m/%Y %H:%M} · {filtros or 'Sin filtros'}", color=TENUE, tam=8)
    h.unir(3, 1, h.n)
    for c in range(1, h.n + 1):
        ws.cell(row=3, column=c).border = Border(bottom=_FUERTE)
    h.fila = 5
    if indicadores:
        h.rejilla(indicadores, columnas=min(len(indicadores), max(1, h.n), 5))
    fmts = [(t, (_ENTERO if der else None)) for t, _, der in columnas]
    for i, (t, _, der) in enumerate(columnas):
        if der and any(isinstance(f[i], float) and not float(f[i]).is_integer() for f in filas):
            fmts[i] = (t, _MONEDA)
    fila_cab = h.tabla(fmts, filas, texto={i for i, (_, _, der) in enumerate(columnas) if not der})
    if filas:
        ws.auto_filter.ref = f"A{fila_cab}:{get_column_letter(h.n)}{fila_cab + len(filas)}"
    ws.freeze_panes = f"A{fila_cab + 1}"
    h.imprimir(fila_cab, True, titulo, False)
