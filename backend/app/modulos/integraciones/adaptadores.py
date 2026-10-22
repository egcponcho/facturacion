"""Adaptadores de formato: convierten el contenido de un sistema externo en
filas con sus nombres de campo originales, y filas internas en contenido.

Contrato (cada adaptador):
- `codigo`, `nombre`: cómo se elige en la integración.
- `parametros`: {nombre: (tipo, valor por defecto, ayuda)} que acepta.
- `leer(contenido, archivo, parametros) -> list[dict]`: una fila por registro,
  {nombre del campo externo: texto}, más `_fila` (número de fila de origen).
- `escribir(filas, columnas, parametros) -> (bytes, tipo MIME, extensión)`.

Los nombres de campo se conservan tal como vienen: el mapeo de la integración
los traduce a los campos internos (servicio.traducir_entrada).
"""
import csv
import io
import json
from datetime import date, datetime

from app.core.archivos import abrir_libro
from app.core.errores import ErrorNegocio


def _texto(v) -> str:
    """Un valor del archivo como texto: enteros sin «.0», fechas en ISO."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v).strip()


class ArchivoTabular:
    """CSV o Excel (.xlsx) con una fila de encabezados."""

    codigo = "archivo_tabular"
    nombre = "Spreadsheet file (CSV or Excel)"
    parametros = {
        "fila_encabezado": ("entero", 1, "Row of the column headers (1 = first)."),
        "delimitador": ("texto", "", "CSV separator; empty: detected (comma or semicolon)."),
        "formato_salida": ("opcion:csv,xlsx", "csv", "Format of the files the system sends."),
    }

    def leer(self, contenido: bytes, archivo: str, parametros: dict) -> list[dict]:
        inicio = max(int(parametros.get("fila_encabezado") or 1), 1) - 1
        if archivo.lower().endswith((".xlsx", ".xlsm")):
            ws = abrir_libro(contenido, read_only=True, data_only=True).active
            filas = [[_texto(v) for v in f] for f in list(ws.iter_rows(values_only=True))[inicio:]]
        else:
            texto = contenido.decode("utf-8-sig", errors="replace")
            muestra = texto[:2000]
            delim = parametros.get("delimitador") or (";" if muestra.count(";") > muestra.count(",") else ",")
            filas = [[v.strip() for v in f] for f in list(csv.reader(io.StringIO(texto), delimiter=delim))[inicio:]]
        if not filas:
            return []
        encabezados = [h.strip() for h in filas[0]]
        res = []
        for n, fila in enumerate(filas[1:], start=inicio + 2):
            if not any(fila):
                continue
            res.append({**{h: (fila[i] if i < len(fila) else "") for i, h in enumerate(encabezados) if h}, "_fila": n})
        return res

    def escribir(self, filas: list[dict], columnas: list[str], parametros: dict) -> tuple[bytes, str, str]:
        if parametros.get("formato_salida") == "xlsx":
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.append(columnas)
            for f in filas:
                ws.append([f.get(c) for c in columnas])
            buf = io.BytesIO()
            wb.save(buf)
            return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=parametros.get("delimitador") or ",")
        w.writerow(columnas)
        for f in filas:
            w.writerow(["" if f.get(c) is None else f.get(c) for c in columnas])
        return buf.getvalue().encode("utf-8-sig"), "text/csv", "csv"


class Json:
    """JSON: una lista de objetos o un objeto con la lista en `filas`, `items` o `data`."""

    codigo = "json"
    nombre = "JSON"
    parametros = {"raiz": ("texto", "", "Key of the list inside the JSON object; empty: filas, items or data.")}

    def leer(self, contenido: bytes, archivo: str, parametros: dict) -> list[dict]:
        try:
            datos = json.loads(contenido.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ErrorNegocio(f"The JSON could not be read: {e}.", 422, "formato_invalido") from e
        if isinstance(datos, dict):
            raiz = parametros.get("raiz")
            claves = [raiz] if raiz else ["filas", "items", "data"]
            datos = next((datos[k] for k in claves if isinstance(datos.get(k), list)), None)
        if not isinstance(datos, list) or not all(isinstance(x, dict) for x in datos):
            raise ErrorNegocio("The JSON must be a list of objects (or an object with that list).", 422, "formato_invalido")
        return [{**{k: _texto(v) for k, v in x.items()}, "_fila": i} for i, x in enumerate(datos, start=1)]

    def escribir(self, filas: list[dict], columnas: list[str], parametros: dict) -> tuple[bytes, str, str]:
        cuerpo = {parametros.get("raiz") or "filas": [{c: f.get(c) for c in columnas} for f in filas]}
        return json.dumps(cuerpo, ensure_ascii=False, default=str, indent=1).encode("utf-8"), "application/json", "json"


REGISTRO = {a.codigo: a for a in (ArchivoTabular(), Json())}


def de(codigo: str):
    a = REGISTRO.get(codigo)
    if a is None:
        raise ErrorNegocio(f"Unknown adapter: {codigo}.", 422, "validacion")
    return a


def validar_parametros(codigo: str, parametros: dict | None) -> dict:
    """Solo los parámetros que el adaptador declara, con su tipo; el resto se descarta."""
    a = de(codigo)
    res = {}
    for nombre, (tipo, defecto, _) in a.parametros.items():
        v = (parametros or {}).get(nombre, defecto)
        if tipo == "entero":
            try:
                v = int(v)
            except (TypeError, ValueError) as e:
                raise ErrorNegocio(f"{nombre} must be a whole number.", 422, "validacion") from e
            if v < 1:
                raise ErrorNegocio(f"{nombre} must be 1 or more.", 422, "validacion")
        elif tipo.startswith("opcion:"):
            opciones = tipo.split(":", 1)[1].split(",")
            if v not in opciones:
                raise ErrorNegocio(f"{nombre} must be one of {', '.join(opciones)}.", 422, "validacion")
        else:
            v = str(v or "")[:40]
        res[nombre] = v
    return res


def catalogo() -> list[dict]:
    return [{"codigo": a.codigo, "nombre": a.nombre,
             "parametros": [{"nombre": n, "tipo": t, "defecto": d, "ayuda": ay} for n, (t, d, ay) in a.parametros.items()]}
            for a in REGISTRO.values()]
