"""Flujo de clasificación: quién hace qué con la ficha técnica.

Los permisos de cada rol dicen a qué entra cada usuario; estos interruptores
dicen cómo se reparte el trabajo en la empresa y se cambian desde el sistema
sin tocar roles:

- proveedor_captura: el proveedor llena los datos de clasificación de sus
  artículos. Apagado, el proveedor solo ve la ficha y la llena el equipo
  interno (comprador o especialista).
- interno_captura: el equipo interno también puede llenar o corregir fichas.
- proveedor_ve_sugerencia: el proveedor ve la partida sugerida y la confianza
  antes de la aprobación. Apagado, solo ve qué datos faltan; la partida
  aprobada sí la ve (la necesita para sus facturas).
- revision_obligatoria: una ficha se aprueba solo después de enviarla a
  revisión.
- cuatro_ojos: quien envió la ficha a revisión no puede aprobarla.
- aprobacion_lote: se permite aprobar varias fichas a la vez.

Las reglas, atributos y dominios del motor son de quien tenga el permiso
«clasificacion.configurar» (administrador o especialista).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Historial, Meta, Usuario
from .common import ErrorNegocio, exigir, registrar

PREFIJO = "flujo."

# (clave, valor por defecto, etiqueta, ayuda)
INTERRUPTORES = [
    ("proveedor_captura", True, "Suppliers fill the classification data",
     "Suppliers fill the technical sheet of their own items. Off: they only see it and the internal team fills it."),
    ("interno_captura", True, "The internal team fills or corrects sheets",
     "Buyers and specialists can fill and correct technical sheets."),
    ("proveedor_ve_sugerencia", True, "Suppliers see the suggested code",
     "Suppliers see the suggested HS code and its confidence before approval. Off: they only see what data is missing."),
    ("revision_obligatoria", False, "Review before approval",
     "A sheet is approved only after it was sent to review."),
    ("cuatro_ojos", False, "Four eyes",
     "Whoever sent a sheet to review cannot approve it."),
    ("aprobacion_lote", True, "Bulk approval",
     "Several complete sheets can be approved at once."),
]
DEFECTOS = {k: d for k, d, _, _ in INTERRUPTORES}


def valores(db: Session) -> dict[str, bool]:
    """Interruptores vigentes (cacheados en la sesión de base de datos)."""
    if "flujo" in db.info:
        return db.info["flujo"]
    guardados = {m.clave[len(PREFIJO):]: m.valor == "1"
                 for m in db.scalars(select(Meta).where(Meta.clave.like(PREFIJO + "%"))).all()}
    out = {k: guardados.get(k, d) for k, d in DEFECTOS.items()}
    db.info["flujo"] = out
    return out


def activo(db: Session, clave: str) -> bool:
    return valores(db)[clave]


def leer(db: Session, user: Usuario) -> dict:
    exigir(user, "producto.ver")
    v = valores(db)
    return {"valores": v, "interruptores": [{"clave": k, "etiqueta": et, "ayuda": ay, "valor": v[k]}
                                            for k, _, et, ay in INTERRUPTORES]}


def guardar(db: Session, user: Usuario, cambios: dict) -> dict:
    exigir(user, "admin")
    desconocidos = set(cambios) - set(DEFECTOS)
    if desconocidos:
        raise ErrorNegocio(f"Unknown workflow setting: {', '.join(sorted(desconocidos))}.", 422, "validacion")
    nuevos = {**valores(db), **{k: bool(x) for k, x in cambios.items()}}
    if not (nuevos["proveedor_captura"] or nuevos["interno_captura"]):
        raise ErrorNegocio("Someone has to fill the technical sheets: keep suppliers or the internal team on.", 422, "validacion")
    for k, x in cambios.items():
        m = db.get(Meta, PREFIJO + k)
        if m:
            m.valor = "1" if x else "0"
        else:
            db.add(Meta(clave=PREFIJO + k, valor="1" if x else "0"))
    db.info.pop("flujo", None)
    registrar(db, user, "flujo", 0, "guardado", {k: bool(x) for k, x in cambios.items()})
    db.flush()
    return leer(db, user)


# ---- Efecto en los permisos -------------------------------------------------
def captura_permitida(db: Session, proveedor_id: int | None) -> bool:
    """Si el usuario (proveedor o interno) puede llenar fichas según el flujo."""
    return activo(db, "proveedor_captura" if proveedor_id else "interno_captura")


def ve_sugerencia(db: Session, user: Usuario) -> bool:
    return not user.proveedor_id or activo(db, "proveedor_ve_sugerencia")


# ---- Reglas de aprobación ---------------------------------------------------
def exigir_aprobacion(db: Session, user: Usuario, p, lote: bool = False) -> None:
    v = valores(db)
    if lote and not v["aprobacion_lote"]:
        raise ErrorNegocio("Bulk approval is turned off: approve each sheet on its own page.", 422, "lote_apagado")
    if v["revision_obligatoria"] and p.estado != "revision":
        raise ErrorNegocio(f"{p.estilo}: send the sheet to review before approving it.", 422, "requiere_envio")
    if v["cuatro_ojos"] and quien_envio(db, p.id) == user.id:
        raise ErrorNegocio(f"{p.estilo}: you sent this sheet to review; another person has to approve it.", 422, "cuatro_ojos")


def quien_envio(db: Session, producto_id: int) -> int | None:
    return db.scalar(select(Historial.usuario_id).where(Historial.entidad == "producto", Historial.entidad_id == producto_id,
                                                       Historial.accion == "enviado").order_by(Historial.id.desc()).limit(1))


# ---- Lo que ve el proveedor -------------------------------------------------
SUGERENCIA = ("sugerido", "sac_sugerido", "confianza", "codigo_desc")
SESION = ("clasificacion", "candidatos", "alternativas", "razones", "reglas", "evidencia", "parecidos", "paises",
          "hs6", "hs6_txt", "sac", "sac_txt", "confianza", "legal_confidence", "historical_confidence",
          "revision_por", "terminos", "perfil")


def ocultar_resumen(item: dict) -> dict:
    """Quita la sugerencia del motor de un producto (antes de su aprobación)."""
    for k in SUGERENCIA:
        if k in item:
            item[k] = None
    if isinstance(item.get("analisis"), dict):
        item["analisis"] = {k: x for k, x in item["analisis"].items() if k in ("faltan", "faltantes")}
    if "partidas" in item and not item.get("codigo"):
        item["partidas"] = {}
    item["sugerencia_oculta"] = True
    return item


def ocultar_sesion(r: dict) -> dict:
    """Resultado de la sesión de clasificación sin códigos ni candidatos:
    quedan las preguntas, lo que falta y las alertas de datos."""
    out = {k: x for k, x in r.items() if k not in SESION}
    out["alertas"] = [a for a in r.get("alertas") or [] if a.get("origen") not in ("codigo", "capitulo", "pais", "regla")]
    out["sugerencia_oculta"] = True
    return out
