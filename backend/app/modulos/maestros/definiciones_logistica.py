"""Catálogos de datos maestros de la logística: puertos, transportistas, tipos de
unidad de carga, liberaciones y lead times (regiones, pasos y reglas). Se unen al
resto en definiciones.CATALOGOS.
"""
from app.modelos import (
    EstadoLiberacion,
    PasoLeadTime,
    Puerto,
    RegionLeadTime,
    ReglaLeadTime,
    TipoUnidad,
    Transportista,
)
from app.modulos.maestros.campos_catalogo import c
from app.modulos.transporte import reglas_lt as rlt

LOGISTICA = {
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
}
