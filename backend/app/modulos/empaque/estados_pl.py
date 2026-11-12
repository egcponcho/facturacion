"""Estados de una lista de empaque: qué le falta para finalizar, sus avisos, y
finalizar, reabrir o cancelar con sus bloqueos.
"""
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.core.estados import PL
from app.modelos import (
    PackingList,
    Usuario,
    ahora,
)
from app.modulos.acceso.permisos import exigir
from app.modulos.comun.formato import cant_txt
from app.modulos.comun.historial import registrar, requerir_motivo, tocar
from app.modulos.empaque import empaques
from app.modulos.empaque.packing import _editable, _ref, cargar_pl, regla_empaque, rehacer
from app.modulos.facturacion.cantidades import (
    inner_de,
    numeracion,
    sin_caja,
)

# ---- Estados ----------------------------------------------------------------
MEDIDA_TXT = {"largo": "length", "ancho": "width", "alto": "height"}


def validar_pl(pl: PackingList) -> list[dict]:
    errores = []
    if not pl.lineas:
        errores.append({"mensaje": "The packing list has no contents."})
    pendientes: dict[str, list] = {}
    for pll in pl.lineas:
        libre = sin_caja(pll)
        if libre > 0:
            d = pendientes.setdefault(pll.factura_linea.unidad, [0, 0])
            d[0] += libre
            d[1] += 1
    for unidad, (cantidad, filas) in pendientes.items():
        errores.append({"codigo": "sin_caja", "mensaje":
            f"{cant_txt(cantidad, unidad)} not in cartons (rows: {filas})."})
    rangos = numeracion(pl)
    for g in pl.grupos:
        etiqueta = f"{empaques.nombre_tipo(g)} {empaques.rango_txt(pl, g, rangos)}"
        # Medidas exteriores: las necesita el bulto y lo que no va dentro de otro empaque
        if g.padre is None or empaques.cuenta_como(g) == "BULTO":
            faltan = [n for n, v in (("largo", g.largo), ("ancho", g.ancho), ("alto", g.alto)) if not v]
            if faltan:
                errores.append({"grupo_id": g.id, "mensaje": f"{etiqueta}: dimensions missing ({', '.join(MEDIDA_TXT[x] for x in faltan)})."})
        if g.items and not g.peso_neto_caja:
            sin = sorted({it.pl_linea.factura_linea.codigo_articulo for it in g.items
                          if empaques.peso_linea(it.pl_linea.factura_linea) is None})
            errores.append({"grupo_id": g.id, "codigo": "sin_peso", "mensaje":
                            f"{etiqueta}: net weight missing. Set the unit weight of item {', '.join(sin)} "
                            "or enter the net weight." if sin else f"{etiqueta}: net weight missing."})
        for it in g.items:
            n = inner_de(it.pl_linea.factura_linea)
            if n and it.cantidad_por_caja % n:
                errores.append({"grupo_id": g.id, "mensaje": f"{etiqueta}: {_ref(it.pl_linea)} carries "
                                f"{it.cantidad_por_caja} per carton, not whole inner packs of {n}."})
        if g.peso_estimado and not empaques.calculado(g):
            errores.append({"grupo_id": g.id, "codigo": "peso_estimado",
                            "mensaje": f"{etiqueta}: the weight is estimated; confirm or correct it."})
    errores.extend(empaques.validar(pl, rangos))
    return errores


def avisos_pl(pl: PackingList) -> list[dict]:
    """Situaciones permitidas que conviene revisar (no impiden finalizar)."""
    avisos = []
    rangos = numeracion(pl)
    for g in pl.grupos:
        if empaques.cuenta_como(g) != "BULTO":
            continue
        cont = empaques.contenido(pl, g)
        if len(cont) != 1:
            continue
        pll, n = cont[0]
        regla, por_caja = regla_empaque(pll.factura_linea)
        if regla == "CASEPACK" and n != por_caja:
            avisos.append({"grupo_id": g.id, "mensaje":
                f"Carton {empaques.rango_txt(pl, g, rangos)}: partial ({n:g} of {por_caja} of the casepack). "
                "Confirm it with the Commercial Brand Manager."})
    sin_peso = sorted({pll.factura_linea.codigo_articulo for pll in pl.lineas if empaques.peso_linea(pll.factura_linea) is None})
    if sin_peso:
        lista = ", ".join(sin_peso[:8]) + ("…" if len(sin_peso) > 8 else "")
        avisos.append({"codigo": "sin_peso_articulo",
                       "mensaje": f"Items without unit weight: {lista}. Their net weight is entered by hand."})
    return avisos


