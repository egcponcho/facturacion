"""Mantenimiento de datos maestros desde un solo lugar.

Cada catálogo se describe una vez (campos, tipos, obligatorios, filtros) y
el mismo código sirve para listar, filtrar, ordenar, crear, editar y
eliminar. La interfaz usa esa misma descripción para dibujar formularios y
tablas, así que agregar un campo aquí lo agrega en pantalla.
"""
import csv
import io
import re

from openpyxl import load_workbook
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    Almacen,
    Articulo,
    Centro,
    Contacto,
    GrupoArticulo,
    Marca,
    Pais,
    Prepack,
    PrepackComponente,
    Proveedor,
    Puerto,
    Sociedad,
    TipoUnidad,
    Transportista,
    Usuario,
)
from .common import ErrorNegocio, exigir, registrar
from .productos import asegurar_producto, fmt_codigo

UNIDADES = [["PAR", "Pairs"], ["UN", "Units"], ["CJ", "Cartons (prepack)"]]
CATEGORIAS = [["CALZADO", "Footwear"], ["ROPA", "Apparel"], ["ACCESORIO", "Accessories"]]


def c(nombre, etiqueta, tipo="texto", obligatorio=False, **extra):
    return {"nombre": nombre, "etiqueta": etiqueta, "tipo": tipo, "obligatorio": obligatorio, **extra}


