"""Mantenimiento de datos maestros desde un solo lugar.

Cada catálogo se describe una vez (campos, tipos, obligatorios, filtros) y
el mismo código sirve para listar, filtrar, ordenar, crear, editar y
eliminar. La interfaz usa esa misma descripción para dibujar formularios y
tablas, así que agregar un campo aquí lo agrega en pantalla.
"""
import csv
import io

from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import listas
from app.core.archivos import abrir_libro
from app.core.campos_propios import definiciones as campos_propios_def
from app.core.campos_propios import limpiar as limpiar_propios
from app.core.errores import ErrorNegocio
from app.modelos import (
    AcuerdoComercial,
    Almacen,
    Articulo,
    ArticuloAtributo,
    ArticuloCodigo,
    ArticuloComponente,
    Atributo,
    Centro,
    CondicionPago,
    Contacto,
    DominioClasificacion,
    EscalaValores,
    EstadoLiberacion,
    Incoterm,
    Marca,
    ModoTransporte,
    Moneda,
    OrdenCompra,
    Pais,
    PasoLeadTime,
    PosicionOC,
    Producto,
    ProductoAtributo,
    Proveedor,
    Puerto,
    RegionLeadTime,
    ReglaLeadTime,
    SerieDocumental,
    Sociedad,
    TipoEmpaque,
    TipoUnidad,
    Transportista,
    UnidadMedida,
    Usuario,
    ValorLista,
)
from app.modulos.acceso.permisos import exigir, exigir_compartido
from app.modulos.comun import tabla
from app.modulos.comun.historial import registrar
from app.modulos.comun.normalizar import Referencias
from app.modulos.comun.normalizar import nombre as nombre_fmt
from app.modulos.comun.normalizar import texto as texto_fmt
from app.modulos.comun.texto import filtro_texto
from app.modulos.maestros import atributos as atr_svc
from app.modulos.maestros import gobierno, unidades
from app.modulos.productos.productos import (
    asegurar_producto,
    codigo_valido,
    fmt_codigo,
    generico_de,
    producto_de,
)
from app.modulos.transporte import reglas_lt as rlt


def c(nombre, etiqueta, tipo="texto", obligatorio=False, **extra):
    return {"nombre": nombre, "etiqueta": etiqueta, "tipo": tipo, "obligatorio": obligatorio, **extra}


