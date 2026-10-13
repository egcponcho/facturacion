"""Capa CUSTOM sobre el dato oficial (OverrideArancel).

El arancel oficial (árbol, notas oficiales, códigos nacionales) nunca se
edita en sitio: lo propio de la empresa se guarda aparte, con el valor
oficial que reemplaza, el motivo, quién, cuándo y su vigencia. Un cambio
nuevo del mismo campo deja el anterior en el historial; quitar el override
vuelve al oficial.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import OverrideArancel, Usuario
from app.modulos.comun.historial import registrar


def vigentes(db: Session, tipo: str, objetivos=None, hoy: date | None = None) -> dict[str, dict]:
    """{objetivo: {campo: valor}} de los overrides activos y vigentes."""
    hoy = hoy or date.today()
    q = select(OverrideArancel).where(OverrideArancel.tipo == tipo, OverrideArancel.activo.is_(True))
    if objetivos is not None:
        objetivos = [str(o) for o in objetivos]
        if not objetivos:
            return {}
        q = q.where(OverrideArancel.objetivo.in_(objetivos))
    out: dict[str, dict] = {}
    for x in db.scalars(q.order_by(OverrideArancel.id)):
        if (x.vigente_desde and x.vigente_desde > hoy) or (x.vigente_hasta and x.vigente_hasta < hoy):
            continue
        out.setdefault(x.objetivo, {})[x.campo] = x.valor
    return out


def poner(db: Session, user: Usuario, tipo: str, objetivo: str, campo: str, valor, oficial, motivo: str | None,
          desde: date | None = None, hasta: date | None = None) -> OverrideArancel | None:
    """Crea el override (o lo quita si el valor vuelve a ser el oficial)."""
    objetivo = str(objetivo)
    valor = None if valor is None else str(valor)
    previos = list(db.scalars(select(OverrideArancel).where(OverrideArancel.tipo == tipo, OverrideArancel.objetivo == objetivo,
                                                           OverrideArancel.campo == campo, OverrideArancel.activo.is_(True))))
    actual = previos[-1].valor if previos else (None if oficial is None else str(oficial))
    if valor == actual:
        return previos[-1] if previos else None
    for x in previos:
        x.activo = False  # queda en el historial
    if valor == (None if oficial is None else str(oficial)) or (valor in (None, "") and campo != "activo"):
        registrar(db, user, "aranceles", 0, "override_quitado", {"tipo": tipo, "objetivo": objetivo, "campo": campo})
        return None
    if not (motivo or "").strip():
        raise ErrorNegocio("Say why the official value is overridden (reason).", 422, "validacion")
    x = OverrideArancel(tipo=tipo, objetivo=objetivo, campo=campo, valor=valor, valor_oficial=None if oficial is None else str(oficial),
                        motivo=motivo.strip()[:300], usuario_id=user.id if user else None, vigente_desde=desde, vigente_hasta=hasta)
    db.add(x)
    db.flush()
    registrar(db, user, "aranceles", x.id, "override", {"tipo": tipo, "objetivo": objetivo, "campo": campo, "motivo": x.motivo})
    return x


def quitar(db: Session, user: Usuario, tipo: str, objetivo: str) -> int:
    n = 0
    for x in db.scalars(select(OverrideArancel).where(OverrideArancel.tipo == tipo, OverrideArancel.objetivo == str(objetivo),
                                                     OverrideArancel.activo.is_(True))):
        x.activo = False
        n += 1
    registrar(db, user, "aranceles", 0, "override_quitado", {"tipo": tipo, "objetivo": objetivo, "campos": n})
    return n


def historial(db: Session, tipo: str, objetivo: str) -> list[dict]:
    return [{"id": x.id, "campo": x.campo, "valor": x.valor, "valor_oficial": x.valor_oficial, "motivo": x.motivo,
             "usuario": x.usuario.nombre if x.usuario else None, "creado_en": x.creado_en, "activo": x.activo,
             "vigente_desde": x.vigente_desde, "vigente_hasta": x.vigente_hasta}
            for x in db.scalars(select(OverrideArancel).where(OverrideArancel.tipo == tipo, OverrideArancel.objetivo == str(objetivo))
                                .order_by(OverrideArancel.id.desc()))]
