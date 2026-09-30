"""Cargas masivas desde Excel.

- Artículos con su ficha técnica: cada fila es una talla (código de
  artículo); las columnas de la ficha se guardan en el producto (estilo-color)
  si todavía no está aprobado. Después el navegador corre el motor sobre los
  productos cargados y los deja clasificados.
- Cualquier catálogo de datos maestros: plantilla con sus columnas, carga
  (crea o actualiza por código) y exportación con los filtros de la pantalla.
"""
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Articulo, GrupoArticulo, Marca, Pais, Proveedor, Usuario
from . import catalogos as cat_svc
from . import documentos, exportar
from .common import ErrorNegocio, exigir, registrar
from .meta import attrs, tipo_de, tipos, valor_opcion
from .plantillas import leer, norm, plantilla, si_no
from .productos import APROBADOS, asegurar_producto

# ---- Artículos con ficha técnica -------------------------------------------------------
PARTES = [("exterior", "Outer fabric"), ("forro", "Lining"), ("relleno", "Fill"), ("corte", "Upper"), ("suela", "Sole"),
          ("plantilla", "Insole"), ("material", "Main material")]
# Atributos que más cambian la partida; los demás los deduce el motor del nombre y la composición
ATRIBUTOS = [("tejido", "Fabric"), ("hechura", "Jacket construction"), ("hechuraSud", "Sweatshirt construction"),
             ("relleno_tipo", "Fill type"), ("tieneForro", "Has a lining"), ("recubierta", "Coated fabric"),
             ("manga", "Sleeve"), ("estiloCalz", "Footwear style"), ("altura", "Height"), ("disenio", "Design"),
             ("puntera", "Protective toe cap"), ("impermeable", "Waterproof")]
GENERO = {"M": "Men", "F": "Women", "U": "Unisex"}
EDAD = {"adulto": "Adult", "nino": "Child", "bebe": "Baby"}

ALIAS_ART = {
    "item_code": "sku", "sku": "sku", "codigo_de_articulo": "sku", "codigo": "sku", "article_code": "sku",
    "supplier_sku": "sku_proveedor", "sku_proveedor": "sku_proveedor", "vendor_sku": "sku_proveedor",
    "upc": "upc", "style": "estilo", "estilo": "estilo", "color": "color", "size": "talla", "talla": "talla",
    "brand": "marca", "marca": "marca", "item_group": "grupo", "group": "grupo", "grupo": "grupo",
    "supplier": "proveedor", "proveedor": "proveedor", "unit": "unidad", "uom": "unidad", "unidad": "unidad",
    "type": "tipo", "active": "activo",
    "commercial_name": "nombre", "product_name": "nombre", "name": "nombre", "description": "nombre",
    "category": "categoria", "product_type": "categoria", "categoria": "categoria",
    "gender": "genero", "genero": "genero", "who_it_is_for": "edad", "age": "edad", "edad": "edad",
    "what_it_is_for": "uso", "use": "uso", "uso": "uso", "size_range": "tallas", "tallas": "tallas",
    "country_of_origin": "pais_origen", "origin": "pais_origen", "pais_origen": "pais_origen",
    "generic_code": "codigo_generico", "proposed_hs_code": "partida", "hs_code": "partida", "partida_arancelaria": "partida",
}
for _k, _l in PARTES:
    ALIAS_ART[norm(_l)] = "comp_" + _k
    ALIAS_ART["comp_" + _k] = "comp_" + _k
for _k, _l in ATRIBUTOS:
    ALIAS_ART[norm(_l)] = "a_" + _k
    ALIAS_ART[norm(_k)] = "a_" + _k


