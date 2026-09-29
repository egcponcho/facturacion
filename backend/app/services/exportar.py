import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .cantidades import cbm_caja, cubierto, nombre_factura, numeracion, totales_pl

_NEGRITA = Font(bold=True)
_ENCABEZADO = PatternFill("solid", fgColor="E8ECEF")


def _encabezados(ws, fila: int, titulos: list[str]) -> None:
    for i, t in enumerate(titulos, start=1):
        c = ws.cell(row=fila, column=i, value=t)
        c.font = _NEGRITA
        c.fill = _ENCABEZADO
        c.alignment = Alignment(wrap_text=True, vertical="center")


def _texto(ws, fila: int, columnas: list[int]) -> None:
    """Códigos como texto para que Excel no borre ceros iniciales."""
    for col in columnas:
        ws.cell(row=fila, column=col).number_format = "@"


def _anchos(ws, anchos: list[int]) -> None:
    for i, a in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = a


def _partes(ws, fila: int, p: dict | None) -> int:
    """Facturar a (sociedad) y notify party (centro) con sus contactos."""
    if not p:
        return fila
    for titulo, d in (("Facturar a", p["facturar_a"]), ("Notify party", p["notify"])):
        contactos = "; ".join(f"{c['nombre']} ({c['correos']}{', ' + c['telefono'] if c.get('telefono') else ''})"
                              for c in d.get("contactos", []))
        texto = " · ".join(x for x in (
            f"{d.get('codigo') or ''} {d.get('razon_social') or d.get('nombre') or ''}".strip(),
            d.get("id_fiscal"), d.get("direccion"), d.get("correos"), contactos) if x)
        ws.cell(row=fila, column=1, value=f"{titulo}: {texto}")
        fila += 1
    if p.get("destino"):
        ws.cell(row=fila, column=1, value=f"Destino final: {p['destino']['codigo']} {p['destino']['nombre'] or ''} "
                                          f"({p['destino']['pais'] or ''})")
        fila += 1
    return fila


