import re

from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, func, or_
from sqlalchemy.sql import operators
from sqlalchemy.orm import Session

from ..config import settings
from ..db import ES_SQLITE, plano
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

# Catálogo de permisos por módulo: (clave, etiqueta, roles de fábrica que lo
# tienen, si un rol de proveedor puede tenerlo). Los roles se arman en Users
# and access marcando estos permisos; el proveedor sigue viendo solo lo suyo.
MODULOS = [
    ("Orders", [
        ("oc.ver", "See purchase orders", TODOS, True),
        ("oc.importar", "Import POs from the ERP", INTERNOS, False),
        ("oc.empaque", "Edit casepack and inner pack of a PO line", INTERNOS, False),
    ]),
    ("Invoices", [
        ("factura.editar", "Create and edit invoices", TODOS, True),
        ("factura.finalizar", "Finalize invoices", "finalizan", True),
        ("factura.reabrir", "Reopen finalized invoices", INTERNOS, False),
        ("factura.cancelar", "Cancel invoices", TODOS, True),
    ]),
    ("Packing lists", [
        ("pl.editar", "Create and edit packing lists", TODOS, True),
        ("pl.finalizar", "Finalize packing lists", "finalizan", True),
        ("pl.reabrir", "Reopen finalized packing lists", INTERNOS, False),
        ("pl.cancelar", "Cancel packing lists", TODOS, True),
        ("plantilla.editar", "Create and edit packing templates", TODOS, True),
    ]),
    ("Shipments", [
        ("transporte.gestionar", "See and manage shipments and load units", INTERNOS, False),
        ("recepcion.registrar", "Register warehouse receipts", INTERNOS, False),
    ]),
    ("Products", [
        ("producto.ver", "See products and technical sheets", TODOS, True),
        ("producto.ficha", "Edit technical sheets and send them to review", TODOS, True),
        ("producto.crear", "Create products", INTERNOS, False),
        ("producto.clasificar", "Classify, approve and return sheets", INTERNOS, False),
    ]),
    ("Tariff schedule", [
        ("aranceles.ver", "See the tariff schedule", INTERNOS, False),
        ("aranceles.editar", "Edit countries, SAC, notes and national codes", INTERNOS, False),
    ]),
    ("Master data", [
        ("catalogos.ver", "See master data", INTERNOS, False),
        ("catalogos.crear", "Create and upload master data", INTERNOS, False),
        ("catalogos.editar", "Edit master data", INTERNOS, False),
        ("catalogos.eliminar", "Delete master data", INTERNOS, False),
    ]),
    ("Tracking", [
        ("seguimiento.ver", "See tracking and lead times", INTERNOS, True),
        ("alertas.ver", "See and resolve alerts", INTERNOS, False),
    ]),
    ("Administration", [
        ("admin", "Users, roles and suppliers", {"admin"}, False),
    ]),
]
PERMISOS = {k: (et, roles, prov) for _, ps in MODULOS for k, et, roles, prov in ps}


def _matriz() -> dict[str, set[str]]:
    finalizan = INTERNOS | ({"proveedor"} if settings.PROVEEDOR_PUEDE_FINALIZAR else set())
    return {k: finalizan if roles == "finalizan" else roles for k, (_, roles, _) in PERMISOS.items()}


def permisos_fabrica(tipo: str) -> list[str]:
    return sorted(p for p, roles in _matriz().items() if tipo in roles)


def alcance(permisos, proveedor_id: int | None) -> str:
    """Qué datos ve el usuario. No lo define el rol sino el usuario: con un
    proveedor asignado solo ve lo de ese proveedor; sin proveedor es del equipo
    interno, y administra si su rol tiene el permiso de administración."""
    if proveedor_id:
        return "proveedor"
    return "admin" if "admin" in (permisos or []) else "interno"


def permisos_validos(permisos, proveedor_id: int | None = None) -> list[str]:
    """Permisos que aplican: un usuario de proveedor no recibe permisos de
    datos globales ni de administración aunque su rol los tenga."""
    return sorted({p for p in permisos or [] if p in PERMISOS and (not proveedor_id or (PERMISOS[p][2] and p != "admin"))})


def catalogo_permisos() -> list[dict]:
    return [{"modulo": m, "permisos": [{"clave": k, "etiqueta": et, "proveedor": prov} for k, et, _, prov in ps]}
            for m, ps in MODULOS]


def permisos_de(user: Usuario) -> list[str]:
    r = user.rol_ref
    if r is not None:
        return permisos_validos(r.permisos, user.proveedor_id) if r.activo else []
    # Usuarios sin rol asignado (datos anteriores): permisos de fábrica de su tipo
    return permisos_fabrica(user.rol)


def tiene(user: Usuario, permiso: str) -> bool:
    return permiso in permisos_de(user)


def exigir(user: Usuario, permiso: str) -> None:
    if not tiene(user, permiso):
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
    from .unidades import texto

    return texto(unidad, cantidad)


def cant_txt(cantidad: int, unidad: str) -> str:
    return f"{cantidad:,} {unidad_txt(unidad, cantidad)}"


def requerir_motivo(motivo: str | None, accion: str) -> str:
    if not motivo or not motivo.strip():
        raise ErrorNegocio(f"Enter the reason to {accion}.", 422, "motivo_requerido")
    return motivo.strip()


# ---- Búsqueda de texto --------------------------------------------------------
SEPARADORES = re.compile(r"[\s,;|]+")


def terminos(q: str | None) -> list[str]:
    """Términos de una búsqueda: se separan por espacios, comas, punto y coma,
    barras o saltos de línea (p. ej. una lista de OCs pegada desde Excel)."""
    return list(dict.fromkeys(t for t in SEPARADORES.split(str(q or "").strip()) if t))


ACENTOS = "áéíóúàèìòùäëïöüâêîôûãõñçÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÂÊÎÔÛÃÕÑÇ"
SIN_ACENTOS = "aeiouaeiouaeiouaeiouaoncAEIOUAEIOUAEIOUAEIOUAONC"


def plano_sql(col):
    """La columna sin acentos y en minúsculas (SQLite: función registrada en la conexión)."""
    if ES_SQLITE:
        return func.plano(col)
    return func.lower(func.translate(col, ACENTOS, SIN_ACENTOS))


def _sin_acentos(condicion, termino: str):
    """Una comparación `columna.ilike(patrón)` pasa a compararse sin acentos ni
    mayúsculas en los dos lados; otras condiciones quedan igual."""
    if getattr(condicion, "operator", None) is operators.ilike_op:
        return plano_sql(condicion.left).like(f"%{plano(termino)}%")
    return condicion


def filtro_texto(q: str | None, condiciones):
    """Condición SQL para una búsqueda inteligente de uno o varios términos.
    `condiciones(patron)` devuelve las columnas comparadas con ese patrón.
    Cada término puede estar en cualquiera de las columnas y en cualquier orden;
    se ignoran acentos y mayúsculas. Varios códigos (términos con números) se
    buscan cualquiera de ellos; varias palabras deben estar todas
    (vietnam cat = vietnam y cat)."""
    ts = terminos(q)
    if not ts:
        return None
    por_termino = [or_(*[_sin_acentos(c, t) for c in condiciones(f"%{t}%")]) for t in ts]
    if len(ts) == 1:
        return por_termino[0]
    return or_(*por_termino) if all(re.search(r"\d", t) for t in ts) else and_(*por_termino)