# Dependencias entre campos (configurables, no propias de una empresa):
#   depende={"campo": <campo del mismo formulario>, "clave": <dato de la opción>}
# La opción solo vale si su dato `clave` coincide con el valor del campo (o lo
# contiene, si es una lista). Ej.: la marca de un artículo depende del
# proveedor (la marca trae la lista de proveedores que la manejan). El
# formulario filtra las opciones y el servidor lo valida al guardar.
# tipo: texto | entero | numero | bool | opcion (opciones) | opciones (varias, separadas por coma)
#       | ref (catalogo: guarda el id)
#       | codigo (catalogo: guarda el código, p. ej. país ISO) | correos
#       | multi (catalogo: varios registros, p. ej. las marcas de un proveedor)
# Las opciones de un campo con `lista` salen de las listas de valores de la
# empresa (core/listas.py), no del código.


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
    "regiones": {
        "modelo": RegionLeadTime, "titulo": "Regions", "singular": "region",
        "ayuda": "Groups of origin countries (Asia, Central America…) to filter, compare and apply one lead time "
                 "plan to the whole region.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("nombre", "Name", obligatorio=True, formato="nombre"),
            c("predeterminada", "Default for other origins", "bool"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
    },
    "pasos_lt": {
        "modelo": PasoLeadTime, "titulo": "Lead time steps", "singular": "lead time step",
        "ayuda": "Catalog of the steps a lead time can use (booking, release, XF, ETD, ETA, customs…). Each "
                 "configuration chooses which steps apply, their reference and days. Linking a step to a "
                 "measured date lets the system compare the plan with what really happened.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=20, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("documento", "Document", "opcion", filtro=True, opciones=[[d, n] for d, n in rlt.DOCUMENTOS],
              ayuda="The document that must fulfill this step (purchase order, invoice, packing list or shipment)."),
            c("hito", "Measured date", "opcion", filtro=True, opciones=[[h, n] for h, n in rlt.HITOS],
              ayuda="Optional. The date the system records for this step (to compare plan and reality)."),
            c("descripcion", "Description"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre", "descripcion"],
    },
    "leadtimes": {
        "modelo": ReglaLeadTime, "titulo": "Lead time rules", "singular": "lead time rule",
        "ayuda": "Lead times by geographic level with inheritance: Port > Country > Region > Global. Each rule only "
                 "defines what it changes (steps it adds, overrides or removes, and the order); the rest is "
                 "inherited from the level above. See the result in Lead time › Effective lead time.",
        "campos": [
            c("nivel", "Level", "opcion", obligatorio=True, filtro=True, opciones=[[n, t] for n, t in rlt.NIVELES]),
            c("region", "Region", "codigo", catalogo="regiones", filtro=True, mostrar_si={"campo": "nivel", "valores": ["REGION"]}),
            c("pais", "Country", "codigo", catalogo="paises", filtro=True, mostrar_si={"campo": "nivel", "valores": ["PAIS"]}),
            c("puerto", "Port", "codigo", catalogo="puertos", mostrar_si={"campo": "nivel", "valores": ["PUERTO"]}),
            c("nombre", "Name", obligatorio=True),
            c("pasos", "Steps", "regla_lt", obligatorio=True,
              ayuda="Inherited steps appear in grey: override only what changes at this level."),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["nombre", "region", "pais", "puerto"],
    },
    "puertos": {
        "modelo": Puerto, "titulo": "Ports", "singular": "port",
        "ayuda": "Sea ports and airports (UN/LOCODE).",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=10, mayus=True),
            c("nombre", "Name", obligatorio=True, formato="nombre"),
            c("pais", "Country", "codigo", obligatorio=True, catalogo="paises", filtro=True),
            c("tipo", "Type", "opcion", obligatorio=True, filtro=True, lista="modo_transporte"),
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
                 "presentation, concentration…) tell the variants apart. Each product family says which ones its "
                 "variants use and which ones are required.",
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
            c("orden", "Order", "entero", minimo=0),
            c("activo", "Active", "bool", filtro=True),
        ],
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
    "liberaciones": {
        "modelo": EstadoLiberacion, "titulo": "Release statuses", "singular": "release status",
        "ayuda": "The codes your ERP sends for the commercial and logistics release of a PO (e.g. SAP: C/P and "
                 "300/301/304). A PO can be invoiced only when both releases are given.",
        "campos": [
            c("tipo", "Release", "opcion", obligatorio=True, filtro=True,
              opciones=[["COMERCIAL", "Commercial"], ["LOGISTICA", "Logistics"]]),
            c("codigo", "Code", obligatorio=True, max=10, mayus=True, ayuda="As it comes from your ERP."),
            c("nombre", "Name", obligatorio=True),
            c("libera", "Released", "bool", ayuda="With this status the release is given."),
            c("con_cambios", "Released with later changes", "bool",
              ayuda="Logistics: status a released PO moves to when it changes afterwards."),
            c("predeterminado", "Default", "bool", ayuda="Used when the file does not bring this release."),
            c("alias", "Other words", max=300, ayuda="Other words the importer accepts, separated by commas."),
            c("orden", "Order", "entero", minimo=0),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre", "alias"],
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
    "transportistas": {
        "modelo": Transportista, "titulo": "Carriers", "singular": "carrier",
        "ayuda": "Registered shipping lines, airlines and road carriers, with the companies they work for.",
        "campos": [
            c("codigo", "Code", obligatorio=True, max=20, mayus=True),
            c("nombre", "Name", obligatorio=True),
            c("tipo", "Type", "opcion", obligatorio=True, filtro=True, lista="modo_transporte",
              opciones_extra=[["MULTIMODAL", "Multimodal"]]),
            c("codigo_internacional", "SCAC / IATA", max=10, mayus=True,
              ayuda="Shipping line SCAC or airline IATA prefix."),
            c("id_fiscal", "Tax ID"),
            c("pais", "Country", "codigo", catalogo="paises"),
            c("contacto", "Contact", formato="nombre"),
            c("correos", "Emails", "correos"),
            c("telefono", "Phone"),
            c("sociedades", "Companies it works with", "multi", catalogo="sociedades", ayuda="Empty = it works with every company.",
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
            c("modo", "Transport mode", "opcion", obligatorio=True, filtro=True, lista="modo_transporte"),
            c("modalidad", "Service", "opcion", obligatorio=True, filtro=True, lista="modalidad_transporte"),
            c("capacidad_cbm", "Max volume (m³)", "numero", minimo=0),
            c("capacidad_kg", "Max weight (kg)", "numero", minimo=0),
            c("requiere_sello", "Requires seal", "bool"),
            c("activo", "Active", "bool", filtro=True),
        ],
        "buscar": ["codigo", "nombre"],
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


def _cat(tipo: str) -> dict:
    if tipo not in CATALOGOS:
        raise ErrorNegocio("The catalog does not exist.", 404, "no_encontrado")
    return CATALOGOS[tipo]


def exigir_editable(tipo: str) -> None:
    """Un catálogo de solo consulta (se mantiene en otro módulo) no se cambia aquí."""
    if _cat(tipo).get("solo_lectura"):
        raise ErrorNegocio("This catalog is maintained in its own module.", 409, "solo_lectura")


def _mostrar(obj) -> str:
    """Texto corto para mostrar un registro referido."""
    if isinstance(obj, Contacto):
        return obj.nombre
    for a, b in (("codigo", "nombre"), ("sku", "descripcion"), ("codigo", "descripcion")):
        if hasattr(obj, a):
            extra = getattr(obj, b, None)
            return f"{getattr(obj, a)} · {extra}" if extra else str(getattr(obj, a))
    return str(obj.id)


def _opciones(campo: dict) -> list[list[str]]:
    """Opciones de un campo: las de su lista de valores o las fijas."""
    if campo.get("lista"):
        return listas.opciones(campo["lista"]) + campo.get("opciones_extra", [])
    return campo.get("opciones", [])


def _tipo_de(cat: dict) -> str:
    return next(k for k, v in CATALOGOS.items() if v is cat)


def campos_variante(cat: dict) -> list[dict]:
    """Atributos de variante de la empresa (talla, color, voltaje…) como campos
    «atr.<código>» del artículo; se guardan en articulo_atributos."""
    from app.core.empresa import configuracion_actual

    if cat["modelo"] is not Articulo:
        return []
    res = []
    for x in configuracion_actual().get("atributos") or []:
        if x.get("nivel") != "VARIANTE":
            continue
        tipo = x.get("tipo") or "texto"
        extra = ({"opciones": [[o, o] for o in atr_svc.opciones(x)]} if tipo == "opcion"
                 else {"ayuda": f"Number in {x['unidad']}."} if tipo == "numero" and x.get("unidad") else {})
        res.append(c(f"atr.{x['codigo']}", x["nombre"], "opcion" if tipo == "opcion" else "texto", max=60, propio=True,
                     seccion="variante", filtro=True, **extra))
    return res


def campos_propios(cat: dict) -> list[dict]:
    """Campos propios de la empresa para este catálogo (core/campos_propios.py),
    como campos «extra.<clave>» que se guardan en la columna extra."""
    if not hasattr(cat["modelo"], "extra"):
        return []
    return [c(f"extra.{x['clave']}", x["etiqueta"], x["tipo"], x["obligatorio"], propio=True,
              **({"opciones": [[o, o] for o in x["opciones"]]} if x["tipo"] == "opcion" else {}))
            for x in campos_propios_def(_tipo_de(cat))]


# Sección de cada dato en el formulario (primero lo común, al final lo propio
# de la empresa). Un dato que no está aquí va en «general».
SECCION_CAMPO = {
    **dict.fromkeys(("proveedor_id", "marcas", "sociedades", "sociedad_id", "centro_id", "moneda", "unidad"), "comercial"),
    **dict.fromkeys(("pais", "puerto", "puertos", "region", "peso_unitario"), "logistica"),
    **dict.fromkeys(("direccion", "contacto", "correos", "telefono", "cargo", "rol"), "contacto"),
    **dict.fromkeys(("activo", "activa", "predeterminada", "predeterminado"), "estado"),
}


def _obligatorio(cat: dict, campo: dict) -> bool:
    """Obligatorio por el sistema o porque la empresa lo pide (gobierno)."""
    return campo["obligatorio"] or campo["nombre"] in gobierno.obligatorios(_tipo_de(cat))


def campos_con_opciones(cat: dict) -> list[dict]:
    """Campos del catálogo con las opciones de las listas de la empresa, su
    sección, si la empresa los volvió obligatorios y los campos propios."""
    extra = gobierno.obligatorios(_tipo_de(cat))
    campos = []
    for x in cat["campos"]:
        y = {**x, "seccion": x.get("seccion") or SECCION_CAMPO.get(x["nombre"], "general")}
        if x["tipo"] in ("opcion", "opciones"):
            y["opciones"] = _opciones(x)
        if x["nombre"] in extra:
            y["obligatorio"] = True
            y["obligatorio_empresa"] = True
        campos.append(y)
    return campos + campos_variante(cat) + [{**x, "seccion": "propios"} for x in campos_propios(cat)]


def meta(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "catalogos.ver")
    return [{"tipo": t, "titulo": CATALOGOS[t]["titulo"], "singular": CATALOGOS[t]["singular"],
             "ayuda": CATALOGOS[t].get("ayuda"), "campos": campos_con_opciones(CATALOGOS[t]),
             "extras": CATALOGOS[t].get("extras", []),
             "total": db.scalar(select(func.count()).select_from(CATALOGOS[t]["modelo"])) or 0,
             "puede": gobierno.puede(user, t),
             "gobierno": gobierno.resumen(db, t, _campos_gobierno(db, t))}
            for t in ORDEN_CATALOGOS]


def _campos_gobierno(db: Session, tipo: str) -> list[dict]:
    """Datos que la empresa puede volver obligatorios: los del catálogo y, en artículos, cada
    atributo de producto o de variante («atributo.<código>»)."""
    campos = CATALOGOS[tipo]["campos"]
    if tipo != "articulos":
        return campos
    return campos + [{"nombre": f"atributo.{a.codigo}", "etiqueta": a.nombre, "tipo": "texto", "obligatorio": False}
                     for a in db.scalars(select(Atributo).where(Atributo.activo.is_(True))
                                         .order_by(Atributo.nivel, Atributo.orden, Atributo.codigo))]


def guardar_gobierno(db: Session, user: Usuario, tipo: str, datos: dict) -> dict:
    """Responsables y datos obligatorios del catálogo (administración)."""
    _cat(tipo)
    return gobierno.guardar(db, user, tipo, _campos_gobierno(db, tipo), datos)


def historial(db: Session, user: Usuario, tipo: str, obj_id: int) -> list[dict]:
    """Cambios de un registro: quién, cuándo y qué cambió (gobierno del dato)."""
    from app.modelos import Historial

    exigir(user, "catalogos.ver")
    cat = _cat(tipo)
    if not db.get(cat["modelo"], obj_id):
        raise ErrorNegocio(f"The {cat['singular']} does not exist.", 404, "no_encontrado")
    filas = db.scalars(select(Historial).where(Historial.entidad == tipo, Historial.entidad_id == obj_id)
                       .order_by(Historial.fecha.desc(), Historial.id.desc()).limit(200)).all()
    res = []
    for h in filas:
        if h.accion == "eliminar":  # lo anterior es de un registro borrado que tuvo el mismo id
            break
        res.append({"id": h.id, "fecha": h.fecha, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
                    "usuario": h.usuario.nombre if h.usuario else None})
    return res


def _fila(cat: dict, obj, refs: dict) -> dict:
    fila = {"id": obj.id}
    for x in campos_propios(cat):
        fila[x["nombre"]] = (obj.extra or {}).get(x["nombre"][6:])
    if campos_variante(cat):
        variantes = obj.variantes
        for x in campos_variante(cat):
            fila[x["nombre"]] = variantes.get(x["nombre"][4:])
    for campo in cat["campos"]:
        v = getattr(obj, campo["nombre"])
        if campo["tipo"] == "opciones":
            fila[campo["nombre"]] = [x for x in (v or "").split(",") if x]
            continue
        if campo["tipo"] == "multi":
            fila[campo["nombre"]] = [x.id for x in v]
            fila[campo["nombre"] + "_txt"] = ", ".join(x.codigo for x in v) or None
            continue
        if campo["tipo"] == "regla_lt":
            fila[campo["nombre"]] = rlt.cargar(v)
            n = len(fila[campo["nombre"]]["pasos"])
            fila[campo["nombre"] + "_txt"] = f"{n} change" if n == 1 else f"{n} changes"
            continue
        fila[campo["nombre"]] = v
        if campo["tipo"] == "ref" and v:
            fila[campo["nombre"] + "_txt"] = refs.get((campo["catalogo"], v))
    if isinstance(obj, Articulo):
        # La ficha técnica y la partida viven en el producto
        prod = producto_de(obj)
        fila["producto_id"] = prod.id if prod else None
        fila["descripcion_txt"] = descripcion_articulo(obj)
        fila["variante"] = " · ".join(str(v) for v in obj.variantes.values() if v not in (None, "")) or None
        fila["codigo_pack"] = obj.codigo_pack
        fila["partida_txt"] = fmt_codigo(prod.codigo) if prod and prod.codigo else None
        fila["clasificacion"] = prod.estado if prod else None
        if obj.tipo == "PREPACK":
            fila["total"] = obj.total_componentes
            fila["componentes"] = len(obj.componentes)
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
    for ex in cat.get("extras", []):
        if ex["nombre"] == "centros_txt" or not ids_obj:
            continue
        hijo = CATALOGOS[ex["catalogo"]]["modelo"]
        if hijo is Articulo and ex["filtro"] == "proveedor_id":
            # El proveedor es del producto: se cuentan las variantes de sus productos
            col = Producto.proveedor_id
            consulta = select(col, func.count(Articulo.id)).join(Producto, Producto.id == Articulo.producto_id)
        else:
            col = getattr(hijo, ex["filtro"])
            consulta = select(col, func.count())
        for padre, n in db.execute(consulta.where(col.in_(ids_obj)).group_by(col)):
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


def es_virtual(modelo, nombre: str) -> bool:
    """Un dato que no es columna sino propiedad del modelo (correos, teléfono,
    dirección y contacto viven en medios_contacto, direcciones y contactos)."""
    import inspect as _inspect

    return isinstance(_inspect.getattr_static(modelo, nombre, None), property)


def _columna_virtual(modelo, nombre: str):
    """Filtro por columna de un dato virtual: la fila pasa si alguno de sus registros tiene el valor."""
    from app.modelos import Contacto, Direccion, MedioContacto

    if hasattr(modelo, "_rol_tercero"):  # proveedor o transportista: en su tercero
        dueno_medio, dueno_dir, padre = MedioContacto.tercero_id, Direccion.tercero_id, modelo.tercero_id
    else:
        clave = {"sociedades": "sociedad_id", "centros": "centro_id", "contactos": "contacto_id"}.get(modelo.__tablename__)
        if clave is None:  # otro dato calculado (p. ej. las tallas de una escala): no se filtra por columna
            return None
        dueno_medio, padre = getattr(MedioContacto, clave), modelo.id
        dueno_dir = getattr(Direccion, clave) if hasattr(Direccion, clave) else None
    if nombre == "correos":
        return tabla.Relacion(MedioContacto.valor, dueno_medio, padre, MedioContacto.tipo == "CORREO")
    if nombre == "telefono":
        return tabla.Relacion(MedioContacto.valor, dueno_medio, padre, MedioContacto.tipo.in_(("TELEFONO", "MOVIL")))
    if nombre == "direccion" and dueno_dir is not None:
        return tabla.Relacion(Direccion.linea1, dueno_dir, padre)
    if nombre == "contacto":
        return tabla.Relacion(Contacto.nombre, Contacto.tercero_id, padre)
    return None


def columnas_tabla(cat: dict) -> dict:
    """Expresión SQL de cada columna de la tabla del catálogo para el filtro por
    columna (app/modulos/comun/tabla.py). Un campo con varios registros (multi)
    filtra por los ids relacionados; los números, por su texto (así el valor
    que se elige es el mismo en SQLite y en PostgreSQL); los campos propios,
    por su dato en `extra`. La regla de lead time no se filtra."""
    modelo = cat["modelo"]
    res = {}
    for x in cat["campos"]:
        n = x["nombre"]
        if x["tipo"] == "regla_lt":
            continue
        if es_virtual(modelo, n):
            if (col := _columna_virtual(modelo, n)) is not None:
                res[n] = col
            continue
        if x["tipo"] == "multi":
            rel = getattr(modelo, n).property
            res[n] = tabla.Relacion(rel.secondary_synchronize_pairs[0][1], rel.synchronize_pairs[0][1], modelo.id)
        elif x["tipo"] == "numero":
            res[n] = cast(getattr(modelo, n), String)
        else:
            res[n] = getattr(modelo, n)
    for x in campos_propios(cat):
        res[x["nombre"]] = modelo.extra[x["nombre"][6:]].as_string()
    for x in campos_variante(cat):
        atributo = select(Atributo.id).where(Atributo.codigo == x["nombre"][4:]).scalar_subquery()
        res[x["nombre"]] = tabla.Relacion(ArticuloAtributo.valor, ArticuloAtributo.articulo_id, Articulo.id,
                                          donde=ArticuloAtributo.atributo_id == atributo)
    if modelo is Articulo:
        # Lo que vive en el producto o en los códigos del artículo
        res["generico"] = tabla.Relacion(Producto.codigo_generico, Producto.id, Articulo.producto_id)
        res["proveedor_id"] = tabla.Relacion(Producto.proveedor_id, Producto.id, Articulo.producto_id)
        for campo, tipo in (("codigo_barras", "BARRAS"), ("codigo_proveedor", "PROVEEDOR")):
            res[campo] = tabla.Relacion(ArticuloCodigo.valor, ArticuloCodigo.articulo_id, Articulo.id,
                                        donde=ArticuloCodigo.tipo == tipo)
    return res


def valores(db: Session, user: Usuario, tipo: str, columna: str, buscar: str | None, filtros_columna: dict,
            q: str | None = None, filtros: dict | None = None) -> list[dict]:
    """Valores únicos de una columna del catálogo, con cuántos registros tienen
    cada uno, bajo la búsqueda y los demás filtros (como el filtro de Excel)."""
    cat, consulta = _consulta(db, user, tipo, q, filtros or {})
    cols = columnas_tabla(cat)
    expr = tabla.columna_valida(cols, columna)
    consulta = tabla.aplicar(consulta, cols, filtros_columna, excepto=columna)
    return tabla.valores(db, consulta, expr, buscar, contar=cat["modelo"].id)


def listar(db: Session, user: Usuario, tipo: str, q: str | None, filtros: dict, orden: str | None,
           page: int, size: int, filtros_columna: dict | None = None) -> dict:
    cat, consulta = _consulta(db, user, tipo, q, filtros)
    modelo = cat["modelo"]
    cols = columnas_tabla(cat)
    consulta = tabla.aplicar(consulta, cols, filtros_columna or {})
    nombres = {x["nombre"]: x for x in cat["campos"]}
    col, _, direccion = (orden or "").partition(":")
    if col in nombres and nombres[col]["tipo"] not in ("multi", "regla_lt") and not es_virtual(modelo, col):
        expr = getattr(modelo, col)
        consulta = consulta.order_by(expr.desc() if direccion == "desc" else expr.asc(), modelo.id)
    elif col.startswith("extra.") and col in cols:
        consulta = consulta.order_by(cols[col].desc() if direccion == "desc" else cols[col].asc(), modelo.id)
    else:
        consulta = consulta.order_by(modelo.id)
    total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    objs = list(db.scalars(consulta.offset((page - 1) * size).limit(size)).all())
    refs = _refs(db, cat, objs)
    return {"items": [_fila(cat, o, refs) for o in objs], "total": total, "page": page, "size": size}


def _consulta(db: Session, user: Usuario, tipo: str, q: str | None, filtros: dict):
    """Registros del catálogo con la búsqueda y los filtros por campo de la
    pantalla (sin los filtros por columna ni el orden)."""
    exigir(user, "catalogos.ver")
    cat = _cat(tipo)
    modelo = cat["modelo"]
    consulta = select(modelo)
    if cat.get("donde"):
        consulta = consulta.where(cat["donde"]())
    if q:
        consulta = consulta.where(filtro_texto(q, lambda p: [getattr(modelo, b).ilike(p) for b in cat["buscar"]
                                                             if not es_virtual(modelo, b)] + _buscar_extra(modelo, p)))
    nombres = {x["nombre"]: x for x in cat["campos"]}
    for k, v in filtros.items():
        if modelo is Articulo and k == "proveedor_id" and v not in (None, ""):
            consulta = consulta.where(Articulo.producto_id.in_(select(Producto.id).where(Producto.proveedor_id == int(v))))
            continue
        if k not in nombres or v in (None, "") or es_virtual(modelo, k):
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
    return cat, consulta


def _buscar_extra(modelo, p) -> list:
    """Búsqueda en lo que no es columna del registro: un artículo también por su producto y sus códigos."""
    if modelo is not Articulo:
        return []
    return [Articulo.producto_id.in_(select(Producto.id).where(Producto.codigo_generico.ilike(p) | Producto.nombre.ilike(p))),
            Articulo.id.in_(select(ArticuloCodigo.articulo_id).where(ArticuloCodigo.valor.ilike(p)))]


def descripcion_articulo(a: Articulo) -> str | None:
    """La descripción del artículo: la suya o la del producto con los valores de la variante."""
    if a.descripcion:
        return a.descripcion
    prod = a.producto
    base = (prod.descripcion_comercial or prod.nombre) if prod else None
    valores = " · ".join(str(v) for v in a.variantes.values() if v not in (None, ""))
    if a.tipo == "PREPACK" and a.codigo_pack:
        valores = f"pack {a.codigo_pack}"
    return ", ".join(x for x in (base, valores) if x) or None


def opciones(db: Session, user: Usuario, tipo: str) -> list[dict]:
    """Lista corta (id, código, texto) para selects y filtros."""
    exigir(user, "catalogos.ver")
    cat = _cat(tipo)
    modelo = cat["modelo"]
    objs = db.scalars(select(modelo).order_by(modelo.id)).all()
    clave = "sku" if tipo == "articulos" else "codigo"
    # Datos para filtrar campos dependientes: sus referencias y, al revés, qué
    # registros de otros catálogos lo incluyen (p. ej. los proveedores de una marca)
    propios = [x for x in cat["campos"] if x["tipo"] in ("ref", "codigo", "multi", "opcion")]
    inversas = [(t, x["nombre"]) for t, c2 in CATALOGOS.items() for x in c2["campos"]
                if x["tipo"] == "multi" and x.get("catalogo") == tipo]
    inv: dict[str, dict[int, list[int]]] = {}
    for t, campo in inversas:
        m = inv.setdefault(t, {})
        for otro in db.scalars(select(CATALOGOS[t]["modelo"])).all():
            for rel in getattr(otro, campo):
                m.setdefault(rel.id, []).append(otro.id)
    # Nombres de los registros referidos (país de un puerto, región de un país…):
    # van en `sub` para que la búsqueda los encuentre ("vietnam cat" → Cat Lai)
    nombres_ref: dict[str, dict] = {}
    for x in propios:
        if x["tipo"] in ("ref", "codigo") and x.get("catalogo") and x["catalogo"] != tipo:
            m = CATALOGOS[x["catalogo"]]["modelo"]
            k = "id" if x["tipo"] == "ref" else ("sku" if x["catalogo"] == "articulos" else "codigo")
            nombres_ref[x["nombre"]] = {getattr(r, k): (getattr(r, "nombre", None) or _mostrar(r))
                                        for r in db.scalars(select(m)).all()}
    res = []
    for o in objs:
        fila = {"id": o.id, "codigo": getattr(o, clave), "texto": _mostrar(o)}
        sub = [nombres_ref[n].get(getattr(o, n)) for n in nombres_ref if getattr(o, n, None) is not None]
        if any(sub):
            fila["sub"] = " · ".join(x for x in sub if x)
        if hasattr(o, "activo") or hasattr(o, "activa"):
            fila["activo"] = bool(getattr(o, "activo", getattr(o, "activa", True)))
        for x in propios:
            v = getattr(o, x["nombre"])
            fila[x["nombre"]] = [y.id for y in v] if x["tipo"] == "multi" else v
        for t, m in inv.items():
            fila[t] = m.get(o.id, [])
        res.append(fila)
    return res


def _valor_dato(db: Session, catalogo: str, valor, clave: str):
    """Dato `clave` de la opción elegida (id o código) de un catálogo."""
    modelo = CATALOGOS[catalogo]["modelo"]
    obj = db.get(modelo, valor) if isinstance(valor, int) else db.scalar(select(modelo).where(modelo.codigo == valor))
    if not obj:
        return None
    if hasattr(obj, clave):
        v = getattr(obj, clave)
        return [y.id for y in v] if isinstance(v, list) else v
    # Relación inversa: qué registros de `clave` (otro catálogo) incluyen esta opción
    for x in CATALOGOS.get(clave, {}).get("campos", []):
        if x["tipo"] == "multi" and x.get("catalogo") == catalogo:
            m = CATALOGOS[clave]["modelo"]
            return [o.id for o in db.scalars(select(m)).all() if obj in getattr(o, x["nombre"])]
    return None


def _dependencias(db: Session, cat: dict, final: dict) -> list[dict]:
    """Valida los campos dependientes declarados en el catálogo."""
    errores = []
    for x in cat["campos"]:
        dep = x.get("depende")
        v, base = final.get(x["nombre"]), final.get((dep or {}).get("campo"))
        if not dep or v in (None, "", []) or base in (None, ""):
            continue
        for elegido in (v if isinstance(v, list) else [v]):
            ident = elegido.id if hasattr(elegido, "id") else elegido
            dato = _valor_dato(db, x["catalogo"], ident, dep["clave"])
            ok = (base in dato) if isinstance(dato, list) else (dato == base)
            if not ok:
                nombre_base = next((y["etiqueta"] for y in cat["campos"] if y["nombre"] == dep["campo"]), dep["campo"])
                errores.append({"campo": x["nombre"], "mensaje":
                                f"{x['etiqueta']}: the option chosen does not belong to the selected {nombre_base.lower()}."})
                break
    return errores


def _limpiar(db: Session, cat: dict, datos: dict, parcial: bool, actual=None) -> dict:
    import re

    errores = []
    limpio = {}
    for campo in cat["campos"]:
        n = campo["nombre"]
        if campo.get("solo_lectura"):
            continue
        obligatorio = _obligatorio(cat, campo)
        if n not in datos:
            if not parcial and obligatorio:
                errores.append({"campo": n, "mensaje": f"{campo['etiqueta']} is required."})
            continue
        v = datos[n]
        if campo["tipo"] == "regla_lt":
            regla, errs = rlt.validar(db, v)
            if errs:
                errores.extend({"campo": n, "mensaje": e} for e in errs)
            else:
                limpio[n] = regla
            continue
        if isinstance(v, str):
            v = nombre_fmt(v) if campo.get("formato") == "nombre" else texto_fmt(v)
            if campo.get("mayus"):
                v = v.upper()
        if v in ("", None) or (campo["tipo"] == "multi" and v == [] and not obligatorio):
            if campo["tipo"] == "multi":
                if obligatorio:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: choose at least one."})
                else:
                    limpio[n] = []
                continue
            v = None
        if v is None:
            if obligatorio:
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
                if campo.get("minimo") is not None and v < campo["minimo"]:
                    raise ValueError
            elif t == "fecha":
                from datetime import date as _fecha

                v = v if isinstance(v, _fecha) else _fecha.fromisoformat(str(v)[:10])
            elif t == "bool":
                v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "si", "sí")
            elif t == "ref":
                v = int(v)
                if not db.get(CATALOGOS[campo["catalogo"]]["modelo"], v):
                    raise ValueError
            elif t == "codigo":
                # El código o el nombre, escrito de cualquier forma, se enlaza con el registro
                modelo = CATALOGOS[campo["catalogo"]]["modelo"]
                obj = db.scalar(select(modelo).where(modelo.codigo == str(v).upper())) or \
                    Referencias(db, modelo).buscar(v)
                if not obj:
                    errores.append({"campo": n, "mensaje": f"{campo['etiqueta']}: {v} is not in the catalog."})
                    continue
                v = obj.codigo
            elif t == "opciones":
                elegidas = v if isinstance(v, list) else [x.strip() for x in str(v).split(",") if x.strip()]
                validas = [o[0] for o in _opciones(campo)]
                if any(x not in validas for x in elegidas):
                    raise ValueError
                v = ",".join(x for x in validas if x in elegidas) or None
            elif t == "opcion" and v not in [o[0] for o in _opciones(campo)] \
                    and not (actual and v == getattr(actual, n)):  # un valor ya guardado que se desactivó
                raise ValueError
            elif t == "multi":
                ids = v if isinstance(v, list) else [x for x in str(v).split(",") if x.strip()]
                modelo = CATALOGOS[campo["catalogo"]]["modelo"]
                objs = list(db.scalars(select(modelo).where(modelo.id.in_([int(x) for x in ids])))) if ids else []
                if len(objs) != len(set(int(x) for x in ids)):
                    raise ValueError
                if obligatorio and not objs:
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

    if cat["modelo"] is Atributo:
        d = {**({k: getattr(actual, k) for k in ("codigo", "nivel", "tipo", "opciones", "catalogo", "unidad")}
                if actual else {}), **limpio}
        errores += _validar_atributo(db, d, actual)
        if (d.get("tipo") or "texto") != "catalogo":
            limpio["catalogo"] = None

    # Atributos de variante: uno por atributo, con el tipo de valor de cada uno
    if cat["modelo"] is Articulo:
        crudos = {k[4:]: v for k, v in datos.items() if k.startswith("atr.")}
        if crudos:
            valores, errs = atr_svc.validar(db, "VARIANTE", crudos, campo="atr")
            errores += [{**e, "campo": e["campo"].replace("atr.", "atr.", 1)} for e in errs]
            if not errs:
                limpio["variantes"] = {k: v for k, v in {**(actual.variantes if actual else {}), **valores}.items() if v}

    # Campos propios: se validan con su tipo y se guardan juntos en extra
    propios = {k[6:]: v for k, v in datos.items() if k.startswith("extra.")}
    if hasattr(cat["modelo"], "extra") and (propios or not parcial):
        try:
            limpio["extra"] = limpiar_propios(_tipo_de(cat), propios, actual.extra if actual else None, parcial)
        except ErrorNegocio as e:
            errores += e.detalle or []
    final = {**({c["nombre"]: getattr(actual, c["nombre"]) for c in cat["campos"]} if actual else {}), **limpio}
    if cat["modelo"] is PasoLeadTime:
        # Un paso con fecha medida pertenece al documento que la registra
        propio = rlt.DOCUMENTO_HITO.get(final.get("hito") or "")
        if propio and not final.get("documento"):
            limpio["documento"] = final["documento"] = propio
        elif propio and final.get("documento") != propio:
            errores.append({"campo": "documento", "mensaje": "That measured date is recorded on another document: "
                            f"{dict(rlt.DOCUMENTOS)[propio].lower()}."})
    if cat["modelo"] is Articulo:
        errores += _validar_articulo(db, final, limpio, actual)
    if cat["modelo"] is Proveedor and actual and "marcas" in limpio:
        quedan = {m.codigo for m in limpio["marcas"]}
        usadas = set(db.scalars(select(ProductoAtributo.valor).join(Atributo).join(Producto).where(
            Atributo.catalogo == "marcas", Producto.proveedor_id == actual.id).distinct()))
        if usadas - quedan:
            errores.append({"campo": "marcas", "mensaje":
                            f"The supplier has products of {', '.join(sorted(usadas - quedan))}: those brands cannot be removed."})
    if cat["modelo"] is Proveedor and actual and "sociedades" in limpio:
        quedan = {x.codigo for x in limpio["sociedades"]}
        usadas = {c for (c,) in db.execute(select(OrdenCompra.sociedad).where(
            OrdenCompra.proveedor_id == actual.id, OrdenCompra.sociedad.is_not(None)).distinct())}
        if usadas - quedan:
            errores.append({"campo": "sociedades", "mensaje":
                            f"The supplier has purchase orders with {', '.join(sorted(usadas - quedan))}: "
                            "those companies cannot be removed."})
    if cat["modelo"] is ReglaLeadTime:
        errores += _validar_regla_lt(db, final, actual, limpio)
    if cat["modelo"] is EstadoLiberacion:
        otros = [x for x in db.scalars(select(EstadoLiberacion).where(EstadoLiberacion.tipo == final.get("tipo")))
                 if not actual or x.id != actual.id]
        if final.get("predeterminado") and any(x.predeterminado for x in otros):
            errores.append({"campo": "predeterminado", "mensaje": "There is already a default status for this release."})
        if final.get("con_cambios") and (final.get("tipo") != "LOGISTICA" or not final.get("libera")):
            errores.append({"campo": "con_cambios", "mensaje": "Only a released logistics status can be the one with later changes."})
        if final.get("con_cambios") and any(x.con_cambios for x in otros):
            errores.append({"campo": "con_cambios", "mensaje": "There is already a status for released POs with later changes."})
        if actual and "codigo" in limpio and limpio["codigo"] != actual.codigo:
            col = OrdenCompra.liberacion_comercial if actual.tipo == "COMERCIAL" else OrdenCompra.liberacion_logistica
            if db.scalar(select(OrdenCompra.id).where(col == actual.codigo).limit(1)):
                errores.append({"campo": "codigo", "mensaje": "Purchase orders use this code: it cannot change."})
    if cat["modelo"] is ValorLista or cat.get("lista"):
        from app.modulos.maestros.listas import validar as validar_valor

        errores += validar_valor(db, final, actual, limpio, cat.get("lista"))
    if cat["modelo"] is EscalaValores:
        from app.modulos.maestros.escalas import validar as validar_escala

        if final.get("valores"):
            errores += [{"campo": "valores", "mensaje": m} for m in validar_escala(final["valores"])]
        if final.get("regla") == "MULTIPLICAR" and not final.get("factor"):
            errores.append({"campo": "factor", "mensaje": "Enter the factor for the rule Value × factor."})
        if final.get("atributo") and not db.scalar(select(Atributo.id).where(Atributo.codigo == final["atributo"],
                                                                            Atributo.nivel == "VARIANTE")):
            errores.append({"campo": "atributo", "mensaje": "Choose a variant attribute."})
    if cat["modelo"] is Contacto and not final.get("sociedad_id") and not final.get("centro_id"):
        errores.append({"campo": "sociedad_id", "mensaje": "Enter the contact's company or plant."})
    if cat["modelo"] in (Centro, Almacen) and actual and "sociedad_id" in limpio and limpio["sociedad_id"] != actual.sociedad_id:
        campo_oc = OrdenCompra.centro_destino if cat["modelo"] is Centro else None
        en_uso = db.scalar(select(OrdenCompra.id).where(
            (OrdenCompra.centro == actual.codigo) | (campo_oc == actual.codigo) if campo_oc is not None
            else OrdenCompra.id.in_(select(PosicionOC.oc_id).where(PosicionOC.almacen == actual.codigo))).limit(1))
        if en_uso:
            errores.append({"campo": "sociedad_id", "mensaje": "It is used on purchase orders: its company cannot change."})
    ya = {e.get("campo") for e in errores}
    errores += [e for e in _dependencias(db, cat, final) if e["campo"] not in ya]
    if errores:
        raise ErrorNegocio("Check the data.", 422, "validacion", errores)
    return limpio


def crear(db: Session, user: Usuario, tipo: str, datos: dict) -> dict:
    exigir(user, "catalogos.crear")
    exigir_editable(tipo)
    exigir_compartido(user, tipo)
    gobierno.exigir_responsable(db, user, tipo)
    cat = _cat(tipo)
    limpio = _limpiar(db, cat, datos, parcial=False)
    for campo in cat["campos"]:
        if campo["tipo"] == "bool" and campo["nombre"] not in datos:
            limpio[campo["nombre"]] = campo.get("defecto", True)
    virtuales = {k: limpio.pop(k) for k in cat.get("virtuales", ()) if k in limpio}
    variantes = limpio.pop("variantes", None)
    obj = cat["modelo"](**limpio)
    if isinstance(obj, Articulo):
        asegurar_producto(db, obj, virtuales.get("generico"))
        db.add(obj)
        if variantes:
            obj.variantes = variantes
        _poner_codigos(obj, virtuales)
    try:
        with db.begin_nested():
            db.add(obj)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"A {cat['singular']} with that code already exists.", 409, "duplicado") from None
    if isinstance(obj, Articulo):
        _exigir_articulo(db, obj)
    _asegurar_tercero(db, obj)
    registrar(db, user, tipo, obj.id, "crear", {"codigo": _mostrar(obj)})
    return _fila(cat, obj, _refs(db, cat, [obj]))


def _asegurar_tercero(db: Session, obj) -> None:
    """Un proveedor o transportista tiene su tercero (identidad fiscal, direcciones y contacto)."""
    from app.modulos.maestros.terceros import asegurar

    if isinstance(obj, Proveedor):
        asegurar(db, obj, "PROVEEDOR")
    elif isinstance(obj, Transportista):
        asegurar(db, obj, "TRANSPORTISTA")


def actualizar(db: Session, user: Usuario, tipo: str, obj_id: int, datos: dict) -> dict:
    exigir(user, "catalogos.editar")
    exigir_editable(tipo)
    exigir_compartido(user, tipo)
    gobierno.exigir_responsable(db, user, tipo)
    cat = _cat(tipo)
    obj = db.get(cat["modelo"], obj_id)
    if not obj:
        raise ErrorNegocio(f"The {cat['singular']} does not exist.", 404, "no_encontrado")
    limpio = _limpiar(db, cat, datos, parcial=True, actual=obj)
    if "codigo" in limpio and limpio["codigo"] != getattr(obj, "codigo", None) and gobierno.en_uso(db, tipo, obj.codigo):
        raise ErrorNegocio(f"{obj.codigo} is used in documents or other records: its code cannot change.", 409, "en_uso",
                           [{"campo": "codigo", "mensaje": "It is in use: its code cannot change."}])
    cambios = {}
    if isinstance(obj, Articulo):
        cambios.update(_cambiar_virtuales(db, obj, {k: limpio.pop(k) for k in cat.get("virtuales", ()) if k in limpio}))
        variantes = limpio.pop("variantes", None)
        if variantes is not None and variantes != obj.variantes:
            cambios["variantes"] = [obj.variantes, variantes]
            obj.variantes = variantes
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
    if isinstance(obj, Articulo) and cambios:
        _exigir_articulo(db, obj)
    if {"nombre", "razon_social", "id_fiscal", "pais"} & set(cambios):
        _asegurar_tercero(db, obj)
    if cambios:
        registrar(db, user, tipo, obj.id, "editar", cambios)
    return _fila(cat, obj, _refs(db, cat, [obj]))


def _poner_codigos(a: Articulo, virtuales: dict) -> None:
    if "codigo_barras" in virtuales:
        a.poner_codigo("BARRAS", virtuales["codigo_barras"])
    if "codigo_proveedor" in virtuales:
        a.poner_codigo("PROVEEDOR", virtuales["codigo_proveedor"], a.proveedor_id)


def _cambiar_virtuales(db: Session, a: Articulo, virtuales: dict) -> dict:
    """Producto y códigos del artículo editado en el catálogo: {dato: [antes, después]} de lo que cambió."""
    cambios = {}
    gen = virtuales.get("generico")
    if gen and gen != a.generico:
        cambios["generico"] = [a.generico, gen]
        asegurar_producto(db, a, gen)
    for campo in ("codigo_barras", "codigo_proveedor"):
        if campo in virtuales and (virtuales[campo] or None) != getattr(a, campo):
            cambios[campo] = [getattr(a, campo), virtuales[campo]]
    _poner_codigos(a, {k: v for k, v in virtuales.items() if k in cambios})
    return cambios


def _exigir_articulo(db: Session, a: Articulo) -> None:
    """Lo que la empresa y la familia exigen a la variante guardada."""
    from app.modulos.maestros.genericos import _exigidos_empresa
    from app.modulos.productos import perfil

    db.flush()
    errores = _exigidos_empresa(db, a)
    if errores:
        raise ErrorNegocio("Some data your company requires is missing.", 422, "validacion", errores)
    perfil.exigir_variantes(db, [a])


def _validar_articulo(db: Session, final: dict, limpio: dict, actual: Articulo | None) -> list[dict]:
    """Reglas del artículo en el catálogo: un compuesto (pack o kit) se crea con su contenido
    en su propia acción y ya no cambia lo que lo enlaza; una variante que está en un compuesto
    no cambia su unidad ni sus valores; dos variantes de un producto no repiten valores."""
    from app.modulos.maestros.genericos import validar_codigos

    errores = []
    if final.get("tipo") == "PREPACK" and not (actual and actual.tipo == "PREPACK"):
        errores.append({"campo": "tipo", "mensaje": "Packs and kits are created with their own action, with their item "
                                                    "code and contents."})
    elif actual and actual.tipo == "PREPACK":
        fijos = [c for c in ("tipo", "unidad", "generico") if c in limpio and limpio[c] != getattr(actual, c)]
        if fijos:
            errores.append({"campo": fijos[0], "mensaje": "A pack or kit and its contents cannot change (product, unit and "
                                                          "type). Create a new one."})
    elif final.get("tipo") == "SOLIDO":
        if actual and db.scalar(select(ArticuloComponente.id).where(ArticuloComponente.componente_id == actual.id).limit(1)):
            if ("unidad" in limpio and limpio["unidad"] != actual.unidad) or \
                    ("variantes" in limpio and limpio["variantes"] != actual.variantes):
                errores.append({"campo": "unidad", "mensaje": "This item is part of a pack or kit: its unit and its "
                                                              "variant values cannot change."})
        if final.get("unidad") in unidades.de_compuestos():
            errores.append({"campo": "unidad", "mensaje": "That unit is only for packs and kits."})
    if actual and "generico" in limpio and limpio["generico"] and limpio["generico"] != actual.generico \
            and db.scalar(select(PosicionOC.id).where(PosicionOC.articulo_id == actual.id).limit(1)):
        errores.append({"campo": "generico", "mensaje": "The item is on purchase orders: its product cannot change."})
    errores += [{"campo": "codigo_barras", "mensaje": m} for m in validar_codigos(db, final.get("codigo_barras"),
                                                                                 final.get("codigo_proveedor"))]
    gen = generico_de(final)
    if gen and final.get("tipo") == "SOLIDO":
        errores += _variante_repetida(db, gen, limpio, actual)
    return errores


def _variante_repetida(db: Session, gen: str, limpio: dict, actual) -> list[dict]:
    """Dos variantes de un mismo producto no pueden tener los mismos valores de variante."""
    valores = {k: str(v) for k, v in (limpio.get("variantes") if "variantes" in limpio
                                      else (actual.variantes if actual else {})).items() if v not in (None, "")}
    if not valores:
        return []
    otras = db.scalars(select(Articulo).join(Producto).where(Producto.codigo_generico == gen, Articulo.tipo == "SOLIDO",
                                                             *([Articulo.id != actual.id] if actual else [])))
    for o in otras:
        if {k: str(v) for k, v in o.variantes.items() if v not in (None, "")} == valores:
            return [{"campo": "sku", "mensaje": f"{o.sku} is already the variant {' · '.join(valores.values())} of product {gen}."}]
    return []


def _en_uso_atributo(db: Session, atributo_id: int) -> bool:
    return bool(db.scalar(select(ArticuloAtributo.id).where(ArticuloAtributo.atributo_id == atributo_id).limit(1))
                or db.scalar(select(ProductoAtributo.id).where(ProductoAtributo.atributo_id == atributo_id).limit(1)))


def _validar_atributo(db: Session, d: dict, actual) -> list[dict]:
    """Un atributo de opciones necesita sus opciones; uno de catálogo, su catálogo; la unidad es de
    los números. Uno en uso no cambia su código ni su nivel, y cambia su tipo solo si los valores
    guardados siguen valiendo."""
    tipo = d.get("tipo") or "texto"
    if tipo == "opcion" and not atr_svc.opciones(d):
        return [{"campo": "opciones", "mensaje": "Write the options, separated by commas."}]
    if tipo == "catalogo" and not d.get("catalogo"):
        return [{"campo": "catalogo", "mensaje": "Choose the catalog its values come from."}]
    if d.get("unidad") and tipo != "numero":
        return [{"campo": "unidad", "mensaje": "Only numbers have a unit."}]
    if actual is None or not _en_uso_atributo(db, actual.id):
        return []
    if d.get("codigo") != actual.codigo:
        return [{"campo": "codigo", "mensaje": "Products already use this attribute: its code cannot change."}]
    if d.get("nivel") != actual.nivel:
        return [{"campo": "nivel", "mensaje": "Products already use this attribute: its level cannot change."}]
    usados = list(db.scalars(select(ArticuloAtributo.valor).where(ArticuloAtributo.atributo_id == actual.id)
                             .distinct().limit(500))) + \
        list(db.scalars(select(ProductoAtributo.valor).where(ProductoAtributo.atributo_id == actual.id).distinct().limit(500)))
    malos = [v for v in usados if atr_svc.valor(db, d, v)[1]]
    if malos:
        return [{"campo": "tipo" if tipo != "opcion" else "opciones",
                 "mensaje": f"Products already have values that do not fit ({', '.join(malos[:5])}): change them first."}]
    return []


def _validar_regla_lt(db: Session, final: dict, actual, limpio: dict) -> list[dict]:
    """Una regla por ámbito, con su ámbito según el nivel, y la cadena que
    resulta (con lo heredado) debe ser válida."""
    errores = []
    nivel = final.get("nivel")
    campo = rlt.CAMPO_NIVEL.get(nivel)
    for otro in rlt.CAMPO_NIVEL.values():
        if otro != campo:
            final[otro] = limpio[otro] = None
    ambito = final.get(campo) if campo else None
    if campo and not ambito:
        return [{"campo": campo, "mensaje": "Choose the scope of this level."}]
    filtro = [ReglaLeadTime.nivel == nivel] + ([getattr(ReglaLeadTime, campo) == ambito] if campo else [])
    otra = db.scalar(select(ReglaLeadTime.id).where(*filtro, ReglaLeadTime.id != (actual.id if actual else 0)))
    if otra:
        errores.append({"campo": campo or "nivel", "mensaje": "There is already a rule for that scope; edit it."})
    regla = rlt.cargar(final.get("pasos"))
    kw = {campo: ambito} if campo else {}
    res = rlt.efectivo(db, **kw, con_regla=(nivel, ambito, regla))
    errores += [{"campo": "pasos", "mensaje": m} for m in res["errores"]]
    return errores


def eliminar(db: Session, user: Usuario, tipo: str, obj_id: int) -> dict:
    exigir(user, "catalogos.eliminar")
    exigir_editable(tipo)
    exigir_compartido(user, tipo)
    gobierno.exigir_responsable(db, user, tipo)
    cat = _cat(tipo)
    obj = db.get(cat["modelo"], obj_id)
    if not obj:
        raise ErrorNegocio(f"The {cat['singular']} does not exist.", 404, "no_encontrado")
    gobierno.exigir_sin_uso(db, tipo, obj)
    from app.modulos.maestros.listas import lista_de

    if obj.codigo in listas.LISTAS.get(lista_de(obj) or "", {}).get("sistema", []):
        raise ErrorNegocio("The system relies on this value: it can be renamed but not deleted.", 409, "en_uso")
    if isinstance(obj, Atributo) and _en_uso_atributo(db, obj.id):
        raise ErrorNegocio("Products use this attribute: deactivate it instead.", 409, "en_uso")
    if isinstance(obj, PasoLeadTime):
        usan = [r.nombre for r in db.scalars(select(ReglaLeadTime)) if any(
            e["paso"] == obj.codigo or e.get("ref") == obj.codigo for e in rlt.cargar(r.pasos)["pasos"])]
        if usan:
            raise ErrorNegocio(f"It cannot be deleted: the step is used in {', '.join(usan)}. Deactivate it instead.",
                               409, "en_uso")
    try:
        with db.begin_nested():
            db.delete(obj)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio(f"It cannot be deleted: the {cat['singular']} is in use. Deactivate it instead.",
                           409, "en_uso") from None
    registrar(db, user, tipo, obj_id, "eliminar", None)
    return {"ok": True}


# ---- Packs y kits: su contenido -------------------------------------------
def componentes(db: Session, user: Usuario, articulo_id: int, validar: bool = True) -> dict:
    if validar:
        exigir(user, "catalogos.ver")
    a = db.get(Articulo, articulo_id)
    if not a or a.tipo != "PREPACK":
        raise ErrorNegocio("That item is not a pack or kit.", 404, "no_encontrado")
    from app.modulos.maestros import variantes as var_svc

    return {
        "id": a.id, "sku": a.sku, "unidad": a.unidad, "codigo": a.codigo_pack, "descripcion": descripcion_articulo(a),
        "generico": a.generico, "kit": a.es_kit, "total": a.total_componentes,
        "marca": a.producto.marca_codigo if a.producto else None,
        "unidad_componentes": a.componentes[0].componente.unidad if a.componentes else None,
        "componentes": [{"articulo_id": x.componente_id, "sku": x.componente.sku, "unidad": x.componente.unidad,
                         "valores": var_svc.de_articulo(db, x.componente),
                         "variante": var_svc.texto(var_svc.de_articulo(db, x.componente)) or None,
                         "cantidad": x.cantidad} for x in a.componentes],
    }


def _validar_contenido(db: Session, items: list[dict], kit: bool = False) -> tuple[list, list]:
    """Solo artículos simples con cantidad y sin repetir artículo. Un pack junta
    variantes de un mismo producto (tallas, sabores, presentaciones…) en una misma
    unidad; un kit junta artículos de cualquier producto."""
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
            errores.append({"mensaje": f"{a.sku}: a pack or kit only carries simple items."})
        if cant < 1:
            errores.append({"mensaje": f"{a.sku}: the quantity must be greater than zero."})
        arts.append((a, cant))
    if not arts:
        errores.append({"mensaje": "The contents need at least one simple item."})
    if len({a.id for a, _ in arts}) != len(arts):
        errores.append({"mensaje": "An item appears twice in the contents."})
    if not kit and arts:
        producto = arts[0][0].producto_id
        otros = [a for a, _ in arts if a.producto_id != producto]
        if otros:
            lista = ", ".join(f"{a.sku} ({a.generico})" for a in otros)
            errores.append({"mensaje": f"A pack carries variants of one product ({arts[0][0].generico}): {lista} is another "
                                       "product. Use a kit."})
        if len({a.unidad for a, _ in arts}) > 1:
            errores.append({"mensaje": "The variants of a pack go in the same unit."})
    return arts, errores


def crear_compuesto(db: Session, user: Usuario, datos: dict) -> dict:
    """Crea el pack o el kit completo en un paso: su artículo con su propio código, su
    identificador (p. ej. AB12) y su contenido. Un pack es del producto de sus variantes
    y comparte su ficha; un kit es su propio producto. El contenido ya no cambia."""
    import re

    exigir(user, "catalogos.crear")
    gobierno.exigir_responsable(db, user, "articulos")
    sku = str(datos.get("sku") or "").strip().upper()
    codigo = str(datos.get("codigo") or "").strip().upper()
    kit = str(datos.get("tipo") or "PACK").upper() == "KIT"
    unidad = unidades.normalizar(datos.get("unidad")) or unidades.de_compuesto()
    errores = []
    if not codigo_valido(sku):
        errores.append({"campo": "sku", "mensaje": "Item code: letters and numbers (also . - _ /), up to 40 characters."})
    elif db.scalar(select(Articulo.id).where(Articulo.sku == sku)):
        errores.append({"campo": "sku", "mensaje": f"Code {sku} already exists in the item master."})
    if not re.fullmatch(r"[A-Z0-9]{2,10}", codigo):
        errores.append({"campo": "codigo", "mensaje": "Pack ID: letters and numbers, for example AB12."})
    if unidad not in unidades.codigos() or not unidades.contable(unidad):
        errores.append({"campo": "unidad", "mensaje": "A pack or kit is counted in whole units: choose a counted unit."})
    arts, err = _validar_contenido(db, datos.get("componentes") or [], kit=kit)
    errores += err
    base = arts[0][0] if arts else None
    # Un kit es su propio producto; un pack es del producto de sus variantes
    generico = sku if kit else (base.generico if base else None)
    if generico and not kit and not errores and db.scalar(
            select(ArticuloCodigo.id).join(Articulo).where(Articulo.producto_id == base.producto_id,
                                                          ArticuloCodigo.tipo == "PACK", ArticuloCodigo.valor == codigo)):
        errores.append({"campo": "codigo", "mensaje": f"Pack {codigo} already exists for product {generico}."})
    if errores:
        raise ErrorNegocio("The pack is not valid.", 422, "validacion", errores)
    prod = base.producto
    nombre = (prod.nombre if prod and prod.nombre else None) or generico
    total = sum(c for _, c in arts)
    descripcion = (str(datos.get("descripcion") or "").strip()[:300]
                   or (f"{nombre} kit {codigo} ({total} pieces)" if kit else
                       f"{nombre} pack {codigo} ({total} {unidades.texto(base.unidad, total)})"))
    art = Articulo(sku=sku, descripcion=descripcion, unidad=unidad, tipo="PREPACK", activo=True,
                   peso_unitario=round(sum((a.peso_unitario or 0) * c for a, c in arts), 4)
                   if all(a.peso_unitario for a, _ in arts) else None)
    if kit:
        asegurar_producto(db, art, generico, prod.proveedor_id if prod else None)
    else:
        art.producto = prod
    db.add(art)
    art.poner_codigo("PACK", codigo)
    art.poner_codigo("BARRAS", (datos.get("codigo_barras") or "").strip() or None)
    for a, cant in arts:
        art.componentes.append(ArticuloComponente(componente=a, cantidad=cant, organizacion_id=art.organizacion_id))
    db.flush()
    registrar(db, user, "articulos", art.id, "crear",
              {"sku": sku, "pack": codigo, "kit": kit, "contenido": {a.sku: c for a, c in arts}})
    return componentes(db, user, art.id)


def explosion(db: Session, user: Usuario, sku: str) -> dict:
    """Contenido de un pack o un kit, de solo lectura (para OC, factura, packing list y seguimiento)."""
    exigir(user, "oc.ver")
    a = db.scalar(select(Articulo).where(Articulo.sku == sku))
    if not a or a.tipo != "PREPACK" or not a.componentes:
        raise ErrorNegocio("That code is not a pack or kit.", 404, "no_encontrado")
    return componentes(db, user, a.id, validar=False)


# ---- Carga masiva ----------------------------------------------------------
# Columnas de las plantillas en inglés -> nombre interno (también se aceptan los internos)
COLUMNAS_EN = {"description": "descripcion", "supplier": "proveedor", "type": "tipo", "uom": "unidad", "unit": "unidad",
               "hs_code": "partida_arancelaria", "country_of_origin": "pais_origen", "pack_item_code": "sku_pack",
               "pack_id": "pack", "item_code": "sku", "quantity": "cantidad", "qty": "cantidad", "kind": "tipo"}
CAMPO_EN = {"proveedor": "Supplier"}


def _filas_archivo(nombre: str, contenido: bytes) -> list[dict]:
    from app.modulos.compras.ordenes import _norm, _texto

    if nombre.lower().endswith((".xlsx", ".xlsm")):
        wb = abrir_libro(contenido, read_only=True, data_only=True)
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


def importar_compuestos(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Columnas: sku_pack (código de artículo del pack o kit), pack (su identificador, p. ej.
    AB12), tipo (PACK o KIT), descripcion, sku (variante simple) y cantidad. Una fila por
    variante del contenido. Un compuesto que ya existe no cambia."""
    exigir(user, "catalogos.crear")
    filas = _filas_archivo(nombre, contenido)
    grupos: dict[str, dict] = {}
    errores = []
    for f in filas:
        sku_pp = (f.get("sku_pack") or f.get("sku_prepack") or "").strip().upper()
        codigo = (f.get("pack") or f.get("prepack_id") or "").strip().upper()
        sku = (f.get("sku") or "").strip()
        if not sku_pp or not codigo or not sku:
            errores.append({"fila": f["_fila"], "mensaje": "Missing pack item code, pack ID or item code."})
            continue
        a = db.scalar(select(Articulo).where(Articulo.sku == sku))
        if not a:
            errores.append({"fila": f["_fila"], "mensaje": f"Item code {sku} does not exist in the item master."})
            continue
        g = grupos.setdefault(sku_pp, {"codigo": codigo, "tipo": (f.get("tipo") or "PACK").strip().upper(),
                                       "descripcion": f.get("descripcion") or None, "items": []})
        g["items"].append({"articulo_id": a.id, "cantidad": f.get("cantidad") or 0})
    creados = sin_cambio = 0
    for sku_pp, g in grupos.items():
        existente = db.scalar(select(Articulo).where(Articulo.sku == sku_pp))
        if existente:
            actual = {x.componente_id: x.cantidad for x in existente.componentes}
            nueva = {it["articulo_id"]: int(it["cantidad"] or 0) for it in g["items"]}
            if actual == nueva:
                sin_cambio += 1
            else:
                errores.append({"fila": sku_pp, "mensaje": "The pack already exists with other contents; "
                                                           "the contents cannot change. Use a new code."})
            continue
        try:
            with db.begin_nested():
                crear_compuesto(db, user, {"sku": sku_pp, **g, "componentes": g["items"]})
            creados += 1
        except ErrorNegocio as e:
            errores.append({"fila": sku_pp, "mensaje": "; ".join(d["mensaje"] for d in e.detalle or []) or e.mensaje})
    return {"creados": creados, "actualizados": 0, "sin_cambio": sin_cambio, "errores": errores[:200]}
