from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import Usuario
from .security import leer_token
from .services.common import ErrorNegocio

_bearer = HTTPBearer(auto_error=False)


def usuario_actual(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    if not cred:
        raise ErrorNegocio("Inicia sesión para continuar.", 401, "no_autenticado")
    uid = leer_token(cred.credentials)
    user = db.get(Usuario, uid) if uid else None
    if not user or not user.activo:
        raise ErrorNegocio("Tu sesión expiró. Inicia sesión de nuevo.", 401, "no_autenticado")
    return user
