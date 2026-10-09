from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.empresa import usar_configuracion
from app.core.errores import ErrorNegocio
from app.core.listas import usar_listas
from app.modelos import Usuario
from app.modulos.acceso import preferencias, visibilidad
from app.modulos.acceso.autenticacion import usuario_de_sesion
from app.modulos.comun import edicion
from app.modulos.documentos import idioma_doc

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
    # Configuración de la empresa (reglas de negocio) para esta petición
    from app.modulos.empresa.organizacion import configuracion

    request.state.config_empresa = configuracion(db)
    # Listas de valores de la empresa (unidades, monedas, modos de transporte…)
    from app.modulos.maestros.listas import cargar as cargar_listas

    request.state.listas = cargar_listas(db)
    return user


# Con contraseña temporal solo se puede completar el asistente inicial
PERMITIDO_TEMPORAL = ("/api/auth/", "/api/perfil")


async def usuario_con_preferencias(request: Request, user: Usuario = Depends(usuario_actual)) -> Usuario:
    """El usuario de la sesión, dejando sus preferencias (formato de fecha,
    etc.) en el contexto de la petición. Es asíncrona a propósito: así el valor
    se fija en el contexto de la petición y lo ven las rutas que corren en hilos."""
    usar_configuracion(request.state.config_empresa)  # antes de las preferencias: dan el idioma por defecto
    usar_listas(request.state.listas)
    preferencias.usar(user)
    # Idioma de los documentos que se descargan: ?idioma= o el del perfil (o el de la pantalla)
    pref = preferencias.actual()
    idioma_doc.usar(request.query_params.get("idioma") or pref.get("idioma_documentos") or pref.get("idioma"))
    edicion.usar_usuario(user.id)
    # Datos que su rol no ve: en las pantallas de trabajo y en la configuración que solo consulta
    visibilidad.usar(user if visibilidad.aplica(request.url.path, user) else None)
    if user.clave_temporal and not request.url.path.startswith(PERMITIDO_TEMPORAL):
        raise ErrorNegocio("Change your temporary password to continue.", 403, "clave_temporal")
    return user
