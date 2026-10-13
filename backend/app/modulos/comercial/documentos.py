"""Documentos comerciales: facturas emitidas y recibidas, notas de crédito y
débito y proformas.

Ciclo de vida: BORRADOR (se edita y se recalcula) → EMITIDO (inmutable, con
número de serie, totales, datos de las partes y vencimientos guardados) →
ANULADO (con motivo, solo sin pagos aplicados). Un documento emitido se
corrige con una nota de crédito o débito relacionada, nunca editándolo.

Cálculo (core/dinero.py): cada línea es cantidad × precio − descuento; sus
impuestos se calculan sobre esa base con la tasa vigente en la fecha del
documento y se copian a la línea. Según la configuración fiscal de la
sociedad se redondea cada línea (predeterminado) o solo el total.
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import dinero, numeracion
from app.core.errores import ErrorNegocio
from app.modelos import (
    Aplicacion,
    Articulo,
    CondicionPago,
    ConfiguracionFiscal,
    CuotaCondicionPago,
    Documento,
    DocumentoLinea,
    Impuesto,
    LineaImpuesto,
    Moneda,
    PosicionOC,
    RelacionDocumento,
    Sociedad,
    Tercero,
    TipoDocumento,
    UnidadMedida,
    Usuario,
    Vencimiento,
    ahora,
)
from app.modulos.acceso.permisos import exigir, sociedades_de
from app.modulos.comercial import terceros as svc_terceros
from app.modulos.comun import tabla
from app.modulos.comun.historial import registrar, requerir_motivo, verificar_version
from app.modulos.comun.texto import filtro_texto

CERO = dinero.CERO
CIEN = Decimal(100)

# Tipos de documento de fábrica: (código, nombre, clase, dirección, signo, afecta saldo, exige origen, prefijo de serie)
TIPOS_FABRICA = [
    ("FACTURA", "Invoice", "FACTURA", "EMITIDO", 1, True, False, "F-"),
    ("NOTA_CREDITO", "Credit note", "NOTA_CREDITO", "EMITIDO", -1, True, True, "NC-"),
    ("NOTA_DEBITO", "Debit note", "NOTA_DEBITO", "EMITIDO", 1, True, True, "ND-"),
    ("PROFORMA", "Proforma invoice", "PROFORMA", "EMITIDO", 1, False, False, "PRO-"),
    ("FACTURA_PROVEEDOR", "Supplier invoice", "FACTURA", "RECIBIDO", 1, True, False, None),
    ("NC_PROVEEDOR", "Supplier credit note", "NOTA_CREDITO", "RECIBIDO", -1, True, True, None),
]
METODOS_FABRICA = [("TRANSFERENCIA", "Bank transfer"), ("CHEQUE", "Check"), ("EFECTIVO", "Cash"), ("TARJETA", "Card"),
                   ("COMPENSACION", "Offsetting")]


def sembrar(db: Session) -> None:
    """Tipos de documento y métodos de pago de fábrica (si faltan)."""
    from app.modelos import MetodoPago

    existentes = set(db.scalars(select(TipoDocumento.codigo)))
    for i, (c, n, cl, d, s, a, o, _) in enumerate(TIPOS_FABRICA, start=1):
        if c not in existentes:
            db.add(TipoDocumento(codigo=c, nombre=n, clase=cl, direccion=d, signo=s, afecta_saldo=a, requiere_origen=o,
                                 orden=i, activo=True))
    if not db.scalar(select(MetodoPago.id).limit(1)):
        for i, (c, n) in enumerate(METODOS_FABRICA, start=1):
            db.add(MetodoPago(codigo=c, nombre=n, orden=i, activo=True))
    db.flush()


# ---- Lectura -------------------------------------------------------------------------------
def tipo_por_codigo(db: Session, codigo: str) -> TipoDocumento:
    t = db.scalar(select(TipoDocumento).where(TipoDocumento.codigo == (codigo or "").upper()))
    if t is None:
        sembrar(db)
        t = db.scalar(select(TipoDocumento).where(TipoDocumento.codigo == (codigo or "").upper()))
    if not t or not t.activo:
        raise ErrorNegocio(f"The document type {codigo} does not exist or is inactive.", 422, "validacion")
    return t


def _sociedad(db: Session, user: Usuario | None, codigo: str) -> Sociedad:
    s = db.scalar(select(Sociedad).where(Sociedad.codigo == (codigo or "").upper()))
    if not s:
        raise ErrorNegocio(f"The company {codigo} does not exist.", 422, "validacion")
    permitidas = sociedades_de(user) if user else None
    if permitidas and s.codigo not in permitidas:
        raise ErrorNegocio("Document not found.", 404, "no_encontrado")
    return s


def cargar(db: Session, user: Usuario | None, documento_id: int, bloquear: bool = False) -> Documento:
    c = select(Documento).where(Documento.id == documento_id)
    if bloquear:
        c = c.with_for_update()
    d = db.scalar(c)
    if not d:
        raise ErrorNegocio("The document does not exist.", 404, "no_encontrado")
    permitidas = sociedades_de(user) if user else None
    if permitidas and db.get(Sociedad, d.sociedad_id).codigo not in permitidas:
        raise ErrorNegocio("The document does not exist.", 404, "no_encontrado")
    return d


def aplicado(db: Session, documento_id: int) -> Decimal:
    """Lo que pagos y notas de crédito activos aplicaron a un documento."""
    return dinero.decimal(db.scalar(select(func.coalesce(func.sum(Aplicacion.importe), 0))
                                    .where(Aplicacion.documento_id == documento_id, Aplicacion.activa.is_(True))))


def credito_usado(db: Session, nota_id: int) -> Decimal:
    return dinero.decimal(db.scalar(select(func.coalesce(func.sum(Aplicacion.importe), 0))
                                    .where(Aplicacion.credito_id == nota_id, Aplicacion.activa.is_(True))))


def saldo(db: Session, d: Documento) -> Decimal:
    """Pendiente de un documento emitido que afecta saldo: de una factura o
    nota de débito, lo que falta cobrar o pagar; de una nota de crédito, lo
    que aún no se aplicó a otro documento."""
    if d.estado != "EMITIDO" or not d.tipo.afecta_saldo:
        return CERO
    usado = credito_usado(db, d.id) if d.tipo.signo < 0 else aplicado(db, d.id)
    return max(dinero.decimal(d.total) - usado, CERO)


def estado_cobro(db: Session, d: Documento, pendiente: Decimal | None = None) -> str | None:
    if d.estado != "EMITIDO" or not d.tipo.afecta_saldo:
        return None
    pendiente = saldo(db, d) if pendiente is None else pendiente
    if pendiente <= 0:
        return "PAGADO" if d.tipo.signo > 0 else "APLICADA"
    if d.tipo.signo > 0 and d.fecha_vencimiento and d.fecha_vencimiento < date.today():
        return "VENCIDO"
    return "PARCIAL" if pendiente < dinero.decimal(d.total) else "PENDIENTE"


def _num(v):
    return dinero.numero(dinero.decimal(v)) if v is not None else None


def dict_documento(db: Session, d: Documento, completo: bool = False) -> dict:
    pendiente = saldo(db, d)
    soc = db.get(Sociedad, d.sociedad_id)
    r = {"id": d.id, "tipo": d.tipo.codigo, "tipo_nombre": d.tipo.nombre, "clase": d.tipo.clase,
         "direccion": d.tipo.direccion, "signo": d.tipo.signo, "numero": d.numero, "referencia_externa": d.referencia_externa,
         "nombre": d.numero or d.referencia_externa or f"#{d.id}", "estado": d.estado, "sociedad": soc.codigo,
         "tercero_id": d.tercero_id, "tercero": d.tercero.nombre, "fecha": d.fecha, "fecha_vencimiento": d.fecha_vencimiento,
         "moneda": d.moneda, "tipo_cambio": _num(d.tipo_cambio), "condicion_pago": d.condicion_pago,
         "subtotal": _num(d.subtotal), "descuentos": _num(d.descuentos), "impuestos": _num(d.impuestos),
         "retenciones": _num(d.retenciones), "total": _num(d.total), "saldo": dinero.numero(pendiente),
         "estado_cobro": estado_cobro(db, d, pendiente), "factura_id": d.factura_id, "version": d.version,
         "emitido_en": d.emitido_en}
    if completo:
        r["notas"], r["extra"], r["copia"] = d.notas, d.extra or {}, d.copia or {}
        r["motivo_anulacion"] = d.motivo_anulacion
        r["lineas"] = [{"id": x.id, "orden": x.orden, "articulo_id": x.articulo_id, "posicion_oc_id": x.posicion_oc_id,
                        "factura_linea_id": x.factura_linea_id, "codigo": x.codigo, "descripcion": x.descripcion,
                        "cantidad": x.cantidad, "unidad": x.unidad, "precio_unitario": x.precio_unitario,
                        "descuento_pct": _num(x.descuento_pct), "descuento": _num(x.descuento), "subtotal": _num(x.subtotal),
                        "impuestos": _num(x.impuestos), "retenciones": _num(x.retenciones), "total": _num(x.total),
                        "impuestos_codigos": [c for c in (x.impuestos_codigos or "").split(",") if c],
                        "aplicados": [{"codigo": a.codigo, "nombre": a.nombre, "tasa": _num(a.tasa), "base": _num(a.base),
                                       "importe": _num(a.importe), "es_retencion": a.es_retencion} for a in x.aplicados]}
                       for x in d.lineas]
        r["vencimientos"] = [{"id": v.id, "numero": v.numero, "fecha": v.fecha, "importe": _num(v.importe)} for v in d.vencimientos]
        r["relaciones"] = relaciones(db, d)
        r["aplicaciones"] = [
            {"id": a.id, "importe": _num(a.importe), "activa": a.activa, "pago_id": a.pago_id, "credito_id": a.credito_id,
             "documento_id": a.documento_id, "creado_en": a.creado_en}
            for a in db.scalars(select(Aplicacion).where(or_(Aplicacion.documento_id == d.id, Aplicacion.credito_id == d.id))
                                .order_by(Aplicacion.id))]
        r["impuestos_detalle"] = _resumen_impuestos(d)
    return r


def _resumen_impuestos(d: Documento) -> list[dict]:
    por: dict[str, dict] = {}
    for x in d.lineas:
        for a in x.aplicados:
            i = por.setdefault(a.codigo, {"codigo": a.codigo, "nombre": a.nombre, "tasa": _num(a.tasa), "base": CERO,
                                          "importe": CERO, "es_retencion": a.es_retencion})
            i["base"] += dinero.decimal(a.base)
            i["importe"] += dinero.decimal(a.importe)
    return [{**i, "base": dinero.numero(i["base"]), "importe": dinero.numero(i["importe"])} for i in por.values()]


def relaciones(db: Session, d: Documento) -> list[dict]:
    res = []
    for r in db.scalars(select(RelacionDocumento).where(or_(RelacionDocumento.origen_id == d.id,
                                                            RelacionDocumento.destino_id == d.id))):
        otro = db.get(Documento, r.destino_id if r.origen_id == d.id else r.origen_id)
        res.append({"tipo": r.tipo, "sentido": "a" if r.origen_id == d.id else "desde", "documento_id": otro.id,
                    "nombre": otro.numero or otro.referencia_externa or f"#{otro.id}", "tipo_documento": otro.tipo.nombre,
                    "estado": otro.estado})
    return res


COLUMNAS = {"tipo": TipoDocumento.codigo, "estado": Documento.estado, "sociedad": Sociedad.codigo,
            "tercero": Tercero.nombre, "moneda": Documento.moneda, "fecha": Documento.fecha,
            "direccion": TipoDocumento.direccion}


def _consulta(user: Usuario, direccion=None, estado=None, q=None, tercero_id=None, desde=None, hasta=None):
    exigir(user, "comercial.ver")
    c = (select(Documento).join(TipoDocumento, TipoDocumento.id == Documento.tipo_documento_id)
         .join(Sociedad, Sociedad.id == Documento.sociedad_id).join(Tercero, Tercero.id == Documento.tercero_id))
    if direccion:
        c = c.where(TipoDocumento.direccion == direccion.upper())
    if estado:
        c = c.where(Documento.estado == estado.upper())
    if tercero_id:
        c = c.where(Documento.tercero_id == tercero_id)
    if desde:
        c = c.where(Documento.fecha >= desde)
    if hasta:
        c = c.where(Documento.fecha <= hasta)
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [x.ilike(p) for x in (Documento.numero, Documento.referencia_externa, Tercero.nombre, Tercero.codigo)]))
    permitidas = sociedades_de(user)
    if permitidas:
        c = c.where(Sociedad.codigo.in_(permitidas))
    return c


def listar(db: Session, user: Usuario, direccion=None, estado=None, q=None, tercero_id=None, desde=None, hasta=None,
           cobro=None, page=1, size=25, orden=None, filtros=None) -> dict:
    c = tabla.aplicar(_consulta(user, direccion, estado, q, tercero_id, desde, hasta), COLUMNAS, filtros or {})
    col, _, dirc = (orden or "").partition(":")
    expr = {**COLUMNAS, "numero": Documento.numero, "total": Documento.total, "vencimiento": Documento.fecha_vencimiento}.get(col)
    c = c.order_by((expr.desc().nullslast() if dirc == "desc" else expr.asc().nullslast()) if expr is not None
                   else Documento.creado_en.desc(), Documento.id.desc())
    if cobro:  # por estado de cobro (se calcula: no es una columna)
        todos = [dict_documento(db, d) for d in db.scalars(c)]
        todos = [x for x in todos if x["estado_cobro"] == cobro.upper()]
        return {"items": todos[(page - 1) * size: page * size], "total": len(todos)}
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    return {"items": [dict_documento(db, d) for d in db.scalars(c.offset((page - 1) * size).limit(size))], "total": total}


def valores(db: Session, user: Usuario, columna: str, buscar=None, filtros=None, **kw) -> list[dict]:
    expr = tabla.columna_valida(COLUMNAS, columna)
    c = tabla.aplicar(_consulta(user, **kw), COLUMNAS, filtros or {}, excepto=columna)
    return tabla.valores(db, c, expr, buscar)


def detalle(db: Session, user: Usuario, documento_id: int) -> dict:
    exigir(user, "comercial.ver")
    return dict_documento(db, cargar(db, user, documento_id), completo=True)


# ---- Cálculo -----------------------------------------------------------------------------------
def impuesto_vigente(db: Session, codigo: str, fecha: date) -> Impuesto:
    imp = db.scalar(select(Impuesto).where(
        Impuesto.codigo == codigo, Impuesto.activo.is_(True),
        or_(Impuesto.vigente_desde.is_(None), Impuesto.vigente_desde <= fecha),
        or_(Impuesto.vigente_hasta.is_(None), Impuesto.vigente_hasta >= fecha)).order_by(Impuesto.vigente_desde.desc()))
    if not imp:
        raise ErrorNegocio(f"The tax {codigo} does not exist or is not in force on {fecha.isoformat()}.", 422, "validacion")
    return imp


def configuracion(db: Session, sociedad_id: int) -> ConfiguracionFiscal | None:
    return db.scalar(select(ConfiguracionFiscal).where(ConfiguracionFiscal.sociedad_id == sociedad_id))


def calcular(db: Session, d: Documento) -> None:
    """Recalcula líneas, impuestos y totales del documento (en borrador)."""
    conf = configuracion(db, d.sociedad_id)
    por_linea = not conf or conf.redondeo == "LINEA"
    dec = dinero.decimales(d.moneda)
    moneda_db = db.scalar(select(Moneda).where(Moneda.codigo == d.moneda))
    if moneda_db is not None:
        dec = moneda_db.decimales

    def r(v):
        return dinero.redondear(v, decimales_=dec) if por_linea else dinero.decimal(v)

    fecha = d.fecha or date.today()
    tot = {"subtotal": CERO, "descuentos": CERO, "impuestos": CERO, "retenciones": CERO}
    for linea in d.lineas:
        bruto = dinero.decimal(linea.cantidad) * dinero.decimal(linea.precio_unitario)
        desc = r(bruto * dinero.decimal(linea.descuento_pct) / CIEN)
        base = r(bruto) - desc if por_linea else bruto - desc
        imp_total, ret_total = CERO, CERO
        linea.aplicados.clear()
        db.flush()
        for codigo in [c for c in (linea.impuestos_codigos or "").split(",") if c]:
            imp = impuesto_vigente(db, codigo, fecha)
            tasa = dinero.decimal(imp.tasa)
            importe = r(base * tasa / CIEN if imp.tipo == "PORCENTAJE" else dinero.decimal(linea.cantidad) * tasa)
            linea.aplicados.append(LineaImpuesto(impuesto_id=imp.id, codigo=imp.codigo, nombre=imp.nombre, tipo=imp.tipo,
                                                 tasa=tasa, base=base, importe=importe, es_retencion=imp.es_retencion))
            if imp.es_retencion:
                ret_total += importe
            else:
                imp_total += importe
        linea.descuento, linea.subtotal = desc, base
        linea.impuestos, linea.retenciones = imp_total, ret_total
        linea.total = base + imp_total - ret_total
        tot["subtotal"] += base
        tot["descuentos"] += desc
        tot["impuestos"] += imp_total
        tot["retenciones"] += ret_total
    tot = {k: dinero.redondear(v, decimales_=dec) for k, v in tot.items()}
    total = tot["subtotal"] + tot["impuestos"] - tot["retenciones"]
    if total < 0:
        raise ErrorNegocio("The withholdings cannot exceed the document amount.", 422, "validacion")
    d.subtotal, d.descuentos, d.impuestos, d.retenciones, d.total = (tot["subtotal"], tot["descuentos"], tot["impuestos"],
                                                                     tot["retenciones"], total)


# ---- Borradores ----------------------------------------------------------------------------------
def _impuestos_defecto(db: Session, d: Documento) -> str | None:
    if d.tipo.direccion != "EMITIDO":
        return None
    conf = configuracion(db, d.sociedad_id)
    return conf.impuestos_defecto if conf and conf.impuestos_defecto else None


def _lineas(db: Session, d: Documento, lineas) -> None:
    errores = []
    d.lineas.clear()
    db.flush()
    for i, ln in enumerate(lineas, start=1):
        art = db.get(Articulo, ln.articulo_id) if ln.articulo_id else None
        pos = db.get(PosicionOC, ln.posicion_oc_id) if ln.posicion_oc_id else None
        if ln.articulo_id and not art:
            errores.append({"campo": f"lineas.{i}.articulo_id", "mensaje": f"Line {i}: the item does not exist."})
            continue
        if ln.posicion_oc_id and not pos:
            errores.append({"campo": f"lineas.{i}.posicion_oc_id", "mensaje": f"Line {i}: the PO line does not exist."})
            continue
        descripcion = (ln.descripcion or "").strip() or (art.descripcion if art else None) or (pos.descripcion if pos else None)
        if not descripcion:
            errores.append({"campo": f"lineas.{i}.descripcion", "mensaje": f"Line {i}: enter the description."})
            continue
        unidad = (ln.unidad or (art.unidad if art else None) or (pos.unidad if pos else None) or "").upper() or None
        if unidad and not db.scalar(select(UnidadMedida.id).where(UnidadMedida.codigo == unidad)):
            errores.append({"campo": f"lineas.{i}.unidad", "mensaje": f"Line {i}: the unit {unidad} is not in the catalog."})
            continue
        codigos = ",".join(sorted({c.strip().upper() for c in ln.impuestos if c.strip()})) if ln.impuestos is not None \
            else _impuestos_defecto(db, d)
        d.lineas.append(DocumentoLinea(
            orden=i, articulo_id=art.id if art else None, posicion_oc_id=pos.id if pos else None,
            codigo=(ln.codigo or (art.sku if art else None) or (pos.codigo_articulo if pos else None)),
            descripcion=descripcion[:300], cantidad=ln.cantidad, unidad=unidad, precio_unitario=ln.precio_unitario,
            descuento_pct=ln.descuento_pct, impuestos_codigos=codigos or None))
    if errores:
        raise ErrorNegocio("Check the document lines.", 422, "validacion", errores)


def _validar_cabecera(db: Session, d: Documento) -> None:
    errores = []
    if not db.scalar(select(Moneda.id).where(Moneda.codigo == d.moneda, Moneda.activo.is_(True))):
        errores.append({"campo": "moneda", "mensaje": f"The currency {d.moneda} is not in the catalog."})
    if d.condicion_pago and not db.scalar(select(CondicionPago.id).where(CondicionPago.codigo == d.condicion_pago)):
        errores.append({"campo": "condicion_pago", "mensaje": f"The payment term {d.condicion_pago} is not in the catalog."})
    t = db.get(Tercero, d.tercero_id)
    roles = {r.rol for r in t.roles} if t else set()
    if not t or not t.activo:
        errores.append({"campo": "tercero_id", "mensaje": "Choose an active business partner."})
    elif d.tipo.direccion == "EMITIDO" and "CLIENTE" not in roles:
        errores.append({"campo": "tercero_id", "mensaje": f"{t.nombre} is not a customer."})
    elif d.tipo.direccion == "RECIBIDO" and not roles & {"PROVEEDOR", "TRANSPORTISTA", "AGENTE"}:
        errores.append({"campo": "tercero_id", "mensaje": f"{t.nombre} is not a supplier, carrier or agent."})
    if errores:
        raise ErrorNegocio("Check the document.", 422, "validacion", errores)


def crear(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "comercial.editar")
    tipo = tipo_por_codigo(db, datos.tipo)
    soc = _sociedad(db, user, datos.sociedad)
    t = svc_terceros.cargar(db, datos.tercero_id)
    d = Documento(tipo_documento_id=tipo.id, sociedad_id=soc.id, tercero_id=t.id, fecha=datos.fecha,
                  moneda=(datos.moneda or t.moneda or soc.moneda).upper(), tipo_cambio=datos.tipo_cambio or 1,
                  condicion_pago=(datos.condicion_pago or t.condicion_pago or None),
                  referencia_externa=(datos.referencia_externa or "").strip() or None, notas=datos.notas,
                  extra=datos.extra or {}, estado="BORRADOR", creado_por=user.id, version=1)
    d.tipo = tipo
    db.add(d)
    _validar_cabecera(db, d)
    db.flush()
    if datos.origen_id:
        origen = cargar(db, user, datos.origen_id)
        _relacionar(db, d, origen)
    _lineas(db, d, datos.lineas)
    calcular(db, d)
    db.flush()
    registrar(db, user, "documento", d.id, "crear", {"tipo": tipo.codigo, "total": dinero.numero(dinero.decimal(d.total))})
    return dict_documento(db, d, completo=True)


def _relacionar(db: Session, d: Documento, origen: Documento) -> None:
    if origen.estado != "EMITIDO":
        raise ErrorNegocio("Only an issued document can be corrected or referenced.", 409, "origen_no_emitido")
    if origen.tercero_id != d.tercero_id or origen.sociedad_id != d.sociedad_id:
        raise ErrorNegocio("The related document is of another company or business partner.", 422, "validacion")
    if origen.tipo.direccion != d.tipo.direccion:
        raise ErrorNegocio("An issued note corrects an issued document; a received note, a received one.", 422, "validacion")
    tipo = "RECTIFICA" if d.tipo.clase in ("NOTA_CREDITO", "NOTA_DEBITO") else "GENERADO_DESDE"
    db.add(RelacionDocumento(origen_id=d.id, destino_id=origen.id, tipo=tipo))


def _borrador(db: Session, user: Usuario, documento_id: int, version: int | None) -> Documento:
    exigir(user, "comercial.editar")
    d = cargar(db, user, documento_id, bloquear=True)
    verificar_version(d, version, "document")
    if d.estado != "BORRADOR":
        raise ErrorNegocio("An issued document cannot be edited: correct it with a credit or debit note.", 409, "no_editable")
    if d.factura_id:
        raise ErrorNegocio("This document mirrors a supplier invoice: edit the invoice.", 409, "no_editable")
    return d


def actualizar(db: Session, user: Usuario, documento_id: int, datos) -> dict:
    d = _borrador(db, user, documento_id, datos.version)
    campos = datos.model_dump(exclude_unset=True)
    for k in ("fecha", "tipo_cambio", "notas", "extra"):
        if k in campos:
            setattr(d, k, campos[k] if k != "tipo_cambio" else (campos[k] or 1))
    if "moneda" in campos and campos["moneda"]:
        d.moneda = campos["moneda"].upper()
    if "condicion_pago" in campos:
        d.condicion_pago = (campos["condicion_pago"] or "").upper() or None
    if "referencia_externa" in campos:
        d.referencia_externa = (campos["referencia_externa"] or "").strip() or None
    _validar_cabecera(db, d)
    if datos.lineas is not None:
        _lineas(db, d, datos.lineas)
    calcular(db, d)
    d.version += 1
    db.flush()
    registrar(db, user, "documento", d.id, "editar", {"total": dinero.numero(dinero.decimal(d.total))})
    return dict_documento(db, d, completo=True)


def eliminar(db: Session, user: Usuario, documento_id: int) -> dict:
    d = _borrador(db, user, documento_id, None)
    registrar(db, user, "documento", d.id, "eliminar", {"tipo": d.tipo.codigo})
    for r in db.scalars(select(RelacionDocumento).where(RelacionDocumento.origen_id == d.id)):
        db.delete(r)
    db.delete(d)
    db.flush()
    return {"eliminado": documento_id}


# ---- Emisión -------------------------------------------------------------------------------------
def _copia_partes(db: Session, d: Documento) -> dict:
    soc = db.get(Sociedad, d.sociedad_id)
    t = db.get(Tercero, d.tercero_id)
    fiscal = svc_terceros.direccion_fiscal(t)
    return {
        "sociedad": {"codigo": soc.codigo, "nombre": soc.nombre, "razon_social": soc.razon_social, "id_fiscal": soc.id_fiscal,
                     "pais": soc.pais, "direccion": soc.direccion},
        "tercero": {"codigo": t.codigo, "nombre": t.nombre, "razon_social": t.razon_social, "id_fiscal": t.id_fiscal,
                    "tipo_identificacion": t.tipo_identificacion, "pais": t.pais,
                    "direccion": fiscal.texto() if fiscal else None,
                    "correos": svc_terceros.correos(t.medios)},
    }


def _vencimientos(db: Session, d: Documento) -> None:
    """Cuotas según la condición de pago: sus cuotas, su plazo único o al contado."""
    d.vencimientos.clear()
    db.flush()
    if not d.tipo.afecta_saldo or d.tipo.signo < 0:
        d.fecha_vencimiento = d.fecha
        return
    total = dinero.decimal(d.total)
    cond = db.scalar(select(CondicionPago).where(CondicionPago.codigo == d.condicion_pago)) if d.condicion_pago else None
    cuotas = list(db.scalars(select(CuotaCondicionPago).where(CuotaCondicionPago.condicion_id == cond.id)
                             .order_by(CuotaCondicionPago.numero))) if cond else []
    if cuotas:
        acumulado = CERO
        for i, c in enumerate(cuotas, start=1):
            importe = total - acumulado if i == len(cuotas) else dinero.redondear(total * dinero.decimal(c.porcentaje) / CIEN, d.moneda)
            acumulado += importe
            d.vencimientos.append(Vencimiento(numero=i, fecha=d.fecha + timedelta(days=c.dias), importe=importe))
    else:
        dias = cond.dias if cond and cond.dias is not None else 0
        d.vencimientos.append(Vencimiento(numero=1, fecha=d.fecha + timedelta(days=dias), importe=total))
    d.fecha_vencimiento = max(v.fecha for v in d.vencimientos)


def _numerar(db: Session, d: Documento) -> None:
    if d.tipo.direccion == "RECIBIDO":
        if not d.referencia_externa:
            raise ErrorNegocio("Enter the number the supplier gave to this document.", 422, "validacion",
                               [{"campo": "referencia_externa", "mensaje": "The supplier's document number is missing."}])
        repetido = db.scalar(select(Documento.id).where(
            Documento.tercero_id == d.tercero_id, Documento.tipo_documento_id == d.tipo_documento_id,
            func.upper(Documento.referencia_externa) == d.referencia_externa.upper(), Documento.estado != "ANULADO",
            Documento.id != d.id))
        if repetido:
            raise ErrorNegocio(f"This partner's document {d.referencia_externa} is already registered.", 409, "duplicado")
        return
    prefijo = next((p for c, *_, p in TIPOS_FABRICA if c == d.tipo.codigo), None) or f"{d.tipo.codigo[:4]}-"
    serie = numeracion.serie_de(db, "documento", sociedad_id=d.sociedad_id, tipo_documento_id=d.tipo_documento_id,
                                fecha=d.fecha)
    if serie is None:
        serie = _serie_predeterminada(db, d, prefijo)
    d.serie_id = serie.id
    d.numero = numeracion.siguiente(db, serie, d.fecha)


def _serie_predeterminada(db: Session, d: Documento, prefijo: str):
    from sqlalchemy.exc import IntegrityError

    from app.modelos import ContadorSerie, SerieDocumental

    codigo = d.tipo.codigo[:20]
    s = SerieDocumental(codigo=codigo, nombre=d.tipo.nombre, objeto="documento", tipo_documento_id=d.tipo_documento_id,
                        prefijo=prefijo, digitos=6)
    try:
        with db.begin_nested():
            db.add(s)
            db.flush()
            db.add(ContadorSerie(serie_id=s.id, periodo="", siguiente=1))
            db.flush()
    except IntegrityError:
        s = numeracion.serie_de(db, "documento", sociedad_id=d.sociedad_id, tipo_documento_id=d.tipo_documento_id)
        if s is None:
            raise ErrorNegocio(f"Create the numbering series for {d.tipo.nombre}.", 409, "sin_serie") from None
    return s


def emitir(db: Session, user: Usuario, documento_id: int, version: int | None = None, interno: bool = False) -> dict:
    if not interno:
        exigir(user, "comercial.emitir")
    d = cargar(db, user, documento_id, bloquear=True)
    verificar_version(d, version, "document")
    if d.estado != "BORRADOR":
        raise ErrorNegocio("The document is already issued or voided.", 409, "transicion_invalida")
    if not d.lineas:
        raise ErrorNegocio("The document has no lines.", 422, "validacion")
    d.fecha = d.fecha or date.today()
    _validar_cabecera(db, d)
    origen = db.scalar(select(RelacionDocumento).where(RelacionDocumento.origen_id == d.id))
    if d.tipo.requiere_origen and not origen:
        raise ErrorNegocio(f"A {d.tipo.nombre.lower()} needs the document it corrects.", 422, "validacion")
    calcular(db, d)
    if dinero.decimal(d.total) <= 0 and d.tipo.afecta_saldo:
        raise ErrorNegocio("The document total must be greater than zero.", 422, "validacion")
    destino = cargar(db, user, origen.destino_id, bloquear=True) if origen else None
    if destino is not None and d.tipo.signo < 0 and \
            dinero.decimal(d.total) > dinero.decimal(destino.total) - _creditos_previos(db, destino, d.id):
        raise ErrorNegocio("The credit notes would exceed the corrected document's total.", 422, "validacion")
    _numerar(db, d)
    d.copia = _copia_partes(db, d)
    _vencimientos(db, d)
    d.estado, d.emitido_en = "EMITIDO", ahora()
    d.version += 1
    db.flush()
    # Una nota de crédito sobre una factura con saldo se aplica a ella
    if destino is not None and d.tipo.signo < 0 and d.tipo.afecta_saldo:
        disponible = min(dinero.decimal(d.total), saldo(db, destino))
        if disponible > 0:
            db.add(Aplicacion(credito_id=d.id, documento_id=destino.id, importe=disponible, activa=True,
                                   fecha=d.fecha))
    db.flush()
    registrar(db, user, "documento", d.id, "emitir", {"numero": d.numero or d.referencia_externa,
                                                      "total": dinero.numero(dinero.decimal(d.total))})
    return dict_documento(db, d, completo=True)


def _creditos_previos(db: Session, destino: Documento, excepto: int) -> Decimal:
    """Notas de crédito emitidas antes sobre el mismo documento."""
    ids = select(RelacionDocumento.origen_id).where(RelacionDocumento.destino_id == destino.id,
                                                   RelacionDocumento.tipo == "RECTIFICA")
    notas = db.scalars(select(Documento).join(TipoDocumento).where(
        Documento.id.in_(ids), Documento.id != excepto, Documento.estado == "EMITIDO", TipoDocumento.signo < 0))
    return sum((dinero.decimal(n.total) for n in notas), CERO)


def anular(db: Session, user: Usuario, documento_id: int, motivo: str | None, interno: bool = False) -> dict:
    if not interno:
        exigir(user, "comercial.emitir")
    motivo = requerir_motivo(motivo, "void the document")
    d = cargar(db, user, documento_id, bloquear=True)
    if d.estado != "EMITIDO":
        raise ErrorNegocio("Only an issued document can be voided (a draft is deleted).", 409, "transicion_invalida")
    if d.factura_id and not interno:
        raise ErrorNegocio("This document mirrors a supplier invoice: cancel the invoice.", 409, "no_editable")
    if aplicado(db, d.id) > 0:
        raise ErrorNegocio("The document has payments or credit notes applied: void those first.", 409, "con_pagos")
    if d.tipo.signo < 0:  # una nota anulada deja de saldar lo que saldaba
        for a in db.scalars(select(Aplicacion).where(Aplicacion.credito_id == d.id, Aplicacion.activa.is_(True))):
            a.activa = False
    d.estado, d.anulado_en, d.motivo_anulacion = "ANULADO", ahora(), motivo[:500]
    d.version += 1
    db.flush()
    registrar(db, user, "documento", d.id, "anular", None, motivo)
    return dict_documento(db, d, completo=True)


def nota(db: Session, user: Usuario, documento_id: int, datos) -> dict:
    """Borrador de nota de crédito o débito sobre un documento emitido, con
    sus líneas (todas o las indicadas, con la cantidad a corregir)."""
    exigir(user, "comercial.editar")
    origen = cargar(db, user, documento_id)
    tipo = tipo_por_codigo(db, datos.tipo)
    if tipo.clase not in ("NOTA_CREDITO", "NOTA_DEBITO") or tipo.direccion != origen.tipo.direccion:
        raise ErrorNegocio("Choose a credit or debit note of the same direction as the document.", 422, "validacion")
    from app.esquemas.comercial import DocumentoIn, LineaIn

    elegidas = {int(x["indice"]): x for x in (datos.lineas or []) if "indice" in x}
    lineas = []
    for i, x in enumerate(origen.lineas):
        if elegidas and i not in elegidas:
            continue
        cantidad = dinero.decimal(elegidas[i].get("cantidad", x.cantidad)) if elegidas else dinero.decimal(x.cantidad)
        precio = dinero.decimal(elegidas[i].get("precio_unitario", x.precio_unitario)) if elegidas else dinero.decimal(x.precio_unitario)
        lineas.append(LineaIn(articulo_id=x.articulo_id, posicion_oc_id=x.posicion_oc_id, codigo=x.codigo,
                              descripcion=x.descripcion, cantidad=cantidad, unidad=x.unidad, precio_unitario=precio,
                              descuento_pct=dinero.decimal(x.descuento_pct),
                              impuestos=[c for c in (x.impuestos_codigos or "").split(",") if c]))
    soc = db.get(Sociedad, origen.sociedad_id)
    return crear(db, user, DocumentoIn(tipo=tipo.codigo, sociedad=soc.codigo, tercero_id=origen.tercero_id, fecha=date.today(),
                                       moneda=origen.moneda, tipo_cambio=dinero.decimal(origen.tipo_cambio),
                                       condicion_pago=origen.condicion_pago, notas=datos.motivo, origen_id=origen.id,
                                       lineas=lineas))


def estado_cuenta(db: Session, user: Usuario, tercero_id: int, direccion: str = "EMITIDO") -> dict:
    """Documentos con saldo y pagos con importe sin aplicar de un tercero, por moneda."""
    from app.modulos.comercial.pagos import dict_pago, sin_aplicar

    exigir(user, "comercial.ver")
    t = svc_terceros.cargar(db, tercero_id)
    docs = [d for d in db.scalars(_consulta(user, direccion=direccion, tercero_id=t.id)
                                  .where(Documento.estado == "EMITIDO").order_by(Documento.fecha, Documento.id))]
    from app.modelos import Pago

    consulta = select(Pago).where(Pago.tercero_id == t.id, Pago.estado == "REGISTRADO",
                                  Pago.direccion == ("COBRO" if direccion == "EMITIDO" else "PAGO"))
    permitidas = sociedades_de(user)
    if permitidas:
        # Solo los pagos de las sociedades del usuario, como los documentos
        consulta = consulta.join(Sociedad, Sociedad.id == Pago.sociedad_id).where(Sociedad.codigo.in_(permitidas))
    pagos = [p for p in db.scalars(consulta) if sin_aplicar(db, p) > 0]
    por_moneda: dict[str, Decimal] = {}
    abiertos = []
    for d in docs:
        s = saldo(db, d)
        if s > 0:
            abiertos.append(dict_documento(db, d))
            por_moneda[d.moneda] = por_moneda.get(d.moneda, CERO) + s * d.tipo.signo
    for p in pagos:
        por_moneda[p.moneda] = por_moneda.get(p.moneda, CERO) - sin_aplicar(db, p)
    return {"tercero": svc_terceros.dict_tercero(t), "documentos": abiertos, "pagos_sin_aplicar": [dict_pago(db, p) for p in pagos],
            "saldo": {m: dinero.numero(v) for m, v in por_moneda.items()}}


def opciones(db: Session, user: Usuario) -> dict:
    """Lo que piden los formularios comerciales: sociedades, tipos de
    documento, impuestos vigentes, métodos y condiciones de pago."""
    from app.modelos import MetodoPago

    exigir(user, "comercial.ver")
    sembrar(db)
    permitidas = sociedades_de(user)
    hoy = date.today()
    return {
        "sociedades": [{"codigo": s.codigo, "nombre": s.nombre, "moneda": s.moneda}
                       for s in db.scalars(select(Sociedad).where(Sociedad.activa.is_(True)).order_by(Sociedad.codigo))
                       if not permitidas or s.codigo in permitidas],
        "tipos": [{"codigo": x.codigo, "nombre": x.nombre, "clase": x.clase, "direccion": x.direccion, "signo": x.signo,
                   "requiere_origen": x.requiere_origen}
                  for x in db.scalars(select(TipoDocumento).where(TipoDocumento.activo.is_(True)).order_by(TipoDocumento.orden))],
        "impuestos": [{"codigo": x.codigo, "nombre": x.nombre, "tasa": _num(x.tasa), "tipo": x.tipo, "es_retencion": x.es_retencion}
                      for x in db.scalars(select(Impuesto).where(
                          Impuesto.activo.is_(True), or_(Impuesto.vigente_desde.is_(None), Impuesto.vigente_desde <= hoy),
                          or_(Impuesto.vigente_hasta.is_(None), Impuesto.vigente_hasta >= hoy)).order_by(Impuesto.codigo))],
        "metodos_pago": [{"codigo": x.codigo, "nombre": x.nombre}
                         for x in db.scalars(select(MetodoPago).where(MetodoPago.activo.is_(True)).order_by(MetodoPago.orden))],
        "condiciones_pago": [{"codigo": x.codigo, "nombre": x.nombre, "dias": x.dias}
                             for x in db.scalars(select(CondicionPago).where(CondicionPago.activo.is_(True))
                                                 .order_by(CondicionPago.orden))],
        "impuestos_defecto": {db.get(Sociedad, c.sociedad_id).codigo: [x for x in (c.impuestos_defecto or "").split(",") if x]
                              for c in db.scalars(select(ConfiguracionFiscal))},
    }
