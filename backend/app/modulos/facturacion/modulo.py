"""Contrato del módulo de facturación: facturas comerciales armadas desde las OCs."""
from app.core.modulos import Modulo
from app.modelos import Archivo, Factura, FacturaLinea
from app.modulos.comun import edicion
from app.modulos.facturacion import api
from app.modulos.facturacion.facturas import cargar_factura


def _al_cargar() -> None:
    # La factura se edita en exclusiva (comun/edicion.py): la factura, sus líneas y sus archivos
    edicion.registrar_documento(
        "factura", Factura,
        {Factura: lambda db, o: o.id, FacturaLinea: lambda db, o: o.factura_id, Archivo: lambda db, o: o.factura_id},
        lambda db, user, factura_id: cargar_factura(db, user, factura_id))


MODULO = Modulo(
    clave="facturacion", nombre="Facturas",
    descripcion="Facturas comerciales armadas desde las líneas de las OCs, su revisión y sus documentos.",
    rutas=lambda: [api.router],
    al_cargar=_al_cargar,
)
