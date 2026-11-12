"""Edición de las líneas de una factura (una celda o en bloque), quitarlas y
actualizar su cabecera. Una línea que ya está en una lista de empaque se
libera de ella cuando baja su cantidad.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import campos_propios, dinero
from app.core.errores import ErrorNegocio
from app.esquemas import FacturaCabecera
from app.modelos import (
    FacturaLinea,
    PLLinea,
    PosicionOC,
    Usuario,
)
from app.modelos.base import exacto
from app.modulos.acceso.permisos import (
    exigir,
)
from app.modulos.comun.formato import cant_txt
from app.modulos.comun.historial import registrar, tocar, verificar_version
from app.modulos.facturacion.cantidades import (
    asignado_por_linea,
    cubierto,
    error_en_linea,
    facturado_por_posicion,
    pl_lineas_activas,
)
from app.modulos.facturacion.estados import EDITABLE_PL, ESTADO_TXT
from app.modulos.facturacion.facturas import _ref_linea, _validar_numero, cargar_factura, exigir_editable


# ---- Edición de líneas (una celda o en bloque) -------------------------------
def _liberar_de_pl(db: Session, linea: FacturaLinea, cantidad: int) -> list[dict]:
    """Quita `cantidad` de los PL editables (del más nuevo al más viejo),
    tomando solo lo que no is in cajas."""
    pendiente = cantidad
    afectados = []
    for pll in pl_lineas_activas(db, [linea.id]):
        if pendiente <= 0:
            break
        if pll.pl.estado not in EDITABLE_PL:
            continue
        libre = pll.cantidad - cubierto(pll)
        tomar = min(libre, pendiente)
        if tomar <= 0:
            continue
        pll.cantidad -= tomar
        pendiente -= tomar
        afectados.append({"pl": pll.pl.numero, "cantidad": tomar})
        tocar(pll.pl)
        if pll.cantidad == 0:
            pll.pl.lineas.remove(pll)
    if pendiente > 0:
        raise ErrorNegocio(
            f"{_ref_linea(linea)}: only {cantidad - pendiente} could be released automatically. "
            f"{pendiente} remain in cartons or finalized PLs. "
            "Unpack those cartons or reopen the PL first.",
            409,
            "ajuste_insuficiente",
        )
    return afectados


def editar_lineas(db: Session, user: Usuario, factura_id: int, datos) -> dict:
    exigir(user, "factura.editar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    exigir_editable(f)
    verificar_version(f, datos.version, "invoice")
    lineas = {l.id: l for l in f.lineas}
    for c in datos.cambios:
        if c.linea_id not in lineas:
            raise ErrorNegocio("One of the lines is no longer on the invoice. Reload.", 404, "no_encontrado")

    con_cantidad = [lineas[c.linea_id] for c in datos.cambios if c.cantidad is not None]
    if con_cantidad:
        db.scalars(
            select(PosicionOC).where(PosicionOC.id.in_([l.posicion_oc_id for l in con_cantidad])).with_for_update()
        ).all()
    facturado = facturado_por_posicion(db, [l.posicion_oc_id for l in con_cantidad])
    asignado = asignado_por_linea(db, [l.id for l in con_cantidad])

    errores: list[dict] = []
    requieren_ajuste: list[dict] = []
    historial: list[dict] = []
    for c in datos.cambios:
        l = lineas[c.linea_id]
        campos = c.model_dump(exclude_unset=True)
        ref = _ref_linea(l)
        cambios_linea = {}

        if c.cantidad is not None and c.cantidad != l.cantidad:
            nueva = c.cantidad
            if (msg := error_en_linea(l, nueva)):
                errores.append({"linea_id": l.id, "mensaje": f"{ref}: {msg}"})
                continue
            if nueva > l.cantidad:
                p = l.posicion_oc
                disponible = p.cantidad - facturado.get(p.id, 0)
                if nueva - l.cantidad > disponible:
                    errores.append({"linea_id": l.id, "mensaje":
                        f"{ref}: the PO only has {cant_txt(max(disponible, 0), l.unidad)} more available."})
                    continue
            en_pl = asignado.get(l.id, 0)
            if nueva < en_pl:
                exceso = en_pl - nueva
                if datos.ajuste_pl == "automatico":
                    cambios_linea["liberado_de_pl"] = _liberar_de_pl(db, l, exceso)
                else:
                    requieren_ajuste.append({
                        "linea_id": l.id,
                        "ref": ref,
                        "cantidad_nueva": nueva,
                        "en_packing_lists": en_pl,
                        "hay_que_liberar": exceso,
                        "packing_lists": [
                            {"pl_id": x.pl_id, "numero": x.pl.numero, "estado": x.pl.estado,
                             "cantidad": x.cantidad, "sin_caja": x.cantidad - cubierto(x)}
                            for x in pl_lineas_activas(db, [l.id])
                        ],
                    })
                    continue
            cambios_linea["cantidad"] = [l.cantidad, nueva]
            l.cantidad = nueva

        if "precio_unitario" in campos and c.precio_unitario is not None:
            nuevo = dinero.numero(exacto(c.precio_unitario, 6))
            motivo = (campos.get("motivo_precio") or l.motivo_precio or "").strip()
            if not dinero.iguales(nuevo, l.precio_oc) and not motivo:
                errores.append({"linea_id": l.id, "codigo": "motivo_precio", "mensaje":
                    f"{ref}: enter the reason for the price change (PO price {l.precio_oc})."})
                continue
            if not dinero.iguales(nuevo, l.precio_unitario):
                cambios_linea["precio_unitario"] = [l.precio_unitario, nuevo]
            l.precio_unitario = nuevo
            l.motivo_precio = motivo if not dinero.iguales(nuevo, l.precio_oc) else None
        elif "motivo_precio" in campos:
            l.motivo_precio = (campos["motivo_precio"] or "").strip() or None

        # La partida no se captura en la factura: viene de la ficha técnica aprobada
        for campo in ("pais_origen", "descripcion_comercial"):
            if campo in campos:
                valor = (campos[campo] or "").strip() or None
                if campo == "pais_origen" and valor:
                    valor = valor.upper()
                if valor != getattr(l, campo):
                    cambios_linea[campo] = [getattr(l, campo), valor]
                    setattr(l, campo, valor)
        if cambios_linea:
            historial.append({"linea_id": l.id, "ref": ref, **cambios_linea})

    if errores:
        raise ErrorNegocio("Some changes could not be applied.", 422, "validacion", errores)
    if requieren_ajuste:
        raise ErrorNegocio(
            "The new quantity is less than what is already in packing lists.",
            409,
            "requiere_ajuste_pl",
            requieren_ajuste,
        )
    if historial:
        tocar(f)
        registrar(db, user, "factura", f.id, "editar_lineas", historial, factura_id=f.id)
    return {"version": f.version, "modificadas": len(historial)}


def eliminar_pl_linea(db: Session, pll: PLLinea) -> None:
    """Quita una parte de un PL junto con su empaque. En cajas mixtas solo
    se quita su contenido y la caja queda marcada para revisar."""
    from app.modulos.empaque import empaques

    pl = pll.pl
    for it in list(pll.items):
        g = it.grupo
        g.items.remove(it)
        if g.items or empaques.hijos(pl, g):
            empaques.nodo_bulto(g).observacion = "Check: contents were removed from this mixed carton."
    # Los empaques que quedaron vacíos (y los contenedores que solo los llevaban) se quitan
    cambio = True
    while cambio:
        cambio = False
        for g in list(pl.grupos):
            if not g.items and not empaques.hijos(pl, g):
                pl.grupos.remove(g)
                cambio = True
    db.flush()
    empaques.recalcular(pl)
    db.expire(pll, ["items"])
    pll.pl.lineas.remove(pll)


def eliminar_lineas(db: Session, user: Usuario, factura_id: int, datos) -> dict:
    exigir(user, "factura.editar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    exigir_editable(f)
    verificar_version(f, datos.version, "invoice")
    lineas = [l for l in f.lineas if l.id in set(datos.linea_ids)]
    if len(lineas) != len(set(datos.linea_ids)):
        raise ErrorNegocio("Some lines are no longer on the invoice. Reload.", 404, "no_encontrado")

    impacto = []
    bloqueos = []
    todas_pll: dict[int, list[PLLinea]] = {}
    for l in lineas:
        plls = list(db.scalars(select(PLLinea).where(PLLinea.factura_linea_id == l.id)).all())
        todas_pll[l.id] = plls
        activas = [x for x in plls if x.pl.estado != "CANCELADO"]
        for x in activas:
            if x.pl.estado not in EDITABLE_PL:
                bloqueos.append(f"{_ref_linea(l)} is in {x.pl.numero}, which is {ESTADO_TXT[x.pl.estado]}.")
        if activas:
            impacto.append({
                "linea_id": l.id,
                "ref": _ref_linea(l),
                "packing_lists": [
                    {"numero": x.pl.numero, "cantidad": x.cantidad, "en_cajas": cubierto(x)} for x in activas
                ],
            })
    if bloqueos:
        raise ErrorNegocio("Reopen the packing lists before removing these lines.", 409, "pl_no_editable",
                           [{"mensaje": b} for b in bloqueos])
    if impacto and not datos.confirmar_cascada:
        raise ErrorNegocio(
            "Some lines have quantities in packing lists. If you continue, they will also be removed from there "
            "(with their cartons) and become available on the PO again.",
            409,
            "requiere_confirmacion",
            impacto,
        )
    pls_tocados = set()
    for l in lineas:
        for x in todas_pll[l.id]:
            if x.pl.estado != "CANCELADO":
                pls_tocados.add(x.pl)
            eliminar_pl_linea(db, x)
        db.flush()
        f.lineas.remove(l)
    for pl in pls_tocados:
        tocar(pl)
    tocar(f)
    registrar(db, user, "factura", f.id, "quitar_lineas",
              [{"ref": _ref_linea(l), "cantidad": l.cantidad} for l in lineas], factura_id=f.id)
    return {"eliminadas": len(lineas), "version": f.version}


def actualizar_cabecera(db: Session, user: Usuario, factura_id: int, datos: FacturaCabecera) -> dict:
    exigir(user, "factura.editar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    exigir_editable(f)
    verificar_version(f, datos.version, "invoice")
    campos = datos.model_dump(exclude_unset=True, exclude={"version"})
    if "numero" in campos:
        campos["numero"] = (campos["numero"] or "").strip() or None
        _validar_numero(db, f.proveedor_id, campos["numero"], f.id)
    if "extra" in campos:
        campos["extra"] = campos_propios.limpiar("facturas", campos["extra"], f.extra)
    cambios = {}
    for k, v in campos.items():
        if isinstance(v, str):
            v = v.strip() or None
        if getattr(f, k) != v:
            cambios[k] = [getattr(f, k), v]
            setattr(f, k, v)
    if cambios:
        tocar(f)
        registrar(db, user, "factura", f.id, "editar_cabecera", cambios, factura_id=f.id)
    return {"version": f.version}