def exportar_pl(pl, partes: dict | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = pl.numero
    f = pl.factura
    titulo = f"Packing list {pl.numero}" + ("" if pl.estado == "FINALIZADO" else "  (BORRADOR, no oficial)")
    ws["A1"] = titulo
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Factura: {nombre_factura(f)}    Proveedor: {f.proveedor.nombre}"
    ws["A3"] = f"Estado: {pl.estado}" + (f"    Unidad: {pl.unidad.numero or pl.unidad.etiqueta}" if pl.unidad else "")
    inicio = _partes(ws, 4, partes) + 1
    titulos = ["Cajas", "N.º cajas", "OC", "Pos.", "Código SAP", "UPC", "Estilo", "Color", "Talla",
               "Cant./caja", "Cantidad", "Unidad", "Largo cm", "Ancho cm", "Alto cm",
               "CBM", "Neto/caja kg", "Bruto/caja kg", "Neto total kg", "Bruto total kg",
               "Etiqueta", "OCs en la caja", "Centro destino", "Pallet"]
    _encabezados(ws, inicio, titulos)
    fila = inicio + 1
    rangos = numeracion(pl)
    from .packing import etiqueta_caja

    for g in pl.grupos:
        d, h = rangos[g.id]
        cbm = cbm_caja(g)
        etiqueta = etiqueta_caja(g)
        for i, it in enumerate(g.items):
            fl = it.pl_linea.factura_linea
            primera = i == 0
            valores = [
                (f"{d}" if d == h else f"{d}-{h}") if primera else "",
                g.num_cajas if primera else None,
                fl.oc_numero, fl.posicion, fl.codigo_sap, fl.upc, fl.estilo, fl.color, fl.talla,
                it.cantidad_por_caja, it.cantidad_por_caja * g.num_cajas, fl.unidad,
                g.largo if primera else None, g.ancho if primera else None, g.alto if primera else None,
                round(cbm * g.num_cajas, 4) if (cbm and primera) else None,
                g.peso_neto_caja if primera else None, g.peso_bruto_caja if primera else None,
                round(g.peso_neto_caja * g.num_cajas, 3) if (g.peso_neto_caja and primera) else None,
                round(g.peso_bruto_caja * g.num_cajas, 3) if (g.peso_bruto_caja and primera) else None,
                ("Estándar" if etiqueta["tipo"] == "ESTANDAR" else "Consolidada") if primera else None,
                ", ".join(etiqueta["ocs"]) if primera else None,
                etiqueta["centro_destino"] if primera else None,
                (g.pallet.numero if g.pallet else None) if primera else None,
            ]
            for col, v in enumerate(valores, start=1):
                ws.cell(row=fila, column=col, value=v)
            _texto(ws, fila, [3, 4, 5, 6])
            fila += 1

    pendientes = [pll for pll in pl.lineas if pll.cantidad - cubierto(pll) > 0]
    if pendientes:
        fila += 1
        ws.cell(row=fila, column=1, value="Sin caja").font = _NEGRITA
        fila += 1
        for pll in pendientes:
            fl = pll.factura_linea
            valores = ["", None, fl.oc_numero, fl.posicion, fl.codigo_sap, fl.upc, fl.estilo, fl.color,
                       fl.talla, None, pll.cantidad - cubierto(pll), fl.unidad]
            for col, v in enumerate(valores, start=1):
                ws.cell(row=fila, column=col, value=v)
            _texto(ws, fila, [3, 4, 5, 6])
            fila += 1

    t = totales_pl(pl)
    fila += 1
    ws.cell(row=fila, column=1, value="Totales").font = _NEGRITA
    ws.cell(row=fila, column=2, value=t["cajas"])
    cantidades = ", ".join(f"{v['cantidad']} {k}" for k, v in t["por_unidad"].items())
    ws.cell(row=fila, column=11, value=cantidades)
    ws.cell(row=fila, column=16, value=t["cbm"])
    ws.cell(row=fila, column=19, value=t["peso_neto"])
    ws.cell(row=fila, column=20, value=t["peso_bruto"])
    if pl.pallets:
        fila += 2
        ws.cell(row=fila, column=1, value="Pallets").font = _NEGRITA
        _encabezados(ws, fila + 1, ["Pallet", "Cajas", "Largo cm", "Ancho cm", "Alto cm", "CBM", "Tara kg"])
        fila += 2
        for p in sorted(pl.pallets, key=lambda x: x.numero):
            cajas = sum(g.num_cajas for g in pl.grupos if g.pallet is p)
            for col, v in enumerate([p.numero, cajas, p.largo, p.ancho, p.alto,
                                     round(p.largo * p.ancho * p.alto / 1_000_000, 4), p.peso_tara], start=1):
                ws.cell(row=fila, column=col, value=v)
            fila += 1
    _anchos(ws, [9, 8, 12, 6, 20, 16, 14, 10, 7, 9, 9, 7, 9, 9, 9, 9, 11, 11, 12, 12, 12, 22, 10, 8])
    ws.freeze_panes = f"A{inicio + 1}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exportar_factura(f, partes: dict | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Factura"
    ws["A1"] = f"Factura {nombre_factura(f)}" + ("" if f.estado == "FINALIZADA" else "  (BORRADOR, no oficial)")
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Proveedor: {f.proveedor.nombre}    Fecha: {f.fecha or ''}    Moneda: {f.moneda}"
    ws["A3"] = f"Sociedad: {f.sociedad}    Centro: {f.centro or ''}    Incoterm: {f.incoterm or ''}"
    inicio = _partes(ws, 4, partes) + 1
    titulos = ["OC", "Pos.", "Código SAP", "UPC", "Estilo", "Color", "Talla", "Descripción comercial",
               "País origen", "Partida", "Cantidad", "Unidad", "Precio unitario", "Total", "Motivo de precio"]
    _encabezados(ws, inicio, titulos)
    fila = inicio + 1
    total = 0.0
    for l in f.lineas:
        importe = round(l.cantidad * l.precio_unitario, 2)
        total += importe
        valores = [l.oc_numero, l.posicion, l.codigo_sap, l.upc, l.estilo, l.color, l.talla,
                   l.descripcion_comercial, l.pais_origen, l.partida_arancelaria, l.cantidad, l.unidad,
                   l.precio_unitario, importe, l.motivo_precio]
        for col, v in enumerate(valores, start=1):
            ws.cell(row=fila, column=col, value=v)
        _texto(ws, fila, [1, 2, 3, 4, 10])
        ws.cell(row=fila, column=13).number_format = "#,##0.0000"
        ws.cell(row=fila, column=14).number_format = "#,##0.00"
        fila += 1
    fila += 1
    ws.cell(row=fila, column=13, value="Total").font = _NEGRITA
    c = ws.cell(row=fila, column=14, value=round(total, 2))
    c.font = _NEGRITA
    c.number_format = "#,##0.00"
    _anchos(ws, [12, 6, 20, 16, 14, 10, 7, 30, 8, 12, 10, 7, 12, 12, 30])
    ws.freeze_panes = f"A{inicio + 1}"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
