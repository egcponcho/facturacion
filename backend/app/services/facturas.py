import os
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Archivo,
    Factura,
    FacturaLinea,
    Historial,
    OrdenCompra,
    PackingList,
    PLLinea,
    PosicionOC,
    Proveedor,
    Usuario,
    ahora,
)
from ..schemas import FacturaCabecera, FacturaCrear, PosicionCantidad
from .cantidades import (
    asignado_por_linea,
    cubierto,
    facturado_por_posicion,
    limpiar_pallets,
    facturas_por_posicion,
    nombre_factura,
    pl_lineas_activas,
    totales_pl,
)
from .partes import partes
from .common import (
    EDITABLE_FACTURA,
    EDITABLE_PL,
    ESTADO_TXT,
    ErrorNegocio,
    asegurar_proveedor,
    cant_txt,
    es_interno,
    exigir,
    proveedor_filtro,
    registrar,
    requerir_motivo,
    tocar,
    verificar_version,
)

ETIQUETAS = {
    "sociedad": "sociedades",
    "moneda": "monedas",
    "centro": "centros de destino",
    "incoterm": "incoterms",
    "centro_destino": "países de destino",
}


# ---- Carga y validaciones de estado -----------------------------------------
def cargar_factura(db: Session, user: Usuario, factura_id: int, bloquear: bool = False) -> Factura:
    consulta = select(Factura).where(Factura.id == factura_id)
    if bloquear:
        consulta = consulta.with_for_update()
    f = db.scalar(consulta)
    if not f:
        raise ErrorNegocio("La factura no existe.", 404, "no_encontrado")
    asegurar_proveedor(user, f.proveedor_id)
    return f


def exigir_editable(f: Factura) -> None:
    if f.estado not in EDITABLE_FACTURA:
        raise ErrorNegocio(
            f"La factura está {ESTADO_TXT[f.estado]} y no se puede editar."
            + (" Reábrela para hacer cambios." if f.estado == "FINALIZADA" else ""),
            409,
            "no_editable",
        )


def _ref_linea(l: FacturaLinea) -> str:
    return f"OC {l.oc_numero} pos. {l.posicion} ({l.codigo_sap}{' talla ' + l.talla if l.talla else ''})"


def _validar_numero(db: Session, proveedor_id: int, numero: str | None, excluir_id: int | None) -> None:
    if not numero:
        return
    consulta = select(Factura.id).where(
        Factura.proveedor_id == proveedor_id,
        Factura.numero == numero,
        Factura.estado != "CANCELADA",
    )
    if excluir_id:
        consulta = consulta.where(Factura.id != excluir_id)
    if db.scalar(consulta):
        raise ErrorNegocio(
            f"Ya existe una factura {numero} de este proveedor.", 409, "numero_duplicado"
        )


