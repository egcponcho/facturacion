"""Cargas masivas desde Excel.

- Productos con sus variantes y su ficha técnica: hoja Products (una fila por
  producto: núcleo, familia, proveedor, una columna por atributo de producto y
  las columnas de la ficha, que se guardan si la ficha no está aprobada) y hoja
  Variants (una fila por variante: una columna por atributo de variante y lo
  propio de cada una). Una sola hoja con las dos cosas también se lee. Después
  el navegador corre el motor sobre los productos cargados y los clasifica.
- Cualquier catálogo de datos maestros: plantilla con sus columnas, carga
  (crea o actualiza por código) y exportación con los filtros de la pantalla.
"""
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.errores import ErrorNegocio
from app.modelos import Articulo, GrupoFamilia, Pais, Producto, Proveedor, Usuario
from app.modulos.acceso.permisos import exigir, exigir_compartido, tiene
from app.modulos.clasificacion.meta import categoria_de, valor_opcion
from app.modulos.comun.historial import registrar
from app.modulos.comun.normalizar import Referencias
from app.modulos.comun.normalizar import texto as texto_fmt
from app.modulos.documentos import documentos, exportar
from app.modulos.documentos.plantillas import hojas, leer, norm, plantilla, plantilla_hojas, si_no
from app.modulos.maestros import atributos as atr_svc
from app.modulos.maestros import catalogos as cat_svc
from app.modulos.maestros import gobierno, variantes
from app.modulos.maestros.unidades import de_articulo, normalizar
from app.modulos.productos import perfil
from app.modulos.productos.productos import (
    APROBADOS,
    MSG_CODIGO,
    codigo_valido,
    descripcion_comercial_simple,
    producto_por_generico,
)

# ---- Productos con variantes y ficha técnica -------------------------------------------
ALIAS_BASE = {
    "item_code": "sku", "sku": "sku", "codigo_de_articulo": "sku", "codigo": "sku", "article_code": "sku",
    "supplier_sku": "codigo_proveedor", "supplier_code": "codigo_proveedor", "vendor_sku": "codigo_proveedor",
    "codigo_proveedor": "codigo_proveedor", "sku_proveedor": "codigo_proveedor",
    "barcode": "codigo_barras", "upc": "codigo_barras", "gtin": "codigo_barras", "ean": "codigo_barras",
    "codigo_barras": "codigo_barras",
    "supplier": "proveedor", "proveedor": "proveedor", "unit": "unidad", "uom": "unidad", "unidad": "unidad",
    "family": "familia", "product_family": "familia", "familia": "familia",
    "type": "tipo", "active": "activo",
    "unit_weight_kg": "peso_unitario", "unit_weight": "peso_unitario", "weight_kg": "peso_unitario",
    "peso_unitario": "peso_unitario", "peso_unitario_kg": "peso_unitario", "peso": "peso_unitario",
    "commercial_name": "nombre", "product_name": "nombre", "name": "nombre", "description": "nombre",
    "category": "categoria", "product_type": "categoria", "categoria": "categoria",
    "what_it_is_for": "uso", "use": "uso", "uso": "uso", "size_range": "tallas", "tallas": "tallas",
    "country_of_origin": "pais_origen", "origin": "pais_origen", "pais_origen": "pais_origen",
    "generic_code": "generico", "generic": "generico", "generico": "generico", "codigo_generico": "generico",
    "product_code": "generico", "size_code": "sufijo", "variant_code": "sufijo", "sufijo": "sufijo",
    "proposed_hs_code": "partida", "hs_code": "partida", "partida_arancelaria": "partida",
}
# Columnas que un atributo no puede tomar (son del núcleo o de la variante)
NUCLEO = {"sku", "generico", "unidad", "nombre", "proveedor", "familia", "sufijo", "activo"}


# Una carga crea con el permiso de crear; lo que ya existe solo lo cambia quien puede editar
SIN_EDITAR = "It already exists and your role cannot edit master data: the row was not applied."

