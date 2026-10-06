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
from sqlalchemy.orm import Session, object_session

from ..models import Articulo, GrupoArticulo, Marca, Pais, Producto, Proveedor, Usuario
from . import catalogos as cat_svc
from . import documentos, exportar
from .common import ErrorNegocio, exigir, registrar
from .normalizar import Referencias
from .normalizar import texto as texto_fmt
from .meta import categoria_de, valor_opcion
from .plantillas import hojas, leer, norm, plantilla, plantilla_hojas, si_no
from .productos import APROBADOS, asegurar_producto, descripcion_comercial_simple, producto_por_generico

# ---- Artículos con ficha técnica -------------------------------------------------------
ALIAS_BASE = {
    "item_code": "sku", "sku": "sku", "codigo_de_articulo": "sku", "codigo": "sku", "article_code": "sku",
    "supplier_sku": "sku_proveedor", "sku_proveedor": "sku_proveedor", "vendor_sku": "sku_proveedor",
    "upc": "upc", "style": "estilo", "estilo": "estilo", "color": "color", "size": "talla", "talla": "talla",
    "brand": "marca", "marca": "marca", "item_group": "grupo", "group": "grupo", "grupo": "grupo",
    "supplier": "proveedor", "proveedor": "proveedor", "unit": "unidad", "uom": "unidad", "unidad": "unidad",
    "type": "tipo", "active": "activo",
    "unit_weight_kg": "peso_unitario", "unit_weight": "peso_unitario", "weight_kg": "peso_unitario",
    "peso_unitario": "peso_unitario", "peso_unitario_kg": "peso_unitario", "peso": "peso_unitario",
    "commercial_name": "nombre", "product_name": "nombre", "name": "nombre", "description": "nombre",
    "category": "categoria", "product_type": "categoria", "categoria": "categoria",
    "gender": "genero", "genero": "genero", "who_it_is_for": "edad", "age": "edad", "edad": "edad",
    "what_it_is_for": "uso", "use": "uso", "uso": "uso", "size_range": "tallas", "tallas": "tallas",
    "country_of_origin": "pais_origen", "origin": "pais_origen", "pais_origen": "pais_origen",
    "generic_code": "codigo_generico", "proposed_hs_code": "partida", "hs_code": "partida", "partida_arancelaria": "partida",
}


def _vocab(db: Session) -> dict:
    """Partes de la composición y atributos de la ficha que van en la carga
    (del catálogo), con nombres de columna únicos, y el género y la edad."""
    from .meta import atributos_carga, partes_carga
    from .ficha import catalogo

    cat = catalogo(db)
    vistos: dict = {}

    def nombre(lbl, k):
        n = vistos[norm(lbl)] = vistos.get(norm(lbl), 0) + 1
        return lbl if n == 1 else f"{lbl} ({k})"
    gen = cat.por_codigo.get("genero")
    edad = cat.por_codigo.get("edadNac")
    for x in ("Category", "Gender", "Who it is for", "What it is for", "Country of origin", *ALIAS_BASE):
        vistos[norm(x)] = 1  # nombres que ya son de otras columnas
    partes = [(a.codigo.split(".", 1)[1], nombre(a.etiqueta, a.codigo)) for a in partes_carga(db)]
    attrs = [(a, nombre(a.etiqueta, a.codigo)) for a in atributos_carga(db) if a.codigo not in ("genero", "edadNac")]
    alias = dict(ALIAS_BASE)
    for k, lbl in partes:
        alias[norm(lbl)] = alias["comp_" + k] = "comp_" + k
    for a, lbl in attrs:
        alias[norm(lbl)] = alias[norm(a.codigo)] = "a_" + a.codigo
    return {"cat": cat, "partes": partes, "attrs": attrs, "alias": alias,
            "genero": {o.codigo: o.etiqueta for o in gen.opciones if o.activo} if gen else {},
            "edad": {o.codigo: o.etiqueta for o in edad.opciones if o.activo} if edad else {}}