# ---- Selección de posiciones (OC completas o parciales) ---------------------
def _preparar_posiciones(
    db: Session,
    user: Usuario,
    solicitudes: list[PosicionCantidad],
    proveedor_id: int | None = None,
    factura: Factura | None = None,
):
    pedidas: dict[int, int] = {}
    for s in solicitudes:
        pedidas[s.posicion_id] = pedidas.get(s.posicion_id, 0) + s.cantidad

    # Bloqueo de filas: dos personas no pueden tomar el mismo saldo a la vez
    posiciones = list(
        db.scalars(
            select(PosicionOC).where(PosicionOC.id.in_(pedidas)).order_by(PosicionOC.id).with_for_update()
        ).all()
    )
    if len(posiciones) != len(pedidas):
        raise ErrorNegocio("Algunas posiciones ya no existen. Recarga la lista.", 404, "no_encontrado")
    ocs = {p.oc_id: p.oc for p in posiciones}

    proveedores = {oc.proveedor_id for oc in ocs.values()}
    if factura:
        proveedores.add(factura.proveedor_id)
    if len(proveedores) > 1:
        raise ErrorNegocio("Una factura solo puede tener posiciones de un mismo proveedor.", 422, "proveedor_mixto")
    prov = next(iter(proveedores))
    if proveedor_id and prov != proveedor_id:
        raise ErrorNegocio("Las posiciones no pertenecen al proveedor seleccionado.", 422, "proveedor_mixto")
    asegurar_proveedor(user, prov)

    errores: list[dict] = []
    advertencias: list[str] = []
    for campo in settings.COMPATIBILIDAD_BLOQUEANTE + settings.COMPATIBILIDAD_ADVERTENCIA:
        valores = {getattr(oc, campo) for oc in ocs.values()}
        if factura:
            valores.add(getattr(factura, campo))
        valores.discard(None)
        if len(valores) > 1:
            texto = f"Estás mezclando {ETIQUETAS[campo]} distintos: {', '.join(sorted(map(str, valores)))}."
            if campo in settings.COMPATIBILIDAD_BLOQUEANTE:
                errores.append({"mensaje": texto + " Sepáralos en facturas diferentes."})
            else:
                advertencias.append(texto)

    ids = list(pedidas)
    facturado = facturado_por_posicion(db, ids)
    activas = facturas_por_posicion(db, ids)
    for p in posiciones:
        oc = ocs[p.oc_id]
        ref = f"OC {oc.numero} pos. {p.posicion}"
        cantidad = pedidas[p.id]
        if not oc.liberada:
            errores.append({"posicion_id": p.id, "mensaje": f"{ref}: la OC no está liberada."})
            continue
        if p.bloqueada:
            errores.append({"posicion_id": p.id, "mensaje": f"{ref}: {p.motivo_bloqueo or 'posición bloqueada'}."})
            continue
        if not settings.POSICION_EN_VARIAS_FACTURAS:
            otras = [a for a in activas.get(p.id, []) if not factura or a["id"] != factura.id]
            if otras:
                errores.append(
                    {
                        "posicion_id": p.id,
                        "mensaje": f"{ref} ya está en {otras[0]['nombre']}. "
                        "Agrega el saldo en esa factura o quítala de ahí primero.",
                    }
                )
                continue
        disponible = p.cantidad - facturado.get(p.id, 0)
        if cantidad > disponible:
            errores.append(
                {
                    "posicion_id": p.id,
                    "mensaje": f"{ref}: solo quedan {cant_txt(max(disponible, 0), p.unidad)} disponibles "
                    f"y pediste {cantidad}.",
                }
            )
    if errores:
        raise ErrorNegocio("No se pudieron agregar algunas posiciones.", 422, "validacion", errores)
    return posiciones, ocs, pedidas, advertencias


def _nueva_linea(p: PosicionOC, oc: OrdenCompra, cantidad: int) -> FacturaLinea:
    return FacturaLinea(
        posicion_oc_id=p.id,
        cantidad=cantidad,
        precio_unitario=p.precio,
        precio_oc=p.precio,
        oc_numero=oc.numero,
        posicion=p.posicion,
        almacen=p.almacen,
        codigo_sap=p.codigo_sap,
        upc=p.upc,
        estilo=p.estilo,
        color=p.color,
        talla=p.talla,
        descripcion=p.descripcion,
        unidad=p.unidad,
        marca=p.marca,
        categoria=p.categoria,
        tipo_empaque=p.tipo_empaque,
        casepack=p.casepack,
        prepack=p.prepack,
        unidades_por_caja=p.unidades_por_caja,
        centro_destino=oc.centro_destino,
        pais_origen=p.pais_origen,
        partida_arancelaria=p.partida_arancelaria,
        descripcion_comercial=p.descripcion,
    )


def crear_factura(db: Session, user: Usuario, datos: FacturaCrear) -> dict:
    exigir(user, "factura.editar")
    posiciones, ocs, pedidas, advertencias = _preparar_posiciones(
        db, user, datos.lineas, proveedor_id=proveedor_filtro(user, datos.proveedor_id)
    )
    oc0 = ocs[posiciones[0].oc_id]
    numero = (datos.numero or "").strip() or None
    _validar_numero(db, oc0.proveedor_id, numero, None)
    f = Factura(
        proveedor_id=oc0.proveedor_id,
        numero=numero,
        fecha=datos.fecha,
        moneda=oc0.moneda,
        incoterm=oc0.incoterm,
        sociedad=oc0.sociedad,
        centro=oc0.centro,
        centro_destino=oc0.centro_destino,
        estado="BORRADOR",
        version=1,
        creado_por=user.id,
    )
    db.add(f)
    for p in posiciones:
        f.lineas.append(_nueva_linea(p, ocs[p.oc_id], pedidas[p.id]))
    db.flush()
    registrar(
        db, user, "factura", f.id, "crear",
        {"lineas": len(posiciones), "ocs": sorted({oc.numero for oc in ocs.values()})},
        factura_id=f.id,
    )
    return {"id": f.id, "nombre": nombre_factura(f), "advertencias": advertencias}


