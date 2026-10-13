"""Familias de producto: cada dominio con su configuración y su salud.

Una familia (dominio) se arma con capítulos, categorías, preguntas
(atributos con ámbito en la familia o en sus categorías) y reglas. El resumen
dice qué tiene, qué le falta para clasificar bien y cómo le va con los
artículos reales (cuántos se aprueban tal cual y cuántos corrige aduanas).
"""
from collections import Counter

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import (
    AtributoAmbito,
    CategoriaProducto,
    ControlCapitulo,
    DominioClasificacion,
    Producto,
    ReglaClasificacion,
    Usuario,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.comun.historial import registrar

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
            "publicada": d.estado != "BORRADOR",
            "capitulos": sorted({c.capitulo for c in d.capitulos}), "capitulos_auto": sorted(automaticos),
            "categorias": len(mis_cats), "preguntas": len(preguntas), "reglas": len(propias), "reglas_acotan": len(acotan),
            "productos": {"total": prod["total"], "aprobados": decididos, "corregidos": prod["corregido"],
                          "pendientes": sum(prod[e] for e in PENDIENTES), "baja_confianza": prod["baja"]},
            "aprobados_sin_cambio": round(100 * prod["aprobado"] / decididos) if decididos else None,
            "avisos": avisos, "estado": "lista" if not avisos else "incompleta",
        })
    return out


# ---- Borrador → probar → publicar ---------------------------------------------
def _familia(db: Session, codigo: str) -> DominioClasificacion:
    d = db.scalar(select(DominioClasificacion).where(DominioClasificacion.codigo == (codigo or "").upper()))
    if not d:
        raise ErrorNegocio("The product family does not exist.", 404, "no_encontrado")
    return d


def probar(db: Session, user: Usuario, codigo: str, entrada: dict) -> dict:
    """Clasifica un artículo de ejemplo con la configuración de la familia,
    aunque esté en borrador. No guarda nada."""
    from app.modulos.clasificacion.motor_clasificacion import clasificar_producto
    from app.modulos.productos.ficha import Catalogo

    exigir(user, "clasificacion.configurar")
    d = _familia(db, codigo)
    cat = Catalogo.desde_db(db, borradores=True)
    e = {k: entrada.get(k) for k in ("categoria", "nombre", "texto", "uso", "ficha", "tocados", "cambio") if entrada.get(k) is not None}
    r = clasificar_producto(db, {**e, "dominio": d.codigo, "sin_origen": True}, catalogo=cat, paises=False)
    return {k: r.get(k) for k in ("categoria", "ficha", "autos", "campos", "preguntas", "faltantes", "completa", "hs6", "hs6_txt", "confianza",
                                  "requiere_revision", "revision_por", "razones", "candidatos", "alertas", "descripciones", "detectado")}


def publicar(db: Session, user: Usuario, codigo: str) -> dict:
    """La familia pasa a estar en uso: la ficha la ofrece y clasifica artículos reales."""
    exigir(user, "clasificacion.configurar")
    d = _familia(db, codigo)
    if not d.capitulos:
        raise ErrorNegocio("Link at least one tariff chapter before publishing the family.", 422, "validacion")
    if not db.scalar(select(func.count()).where(CategoriaProducto.dominio == d.codigo, CategoriaProducto.activo.is_(True))):
        raise ErrorNegocio("Add at least one category before publishing the family.", 422, "validacion")
    d.estado = "PUBLICADA"
    registrar(db, user, "aranceles", d.id, "familia_publicada", {"codigo": d.codigo})
    db.flush()
    return next(x for x in resumen(db, user) if x["codigo"] == d.codigo)


def despublicar(db: Session, user: Usuario, codigo: str) -> dict:
    """La familia vuelve a borrador para cambiarla con calma: la ficha deja de
    ofrecerla y no clasifica artículos nuevos. Los artículos ya aprobados
    conservan su partida."""
    exigir(user, "clasificacion.configurar")
    d = _familia(db, codigo)
    d.estado = "BORRADOR"
    registrar(db, user, "aranceles", d.id, "familia_despublicada", {"codigo": d.codigo})
    db.flush()
    return next(x for x in resumen(db, user) if x["codigo"] == d.codigo)


def detalle(db: Session, user: Usuario, codigo: str) -> dict:
    """Todo lo que arma una familia, para el asistente: capítulos, categorías,
    preguntas (atributos con ámbito en la familia) y reglas de la familia."""
    from app.modelos import AtributoDef

    exigir(user, "clasificacion.ver")
    d = _familia(db, codigo)
    caps = {c.capitulo: c for c in db.scalars(select(ControlCapitulo))}
    cats = db.scalars(select(CategoriaProducto).where(CategoriaProducto.dominio == d.codigo).order_by(CategoriaProducto.orden)).all()
    mis = {c.codigo for c in cats}
    preguntas = []
    for a in db.scalars(select(AtributoDef).options(selectinload(AtributoDef.ambitos)).where(AtributoDef.activo.is_(True)).order_by(AtributoDef.orden)):
        for x in a.ambitos:
            if (x.tipo_ambito == "DOMAIN" and x.codigo_ambito == d.codigo) or (x.tipo_ambito == "CATEGORY" and x.codigo_ambito in mis):
                preguntas.append({"atributo_id": a.id, "codigo": a.codigo, "etiqueta": a.etiqueta, "ambito_id": x.id, "tipo_ambito": x.tipo_ambito,
                                  "codigo_ambito": x.codigo_ambito, "modo": x.modo, "activo": x.activo})
    reglas = db.scalars(select(ReglaClasificacion).where(ReglaClasificacion.tipo_regla != "NATIONAL_SELECT", or_(
        (ReglaClasificacion.tipo_ambito == "DOMAIN") & (ReglaClasificacion.codigo_ambito == d.codigo),
        (ReglaClasificacion.tipo_ambito == "CATEGORY") & ReglaClasificacion.codigo_ambito.in_(mis or {""}))).order_by(ReglaClasificacion.prioridad.desc())).all()
    return {
        "id": d.id, "codigo": d.codigo, "nombre": d.nombre, "descripcion": d.descripcion, "modo": d.modo, "activo": d.activo,
        "publicada": d.estado != "BORRADOR",
        "capitulos": [{"capitulo": c.capitulo, "relevancia": c.relevancia, "habilitado": c.habilitado,
                       "titulo": caps[c.capitulo].titulo if c.capitulo in caps else "",
                       "automatico": bool(c.capitulo in caps and caps[c.capitulo].clasificacion and not caps[c.capitulo].solo_manual)}
                      for c in sorted(d.capitulos, key=lambda c: c.capitulo)],
        "categorias": [{"id": c.id, "codigo": c.codigo, "nombre": c.nombre, "nombre_aduana": c.nombre_aduana, "activo": c.activo} for c in cats],
        "preguntas": preguntas,
        "reglas": [{"id": r.id, "codigo": r.codigo, "tipo_regla": r.tipo_regla, "efecto": r.efecto, "activo": r.activo, "prioridad": r.prioridad,
                    "accion": r.accion, "tipo_ambito": r.tipo_ambito, "codigo_ambito": r.codigo_ambito} for r in reglas],
    }
