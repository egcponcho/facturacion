from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Historial, Idempotencia, Usuario, ahora

EDITABLE_FACTURA = ("BORRADOR", "EN_CORRECCION")
EDITABLE_PL = ("BORRADOR", "EN_CORRECCION")

ESTADO_TXT = {
    "BORRADOR": "in draft",
    "EN_CORRECCION": "under correction",
    "FINALIZADA": "finalized",
    "FINALIZADO": "finalized",
    "CANCELADA": "cancelled",
    "CANCELADO": "cancelled",
}


class ErrorNegocio(Exception):
    """Error con mensaje para el usuario y, opcionalmente, un detalle
    estructurado (lista de problemas, impacto de una acción, etc.)."""

    def __init__(self, mensaje: str, status: int = 400, codigo: str = "error", detalle=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status
        self.codigo = codigo
        self.detalle = detalle


# ---- Permisos ---------------------------------------------------------------
TODOS = {"admin", "interno", "proveedor"}
INTERNOS = {"admin", "interno"}


def _matriz() -> dict[str, set[str]]:
    finalizan = INTERNOS | ({"proveedor"} if settings.PROVEEDOR_PUEDE_FINALIZAR else set())
    return {
        "oc.ver": TODOS,
        "oc.importar": INTERNOS,
        "oc.empaque": INTERNOS,
        "factura.editar": TODOS,
        "factura.finalizar": finalizan,
        "factura.reabrir": INTERNOS,
        "factura.cancelar": TODOS,  # el proveedor solo en borrador
        "pl.editar": TODOS,
        "pl.finalizar": finalizan,
        "pl.reabrir": INTERNOS,
        "pl.cancelar": TODOS,
        "plantilla.editar": TODOS,
        "transporte.gestionar": INTERNOS,
        "recepcion.registrar": INTERNOS,
        "alertas.ver": INTERNOS,
        "catalogos.ver": INTERNOS,
        # Productos: el proveedor completa la ficha técnica de lo suyo; el equipo
        # interno clasifica, aprueba, devuelve y enseña códigos nacionales
        "producto.ver": TODOS,
        "producto.ficha": TODOS,
        "producto.crear": INTERNOS,
        "producto.clasificar": INTERNOS,
        "catalogos.editar": INTERNOS,
        "admin": {"admin"},
    }


def permisos_de(user: Usuario) -> list[str]:
    return sorted(p for p, roles in _matriz().items() if user.rol in roles)


def exigir(user: Usuario, permiso: str) -> None:
    if user.rol not in _matriz().get(permiso, set()):
        raise ErrorNegocio("You do not have permission for this action.", 403, "sin_permiso")


def es_interno(user: Usuario) -> bool:
    return user.rol in INTERNOS


# ---- Separación por proveedor -----------------------------------------------
def proveedor_filtro(user: Usuario, proveedor_id: int | None = None) -> int | None:
    """El proveedor siempre queda limitado a sus datos; el interno puede
    elegir uno o ver todos (None)."""
    if user.rol == "proveedor":
        return user.proveedor_id
    return proveedor_id


def asegurar_proveedor(user: Usuario, proveedor_id: int) -> None:
    if user.rol == "proveedor" and user.proveedor_id != proveedor_id:
        # 404 para no revelar que el documento existe
        raise ErrorNegocio("Document not found.", 404, "no_encontrado")


# ---- Versiones (control optimista) ------------------------------------------
def verificar_version(doc, version: int | None, nombre: str = "document") -> None:
    if version is not None and doc.version != version:
        raise ErrorNegocio(
            f"Another user changed this {nombre} while you had it open. "
            "Reload to see the current version; your changes were not applied.",
            409,
            "conflicto_version",
            {"version_actual": doc.version},
        )


def tocar(doc) -> None:
    doc.version = (doc.version or 0) + 1
    doc.actualizado_en = ahora()


# ---- Historial --------------------------------------------------------------
def registrar(
    db: Session,
    user: Usuario | None,
    entidad: str,
    entidad_id: int,
    accion: str,
    detalle=None,
    motivo: str | None = None,
    factura_id: int | None = None,
) -> None:
    db.add(
        Historial(
            entidad=entidad,
            entidad_id=entidad_id,
            accion=accion,
            detalle=jsonable_encoder(detalle) if detalle is not None else None,
            motivo=motivo,
            factura_id=factura_id,
            usuario_id=user.id if user else None,
        )
    )


# ---- Idempotencia -----------------------------------------------------------
def idempotente(db: Session, user: Usuario, clave: str | None, fn):
    """Si la misma operación llega dos veces (doble clic, reintento de red),
    devuelve el resultado de la primera en lugar de repetirla."""
    if not clave:
        return fn()
    k = f"{user.id}:{clave}"[:160]
    previo = db.get(Idempotencia, k)
    if previo:
        return previo.respuesta
    resultado = jsonable_encoder(fn())
    db.add(Idempotencia(clave=k, usuario_id=user.id, respuesta=resultado))
    return resultado


# ---- Textos -----------------------------------------------------------------
def unidad_txt(unidad: str, cantidad: int | None = None) -> str:
    if unidad == "PAR":
        return "pair" if cantidad == 1 else "pairs"
    return "unit" if cantidad == 1 else "units"


def cant_txt(cantidad: int, unidad: str) -> str:
    return f"{cantidad:,} {unidad_txt(unidad, cantidad)}"


def requerir_motivo(motivo: str | None, accion: str) -> str:
    if not motivo or not motivo.strip():
        raise ErrorNegocio(f"Enter the reason to {accion}.", 422, "motivo_requerido")
    return motivo.strip()
