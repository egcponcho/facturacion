"""Ciclo de vida de la orden de compra (docs/FLUJOS.md §1).

Dos dimensiones que no se mezclan:
- Estado del documento (`OrdenCompra.estado`, máquina `core.estados.OC`):
  borrador → (aprobación) → aprobada → cerrada, o cancelada.
- Avance logístico (`avance`): se calcula de las cantidades facturadas,
  embarcadas y recibidas; una OC aprobada puede estar «en tránsito parcial».

Creación en pasos (asistente): el borrador guarda lo que se va llenando sin
exigir nada; cada paso se valida en el acto (`validar_paso`) y el envío pasa
las líneas por la misma validación que una carga del ERP
(`ordenes.aplicar_importacion`), así hay una sola regla para ambos caminos.
"""
import re
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import campos_propios, listas
from app.core.empresa import configuracion_actual, regla
from app.core.errores import ErrorNegocio
from app.core.estados import OC
from app.modelos import (
    AprobacionOC,
    Articulo,
    Centro,
    Embarque,
    Factura,
    FacturaLinea,
    Historial,
    ImportacionOC,
    OrdenCompra,
    PackingList,
    Pais,
    PLLinea,
    PosicionOC,
    Proveedor,
    Puerto,
    RecepcionLinea,
    Rol,
    Sociedad,
    UnidadCarga,
    Usuario,
    ahora,
)
from app.modulos.acceso.permisos import asegurar_proveedor, exigir, proveedor_filtro, tiene
from app.modulos.compras import liberaciones
from app.modulos.comun.historial import registrar, requerir_motivo, tocar, verificar_version

# Pasos del asistente y los datos que pide cada uno
PASOS = [
    ("general", "General data"),
    ("articulos", "Items and quantities"),
    ("condiciones", "Commercial terms"),
    ("logistica", "Logistics and dates"),
    ("documentacion", "Documentation and extras"),
    ("revision", "Review and send"),
]
CABECERA = ("proveedor", "oc", "sociedad", "fecha_oc", "moneda", "incoterm", "condicion_pago", "centro", "centro_destino",
            "puerto_despacho", "pais_origen", "pais_procedencia", "fecha_xf", "fecha_tienda", "notas")
LINEA = ("codigo_sap", "cantidad", "unidad", "precio", "casepack", "inner_pack", "almacen", "fecha_entrega")
# Datos del asistente → nombre del dato en la configuración de obligatorios
OBLIGABLES = {"fecha_oc": "fecha", "incoterm": "incoterm", "condicion_pago": "condicion_pago", "centro": "centro",
              "centro_destino": "centro_destino", "puerto_despacho": "puerto_despacho", "pais_origen": "pais_origen",
              "fecha_tienda": "fecha_tienda"}
AVANCES = {"SIN_FACTURAR": "Not invoiced", "FACTURADA_PARCIAL": "Partly invoiced", "FACTURADA": "Invoiced",
           "EMBARCADA_PARCIAL": "Partly shipped", "EN_TRANSITO": "In transit", "RECIBIDA_PARCIAL": "Partly received",
           "RECIBIDA": "Received"}


