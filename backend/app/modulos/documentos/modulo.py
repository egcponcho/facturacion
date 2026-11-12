"""Contrato del módulo de documentos: PDF y Excel de los documentos
(factura, lista de empaque…), sus plantillas e idioma. No tiene rutas
propias: cada módulo descarga sus documentos desde sus rutas."""
from app.core.modulos import Modulo

MODULO = Modulo(
    clave="documentos", nombre="Documentos",
    descripcion="Generación de PDF y Excel de los documentos, sus plantillas e idioma.",
)