# tipo: texto | entero | numero | bool | opcion (opciones) | ref (catalogo: guarda el id)
#       | codigo (catalogo: guarda el código, p. ej. país ISO) | correos
#       | multi (catalogo: varios registros, p. ej. las marcas de un proveedor)
MODOS = [["MARITIMO", "Ocean"], ["AEREO", "Air"], ["TERRESTRE", "Road"]]
CATALOGOS = {
    "sociedades": {
        "modelo": Sociedad, "titulo": "Companies", "singular": "company",
        "ayuda": "Companies that are invoiced (the PO company). Each one has its assigned plants.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("razon_social", "Legal name"),
            c("id_fiscal", "Tax ID"),
            c("pais", "Country", "codigo", catalogo="paises", filtro=True),
            c("moneda", "Currency", obligatorio=True, max=3, mayus=True),
            c("direccion", "Address"),
            c("correos", "Billing emails", "correos", ayuda="One or more, separated by commas."),
            c("activa", "Active", "bool", filtro=True),
        ],
        "extras": [{"nombre": "centros_txt", "etiqueta": "Plants", "catalogo": "centros", "filtro": "sociedad_id"},
                   {"nombre": "contactos", "etiqueta": "Contacts", "catalogo": "contactos", "filtro": "sociedad_id"}],
        "buscar": ["codigo", "nombre", "razon_social", "id_fiscal"],
    },
    "centros": {
        "modelo": Centro, "titulo": "Plants", "singular": "plant",
        "ayuda": "Plants assigned to each company. A plant is the shipment notify party and, as the PO destination center "
                 "(e.g. 2220), it tells which country the goods go to. Its port is the arrival port.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("sociedad_id", "Company", "ref", obligatorio=True, catalogo="sociedades", filtro=True),
            c("nombre", "Name", obligatorio=True),
            c("pais", "Country", "codigo", obligatorio=True, catalogo="paises", filtro=True),
            c("puerto", "Arrival port", "codigo", catalogo="puertos", filtro=True),
            c("tipo", "Type", "opcion", obligatorio=True,
              opciones=[["BODEGA_FISCAL", "Bonded warehouse"], ["ZONA_FRANCA", "Free trade zone"], ["LOCAL", "Local warehouse"],
                        ["TIENDA", "Store / DC"]]),
            c("puertos", "Other arrival ports", "multi", catalogo="puertos",
              ayuda="Besides the main one. The shipment suggests the main port and lets you switch between these."),
            c("direccion", "Address"),
            c("correos", "Emails (notify)", "correos", ayuda="One or more, separated by commas."),
            c("activo", "Active", "bool", filtro=True),
        ],
        "extras": [{"nombre": "contactos", "etiqueta": "Contacts", "catalogo": "contactos", "filtro": "centro_id"}],
        "buscar": ["codigo", "nombre"],
    },
    "almacenes": {
        "modelo": Almacen, "titulo": "Storage locations", "singular": "storage location",
        "ayuda": "Inventory split in the system (virtual, retail, wholesale); it is not a physical place. "
                 "Each PO line states its own.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("sociedad_id", "Company", "ref", obligatorio=True, catalogo="sociedades", filtro=True),
            c("nombre", "Name", obligatorio=True),
            c("tipo", "Type", "opcion", obligatorio=True, filtro=True,
              opciones=[["VIRTUAL", "Virtual"], ["DETALLE", "Retail"], ["MAYOREO", "Wholesale"]]),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "contactos": {
        "modelo": Contacto, "titulo": "Contacts", "singular": "contact",
        "ayuda": "Contact people of a company (billing) or of a plant (notify party). "
                 "They appear on the invoice and the packing list.",
        "campos": [
            c("nombre", "Name", obligatorio=True),
            c("cargo", "Job title"),
            c("rol", "Role", "opcion", obligatorio=True, filtro=True,
              opciones=[["FACTURACION", "Billing"], ["NOTIFY", "Notify party"], ["LOGISTICA", "Logistics"]]),
            c("sociedad_id", "Company", "ref", catalogo="sociedades", filtro=True),
            c("centro_id", "Plant", "ref", catalogo="centros", filtro=True),
            c("correos", "Emails", "correos", obligatorio=True, ayuda="One or more, separated by commas."),
            c("telefono", "Phone"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["nombre", "cargo", "correos"],
    },
    "paises": {
        "modelo": Pais, "titulo": "Countries", "singular": "country",
        "ayuda": "Countries of origin and shipment (2-letter ISO).",
        "campos": [
            c("codigo", "ISO code", obligatorio=True, max=2, mayus=True, patron=r"^[A-Z]{2}$",
              mensaje_patron="Use the 2-letter ISO code."),
            c("nombre", "Name", obligatorio=True),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "puertos": {
        "modelo": Puerto, "titulo": "Ports", "singular": "port",
        "ayuda": "Sea ports and airports (UN/LOCODE).",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("pais", "Country", "codigo", obligatorio=True, catalogo="paises", filtro=True),
            c("tipo", "Type", "opcion", obligatorio=True, filtro=True,
              opciones=[["MARITIMO", "Ocean"], ["AEREO", "Air"], ["TERRESTRE", "Road"]]),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "marcas": {
        "modelo": Marca, "titulo": "Brands", "singular": "brand",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("activa", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "grupos": {
        "modelo": GrupoArticulo, "titulo": "Item groups", "singular": "group",
        "ayuda": "Each item belongs to a single group. The category sets the packing rule.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=15, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("categoria", "Category", "opcion", obligatorio=True, opciones=CATEGORIAS, filtro=True),
            c("activo", "Active", "bool", filtro=True),
        ],
        "extras": [{"nombre": "articulos", "etiqueta": "Items", "catalogo": "articulos", "filtro": "grupo_id"}],
        "buscar": ["codigo", "nombre"],
    },
    "proveedores": {
        "modelo": Proveedor, "titulo": "Suppliers", "singular": "supplier",
        "ayuda": "Exporters. Each one handles its own brands and items and works with the assigned companies.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=30, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("razon_social", "Legal name"),
            c("id_fiscal", "Tax ID"),
            c("pais", "Country", "codigo", catalogo="paises", filtro=True),
            c("direccion", "Address"),
            c("contacto", "Contact"),
            c("correos", "Emails", "correos", ayuda="One or more, separated by commas."),
            c("telefono", "Phone"),
            c("marcas", "Brands handled", "multi", catalogo="marcas", filtro=True),
            c("sociedades", "Companies it works with", "multi", catalogo="sociedades", filtro=True),
            c("activo", "Active", "bool", filtro=True),
        ],
        "extras": [{"nombre": "articulos", "etiqueta": "Items", "catalogo": "articulos", "filtro": "proveedor_id"}],
        "buscar": ["codigo", "nombre", "razon_social"],
    },
    "transportistas": {
        "modelo": Transportista, "titulo": "Carriers", "singular": "carrier",
        "ayuda": "Registered shipping lines, airlines and road carriers, with the companies they work for.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=20, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("tipo", "Type", "opcion", obligatorio=True, filtro=True, opciones=MODOS + [["MULTIMODAL", "Multimodal"]]),
            c("codigo_internacional", "SCAC / IATA", max=10, mayus=True,
              ayuda="Shipping line SCAC or airline IATA prefix."),
            c("id_fiscal", "Tax ID"),
            c("pais", "Country", "codigo", catalogo="paises"),
            c("contacto", "Contact"),
            c("correos", "Emails", "correos"),
            c("telefono", "Phone"),
            c("sociedades", "Companies it works with", "multi", catalogo="sociedades", obligatorio=True,
              filtro=True),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre", "codigo_internacional"],
    },
    "tipos_unidad": {
        "modelo": TipoUnidad, "titulo": "Unit types", "singular": "unit type",
        "ayuda": "Load units by transport mode with their capacity. A shipment only offers those of its mode; "
                 "the service (FCL, LCL…) belongs to each unit, so a shipment can be mixed.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("modo", "Transport mode", "opcion", obligatorio=True, filtro=True, opciones=MODOS),
            c("modalidad", "Service", "opcion", obligatorio=True, filtro=True,
              opciones=[["FCL", "FCL · full container"], ["LCL", "LCL · consolidated cargo"],
                        ["AEREO", "Air cargo"], ["FTL", "FTL · full truck"], ["LTL", "LTL · partial load"]]),
            c("capacidad_cbm", "Max volume (m³)", "numero", minimo=0),
            c("capacidad_kg", "Max weight (kg)", "numero", minimo=0),
            c("requiere_sello", "Requires seal", "bool"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "articulos": {
        "modelo": Articulo, "titulo": "Items", "singular": "item",
        "ayuda": "Master data of each item with its unit of measure. Solids are created here; casepack and inner "
                 "pack come on each PO line. Prepacks are created in the Prepacks tab with their breakdown.",
        "campos": [
            c("sku", "Item number (SKU)", obligatorio=True, max=18, patron=r"^\d{6,18}$",
              mensaje_patron="Digits only, for example 30095120001."),
            c("estilo", "Style", obligatorio=True, mayus=True),
            c("color", "Color", obligatorio=True),
            c("talla", "Size / prepack ID", obligatorio=True, mayus=True,
              ayuda="For a prepack it is its prepack ID, e.g. AB12."),
            c("descripcion", "Description"),
            c("marca_id", "Brand", "ref", obligatorio=True, catalogo="marcas", filtro=True),
            c("grupo_id", "Group", "ref", obligatorio=True, catalogo="grupos", filtro=True),
            c("proveedor_id", "Supplier", "ref", obligatorio=True, catalogo="proveedores", filtro=True,
              ayuda="Each supplier handles its items; the brand must be one of theirs."),
            c("tipo", "Type", "opcion", obligatorio=True, filtro=True,
              opciones=[["SOLIDO", "Solid"], ["PREPACK", "Prepack"]]),
            c("unidad", "Unit", "opcion", obligatorio=True, opciones=UNIDADES, filtro=True),
            c("upc", "UPC"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["sku", "estilo", "color", "upc", "descripcion"],
    },
    "prepacks": {
        "modelo": Prepack, "titulo": "Prepacks (assortments)", "singular": "prepack",
        "ayuda": "A prepack is an item with its own product code. Its assortment (breakdown) spreads "
                 "sizes and quantities per master carton with solids of the same style and color, and its prepack ID "
                 "(usually 2 letters and 2 digits, e.g. AB12) is its size. The breakdown can be viewed but not changed.",
        "campos": [
            c("codigo", "Prepack ID", obligatorio=True, max=10, mayus=True, patron=r"^[A-Z0-9]{2,10}$",
              mensaje_patron="Letters and numbers only, e.g. AB12."),
            c("estilo", "Style", obligatorio=True, mayus=True, filtro=True),
            c("color", "Color", obligatorio=True),
            c("descripcion", "Description"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "estilo", "color", "descripcion"],
    },
}
ORDEN_CATALOGOS = ["articulos", "prepacks", "marcas", "grupos", "proveedores", "sociedades", "centros",
                   "contactos", "almacenes", "transportistas", "tipos_unidad", "paises", "puertos"]
CORREO = r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$"


def _cat(tipo: str) -> dict:
    if tipo not in CATALOGOS:
        raise ErrorNegocio("The catalog does not exist.", 404, "no_encontrado")
    return CATALOGOS[tipo]


def _mostrar(obj) -> str:
    """Texto corto para mostrar un registro referido."""
    if isinstance(obj, Prepack):
        return f"{obj.codigo} · {obj.estilo} {obj.color or ''}".strip()
    if isinstance(obj, Contacto):
        return obj.nombre
    for a, b in (("codigo", "nombre"), ("sku", "estilo"), ("codigo", "descripcion")):
        if hasattr(obj, a):
            extra = getattr(obj, b, None)
            return f"{getattr(obj, a)} · {extra}" if extra else str(getattr(obj, a))
    return str(obj.id)


def meta(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "catalogos.ver")
    return [{"tipo": t, "titulo": CATALOGOS[t]["titulo"], "singular": CATALOGOS[t]["singular"],
             "ayuda": CATALOGOS[t].get("ayuda"), "campos": CATALOGOS[t]["campos"],
             "extras": CATALOGOS[t].get("extras", []),
             "total": db.scalar(select(func.count()).select_from(CATALOGOS[t]["modelo"])) or 0}
            for t in ORDEN_CATALOGOS]


def _fila(cat: dict, obj, refs: dict) -> dict:
    fila = {"id": obj.id}
    for campo in cat["campos"]:
        v = getattr(obj, campo["nombre"])
        if campo["tipo"] == "multi":
            fila[campo["nombre"]] = [x.id for x in v]
            fila[campo["nombre"] + "_txt"] = ", ".join(x.codigo for x in v) or None
            continue
        fila[campo["nombre"]] = v
        if campo["tipo"] == "ref" and v:
            fila[campo["nombre"] + "_txt"] = refs.get((campo["catalogo"], v))
    if isinstance(obj, Articulo):
        # La ficha técnica y la partida viven en el producto (estilo-color)
        prod = obj.producto
        fila["producto_id"] = obj.producto_id
        fila["partida_txt"] = fmt_codigo(prod.codigo) if prod and prod.codigo else None
        fila["clasificacion"] = prod.estado if prod else None
    if isinstance(obj, Prepack):
        fila["total"] = obj.total
        fila["componentes"] = len(obj.componentes)
        fila["sku"] = refs.get(("_sku_prepack", obj.id))
    # Relaciones hijas: centros de la sociedad, artículos del grupo, contactos
    if isinstance(obj, Sociedad):
        fila["centros_txt"] = ", ".join(c.codigo for c in obj.centros) or None
    for ex in cat.get("extras", []):
        if ex["nombre"] != "centros_txt":
            fila[ex["nombre"]] = refs.get(("_" + ex["nombre"], obj.id), 0)
    return fila


def _refs(db: Session, cat: dict, objs: list) -> dict:
    refs = {}
    ids_obj = [o.id for o in objs]
    if cat["modelo"] is Prepack and ids_obj:
        for pid, sku in db.execute(select(Articulo.prepack_id, Articulo.sku).where(Articulo.prepack_id.in_(ids_obj))):
            refs[("_sku_prepack", pid)] = sku
    for ex in cat.get("extras", []):
        if ex["nombre"] == "centros_txt" or not ids_obj:
            continue
        hijo = CATALOGOS[ex["catalogo"]]["modelo"]
        col = getattr(hijo, ex["filtro"])
        for padre, n in db.execute(select(col, func.count()).where(col.in_(ids_obj)).group_by(col)):
            refs[("_" + ex["nombre"], padre)] = n
    for campo in cat["campos"]:
        if campo["tipo"] != "ref":
            continue
        ids = {getattr(o, campo["nombre"]) for o in objs} - {None}
        if not ids:
            continue
        modelo = CATALOGOS[campo["catalogo"]]["modelo"]
        for r in db.scalars(select(modelo).where(modelo.id.in_(ids))).all():
            refs[(campo["catalogo"], r.id)] = _mostrar(r)
    return refs


def listar(db: Session, user: Usuario, tipo: str, q: str | None, filtros: dict, orden: str | None,
           page: int, size: int) -> dict:
    exigir(user, "catalogos.ver")
    cat = _cat(tipo)
    modelo = cat["modelo"]
    consulta = select(modelo)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(or_(*[getattr(modelo, b).ilike(patron) for b in cat["buscar"]]))
    nombres = {x["nombre"]: x for x in cat["campos"]}
    for k, v in filtros.items():
        if k not in nombres or v in (None, ""):
            continue
        campo = nombres[k]
        if campo["tipo"] == "multi":
            consulta = consulta.where(getattr(modelo, k).any(id=int(v)))
            continue
        if campo["tipo"] == "bool":
            v = str(v).lower() in ("1", "true", "si", "sí")
        elif campo["tipo"] in ("ref", "entero"):
            v = int(v)
        consulta = consulta.where(getattr(modelo, k) == v)
    col, _, direccion = (orden or "").partition(":")
    if col in nombres and nombres[col]["tipo"] != "multi":
        expr = getattr(modelo, col)
        consulta = consulta.order_by(expr.desc() if direccion == "desc" else expr.asc(), modelo.id)
    else:
        consulta = consulta.order_by(modelo.id)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    objs = list(db.scalars(consulta.offset((page - 1) * size).limit(size)).all())
    refs = _refs(db, cat, objs)
    return {"items": [_fila(cat, o, refs) for o in objs], "total": total, "page": page, "size": size}


def opciones(db: Session, user: Usuario, tipo: str) -> list[dict]:
    """Lista corta (id, código, texto) para selects y filtros."""
    exigir(user, "catalogos.ver")
    cat = _cat(tipo)
    modelo = cat["modelo"]
    objs = db.scalars(select(modelo).order_by(modelo.id)).all()
    clave = "sku" if tipo == "articulos" else "codigo"
    return [{"id": o.id, "codigo": getattr(o, clave), "texto": _mostrar(o)} for o in objs]


def _limpiar(db: Session, cat: dict, datos: dict, parcial: bool, actual=None) -> dict:
    import re

    errores = []
    limpio = {}
    for campo in cat["campos"]:
        n = campo["nombre"]
        if n not in datos:
            if not parcial and campo["obligatorio"]:
                errores.append({"campo": n, "mensaje": f"{campo['etiqueta']} is required."})
            continue
        v = datos[n]
        if isinstance(v, str):
            v = v.strip()
            if campo.get("mayus"):
                v = v.upper()
        if v in ("", None) or (campo["tipo"] == "multi" and v == [] and not campo["obligatorio"]):
            if campo["tipo"] == "multi":
                if campo["obligatorio"]:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: choose at least one."})
                else:
                    limpio[n] = []
                continue
            v = None
        if v is None:
            if campo["obligatorio"]:
                errores.append({"campo": n, "mensaje": f"{campo['etiqueta']} is required."})
            limpio[n] = False if campo["tipo"] == "bool" else None
            continue
        t = campo["tipo"]
        try:
            if t == "entero":
                v = int(v)
                if campo.get("minimo") is not None and v < campo["minimo"]:
                    raise ValueError
            elif t == "numero":
                v = float(v)
            elif t == "bool":
                v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "si", "sí")
            elif t == "ref":
                v = int(v)
                if not db.get(CATALOGOS[campo["catalogo"]]["modelo"], v):
                    raise ValueError
            elif t == "codigo":
                v = str(v).upper()
                modelo = CATALOGOS[campo["catalogo"]]["modelo"]
                if not db.scalar(select(modelo.id).where(modelo.codigo == v)):
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {v} is not in the catalog."})
                    continue
            elif t == "opcion" and v not in [o[0] for o in campo["opciones"]]:
                raise ValueError
            elif t == "multi":
                ids = v if isinstance(v, list) else [x for x in str(v).split(",") if x.strip()]
                modelo = CATALOGOS[campo["catalogo"]]["modelo"]
                objs = list(db.scalars(select(modelo).where(modelo.id.in_([int(x) for x in ids])))) if ids else []
                if len(objs) != len(set(int(x) for x in ids)):
                    raise ValueError
                if campo["obligatorio"] and not objs:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: choose at least one."})
                    continue
                v = objs
            elif t == "correos":
                lista = [x.strip().lower() for x in re.split(r"[,;\s]+", str(v)) if x.strip()]
                malos = [x for x in lista if not re.match(CORREO, x)]
                if malos:
                    errores.append({"campo": n, "mensaje": f"Invalid email: {', '.join(malos)}."})
                    continue
                v = ", ".join(dict.fromkeys(lista))
            else:
                v = str(v)
        except (TypeError, ValueError):
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: invalid value."})
            continue
        if campo.get("max") and isinstance(v, str) and len(v) > campo["max"]:
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {campo['max']} characters maximum."})
            continue
        if campo.get("patron") and isinstance(v, str) and not re.match(campo["patron"], v):
            errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {campo.get('mensaje_patron', 'invalid format')}"})
            continue
        limpio[n] = v

    final = {**({c["nombre"]: getattr(actual, c["nombre"]) for c in cat["campos"]} if actual else {}), **limpio}
    # Reglas propias de los artículos: el prepack se enlaza por estilo, color
    # y prepack ID (la talla); debe existir su curva
    if cat["modelo"] is Articulo:
        if final.get("tipo") == "PREPACK" and not (actual and actual.tipo == "PREPACK"):
            errores.append({"campo": "tipo", "mensaje":
                            "Prepacks are created in the Prepacks tab, with their product code and breakdown."})
        elif actual and actual.tipo == "PREPACK":
            # La explosión es fija: no cambia lo que la enlaza
            fijos = [c for c in ("tipo", "estilo", "color", "talla", "unidad") if c in limpio and limpio[c] != getattr(actual, c)]
            if fijos:
                errores.append({"campo": fijos[0], "mensaje":
                                "A prepack and its breakdown cannot change (style, color, prepack ID, unit and type). "
                                "Create a new prepack."})
        elif final.get("tipo") == "SOLIDO":
            if actual and db.scalar(select(PrepackComponente.id).where(PrepackComponente.articulo_id == actual.id)):
                fijos = [c for c in ("estilo", "color", "talla", "unidad") if c in limpio and limpio[c] != getattr(actual, c)]
                if fijos:
                    errores.append({"campo": fijos[0], "mensaje":
                                    "This solid is part of a prepack breakdown: its style, "
                                    "color, size and unit cannot change."})
            limpio["prepack_id"] = None
            if final.get("unidad") == "CJ":
                errores.append({"campo": "unidad", "mensaje": "A solid is handled in pairs or units."})
    if cat["modelo"] is Articulo and final.get("proveedor_id") and final.get("marca_id"):
        prov = db.get(Proveedor, final["proveedor_id"])
        if prov and prov.marcas and final["marca_id"] not in {m.id for m in prov.marcas}:
            errores.append({"campo": "marca_id", "mensaje":
                            f"The brand does not belong to {prov.nombre}; its brands are {', '.join(m.codigo for m in prov.marcas)}."})
    if cat["modelo"] is Proveedor and actual and "marcas" in limpio:
        quedan = {m.id for m in limpio["marcas"]}
        usadas = {m for (m,) in db.execute(select(Articulo.marca_id).where(Articulo.proveedor_id == actual.id).distinct())}
        if usadas - quedan:
            nombres_m = [m.codigo for m in db.scalars(select(Marca).where(Marca.id.in_(usadas - quedan)))]
            errores.append({"campo": "marcas", "mensaje":
                            f"The supplier has items of {', '.join(nombres_m)}: those brands cannot be removed."})
    if cat["modelo"] is Contacto and not final.get("sociedad_id") and not final.get("centro_id"):
        errores.append({"campo": "sociedad_id", "mensaje": "Enter the contact's company or plant."})
    if cat["modelo"] is Prepack and actual:
        fijos = [c for c in ("codigo", "estilo", "color") if c in limpio and limpio[c] != getattr(actual, c)]
        if fijos:
            errores.append({"campo": fijos[0], "mensaje":
                            "The prepack ID, style and color cannot change; only the description and whether it is active."})
    if errores:
        raise ErrorNegocio("Check the data.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, tipo: str, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    if tipo == "prepacks":
        return crear_prepack(db, user, datos)
    cat = _cat(tipo)
    limpio = _limpiar(db, cat, datos, parcial=False)
    for campo in cat["campos"]:
        if campo["tipo"] == "bool" and campo["nombre"] not in datos:
            limpio[campo["nombre"]] = True
    obj = cat["modelo"](**limpio)
    try:
        with db.begin_nested():
            db.add(obj)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"A {cat['singular']} with that code already exists.", 409, "duplicado") from None
    if isinstance(obj, Articulo):
        asegurar_producto(db, obj)
    registrar(db, user, tipo, obj.id, "crear", {"codigo": _mostrar(obj)})
    return _fila(cat, obj, _refs(db, cat, [obj]))


def actualizar(db: Session, user: Usuario, tipo: str, obj_id: int, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    cat = _cat(tipo)
    obj = db.get(cat["modelo"], obj_id)
    if not obj:
        raise ErrorNegocio(f"The {cat['singular']} does not exist.", 404, "no_encontrado")
    limpio = _limpiar(db, cat, datos, parcial=True, actual=obj)
    cambios = {}
    for k, v in limpio.items():
        if getattr(obj, k) != v:
            antes = getattr(obj, k)
            if isinstance(v, list):  # relaciones: se guardan los códigos en el historial
                cambios[k] = [[x.codigo for x in antes], [x.codigo for x in v]]
            else:
                cambios[k] = [antes, v]
            setattr(obj, k, v)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"A {cat['singular']} with that code already exists.", 409, "duplicado") from None
    if isinstance(obj, Articulo) and {"estilo", "color", "proveedor_id"} & set(cambios):
        asegurar_producto(db, obj)
    if cambios:
        registrar(db, user, tipo, obj.id, "editar", cambios)
    return _fila(cat, obj, _refs(db, cat, [obj]))


def eliminar(db: Session, user: Usuario, tipo: str, obj_id: int) -> dict:
    exigir(user, "catalogos.editar")
    cat = _cat(tipo)
    obj = db.get(cat["modelo"], obj_id)
    if not obj:
        raise ErrorNegocio(f"The {cat['singular']} does not exist.", 404, "no_encontrado")
    try:
        with db.begin_nested():
            db.delete(obj)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"It cannot be deleted: the {cat['singular']} is in use. Deactivate it instead.",
                           409, "en_uso") from None
    registrar(db, user, tipo, obj_id, "eliminar", None)
    return {"ok": True}


# ---- Prepacks: componentes -------------------------------------------------
def componentes(db: Session, user: Usuario, prepack_id: int, validar: bool = True) -> dict:
    if validar:
        exigir(user, "catalogos.ver")
    p = db.get(Prepack, prepack_id)
    if not p:
        raise ErrorNegocio("The prepack does not exist.", 404, "no_encontrado")
    art = db.scalar(select(Articulo).where(Articulo.prepack_id == p.id))
    return {
        "sku": art.sku if art else None, "unidad": "CJ", "marca": art.marca.codigo if art else None,
        "id": p.id, "codigo": p.codigo, "estilo": p.estilo, "color": p.color, "descripcion": p.descripcion,
        "total": p.total,
        "unidad_componentes": p.componentes[0].articulo.unidad if p.componentes else None,
        "componentes": [{"articulo_id": x.articulo_id, "sku": x.articulo.sku, "estilo": x.articulo.estilo,
                         "color": x.articulo.color, "talla": x.articulo.talla, "unidad": x.articulo.unidad,
                         "cantidad": x.cantidad} for x in p.componentes],
    }


def _validar_curva(db: Session, estilo: str, color: str, items: list[dict]) -> tuple[list, list]:
    """Solo sólidos del mismo estilo y color del prepack, con cantidad, sin
    repetir artículo y sin mezclar pares con unidades."""
    errores = []
    arts = []
    for it in items:
        a = db.get(Articulo, int(it.get("articulo_id") or 0))
        try:
            cant = int(it.get("cantidad") or 0)
        except (TypeError, ValueError):
            cant = 0
        if not a:
            errores.append({"mensaje": "One of the items does not exist."})
            continue
        if a.tipo != "SOLIDO":
            errores.append({"mensaje": f"{a.sku}: a breakdown only carries solid items."})
        if cant < 1:
            errores.append({"mensaje": f"{a.sku}: the quantity must be greater than zero."})
        arts.append((a, cant))
    if not arts:
        errores.append({"mensaje": "The breakdown needs at least one solid item."})
    if len({a.id for a, _ in arts}) != len(arts):
        errores.append({"mensaje": "An item appears twice in the breakdown."})
    otros = [a for a, _ in arts if (a.estilo, a.color) != (estilo, color)]
    if otros:
        errores.append({"mensaje": f"The prepack is {estilo} {color}: "
                                   + ", ".join(f"{a.sku} ({a.estilo} {a.color})" for a in otros)
                                   + " is not the same style and color."})
    if len({a.unidad for a, _ in arts}) > 1:
        errores.append({"mensaje": "Pairs and units cannot be mixed in a breakdown."})
    return arts, errores


def crear_prepack(db: Session, user: Usuario, datos: dict) -> dict:
    """Crea el prepack completo en un paso: su curva (explosión) y el artículo
    prepack con su propio código de producto. La explosión ya no cambia."""
    import re

    exigir(user, "catalogos.editar")
    sku = str(datos.get("sku") or "").strip()
    codigo = str(datos.get("codigo") or "").strip().upper()
    estilo = str(datos.get("estilo") or "").strip().upper()
    color = str(datos.get("color") or "").strip()
    errores = []
    if not re.fullmatch(r"\d{6,18}", sku):
        errores.append({"campo": "sku", "mensaje": "Product code: digits only, for example 30095120027."})
    elif db.scalar(select(Articulo.id).where(Articulo.sku == sku)):
        errores.append({"campo": "sku", "mensaje": f"Code {sku} already exists in the item master."})
    if not re.fullmatch(r"[A-Z0-9]{2,10}", codigo):
        errores.append({"campo": "codigo", "mensaje": "Prepack ID: letters and numbers, for example AB12."})
    if not estilo or not color:
        errores.append({"campo": "estilo", "mensaje": "Enter the prepack's style and color."})
    elif db.scalar(select(Prepack.id).where(Prepack.estilo == estilo, Prepack.color == color, Prepack.codigo == codigo)):
        errores.append({"campo": "codigo", "mensaje": f"Prepack {codigo} already exists for {estilo} {color}."})
    arts, err_curva = _validar_curva(db, estilo, color, datos.get("componentes") or [])
    errores += err_curva
    if errores:
        raise ErrorNegocio("The prepack is not valid.", 422, "validacion", errores)
    base = arts[0][0]
    p = Prepack(codigo=codigo, estilo=estilo, color=color, activo=True,
                descripcion=(datos.get("descripcion") or "").strip()
                or f"{estilo} {color} prepack {codigo} ({sum(c for _, c in arts)} {base.unidad.lower()})")
    for a, cant in arts:
        p.componentes.append(PrepackComponente(articulo_id=a.id, cantidad=cant))
    db.add(p)
    db.flush()
    art = Articulo(sku=sku, upc=(datos.get("upc") or "").strip() or None, estilo=estilo, color=color, talla=codigo,
                   descripcion=p.descripcion, marca_id=base.marca_id, grupo_id=base.grupo_id,
                   proveedor_id=base.proveedor_id, unidad="CJ", tipo="PREPACK", prepack_id=p.id,
                   activo=True)
    db.add(art)
    db.flush()
    asegurar_producto(db, art)
    registrar(db, user, "prepacks", p.id, "crear",
              {"sku": sku, "prepack": codigo, "explosion": {a.talla: c for a, c in arts}})
    return componentes(db, user, p.id)


def explosion(db: Session, user: Usuario, sku: str) -> dict:
    """Explosión de un artículo prepack, de solo lectura (para OC, factura,
    packing list y seguimiento)."""
    exigir(user, "oc.ver")
    a = db.scalar(select(Articulo).where(Articulo.sku == sku))
    if not a or a.tipo != "PREPACK" or not a.prepack:
        raise ErrorNegocio("That code is not a prepack item.", 404, "no_encontrado")
    return componentes(db, user, a.prepack_id, validar=False)


# ---- Carga masiva ----------------------------------------------------------
# Columnas de las plantillas en inglés -> nombre interno (también se aceptan los internos)
COLUMNAS_EN = {"style": "estilo", "size": "talla", "description": "descripcion", "brand": "marca", "group": "grupo",
               "supplier": "proveedor", "type": "tipo", "uom": "unidad", "unit": "unidad",
               "hs_code": "partida_arancelaria", "country_of_origin": "pais_origen", "prepack_sku": "sku_prepack",
               "quantity": "cantidad", "qty": "cantidad"}
CAMPO_EN = {"marca": "Brand", "grupo": "Group", "proveedor": "Supplier"}


def _filas_archivo(nombre: str, contenido: bytes) -> list[dict]:
    from .ordenes import _norm, _texto

    if nombre.lower().endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        filas = [[_texto(v) for v in f] for f in wb.active.iter_rows(values_only=True)]
    else:
        texto = contenido.decode("utf-8-sig", errors="replace")
        delim = ";" if texto[:2000].count(";") > texto[:2000].count(",") else ","
        filas = [[v.strip() for v in f] for f in csv.reader(io.StringIO(texto), delimiter=delim)]
    if not filas:
        return []
    enc = [COLUMNAS_EN.get(_norm(h), _norm(h)) for h in filas[0]]
    return [{**{enc[i]: (f[i] if i < len(f) else "") for i in range(len(enc))}, "_fila": n}
            for n, f in enumerate(filas[1:], start=2) if any(f)]


def importar_articulos(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Crea o actualiza artículos por SKU. Marca, grupo, proveedor y prepack
    se indican por código."""
    exigir(user, "catalogos.editar")
    filas = _filas_archivo(nombre, contenido)
    if not filas:
        raise ErrorNegocio("The file has no rows with data.", 422, "archivo_vacio")
    por_codigo = {
        "marca": {m.codigo: m.id for m in db.scalars(select(Marca))},
        "grupo": {g.codigo: g.id for g in db.scalars(select(GrupoArticulo))},
        "proveedor": {p.codigo: p.id for p in db.scalars(select(Proveedor))},
    }
    cat = CATALOGOS["articulos"]
    creados = actualizados = 0
    errores = []
    for f in filas:
        datos = {k: f.get(k, "") for k in ("sku", "estilo", "color", "talla", "descripcion", "upc", "unidad")}
        # Origen y partida propuesta van al producto (estilo-color), no a la talla
        origen = (f.get("pais_origen") or "").strip().upper()[:2]
        propuesta = re.sub(r"\D", "", f.get("partida_arancelaria") or "")
        datos["tipo"] = (f.get("tipo") or "SOLIDO").upper()
        if datos["tipo"] == "PREPACK":
            errores.append({"fila": f["_fila"], "mensaje":
                            "Prepacks are loaded with the prepack format (product code and breakdown)."})
            continue
        datos["unidad"] = (datos["unidad"] or "").upper()
        faltan = []
        for campo, destino in (("marca", "marca_id"), ("grupo", "grupo_id"), ("proveedor", "proveedor_id")):
            codigo = (f.get(campo) or "").strip().upper()
            if not codigo:
                continue
            if codigo not in por_codigo[campo]:
                faltan.append(f"{CAMPO_EN[campo]} {codigo} does not exist")
            else:
                datos[destino] = por_codigo[campo][codigo]
        if faltan:
            errores.append({"fila": f["_fila"], "mensaje": "; ".join(faltan) + "."})
            continue
        existente = db.scalar(select(Articulo).where(Articulo.sku == datos["sku"].strip()))
        try:
            with db.begin_nested():
                if existente:
                    limpio = _limpiar(db, cat, {k: v for k, v in datos.items() if v != ""}, parcial=True, actual=existente)
                    for k, v in limpio.items():
                        setattr(existente, k, v)
                    art = existente
                else:
                    limpio = _limpiar(db, cat, datos, parcial=False)
                    art = Articulo(**limpio, activo=True)
                    db.add(art)
                db.flush()
                prod = asegurar_producto(db, art)
                if prod and origen and not prod.pais_origen:
                    prod.pais_origen = origen
                if prod and len(propuesta) >= 6 and not prod.aprobado:
                    prod.propuesta = propuesta[:14]
            if existente:
                actualizados += 1
            else:
                creados += 1
        except IntegrityError:
            errores.append({"fila": f["_fila"], "mensaje": "Duplicated or inconsistent data."})
        except ErrorNegocio as e:
            errores.append({"fila": f["_fila"], "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    registrar(db, user, "articulos", 0, "importar", {"creados": creados, "actualizados": actualizados,
                                                      "errores": len(errores)})
    return {"creados": creados, "actualizados": actualizados, "errores": errores[:200]}


def importar_prepacks(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Columnas: sku_prepack (código de producto del prepack), prepack_id,
    descripcion, sku (sólido) y cantidad. Una fila por talla de la explosión.
    Estilo y color salen de los sólidos. Un prepack que ya existe no cambia."""
    exigir(user, "catalogos.editar")
    filas = _filas_archivo(nombre, contenido)
    grupos: dict[str, dict] = {}
    errores = []
    for f in filas:
        sku_pp = (f.get("sku_prepack") or f.get("codigo_prepack") or "").strip()
        codigo = (f.get("prepack_id") or f.get("prepack") or "").strip().upper()
        sku = (f.get("sku") or "").strip()
        if not sku_pp or not codigo or not sku:
            errores.append({"fila": f["_fila"], "mensaje": "Missing prepack_sku, prepack_id or sku."})
            continue
        a = db.scalar(select(Articulo).where(Articulo.sku == sku))
        if not a:
            errores.append({"fila": f["_fila"], "mensaje": f"SKU {sku} does not exist in the item master."})
            continue
        g = grupos.setdefault(sku_pp, {"codigo": codigo, "estilo": a.estilo, "color": a.color,
                                       "descripcion": f.get("descripcion") or None, "items": []})
        g["items"].append({"articulo_id": a.id, "cantidad": f.get("cantidad") or 0})
    creados = sin_cambio = 0
    for sku_pp, g in grupos.items():
        existente = db.scalar(select(Articulo).where(Articulo.sku == sku_pp))
        if existente:
            actual = {x.articulo_id: x.cantidad for x in existente.prepack.componentes} if existente.prepack else {}
            nueva = {it["articulo_id"]: int(it["cantidad"] or 0) for it in g["items"]}
            if actual == nueva:
                sin_cambio += 1
            else:
                errores.append({"fila": sku_pp, "mensaje": "The prepack already exists with another breakdown; "
                                                           "the breakdown cannot change. Use a new code."})
            continue
        try:
            with db.begin_nested():
                crear_prepack(db, user, {"sku": sku_pp, **g, "componentes": g["items"]})
            creados += 1
        except ErrorNegocio as e:
            errores.append({"fila": sku_pp, "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    return {"creados": creados, "actualizados": 0, "sin_cambio": sin_cambio, "errores": errores[:200]}