# ---- Carga y permisos ---------------------------------------------------------------
def cargar(db: Session, user: Usuario, oc_id: int) -> OrdenCompra:
    exigir(user, "oc.ver")
    oc = db.get(OrdenCompra, oc_id)
    if not oc:
        raise ErrorNegocio("The purchase order does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, oc.proveedor_id, oc.sociedad)
    return oc


def _texto(v) -> str:
    return "" if v is None else str(v).strip()


def _fecha(v) -> date | None:
    try:
        return date.fromisoformat(_texto(v)[:10]) if _texto(v) else None
    except ValueError:
        return None


def _numero(v) -> float | None:
    try:
        return float(_texto(v).replace(",", "")) if _texto(v) else None
    except ValueError:
        return None


# ---- Borrador -------------------------------------------------------------------------
def crear_borrador(db: Session, user: Usuario, cabecera: dict) -> dict:
    """Primer paso del asistente: con proveedor y número ya existe el borrador."""
    exigir(user, "oc.editar")
    cab = {k: cabecera.get(k) for k in CABECERA if k in cabecera}
    errores = validar_paso(db, user, {"cabecera": cab, "lineas": []}, "general", None)
    if any(e["campo"] in ("proveedor", "oc") for e in errores):
        raise ErrorNegocio("Check the general data.", 422, "validacion", errores)
    prov = db.scalar(select(Proveedor).where(Proveedor.codigo == _texto(cab["proveedor"]).upper()))
    lib = liberaciones.de(db)
    oc = OrdenCompra(proveedor_id=prov.id, numero=_texto(cab["oc"]), estado="BORRADOR", origen="PLATAFORMA",
                     liberacion_comercial=lib.comercial.sin_liberar() or "", liberacion_logistica=lib.logistica.sin_liberar() or "",
                     liberada=False, creada_por=user.id, borrador={"cabecera": cab, "lineas": []})
    _copiar_cabecera(oc, cab)
    db.add(oc)
    db.flush()
    registrar(db, user, "orden", oc.id, "borrador_creado", {"numero": oc.numero})
    return detalle(db, user, oc.id)


def _copiar_cabecera(oc: OrdenCompra, cab: dict) -> None:
    """Lo que ya se puede mostrar del borrador en la lista de OCs."""
    oc.sociedad = _texto(cab.get("sociedad")).upper() or None
    oc.moneda = _texto(cab.get("moneda")).upper() or None
    oc.fecha = _fecha(cab.get("fecha_oc"))
    oc.fecha_xf = oc.fecha_xf_original = _fecha(cab.get("fecha_xf"))
    oc.fecha_tienda = _fecha(cab.get("fecha_tienda"))
    oc.condicion_pago = _texto(cab.get("condicion_pago")).upper() or None
    oc.notas = _texto(cab.get("notas"))[:2000] or None


def guardar_borrador(db: Session, user: Usuario, oc_id: int, datos: dict) -> dict:
    """Guarda lo que lleva el asistente, aunque falten datos (se valida al
    enviar). Una OC rechazada vuelve a borrador al editarla."""
    exigir(user, "oc.editar")
    oc = cargar(db, user, oc_id)
    OC.exigir("editar", oc.estado)
    verificar_version(oc, datos.get("version"), "purchase order")
    borrador = dict(oc.borrador or _borrador_de(oc))
    if "cabecera" in datos:
        cab = {**borrador.get("cabecera", {}), **{k: v for k, v in (datos["cabecera"] or {}).items() if k in CABECERA or k == "extra"}}
        nuevo = _texto(cab.get("oc"))
        if nuevo and nuevo != oc.numero:
            if db.scalar(select(OrdenCompra.id).where(OrdenCompra.proveedor_id == oc.proveedor_id,
                                                      OrdenCompra.numero == nuevo, OrdenCompra.id != oc.id)):
                raise ErrorNegocio(f"PO {nuevo} already exists for this supplier.", 409, "duplicado",
                                   [{"campo": "oc", "mensaje": f"PO {nuevo} already exists for this supplier."}])
            oc.numero = nuevo[:40]
        cab["proveedor"] = oc.proveedor.codigo  # el proveedor no cambia: se crea otra OC
        borrador["cabecera"] = cab
        _copiar_cabecera(oc, cab)
    if "lineas" in datos:
        borrador["lineas"] = [{k: x.get(k) for k in LINEA} for x in (datos["lineas"] or [])][:500]
    if oc.estado == "RECHAZADA":
        oc.estado = "BORRADOR"
        registrar(db, user, "orden", oc.id, "vuelve_a_borrador", None)
    oc.borrador = borrador
    tocar(oc)
    return detalle(db, user, oc.id)


def _borrador_de(oc: OrdenCompra) -> dict:
    """El borrador de una OC que ya tenía líneas (p. ej. rechazada)."""
    cab = {"proveedor": oc.proveedor.codigo, "oc": oc.numero, "sociedad": oc.sociedad, "fecha_oc": oc.fecha,
           "moneda": oc.moneda, "incoterm": oc.incoterm, "condicion_pago": oc.condicion_pago, "centro": oc.centro,
           "centro_destino": oc.centro_destino, "puerto_despacho": oc.puerto_despacho, "pais_origen": oc.pais_origen,
           "pais_procedencia": oc.pais_procedencia, "fecha_xf": oc.fecha_xf, "fecha_tienda": oc.fecha_tienda,
           "notas": oc.notas, "extra": oc.extra or {}}
    lineas = [{"codigo_sap": p.codigo_sap, "cantidad": p.cantidad, "unidad": p.unidad, "precio": p.precio,
               "casepack": p.casepack, "inner_pack": p.inner_pack, "almacen": p.almacen, "fecha_entrega": p.fecha_entrega}
              for p in oc.posiciones]
    return {"cabecera": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in cab.items()}, "lineas": lineas}


