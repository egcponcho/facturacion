
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.core import campos_propios, dinero
from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.core.estados import FACTURA, OC
from app.esquemas import FacturaCrear, PosicionCantidad
from app.modelos import (
    Factura,
    FacturaLinea,
    OrdenCompra,
    PosicionOC,
    Usuario,
    ahora,
)
from app.modulos.acceso.permisos import (
    asegurar_proveedor,
    exige_datos_aduana,
    exigir,
    proveedor_filtro,
)
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comex import servicio as comex
from app.modulos.comun.formato import cant_txt
from app.modulos.comun.historial import registrar, requerir_motivo, tocar, verificar_version
from app.modulos.facturacion.cantidades import (
    asignado_por_linea,
    error_en_linea,
    facturado_por_posicion,
    facturas_por_posicion,
    nombre_factura,
)
from app.modulos.facturacion.estados import EDITABLE_FACTURA, EDITABLE_PL, ESTADO_TXT

ETIQUETAS = {
    "sociedad": "companies",
    "moneda": "currencies",
    "centro": "plants",
    "incoterm": "incoterms",
    "centro_destino": "destination plants",
    "puerto_despacho": "ports of loading",
    "pais_origen": "countries of origin",
}


# ---- Carga y validaciones de estado -----------------------------------------
def cargar_factura(db: Session, user: Usuario, factura_id: int, bloquear: bool = False) -> Factura:
    exigir(user, "factura.ver")
    consulta = select(Factura).where(Factura.id == factura_id)
    if bloquear:
        consulta = consulta.with_for_update()
    f = db.scalar(consulta)
    if not f:
        raise ErrorNegocio("The invoice does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, f.proveedor_id, f.sociedad)
    return f


def exigir_editable(f: Factura) -> None:
    if f.estado not in EDITABLE_FACTURA:
        raise ErrorNegocio(
            f"The invoice is {ESTADO_TXT[f.estado]} and cannot be edited."
            + (" Reopen it to make changes." if f.estado == "FINALIZADA" else ""),
            409,
            "no_editable",
        )


def _ref_linea(l: FacturaLinea) -> str:
    variante = catalogo.texto(l.variante)
    return f"PO {l.oc_numero} line {l.posicion} ({l.codigo_articulo}{' · ' + variante if variante else ''})"


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
            f"Invoice {numero} already exists for this supplier.", 409, "numero_duplicado"
        )


