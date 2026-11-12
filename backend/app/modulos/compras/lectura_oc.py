"""Lectura de un archivo de OCs (Excel o CSV): reconoce las columnas por sus
nombres habituales, convierte cada fila en valores tipados y la valida contra
los datos maestros de la empresa.
"""
import csv
import io
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import campos_propios, listas
from app.core.archivos import abrir_libro
from app.core.errores import ErrorNegocio
from app.modelos import (
    Almacen,
    Centro,
    Pais,
    Proveedor,
    Puerto,
    Sociedad,
)
from app.modelos import cant as cant_norm
from app.modulos.acceso.preferencias import leer_fecha
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comex import servicio as comex
from app.modulos.compras import liberaciones, perfiles
from app.modulos.compras.ordenes import validar_empaque
from app.modulos.comun.normalizar import celda, encabezado
from app.modulos.maestros.unidades import error_cantidad
from app.modulos.maestros.unidades import normalizar as unidad_de

# ---- Importación ------------------------------------------------------------
# Nombres de columna que el sistema reconoce sin perfil (genéricos, en inglés y
# español). El primero es el de la plantilla. Los nombres propios del ERP de la
# empresa van en un perfil de importación (perfiles.py).
ALIAS = {
    "proveedor": ["supplier", "vendor", "supplier_code", "proveedor", "codigo_proveedor", "proveedor_codigo"],
    "oc": ["po", "po_number", "purchase_order", "oc", "orden", "orden_compra", "numero_oc"],
    "posicion": ["po_line", "line", "item", "posicion", "pos", "linea"],
    "sociedad": ["company", "company_code", "sociedad", "compania"],
    "centro": ["plant", "bonded_warehouse", "centro", "bodega", "bodega_fiscal"],
    "almacen": ["storage_location", "sloc", "almacen"],
    "centro_destino": ["destination", "destination_center", "destination_country", "centro_destino", "pais_destino",
                       "destino", "codigo_destino"],
    "moneda": ["currency", "moneda"],
    "incoterm": ["incoterm"],
    "fecha_oc": ["po_date", "fecha_oc", "fecha"],
    "puerto_despacho": ["port_of_loading", "pol", "port", "puerto_despacho", "puerto", "puerto_embarque"],
    "pais_origen": ["country_of_origin", "coo", "origin", "pais_origen", "origen"],
    "pais_procedencia": ["country_of_shipment", "provenance", "pais_procedencia", "procedencia"],
    "fecha_xf_original": ["xf_date_original", "original_xf_date", "fecha_xf_original", "xf_original"],
    "fecha_xf": ["xf_date", "xf", "updated_xf_date", "fecha_xf", "fecha_xf_actualizada", "xf_actualizada"],
    "fecha_tienda": ["in_store_date", "store_date", "fecha_tienda", "fecha_requerida_tienda", "fecha_requerida"],
    "liberacion_comercial": ["commercial_release", "liberacion_comercial", "lib_comercial", "liberada",
                             "estado_liberacion"],
    "liberacion_logistica": ["logistics_release", "liberacion_logistica", "lib_logistica"],
    "fecha_lib_comercial": ["commercial_release_date", "fecha_liberacion_comercial", "fecha_lib_comercial"],
    "fecha_lib_logistica": ["logistics_release_date", "fecha_liberacion_logistica", "fecha_lib_logistica"],
    "codigo_articulo": ["sku", "item_code", "material", "codigo", "codigo_sap", "articulo"],
    "cantidad": ["quantity", "qty", "cantidad"],
    "unidad": ["uom", "unit", "um", "unidad"],
    "precio": ["unit_price", "price", "precio", "precio_unitario"],
    "casepack": ["casepack", "case_pack"],
    "inner_pack": ["inner_pack", "inner", "innerpack", "inner_casepack", "pack"],
    "fecha_entrega": ["delivery_date", "fecha_entrega", "entrega"],
}
# Lo mínimo para registrar una OC; el resto es opcional y lo que falte para
# facturar (empresa, moneda, precio) se pide al facturar
REQUERIDOS = ["proveedor", "oc", "posicion", "codigo_articulo", "cantidad"]
NOMBRE_CAMPO = {"proveedor": "supplier", "oc": "PO number", "posicion": "PO line", "codigo_articulo": "item code",
                "cantidad": "quantity"}
