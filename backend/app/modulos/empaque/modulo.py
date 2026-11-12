"""Contrato del módulo de empaque: listas de empaque, cajas y plantillas."""
from app.core.modulos import Modulo
from app.modelos import GrupoCajas, GrupoCajasItem, PackingList, PLLinea
from app.modulos.catalogo.secciones import registrar_seccion_familia
from app.modulos.comun import edicion
from app.modulos.empaque import api, api_plantillas, api_recetas, familia
from app.modulos.empaque.packing import cargar_pl


def _al_cargar() -> None:
    registrar_seccion_familia(familia.SECCION)
    # La lista de empaque se edita en exclusiva (comun/edicion.py): la lista, sus líneas y sus cajas
    edicion.registrar_documento(
        "packing_list", PackingList,
        {PackingList: lambda db, o: o.id, PLLinea: lambda db, o: o.pl_id, GrupoCajas: lambda db, o: o.pl_id,
         GrupoCajasItem: lambda db, o: (db.get(GrupoCajas, o.grupo_id) or GrupoCajas()).pl_id},
        lambda db, user, pl_id: cargar_pl(db, user, pl_id))


MODULO = Modulo(
    clave="empaque", nombre="Listas de empaque",
    descripcion="Listas de empaque con su estructura de cajas, inner packs y prepacks, y plantillas de caja.",
    rutas=lambda: [api.router, api_plantillas.router, api_recetas.router],
    al_cargar=_al_cargar,
)