# ---- Selección de posiciones (OC completas o parciales) ---------------------
def _preparar_posiciones(
    db: Session,
    user: Usuario,
    solicitudes: list[PosicionCantidad],
    proveedor_id: frozenset | None = None,
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
        raise ErrorNegocio("Some PO lines no longer exist. Reload the list.", 404, "no_encontrado")
    ocs = {p.oc_id: p.oc for p in posiciones}

    proveedores = {oc.proveedor_id for oc in ocs.values()}
    if factura:
        proveedores.add(factura.proveedor_id)
    if len(proveedores) > 1:
        raise ErrorNegocio("An invoice can only have PO lines from one supplier.", 422, "proveedor_mixto")
    prov = next(iter(proveedores))
    if proveedor_id and prov not in proveedor_id:  # el proveedor elegido (o los del alcance)
        raise ErrorNegocio("The PO lines do not belong to the selected supplier.", 422, "proveedor_mixto")
    asegurar_proveedor(user, prov, next(iter(ocs.values())).sociedad)

    errores: list[dict] = []
    advertencias: list[str] = []
    # Campos de la OC que no se mezclan en una factura (Configuración → Empresa)
    bloquean, avisan = list(regla("COMPATIBILIDAD_BLOQUEANTE")), list(regla("COMPATIBILIDAD_ADVERTENCIA"))
    for campo in [c for c in bloquean + avisan if c in ETIQUETAS]:
        valores = {getattr(oc, campo) for oc in ocs.values()}
        if factura:
            valores.add(getattr(factura, campo))
        valores.discard(None)
        if len(valores) > 1:
            texto = f"You are mixing different {ETIQUETAS[campo]}: {', '.join(sorted(map(str, valores)))}."
            if campo in bloquean:
                errores.append({"mensaje": texto + " Split them into separate invoices."})
            else:
                advertencias.append(texto)

    ids = list(pedidas)
    facturado = facturado_por_posicion(db, ids)
    activas = facturas_por_posicion(db, ids)
    for p in posiciones:
        oc = ocs[p.oc_id]
        ref = f"PO {oc.numero} line {p.posicion}"
        cantidad = pedidas[p.id]
        if not OC.puede("facturar", oc.estado):
            errores.append({"posicion_id": p.id, "mensaje": f"{ref}: the PO is {OC.texto(oc.estado)}: it cannot be invoiced."})
            continue
        if not oc.liberada:
            errores.append({"posicion_id": p.id, "mensaje": f"{ref}: the PO is not released."})
            continue
        if p.bloqueada:
            errores.append({"posicion_id": p.id, "mensaje": f"{ref}: {p.motivo_bloqueo or 'line blocked'}."})
            continue
        if not regla("POSICION_EN_VARIAS_FACTURAS"):
            otras = [a for a in activas.get(p.id, []) if not factura or a["id"] != factura.id]
            if otras:
                errores.append(
                    {
                        "posicion_id": p.id,
                        "mensaje": f"{ref} is already in {otras[0]['nombre']}. "
                        "Add the balance to that invoice or remove it from there first.",
                    }
                )
                continue
        faltan = [x for x, v in (("company (bill to)", oc.sociedad), ("currency", oc.moneda), ("price", p.precio))
                  if v in (None, "")]
        if faltan:
            errores.append({"posicion_id": p.id, "mensaje": f"{ref}: complete the PO before invoicing; missing {', '.join(faltan)}."})
            continue
        if (msg := error_en_linea(p, cantidad)):
            errores.append({"posicion_id": p.id, "mensaje": f"{ref}: {msg}"})
            continue
        disponible = p.cantidad - facturado.get(p.id, 0)
        if cantidad > disponible:
            errores.append(
                {
                    "posicion_id": p.id,
                    "mensaje": f"{ref}: only {cant_txt(max(disponible, 0), p.unidad)} available "
                    f"and you asked for {cantidad}.",
                }
            )
    if errores:
        raise ErrorNegocio("Some PO lines could not be added.", 422, "validacion", errores)
    return posiciones, ocs, pedidas, advertencias


def _nueva_linea(p: PosicionOC, oc: OrdenCompra, cantidad: int) -> FacturaLinea:
    # Partida, origen y descripción aduanera salen de la ficha del producto (comercio exterior); la
    # variante y los atributos del producto, de la foto de la línea de la OC
    db = object_session(p)
    ficha = comex.de_articulos(db, [p.articulo_id]).get(p.articulo_id)
    marca = catalogo.marca(db, p.atributos)
    return FacturaLinea(
        posicion_oc_id=p.id,
        cantidad=cantidad,
        precio_unitario=p.precio,
        precio_oc=p.precio,
        oc_numero=oc.numero,
        posicion=p.posicion,
        almacen=p.almacen,
        codigo_articulo=p.codigo_articulo,
        codigo_barras=p.codigo_barras,
        variante=dict(p.variante) if p.variante else None,
        atributos=dict(p.atributos) if p.atributos else None,
        descripcion=p.descripcion,
        unidad=p.unidad,
        tipo_empaque=p.tipo_empaque,
        casepack=p.casepack,
        inner_pack=p.inner_pack,
        codigo_pack=p.codigo_pack,
        unidades_por_caja=p.unidades_por_caja,
        receta_id=p.receta_id,
        receta_foto=p.receta_foto,
        centro_destino=oc.centro_destino,
        pais_origen=p.pais_origen or (ficha.pais_origen if ficha else None),
        partida_arancelaria=ficha.partida if ficha else None,  # 6 dígitos: el destino es solo proyectado
        # Descripción aduanera del artículo, sin la marca (va en su propia columna)
        descripcion_comercial=comex.sin_marca((ficha.descripcion_aduana or ficha.descripcion_comercial) if ficha else None, marca)
        or comex.sin_marca(p.descripcion, marca),
    )


def completar_aduana(db: Session, f: Factura) -> None:
    """Llena la partida y el origen que falten en las líneas con el producto
    ya clasificado (por ejemplo, si se aprobó después de facturar)."""
    faltan = [l for l in f.lineas if not (l.partida_arancelaria and l.pais_origen)]
    fichas = comex.de_articulos(db, [l.posicion_oc.articulo_id for l in faltan])
    for l in faltan:
        ficha = fichas.get(l.posicion_oc.articulo_id)
        if ficha is None:
            continue
        if not l.partida_arancelaria:
            l.partida_arancelaria = ficha.partida
        if not l.pais_origen:
            l.pais_origen = ficha.pais_origen


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
    verificar_version(f, version, "invoice")
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


# ---- Estados ----------------------------------------------------------------
def validar_factura(db: Session, f: Factura) -> list[dict]:
    errores = []
    for c in campos_propios.definiciones("facturas"):
        if c["obligatorio"] and (f.extra or {}).get(c["clave"]) in (None, ""):
            errores.append({"campo": f"extra.{c['clave']}", "mensaje": f"{c['etiqueta']} is missing."})
    if not f.numero:
        errores.append({"campo": "numero", "mensaje": "The invoice number is missing."})
    if not f.fecha:
        errores.append({"campo": "fecha", "mensaje": "The invoice date is missing."})
    if not f.incoterm:
        errores.append({"campo": "incoterm", "mensaje": "The incoterm (delivery terms) is missing."})
    if not f.lineas:
        errores.append({"mensaje": "The invoice has no lines."})
    facturado = facturado_por_posicion(db, [l.posicion_oc_id for l in f.lineas])
    fichas = comex.de_articulos(db, [l.posicion_oc.articulo_id for l in f.lineas])
    productos = catalogo.productos(db, [x.producto_id for x in fichas.values()])
    for l in f.lineas:
        ref = _ref_linea(l)
        if l.precio_unitario <= 0:
            errores.append({"linea_id": l.id, "mensaje": f"{ref}: the price must be greater than zero."})
        if not dinero.iguales(l.precio_unitario, l.precio_oc) and not l.motivo_precio:
            errores.append({"linea_id": l.id, "mensaje": f"{ref}: the reason for the price change is missing."})
        if not (l.descripcion_comercial or "").strip():
            errores.append({"linea_id": l.id, "mensaje": f"{ref}: the commercial description of the goods is missing."})
        if exige_datos_aduana():
            if not l.pais_origen:
                errores.append({"linea_id": l.id, "mensaje": f"{ref}: the country of origin is missing."})
            if not l.partida_arancelaria:
                ficha = fichas.get(l.posicion_oc.articulo_id)
                if ficha and not ficha.aprobado:
                    prod = productos.get(ficha.producto_id)
                    nombre = (prod.codigo or prod.nombre) if prod else ficha.producto_id
                    errores.append({"linea_id": l.id, "codigo": "sin_clasificar", "producto_id": ficha.producto_id, "mensaje":
                                    f"{ref}: the HS code is missing: product {nombre} is not "
                                    "classified yet (Products)."})
                else:
                    errores.append({"linea_id": l.id, "mensaje": f"{ref}: the HS code is missing."})
        p = l.posicion_oc
        if facturado.get(p.id, 0) > p.cantidad:
            errores.append({"linea_id": l.id, "mensaje":
                f"{ref}: the invoiced quantity ({facturado[p.id]}) exceeds the current PO quantity ({p.cantidad})."})
        if p.bloqueada:
            errores.append({"linea_id": l.id, "mensaje": f"{ref}: the line is blocked on the PO."})
    return errores


def finalizar(db: Session, user: Usuario, factura_id: int, version: int, incluir_pls: bool) -> dict:
    from app.modulos.empaque.estados_pl import validar_pl  # evitar import circular

    exigir(user, "factura.finalizar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    FACTURA.exigir("finalizar", f.estado, "no_editable")
    verificar_version(f, version, "invoice")
    completar_aduana(db, f)
    errores = validar_factura(db, f)
    pls = []
    if incluir_pls:
        exigir(user, "pl.finalizar")
        asignado = asignado_por_linea(db, [l.id for l in f.lineas])
        for l in f.lineas:
            falta = l.cantidad - asignado.get(l.id, 0)
            if falta > 0:
                errores.append({"linea_id": l.id, "mensaje":
                    f"{_ref_linea(l)}: {cant_txt(falta, l.unidad)} not assigned to a packing list."})
        pls = [pl for pl in f.packing_lists if pl.estado in EDITABLE_PL]
        for pl in pls:
            errores += [{**e, "mensaje": f"{pl.numero}: {e['mensaje']}"} for e in validar_pl(pl)]
    if errores:
        raise ErrorNegocio("Some data is missing before finalizing.", 422, "pendientes", errores)
    f.estado = "FINALIZADA"
    f.finalizado_en = ahora()
    tocar(f)
    db.flush()
    registrar(db, user, "factura", f.id, "finalizar", {"con_pl": [pl.numero for pl in pls]}, factura_id=f.id)
    for pl in pls:
        pl.estado, pl.finalizado_en = "FINALIZADO", ahora()
        tocar(pl)
        registrar(db, user, "packing_list", pl.id, "finalizar", None, factura_id=f.id)
    return {"estado": f.estado, "version": f.version}


def reabrir(db: Session, user: Usuario, factura_id: int, motivo: str | None) -> dict:
    exigir(user, "factura.reabrir")
    motivo = requerir_motivo(motivo, "reopen the invoice")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    FACTURA.exigir("reabrir", f.estado, "no_editable")
    viajando = [pl.numero for pl in f.packing_lists if pl.unidad and pl.unidad.embarque.estado != "PLANIFICADO"]
    if viajando:
        raise ErrorNegocio(f"Its packing lists are already traveling: {', '.join(viajando)}. It cannot be reopened.",
                           409, "embarque_cerrado")
    # Solo lo finalizado va en un embarque: al reabrirla, sus PL salen de la unidad de carga
    quitados = []
    for pl in f.packing_lists:
        if pl.unidad_carga_id and pl.estado != "CANCELADO":
            quitados.append(f"{pl.numero} ({pl.unidad.numero or pl.unidad.etiqueta})")
            pl.unidad_carga_id, pl.asignacion, pl.recolectado_en = None, None, None
    f.estado = "EN_CORRECCION"
    tocar(f)
    nota = f"Removed from their load unit: {', '.join(quitados)}. Add them again once finalized." if quitados else None
    registrar(db, user, "factura", f.id, "reabrir", {"nota": nota} if nota else None, motivo, factura_id=f.id)
    return {"estado": f.estado, "version": f.version, "nota": nota}


def cancelar(db: Session, user: Usuario, factura_id: int, motivo: str | None) -> dict:
    exigir(user, "factura.cancelar")
    f = cargar_factura(db, user, factura_id, bloquear=True)
    FACTURA.exigir("cancelar", f.estado, "no_editable")
    if user.rol == "proveedor" and f.estado != "BORRADOR":
        raise ErrorNegocio("You can only cancel draft invoices. Ask the internal team to cancel it.",
                           403, "sin_permiso")
    if f.estado != "BORRADOR":
        motivo = requerir_motivo(motivo, "cancel the invoice")
    confirmados = [pl.numero for pl in f.packing_lists if pl.asignacion == "CONFIRMADA" and pl.estado != "CANCELADO"]
    if confirmados:
        raise ErrorNegocio(
            "First remove the confirmed PLs from their load unit: " + ", ".join(confirmados) + ".",
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