CAMPOS_CABECERA = ["sociedad", "centro", "centro_destino", "moneda", "incoterm", "fecha", "puerto_despacho",
                   "pais_origen", "pais_procedencia", "fecha_xf_original", "fecha_xf", "fecha_tienda",
                   "liberacion_comercial"]
CAMPOS_POSICION = [
    "almacen", "articulo_id", "codigo_articulo", "codigo_barras", "descripcion",
    "tipo_empaque", "casepack", "inner_pack", "codigo_pack", "unidades_por_caja", "cantidad", "unidad", "precio", "fecha_entrega",
    "pais_origen",
]


def _leer_archivo(nombre: str, contenido: bytes, perfil=None) -> list[dict]:
    """Filas del archivo como {campo: texto}. Con un perfil de importación, sus
    nombres de columna mandan, los encabezados van en su fila, las fechas se
    leen con su formato y lo que falta toma sus valores por defecto."""
    inicio = (perfil.fila_encabezado if perfil else 1) - 1
    if nombre.lower().endswith((".xlsx", ".xlsm")):
        wb = abrir_libro(contenido, read_only=True, data_only=True)
        ws = wb.active
        filas = list(ws.iter_rows(values_only=True))[inicio:]
        if not filas:
            return []
        encabezados = [celda(h) for h in filas[0]]
        datos = [[celda(v) for v in fila] for fila in filas[1:]]
    else:
        texto = contenido.decode("utf-8-sig", errors="replace")
        muestra = texto[:2000]
        delimitador = ";" if muestra.count(";") > muestra.count(",") else ","
        lector = list(csv.reader(io.StringIO(texto), delimiter=delimitador))[inicio:]
        if not lector:
            return []
        encabezados = lector[0]
        datos = [[v.strip() for v in fila] for fila in lector[1:]]

    propios = {c: [encabezado(x) for x in str(v).split(",") if x.strip()] for c, v in ((perfil.columnas or {}) if perfil else {}).items()}
    normalizados = [encabezado(h) for h in encabezados]
    # Campos propios de las OCs: se reconocen por su nombre o su clave
    extra = {f"extra.{c['clave']}": [encabezado(c["etiqueta"]), encabezado(c["clave"])] for c in campos_propios.definiciones("ordenes")}
    mapa = {}
    for fuente in (propios, ALIAS, extra):  # primero los nombres del perfil
        for campo, nombres in fuente.items():
            i = next((i for i, n in enumerate(normalizados) if n in nombres), None)
            if campo not in mapa and i is not None:
                mapa[campo] = i
    defectos = (perfil.valores or {}) if perfil else {}
    faltan = [c for c in REQUERIDOS if c not in mapa]
    if faltan:
        nombres = [((perfil.columnas or {}).get(c) if perfil else None) or ALIAS[c][0] for c in faltan]
        raise ErrorNegocio(
            "The file is missing required columns: " + ", ".join(nombres) + ".",
            422,
            "columnas_faltantes",
            {"faltan": faltan, "encontradas": encabezados},
        )
    filas_dict = []
    for n_fila, fila in enumerate(datos, start=inicio + 2):
        if not any(fila):
            continue
        registro = {campo: (fila[i] if i < len(fila) else "") for campo, i in mapa.items()}
        for campo, valor in defectos.items():
            if not registro.get(campo):
                registro[campo] = valor
        if perfil and perfil.formato_fecha:
            for campo in registro:
                if campo.startswith("fecha") and registro[campo]:
                    registro[campo] = perfiles.fecha_iso(registro[campo], perfil.formato_fecha)
        registro["_fila"] = n_fila
        filas_dict.append(registro)
    return filas_dict


def _fecha(valor: str) -> date | None:
    # ISO o el formato de fecha del usuario (con su orden día/mes para no confundirlos)
    return leer_fecha(valor)


