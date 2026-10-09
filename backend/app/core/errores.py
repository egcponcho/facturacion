"""Error de negocio: un mensaje para el usuario con su código HTTP y, si hace
falta, un detalle estructurado. main.py lo convierte en la respuesta de la API.
"""


class ErrorNegocio(Exception):
    """Error con mensaje para el usuario y, opcionalmente, un detalle
    estructurado (lista de problemas, impacto de una acción, etc.)."""

    def __init__(self, mensaje: str, status: int = 400, codigo: str = "error", detalle=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.codigo = codigo
        self.detalle = detalle