def _cols_ficha(db: Session) -> list[dict]:
    v = _vocab(db)
    categorias = [c.nombre for c in sorted(v["cat"].categorias.values(), key=lambda c: (c.orden, c.nombre)) if c.activo]
    cols = [
        {"nombre": "Category", "opciones": categorias, "ayuda": "Technical sheet: what the product is. Required to classify.", "ancho": 30},
        {"nombre": "Gender", "opciones": list(v["genero"].values()), "ancho": 10},
        {"nombre": "Who it is for", "opciones": list(v["edad"].values()), "ancho": 12},
        {"nombre": "What it is for", "ayuda": "Short phrase, e.g. casual everyday sneaker.", "ancho": 26},
        {"nombre": "Country of origin", "ayuda": "ISO code or name (e.g. VN or Vietnam).", "ancho": 14},
    ]
    for k, l in v["partes"]:
        cols.append({"nombre": l, "ayuda": f"Composition of the {l.lower()} with percentages, e.g. 60% cotton, 40% polyester.", "ancho": 22})
    for a, l in v["attrs"]:
        if a.booleano:
            cols.append({"nombre": l, "opciones": ["Yes", "No"], "ayuda": a.etiqueta, "ancho": 12})
        else:
            cols.append({"nombre": l, "opciones": [o.etiqueta for o in a.opciones if o.activo], "ayuda": a.etiqueta, "ancho": 22})
    cols.append({"nombre": "Proposed HS code", "ayuda": "Optional: HS code the supplier proposes. Customs reviews it.", "ancho": 14})
    return cols


def plantilla_articulos(db: Session) -> bytes:
    """Dos hojas: Generics (una fila por genérico, con su ficha técnica) y
    Sizes (una fila por talla, con lo propio de cada una)."""
    marcas = [m.codigo for m in db.scalars(select(Marca).order_by(Marca.codigo))]
    grupos = [g.codigo for g in db.scalars(select(GrupoArticulo).order_by(GrupoArticulo.codigo))]
    provs = [p.codigo for p in db.scalars(select(Proveedor).order_by(Proveedor.codigo))]
    gen_cols = [
        {"nombre": "Generic code", "req": True, "ayuda": "Your code for the style-color (numbers or letters); all its sizes share the technical sheet.", "ancho": 13},
        {"nombre": "Style", "req": True, "ancho": 12}, {"nombre": "Color", "req": True, "ancho": 14},
        {"nombre": "Brand", "req": True, "opciones": marcas, "ayuda": "Brand code.", "ancho": 10},
        {"nombre": "Item group", "req": True, "opciones": grupos, "ayuda": "Group code (packing rule).", "ancho": 12},
        {"nombre": "Supplier", "req": True, "opciones": provs, "ayuda": "Supplier code.", "ancho": 10},
        {"nombre": "Unit", "req": True, "opciones": ["PAR", "UN"], "ayuda": "PAR (pairs) or UN (units) of its sizes.", "ancho": 8},
    ] + _cols_ficha(db)
    tallas_cols = [
        {"nombre": "Generic code", "req": True, "ayuda": "The generic of the sheet Generics (or one already loaded).", "ancho": 13},
        {"nombre": "Size", "req": True, "ayuda": "e.g. 8, 8.5, M, OS.", "ancho": 8},
        {"nombre": "Item code", "ayuda": "Your item code for this size (numbers or letters). Empty = generic + size code.", "ancho": 14},
        {"nombre": "Size code", "ayuda": "Only if the item code is empty: it is added to the generic. Empty = generated (numeric sizes × 10: 7 → 070; others 001, 002…).", "ancho": 10},
        {"nombre": "Unit weight kg", "ayuda": "Net weight of one unit (pair or piece), without packaging: each "
         "packaging level adds its own tare in the packing list.", "ancho": 11},
        {"nombre": "UPC", "ancho": 15},
        {"nombre": "Supplier SKU", "ayuda": "The supplier's own code (e.g. VN0A5KRFBLK-8).", "ancho": 18},
        {"nombre": "Active", "opciones": ["Yes", "No"], "ancho": 8},
    ]
    ej_gen = ["30095129", "VN0A5KRF", "Black", marcas[-1] if marcas else "", grupos[0] if grupos else "",
              provs[-1] if provs else "", "PAR", "Footwear: sneakers, boots, shoes, sandals", "Unisex",
              "Adult", "Casual skate sneaker", "VN", "", "", "", "100% canvas", "100% rubber", "100% textile", "100% EVA"]
    ej_tallas = [["30095129", t, "", f"{int(t) * 10:03d}", 0.8, f"01960129{i:04d}", f"VN0A5KRFBLK-{t}", "Yes"]
                 for i, t in enumerate(["8", "9", "10"], 1)]
    return plantilla_hojas("Items by generic, with technical sheet",
                           [("Generics", gen_cols, [ej_gen]), ("Sizes", tallas_cols, ej_tallas)], [
        "The generic groups the sizes of one style-color: classification and technical sheet are per generic, "
        "so they are loaded once in the sheet Generics. Item codes follow your company's own format.",
        "Sheet Sizes: one row per size of each generic with its own data (size code, UPC, supplier SKU). "
        "The style, color, brand, group, supplier and unit come from the generic.",
        "Fill the technical sheet columns you have: the classification engine completes the rest and suggests the HS code right after the upload.",
        "Prepacks are not loaded here: they are created with the generic of their solids in Master data → Prepacks and take their classification.",
        "Approved technical sheets are not changed by an upload; open a new version to change them.",
    ])