def plantilla_articulos(db: Session) -> bytes:
    marcas = [m.codigo for m in db.scalars(select(Marca).order_by(Marca.codigo))]
    grupos = [g.codigo for g in db.scalars(select(GrupoArticulo).order_by(GrupoArticulo.codigo))]
    provs = [p.codigo for p in db.scalars(select(Proveedor).order_by(Proveedor.codigo))]
    categorias = [t["l"] for t in tipos().values()]
    cols = [
        {"nombre": "Item code", "req": True, "ayuda": "11 digits starting with 3 (e.g. 30095120001). Existing codes are updated.", "ancho": 14},
        {"nombre": "Supplier SKU", "ayuda": "The supplier's own code (e.g. VN0A4BV4W00-7).", "ancho": 18},
        {"nombre": "UPC", "ancho": 15},
        {"nombre": "Style", "req": True, "ancho": 12}, {"nombre": "Color", "req": True, "ancho": 14},
        {"nombre": "Size", "req": True, "ancho": 8},
        {"nombre": "Brand", "req": True, "opciones": marcas, "ayuda": "Brand code.", "ancho": 10},
        {"nombre": "Item group", "req": True, "opciones": grupos, "ayuda": "Group code (packing rule).", "ancho": 12},
        {"nombre": "Supplier", "req": True, "opciones": provs, "ayuda": "Supplier code.", "ancho": 10},
        {"nombre": "Unit", "req": True, "opciones": ["PAR", "UN"], "ayuda": "PAR (pairs) or UN (units).", "ancho": 8},
        {"nombre": "Commercial name", "ayuda": "Technical sheet: product name, e.g. Old Skool canvas sneaker. The engine reads it.", "ancho": 30},
        {"nombre": "Category", "opciones": categorias, "ayuda": "Technical sheet: what the product is. If empty, the engine detects it from the name.", "ancho": 30},
        {"nombre": "Gender", "opciones": list(GENERO.values()), "ancho": 10},
        {"nombre": "Who it is for", "opciones": list(EDAD.values()), "ancho": 12},
        {"nombre": "What it is for", "ayuda": "Short phrase, e.g. casual everyday sneaker.", "ancho": 26},
        {"nombre": "Size range", "ayuda": "e.g. 7 to 12, S to XL. If empty, taken from the sizes.", "ancho": 12},
        {"nombre": "Country of origin", "ayuda": "ISO code or name (e.g. VN or Vietnam).", "ancho": 14},
        {"nombre": "Generic code", "ancho": 12},
    ]
    for k, l in PARTES:
        cols.append({"nombre": l, "ayuda": f"Composition of the {l.lower()} with percentages, e.g. 60% cotton, 40% polyester.", "ancho": 22})
    for k, l in ATRIBUTOS:
        a = attrs().get(k)
        if a and a["tipo"] == "check":
            cols.append({"nombre": l, "opciones": ["Yes", "No"], "ayuda": a["label"], "ancho": 12})
        elif a:
            cols.append({"nombre": l, "opciones": [o["l"] for o in a["ops"]], "ayuda": a["label"], "ancho": 22})
    cols.append({"nombre": "Proposed HS code", "ayuda": "Optional: HS code the supplier proposes. Customs reviews it.", "ancho": 14})
    ej = ["30095129001", "VN0A5KRFBLK-8", "0196012345678", "VN0A5KRF", "Black", "8", marcas[0] if marcas else "",
          grupos[0] if grupos else "", provs[0] if provs else "", "PAR", "Sk8-Hi canvas sneaker", "Footwear: sneakers, boots, shoes, sandals",
          "Unisex", "Adult", "Casual skate sneaker", "6 to 12", "VN", "", "", "", "", "100% canvas", "100% rubber", "100% textile",
          "100% EVA", "", "", "", "", "", "", "", "Sneaker", "Covers the ankle", "Skate", "No toe cap", "No", ""]
    return plantilla("Items with technical sheet", cols, [ej[:len(cols)]], [
        "One row per item (size). Rows of the same style and color share one product and its technical sheet.",
        "Only the item columns are required. Fill the technical sheet columns you have: the classification engine "
        "completes the rest from the name, the use and the composition, and suggests the HS code right after the upload.",
        "Prepacks are not loaded here: they are built from solids in Master data → Prepacks and take their classification.",
        "Approved technical sheets are not changed by an upload; open a new version to change them.",
    ])


