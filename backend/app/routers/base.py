from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import usuario_actual
from ..models import Usuario
from ..services.common import idempotente

Db = Annotated[Session, Depends(get_db)]
User = Annotated[Usuario, Depends(usuario_actual)]
Clave = Annotated[str | None, Header(alias="Idempotency-Key")]

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def ejecutar(db: Session, user: Usuario, clave: str | None, fn):
    """Ejecuta una operación en una sola transacción (todo o nada) y la
    protege contra duplicados con la clave de idempotencia."""
    resultado = idempotente(db, user, clave, fn)
    db.commit()
    return resultado
