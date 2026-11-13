"""Contrato del módulo de compras: órdenes de compra y su flujo."""
from app.core.errores import ErrorNegocio
from app.core.modulos import Modulo
from app.modelos import OrdenCompra, PosicionOC
from app.modulos.acceso.permisos import asegurar_proveedor
from app.modulos.compras import api, api_flujo, api_solicitudes
from app.modulos.comun import edicion


def _ver_orden(db, user, oc_id: int) -> None:
    """Solo pide editar una OC quien la ve (un proveedor, solo las suyas)."""
    oc = db.get(OrdenCompra, oc_id)
    if not oc:
        raise ErrorNegocio("The purchase order does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, oc.proveedor_id, oc.sociedad)


def _al_cargar() -> None:
    # La OC se edita en exclusiva (comun/edicion.py): la orden y sus posiciones
    edicion.registrar_documento("orden", OrdenCompra, {OrdenCompra: lambda db, o: o.id, PosicionOC: lambda db, o: o.oc_id},
                                _ver_orden)


MODULO = Modulo(
    clave="compras", nombre="Órdenes de compra",
    descripcion="Órdenes de compra: importación, asistente, aprobación, liberaciones y líneas disponibles para facturar.",
    rutas=lambda: [api.router, api_flujo.router, api_solicitudes.router],
    al_cargar=_al_cargar,
)