def _vocab(db: Session) -> dict:
    """Columnas de la carga: las de la ficha técnica (partes de la composición y atributos
    de clasificación, del catálogo) y una por atributo de producto y de variante de la empresa
    (por su código o su nombre), con nombres de columna únicos."""
    from app.modulos.clasificacion.meta import atributos_carga, partes_carga
    from app.modulos.productos.ficha import catalogo

    cat = catalogo(db)
    vistos: dict = {}

    def nombre(lbl, k):
        n = vistos[norm(lbl)] = vistos.get(norm(lbl), 0) + 1
        return lbl if n == 1 else f"{lbl} ({k})"
    for x in ("Category", "What it is for", "Country of origin", *ALIAS_BASE):
        vistos[norm(x)] = 1  # nombres que ya son de otras columnas
    de_producto = [(a, nombre(a.nombre, a.codigo)) for a in variantes.atributos(db, "PRODUCTO")]
    de_variante = [(a, nombre(a.nombre, a.codigo)) for a in variantes.atributos(db)]
    partes = [(a.codigo.split(".", 1)[1], nombre(a.etiqueta, a.codigo)) for a in partes_carga(db)]
    attrs = [(a, nombre(a.etiqueta, a.codigo)) for a in atributos_carga(db)]
    alias = dict(ALIAS_BASE)
    for k, lbl in partes:
        alias[norm(lbl)] = alias["comp_" + k] = "comp_" + k
    for a, lbl in attrs:
        for x in (lbl, a.etiqueta, a.codigo, *a.alias):  # su etiqueta, su código y sus otros códigos
            alias.setdefault(norm(x), "a_" + a.codigo)
        alias[norm(lbl)] = "a_" + a.codigo
    # Los atributos de la empresa ganan sobre los de la ficha con el mismo nombre
    for prefijo, lista in (("atrp.", de_producto), ("atr.", de_variante)):
        for a, lbl in lista:
            for x in (lbl, a.nombre, a.codigo, *(["brand", "marca"] if a.catalogo == "marcas" else [])):
                if alias.get(norm(x)) not in NUCLEO:
                    alias[norm(x)] = prefijo + a.codigo
    return {"cat": cat, "partes": partes, "attrs": attrs, "alias": alias, "de_producto": de_producto,
            "de_variante": de_variante}


def _cols_ficha(db: Session) -> list[dict]:
    v = _vocab(db)
    categorias = [c.nombre for c in sorted(v["cat"].categorias.values(), key=lambda c: (c.orden, c.nombre)) if c.activo]
    cols = [
        {"nombre": "Category", "opciones": categorias, "ayuda": "Technical sheet: what the product is. Required to classify.", "ancho": 30},
        {"nombre": "What it is for", "ayuda": "Short phrase, e.g. casual everyday sneaker.", "ancho": 26},
        {"nombre": "Country of origin", "ayuda": "ISO code or name (e.g. VN or Vietnam).", "ancho": 14},
    ]
    for _k, l in v["partes"]:
        cols.append({"nombre": l, "ayuda": f"Composition ({l}) with percentages, e.g. 60% cotton, 40% polyester.", "ancho": 22})
    for a, l in v["attrs"]:
        if a.booleano:
            cols.append({"nombre": l, "opciones": ["Yes", "No"], "ayuda": a.etiqueta, "ancho": 12})
        else:
            cols.append({"nombre": l, "opciones": [o.etiqueta for o in a.opciones if o.activo], "ayuda": a.etiqueta, "ancho": 22})
    cols.append({"nombre": "Proposed HS code", "ayuda": "Optional: HS code the supplier proposes. Customs reviews it.", "ancho": 14})
    return cols


def _col_atributo(db: Session, a, lbl: str) -> dict:
    col = {"nombre": lbl, "ayuda": f"{'Product' if a.nivel == 'PRODUCTO' else 'Variant'} attribute ({a.codigo}).", "ancho": 12}
    if a.tipo == "opcion":
        col["opciones"] = atr_svc.opciones(a)
    elif a.tipo == "bool":
        col["opciones"] = ["Yes", "No"]
    elif a.tipo == "catalogo" and a.catalogo == "marcas":
        from app.modelos import Marca

        col["opciones"] = [m.codigo for m in db.scalars(select(Marca).order_by(Marca.codigo))]
    elif a.tipo == "numero" and a.unidad:
        col["ayuda"] += f" Number in {a.unidad}."
    elif a.tipo == "fecha":
        col["ayuda"] += " Date YYYY-MM-DD."
    if not a.general:
        col["ayuda"] += f" Only for the families {', '.join(f.nombre for f in a.familias)} (and their subfamilies)."
    return col


