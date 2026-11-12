"""Contrato del módulo de acceso: ingreso, sesión, usuarios, roles y permisos."""
from app.core import cambios, respuestas
from app.core.modulos import Modulo
from app.modulos.acceso import api, visibilidad
from app.modulos.acceso.autenticacion import usuario_de_sesion


def _al_cargar() -> None:
    # El canal de cambios (core/cambios.py) reconoce al usuario de cada petición con la sesión de este módulo
    cambios.registrar_identificador(usuario_de_sesion)
    # Cada respuesta de la API sale sin los datos que el rol del usuario no ve
    respuestas.registrar_filtro(visibilidad.quitar)


MODULO = Modulo(
    clave="acceso", nombre="Acceso",
    descripcion="Ingreso en dos pasos, sesión, perfil y preferencias, usuarios, roles y permisos.",
    rutas=lambda: [api.router],
    al_cargar=_al_cargar,
)
