"""Familias de producto: cada dominio con su configuración y su salud.

Una familia (dominio) se arma con capítulos, categorías, preguntas
(atributos con ámbito en la familia o en sus categorías) y reglas. El resumen
dice qué tiene, qué le falta para clasificar bien y cómo le va con los
artículos reales (cuántos se aprueban tal cual y cuántos corrige aduanas).
"""
from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..models import (
    AtributoAmbito,
    CategoriaProducto,
    ControlCapitulo,
    DominioClasificacion,
    Producto,
    ReglaClasificacion,
    Usuario,
)
from .common import exigir

PENDIENTES = ("borrador", "sugerida", "revision", "observado")


def resumen(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "clasificacion.ver")
    caps = {c.capitulo: c for c in db.scalars(select(ControlCapitulo))}
    cats = db.scalars(select(CategoriaProducto).where(CategoriaProducto.activo.is_(True))).all()
    cats_de: dict[str, list] = {}
    for c in cats:
        cats_de.setdefault(c.dominio or "", []).append(c.codigo)
    ambitos = db.execute(select(AtributoAmbito.tipo_ambito, AtributoAmbito.codigo_ambito, AtributoAmbito.atributo_id)
                         .where(AtributoAmbito.activo.is_(True), AtributoAmbito.modo != "HIDE")).all()
    reglas = db.execute(select(ReglaClasificacion.tipo_ambito, ReglaClasificacion.codigo_ambito, ReglaClasificacion.accion,
                               ReglaClasificacion.tipo_regla)
                        .where(ReglaClasificacion.activo.is_(True), ReglaClasificacion.tipo_regla != "NATIONAL_SELECT",
                               ReglaClasificacion.tipo_ambito.in_(("DOMAIN", "CATEGORY")))).all()
    por_tipo = {(t, e, conf): n for t, e, conf, n in db.execute(
        select(Producto.tipo, Producto.estado, Producto.confianza, func.count()).group_by(Producto.tipo, Producto.estado, Producto.confianza))}
    out = []
    for d in db.scalars(select(DominioClasificacion).options(selectinload(DominioClasificacion.capitulos))
                        .order_by(DominioClasificacion.orden, DominioClasificacion.codigo)):
        mis_cats = set(cats_de.get(d.codigo, []))
        de_familia = lambda tipo, cod: (tipo == "DOMAIN" and cod == d.codigo) or (tipo == "CATEGORY" and cod in mis_cats)  # noqa: E731
        preguntas = {a for t, c, a in ambitos if de_familia(t, c)}
        propias = [r for r in reglas if de_familia(r.tipo_ambito, r.codigo_ambito)]
        acotan = [r for r in propias if (r.accion or {}).get("tipo") == "RESTRICT" or r.tipo_regla == "HARD_CONSTRAINT"]
        automaticos = [c.capitulo for c in d.capitulos if c.habilitado and c.capitulo in caps
                       and caps[c.capitulo].clasificacion and not caps[c.capitulo].solo_manual]
        prod = Counter()
        for (tipo, estado, conf), n in por_tipo.items():
            if tipo in mis_cats:
                prod["total"] += n
                prod[estado] += n
                if estado in PENDIENTES and conf == "low":
                    prod["baja"] += n
        decididos = prod["aprobado"] + prod["corregido"]
        avisos = []
        if not d.capitulos:
            avisos.append("Link the chapters of the tariff where this family is classified.")
        elif not automaticos:
            avisos.append("None of its chapters is enabled for automatic classification: every code is chosen by hand.")
        if not mis_cats:
            avisos.append("Add at least one category so products can be assigned to this family.")
        if not preguntas:
            avisos.append("No questions yet: add the attributes that decide its code.")
        if not acotan:
            avisos.append("No rule narrows its codes yet: suggestions come from the official text only (low confidence).")
        out.append({
            "id": d.id, "codigo": d.codigo, "nombre": d.nombre, "descripcion": d.descripcion, "modo": d.modo, "activo": d.activo,
            "capitulos": sorted({c.capitulo for c in d.capitulos}), "capitulos_auto": sorted(automaticos),
            "categorias": len(mis_cats), "preguntas": len(preguntas), "reglas": len(propias), "reglas_acotan": len(acotan),
            "productos": {"total": prod["total"], "aprobados": decididos, "corregidos": prod["corregido"],
                          "pendientes": sum(prod[e] for e in PENDIENTES), "baja_confianza": prod["baja"]},
            "aprobados_sin_cambio": round(100 * prod["aprobado"] / decididos) if decididos else None,
            "avisos": avisos, "estado": "lista" if not avisos else "incompleta",
        })
    return out