def importar_articulos(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    exigir(user, "catalogos.editar")
    filas = leer(nombre, contenido, ALIAS_ART)
    cods = {
        "marca": {m.codigo: m.id for m in db.scalars(select(Marca))},
        "grupo": {g.codigo: g.id for g in db.scalars(select(GrupoArticulo))},
        "proveedor": {p.codigo: p.id for p in db.scalars(select(Proveedor))},
    }
    paises = {}
    for p in db.scalars(select(Pais)):
        paises[norm(p.codigo)] = p.codigo
        paises[norm(p.nombre)] = p.codigo
    cat = cat_svc.CATALOGOS["articulos"]
    creados = actualizados = 0
    errores, productos = [], {}
    for f in filas:
        tipo_art = (f.get("tipo") or "SOLIDO").strip().upper()
        if tipo_art == "PREPACK":
            errores.append({"fila": f["_fila"], "mensaje": "Prepacks are loaded in Master data → Prepacks with their breakdown."})
            continue
        datos = {k: f.get(k, "") for k in ("sku", "sku_proveedor", "estilo", "color", "talla", "upc") if f.get(k, "") != ""}
        datos["tipo"] = "SOLIDO"
        if f.get("unidad"):
            datos["unidad"] = f["unidad"].strip().upper()
        if f.get("activo"):
            datos["activo"] = si_no(f["activo"]) is not False
        faltan = []
        for campo, destino, lbl in (("marca", "marca_id", "Brand"), ("grupo", "grupo_id", "Item group"),
                                    ("proveedor", "proveedor_id", "Supplier")):
            codigo = (f.get(campo) or "").strip().upper()
            if not codigo:
                continue
            if codigo not in cods[campo]:
                faltan.append(f"{lbl} {codigo} does not exist")
            else:
                datos[destino] = cods[campo][codigo]
        if faltan:
            errores.append({"fila": f["_fila"], "mensaje": "; ".join(faltan) + "."})
            continue
        existente = db.scalar(select(Articulo).where(Articulo.sku == (datos.get("sku") or "").strip()))
        try:
            with db.begin_nested():
                if existente:
                    for k, v in cat_svc._limpiar(db, cat, datos, parcial=True, actual=existente).items():
                        setattr(existente, k, v)
                    art = existente
                else:
                    art = Articulo(**cat_svc._limpiar(db, cat, datos, parcial=False), activo=datos.get("activo", True))
                    db.add(art)
                db.flush()
                prod = asegurar_producto(db, art)
                if prod:
                    aviso = _ficha_desde_fila(prod, f, paises)
                    if aviso:
                        errores.append({"fila": f["_fila"], "mensaje": aviso})
                    productos[prod.id] = prod.estado
        except IntegrityError:
            errores.append({"fila": f["_fila"], "mensaje": "Duplicated or inconsistent data."})
            continue
        except ErrorNegocio as e:
            errores.append({"fila": f["_fila"], "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
            continue
        if existente:
            actualizados += 1
        else:
            creados += 1
    db.flush()
    registrar(db, user, "articulos", 0, "importar", {"creados": creados, "actualizados": actualizados,
                                                      "errores": len(errores), "productos": len(productos)})
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:300],
            "productos": [pid for pid, e in productos.items() if e not in APROBADOS],
            "productos_total": len(productos)}


def _ficha_desde_fila(p, f: dict, paises: dict) -> str | None:
    """Pasa las columnas de la ficha al producto (solo lo que viene lleno y
    solo si la ficha no está aprobada). Devuelve un aviso si algo no se entendió."""
    if p.estado in APROBADOS:
        return None
    ficha = dict(p.ficha or {})
    avisos = []
    if f.get("nombre"):
        p.nombre = f["nombre"][:200]
    if f.get("codigo_generico"):
        p.codigo_generico = f["codigo_generico"][:20]
    if f.get("categoria"):
        k = tipo_de(f["categoria"])
        if k:
            p.tipo = k
            ficha.pop("_categoria", None)
        elif not p.tipo:
            ficha["_categoria"] = f["categoria"][:100]
    if f.get("genero"):
        g = valor_opcion(GENERO, f["genero"])
        if g:
            ficha["genero"] = g
        else:
            avisos.append(f"Gender “{f['genero']}” not recognized")
    if f.get("edad"):
        e = valor_opcion(EDAD, f["edad"])
        if e:
            ficha["edadNac"] = e
            ficha["edad"] = "bebe" if e == "bebe" else "general"
        else:
            avisos.append(f"Age “{f['edad']}” not recognized")
    for k in ("uso", "tallas"):
        if f.get(k):
            ficha[k] = f[k][:200]
    if f.get("pais_origen"):
        iso = paises.get(norm(f["pais_origen"]))
        if iso:
            p.pais_origen = iso
        else:
            avisos.append(f"Country “{f['pais_origen']}” not in the countries catalog")
    comp = dict(ficha.get("comp") or {})
    for k, _ in PARTES:
        if f.get("comp_" + k):
            comp[k] = f["comp_" + k][:300]
    if comp:
        ficha["comp"] = comp
    for k, lbl in ATRIBUTOS:
        v = f.get("a_" + k)
        if not v:
            continue
        a = attrs().get(k)
        if a and a["tipo"] == "check":
            b = si_no(v)
            if b is None:
                avisos.append(f"{lbl}: write Yes or No")
            else:
                ficha[k] = b
        elif a:
            x = valor_opcion({o["v"]: o["l"] for o in a["ops"]}, v)
            if x:
                ficha[k] = x
            else:
                avisos.append(f"{lbl}: “{v}” is not a valid value")
    if f.get("partida"):
        d = re.sub(r"\D", "", f["partida"])
        if len(d) >= 6:
            p.propuesta = d[:14]
    p.ficha = ficha
    return ("Item loaded, but: " + "; ".join(avisos) + ".") if avisos else None


# ---- Cualquier catálogo de datos maestros ------------------------------------------------
def _cols_catalogo(db: Session, tipo: str) -> list[dict]:
    c = cat_svc._cat(tipo)
    cols = []
    for x in c["campos"]:
        col = {"campo": x, "nombre": x["etiqueta"], "req": x["obligatorio"], "ayuda": x.get("ayuda") or ""}
        if x["tipo"] == "opcion":
            col["opciones"] = [t for _, t in x["opciones"]]
        elif x["tipo"] == "bool":
            col["opciones"] = ["Yes", "No"]
        elif x["tipo"] in ("ref", "codigo", "multi"):
            modelo = cat_svc.CATALOGOS[x["catalogo"]]["modelo"]
            clave = "sku" if x["catalogo"] == "articulos" else "codigo"
            codigos = [getattr(o, clave) for o in db.scalars(select(modelo))]
            if x["tipo"] == "multi":
                col["ayuda"] = (col["ayuda"] + " " if col["ayuda"] else "") + "Codes separated by commas: " + ", ".join(codigos[:40])
            else:
                col["opciones"] = codigos
                col["ayuda"] = (col["ayuda"] + " " if col["ayuda"] else "") + "Code."
        cols.append(col)
    return cols


def plantilla_catalogo(db: Session, user: Usuario, tipo: str) -> bytes:
    exigir(user, "catalogos.ver")
    if tipo == "articulos":
        return plantilla_articulos(db)
    c = cat_svc._cat(tipo)
    cols = _cols_catalogo(db, tipo)
    return plantilla(c["titulo"], [{k: v for k, v in x.items() if k != "campo"} for x in cols], None, [
        c.get("ayuda") or "",
        "One row per record. A row whose code already exists updates that record; the others are created.",
    ])


def importar_catalogo(db: Session, user: Usuario, tipo: str, nombre: str, contenido: bytes) -> dict:
    exigir(user, "catalogos.editar")
    if tipo == "articulos":
        return importar_articulos(db, user, nombre, contenido)
    if tipo == "prepacks":
        return cat_svc.importar_prepacks(db, user, nombre, contenido)
    c = cat_svc._cat(tipo)
    cols = _cols_catalogo(db, tipo)
    alias = {}
    for x in cols:
        alias[norm(x["nombre"])] = x["campo"]["nombre"]
        alias[norm(x["campo"]["nombre"])] = x["campo"]["nombre"]
    filas = leer(nombre, contenido, alias)
    modelo = c["modelo"]
    clave = "codigo" if any(x["nombre"] == "codigo" for x in c["campos"]) else None
    creados = actualizados = 0
    errores = []
    for f in filas:
        datos, mal = {}, None
        for x in c["campos"]:
            n = x["nombre"]
            if n not in f or f[n] == "":
                continue
            v = f[n].strip()
            if x["tipo"] == "opcion":
                v = next((k for k, t in x["opciones"] if norm(v) in (norm(k), norm(t))), v)
            elif x["tipo"] == "bool":
                v = si_no(v) is not False
            elif x["tipo"] in ("ref", "multi"):
                m = cat_svc.CATALOGOS[x["catalogo"]]["modelo"]
                campo_cod = m.sku if x["catalogo"] == "articulos" else m.codigo
                cods = [s.strip().upper() for s in v.split(",") if s.strip()] if x["tipo"] == "multi" else [v.upper()]
                ids = [db.scalar(select(m.id).where(campo_cod == cd)) for cd in cods]
                if None in ids:
                    mal = f"{x['etiqueta']}: {cods[ids.index(None)]} does not exist."
                    break
                v = ids if x["tipo"] == "multi" else ids[0]
            datos[n] = v
        if mal:
            errores.append({"fila": f["_fila"], "mensaje": mal})
            continue
        actual = None
        if clave and datos.get(clave):
            actual = db.scalar(select(modelo).where(getattr(modelo, clave) == str(datos[clave]).strip().upper()))
        try:
            with db.begin_nested():
                if actual:
                    for k, v in cat_svc._limpiar(db, c, datos, parcial=True, actual=actual).items():
                        setattr(actual, k, v)
                    actualizados += 1
                else:
                    limpio = cat_svc._limpiar(db, c, datos, parcial=False)
                    for x in c["campos"]:
                        if x["tipo"] == "bool" and x["nombre"] not in datos:
                            limpio[x["nombre"]] = True
                    db.add(modelo(**limpio))
                    creados += 1
                db.flush()
        except IntegrityError:
            errores.append({"fila": f["_fila"], "mensaje": "Duplicated code or data in use."})
        except ErrorNegocio as e:
            errores.append({"fila": f["_fila"], "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    registrar(db, user, tipo, 0, "importar", {"creados": creados, "actualizados": actualizados, "errores": len(errores)})
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:300]}


def exportar_catalogo(db: Session, user: Usuario, tipo: str, q: str | None, filtros: dict, orden: str | None,
                      formato: str) -> bytes:
    c = cat_svc._cat(tipo)
    r = cat_svc.listar(db, user, tipo, q, filtros, orden, 1, 100_000)
    campos = c["campos"]
    extra = [("descripcion", "Description"), ("partida_txt", "HS code")] if tipo == "articulos" else []
    columnas = [(x["etiqueta"], 1.2 if x["tipo"] not in ("correos",) else 2, x["tipo"] in ("entero", "numero"))
                for x in campos] + [(t, 1.8, False) for _, t in extra]

    def val(x, fila):
        n = x["nombre"]
        if x["tipo"] in ("ref", "multi"):
            return fila.get(n + "_txt") or "—"
        if x["tipo"] == "bool":
            return "Yes" if fila.get(n) else "No"
        if x["tipo"] == "opcion":
            return dict(x["opciones"]).get(fila.get(n), fila.get(n)) or "—"
        v = fila.get(n)
        return v if v not in (None, "") else "—"

    filas = [[val(x, f) for x in campos] + [f.get(k) or "—" for k, _ in extra] for f in r["items"]]
    etiquetas = {x["nombre"]: x["etiqueta"] for x in c["campos"]}
    partes = ([f"Search: {q}"] if q else []) + [f"{etiquetas.get(k, k)}: {v}" for k, v in filtros.items() if v not in (None, "")]
    texto = "Filters: " + " · ".join(partes) if partes else "No filters"
    ind = [(c["titulo"], f"{r['total']:,}")]
    if formato == "pdf":
        return documentos.pdf_reporte(c["titulo"], "Master data", texto, ind, columnas, [[str(v) for v in f] for f in filas])
    return exportar.exportar_reporte(c["titulo"], "Master data", texto, ind, columnas, filas)