def agregar_lineas(db: Session, user: Usuario, factura_id: int, version: int, lineas) -> dict:
    exigir(user, "factura.editar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    exigir_editable(f)
    verificar_version(f, version, "factura")
    posiciones, ocs, pedidas, advertencias = _preparar_posiciones(db, user, lineas, factura=f)
    existentes = {l.posicion_oc_id: l for l in f.lineas}
    agregadas = aumentadas = 0
    for p in posiciones:
        if p.id in existentes:
            existentes[p.id].cantidad += pedidas[p.id]
            aumentadas += 1
        else:
            f.lineas.append(_nueva_linea(p, ocs[p.oc_id], pedidas[p.id]))
            agregadas += 1
    tocar(f)
    registrar(db, user, "factura", f.id, "agregar_lineas",
              {"nuevas": agregadas, "aumentadas": aumentadas}, factura_id=f.id)
    return {"agregadas": agregadas, "aumentadas": aumentadas, "advertencias": advertencias}


# ---- Edición de líneas (una celda o en bloque) -------------------------------
def _liberar_de_pl(db: Session, linea: FacturaLinea, cantidad: int) -> list[dict]:
    """Quita `cantidad` de los PL editables (del más nuevo al más viejo),
    tomando solo lo que no está en cajas."""
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
            f"{_ref_linea(linea)}: solo se pudieron liberar {cantidad - pendiente} automáticamente. "
            f"Faltan {pendiente}, que están en cajas o en PL finalizados. "
            "Desempaca esas cajas o reabre el PL primero.",
            409,
            "ajuste_insuficiente",
        )
    return afectados