def plantilla_articulos(db: Session) -> bytes:
    """Dos hojas: Products (una fila por producto, con sus atributos y su ficha técnica) y
    Variants (una fila por variante, con sus valores y lo propio de cada una)."""
    v = _vocab(db)
    provs = [p.codigo for p in db.scalars(select(Proveedor).order_by(Proveedor.codigo))]
    familias = [g.codigo for g in db.scalars(select(GrupoFamilia).order_by(GrupoFamilia.codigo))]
    gen_cols = [
        {"nombre": "Product code", "req": True, "ayuda": "Your code for the product (numbers or letters); all its variants share the technical sheet.", "ancho": 13},
        {"nombre": "Name", "ayuda": "How the product is called in lists and documents. Empty = the product code.", "ancho": 22},
        {"nombre": "Unit", "req": True, "opciones": de_articulo(), "ayuda": f"Unit of its variants: {', '.join(de_articulo())}.", "ancho": 8},
        {"nombre": "Family", "opciones": familias, "ayuda": "Optional: product family code (it says which attributes its variants use).", "ancho": 12},
        {"nombre": "Supplier", "opciones": provs, "ayuda": "Optional: supplier code. Empty for your own products.", "ancho": 10},
        *[_col_atributo(db, a, lbl) for a, lbl in v["de_producto"]],
    ] + _cols_ficha(db)
    var_cols = [
        {"nombre": "Product code", "req": True, "ayuda": "The product of the sheet Products (or one already loaded).", "ancho": 13},
        *[_col_atributo(db, a, lbl) for a, lbl in v["de_variante"]],
        {"nombre": "Item code", "ayuda": "Your item code for this variant (numbers or letters). Empty = product code + variant code.", "ancho": 14},
        {"nombre": "Variant code", "ayuda": "Only if the item code is empty: it is added to the product code. Empty = generated from the value scale or the next free one.", "ancho": 10},
        {"nombre": "Unit weight kg", "ayuda": "Net weight of one unit, without packaging: each "
         "packaging level adds its own tare in the packing list.", "ancho": 11},
        {"nombre": "Barcode", "ayuda": "GTIN, EAN or UPC.", "ancho": 15},
        {"nombre": "Supplier code", "ayuda": "The supplier's own code for this variant.", "ancho": 18},
        {"nombre": "Active", "opciones": ["Yes", "No"], "ancho": 8},
    ]
    # Ejemplo: un producto con sus datos y la primera categoría; la ficha se llena con lo que tenga cada familia
    cats = [c for c in _cols_ficha(db)[0].get("opciones") or []]
    ej_gen = ["P-1001", "Example product", de_articulo()[0], "", provs[-1] if provs else "", *[""] * len(v["de_producto"]),
              cats[0] if cats else "", "Short description of its use", "CN"]
    n = len(v["de_variante"])
    ej_var = [["P-1001", *[f"V{i}" if j == n - 1 else "" for j in range(n)], "", "", 0.8, "", "", "Yes"] for i in range(1, 3)]
    return plantilla_hojas("Products with variants and technical sheet",
                           [("Products", gen_cols, [ej_gen]), ("Variants", var_cols, ej_var)], [
        "Each product is loaded once in the sheet Products: its code, name and unit are required; the rest is optional "
        "unless your company or the product family requires it. One column per product attribute (brand, model…). "
        "Item codes follow your company's own format.",
        "Sheet Variants: one row per variant with its values (one column per variant attribute) and its own data "
        "(item code, barcode, supplier code, weight). The unit, supplier and attributes come from the product.",
        "Fill the technical sheet columns you have: the classification engine completes the rest and suggests the HS code right after the upload.",
        "Packs and kits are not loaded here: they are created from the product's variants and take their classification.",
        "Approved technical sheets are not changed by an upload; open a new version to change them.",
        "The sheets Generics and Sizes of earlier templates are still read.",
    ])


