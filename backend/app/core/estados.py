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

# Recepción de cada unidad de carga (contenedor, guía, camión) en bodega: se
# cuenta en una o varias partes; queda recibida al completar lo enviado, al
# confirmar lo pendiente sin conteo o al cerrarla con faltantes. Después solo
# se corrige con ajustes (con motivo).
RECEPCION = Maquina(
    "the load unit receipt",
    {"PENDIENTE": "pending", "EN_RECEPCION": "being received", "RECIBIDA": "received"},
    {
        "contar": (("PENDIENTE", "EN_RECEPCION"), "EN_RECEPCION"),
        "ajustar": (("EN_RECEPCION", "RECIBIDA"), None),
        "sin_conteo": (("PENDIENTE", "EN_RECEPCION"), "RECIBIDA"),
        "cerrar": (("EN_RECEPCION",), "RECIBIDA"),
    },
)


# ---- Estados que la empresa puede personalizar --------------------------------------------
# Los códigos son fijos (el sistema decide con ellos); la empresa elige cómo se
# leen (etiqueta), su color y el orden en filtros y listas (tabla
# estados_documento). Documento → (nombre, códigos en su orden de fábrica).
TONOS = ("neutro", "info", "ok", "aviso", "error")
PERSONALIZABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "oc": ("Purchase orders", tuple(OC.estados)),
    "avance": ("Purchase order progress", ("SIN_FACTURAR", "FACTURADA_PARCIAL", "FACTURADA", "EMBARCADA_PARCIAL",
                                           "EN_TRANSITO", "RECIBIDA_PARCIAL", "RECIBIDA")),
    "factura": ("Invoices", tuple(FACTURA.estados)),
    "pl": ("Packing lists", tuple(PL.estados)),
    "embarque": ("Shipments", tuple(EMBARQUE.estados)),
    "recepcion": ("Load unit receipt", tuple(RECEPCION.estados)),
    "producto": ("Products", ("borrador", "sugerida", "revision", "observado", "aprobado", "corregido")),
}


def personalizados(db) -> dict:
    """{documento: {código: {etiqueta, tono, orden}}} de la organización de la sesión."""
    from sqlalchemy import select

    from app.modelos import EstadoDocumento

    res: dict[str, dict] = {}
    for e in db.scalars(select(EstadoDocumento)):
        res.setdefault(e.documento, {})[e.codigo] = {"etiqueta": e.etiqueta, "tono": e.tono, "orden": e.orden}
    return res


def guardar_personalizados(db, datos) -> None:
    """Reemplaza la personalización de los documentos indicados:
    {documento: [{codigo, etiqueta?, tono?}] en el orden deseado}. Un estado
    sin etiqueta ni tono propio y en su lugar de fábrica no guarda fila."""
    from sqlalchemy import delete

    from app.modelos import EstadoDocumento

    if not isinstance(datos, dict) or set(datos) - set(PERSONALIZABLES):
        raise ErrorNegocio("Statuses go by document.", 422, "validacion")
    for documento, filas in datos.items():
        codigos = PERSONALIZABLES[documento][1]
        if not isinstance(filas, list) or any(not isinstance(f, dict) for f in filas):
            raise ErrorNegocio("Send the statuses of each document in a list.", 422, "validacion")
        vistos = [f.get("codigo") for f in filas]
        if set(vistos) - set(codigos) or len(vistos) != len(set(vistos)):
            raise ErrorNegocio(f"The statuses of {documento} are fixed: {', '.join(codigos)}.", 422, "validacion")
        # Los que no vinieron conservan su lugar después de los enviados
        orden = vistos + [c for c in codigos if c not in vistos]
        por_codigo = {f["codigo"]: f for f in filas}
        db.execute(delete(EstadoDocumento).where(EstadoDocumento.documento == documento))
        for i, codigo in enumerate(orden, start=1):
            f = por_codigo.get(codigo, {})
            etiqueta = str(f.get("etiqueta") or "").strip()[:60] or None
            tono = f.get("tono") or None
            if tono is not None and tono not in TONOS:
                raise ErrorNegocio(f"The color must be one of {', '.join(TONOS)}.", 422, "validacion")
            propio_orden = orden != list(codigos)
            if etiqueta or tono or propio_orden:
                db.add(EstadoDocumento(documento=documento, codigo=codigo, etiqueta=etiqueta, tono=tono,
                                       orden=i if propio_orden else None))
    db.flush()
