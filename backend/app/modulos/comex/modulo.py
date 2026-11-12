"""Contrato del módulo de comercio exterior: la ficha aduanera del producto y
lo que cada familia guarda para clasificarse. No tiene rutas propias: sus
pantallas usan las de productos y clasificación."""
from app.core.modulos import Modulo
from app.modulos.catalogo.secciones import registrar_seccion_familia
from app.modulos.comex import familia


def _al_cargar() -> None:
    registrar_seccion_familia(familia.SECCION)


MODULO = Modulo(
    clave="comex", nombre="Comercio exterior",
    descripcion="Ficha aduanera del producto y categoría aduanera de cada familia.",
    al_cargar=_al_cargar,
)