# ---- Validación por paso ---------------------------------------------------------------
def _obligatorios() -> set[str]:
    return set((configuracion_actual().get("obligatorios") or {}).get("orden") or [])


def validar_paso(db: Session, user: Usuario, borrador: dict, paso: str, oc_id: int | None) -> list[dict]:
    """Errores de un paso del asistente, campo por campo. «revision» revisa todos."""
    if paso == "revision":
        return [e for p, _ in PASOS[:-1] for e in validar_paso(db, user, borrador, p, oc_id)]
    cab, lineas = borrador.get("cabecera") or {}, borrador.get("lineas") or []
    obligatorios = _obligatorios()
    err: list[dict] = []

    def falta(campo: str, mensaje: str) -> None:
        err.append({"paso": paso, "campo": campo, "mensaje": mensaje})

    def requerido(campo: str, mensaje: str, siempre: bool = False) -> bool:
        # El mensaje va completo (no «{dato} is required.»): en español cada dato concuerda en género
        if (siempre or OBLIGABLES.get(campo) in obligatorios) and not _texto(cab.get(campo)):
            falta(campo, mensaje)
            return False
        return True

    def de_lista(campo: str, lista: str, etiqueta: str) -> None:
        v = _texto(cab.get(campo)).upper()
        if v and v not in listas.codigos(lista):
            falta(campo, f"{etiqueta} {v} is not in the list.")

    def existe(campo: str, modelo, etiqueta: str) -> None:
        v = _texto(cab.get(campo)).upper()
        if v and not db.scalar(select(modelo.id).where(modelo.codigo == v)):
            falta(campo, f"{etiqueta} {v} does not exist.")

    if paso == "general":
        if requerido("proveedor", "The supplier is required.", siempre=True):
            prov = db.scalar(select(Proveedor).where(Proveedor.codigo == _texto(cab["proveedor"]).upper()))
            permitidos = proveedor_filtro(user)
            if not prov or not prov.activo or (permitidos is not None and prov.id not in permitidos):
                falta("proveedor", "Choose an active supplier.")
            elif requerido("oc", "The PO number is required.", siempre=True):
                if not re.fullmatch(r"[\w./-]{1,40}", _texto(cab["oc"])):
                    falta("oc", "The PO number has letters, numbers, ., / and - (up to 40).")
                elif db.scalar(select(OrdenCompra.id).where(OrdenCompra.proveedor_id == prov.id,
                                                            OrdenCompra.numero == _texto(cab["oc"]),
                                                            OrdenCompra.id != (oc_id or 0))):
                    falta("oc", f"PO {_texto(cab['oc'])} already exists for this supplier.")
        else:
            requerido("oc", "The PO number is required.", siempre=True)
        if requerido("sociedad", "The company (bill to) is required.", siempre=True):
            existe("sociedad", Sociedad, "Company")
        requerido("fecha_oc", "The PO date is required.")
        if _texto(cab.get("fecha_oc")) and not _fecha(cab.get("fecha_oc")):
            falta("fecha_oc", "Enter a valid date.")
    elif paso == "articulos":
        if not lineas:
            falta("lineas", "Add at least one item.")
        prov = db.scalar(select(Proveedor).where(Proveedor.codigo == _texto(cab.get("proveedor")).upper()))
        for i, ln in enumerate(lineas):
            ref = f"lineas.{i}"
            art = db.scalar(select(Articulo).where(Articulo.sku == _texto(ln.get("codigo_sap")))) if _texto(ln.get("codigo_sap")) else None
            if not art:
                falta(f"{ref}.codigo_sap", f"Line {i + 1}: choose an item from the item master.")
            elif prov and art.proveedor_id not in (None, prov.id):
                falta(f"{ref}.codigo_sap", f"Line {i + 1}: the item belongs to another supplier.")
            elif not art.activo:
                falta(f"{ref}.codigo_sap", f"Line {i + 1}: the item is inactive.")
            cant = _numero(ln.get("cantidad"))
            if cant is None or cant <= 0:
                falta(f"{ref}.cantidad", f"Line {i + 1}: enter a quantity greater than zero.")
            unidad = _texto(ln.get("unidad")).upper() or (art.unidad if art else "")
            if unidad and unidad not in listas.codigos("unidad"):
                falta(f"{ref}.unidad", f"Line {i + 1}: unit {unidad} is not in the list.")
            elif cant and unidad and (listas.valor("unidad", unidad) or {}).get("contable") and cant != int(cant):
                falta(f"{ref}.cantidad", f"Line {i + 1}: {unidad} is counted in whole numbers.")
        repetidos = {x for x in (_texto(ln.get("codigo_sap")) for ln in lineas) if x}
        if len(repetidos) < len([ln for ln in lineas if _texto(ln.get("codigo_sap"))]):
            falta("lineas", "An item appears twice: add the quantities in one line.")
    elif paso == "condiciones":
        if requerido("moneda", "The currency is required.", siempre=True):
            de_lista("moneda", "moneda", "Currency")
        requerido("incoterm", "The Incoterm is required.")
        de_lista("incoterm", "incoterm", "Incoterm")
        requerido("condicion_pago", "The payment terms are required.")
        de_lista("condicion_pago", "condicion_pago", "Payment terms")
        for i, ln in enumerate(lineas):
            ref = f"lineas.{i}"
            precio = _numero(ln.get("precio"))
            if precio is None or precio <= 0:
                falta(f"{ref}.precio", f"Line {i + 1}: enter the unit price.")
    elif paso == "logistica":
        if requerido("fecha_xf", "The ship date (XF) is required.", siempre=True) and not _fecha(cab.get("fecha_xf")):
            falta("fecha_xf", "Enter a valid date.")
        requerido("fecha_tienda", "The in-store date is required.")
        xf, tienda = _fecha(cab.get("fecha_xf")), _fecha(cab.get("fecha_tienda"))
        if xf and tienda and tienda < xf:
            falta("fecha_tienda", "The in-store date cannot be before the ship date.")
        for campo, modelo, etiqueta in (("centro", Centro, "Plant"), ("centro_destino", Centro, "Destination plant"),
                                        ("puerto_despacho", Puerto, "Port"), ("pais_origen", Pais, "Country"),
                                        ("pais_procedencia", Pais, "Country")):
            texto = {"centro": "The receiving plant is required.", "centro_destino": "The destination plant is required.",
                     "puerto_despacho": "The port of loading is required.", "pais_origen": "The country of origin is required."}.get(campo, "")
            if texto:
                requerido(campo, texto)
            existe(campo, modelo, etiqueta)
        # Datos de aduana: se piden aquí (no antes) si la empresa los exige para facturar
        if regla("REQUERIR_DATOS_ADUANA") and "pais_origen" not in obligatorios and not _texto(cab.get("pais_origen")):
            arts = [db.scalar(select(Articulo).where(Articulo.sku == _texto(ln.get("codigo_sap")))) for ln in lineas]
            if any(a is not None and not (a.producto and a.producto.pais_origen) for a in arts):
                falta("pais_origen", "The country of origin is required for customs (some items do not have it).")
    elif paso == "documentacion":
        extra = cab.get("extra") or {}
        try:
            campos_propios.limpiar("ordenes", extra, parcial=False)
        except ErrorNegocio as e:
            err += [{"paso": paso, "campo": d["campo"], "mensaje": d["mensaje"]} for d in (e.detalle or [])]
    return err