def importar_articulos(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    exigir(user, "catalogos.crear")
    if "Generics" in hojas(nombre, contenido) or "Sizes" in hojas(nombre, contenido):
        return importar_por_generico(db, user, nombre, contenido)
    return _importar_por_articulo(db, user, nombre, contenido)


def _paises(db: Session) -> dict:
    out = {}
    for p in db.scalars(select(Pais)):
        out[norm(p.codigo)] = p.codigo
        out[norm(p.nombre)] = p.codigo
    return out


def importar_por_generico(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Hoja Generics: datos maestros y ficha de cada genérico. Hoja Sizes:
    las tallas de cada genérico con su código, UPC y SKU del proveedor."""
    from .genericos import siguiente_sufijo, _articulos
    from .productos import MSG_CODIGO, codigo_valido

    voc = _vocab(db)
    alias = {**voc["alias"], "generic_code": "generico", "generic": "generico", "generico": "generico",
             "size_code": "sufijo", "sufijo": "sufijo"}
    gens = leer(nombre, contenido, alias, hoja="Generics", vacio_ok=True)
    tallas = leer(nombre, contenido, alias, hoja="Sizes", vacio_ok=True)
    # Marca, grupo y proveedor por código o nombre, escritos de cualquier forma
    cods = {"marca": Referencias(db, Marca), "grupo": Referencias(db, GrupoArticulo), "proveedor": Referencias(db, Proveedor)}
    paises = _paises(db)
    errores, productos = [], {}
    creados = actualizados = 0
    for f in gens:
        gen = (f.get("generico") or "").strip().upper()
        if not codigo_valido(gen):
            errores.append({"fila": f"Generics {f['_fila']}", "mensaje": f"Generic code: {MSG_CODIGO}"})
            continue
        faltan, ids = [], {}
        for campo, lbl in (("marca", "Brand"), ("grupo", "Item group"), ("proveedor", "Supplier")):
            cod = texto_fmt(f.get(campo))
            obj = cods[campo].buscar(cod)
            if not obj:
                faltan.append(f"{lbl} {cod or '(empty)'} does not exist")
            ids[campo] = obj.id if obj else None
        unidad = (f.get("unidad") or "").strip().upper()
        if unidad not in ("PAR", "UN"):
            faltan.append("Unit must be PAR or UN")
        estilo, color = (f.get("estilo") or "").strip().upper(), (f.get("color") or "").strip()
        if not estilo or not color:
            faltan.append("Style and color are required")
        if faltan:
            errores.append({"fila": f"Generics {f['_fila']}", "mensaje": "; ".join(faltan) + "."})
            continue
        p = producto_por_generico(db, gen)
        if p and db.scalar(_articulos(db, gen).limit(1)) and (p.estilo != estilo or (p.color or "") != color or p.proveedor_id != ids["proveedor"]):
            errores.append({"fila": f"Generics {f['_fila']}", "mensaje": f"Generic {gen} already exists as {p.estilo} {p.color}."})
            continue
        try:
            with db.begin_nested():
                if not p:
                    p = Producto(codigo_generico=gen, ficha={}, faltan=[], alertas_ok=[])
                    db.add(p)
                    creados += 1
                else:
                    actualizados += 1
                p.estilo, p.color, p.proveedor_id = estilo, color, ids["proveedor"]
                p.marca_id, p.grupo_id, p.unidad = ids["marca"], ids["grupo"], unidad
                db.flush()
                aviso = _ficha_desde_fila(p, {k: v for k, v in f.items() if k != "codigo_generico"}, paises, voc)
                if not (p.ficha or {}).get("comManual"):
                    p.descripcion_comercial = descripcion_comercial_simple(p)
                if aviso:
                    errores.append({"fila": f"Generics {f['_fila']}", "mensaje": aviso})
                productos[p.id] = p.estado
        except IntegrityError:
            errores.append({"fila": f"Generics {f['_fila']}", "mensaje": f"{estilo} {color} already exists with another generic."})
    cat = cat_svc.CATALOGOS["articulos"]
    tallas_creadas = tallas_act = 0
    for f in tallas:
        gen = (f.get("generico") or "").strip().upper()
        sku = (f.get("sku") or "").strip().upper()
        if not gen and sku:
            gen = (db.scalar(select(Articulo.generico).where(Articulo.sku == sku)) or "")
        p = producto_por_generico(db, gen)
        talla = (f.get("talla") or "").strip().upper()
        if not p or not talla:
            errores.append({"fila": f"Sizes {f['_fila']}", "mensaje": f"Generic {gen or '(empty)'} does not exist or the size is empty."})
            continue
        suf = (f.get("sufijo") or "").strip().upper()
        if sku and not codigo_valido(sku):
            errores.append({"fila": f"Sizes {f['_fila']}", "mensaje": f"Item code: {MSG_CODIGO}"})
            continue
        existente = (db.scalar(select(Articulo).where(Articulo.sku == (sku or gen + suf))) if sku or suf else None) or db.scalar(
            _articulos(db, gen).where(Articulo.tipo == "SOLIDO", Articulo.talla == talla))
        datos = {"sku": existente.sku if existente else sku or gen + (suf or siguiente_sufijo(db, gen, talla=talla)), "generico": gen,
                 "estilo": p.estilo, "color": p.color, "talla": talla, "marca_id": p.marca_id, "grupo_id": p.grupo_id,
                 "proveedor_id": p.proveedor_id, "tipo": "SOLIDO", "unidad": p.unidad or "UN"}
        for k in ("upc", "sku_proveedor"):
            if f.get(k):
                datos[k] = f[k].strip()
        if f.get("peso_unitario"):
            datos["peso_unitario"] = f["peso_unitario"].replace(",", ".").strip()
        if f.get("activo"):
            datos["activo"] = si_no(f["activo"]) is not False
        try:
            with db.begin_nested():
                if existente:
                    if existente.tipo == "PREPACK":
                        raise ErrorNegocio(f"{existente.sku} is a prepack.", 422, "validacion")
                    for k, v in cat_svc._limpiar(db, cat, datos, parcial=True, actual=existente).items():
                        setattr(existente, k, v)
                    tallas_act += 1
                else:
                    a = Articulo(**cat_svc._limpiar(db, cat, datos, parcial=False), activo=datos.get("activo", True))
                    db.add(a)
                    db.flush()
                    asegurar_producto(db, a)
                    tallas_creadas += 1
                productos[p.id] = p.estado
        except IntegrityError:
            errores.append({"fila": f"Sizes {f['_fila']}", "mensaje": "Duplicated item code or UPC."})
        except ErrorNegocio as e:
            errores.append({"fila": f"Sizes {f['_fila']}", "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    db.flush()
    registrar(db, user, "articulos", 0, "importar_genericos",
              {"genericos": creados + actualizados, "tallas": tallas_creadas + tallas_act, "errores": len(errores)})
    return {"creados": tallas_creadas, "actualizados": tallas_act, "genericos_creados": creados,
            "genericos_actualizados": actualizados, "errores": errores[:300],
            "productos": [pid for pid, e in productos.items() if e not in APROBADOS], "productos_total": len(productos)}


def _importar_por_articulo(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Formato de una sola hoja: una fila por artículo (talla) con su ficha."""
    voc = _vocab(db)
    filas = leer(nombre, contenido, voc["alias"])
    cods = {
        "marca": {m.codigo: m.id for m in db.scalars(select(Marca))},
        "grupo": {g.codigo: g.id for g in db.scalars(select(GrupoArticulo))},
        "proveedor": {p.codigo: p.id for p in db.scalars(select(Proveedor))},
    }
    paises = _paises(db)
    cat = cat_svc.CATALOGOS["articulos"]
    creados = actualizados = 0
    errores, productos = [], {}
    for f in filas:
        tipo_art = (f.get("tipo") or "SOLIDO").strip().upper()
        if tipo_art == "PREPACK":
            errores.append({"fila": f["_fila"], "mensaje": "Prepacks are loaded in Master data → Prepacks with their breakdown."})
            continue
        datos = {k: f.get(k, "") for k in ("sku", "sku_proveedor", "estilo", "color", "talla", "upc") if f.get(k, "") != ""}
        if f.get("codigo_generico"):
            datos["generico"] = f["codigo_generico"].strip().upper()
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
        existente = db.scalar(select(Articulo).where(Articulo.sku == (datos.get("sku") or "").strip().upper()))
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
                    aviso = _ficha_desde_fila(prod, f, paises, voc)
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


def _ficha_desde_fila(p, f: dict, paises: dict, voc: dict) -> str | None:
    """Pasa las columnas de la ficha al producto (solo lo que viene lleno y
    solo si la ficha no está aprobada). Devuelve un aviso si algo no se entendió."""
    if p.estado in APROBADOS:
        return None
    ficha = dict(p.ficha or {})
    avisos = []
    if f.get("nombre"):
        p.nombre = f["nombre"][:200]
    if f.get("categoria"):
        k = categoria_de(object_session(p), f["categoria"])
        if k:
            p.tipo = k
            ficha.pop("_categoria", None)
        elif not p.tipo:
            ficha["_categoria"] = f["categoria"][:100]
    if f.get("genero"):
        g = valor_opcion(voc["genero"], f["genero"])
        if g:
            ficha["genero"] = g
        else:
            avisos.append(f"Gender “{f['genero']}” not recognized")
    if f.get("edad"):
        e = valor_opcion(voc["edad"], f["edad"])
        if e:
            ficha["edadNac"] = e
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
    for k, _ in voc["partes"]:
        if f.get("comp_" + k):
            comp[k] = f["comp_" + k][:300]
    if comp:
        ficha["comp"] = comp
    for a, lbl in voc["attrs"]:
        v = f.get("a_" + a.codigo)
        if not v:
            continue
        if a.booleano:
            b = si_no(v)
            if b is None:
                avisos.append(f"{lbl}: write Yes or No")
            else:
                ficha[a.codigo] = b
        else:
            x = valor_opcion({o.codigo: o.etiqueta for o in a.opciones if o.activo}, v)
            if x:
                ficha[a.codigo] = x
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
    exigir(user, "catalogos.crear")
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
    refs_cache: dict = {}
    # Registro existente: por su código escrito de cualquier forma (" tnf" = "TNF")
    existentes = Referencias(db, modelo, ("codigo",)) if clave else None
    for f in filas:
        datos, mal = {}, None
        for x in c["campos"]:
            n = x["nombre"]
            if n not in f or f[n] == "":
                continue
            v = texto_fmt(f[n])
            if x["tipo"] == "opcion":
                v = next((k for k, t in x["opciones"] if norm(v) in (norm(k), norm(t))), v)
            elif x["tipo"] == "bool":
                v = si_no(v) is not False
            elif x["tipo"] in ("ref", "multi"):
                # Por código o nombre, escrito de cualquier forma (sin duplicar registros)
                refs = refs_cache.setdefault(x["catalogo"], Referencias(
                    db, cat_svc.CATALOGOS[x["catalogo"]]["modelo"], ("sku",) if x["catalogo"] == "articulos" else ("codigo", "nombre")))
                cods = [s.strip() for s in re.split(r"[,;]", v) if s.strip()] if x["tipo"] == "multi" else [v]
                objs = [refs.buscar(cd) for cd in cods]
                if None in objs:
                    mal = f"{x['etiqueta']}: {cods[objs.index(None)]} does not exist."
                    break
                v = [o.id for o in objs] if x["tipo"] == "multi" else objs[0].id
            datos[n] = v
        if mal:
            errores.append({"fila": f["_fila"], "mensaje": mal})
            continue
        actual = None
        if clave and datos.get(clave):
            actual = existentes.buscar(datos[clave])
            if actual:
                datos[clave] = actual.codigo
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
        if x["tipo"] in ("ref", "multi", "pasos"):
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