def finalizar_pl(db: Session, user: Usuario, pl_id: int, version: int) -> dict:
    exigir(user, "pl.finalizar")
    pl = _editable(db, user, pl_id, version)
    if pl.factura.estado == "CANCELADA":
        raise ErrorNegocio("The invoice is cancelled.", 409, "no_editable")
    rehacer(db, pl)
    errores = validar_pl(pl)
    if errores:
        raise ErrorNegocio("Some data is missing before finalizing.", 422, "pendientes", errores)
    pl.estado, pl.finalizado_en = "FINALIZADO", ahora()
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "finalizar", None, factura_id=pl.factura_id)
    return {"estado": pl.estado, "version": pl.version}


def bloqueo_reabrir(pl: PackingList) -> str | None:
    """Por qué el PL no se puede reabrir (None: se puede). La pantalla lo
    muestra junto al botón y la acción usa la misma regla."""
    if not PL.puede("reabrir", pl.estado):
        return None if pl.estado == "CANCELADO" else "Only a finalized packing list is reopened."
    if pl.unidad and pl.unidad.embarque.estado != "PLANIFICADO":
        return f"{pl.numero} is already traveling on {pl.unidad.embarque.codigo}; it cannot be reopened."
    return None


def bloqueo_cancelar(pl: PackingList, user: Usuario) -> str | None:
    if not PL.puede("cancelar", pl.estado):
        return "The packing list is already cancelled."
    if user.rol == "proveedor" and pl.estado != "BORRADOR":
        return "You can only cancel draft packing lists."
    if pl.asignacion == "CONFIRMADA":
        return "First remove the PL from its load unit."
    return None


def reabrir_pl(db: Session, user: Usuario, pl_id: int, motivo: str | None) -> dict:
    exigir(user, "pl.reabrir")
    motivo = requerir_motivo(motivo, "reopen the packing list")
    pl = cargar_pl(db, user, pl_id)
    PL.exigir("reabrir", pl.estado, "no_editable")
    if (bloqueo := bloqueo_reabrir(pl)):
        raise ErrorNegocio(bloqueo, 409, "embarque_cerrado")
    nota = None
    if pl.unidad:
        # Solo lo finalizado va en un embarque: al reabrirlo sale de la unidad de carga
        nota = f"Removed from {pl.unidad.numero or pl.unidad.etiqueta}. Add it again once finalized."
        pl.unidad_carga_id, pl.asignacion, pl.recolectado_en = None, None, None
    pl.estado, pl.finalizado_en = "EN_CORRECCION", None
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "reabrir", {"nota": nota} if nota else None, motivo,
              factura_id=pl.factura_id)
    return {"estado": pl.estado, "nota": nota}


def cancelar_pl(db: Session, user: Usuario, pl_id: int, motivo: str | None) -> dict:
    exigir(user, "pl.cancelar")
    pl = cargar_pl(db, user, pl_id)
    PL.exigir("cancelar", pl.estado, "no_editable")
    if (bloqueo := bloqueo_cancelar(pl, user)):
        raise ErrorNegocio(bloqueo, 403 if "draft" in bloqueo else 409,
                           "sin_permiso" if "draft" in bloqueo else "pl_en_transporte")
    if pl.estado != "BORRADOR":
        motivo = requerir_motivo(motivo, "cancel the packing list")
    pl.estado = "CANCELADO"
    pl.unidad_carga_id = None
    pl.asignacion = None
    tocar(pl)
    registrar(db, user, "packing_list", pl.id, "cancelar", None, motivo, factura_id=pl.factura_id)
    return {"estado": pl.estado}