def editar_lineas(db: Session, user: Usuario, factura_id: int, datos) -> dict:
    exigir(user, "factura.editar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    exigir_editable(f)
    verificar_version(f, datos.version, "factura")
    lineas = {l.id: l for l in f.lineas}
    for c in datos.cambios:
        if c.linea_id not in lineas:
            raise ErrorNegocio("Una de las líneas ya no está en la factura. Recarga.", 404, "no_encontrado")

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
            if nueva > l.cantidad:
                p = l.posicion_oc
                disponible = p.cantidad - facturado.get(p.id, 0)
                if nueva - l.cantidad > disponible:
                    errores.append({"linea_id": l.id, "mensaje":
                        f"{ref}: la OC solo tiene {cant_txt(max(disponible, 0), l.unidad)} más disponibles."})
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
            nuevo = round(c.precio_unitario, 4)
            motivo = (campos.get("motivo_precio") or l.motivo_precio or "").strip()
            if abs(nuevo - l.precio_oc) > 1e-9 and not motivo:
                errores.append({"linea_id": l.id, "codigo": "motivo_precio", "mensaje":
                    f"{ref}: indica el motivo del cambio de precio (precio OC {l.precio_oc})."})
                continue
            if abs(nuevo - l.precio_unitario) > 1e-9:
                cambios_linea["precio_unitario"] = [l.precio_unitario, nuevo]
            l.precio_unitario = nuevo
            l.motivo_precio = motivo if abs(nuevo - l.precio_oc) > 1e-9 else None
        elif "motivo_precio" in campos:
            l.motivo_precio = (campos["motivo_precio"] or "").strip() or None

        for campo in ("pais_origen", "partida_arancelaria", "descripcion_comercial"):
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
        raise ErrorNegocio("Algunos cambios no se pudieron aplicar.", 422, "validacion", errores)
    if requieren_ajuste:
        raise ErrorNegocio(
            "La nueva cantidad es menor que lo que ya está en packing lists.",
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
    for it in list(pll.items):
        g = it.grupo
        g.items.remove(it)
        if not g.items:
            g.pl.grupos.remove(g)
        else:
            g.peso_estimado = True
            g.observacion = "Revisar: se retiró contenido de esta caja mixta."
    limpiar_pallets(pll.pl)
    db.flush()
    db.expire(pll, ["items"])
    pll.pl.lineas.remove(pll)


def eliminar_lineas(db: Session, user: Usuario, factura_id: int, datos) -> dict:
    exigir(user, "factura.editar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    exigir_editable(f)
    verificar_version(f, datos.version, "factura")
    lineas = [l for l in f.lineas if l.id in set(datos.linea_ids)]
    if len(lineas) != len(set(datos.linea_ids)):
        raise ErrorNegocio("Algunas líneas ya no están en la factura. Recarga.", 404, "no_encontrado")

    impacto = []
    bloqueos = []
    todas_pll: dict[int, list[PLLinea]] = {}
    for l in lineas:
        plls = list(db.scalars(select(PLLinea).where(PLLinea.factura_linea_id == l.id)).all())
        todas_pll[l.id] = plls
        activas = [x for x in plls if x.pl.estado != "CANCELADO"]
        for x in activas:
            if x.pl.estado not in EDITABLE_PL:
                bloqueos.append(f"{_ref_linea(l)} está en {x.pl.numero}, que está {ESTADO_TXT[x.pl.estado]}.")
        if activas:
            impacto.append({
                "linea_id": l.id,
                "ref": _ref_linea(l),
                "packing_lists": [
                    {"numero": x.pl.numero, "cantidad": x.cantidad, "en_cajas": cubierto(x)} for x in activas
                ],
            })
    if bloqueos:
        raise ErrorNegocio("Reabre los packing lists antes de quitar estas líneas.", 409, "pl_no_editable",
                           [{"mensaje": b} for b in bloqueos])
    if impacto and not datos.confirmar_cascada:
        raise ErrorNegocio(
            "Algunas líneas tienen cantidades en packing lists. Si continúas, también se quitarán de ahí "
            "(con sus cajas) y volverán a estar disponibles en la OC.",
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
    verificar_version(f, datos.version, "factura")
    campos = datos.model_dump(exclude_unset=True, exclude={"version"})
    if "numero" in campos:
        campos["numero"] = (campos["numero"] or "").strip() or None
        _validar_numero(db, f.proveedor_id, campos["numero"], f.id)
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


# ---- Estados ----------------------------------------------------------------
def validar_factura(db: Session, f: Factura) -> list[dict]:
    errores = []
    if not f.numero:
        errores.append({"campo": "numero", "mensaje": "Falta el número de factura."})
    if not f.fecha:
        errores.append({"campo": "fecha", "mensaje": "Falta la fecha de la factura."})
    if not f.incoterm:
        errores.append({"campo": "incoterm", "mensaje": "Falta el incoterm (condición de entrega)."})
    if not f.lineas:
        errores.append({"mensaje": "La factura no tiene líneas."})
    facturado = facturado_por_posicion(db, [l.posicion_oc_id for l in f.lineas])
    for l in f.lineas:
        ref = _ref_linea(l)
        if l.precio_unitario <= 0:
            errores.append({"linea_id": l.id, "mensaje": f"{ref}: el precio debe ser mayor que cero."})
        if abs(l.precio_unitario - l.precio_oc) > 1e-9 and not l.motivo_precio:
            errores.append({"linea_id": l.id, "mensaje": f"{ref}: falta el motivo del cambio de precio."})
        if not (l.descripcion_comercial or "").strip():
            errores.append({"linea_id": l.id, "mensaje": f"{ref}: falta la descripción comercial de la mercancía."})
        if settings.REQUERIR_DATOS_ADUANA:
            if not l.pais_origen:
                errores.append({"linea_id": l.id, "mensaje": f"{ref}: falta el país de origen."})
            if not l.partida_arancelaria:
                errores.append({"linea_id": l.id, "mensaje": f"{ref}: falta la partida arancelaria."})
        p = l.posicion_oc
        if facturado.get(p.id, 0) > p.cantidad:
            errores.append({"linea_id": l.id, "mensaje":
                f"{ref}: lo facturado ({facturado[p.id]}) supera la cantidad actual de la OC ({p.cantidad})."})
        if p.bloqueada:
            errores.append({"linea_id": l.id, "mensaje": f"{ref}: la posición está bloqueada en la OC."})
    return errores


def finalizar(db: Session, user: Usuario, factura_id: int, version: int, incluir_pls: bool) -> dict:
    from .packing import validar_pl  # evitar import circular

    exigir(user, "factura.finalizar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    if f.estado not in EDITABLE_FACTURA:
        raise ErrorNegocio(f"La factura ya está {ESTADO_TXT[f.estado]}.", 409, "no_editable")
    verificar_version(f, version, "factura")
    errores = validar_factura(db, f)
    pls = []
    if incluir_pls:
        exigir(user, "pl.finalizar")
        asignado = asignado_por_linea(db, [l.id for l in f.lineas])
        for l in f.lineas:
            falta = l.cantidad - asignado.get(l.id, 0)
            if falta > 0:
                errores.append({"linea_id": l.id, "mensaje":
                    f"{_ref_linea(l)}: quedan {cant_txt(falta, l.unidad)} sin asignar a un packing list."})
        pls = [pl for pl in f.packing_lists if pl.estado in EDITABLE_PL]
        for pl in pls:
            errores += [{**e, "mensaje": f"{pl.numero}: {e['mensaje']}"} for e in validar_pl(pl)]
    if errores:
        raise ErrorNegocio("Hay datos pendientes antes de finalizar.", 422, "pendientes", errores)
    f.estado = "FINALIZADA"
    f.finalizado_en = ahora()
    tocar(f)
    registrar(db, user, "factura", f.id, "finalizar", {"con_pl": [pl.numero for pl in pls]}, factura_id=f.id)
    for pl in pls:
        pl.estado = "FINALIZADO"
        tocar(pl)
        registrar(db, user, "packing_list", pl.id, "finalizar", None, factura_id=f.id)
    return {"estado": f.estado, "version": f.version}


def reabrir(db: Session, user: Usuario, factura_id: int, motivo: str | None) -> dict:
    exigir(user, "factura.reabrir")
    motivo = requerir_motivo(motivo, "reabrir la factura")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    if f.estado != "FINALIZADA":
        raise ErrorNegocio("Solo se pueden reabrir facturas finalizadas.", 409, "no_editable")
    f.estado = "EN_CORRECCION"
    tocar(f)
    registrar(db, user, "factura", f.id, "reabrir", None, motivo, factura_id=f.id)
    return {"estado": f.estado, "version": f.version}


def cancelar(db: Session, user: Usuario, factura_id: int, motivo: str | None) -> dict:
    exigir(user, "factura.cancelar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    if f.estado == "CANCELADA":
        raise ErrorNegocio("La factura ya está cancelada.", 409, "no_editable")
    if user.rol == "proveedor" and f.estado != "BORRADOR":
        raise ErrorNegocio("Solo puedes cancelar facturas en borrador. Pide al equipo interno que la cancele.",
                           403, "sin_permiso")
    if f.estado != "BORRADOR":
        motivo = requerir_motivo(motivo, "cancelar la factura")
    confirmados = [pl.numero for pl in f.packing_lists if pl.asignacion == "CONFIRMADA" and pl.estado != "CANCELADO"]
    if confirmados:
        raise ErrorNegocio(
            "Primero quita de su unidad de carga los PL confirmados: " + ", ".join(confirmados) + ".",
            409, "pl_en_transporte",
        )
    for pl in f.packing_lists:
        if pl.estado != "CANCELADO":
            pl.estado = "CANCELADO"
            pl.unidad_carga_id = None
            pl.asignacion = None
            tocar(pl)
    f.estado = "CANCELADA"
    tocar(f)
    registrar(db, user, "factura", f.id, "cancelar", None, motivo, factura_id=f.id)
    return {"estado": f.estado}


# ---- Consultas --------------------------------------------------------------
def resumen_distribucion(db: Session, factura_ids) -> dict[int, dict]:
    ids = list(set(factura_ids))
    if not ids:
        return {}
    res = {i: {"facturado": 0, "asignado": 0, "pls": 0, "pls_finalizados": 0, "pls_confirmados": 0,
               "importe": 0.0, "lineas": 0} for i in ids}
    for fid, cant, imp, n in db.execute(
        select(FacturaLinea.factura_id, func.sum(FacturaLinea.cantidad),
               func.sum(FacturaLinea.cantidad * FacturaLinea.precio_unitario), func.count(FacturaLinea.id))
        .where(FacturaLinea.factura_id.in_(ids)).group_by(FacturaLinea.factura_id)
    ).all():
        res[fid].update(facturado=int(cant or 0), importe=round(float(imp or 0), 2), lineas=n)
    for fid, cant in db.execute(
        select(PackingList.factura_id, func.sum(PLLinea.cantidad))
        .join(PLLinea, PLLinea.pl_id == PackingList.id)
        .where(PackingList.factura_id.in_(ids), PackingList.estado != "CANCELADO")
        .group_by(PackingList.factura_id)
    ).all():
        res[fid]["asignado"] = int(cant or 0)
    for pl in db.scalars(
        select(PackingList).where(PackingList.factura_id.in_(ids), PackingList.estado != "CANCELADO")
    ).all():
        r = res[pl.factura_id]
        r["pls"] += 1
        r["pls_finalizados"] += pl.estado == "FINALIZADO"
        r["pls_confirmados"] += pl.asignacion == "CONFIRMADA"
    return res


def _lista_para_transporte(f: Factura, r: dict) -> bool:
    return (
        f.estado == "FINALIZADA"
        and r["facturado"] > 0
        and r["asignado"] == r["facturado"]
        and r["pls"] > 0
        and r["pls"] == r["pls_finalizados"]
    )


def listar_facturas(
    db: Session,
    user: Usuario,
    proveedor_id: int | None = None,
    estado: str | None = None,
    q: str | None = None,
    vista: str | None = None,
    page: int = 1,
    size: int = 25,
    orden: str | None = None,
) -> dict:
    prov = proveedor_filtro(user, proveedor_id)
    consulta = select(Factura).join(Proveedor, Proveedor.id == Factura.proveedor_id)
    if prov:
        consulta = consulta.where(Factura.proveedor_id == prov)
    if estado:
        consulta = consulta.where(Factura.estado == estado)
    if q:
        patron = f"%{q.strip()}%"
        sub = select(FacturaLinea.factura_id).where(FacturaLinea.oc_numero.ilike(patron))
        consulta = consulta.where((Factura.numero.ilike(patron)) | Factura.id.in_(sub))
    if vista == "editables":
        consulta = consulta.where(Factura.estado.in_(EDITABLE_FACTURA))
    elif vista == "pl_incompletos":
        consulta = consulta.where(Factura.id.in_(
            select(PackingList.factura_id).where(PackingList.estado.in_(EDITABLE_PL))))
    elif vista == "pl_sin_unidad":
        consulta = consulta.where(Factura.id.in_(
            select(PackingList.factura_id).where(PackingList.estado == "FINALIZADO",
                                                 PackingList.unidad_carga_id.is_(None))))
    elif vista == "borradores_antiguos":
        limite = ahora() - timedelta(days=settings.DIAS_ALERTA_BORRADOR)
        consulta = consulta.where(Factura.estado == "BORRADOR", Factura.creado_en < limite)
    elif vista == "lista_transporte":
        consulta = consulta.where(Factura.estado == "FINALIZADA")
    col, _, direccion = (orden or "").partition(":")
    expr = {"nombre": Factura.numero, "fecha": Factura.fecha, "estado": Factura.estado,
            "proveedor": Proveedor.nombre, "actualizado": Factura.actualizado_en}.get(col)
    if expr is not None:
        consulta = consulta.order_by(expr.desc().nullslast() if direccion == "desc" else expr.asc().nullslast(), Factura.id)
    else:
        consulta = consulta.order_by(Factura.actualizado_en.desc())

    if vista == "lista_transporte":
        todas = list(db.scalars(consulta).all())
        res = resumen_distribucion(db, [f.id for f in todas])
        todas = [f for f in todas if _lista_para_transporte(f, res[f.id]) and res[f.id]["pls_confirmados"] < res[f.id]["pls"]]
        total = len(todas)
        facturas = todas[(page - 1) * size: page * size]
    else:
        total = db.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        facturas = list(db.scalars(consulta.offset((page - 1) * size).limit(size)).all())
        res = resumen_distribucion(db, [f.id for f in facturas])

    items = []
    for f in facturas:
        r = res[f.id]
        items.append({
            "id": f.id,
            "nombre": nombre_factura(f),
            "numero": f.numero,
            "proveedor_id": f.proveedor_id,
            "proveedor": f.proveedor.nombre,
            "fecha": f.fecha,
            "estado": f.estado,
            "moneda": f.moneda,
            "centro": f.centro,
            "sociedad": f.sociedad,
            "importe": r["importe"],
            "lineas": r["lineas"],
            "facturado": r["facturado"],
            "asignado": r["asignado"],
            "pls": r["pls"],
            "pls_finalizados": r["pls_finalizados"],
            "pls_confirmados": r["pls_confirmados"],
            "lista_transporte": _lista_para_transporte(f, r),
            "creado_en": f.creado_en,
            "actualizado_en": f.actualizado_en,
        })
    return {"items": items, "total": total, "page": page, "size": size}


def _info_transporte(pl: PackingList) -> dict | None:
    u = pl.unidad
    if not u:
        return None
    e = u.embarque
    return {
        "unidad_id": u.id,
        "unidad": u.numero or u.etiqueta,
        "tipo": u.tipo,
        "asignacion": pl.asignacion,
        "embarque_id": e.id,
        "embarque": e.codigo,
        "documento": e.documento_numero,
        "estado": e.estado,
        "etd": e.etd,
        "eta": e.eta,
        "salida_real": e.salida_real,
        "arribo_real": e.arribo_real,
        "ultimo_evento": (
            {"tipo": e.eventos[-1].tipo, "fecha": e.eventos[-1].fecha, "ubicacion": e.eventos[-1].ubicacion}
            if e.eventos else None
        ),
    }


def detalle_factura(db: Session, user: Usuario, factura_id: int) -> dict:
    f = cargar_factura(db, user, factura_id)
    pls_activos = [pl for pl in f.packing_lists if pl.estado != "CANCELADO"]
    en_pl: dict[int, int] = {}
    empacado: dict[int, int] = {}
    for pl in pls_activos:
        for pll in pl.lineas:
            en_pl[pll.factura_linea_id] = en_pl.get(pll.factura_linea_id, 0) + pll.cantidad
            empacado[pll.factura_linea_id] = empacado.get(pll.factura_linea_id, 0) + cubierto(pll)

    lineas = []
    por_unidad: dict[str, dict] = {}
    importe = 0.0
    for l in f.lineas:
        a = en_pl.get(l.id, 0)
        e = empacado.get(l.id, 0)
        total = round(l.cantidad * l.precio_unitario, 2)
        importe += total
        u = por_unidad.setdefault(l.unidad, {"facturado": 0, "en_pl": 0, "empacado": 0})
        u["facturado"] += l.cantidad
        u["en_pl"] += a
        u["empacado"] += e
        lineas.append({
            "id": l.id,
            "posicion_oc_id": l.posicion_oc_id,
            "oc_numero": l.oc_numero,
            "almacen": l.almacen,
            "posicion": l.posicion,
            "codigo_sap": l.codigo_sap,
            "upc": l.upc,
            "estilo": l.estilo,
            "color": l.color,
            "talla": l.talla,
            "descripcion": l.descripcion,
            "unidad": l.unidad,
            "marca": l.marca,
            "tipo_empaque": l.tipo_empaque,
            "casepack": l.casepack,
            "prepack": l.prepack,
            "unidades_por_caja": l.unidades_por_caja,
            "cantidad": l.cantidad,
            "cantidad_oc": l.posicion_oc.cantidad,
            "precio_unitario": l.precio_unitario,
            "precio_oc": l.precio_oc,
            "motivo_precio": l.motivo_precio,
            "total": total,
            "pais_origen": l.pais_origen,
            "partida_arancelaria": l.partida_arancelaria,
            "descripcion_comercial": l.descripcion_comercial,
            "en_pl": a,
            "sin_asignar": l.cantidad - a,
            "empacado": e,
            "pendiente_empaque": a - e,
        })

    r = resumen_distribucion(db, [f.id])[f.id]
    editable = f.estado in EDITABLE_FACTURA
    permisos_finalizar = user.rol in ("admin", "interno") or settings.PROVEEDOR_PUEDE_FINALIZAR
    return {
        "id": f.id,
        "nombre": nombre_factura(f),
        "numero": f.numero,
        "fecha": f.fecha,
        "estado": f.estado,
        "version": f.version,
        "proveedor_id": f.proveedor_id,
        "proveedor": f.proveedor.nombre,
        "moneda": f.moneda,
        "incoterm": f.incoterm,
        "sociedad": f.sociedad,
        "centro": f.centro,
        "centro_destino": f.centro_destino,
        **partes(db, f.sociedad, f.centro, f.centro_destino),
        "condiciones": f.condiciones,
        "observaciones": f.observaciones,
        "creado_en": f.creado_en,
        "actualizado_en": f.actualizado_en,
        "finalizado_en": f.finalizado_en,
        "lineas": lineas,
        "totales": {"importe": round(importe, 2), "por_unidad": por_unidad},
        "lista_transporte": _lista_para_transporte(f, r),
        "pendientes": validar_factura(db, f) if editable else [],
        "packing_lists": [
            {
                "id": pl.id,
                "numero": pl.numero,
                "estado": pl.estado,
                "version": pl.version,
                "totales": totales_pl(pl),
                "transporte": _info_transporte(pl),
            }
            for pl in f.packing_lists
        ],
        "puede": {
            "editar": editable,
            "finalizar": editable and permisos_finalizar,
            "reabrir": f.estado == "FINALIZADA" and es_interno(user),
            "cancelar": f.estado != "CANCELADA" and (es_interno(user) or f.estado == "BORRADOR"),
            "crear_pl": f.estado != "CANCELADA" and any(l["sin_asignar"] > 0 for l in lineas),
        },
    }


def historial_factura(db: Session, user: Usuario, factura_id: int) -> list[dict]:
    cargar_factura(db, user, factura_id)
    filas = db.scalars(
        select(Historial).where(Historial.factura_id == factura_id).order_by(Historial.fecha.desc(), Historial.id.desc())
    ).all()
    return [
        {
            "id": h.id,
            "fecha": h.fecha,
            "entidad": h.entidad,
            "entidad_id": h.entidad_id,
            "accion": h.accion,
            "detalle": h.detalle,
            "motivo": h.motivo,
            "usuario": h.usuario.nombre if h.usuario else None,
        }
        for h in filas
    ]


# ---- Archivos ---------------------------------------------------------------
def subir_archivo(db: Session, user: Usuario, factura_id: int, nombre: str, contenido: bytes, tipo: str) -> dict:
    exigir(user, "factura.editar")
    f = cargar_factura(db, user, factura_id)
    if f.estado == "CANCELADA":
        raise ErrorNegocio("No se pueden adjuntar archivos a una factura cancelada.", 409, "no_editable")
    if len(contenido) > 20 * 1024 * 1024:
        raise ErrorNegocio("El archivo supera 20 MB.", 413, "archivo_grande")
    carpeta = os.path.join(settings.UPLOAD_DIR, str(f.id))
    os.makedirs(carpeta, exist_ok=True)
    seguro = "".join(c for c in os.path.basename(nombre) if c.isalnum() or c in "._- ") or "archivo"
    ruta = os.path.join(carpeta, f"{uuid.uuid4().hex}_{seguro}")
    with open(ruta, "wb") as fh:
        fh.write(contenido)
    a = Archivo(factura_id=f.id, tipo=tipo, nombre=seguro, ruta=ruta, tamano=len(contenido), subido_por=user.id)
    db.add(a)
    db.flush()
    registrar(db, user, "factura", f.id, "adjuntar_archivo", {"archivo": seguro, "tipo": tipo}, factura_id=f.id)
    return {"id": a.id}


def listar_archivos(db: Session, user: Usuario, factura_id: int) -> list[dict]:
    cargar_factura(db, user, factura_id)
    return [
        {"id": a.id, "tipo": a.tipo, "nombre": a.nombre, "tamano": a.tamano, "subido_en": a.subido_en}
        for a in db.scalars(select(Archivo).where(Archivo.factura_id == factura_id).order_by(Archivo.id)).all()
    ]


def obtener_archivo(db: Session, user: Usuario, archivo_id: int) -> Archivo:
    a = db.get(Archivo, archivo_id)
    if not a:
        raise ErrorNegocio("El archivo no existe.", 404, "no_encontrado")
    cargar_factura(db, user, a.factura_id)
    return a
