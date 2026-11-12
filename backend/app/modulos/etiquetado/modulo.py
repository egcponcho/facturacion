"""Contrato del módulo de etiquetado (la empresa lo apaga en Configuración →
Empresa → Módulos)."""
import asyncio
import logging

from app.core.config import settings
from app.core.modulos import Modulo
from app.modulos.catalogo.secciones import registrar_seccion_familia
from app.modulos.etiquetado import api, familia
from app.modulos.etiquetado.trabajos import recuperar


async def _recuperar_trabajos() -> None:
    """Retoma los trabajos de etiquetado que quedaron a medias (el proceso que
    los generaba se detuvo): al arrancar y luego cada ETIQUETAS_RECUPERAR_SEG
    segundos. Con 0 no corre (las pruebas la llaman directamente)."""
    while settings.ETIQUETAS_RECUPERAR_SEG > 0:
        try:
            await asyncio.to_thread(recuperar)
        except Exception:  # la recuperación nunca debe tumbar el servidor
            logging.getLogger("etiquetado").exception("Falló la recuperación de trabajos de etiquetado")
        await asyncio.sleep(settings.ETIQUETAS_RECUPERAR_SEG)


def _al_cargar() -> None:
    registrar_seccion_familia(familia.SECCION)


MODULO = Modulo(
    clave="etiquetado", nombre="Etiquetado",
    descripcion="Tipos de etiqueta, familias, diseños con versiones y aprobación, qué diseño lleva cada cosa, trabajos "
                "desde OC, artículos y listas de empaque, descargas e historial.",
    rutas=lambda: [api.router],
    al_cargar=_al_cargar,
    tareas=(_recuperar_trabajos,),
)