def estado_pasos(db: Session, user: Usuario, oc: OrdenCompra) -> list[dict]:
    borrador = oc.borrador or _borrador_de(oc)
    res = []
    for clave, titulo in PASOS:
        errores = [] if clave == "revision" else validar_paso(db, user, borrador, clave, oc.id)
        res.append({"clave": clave, "titulo": titulo, "errores": errores, "completo": not errores})
    return res


# ---- Envío y aprobación ------------------------------------------------------------------
def _total(oc: OrdenCompra) -> float:
    return sum((p.cantidad or 0) * (p.precio or 0) for p in oc.posiciones)


def reglas_que_aplican(oc: OrdenCompra) -> list[dict]:
    total = _total(oc)
    return [r for r in (configuracion_actual().get("aprobaciones_oc") or [])
            if r["moneda"] == (oc.moneda or "") and total >= float(r["monto_minimo"])
            and (not r.get("sociedad") or r["sociedad"] == oc.sociedad)]


def _liberar(db: Session, oc: OrdenCompra) -> None:
    """Una OC aprobada en la plataforma queda liberada para facturar."""
    lib = liberaciones.de(db)
    com = next((x.codigo for x in lib.comercial.lista if x.libera and not x.con_cambios), None)
    log = next((x.codigo for x in lib.logistica.lista if x.libera and not x.con_cambios), None)
    if com and log:
        oc.liberacion_comercial, oc.liberacion_logistica = com, log
    oc.liberada = lib.liberada(oc.liberacion_comercial, oc.liberacion_logistica) if com and log else True
    lib.fechar(oc)


