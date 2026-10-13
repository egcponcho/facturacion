"""Dónde se aplica cada plantilla y cuál se elige para una etiqueta.

Prioridad (docs/ETIQUETADO.md): excepción de la OC → artículo → producto →
familia del artículo → general de la organización. Solo cuentan plantillas
activas de la modalidad pedida con una versión aprobada vigente. En el primer
nivel con candidatas: una sola se usa; varias, la predeterminada; si no hay
una inequívoca, el usuario elige (nunca se elige un diseño al azar).
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    AsignacionEtiqueta,
    FamiliaEtiquetado,
    OrdenCompra,
    PlantillaEtiqueta,
    Producto,
    Usuario,
)
from app.modelos.etiquetado import AMBITOS
from app.modulos.acceso.permisos import exigir
from app.modulos.comun.historial import registrar

# Modalidades que admite cada ámbito: una OC no tiene artículo y un artículo no tiene OC
MODALIDADES_DE = {"GENERAL": {"ARTICULO", "OC", "OC_ARTICULO"}, "FAMILIA": {"ARTICULO", "OC_ARTICULO"},
                  "PRODUCTO": {"ARTICULO", "OC_ARTICULO"}, "ARTICULO": {"ARTICULO", "OC_ARTICULO"},
                  "OC": {"OC", "OC_ARTICULO"}}
DESTINO = {"FAMILIA": "familia_id", "PRODUCTO": "producto_id", "ARTICULO": "articulo_id", "OC": "oc_id"}


def _destino_txt(db: Session, a: AsignacionEtiqueta) -> str | None:
    if a.ambito == "FAMILIA" and a.familia_id:
        f = db.get(FamiliaEtiquetado, a.familia_id)
        return f.nombre if f else None
    if a.ambito == "PRODUCTO" and a.producto_id:
        p = db.get(Producto, a.producto_id)
        return (p.nombre or p.estilo) if p else None
    if a.ambito == "ARTICULO" and a.articulo_id:
        art = db.get(Articulo, a.articulo_id)
        return art.sku if art else None
    if a.ambito == "OC" and a.oc_id:
        oc = db.get(OrdenCompra, a.oc_id)
        return oc.numero if oc else None
    return None


def dict_asignacion(db: Session, a: AsignacionEtiqueta) -> dict:
    p = a.plantilla
    return {"id": a.id, "plantilla_id": a.plantilla_id, "plantilla": p.nombre, "modalidad": p.modalidad, "ambito": a.ambito,
            "familia_id": a.familia_id, "producto_id": a.producto_id, "articulo_id": a.articulo_id, "oc_id": a.oc_id,
            "destino": _destino_txt(db, a), "predeterminada": a.predeterminada, "activa": a.activa, "motivo": a.motivo,
            "creada_en": a.creada_en, "version_vigente": p.vigente.numero if p.vigente else None}


def listar(db: Session, user: Usuario, plantilla_id=None, ambito=None, familia_id=None, producto_id=None, articulo_id=None,
           oc_id=None, activas: bool | None = True) -> list[dict]:
    exigir(user, "etiquetas.ver")
    c = select(AsignacionEtiqueta).order_by(AsignacionEtiqueta.ambito, AsignacionEtiqueta.id)
    for col, v in (("plantilla_id", plantilla_id), ("familia_id", familia_id), ("producto_id", producto_id),
                   ("articulo_id", articulo_id), ("oc_id", oc_id)):
        if v:
            c = c.where(getattr(AsignacionEtiqueta, col) == v)
    if ambito:
        c = c.where(AsignacionEtiqueta.ambito == ambito.upper())
    if activas is not None:
        c = c.where(AsignacionEtiqueta.activa.is_(activas))
    return [dict_asignacion(db, a) for a in db.scalars(c)]


def _cargar(db: Session, asignacion_id: int) -> AsignacionEtiqueta:
    a = db.get(AsignacionEtiqueta, asignacion_id)
    if not a:
        raise ErrorNegocio("The assignment does not exist.", 404, "no_encontrado")
    return a


def _hermanas(db: Session, a: AsignacionEtiqueta):
    """Asignaciones activas del mismo nivel, destino y modalidad (compiten entre sí)."""
    c = select(AsignacionEtiqueta).join(PlantillaEtiqueta).where(
        AsignacionEtiqueta.ambito == a.ambito, AsignacionEtiqueta.activa.is_(True), AsignacionEtiqueta.id != a.id,
        PlantillaEtiqueta.modalidad == a.plantilla.modalidad)
    if a.ambito in DESTINO:
        c = c.where(getattr(AsignacionEtiqueta, DESTINO[a.ambito]) == getattr(a, DESTINO[a.ambito]))
    return db.scalars(c)


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "etiquetas.asignar")
    from app.modulos.etiquetado.plantillas import cargar as cargar_plantilla

    p = cargar_plantilla(db, datos.get("plantilla_id") or 0)
    ambito = (datos.get("ambito") or "").upper()
    if ambito not in AMBITOS:
        raise ErrorNegocio("Choose where the design applies.", 422, "validacion")
    if p.estado != "ACTIVA":
        raise ErrorNegocio("The design is archived.", 422, "validacion")
    if p.modalidad not in MODALIDADES_DE[ambito]:
        raise ErrorNegocio("This design's data mode does not apply there (a PO design has no item, an item design has no PO).",
                           422, "validacion")
    destino = {}
    if ambito in DESTINO:
        col = DESTINO[ambito]
        valor = datos.get(col)
        modelo = {"familia_id": FamiliaEtiquetado, "producto_id": Producto, "articulo_id": Articulo, "oc_id": OrdenCompra}[col]
        if not valor or not db.get(modelo, valor):
            raise ErrorNegocio("Choose where the design applies.", 422, "validacion", [{"campo": col, "mensaje": "It does not exist."}])
        destino[col] = valor
    repetida = db.scalar(select(AsignacionEtiqueta.id).where(
        AsignacionEtiqueta.plantilla_id == p.id, AsignacionEtiqueta.ambito == ambito, AsignacionEtiqueta.activa.is_(True),
        *[getattr(AsignacionEtiqueta, k) == v for k, v in destino.items()]))
    if repetida:
        raise ErrorNegocio("The design is already assigned there.", 409, "repetida")
    motivo = (datos.get("motivo") or "").strip()[:300] or None
    if ambito == "OC" and not motivo:
        raise ErrorNegocio("Explain why this PO is an exception.", 422, "validacion", [{"campo": "motivo", "mensaje": "Required."}])
    a = AsignacionEtiqueta(plantilla_id=p.id, ambito=ambito, predeterminada=bool(datos.get("predeterminada")), activa=True,
                           motivo=motivo, creada_por=user.id, **destino)
    db.add(a)
    db.flush()
    db.refresh(a)
    if a.predeterminada:
        for otra in _hermanas(db, a):
            otra.predeterminada = False
    db.flush()
    registrar(db, user, "plantilla_etiqueta", p.id, "asignar", {"ambito": ambito, **destino, "predeterminada": a.predeterminada},
              motivo)
    return dict_asignacion(db, a)


def actualizar(db: Session, user: Usuario, asignacion_id: int, datos: dict) -> dict:
    exigir(user, "etiquetas.asignar")
    a = _cargar(db, asignacion_id)
    if "activa" in datos:
        a.activa = bool(datos["activa"])
    if "predeterminada" in datos:
        a.predeterminada = bool(datos["predeterminada"])
        if a.predeterminada:
            for otra in _hermanas(db, a):
                otra.predeterminada = False
    if "motivo" in datos:
        a.motivo = (datos.get("motivo") or "").strip()[:300] or None
    db.flush()
    registrar(db, user, "plantilla_etiqueta", a.plantilla_id, "editar_asignacion",
              {"asignacion": a.id, "activa": a.activa, "predeterminada": a.predeterminada})
    return dict_asignacion(db, a)


def eliminar(db: Session, user: Usuario, asignacion_id: int) -> dict:
    exigir(user, "etiquetas.asignar")
    a = _cargar(db, asignacion_id)
    registrar(db, user, "plantilla_etiqueta", a.plantilla_id, "quitar_asignacion", {"ambito": a.ambito, "destino": _destino_txt(db, a)})
    db.delete(a)
    db.flush()
    return {"ok": True}


# ---- Resolución -------------------------------------------------------------------------
NIVELES = ("OC", "ARTICULO", "PRODUCTO", "FAMILIA", "GENERAL")


@dataclass
class Eleccion:
    plantilla: PlantillaEtiqueta | None = None
    nivel: str | None = None
    motivo: str | None = None
    candidatas: list[PlantillaEtiqueta] = field(default_factory=list)  # si hay que elegir
    sin_aprobar: list[PlantillaEtiqueta] = field(default_factory=list)  # asignadas pero sin versión aprobada
    avisos: list[str] = field(default_factory=list)

    @property
    def ambigua(self) -> bool:
        return self.plantilla is None and len(self.candidatas) > 1

    def dict(self) -> dict:
        p = self.plantilla
        return {"plantilla_id": p.id if p else None, "plantilla": p.nombre if p else None,
                "familia": p.familia.nombre if p and p.familia else None,
                "version_id": p.version_vigente_id if p else None, "version": p.vigente.numero if p and p.vigente else None,
                "nivel": self.nivel, "motivo": self.motivo, "ambigua": self.ambigua,
                "candidatas": [{"plantilla_id": c.id, "plantilla": c.nombre, "version": c.vigente.numero if c.vigente else None}
                               for c in self.candidatas],
                "sin_aprobar": [{"plantilla_id": c.id, "plantilla": c.nombre} for c in self.sin_aprobar],
                "avisos": self.avisos}


def resolver(db: Session, modalidad: str, articulo: Articulo | None = None, oc: OrdenCompra | None = None,
             elegida_id: int | None = None) -> Eleccion:
    """La plantilla que corresponde (con la vigente aprobada) y por qué.
    `elegida_id`: la que eligió el usuario entre varias del mismo nivel."""
    filtros = {"OC": oc.id if oc else None, "ARTICULO": articulo.id if articulo else None,
               "PRODUCTO": articulo.producto_id if articulo else None,
               "FAMILIA": articulo.familia_etiquetado_id if articulo else None, "GENERAL": True}
    res = Eleccion()
    for nivel in NIVELES:
        if not filtros[nivel] or modalidad not in MODALIDADES_DE[nivel]:
            continue
        c = select(AsignacionEtiqueta).join(PlantillaEtiqueta).where(
            AsignacionEtiqueta.ambito == nivel, AsignacionEtiqueta.activa.is_(True), PlantillaEtiqueta.estado == "ACTIVA",
            PlantillaEtiqueta.modalidad == modalidad)
        if nivel in DESTINO:
            c = c.where(getattr(AsignacionEtiqueta, DESTINO[nivel]) == filtros[nivel])
        asignadas = list(db.scalars(c.order_by(AsignacionEtiqueta.id)))
        if not asignadas:
            continue
        res.sin_aprobar += [a.plantilla for a in asignadas if not a.plantilla.version_vigente_id]
        aprobadas = [a for a in asignadas if a.plantilla.version_vigente_id]
        if not aprobadas:
            continue
        res.nivel = nivel
        if elegida_id and any(a.plantilla_id == elegida_id for a in aprobadas):
            elegida = next(a for a in aprobadas if a.plantilla_id == elegida_id)
            res.plantilla, res.motivo = elegida.plantilla, "Chosen by the user among the designs of the same level."
        elif len({a.plantilla_id for a in aprobadas}) == 1:
            res.plantilla = aprobadas[0].plantilla
        else:
            predeterminadas = [a for a in aprobadas if a.predeterminada]
            if len(predeterminadas) == 1:
                res.plantilla = predeterminadas[0].plantilla
            else:
                res.candidatas = list({a.plantilla_id: a.plantilla for a in aprobadas}.values())
                res.motivo = "Several designs apply with the same priority: choose one."
                break
        if not res.motivo:
            res.motivo = _motivo(db, nivel, articulo, oc, len(aprobadas) > 1)
        break
    if res.plantilla and articulo and res.plantilla.familia_id and articulo.familia_etiquetado_id \
            and res.plantilla.familia_id != articulo.familia_etiquetado_id:
        res.avisos.append("The design was made for another labeling family.")
    if articulo is not None and not articulo.familia_etiquetado_id:
        res.avisos.append("The item has no labeling family.")
    return res


def _motivo(db: Session, nivel: str, articulo, oc, por_predeterminada: bool) -> str:
    extra = " (default among several)" if por_predeterminada else ""
    if nivel == "OC":
        return f"Exception assigned to PO {oc.numero}{extra}."
    if nivel == "ARTICULO":
        return f"Assigned to the item {articulo.sku}{extra}."
    if nivel == "PRODUCTO":
        return f"Assigned to the product {articulo.estilo} (all its variants){extra}."
    if nivel == "FAMILIA":
        f = db.get(FamiliaEtiquetado, articulo.familia_etiquetado_id)
        return f"Design of the labeling family {f.nombre if f else ''}{extra}."
    return f"General design of the organization{extra}."
