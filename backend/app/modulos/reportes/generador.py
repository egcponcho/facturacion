"""Generador de reportes: valida la definición, arma la consulta con los campos
de la fuente, la ejecuta con el alcance de datos del usuario y exporta.

Una definición es:
    {"fuente": "ordenes",
     "columnas": ["numero", "proveedor", "valor"],            # reporte operativo (filas)
     "agrupar": ["proveedor"],                                # o analítico (agrupado)…
     "medidas": [{"campo": "*", "funcion": "contar"},          # …con sus medidas
                 {"campo": "valor", "funcion": "suma"}],
     "filtros": [{"campo": "estado", "op": "igual", "valor": "APROBADA"},
                 {"campo": "fecha_xf", "op": "ultimos_dias", "valor": 90}],
     "orden": {"campo": "valor", "dir": "desc"}}

Sin agrupación es un reporte operativo (una fila por registro, para el trabajo
del día); con agrupación es analítico (totales por grupo). Los dos se
calculan siempre en el momento: un reporte guardado no guarda datos.
"""
import csv
import io
import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Usuario
from app.modulos.acceso.permisos import tiene
from app.modulos.reportes.fuentes import FUENTES, Campo, Fuente, alcance, visible

OPERADORES = {
    "texto": ("contiene", "igual", "distinto", "empieza", "vacio", "no_vacio"),
    "estado": ("igual", "distinto", "en", "vacio", "no_vacio"),
    "numero": ("igual", "distinto", "mayor", "menor", "entre", "vacio", "no_vacio"),
    "moneda": ("igual", "distinto", "mayor", "menor", "entre", "vacio", "no_vacio"),
    "fecha": ("igual", "desde", "hasta", "entre", "ultimos_dias", "vacio", "no_vacio"),
}
FUNCIONES = {"contar": func.count, "suma": func.sum, "promedio": func.avg, "minimo": func.min, "maximo": func.max}
FUNCION_TXT = {"contar": "Count", "suma": "Sum", "promedio": "Average", "minimo": "Minimum", "maximo": "Maximum"}
OPERADOR_TXT = {"contiene": "contains", "igual": "is", "distinto": "is not", "empieza": "starts with", "vacio": "is empty",
                "no_vacio": "is not empty", "en": "is one of", "mayor": "greater than", "menor": "less than",
                "entre": "between", "desde": "from", "hasta": "until", "ultimos_dias": "last days"}
MAX_COLUMNAS, MAX_FILTROS, MAX_GRUPOS, MAX_MEDIDAS = 30, 15, 3, 6
MAX_VISTA, MAX_EXPORTAR = 500, 10_000


def _error(mensaje: str, campo: str = "definicion") -> ErrorNegocio:
    return ErrorNegocio(mensaje, 422, "validacion", [{"campo": campo, "mensaje": mensaje}])


def fuente_de(user: Usuario, clave) -> Fuente:
    f = FUENTES.get(clave)
    if not f:
        raise _error("Choose a data source.", "fuente")
    if not tiene(user, f.permiso):
        raise ErrorNegocio("You do not have access to this data source.", 403, "sin_permiso")
    return f


def _campo(f: Fuente, clave, donde: str) -> Campo:
    c = f.campo(clave) if isinstance(clave, str) else None
    if not c or not visible(c):
        raise _error(f"Unknown field: {clave}.", donde)
    return c