def iniciar_aprobacion(db: Session, user: Usuario | None, oc: OrdenCompra) -> None:
    """Pasos de aprobación según las reglas; sin reglas que apliquen, aprobada."""
    for a in list(oc.aprobaciones):
        db.delete(a)
    db.flush()
    reglas = reglas_que_aplican(oc)
    oc.enviada_en = ahora()
    if not reglas:
        oc.estado, oc.aprobada_en = "APROBADA", ahora()
        if oc.origen == "PLATAFORMA":
            _liberar(db, oc)
        return
    oc.estado, oc.liberada = "EN_APROBACION", False
    for i, r in enumerate(reglas, start=1):
        oc.aprobaciones.append(AprobacionOC(paso=i, regla=r["nombre"], rol_id=r["rol_id"], estado="PENDIENTE"))
    db.flush()


def enviar(db: Session, user: Usuario, oc_id: int, version: int | None) -> dict:
    """Valida todo el borrador, guarda sus líneas con el mismo proceso que una
    carga del ERP y la envía a aprobación (o la aprueba si ninguna regla aplica)."""
    from app.modulos.compras.ordenes import _clasificar, aplicar_importacion

    exigir(user, "oc.editar")
    oc = cargar(db, user, oc_id)
    OC.exigir("enviar", oc.estado)
    verificar_version(oc, version, "purchase order")
    borrador = oc.borrador or _borrador_de(oc)
    errores = validar_paso(db, user, borrador, "revision", oc.id)
    if errores:
        raise ErrorNegocio("Some steps are incomplete.", 422, "validacion", errores)
    cab = borrador["cabecera"]
    filas = []
    for i, ln in enumerate(borrador["lineas"], start=1):
        fila = {k: _texto(cab.get(k)) for k in CABECERA if k not in ("condicion_pago", "notas")}
        fila.update({k: _texto(v) for k, v in ln.items() if k in LINEA})
        fila.update({f"extra.{k}": v for k, v in (cab.get("extra") or {}).items()})
        fila["posicion"], fila["_fila"] = str(i * 10), i
        # Las liberaciones del ERP no aplican: la aprobación de la plataforma las da
        fila["liberacion_comercial"] = fila["liberacion_logistica"] = ""
        filas.append(fila)
    # Las líneas se vuelven a crear (si fue rechazada, las anteriores no se facturaron)
    for p in list(oc.posiciones):
        db.delete(p)
    db.flush()
    db.expire(oc, ["posiciones"])
    malas = [c for c in _clasificar(db, filas, oc.id) if c["estado"] in ("error", "conflicto")]
    if malas:
        raise ErrorNegocio("Check the purchase order.", 422, "validacion",
                           [{"paso": "revision", "campo": f"lineas.{c['fila'] - 1}", "mensaje": f"Line {c['fila']}: {m}"}
                            for c in malas for m in c["mensajes"]])
    imp = ImportacionOC(usuario_id=user.id, nombre_archivo="(assistant)", filas=filas)
    db.add(imp)
    db.flush()
    aplicar_importacion(db, user, imp, propia=oc.id)
    db.refresh(oc)
    oc.condicion_pago = _texto(cab.get("condicion_pago")).upper() or None
    oc.notas = _texto(cab.get("notas"))[:2000] or None
    oc.borrador, oc.motivo_estado = None, None
    iniciar_aprobacion(db, user, oc)
    tocar(oc)
    registrar(db, user, "orden", oc.id, "enviada", {"lineas": len(filas), "total": round(_total(oc), 2), "moneda": oc.moneda,
                                                     "estado": oc.estado, "pasos": [a.regla for a in oc.aprobaciones]})
    return detalle(db, user, oc.id)


def _paso_actual(oc: OrdenCompra) -> AprobacionOC | None:
    return next((a for a in oc.aprobaciones if a.estado == "PENDIENTE"), None)


def _exigir_aprobador(db: Session, user: Usuario, oc: OrdenCompra) -> AprobacionOC:
    exigir(user, "oc.aprobar")
    paso = _paso_actual(oc)
    if not paso:
        raise ErrorNegocio("The purchase order has no pending approval.", 409, "transicion_invalida")
    if paso.rol_id and user.rol_id != paso.rol_id and not tiene(user, "admin"):
        rol = db.get(Rol, paso.rol_id)
        raise ErrorNegocio(f"This step is approved by the role {rol.nombre if rol else '?'}.", 403, "sin_permiso")
    if regla("APROBACION_CUATRO_OJOS"):
        envio = db.scalar(select(Historial.usuario_id).where(Historial.entidad == "orden", Historial.entidad_id == oc.id,
                                                              Historial.accion == "enviada").order_by(Historial.id.desc()))
        if user.id in (oc.creada_por, envio):
            raise ErrorNegocio("Whoever created or sent the purchase order cannot approve it.", 403, "cuatro_ojos")
    return paso


