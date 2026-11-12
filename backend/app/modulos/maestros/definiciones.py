"""Descripción de cada catálogo de datos maestros: sus campos, tipos, obligatorios,
filtros y búsqueda. Es la única fuente: el mismo diccionario sirve para listar,
validar y guardar (catalogos.py) y para que la interfaz dibuje formularios y tablas.
"""
from app.core import listas
from app.modelos import (
    AcuerdoComercial,
    Almacen,
    Articulo,
    Atributo,
    Centro,
    CondicionPago,
    Contacto,
    DominioClasificacion,
    EscalaValores,
    GrupoFamilia,
    Incoterm,
    Marca,
    ModoTransporte,
    Moneda,
    Pais,
    Proveedor,
    SerieDocumental,
    Sociedad,
    TipoEmpaque,
    UnidadMedida,
    ValorLista,
)
from app.modulos.maestros import atributos as atr_svc
from app.modulos.maestros.campos_catalogo import c
from app.modulos.maestros.definiciones_logistica import LOGISTICA


def _atributo(a: str, **extra) -> dict:
    """Campo de formulario de un atributo de lista (core/listas.ATRIBUTOS)."""
    etiqueta, tipo = listas.ATRIBUTOS[a][0], listas.ATRIBUTOS[a][1]
    return c(a, etiqueta, "opcion" if tipo.startswith("lista") else tipo,
             **({"lista": tipo.split(":")[1]} if tipo.startswith("lista") else {}),
             **({"opciones": listas.CALCULOS} if a == "calculo" else {"opciones": listas.ICONOS} if a == "icono"
                else {"opciones": listas.ESTADOS_EMBARQUE} if a == "estados" else {}),
             **({"minimo": 0} if tipo in ("entero", "numero") else {}),
             **({"max": listas.ATRIBUTOS[a][2]} if tipo == "texto" else {}), **extra)


