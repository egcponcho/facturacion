"""Historial de cambios, control de versiones (concurrencia optimista),
idempotencia de las peticiones y motivo obligatorio de los cambios.
"""
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Historial, Idempotencia, Usuario, ahora


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


def requerir_motivo(motivo: str | None, accion: str) -> str:
    if not motivo or not motivo.strip():
        raise ErrorNegocio(f"Enter the reason to {accion}.", 422, "motivo_requerido")
    return motivo.strip()
