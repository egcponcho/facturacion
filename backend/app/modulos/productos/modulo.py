"""Contrato del módulo de productos: fichas, su flujo de revisión y aprobación."""
from app.core.modulos import Modulo
from app.modelos import PartidaPais, Producto, ProductoDocumento, ProductoFoto
from app.modulos.comun import edicion
from app.modulos.productos import api, api_flujo
from app.modulos.productos.productos import ver_producto


def _al_cargar() -> None:
    # La ficha del producto se edita en exclusiva (comun/edicion.py): el producto y sus partes
    edicion.registrar_documento(
        "producto", Producto,
        {Producto: lambda db, o: o.id, PartidaPais: lambda db, o: o.producto_id, ProductoFoto: lambda db, o: o.producto_id,
         ProductoDocumento: lambda db, o: o.producto_id},
        ver_producto)


MODULO = Modulo(
    clave="productos", nombre="Productos",
    descripcion="Fichas técnicas de producto, su flujo de revisión y aprobación y sus partidas por país.",
    rutas=lambda: [api_flujo.router, api.router],
    al_cargar=_al_cargar,
)