def _valor(c: Campo, op: str, v):
    """El valor de un filtro según el tipo del campo (y del operador)."""
    if op in ("vacio", "no_vacio"):
        return None
    if op == "ultimos_dias":
        try:
            n = int(v)
        except (TypeError, ValueError):
            n = 0
        if not 1 <= n <= 3650:
            raise _error("Enter a number of days between 1 and 3650.", "filtros")
        return n
    if op == "entre":
        if not isinstance(v, list) or len(v) != 2:
            raise _error("A range needs a start and an end.", "filtros")
        return [_valor(c, "igual", x) for x in v]
    if op == "en":
        if not isinstance(v, list) or not v:
            raise _error("Choose at least one value.", "filtros")
        return [_valor(c, "igual", x) for x in v][:50]
    if c.tipo in ("numero", "moneda"):
        try:
            return float(str(v).replace(",", ""))
        except (TypeError, ValueError):
            raise _error(f"{c.titulo}: enter a number.", "filtros") from None
    if c.tipo == "fecha":
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            raise _error(f"{c.titulo}: enter a valid date.", "filtros") from None
    texto = str(v if v is not None else "").strip()[:200]
    if c.tipo == "estado" and c.opciones and texto not in {o[0] for o in c.opciones}:
        raise _error(f"{c.titulo}: unknown value.", "filtros")
    if not texto:
        raise _error(f"{c.titulo}: enter a value.", "filtros")
    return texto


def validar(user: Usuario, d) -> dict:
    """La definición limpia (o un 422 que dice qué está mal)."""
    if not isinstance(d, dict):
        raise _error("The report definition is not valid.")
    f = fuente_de(user, d.get("fuente"))
    agrupar = [_campo(f, x, "agrupar").clave for x in (d.get("agrupar") or [])][:MAX_GRUPOS + 1]
    if len(agrupar) > MAX_GRUPOS:
        raise _error(f"Group by up to {MAX_GRUPOS} fields.", "agrupar")
    for k in agrupar:
        if f.campo(k).tipo in ("numero", "moneda"):
            raise _error(f"{f.campo(k).titulo}: amounts and quantities are measured, not grouped.", "agrupar")
    medidas = []
    for m in (d.get("medidas") or [])[:MAX_MEDIDAS + 1]:
        funcion, campo = (m or {}).get("funcion"), (m or {}).get("campo")
        if funcion not in FUNCIONES:
            raise _error("Unknown measure.", "medidas")
        if funcion == "contar":
            medidas.append({"campo": "*", "funcion": "contar"})
            continue
        c = _campo(f, campo, "medidas")
        if c.tipo not in ("numero", "moneda") and not (funcion in ("minimo", "maximo") and c.tipo == "fecha"):
            raise _error(f"{c.titulo}: only quantities and amounts can be added or averaged.", "medidas")
        medidas.append({"campo": c.clave, "funcion": funcion})
    if len(medidas) > MAX_MEDIDAS:
        raise _error(f"Up to {MAX_MEDIDAS} measures.", "medidas")
    columnas = [_campo(f, x, "columnas").clave for x in (d.get("columnas") or [])][:MAX_COLUMNAS + 1]
    if len(columnas) > MAX_COLUMNAS:
        raise _error(f"Up to {MAX_COLUMNAS} columns.", "columnas")
    if agrupar:
        columnas = []
        medidas = medidas or [{"campo": "*", "funcion": "contar"}]
    elif not columnas:
        raise _error("Choose at least one column.", "columnas")
    filtros = []
    for x in (d.get("filtros") or [])[:MAX_FILTROS + 1]:
        c = _campo(f, (x or {}).get("campo"), "filtros")
        op = (x or {}).get("op")
        if op not in OPERADORES[c.tipo]:
            raise _error(f"{c.titulo}: this condition does not apply.", "filtros")
        filtros.append({"campo": c.clave, "op": op, "valor": _valor(c, op, (x or {}).get("valor"))})
    if len(filtros) > MAX_FILTROS:
        raise _error(f"Up to {MAX_FILTROS} filters.", "filtros")
    salidas = set(columnas) | set(agrupar) | {_alias(m) for m in medidas}
    orden = d.get("orden") or {}
    orden = ({"campo": orden.get("campo"), "dir": "desc" if orden.get("dir") == "desc" else "asc"}
             if orden.get("campo") in salidas else None)
    return {"fuente": f.clave, "columnas": columnas, "agrupar": agrupar, "medidas": medidas if agrupar else [],
            "filtros": [{**x, "valor": x["valor"].isoformat() if isinstance(x["valor"], date) else
                         [y.isoformat() if isinstance(y, date) else y for y in x["valor"]] if isinstance(x["valor"], list)
                         else x["valor"]} for x in filtros],
            "orden": orden, "tipo": "analitico" if agrupar else "operativo"}


