"""Límite de peticiones por IP para los pasos del inicio de sesión (en
memoria: frena ataques de fuerza bruta desde una misma dirección)."""
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.errores import ErrorNegocio

VENTANA_SEG = 300
MAXIMO = {"login": 20, "verificar": 20, "reenviar": 10}
_registro: dict[tuple[str, str], deque] = defaultdict(deque)


MAX_DIRECCIONES = 10_000


def _purgar(ahora: float) -> None:
    """Olvida las direcciones sin intentos recientes (la tabla no crece sin límite)."""
    for clave in [k for k, m in _registro.items() if not m or ahora - m[-1] > VENTANA_SEG]:
        del _registro[clave]


def limitar(request: Request, accion: str) -> None:
    ip = request.client.host if request.client else "?"
    ahora = time.monotonic()
    if len(_registro) > MAX_DIRECCIONES:
        _purgar(ahora)
    marcas = _registro[(accion, ip)]
    while marcas and ahora - marcas[0] > VENTANA_SEG:
        marcas.popleft()
    if len(marcas) >= MAXIMO[accion]:
        raise ErrorNegocio("Too many attempts from this network. Wait a few minutes.", 429, "limite")
    marcas.append(ahora)


def reiniciar() -> None:
    _registro.clear()