def _catalogo_lista(lista: str, modelo, singular: str, max_codigo: int, obligatorios=()) -> dict:
    """Catálogo de una lista con tabla propia (monedas, unidades…)."""
    d = listas.LISTAS[lista]
    return {
        "modelo": modelo, "titulo": d["etiqueta"], "singular": singular, "lista": lista,
        "ayuda": d["ayuda"] + (" Values the system relies on can be renamed but not deleted or deactivated."
                               if d["sistema"] else ""),
        "campos": [
            c("codigo", "Code", obligatorio=True, max=max_codigo, mayus=True),
            c("nombre", "Name", obligatorio=True, max=120),
            *[_atributo(a, obligatorio=a in obligatorios) for a in d["atributos"]],
            c("orden", "Order", "entero", minimo=0),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre", *(["alias"] if "alias" in d["atributos"] else [])],
    }


SIMPLES = [k for k in listas.LISTAS if k not in listas.TABLA]
CATALOGOS = {
    **LOGISTICA,
    "sociedades": {
        "modelo": Sociedad, "titulo": "Companies", "singular": "company",
        "ayuda": "Companies that are invoiced (the PO company). Each one has its assigned plants.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("nombre", "Name", obligatorio=True, formato="nombre"),
            c("razon_social", "Legal name"),
            c("id_fiscal", "Tax ID"),
            c("pais", "Country", "codigo", catalogo="paises", filtro=True),
            c("moneda", "Currency", max=3, mayus=True, ayuda="Default currency of its POs and invoices."),
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
            c("nombre", "Name", obligatorio=True, formato="nombre"),
            c("pais", "Country", "codigo", obligatorio=True, catalogo="paises", filtro=True),
            c("puerto", "Arrival port", "codigo", catalogo="puertos", filtro=True, depende={"campo": "pais", "clave": "pais"}),
            c("tipo", "Type", "opcion", obligatorio=True, lista="tipo_centro"),
            c("puertos", "Other arrival ports", "multi", catalogo="puertos", depende={"campo": "pais", "clave": "pais"},
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
            c("nombre", "Name", obligatorio=True, formato="nombre"),
            c("tipo", "Type", "opcion", obligatorio=True, filtro=True,
              lista="tipo_almacen"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "contactos": {
        "modelo": Contacto, "titulo": "Contacts", "singular": "contact",
        "ayuda": "Contact people of a company (billing) or of a plant (notify party). "
                 "They appear on the invoice and the packing list.",
        "campos": [
            c("nombre", "Name", obligatorio=True, formato="nombre"),
            c("cargo", "Job title", formato="nombre"),
            c("rol", "Role", "opcion", obligatorio=True, filtro=True,
              lista="tipo_contacto"),
            c("sociedad_id", "Company", "ref", catalogo="sociedades", filtro=True),
            c("centro_id", "Plant", "ref", catalogo="centros", filtro=True, depende={"campo": "sociedad_id", "clave": "sociedad_id"}),
            c("correos", "Emails", "correos", ayuda="One or more, separated by commas."),
            c("telefono", "Phone"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["nombre", "cargo"],
        # Las personas de contacto de proveedores y transportistas viven en su tercero
        "donde": lambda: Contacto.tercero_id.is_(None),
    },
    "paises": {
        "modelo": Pais, "titulo": "Countries", "singular": "country",
        "ayuda": "Countries of origin and shipment (2-letter ISO).",
        "campos": [
            c("codigo", "ISO code", obligatorio=True, max=2, mayus=True, patron=r"^[A-Z]{2}$",
              mensaje_patron="Use the 2-letter ISO code."),
            c("nombre", "Name", obligatorio=True, formato="nombre"),
            c("region", "Lead time region", "codigo", catalogo="regiones", filtro=True,
              ayuda="Origin region (e.g. ASIA). Lead time plans can apply to the whole region."),
            c("nombre_id_fiscal", "Tax ID name", max=30,
              ayuda="How the company tax ID is called in this country (NIT, RUC, RFC, EIN…). Documents use it."),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "acuerdos": {
        "modelo": AcuerdoComercial, "titulo": "Trade agreements", "singular": "agreement",
        "ayuda": "Trade agreements in force: goods originating in the origin countries enter the destination countries "
                 "with a preferential duty when the proof of origin is presented. The technical sheet shows them "
                 "for the product's country of origin.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=20, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("origenes", "Origin countries", "multi", obligatorio=True, catalogo="paises", filtro=True),
            c("destinos", "Destination countries", "multi", obligatorio=True, catalogo="paises", filtro=True,
              ayuda="Destination countries where it applies."),
            c("prueba", "Proof of origin"),
            c("nota", "Note"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "tipos_empaque": {
        "modelo": TipoEmpaque, "titulo": "Packaging types", "singular": "packaging type",
        "ayuda": "Configurable logistics units (inner pack, carton, pallet, bag, drum…) and which ones each can "
                 "contain. A packing list is a tree of packaging inside packaging with the products inside: the "
                 "net weight comes from each item's unit weight, and each level adds its tare.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=20, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("nivel", "Level", "entero", obligatorio=True, minimo=1, ayuda="1 = the innermost."),
            c("prefijo", "Label prefix", max=6, mayus=True, ayuda="Numbering of each unit, e.g. C → C1, C2…"),
            c("cuenta_como", "Counts as", "opcion", obligatorio=True, filtro=True, opciones=[
                ["BULTO", "Package (carton)"], ["INTERIOR", "Inner unit (inside a package)"],
                ["SOPORTE", "Support that carries packages (pallet)"]]),
            c("contiene", "Can contain", "multi", catalogo="tipos_empaque",
              ayuda="Packaging types that can go inside this one."),
            c("contiene_productos", "Holds products directly", "bool"),
            c("largo", "Length (cm)", "numero", minimo=0, ayuda="Outer dimensions by default; each unit can change them."),
            c("ancho", "Width (cm)", "numero", minimo=0),
            c("alto", "Height (cm)", "numero", minimo=0),
            c("tara", "Tare (kg)", "numero", minimo=0, ayuda="Weight of the empty packaging."),
            c("peso_max", "Max gross weight (kg)", "numero", minimo=0),
            c("max_unidades", "Max product units", "entero", minimo=1),
            c("max_contenido", "Max inner packaging", "entero", minimo=1),
            c("mezcla_productos", "Can mix products", "bool"),
            c("mezcla_tallas", "Can mix variants (sizes, flavors, presentations…)", "bool"),
            c("mezcla_oc", "Can mix POs", "bool"),
            c("uom", "UoM", max=10, mayus=True),
            c("identificador", "Identifier", "opcion", opciones=[
                ["SERIAL", "Serial number"], ["CODIGO_BARRAS", "Barcode"], ["SSCC", "SSCC (GS1)"]]),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre", "prefijo"],
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
    "atributos": {
        "modelo": Atributo, "titulo": "Attributes", "singular": "attribute",
        "ayuda": "The data your company records for its products. Product attributes (brand, model, material, UN "
                 "number…) are shared by all the variants of a product; variant attributes (size, color, flavor, "
                 "presentation, concentration…) tell the variants apart. Each attribute applies to the families "
                 "you choose (and their subfamilies and categories) or to all of them: a product only takes the "
                 "attributes of its family, and its variants are told apart by the variant attributes of that family.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=20, mayus=True, patron=r"^[A-Z][A-Z0-9_]{0,19}$",
              mensaje_patron="Letters, numbers and _, starting with a letter."),
            c("nombre", "Name", obligatorio=True, max=60),
            c("nivel", "Level", "opcion", filtro=True, opciones=atr_svc.NIVELES, ayuda="Empty = variant."),
            c("tipo", "Kind of value", "opcion", filtro=True, opciones=atr_svc.TIPOS, ayuda="Empty = text."),
            c("opciones", "Options (comma-separated)", max=500, mostrar_si={"campo": "tipo", "valores": ["opcion"]},
              ayuda="For the «one of the options» kind: e.g. 110 V, 220 V."),
            c("catalogo", "Catalog", "opcion", opciones=atr_svc.CATALOGOS, mostrar_si={"campo": "tipo", "valores": ["catalogo"]},
              ayuda="For a record of a catalog: the value is the record's code (a brand: brands of the product's supplier)."),
            c("unidad", "Unit", "opcion", lista="unidad", mostrar_si={"campo": "tipo", "valores": ["numero"]},
              ayuda="For numbers: the unit the value is written in (ml, kg, V…)."),
            c("general", "All families", "bool", filtro=True, defecto=False,
              ayuda="It applies to every family and to products without a family."),
            c("familias", "Families", "multi", catalogo="familias", filtro=True,
              mostrar_si={"campo": "general", "valores": [False]},
              ayuda="Where it applies: these families, their subfamilies and their categories."),
            c("orden", "Order", "entero", minimo=0),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    # Familias de producto (se mantienen en Productos → Familias): solo para elegirlas desde otros catálogos
    "familias": {
        "modelo": GrupoFamilia, "titulo": "Product families", "singular": "product family",
        "solo_lectura": True,
        "campos": [c("codigo", "Code"), c("nombre", "Name"), c("activa", "Active", "bool")],
        "buscar": ["codigo", "nombre"],
    },
    "escalas": {
        "modelo": EscalaValores, "titulo": "Value scales", "singular": "value scale",
        "ayuda": "Reusable ordered values of a variant attribute: a series of sizes, presentations "
                 "(250 ml, 500 ml, 1 L), concentrations… A product's variants start from a scale: its values come in "
                 "order and each item code is generated with the scale's rule or typed in the list.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=20, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("atributo", "Variant attribute", "codigo", catalogo="atributos", obligatorio=True, filtro=True,
              ayuda="Whose values the scale orders."),
            c("regla", "Code rule", "opcion", obligatorio=True, filtro=True, opciones=[
                ["MULTIPLICAR", "Value × factor (7.5 × 10 → 075)"], ["CONSECUTIVO", "Consecutive (001, 002…)"],
                ["VALOR", "Same as the value (S, M, XL)"]]),
            c("factor", "Factor", "entero", minimo=1, ayuda="For Value × factor, e.g. 10."),
            c("longitud", "Code digits", "entero", minimo=1, ayuda="Zeros on the left, e.g. 3 → 070."),
            c("valores", "Values", obligatorio=True,
              ayuda="In order, separated by commas. Ranges allowed (6-10, 6.5-9.5). A fixed code with = (7=070)."),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    # Dominios de clasificación (compartidos, se configuran en Clasificación):
    # solo para elegirlos desde otros catálogos
    "dominios": {
        "modelo": DominioClasificacion, "titulo": "Classification domains", "singular": "classification domain",
        "solo_lectura": True,
        "campos": [c("codigo", "Code"), c("nombre", "Name"), c("activo", "Active", "bool")],
        "buscar": ["codigo", "nombre"],
    },
    "listas": {
        "modelo": ValorLista, "titulo": "Lists of values", "singular": "value",
        "ayuda": "Values offered in forms and files: transport modalities and shipment milestones, and the types of "
                 "plants, storage locations, contacts, taxes and technical documents. Currencies, units of measure, "
                 "transport modes, incoterms and payment terms have their own catalogs. "
                 "Values the system relies on can be renamed but not deleted or deactivated.",
        "campos": [
            c("lista", "List", "opcion", obligatorio=True, filtro=True,
              opciones=[[k, listas.LISTAS[k]["etiqueta"]] for k in SIMPLES]),
            c("codigo", "Code", obligatorio=True, max=20, mayus=True),
            c("nombre", "Name", obligatorio=True, max=120),
            *[_atributo(a, mostrar_si={"campo": "lista", "valores": [k for k in SIMPLES if a in listas.LISTAS[k]["atributos"]]})
              for a in ("padre", "consolidado", "estados")],
            c("orden", "Order", "entero", minimo=0),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "monedas": _catalogo_lista("moneda", Moneda, "currency", 3, obligatorios=("decimales",)),
    # ---- Numeración ----
    "series": {
        "modelo": SerieDocumental, "titulo": "Numbering series", "singular": "numbering series",
        "ayuda": "How shipments are numbered: prefix ({año} is replaced by the year), digits and whether it restarts "
                 "every year. The number is assigned with the counter locked: two users never get the same one.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=20, mayus=True),
            c("nombre", "Name", obligatorio=True, max=120),
            c("objeto", "Numbers", "opcion", obligatorio=True, filtro=True,
              opciones=[["embarque", "Shipments"], ["etiqueta", "Labels (controlled label ID)"]]),
            c("sociedad_id", "Company", "ref", catalogo="sociedades", filtro=True),
            c("prefijo", "Prefix", max=20),
            c("digitos", "Digits", "entero", obligatorio=True, minimo=1),
            c("reinicio", "Restart", "opcion", obligatorio=True, opciones=[["NUNCA", "Never"], ["ANUAL", "Every year"]]),
            c("predeterminada", "Default", "bool"),
            c("vigente_desde", "Valid from", "fecha"),
            c("vigente_hasta", "Valid until", "fecha"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre", "prefijo"],
    },
    "unidades": _catalogo_lista("unidad", UnidadMedida, "unit of measure", 10),
    "modos_transporte": _catalogo_lista("modo_transporte", ModoTransporte, "transport mode", 20, obligatorios=("calculo",)),
    "incoterms": _catalogo_lista("incoterm", Incoterm, "incoterm", 10),
    "condiciones_pago": _catalogo_lista("condicion_pago", CondicionPago, "payment term", 20),
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
            c("contacto", "Contact", formato="nombre"),
            c("correos", "Emails", "correos", ayuda="One or more, separated by commas."),
            c("telefono", "Phone"),
            c("marcas", "Brands handled", "multi", catalogo="marcas", filtro=True),
            c("sociedades", "Companies it works with", "multi", catalogo="sociedades", filtro=True),
            c("activo", "Active", "bool", filtro=True),
        ],
        "extras": [{"nombre": "articulos", "etiqueta": "Items", "catalogo": "articulos", "filtro": "proveedor_id"}],
        "buscar": ["codigo", "nombre", "razon_social"],
    },
    "articulos": {
        "modelo": Articulo, "titulo": "Items", "singular": "item",
        "ayuda": "Each variant of a product (item) and each pack or kit: its item code (your company's own format) is "
                 "not the supplier code. Only the item code, the product, the type and the unit are required; your "
                 "company (required data) or the product family can require more. The product's data (name, family, "
                 "supplier, brand, model…) is edited on the product.",
        "campos": [
            c("sku", "Item code", obligatorio=True, max=40, mayus=True, patron=r"^[A-Za-z0-9][A-Za-z0-9._\-/]{0,39}$",
              mensaje_patron="Letters and numbers (also . - _ /), up to 40 characters."),
            c("generico", "Product code", max=40, mayus=True,
              ayuda="Groups the variants, packs and kits of one product: they share its data. Empty = the item code "
                    "(a product without variants)."),
            c("proveedor_id", "Supplier", "ref", catalogo="proveedores", filtro=True, solo_lectura=True,
              ayuda="The product's supplier: it is changed on the product."),
            c("tipo", "Type", "opcion", obligatorio=True, filtro=True,
              opciones=[["SOLIDO", "Simple"], ["PREPACK", "Pack or kit"]]),
            c("unidad", "Unit", "opcion", obligatorio=True, lista="unidad", filtro=True),
            c("peso_unitario", "Unit weight (kg)", "numero", minimo=0,
              ayuda="Net weight of one unit of the item (for a pack or kit, all of its contents). The packaging "
                    "weight is not included: each packaging level adds its own tare. Empty in a pack = sum of its contents."),
            c("codigo_barras", "Barcode", max=40, ayuda="GTIN, EAN or UPC (one per item here; more on the product page)."),
            c("codigo_proveedor", "Supplier code", max=60, mayus=True, ayuda="The supplier's own code for this item."),
            c("descripcion", "Description", max=300, ayuda="Empty = made from the product and the variant values."),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["sku", "descripcion"],
        # Datos que no son columnas del artículo: viven en su producto o en sus códigos
        "virtuales": ("generico", "proveedor_id", "codigo_barras", "codigo_proveedor"),
    },
}
ORDEN_CATALOGOS = ["articulos", "atributos", "escalas", "tipos_empaque", "marcas", "proveedores", "sociedades", "centros",
                   "contactos", "almacenes", "transportistas", "tipos_unidad", "paises", "puertos", "regiones", "pasos_lt", "leadtimes", "acuerdos",
                   "liberaciones", "monedas", "unidades", "incoterms", "condiciones_pago",
                   "modos_transporte", "listas", "series"]
CORREO = r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$"