def _alias(m: dict) -> str:
    return f"{m['funcion']}_{'todo' if m['campo'] == '*' else m['campo']}"


def _condicion(c: Campo, op: str, v):
    e = c.expr()
    if c.tipo == "fecha" and isinstance(v, str):
        v = date.fromisoformat(v)
    if c.tipo == "fecha" and isinstance(v, list):
        v = [date.fromisoformat(x) if isinstance(x, str) else x for x in v]
    if op == "vacio":
        return or_(e.is_(None), e == "") if c.tipo == "texto" else e.is_(None)
    if op == "no_vacio":
        return (e.is_not(None) & (e != "")) if c.tipo == "texto" else e.is_not(None)
    if op == "contiene":
        return func.lower(e).like(f"%{_escapar(v.lower())}%", escape="\\")
    if op == "empieza":
        return func.lower(e).like(f"{_escapar(v.lower())}%", escape="\\")
    if op == "igual":
        return func.lower(e) == v.lower() if c.tipo == "texto" else e == v
    if op == "distinto":
        return or_(e.is_(None), (func.lower(e) != v.lower()) if c.tipo == "texto" else e != v)
    if op == "en":
        return e.in_(v)
    if op in ("mayor", "desde"):
        return e > v if op == "mayor" else e >= v
    if op in ("menor", "hasta"):
        return e < v if op == "menor" else e <= v
    if op == "entre":
        return e.between(min(v), max(v))
    if op == "ultimos_dias":
        hoy = date.today()
        return e.between(hoy - timedelta(days=v - 1), hoy)
    raise _error("Unknown condition.", "filtros")


def _escapar(texto: str) -> str:
    return re.sub(r"([\\%_])", r"\\\1", texto)


