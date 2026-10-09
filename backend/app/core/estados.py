"""Máquinas de estados de los documentos.

Cada documento declara sus estados y, por acción, desde qué estados se
permite y a cuál lleva. Los servicios preguntan aquí antes de cambiar algo
(`exigir`) y la pantalla recibe las acciones posibles (`acciones`), así el
flujo se lee en un solo lugar en vez de repartido en condiciones sueltas.
Las reglas de negocio de cada acción (motivos, cantidades, permisos) siguen en
su servicio. Ver docs/FLUJOS.md.
"""
from dataclasses import dataclass, field

from app.core.errores import ErrorNegocio


@dataclass(frozen=True)
class Maquina:
    documento: str  # con su artículo, para los mensajes ("the purchase order"…)
    estados: dict[str, str]  # código → texto (sin repetir palabras entre documentos de distinto género)
    acciones: dict[str, tuple[tuple[str, ...], str | None]] = field(default_factory=dict)  # acción → (desde, hacia)

    def texto(self, estado: str) -> str:
        return self.estados.get(estado, estado)

    def puede(self, accion: str, estado: str) -> bool:
        desde, _ = self.acciones[accion]
        return estado in desde

    def exigir(self, accion: str, estado: str, codigo: str = "transicion_invalida") -> None:
        if not self.puede(accion, estado):
            raise ErrorNegocio(f"This action is not possible: {self.documento} is {self.texto(estado)}.",
                               409, codigo, {"estado": estado, "accion": accion})

    def destino(self, accion: str) -> str | None:
        return self.acciones[accion][1]

    def disponibles(self, estado: str) -> list[str]:
        return [a for a, (desde, _) in self.acciones.items() if estado in desde]


# ---- Orden de compra -----------------------------------------------------------
OC = Maquina(
    "the purchase order",
    {"BORRADOR": "in draft", "EN_APROBACION": "pending approval", "RECHAZADA": "rejected", "APROBADA": "approved",
     "CERRADA": "closed", "CANCELADA": "cancelled"},
    {
        "editar": (("BORRADOR", "RECHAZADA"), "BORRADOR"),
        "enviar": (("BORRADOR", "RECHAZADA"), None),  # a EN_APROBACION o APROBADA según las reglas de aprobación
        "aprobar": (("EN_APROBACION",), None),  # a APROBADA cuando se aprueba el último paso
        "rechazar": (("EN_APROBACION",), "RECHAZADA"),
        "cancelar": (("BORRADOR", "EN_APROBACION", "RECHAZADA", "APROBADA"), "CANCELADA"),
        "cerrar": (("APROBADA",), "CERRADA"),
        "reabrir": (("CERRADA",), "APROBADA"),
        "eliminar": (("BORRADOR",), None),
        "facturar": (("APROBADA",), None),
        "importar": (("APROBADA",), None),  # una carga del ERP solo actualiza OCs aprobadas
    },
)

# ---- Factura y lista de empaque ---------------------------------------------------
FACTURA = Maquina(
    "the invoice",
    {"BORRADOR": "in draft", "EN_CORRECCION": "under correction", "FINALIZADA": "finalized", "CANCELADA": "cancelled"},
    {
        "editar": (("BORRADOR", "EN_CORRECCION"), None),
        "finalizar": (("BORRADOR", "EN_CORRECCION"), "FINALIZADA"),
        "reabrir": (("FINALIZADA",), "EN_CORRECCION"),
        "cancelar": (("BORRADOR", "EN_CORRECCION", "FINALIZADA"), "CANCELADA"),
    },
)
PL = Maquina(
    "the packing list",
    {"BORRADOR": "in draft", "EN_CORRECCION": "under correction", "FINALIZADO": "finalized", "CANCELADO": "cancelled"},
    {
        "editar": (("BORRADOR", "EN_CORRECCION"), None),
        "finalizar": (("BORRADOR", "EN_CORRECCION"), "FINALIZADO"),
        "reabrir": (("FINALIZADO",), "EN_CORRECCION"),
        "cancelar": (("BORRADOR", "EN_CORRECCION", "FINALIZADO"), "CANCELADO"),
        "recibir": (("FINALIZADO",), None),
    },
)

# ---- Embarque ------------------------------------------------------------------------
# Los hitos (salida, arribo, entrega, recepción…) mueven el embarque entre sus
# estados; qué hito se permite en cada estado lo configura la empresa en la
# lista «Eventos del embarque».
EMBARQUE = Maquina(
    "the shipment",
    {"PLANIFICADO": "planned", "EN_TRANSITO": "in transit", "ARRIBADO": "at destination", "ENTREGADO": "delivered to the plant",
     "RECIBIDO": "received at the warehouse", "CANCELADO": "called off"},
    {
        "editar": (("PLANIFICADO",), None),
        "cancelar": (("PLANIFICADO",), "CANCELADO"),
        "recibir": (("ARRIBADO", "ENTREGADO", "RECIBIDO"), None),
    },
)