def aprobar(db: Session, user: Usuario, oc_id: int, comentario: str | None) -> dict:
    oc = cargar(db, user, oc_id)
    OC.exigir("aprobar", oc.estado)
    paso = _exigir_aprobador(db, user, oc)
    paso.estado, paso.usuario_id, paso.fecha = "APROBADA", user.id, ahora()
    paso.comentario = _texto(comentario)[:500] or None
    if not _paso_actual(oc):
        oc.estado, oc.aprobada_en = "APROBADA", ahora()
        _liberar(db, oc)
    tocar(oc)
    registrar(db, user, "orden", oc.id, "aprobada" if oc.estado == "APROBADA" else "paso_aprobado",
              {"paso": paso.paso, "regla": paso.regla, "comentario": paso.comentario})
    return detalle(db, user, oc.id)


def rechazar(db: Session, user: Usuario, oc_id: int, motivo: str | None) -> dict:
    motivo = requerir_motivo(motivo, "reject the purchase order")
    oc = cargar(db, user, oc_id)
    OC.exigir("rechazar", oc.estado)
    paso = _exigir_aprobador(db, user, oc)
    paso.estado, paso.usuario_id, paso.fecha, paso.comentario = "RECHAZADA", user.id, ahora(), motivo[:500]
    oc.estado, oc.motivo_estado, oc.liberada = "RECHAZADA", motivo[:500], False
    tocar(oc)
    registrar(db, user, "orden", oc.id, "rechazada", {"paso": paso.paso, "regla": paso.regla}, motivo=motivo)
    return detalle(db, user, oc.id)


def _facturas_activas(db: Session, oc: OrdenCompra) -> list[str]:
    return sorted({n or f"#{i}" for i, n in db.execute(
        select(Factura.id, Factura.numero).join(FacturaLinea, FacturaLinea.factura_id == Factura.id)
        .join(PosicionOC, PosicionOC.id == FacturaLinea.posicion_oc_id)
        .where(PosicionOC.oc_id == oc.id, Factura.estado != "CANCELADA"))})


def cancelar(db: Session, user: Usuario, oc_id: int, motivo: str | None) -> dict:
    exigir(user, "oc.cancelar")
    motivo = requerir_motivo(motivo, "cancel the purchase order")
    oc = cargar(db, user, oc_id)
    OC.exigir("cancelar", oc.estado)
    activas = _facturas_activas(db, oc)
    if activas:
        raise ErrorNegocio(f"The purchase order is in active invoices ({', '.join(activas)}): cancel them first or close "
                           "the purchase order instead.", 409, "facturada")
    oc.estado, oc.motivo_estado, oc.liberada = "CANCELADA", motivo[:500], False
    tocar(oc)
    registrar(db, user, "orden", oc.id, "cancelada", None, motivo=motivo)
    return detalle(db, user, oc.id)


def cerrar(db: Session, user: Usuario, oc_id: int, motivo: str | None) -> dict:
    """Cierra una OC aprobada: lo que falta por facturar deja de estar disponible."""
    exigir(user, "oc.cancelar")
    motivo = requerir_motivo(motivo, "close the purchase order")
    oc = cargar(db, user, oc_id)
    OC.exigir("cerrar", oc.estado)
    oc.estado, oc.motivo_estado, oc.cerrada_en = "CERRADA", motivo[:500], ahora()
    tocar(oc)
    registrar(db, user, "orden", oc.id, "cerrada", None, motivo=motivo)
    return detalle(db, user, oc.id)


def reabrir(db: Session, user: Usuario, oc_id: int, motivo: str | None) -> dict:
    exigir(user, "oc.aprobar")
    motivo = requerir_motivo(motivo, "reopen the purchase order")
    oc = cargar(db, user, oc_id)
    OC.exigir("reabrir", oc.estado)
    oc.estado, oc.motivo_estado, oc.cerrada_en = "APROBADA", None, None
    tocar(oc)
    registrar(db, user, "orden", oc.id, "reabierta", None, motivo=motivo)
    return detalle(db, user, oc.id)


