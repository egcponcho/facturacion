"""Respuesta JSON de la API, con los filtros que los módulos inscriben.

Un filtro recibe el contenido de la respuesta y devuelve lo que se envía. El
módulo de acceso inscribe el suyo (acceso/modulo.py): quita los datos que el
rol del usuario no ve (acceso/visibilidad.py). `core` no sabe de roles.
"""
from collections.abc import Callable

from fastapi.responses import JSONResponse

_FILTROS: list[Callable] = []


def registrar_filtro(filtro: Callable) -> None:
    if filtro not in _FILTROS:
        _FILTROS.append(filtro)


class RespuestaJSON(JSONResponse):
    def render(self, content) -> bytes:
        for filtro in _FILTROS:
            content = filtro(content)
        return super().render(content)