def importar_articulos(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    exigir(user, "catalogos.crear")
    gobierno.exigir_responsable(db, user, "articulos")
    return importar_por_generico(db, user, nombre, contenido)


def _paises(db: Session) -> dict:
    out = {}
    for p in db.scalars(select(Pais)):
        out[norm(p.codigo)] = p.codigo
        out[norm(p.nombre)] = p.codigo
    return out


def importar_por_generico(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Hoja Products: núcleo, atributos y ficha de cada producto. Hoja Variants: las
    variantes de cada producto con sus valores, su código, su código de barras y el del
    proveedor. Un libro de una sola hoja trae las dos cosas en cada fila."""
    edita = tiene(user, "catalogos.editar")
    from app.modulos.maestros.genericos import _exigidos_empresa, nueva_variante, siguiente_sufijo, validar_codigos

    voc = _vocab(db)
    alias = voc["alias"]
    nombres = set(hojas(nombre, contenido))
    if {"Products", "Variants", "Generics", "Sizes"} & nombres:
        gens = leer(nombre, contenido, alias, hoja="Products" if "Products" in nombres else "Generics", vacio_ok=True)
        filas_var = leer(nombre, contenido, alias, hoja="Variants" if "Variants" in nombres else "Sizes", vacio_ok=True)
        hoja_p, hoja_v = "Products", "Variants"
    else:
        # Una sola hoja: cada fila es una variante con los datos de su producto
        filas_var = leer(nombre, contenido, alias)
        gens = [{**f, "generico": f.get("generico") or f.get("sku")} for f in filas_var]
        filas_var = [{**f, "generico": f.get("generico") or f.get("sku")} for f in filas_var]
        hoja_p = hoja_v = "Row"
    provs = Referencias(db, Proveedor)
    familias = Referencias(db, GrupoFamilia)
    paises = _paises(db)
    errores, productos, vistos = [], {}, set()
    creados = actualizados = 0
    for f in gens:
        gen = (f.get("generico") or "").strip().upper()
        if gen in vistos and hoja_p == "Row":
            continue
        vistos.add(gen)
        donde = f"{hoja_p} {f['_fila']}"
        if not codigo_valido(gen):
            errores.append({"fila": donde, "mensaje": f"Product code: {MSG_CODIGO}"})
            continue
        faltan = []
        cod = texto_fmt(f.get("proveedor"))
        prov = provs.buscar(cod) if cod else None
        if cod and not prov:
            faltan.append(f"Supplier {cod} does not exist")
        elif not cod and "proveedor_id" in gobierno.obligatorios("articulos") and not user.proveedor_id:
            faltan.append("Supplier is required by your company")
        prov_id = prov.id if prov else user.proveedor_id
        if user.proveedor_id and prov_id != user.proveedor_id:
            faltan.append("You can only load your own products")
        cod = texto_fmt(f.get("familia"))
        familia = familias.buscar(cod) if cod else None
        if cod and not familia:
            faltan.append(f"Family {cod} does not exist")
        unidad = normalizar(f.get("unidad")) or (f.get("unidad") or "").strip().upper()
        if unidad not in de_articulo():
            faltan.append(f"Unit must be one of {', '.join(de_articulo())}")
        p = producto_por_generico(db, gen)
        grupo = familia if familia is not None else p.grupo_producto if p is not None else None
        valores, errs = atr_svc.validar(db, "PRODUCTO", {k[5:]: v for k, v in f.items() if k.startswith("atrp.")}, prov_id,
                                        grupo=grupo)
        valores = {k: v for k, v in valores.items() if v}
        faltan += [e["mensaje"] for e in errs]
        if p is None:
            faltan += [e["mensaje"] for e in atr_svc.exigir_empresa(db, "PRODUCTO", valores, grupo=grupo)]
        elif familia is not None and familia.id != p.grupo_producto_id:
            faltan += [e["mensaje"] for e in atr_svc.fuera_de_familia(db, p, familia)]
        if faltan:
            errores.append({"fila": donde, "mensaje": "; ".join(faltan) + "."})
            continue
        if p and not edita:
            errores.append({"fila": donde, "mensaje": SIN_EDITAR})
            continue
        if p and p.articulos and prov_id and p.proveedor_id and p.proveedor_id != prov_id:
            errores.append({"fila": donde, "mensaje": f"Product {gen} already has variants with another supplier."})
            continue
        try:
            with db.begin_nested():
                if not p:
                    p = Producto(codigo_generico=gen)
                    db.add(p)
                    creados += 1
                else:
                    actualizados += 1
                p.proveedor_id, p.unidad = prov_id or p.proveedor_id, unidad
                if familia is not None:
                    p.grupo_producto_id = familia.id
                p.nombre = (f.get("nombre") or "").strip()[:200] or p.nombre or gen
                atr_svc.poner(db, p, valores)
                db.flush()
                aviso = _ficha_desde_fila(p, {k: v for k, v in f.items() if k != "generico"}, paises, voc)
                if not (p.comex.ficha or {}).get("comManual"):
                    p.comex.descripcion_comercial = descripcion_comercial_simple(p)
                perfil.exigir_producto(db, p)
                if aviso:
                    errores.append({"fila": donde, "mensaje": aviso})
                productos[p.id] = p.comex.estado
        except IntegrityError:
            errores.append({"fila": donde, "mensaje": f"Product {gen} could not be saved (duplicated data)."})
        except ErrorNegocio as e:
            errores.append({"fila": donde, "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    var_creadas = var_act = 0
    for f in filas_var:
        donde = f"{hoja_v} {f['_fila']}"
        gen = (f.get("generico") or "").strip().upper()
        sku = (f.get("sku") or "").strip().upper()
        if not gen and sku:
            a = db.scalar(select(Articulo).where(Articulo.sku == sku))
            gen = a.generico if a else ""
        p = producto_por_generico(db, gen)
        crudos = {k[4:]: v.strip() for k, v in f.items() if k.startswith("atr.") and (v or "").strip()}
        if not p or not (crudos or sku):
            errores.append({"fila": donde, "mensaje": f"Product {gen or '(empty)'} does not exist or the row has no variant values."})
            continue
        if (f.get("tipo") or "").strip().upper() in ("PREPACK", "PACK", "KIT"):
            errores.append({"fila": donde, "mensaje": "Packs and kits are loaded with their contents in their own tab."})
            continue
        valores, errs = atr_svc.validar(db, "VARIANTE", crudos, grupo=p.grupo_producto)
        valores = {k: v for k, v in valores.items() if v}
        suf = (f.get("sufijo") or "").strip().upper()
        if sku and not codigo_valido(sku):
            errs.append({"mensaje": f"Item code: {MSG_CODIGO}"})
        barras, cod_prov = (f.get("codigo_barras") or "").strip() or None, (f.get("codigo_proveedor") or "").strip() or None
        errs += [{"mensaje": m} for m in validar_codigos(db, barras, cod_prov)]
        peso = None
        if f.get("peso_unitario"):
            try:
                peso = float(f["peso_unitario"].replace(",", ".").strip())
            except ValueError:
                errs.append({"mensaje": "Unit weight kg is not a number"})
        if errs:
            errores.append({"fila": donde, "mensaje": "; ".join(e["mensaje"] for e in errs) + "."})
            continue
        clave = {k: v.upper() for k, v in valores.items()}
        existente = (db.scalar(select(Articulo).where(Articulo.sku == (sku or gen + suf))) if sku or suf else None) or next(
            (a for a in p.articulos if a.tipo == "SOLIDO" and clave
             and {k: str(v).upper() for k, v in a.variantes.items()} == clave), None)
        if existente and not edita:
            errores.append({"fila": donde, "mensaje": SIN_EDITAR})
            continue
        try:
            with db.begin_nested():
                if existente:
                    if existente.tipo == "PREPACK":
                        raise ErrorNegocio(f"{existente.sku} is a pack or kit.", 422, "validacion")
                    if existente.producto_id != p.id:
                        raise ErrorNegocio(f"{existente.sku} belongs to product {existente.generico}.", 422, "validacion")
                    if valores:
                        existente.variantes = {**existente.variantes, **valores}
                    for tipo, v in (("BARRAS", barras), ("PROVEEDOR", cod_prov)):
                        if v:
                            existente.poner_codigo(tipo, v, p.proveedor_id if tipo == "PROVEEDOR" else None)
                    if peso is not None:
                        existente.peso_unitario = peso
                    if f.get("activo"):
                        existente.activo = si_no(f["activo"]) is not False
                    a = existente
                else:
                    ejes = variantes.ejes_de_grupo(db, p.grupo_producto)
                    base = next((valores[e] for e in reversed(ejes) if e in valores), "")
                    a = nueva_variante(db, p, sku or gen + (suf or siguiente_sufijo(db, gen, valor=base)), valores, barras,
                                       cod_prov, peso)
                    if f.get("activo"):
                        a.activo = si_no(f["activo"]) is not False
                db.flush()
                errs = _exigidos_empresa(db, a)
                if errs:
                    raise ErrorNegocio("Some data your company requires is missing.", 422, "validacion", errs)
                perfil.exigir_variantes(db, [a])
            if existente:
                var_act += 1
            else:
                var_creadas += 1
            productos[p.id] = p.comex.estado
        except IntegrityError:
            errores.append({"fila": donde, "mensaje": "Duplicated item code or code."})
        except ErrorNegocio as e:
            errores.append({"fila": donde, "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    db.flush()
    registrar(db, user, "articulos", 0, "importar_productos",
              {"productos": creados + actualizados, "variantes": var_creadas + var_act, "errores": len(errores)})
    return {"creados": var_creadas, "actualizados": var_act, "genericos_creados": creados,
            "genericos_actualizados": actualizados, "errores": errores[:300],
            "productos": [pid for pid, e in productos.items() if e not in APROBADOS], "productos_total": len(productos)}


def _ficha_desde_fila(p, f: dict, paises: dict, voc: dict) -> str | None:
    """Pasa las columnas de la ficha al producto (solo lo que viene lleno y
    solo si la ficha no está aprobada). Devuelve un aviso si algo no se entendió."""
    c = p.comex
    if c.estado in APROBADOS:
        return None
    ficha = dict(c.ficha or {})
    avisos = []
    if f.get("nombre"):
        p.nombre = f["nombre"][:200]
    if f.get("categoria"):
        k = categoria_de(object_session(p), f["categoria"])
        if k:
            c.tipo = k
            ficha.pop("_categoria", None)
        elif not c.tipo:
            ficha["_categoria"] = f["categoria"][:100]
    for k in ("uso", "tallas"):
        if f.get(k):
            ficha[k] = f[k][:200]
    if f.get("pais_origen"):
        iso = paises.get(norm(f["pais_origen"]))
        if iso:
            c.pais_origen = iso
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
            c.propuesta = d[:14]
    c.ficha = ficha
    return ("Item loaded, but: " + "; ".join(avisos) + ".") if avisos else None


# ---- Cualquier catálogo de datos maestros ------------------------------------------------
def _cols_catalogo(db: Session, tipo: str) -> list[dict]:
    c = cat_svc._cat(tipo)
    cols = []
    for x in cat_svc.campos_con_opciones(c):
        col = {"campo": x, "nombre": x["etiqueta"], "req": x["obligatorio"], "ayuda": x.get("ayuda") or ""}
        if x["tipo"] == "opcion":
            col["opciones"] = [t for _, t in x["opciones"]]
        elif x["tipo"] == "opciones":
            col["ayuda"] = (col["ayuda"] + " " if col["ayuda"] else "") + "Separated by commas: " + ", ".join(k for k, _ in x["opciones"])
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
    if tipo == "compuestos":
        return plantilla("Packs and kits", [
            {"nombre": "Pack item code", "req": True, "ayuda": "The item code of the pack or kit.", "ancho": 16},
            {"nombre": "Pack ID", "req": True, "ayuda": "Its short identifier, e.g. AB12.", "ancho": 10},
            {"nombre": "Kind", "opciones": ["PACK", "KIT"], "ayuda": "PACK: variants of one product. KIT: items of any products.", "ancho": 8},
            {"nombre": "Description", "ancho": 26},
            {"nombre": "Item code", "req": True, "ayuda": "A simple item of its contents.", "ancho": 16},
            {"nombre": "Quantity", "req": True, "ayuda": "Units of that item in one pack or kit.", "ancho": 10},
        ], None, ["One row per item of the contents: the rows with the same pack item code make one pack or kit.",
                  "A pack or kit that already exists does not change."])
    c = cat_svc._cat(tipo)
    cols = _cols_catalogo(db, tipo)
    return plantilla(c["titulo"], [{k: v for k, v in x.items() if k != "campo"} for x in cols], None, [
        c.get("ayuda") or "",
        "One row per record. A row whose code already exists updates that record; the others are created.",
    ])


def importar_catalogo(db: Session, user: Usuario, tipo: str, nombre: str, contenido: bytes) -> dict:
    edita = tiene(user, "catalogos.editar")
    exigir(user, "catalogos.crear")
    if tipo == "compuestos":
        gobierno.exigir_responsable(db, user, "articulos")
        return cat_svc.importar_compuestos(db, user, nombre, contenido)
    exigir_compartido(user, tipo)
    cat_svc.exigir_editable(tipo)
    gobierno.exigir_responsable(db, user, tipo)
    if tipo == "articulos":
        return importar_articulos(db, user, nombre, contenido)
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
        for x in cat_svc.campos_con_opciones(c):
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
        if actual and not edita:
            errores.append({"fila": f["_fila"], "mensaje": SIN_EDITAR})
            continue
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
                      formato: str, filtros_columna: dict | None = None) -> bytes:
    c = cat_svc._cat(tipo)
    r = cat_svc.listar(db, user, tipo, q, filtros, orden, 1, 100_000, filtros_columna)
    campos = cat_svc.campos_con_opciones(c)
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
        if x["tipo"] == "opciones":
            return ", ".join(dict(x["opciones"]).get(k, k) for k in fila.get(n) or []) or "—"
        v = fila.get(n)
        return v if v not in (None, "") else "—"

    filas = [[val(x, f) for x in campos] + [f.get(k) or "—" for k, _ in extra] for f in r["items"]]
    etiquetas = {x["nombre"]: x["etiqueta"] for x in campos}
    por_nombre = {x["nombre"]: x for x in campos}

    def texto_filtro(k, v):
        """Cómo se lee un valor elegido en el filtro de una columna (nombre, no id ni código)."""
        x = por_nombre.get(k)
        if v == "__vacio__":
            return "(Empty)"
        if not x:
            return v
        if x["tipo"] == "bool":
            return "Yes" if v.lower() in ("true", "1") else "No"
        if x["tipo"] == "opcion":
            return dict(x["opciones"]).get(v, v)
        if x["tipo"] in ("ref", "multi") and v.isdigit():
            obj = db.get(cat_svc.CATALOGOS[x["catalogo"]]["modelo"], int(v))
            return cat_svc._mostrar(obj) if obj else v
        return v

    partes = ([f"Search: {q}"] if q else []) + [f"{etiquetas.get(k, k)}: {v}" for k, v in filtros.items() if v not in (None, "")]
    partes += [f"{etiquetas.get(k, 'Item code' if k == 'sku' else k)}: {', '.join(texto_filtro(k, v) for v in vals)}"
               for k, vals in (filtros_columna or {}).items() if k in cat_svc.columnas_tabla(c)]
    texto = "Filters: " + " · ".join(partes) if partes else "No filters"
    ind = [(c["titulo"], f"{r['total']:,}")]
    if formato == "pdf":
        return documentos.pdf_reporte(c["titulo"], "Master data", texto, ind, columnas, [[str(v) for v in f] for f in filas])
    return exportar.exportar_reporte(c["titulo"], "Master data", texto, ind, columnas, filas)
