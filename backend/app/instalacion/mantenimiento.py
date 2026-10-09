"""Limpieza periódica de tablas técnicas que crecen con el uso.

Corre al arrancar y luego cada hora (`main.lifespan`). Solo borra datos que ya
no sirven: nada de negocio ni de la bitácora.

- Claves de idempotencia de más de un día (un reintento llega en segundos).
- Sesiones vencidas o revocadas hace más de 30 días.
- Desafíos de dos pasos vencidos hace más de un día.
- Permisos de edición vencidos.
"""
import logging
from datetime import timedelta

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.modelos import DesafioDosPasos, Edicion, Idempotencia, SesionUsuario
from app.modelos.base import ahora

log = logging.getLogger("mantenimiento")

INTERVALO_SEG = 3600


def purgar(db: Session) -> dict[str, int]:
    hoy = ahora()
    borrados = {
        "idempotencia": db.execute(delete(Idempotencia).where(Idempotencia.creada_en < hoy - timedelta(days=1))).rowcount,
        "sesiones": db.execute(delete(SesionUsuario).where(
            or_(SesionUsuario.expira < hoy - timedelta(days=30),
                SesionUsuario.revocada.is_(True) & (SesionUsuario.ultima_actividad < hoy - timedelta(days=30))))).rowcount,
        "desafios": db.execute(delete(DesafioDosPasos).where(DesafioDosPasos.expira < hoy - timedelta(days=1))).rowcount,
        "ediciones": db.execute(delete(Edicion).where(Edicion.vence < hoy)).rowcount,
    }
    db.commit()
    if any(borrados.values()):
        log.info("Limpieza: %s", borrados)
    return borrados