def eliminar(db: Session, user: Usuario, oc_id: int) -> None:
    """Un borrador que nunca se envió se puede borrar."""
    exigir(user, "oc.editar")
    oc = cargar(db, user, oc_id)
    OC.exigir("eliminar", oc.estado)
    if oc.posiciones or oc.enviada_en:
        raise ErrorNegocio("Only a draft that was never sent can be deleted; cancel it instead.", 409, "transicion_invalida")
    registrar(db, user, "orden", oc.id, "borrador_eliminado", {"numero": oc.numero})
    db.delete(oc)


# ---- Avance logístico -------------------------------------------------------------------
def avances(db: Session, oc_ids: list[int]) -> dict[int, dict]:
    """Por OC: avance (SIN_FACTURAR … RECIBIDA) y el porcentaje de cada etapa.
    Cada línea cuenta hasta su cantidad (nada se suma entre unidades distintas:
    el porcentaje es por valor si hay precios, si no por líneas)."""
    if not oc_ids:
        return {}
    lineas = db.execute(select(PosicionOC.id, PosicionOC.oc_id, PosicionOC.cantidad, PosicionOC.precio)
                        .where(PosicionOC.oc_id.in_(oc_ids))).all()
    ids = [x.id for x in lineas]

    def suma(consulta) -> dict[int, float]:
        return {pid: float(c or 0) for pid, c in db.execute(consulta)} if ids else {}

    activas = Factura.estado != "CANCELADA"
    fact = suma(select(FacturaLinea.posicion_oc_id, func.sum(FacturaLinea.cantidad)).join(Factura)
                .where(FacturaLinea.posicion_oc_id.in_(ids), activas).group_by(FacturaLinea.posicion_oc_id))
    base = (select(FacturaLinea.posicion_oc_id, func.sum(PLLinea.cantidad))
            .join(PLLinea, PLLinea.factura_linea_id == FacturaLinea.id).join(PackingList, PackingList.id == PLLinea.pl_id)
            .join(Factura, Factura.id == FacturaLinea.factura_id)
            .where(FacturaLinea.posicion_oc_id.in_(ids), activas, PackingList.estado != "CANCELADO"))
    emb = suma(base.join(UnidadCarga, UnidadCarga.id == PackingList.unidad_carga_id)
               .join(Embarque, Embarque.id == UnidadCarga.embarque_id)
               .where(Embarque.estado.notin_(("PLANIFICADO", "CANCELADO"))).group_by(FacturaLinea.posicion_oc_id))
    rec = suma(select(FacturaLinea.posicion_oc_id, func.sum(RecepcionLinea.cantidad_recibida))
               .join(PLLinea, PLLinea.factura_linea_id == FacturaLinea.id)
               .join(RecepcionLinea, RecepcionLinea.pl_linea_id == PLLinea.id)
               .join(Factura, Factura.id == FacturaLinea.factura_id)
               .where(FacturaLinea.posicion_oc_id.in_(ids), activas).group_by(FacturaLinea.posicion_oc_id))
    por_oc: dict[int, list] = {}
    for x in lineas:
        por_oc.setdefault(x.oc_id, []).append(x)
    res = {}
    for oc_id in oc_ids:
        ls = por_oc.get(oc_id, [])
        con_precio = ls and all(x.precio for x in ls)
        peso = {x.id: (float(x.precio) * float(x.cantidad or 0) if con_precio else 1.0) for x in ls}
        total = sum(peso.values()) or 1.0

        def pct(d: dict, _ls=ls, _peso=peso, _total=total) -> float:
            return round(sum(_peso[x.id] * min(d.get(x.id, 0) / float(x.cantidad), 1.0) for x in _ls if x.cantidad) * 100 / _total, 1)

        f, e, r = pct(fact), pct(emb), pct(rec)
        codigo = ("RECIBIDA" if r >= 100 else "RECIBIDA_PARCIAL" if r > 0 else "EN_TRANSITO" if e >= 100
                  else "EMBARCADA_PARCIAL" if e > 0 else "FACTURADA" if f >= 100 else "FACTURADA_PARCIAL" if f > 0
                  else "SIN_FACTURAR")
        res[oc_id] = {"codigo": codigo, "texto": AVANCES[codigo], "facturado": f, "embarcado": e, "recibido": r,
                      "base": "valor" if con_precio else "lineas"}
    return res