def _celda(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def ejecutar(db: Session, user: Usuario, definicion: dict, limite: int = MAX_VISTA) -> dict:
    d = validar(user, definicion)
    f = FUENTES[d["fuente"]]
    condiciones = alcance(db, user, f) + [_condicion(f.campo(x["campo"]), x["op"], x["valor"]) for x in d["filtros"]]
    if d["tipo"] == "analitico":
        grupos = [f.campo(k).expr().label(k) for k in d["agrupar"]]
        medidas = [(FUNCIONES[m["funcion"]]() if m["campo"] == "*" else FUNCIONES[m["funcion"]](f.campo(m["campo"]).expr()))
                   .label(_alias(m)) for m in d["medidas"]]
        consulta = f.desde(select(*grupos, *medidas)).where(*condiciones).group_by(*[f.campo(k).expr() for k in d["agrupar"]])
        columnas = [{"clave": k, "titulo": f.campo(k).titulo, "tipo": f.campo(k).tipo} for k in d["agrupar"]] + [
            # El título de una medida va en partes (función y dato) para traducir cada una
            {"clave": _alias(m), "titulo": FUNCION_TXT[m["funcion"]], "titulo_campo": None if m["campo"] == "*" else f.campo(m["campo"]).titulo,
             "tipo": "numero" if m["funcion"] == "contar" or m["campo"] == "*" else f.campo(m["campo"]).tipo,
             "funcion": m["funcion"], "campo": m["campo"]} for m in d["medidas"]]
    else:
        consulta = f.desde(select(*[f.campo(k).expr().label(k) for k in d["columnas"]])).where(*condiciones)
        columnas = [{"clave": k, "titulo": f.campo(k).titulo, "tipo": f.campo(k).tipo} for k in d["columnas"]]
    total = db.scalar(select(func.count()).select_from(consulta.subquery()))
    if d["orden"]:
        col = consulta.selected_columns[d["orden"]["campo"]]
        consulta = consulta.order_by(col.desc() if d["orden"]["dir"] == "desc" else col.asc())
    filas = [[_celda(v) for v in fila] for fila in db.execute(consulta.limit(limite)).all()]
    opciones = {c["clave"]: dict(f.campo(c["clave"]).opciones) for c in columnas
                if f.campo(c["clave"]) and f.campo(c["clave"]).opciones}
    return {"definicion": d, "tipo": d["tipo"], "fuente": {"clave": f.clave, "titulo": f.titulo}, "columnas": columnas,
            "filas": filas, "total": total, "truncado": total > len(filas), "opciones": opciones}


def describir_filtros(definicion: dict) -> str:
    """Los filtros en palabras (para el encabezado del archivo)."""
    from app.modulos.documentos.idioma_doc import L

    f = FUENTES[definicion["fuente"]]
    partes = []
    for x in definicion["filtros"]:
        c = f.campo(x["campo"])
        v = x["valor"]
        if c.opciones:
            nombres = dict(c.opciones)
            v = [L(nombres.get(y, y)) for y in v] if isinstance(v, list) else L(nombres.get(v, v))
        v = " – ".join(str(y) for y in v) if isinstance(v, list) else ("" if v is None else str(v))
        partes.append(f"{L(c.titulo)} {L(OPERADOR_TXT[x['op']])} {v}".strip())
    return L("Filters: {0}", " · ".join(partes)) if partes else L("No filters")


def _titulo(c: dict) -> str:
    from app.modulos.documentos.idioma_doc import L

    return f"{L(c['titulo'])}: {L(c['titulo_campo'])}" if c.get("titulo_campo") else L(c["titulo"])


def exportar(db: Session, user: Usuario, definicion: dict, formato: str, titulo: str | None = None) -> tuple[bytes, str]:
    """El reporte como archivo: CSV, Excel o PDF (hasta 10 000 filas)."""
    from app.modulos.documentos import documentos
    from app.modulos.documentos import exportar as excel
    from app.modulos.documentos.idioma_doc import L

    r = ejecutar(db, user, definicion, MAX_EXPORTAR)
    titulo = (titulo or "").strip()[:120] or r["fuente"]["titulo"]
    nombres = r["opciones"]
    filas = [[L(nombres[c["clave"]].get(v, v)) if c["clave"] in nombres and v is not None else v
              for c, v in zip(r["columnas"], fila, strict=False)] for fila in r["filas"]]
    filtros = describir_filtros(r["definicion"])
    if r["truncado"]:
        filtros += " · " + L("First {0} of {1} rows", len(filas), r["total"])
    if formato == "csv":
        salida = io.StringIO()
        escritor = csv.writer(salida)
        escritor.writerow([_titulo(c) for c in r["columnas"]])
        escritor.writerows([["" if v is None else v for v in fila] for fila in filas])
        return ("﻿" + salida.getvalue()).encode("utf-8"), titulo
    columnas = [(_titulo(c), 1.0, c["tipo"] in ("numero", "moneda")) for c in r["columnas"]]
    subtitulo = L("Analytical report: totals by group.") if r["tipo"] == "analitico" else L("Operational report: one row per record.")
    indicadores = [("Rows", f"{r['total']:,}")]
    if formato == "pdf":
        filas_pdf = [[documentos._num(v, 0 if float(v).is_integer() else 2) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
                      for v in fila] for fila in filas]
        return documentos.pdf_reporte(titulo, subtitulo, filtros, indicadores, columnas, filas_pdf), titulo
    return excel.exportar_reporte(titulo, subtitulo, filtros, indicadores, columnas, filas), titulo