class Maestros:
    """Catálogos precargados para validar un archivo completo sin consultas por fila."""

    def __init__(self, db: Session):
        self.lib = liberaciones.de(db)
        self.proveedores = {p.codigo: p for p in db.scalars(select(Proveedor))}
        self.sociedades = {s.codigo: s for s in db.scalars(select(Sociedad))}
        self.centros = {c.codigo: c for c in db.scalars(select(Centro))}
        self.almacenes = {a.codigo: a for a in db.scalars(select(Almacen))}
        self.puertos = {p.codigo: p for p in db.scalars(select(Puerto))}
        self.paises = {p.codigo for p in db.scalars(select(Pais))}
        self.articulos: dict[str, catalogo.FichaArticulo | None] = {}
        self._db = db
        # Códigos escritos de otra forma (minúsculas, espacios, por nombre) -> código real
        from app.modulos.comun.normalizar import Referencias

        self.refs = {"proveedor": Referencias(db, Proveedor), "sociedad": Referencias(db, Sociedad),
                     "centro": Referencias(db, Centro), "almacen": Referencias(db, Almacen),
                     "puerto": Referencias(db, Puerto), "pais": Referencias(db, Pais)}

    def canon(self, tabla: str, valor):
        obj = self.refs[tabla].buscar(valor)
        return obj.codigo if obj else valor

    def articulo(self, codigo: str) -> catalogo.FichaArticulo | None:
        if codigo not in self.articulos:
            self.articulos[codigo] = catalogo.por_codigo(self._db, codigo)
        return self.articulos[codigo]


PAIS_TXT = {"pais_origen": "country of origin", "pais_procedencia": "country of shipment"}


