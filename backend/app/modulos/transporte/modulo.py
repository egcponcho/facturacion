"""Contrato del módulo de transporte: embarques, unidades de carga y costos logísticos."""
from app.core.modulos import Modulo
from app.modelos import Embarque, EventoEmbarque, UnidadCarga
from app.modulos.catalogo.secciones import registrar_seccion_familia
from app.modulos.comun import edicion
from app.modulos.transporte import api, api_leadtimes, familia
from app.modulos.transporte.transporte import cargar_embarque


def _al_cargar() -> None:
    registrar_seccion_familia(familia.SECCION)
    # El embarque se edita en exclusiva (comun/edicion.py): el embarque, sus unidades y sus hitos
    edicion.registrar_documento(
        "embarque", Embarque,
        {Embarque: lambda db, o: o.id, UnidadCarga: lambda db, o: o.embarque_id, EventoEmbarque: lambda db, o: o.embarque_id},
        lambda db, user, embarque_id: cargar_embarque(db, user, embarque_id))


MODULO = Modulo(
    clave="transporte", nombre="Transporte",
    descripcion="Embarques, unidades de carga, hitos, recolección, costos logísticos y lead times.",
    rutas=lambda: [api.router, api_leadtimes.router],
    al_cargar=_al_cargar,
)
