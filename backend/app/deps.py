from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import Usuario
from .services import preferencias
from .services.acceso import usuario_de_sesion
from .services.common import ErrorNegocio

COOKIE = "sesion"
_bearer = HTTPBearer(auto_error=False)
SEGUROS = {"GET", "HEAD", "OPTIONS"}


def token_de(request: Request, cred: HTTPAuthorizationCredentials | None) -> tuple[str | None, bool]:
    """Token de la sesión y si vino en la cookie del navegador."""
    if cred:
        return cred.credentials, False
    return request.cookies.get(COOKIE), True


def usuario_actual(
    request: Request,
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    token, de_cookie = token_de(request, cred)
    if not token:
        raise ErrorNegocio("Sign in to continue.", 401, "no_autenticado")
    # Con cookie, una petición que cambia datos debe traer el encabezado propio
    # de la aplicación: otro sitio no puede enviarlo (protección CSRF).
    if de_cookie and request.method not in SEGUROS and request.headers.get("X-Requested-With") != "fetch":
        raise ErrorNegocio("Request not allowed.", 403, "csrf")
    user = usuario_de_sesion(db, token)
    if not user:
        raise ErrorNegocio("Your session expired. Sign in again.", 401, "no_autenticado")
    request.state.token = token
    return user


async def usuario_con_preferencias(user: Usuario = Depends(usuario_actual)) -> Usuario:
    """El usuario de la sesión, dejando sus preferencias (formato de fecha,
    etc.) en el contexto de la petición. Es asíncrona a propósito: así el valor
    se fija en el contexto de la petición y lo ven las rutas que corren en hilos."""
    preferencias.usar(user)
    return user