def _normalizar(registro: dict, m: Maestros) -> tuple[dict, list[str]]:
    """Convierte los textos de una fila en valores tipados y la valida contra
    los datos maestros. Los códigos se mantienen como texto."""
    errores = []
    r = {k: (v or "").strip() for k, v in registro.items() if k != "_fila"}
    for campo in REQUERIDOS:
        if not r.get(campo):
            errores.append(f"Missing: {NOMBRE_CAMPO[campo]}.")
    d = {
        "proveedor": r.get("proveedor", "").upper(),
        "oc": r.get("oc", ""),
        "posicion": r.get("posicion", "").lstrip("0") or r.get("posicion", ""),
        "sociedad": r.get("sociedad", "").upper(),
        "centro": (r.get("centro") or "").upper() or None,
        "almacen": (r.get("almacen") or "").upper() or None,
        "centro_destino": r.get("centro_destino") or None,
        "moneda": (r.get("moneda") or "").upper(),
        "incoterm": (r.get("incoterm") or "").upper() or None,
        "puerto_despacho": (r.get("puerto_despacho") or "").upper() or None,
        "pais_origen": (r.get("pais_origen") or "").upper() or None,
        "pais_procedencia": (r.get("pais_procedencia") or r.get("pais_origen") or "").upper() or None,
        "liberacion_comercial": (r.get("liberacion_comercial") or "").strip() or None,
        "liberacion_logistica_archivo": (r.get("liberacion_logistica") or "").strip() or None,
        "codigo_articulo": r.get("codigo_articulo", ""),
    }
    com = m.lib.comercial.leer(d["liberacion_comercial"])
    if com is False:
        errores.append(f"Invalid commercial release {d['liberacion_comercial']} (use {m.lib.comercial.ayuda()}).")
        com = None
    d["liberacion_comercial"] = com or m.lib.comercial.predeterminado()
    log = m.lib.logistica.leer(d["liberacion_logistica_archivo"])
    d["liberacion_logistica_archivo"] = log
    if log is False:
        errores.append(f"Invalid logistics release {r.get('liberacion_logistica')} (use {m.lib.logistica.ayuda()}).")
        log = d["liberacion_logistica_archivo"] = None
    elif log and m.lib.logistica.libera(log) and not m.lib.comercial.libera(d["liberacion_comercial"]):
        errores.append(f"Logistics cannot release ({log}) without commercial release.")
    if d["oc"] and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}", d["oc"]):
        errores.append(f"PO {d['oc']}: letters and numbers (also . - _ /), up to 40 characters.")
    if d["posicion"] and not re.fullmatch(r"[A-Za-z0-9]{1,10}", d["posicion"]):
        errores.append(f"Line {d['posicion']}: letters and numbers, up to 10 characters.")
    try:
        cant = float(r.get("cantidad", "").replace(",", "")) if r.get("cantidad") else None
        if cant is not None and cant < 0:
            raise ValueError
        d["cantidad"] = cant_norm(cant)
    except ValueError:
        errores.append(f"Invalid quantity: {r.get('cantidad')}.")
        d["cantidad"] = None
    try:
        d["precio"] = float(r.get("precio", "").replace(",", "")) if r.get("precio") else None
        if d["precio"] is not None and d["precio"] < 0:
            raise ValueError
    except ValueError:
        errores.append(f"Invalid price: {r.get('precio')}.")
        d["precio"] = None
    # Empaque de la compra: viene en la posición de la OC, no en el artículo
    for campo, texto in (("casepack", "Casepack"), ("inner_pack", "Inner pack")):
        try:
            d[campo] = int(float(r[campo])) if r.get(campo) else None
            if d[campo] is not None and d[campo] < 1:
                raise ValueError
        except ValueError:
            errores.append(f"Invalid {texto.lower()}: {r.get(campo)}.")
            d[campo] = None
    unidad = unidad_de(r.get("unidad"))
    if r.get("unidad") and not unidad:
        errores.append(f"Unknown unit: {r.get('unidad')} (use PAR, UN or CJ).")
    d["unidad"] = unidad
    for campo, destino in (("fecha_oc", "fecha"), ("fecha_entrega", "fecha_entrega"),
                           ("fecha_xf_original", "fecha_xf_original"), ("fecha_xf", "fecha_xf"),
                           ("fecha_tienda", "fecha_tienda"), ("fecha_lib_comercial", "fecha_lib_comercial"),
                           ("fecha_lib_logistica", "fecha_lib_logistica")):
        try:
            d[destino] = _fecha(r.get(campo, ""))
        except ValueError as e:
            errores.append(str(e).capitalize() + ".")
            d[destino] = None
    if d["precio"] is not None and not d["moneda"]:
        errores.append("Enter the currency of the price.")
    if d["cantidad"] == 0:
        errores.append("The quantity must be greater than zero.")
    d["moneda"] = d["moneda"] or None
    d["sociedad"] = d["sociedad"] or None
    d["fecha_xf_original"] = d["fecha_xf_original"] or d["fecha_xf"]
    d["fecha_xf"] = d["fecha_xf"] or d["fecha_xf_original"]
    try:
        d["extra"] = campos_propios.limpiar("ordenes", {k[6:]: v for k, v in r.items() if k.startswith("extra.")})
    except ErrorNegocio as e:
        errores += [x["mensaje"] for x in e.detalle or []]
        d["extra"] = {}

    if m is None:
        return d, errores
    for campo, tabla in (("proveedor", "proveedor"), ("sociedad", "sociedad"), ("centro", "centro"), ("almacen", "almacen"),
                         ("centro_destino", "centro"), ("puerto_despacho", "puerto"), ("pais_origen", "pais"),
                         ("pais_procedencia", "pais")):
        if d.get(campo):
            d[campo] = m.canon(tabla, d[campo])
    # Datos maestros. Todo queda encadenado: el proveedor trabaja con la
    # sociedad; centro, almacén y centro destino son de esa sociedad; el
    # artículo y su marca son del proveedor. Sin sociedad, se toma la del
    # centro o almacén indicado.
    if not d["sociedad"]:
        for campo, tabla in (("centro", m.centros), ("almacen", m.almacenes), ("centro_destino", m.centros)):
            x = tabla.get(d[campo]) if d[campo] else None
            if x and x.sociedad:
                d["sociedad"] = x.sociedad.codigo
                break
    soc = m.sociedades.get(d["sociedad"])
    if d["sociedad"] and not soc:
        errores.append(f"Company {d['sociedad']} does not exist.")
    cen = m.centros.get(d["centro"]) if d["centro"] else None
    if d["centro"] and not cen:
        errores.append(f"Plant {d['centro']} does not exist.")
    elif cen and soc and cen.sociedad_id != soc.id:
        errores.append(f"Plant {d['centro']} does not belong to company {d['sociedad']}.")
    if d["almacen"]:
        alm = m.almacenes.get(d["almacen"])
        if not alm:
            errores.append(f"Storage location {d['almacen']} does not exist.")
        elif soc and alm.sociedad_id != soc.id:
            errores.append(f"Storage location {d['almacen']} does not belong to company {d['sociedad']}.")
    prov = m.proveedores.get(d["proveedor"])
    if prov and not prov.activo:
        errores.append(f"Supplier {prov.nombre} is inactive.")
    if prov and soc and soc.id not in {x.id for x in prov.sociedades}:
        errores.append(f"Supplier {prov.nombre} does not work with company {d['sociedad']}. "
                       "Assign the company to the supplier in master data first.")
    destino = m.centros.get(d["centro_destino"]) if d["centro_destino"] else None
    if d["centro_destino"] and not destino:
        errores.append(f"Destination center {d['centro_destino']} is not registered in master data.")
    elif destino and soc and destino.sociedad_id != soc.id:
        errores.append(f"Destination center {d['centro_destino']} does not belong to company {d['sociedad']}.")
    if d["puerto_despacho"] and d["puerto_despacho"] not in m.puertos:
        errores.append(f"Port {d['puerto_despacho']} is not registered.")
    # Moneda e incoterm: de las listas de la empresa (Datos maestros → Listas de valores)
    if d["moneda"] and d["moneda"] not in listas.codigos("moneda"):
        errores.append(f"Currency {d['moneda']} is not in the list of currencies.")
    if d["incoterm"] and d["incoterm"] not in listas.codigos("incoterm"):
        errores.append(f"Incoterm {d['incoterm']} is not in the list of Incoterms.")
    for campo in ("pais_origen", "pais_procedencia"):
        if d[campo] and d[campo] not in m.paises:
            errores.append(f"Country {d[campo]} ({PAIS_TXT[campo]}) is not registered.")
    art = m.articulo(d["codigo_articulo"]) if d["codigo_articulo"] else None
    if d["codigo_articulo"] and not art:
        errores.append(f"SKU {d['codigo_articulo']} does not exist in the item master. Load it first.")
    elif art:
        prov = m.proveedores.get(d["proveedor"])
        if prov and art.proveedor_id and art.proveedor_id != prov.id:
            errores.append(f"SKU {art.codigo} belongs to another supplier, not {prov.nombre}.")
        elif prov and art.marca and art.marca not in {x.codigo for x in prov.marcas}:
            errores.append(f"Brand {art.marca} of SKU {art.codigo} is not a brand of {prov.nombre}.")
        if not art.activo:
            errores.append(f"SKU {art.codigo} is inactive in the item master.")
        if d["unidad"] and d["unidad"] != art.unidad:
            errores.append(f"Unit {d['unidad']} does not match the item master ({art.unidad}).")
        d.update(
            articulo_id=art.id, codigo_barras=art.codigo_barras, descripcion=art.descripcion,
            tipo_empaque=art.tipo, unidad=art.unidad, codigo_pack=art.codigo_pack,
            unidades_por_caja=art.total_componentes if art.es_pack else None,
        )
        errores += validar_empaque(art.tipo, d["casepack"], d["inner_pack"], d["cantidad"])
        if d["cantidad"] and (msg := error_cantidad(d["cantidad"], art.unidad)):
            errores.append(msg)
        ficha = comex.de_articulos(m._db, [art.id]).get(art.id)
        d["pais_origen_pos"] = (ficha.pais_origen if ficha else None) or d["pais_origen"]
    return d, errores