# ---- Detalle e historial ---------------------------------------------------------------------
def _es_aprobador(db: Session, user: Usuario, oc: OrdenCompra) -> bool:
    """Si el usuario aprueba el paso pendiente (las mismas reglas que al aprobar),
    para no ofrecerle un botón que el servidor le va a negar."""
    if not (tiene(user, "oc.aprobar") and OC.puede("aprobar", oc.estado)):
        return False
    try:
        _exigir_aprobador(db, user, oc)
    except ErrorNegocio:
        return False
    return True


def puede(db: Session, user: Usuario, oc: OrdenCompra) -> dict:
    aprobador = _es_aprobador(db, user, oc)
    return {
        "editar": tiene(user, "oc.editar") and OC.puede("editar", oc.estado),
        "enviar": tiene(user, "oc.editar") and OC.puede("enviar", oc.estado),
        "aprobar": aprobador,
        "rechazar": aprobador,
        "cancelar": tiene(user, "oc.cancelar") and OC.puede("cancelar", oc.estado),
        "cerrar": tiene(user, "oc.cancelar") and OC.puede("cerrar", oc.estado),
        "reabrir": tiene(user, "oc.aprobar") and OC.puede("reabrir", oc.estado),
        "eliminar": tiene(user, "oc.editar") and OC.puede("eliminar", oc.estado) and not oc.enviada_en,
    }


def detalle(db: Session, user: Usuario, oc_id: int) -> dict:
    from app.modulos.compras.ordenes import posiciones_oc

    oc = cargar(db, user, oc_id)
    base = posiciones_oc(db, user, oc.id)
    roles = {r.id: r.nombre for r in db.scalars(select(Rol))}
    usuarios = {u.id: u.nombre for u in db.scalars(select(Usuario).where(
        Usuario.id.in_([a.usuario_id for a in oc.aprobaciones if a.usuario_id] + [oc.creada_por or 0])))}
    paso = _paso_actual(oc)
    return {
        **base,
        "oc": {**base["oc"], "notas": oc.notas, "creada_por": usuarios.get(oc.creada_por), "enviada_en": oc.enviada_en,
               "aprobada_en": oc.aprobada_en, "cerrada_en": oc.cerrada_en, "motivo_estado": oc.motivo_estado,
               "total": round(_total(oc), 2)},
        "avance": avances(db, [oc.id]).get(oc.id),
        "aprobaciones": [{"paso": a.paso, "regla": a.regla, "rol": roles.get(a.rol_id), "estado": a.estado,
                          "usuario": usuarios.get(a.usuario_id), "fecha": a.fecha, "comentario": a.comentario,
                          "actual": a is paso} for a in oc.aprobaciones],
        "borrador": (oc.borrador or _borrador_de(oc)) if OC.puede("editar", oc.estado) else None,
        "pasos": estado_pasos(db, user, oc) if OC.puede("editar", oc.estado) else None,
        "puede": puede(db, user, oc),
        "acciones": OC.disponibles(oc.estado),
    }


def historial(db: Session, user: Usuario, oc_id: int) -> list[dict]:
    oc = cargar(db, user, oc_id)
    filas = db.scalars(select(Historial).where(Historial.entidad == "orden", Historial.entidad_id == oc.id)
                       .order_by(Historial.fecha.desc(), Historial.id.desc())).all()
    return [{"id": h.id, "fecha": h.fecha, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
             "usuario": h.usuario.nombre if h.usuario else None} for h in filas]


def pendientes_de_aprobar(db: Session, user: Usuario) -> list[dict]:
    """OCs que esperan la aprobación del rol del usuario (para su bandeja)."""
    if not tiene(user, "oc.aprobar"):
        return []
    prov = proveedor_filtro(user)
    consulta = (select(OrdenCompra, AprobacionOC).join(AprobacionOC, AprobacionOC.oc_id == OrdenCompra.id)
                .where(OrdenCompra.estado == "EN_APROBACION", AprobacionOC.estado == "PENDIENTE"))
    if prov:
        consulta = consulta.where(OrdenCompra.proveedor_id.in_(prov))
    res, vistas = [], set()
    for oc, a in db.execute(consulta.order_by(OrdenCompra.enviada_en, AprobacionOC.paso)).all():
        if oc.id in vistas:
            continue
        vistas.add(oc.id)
        if _es_aprobador(db, user, oc):  # su rol y, con cuatro ojos, no la creó ni la envió
            res.append({"id": oc.id, "numero": oc.numero, "proveedor": oc.proveedor.nombre, "total": round(_total(oc), 2),
                        "moneda": oc.moneda, "regla": a.regla, "enviada_en": oc.enviada_en})
    return res
