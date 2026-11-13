"""Facturas y pagos a proveedores (cuentas por pagar), con el cuadre de tres vías.

Qué se paga: las facturas comerciales finalizadas de los proveedores. Por cada
una se calcula:

- Importe: la suma de sus líneas (cantidad × precio), en la moneda de la factura.
- Vencimiento: la fecha que se le puso (`facturas.vence`) o, si no tiene, la
  fecha de la factura más los días de la condición de pago de su OC (o
  PLAZO_DEFECTO días si la OC no tiene condición con días).
- Pagado, programado y saldo, con sus pagos (`pagos_proveedor`).
- Cuadre de tres vías, línea por línea: el precio de la factura contra el de la
  OC, y lo facturado contra lo recibido en bodega. Resultado:
    PRECIO        algún precio no es el de la OC;
    POR_RECIBIR   todavía no se recibe todo lo de la factura en bodega;
    CANTIDAD      ya se recibió y lo recibido no es lo facturado;
    CUADRA        OC = factura = recibido.
- Estado de pago: PAGADA (saldo 0), PROGRAMADA (lo programado cubre el saldo),
  VENCIDA (pasó el vencimiento con saldo) o PENDIENTE.

El resumen (gráfico y antigüedad del saldo) va en la moneda de la empresa; lo
de otras monedas se informa aparte, como en el Inicio.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import dinero
from app.core.empresa import configuracion_actual
from app.core.errores import ErrorNegocio
from app.modelos import (
    CondicionPago,
    Factura,
    FacturaLinea,
    Moneda,
    PackingList,
    PagoProveedor,
    PLLinea,
    PosicionOC,
    RecepcionLinea,
    UnidadCarga,
    Usuario,
    ahora,
)
from app.modulos.acceso import visibilidad
from app.modulos.acceso.permisos import asegurar_proveedor, exigir, proveedor_filtro, sociedad_filtro
from app.modulos.comun.historial import registrar

PLAZO_DEFECTO = 30  # días, cuando la OC no tiene condición de pago con plazo
VISTAS = ("por_pagar", "diferencias", "pagadas", "todas")
SEMANAS = 6  # del gráfico de pagos por semana
TRAMOS = (("por_vencer", None), ("1_15", 15), ("16_30", 30), ("mas_30", None))
LIMITE = 1000
CERO = Decimal(0)


# ---- Lectura -------------------------------------------------------------------

def _consulta(user: Usuario, proveedor_id: int | None = None):
    cond = [Factura.estado == "FINALIZADA", *sociedad_filtro(user, Factura.sociedad)]
    prov = proveedor_filtro(user, proveedor_id)
    if prov is not None:
        cond.append(Factura.proveedor_id.in_(prov))
    return (select(Factura).where(*cond)
            .options(selectinload(Factura.lineas).selectinload(FacturaLinea.posicion_oc).selectinload(PosicionOC.oc),
                     selectinload(Factura.pagos), selectinload(Factura.proveedor)))


def _recibido_por_linea(db: Session, linea_ids: list[int]) -> dict[int, Decimal]:
    """Lo recibido en bodega de cada línea de factura (sus líneas de PL vigentes)."""
    res: dict[int, Decimal] = defaultdict(lambda: CERO)
    for i in range(0, len(linea_ids), 900):  # límite de parámetros de sqlite
        for fl_id, cant in db.execute(
                select(PLLinea.factura_linea_id, func.sum(RecepcionLinea.cantidad_recibida))
                .join(RecepcionLinea, RecepcionLinea.pl_linea_id == PLLinea.id)
                .join(PackingList, PackingList.id == PLLinea.pl_id)
                .where(PLLinea.factura_linea_id.in_(linea_ids[i:i + 900]), PackingList.estado != "CANCELADO")
                .group_by(PLLinea.factura_linea_id)):
            res[fl_id] = dinero.decimal(cant or 0)
    return res


def _recepcion_cerrada(db: Session, factura_ids: list[int]) -> dict[int, bool]:
    """¿Ya se recibió en bodega todo lo de la factura? Sí cuando tiene packing
    lists y todas sus unidades de carga quedaron recibidas."""
    estados: dict[int, list[str | None]] = defaultdict(list)
    for i in range(0, len(factura_ids), 900):
        for fid, est in db.execute(
                select(PackingList.factura_id, UnidadCarga.recepcion_estado)
                .outerjoin(UnidadCarga, UnidadCarga.id == PackingList.unidad_carga_id)
                .where(PackingList.factura_id.in_(factura_ids[i:i + 900]), PackingList.estado != "CANCELADO")):
            estados[fid].append(est)
    return {fid: bool(e) and all(x == "RECIBIDA" for x in e) for fid, e in estados.items()}


def _plazos(db: Session) -> dict[str, int]:
    return {c: d for c, d in db.execute(select(CondicionPago.codigo, CondicionPago.dias)) if d is not None}


def _vence(f: Factura, plazos: dict[str, int]) -> date | None:
    if f.vence:
        return f.vence
    base = f.fecha or (f.finalizado_en.date() if f.finalizado_en else None)
    if base is None:
        return None
    ocs = [ln.posicion_oc.oc for ln in f.lineas if ln.posicion_oc is not None]
    dias = next((plazos[oc.condicion_pago] for oc in ocs if oc.condicion_pago in plazos), PLAZO_DEFECTO)
    return base + timedelta(days=dias)


def _cuadre(f: Factura, recibido: dict[int, Decimal], cerrada: bool) -> tuple[str, list[dict]]:
    lineas, precio, cantidad = [], False, False
    for ln in f.lineas:
        fact, rec = dinero.decimal(ln.cantidad), recibido.get(ln.id, CERO)
        dif_precio = not dinero.iguales(ln.precio_unitario, ln.precio_oc)
        dif_cant = cerrada and rec != fact
        precio |= dif_precio
        cantidad |= dif_cant
        lineas.append({
            "id": ln.id, "oc": ln.oc_numero, "posicion": ln.posicion, "codigo": ln.codigo_articulo,
            "descripcion": ln.descripcion, "unidad": ln.unidad,
            "cantidad_oc": dinero.numero(dinero.decimal(ln.posicion_oc.cantidad)) if ln.posicion_oc else None,
            "facturado": dinero.numero(fact), "recibido": dinero.numero(rec),
            "precio_oc": dinero.numero(dinero.decimal(ln.precio_oc)),
            "precio": dinero.numero(dinero.decimal(ln.precio_unitario)),
            "dif_precio": dif_precio, "dif_cantidad": dif_cant,
        })
    estado = "PRECIO" if precio else "CANTIDAD" if cantidad else "CUADRA" if cerrada else "POR_RECIBIR"
    return estado, lineas


def _fila(f: Factura, plazos, recibido, cerradas, hoy: date, con_lineas: bool = False) -> dict:
    moneda = f.moneda
    importe = dinero.total(((ln.cantidad, ln.precio_unitario) for ln in f.lineas), moneda)
    pagado = sum((dinero.decimal(p.importe) for p in f.pagos if p.estado == "PAGADO"), CERO)
    programado = sum((dinero.decimal(p.importe) for p in f.pagos if p.estado == "PROGRAMADO"), CERO)
    saldo = max(importe - pagado, CERO)
    vence = _vence(f, plazos)
    if saldo <= 0:
        estado_pago = "PAGADA"
    elif programado >= saldo:
        estado_pago = "PROGRAMADA"
    elif vence and vence < hoy:
        estado_pago = "VENCIDA"
    else:
        estado_pago = "PENDIENTE"
    cuadre, lineas = _cuadre(f, recibido, cerradas.get(f.id, False))
    fila = {
        "id": f.id, "numero": f.numero, "fecha": f.fecha, "vence": vence, "vence_propio": f.vence is not None,
        "proveedor": {"id": f.proveedor_id, "nombre": f.proveedor.nombre}, "sociedad": f.sociedad,
        "ocs": sorted({ln.oc_numero for ln in f.lineas}), "moneda": moneda,
        "importe": dinero.numero(importe), "pagado": dinero.numero(pagado),
        "programado": dinero.numero(programado), "saldo": dinero.numero(saldo),
        "estado_pago": estado_pago, "cuadre": cuadre,
        "proximo_pago": min((p.fecha_programada for p in f.pagos if p.estado == "PROGRAMADO"), default=None),
    }
    if con_lineas:
        fila["lineas"] = lineas
        fila["pagos"] = [{"id": p.id, "importe": dinero.numero(dinero.decimal(p.importe)), "estado": p.estado,
                          "fecha_programada": p.fecha_programada, "fecha_pago": p.fecha_pago,
                          "referencia": p.referencia} for p in f.pagos]
    return fila


def _filas(db: Session, user: Usuario, facturas: list[Factura], con_lineas: bool = False) -> list[dict]:
    if not facturas:
        return []
    recibido = _recibido_por_linea(db, [ln.id for f in facturas for ln in f.lineas])
    cerradas = _recepcion_cerrada(db, [f.id for f in facturas])
    plazos, hoy = _plazos(db), date.today()
    return [_fila(f, plazos, recibido, cerradas, hoy, con_lineas) for f in facturas]


def _en_vista(fila: dict, vista: str) -> bool:
    if vista == "por_pagar":
        return fila["estado_pago"] != "PAGADA"
    if vista == "diferencias":
        return fila["cuadre"] in ("PRECIO", "CANTIDAD") and fila["estado_pago"] != "PAGADA"
    if vista == "pagadas":
        return fila["estado_pago"] == "PAGADA"
    return True


def lista(db: Session, user: Usuario, vista: str = "por_pagar", proveedor_id: int | None = None) -> dict:
    """Facturas de la vista, ordenadas por vencimiento, y cuántas hay en cada vista (para las pestañas)."""
    exigir(user, "pago.ver")
    vista = vista if vista in VISTAS else "por_pagar"
    facturas = db.scalars(_consulta(user, proveedor_id).order_by(Factura.fecha.desc(), Factura.id.desc()).limit(LIMITE)).all()
    filas = _filas(db, user, list(facturas))
    cuentas = {v: sum(1 for f in filas if _en_vista(f, v)) for v in VISTAS}
    items = sorted((f for f in filas if _en_vista(f, vista)),
                   key=lambda f: (f["vence"] is None, f["vence"] or date.max, f["id"]))
    if vista == "pagadas":
        items.reverse()
    return {"items": items, "cuentas": cuentas, "truncado": len(facturas) == LIMITE}


def detalle(db: Session, user: Usuario, factura_id: int) -> dict:
    """Una factura con el cuadre línea por línea y sus pagos."""
    exigir(user, "pago.ver")
    f = db.scalar(_consulta(user).where(Factura.id == factura_id))
    if f is None:
        raise ErrorNegocio("Document not found.", 404, "no_encontrado")
    return _filas(db, user, [f], con_lineas=True)[0]


def _moneda_base(db: Session) -> str | None:
    """Moneda de la empresa (Configuración → Empresa) o la primera activa de la lista."""
    propia = (configuracion_actual().get("preferencias") or {}).get("moneda")
    return propia or db.scalar(select(Moneda.codigo).where(Moneda.activo.is_(True)).order_by(Moneda.orden, Moneda.codigo).limit(1))


def _semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


def resumen(db: Session, user: Usuario, proveedor_id: int | None = None) -> dict:
    """Pagos por semana (las próximas SEMANAS: lo programado y lo que vence sin
    programar; lo ya vencido sin programar cae en la semana actual) y antigüedad
    del saldo por tramos de días vencidos, en la moneda de la empresa."""
    exigir(user, "pago.ver")
    if visibilidad.oculto("precios"):
        raise ErrorNegocio("Your role does not see prices.", 403, "sin_permiso")
    base, hoy = _moneda_base(db), date.today()
    inicio = _semana(hoy)
    semanas = [inicio + timedelta(weeks=i) for i in range(SEMANAS)]
    programado: dict[date, Decimal] = defaultdict(lambda: CERO)
    sin_programar: dict[date, Decimal] = defaultdict(lambda: CERO)
    tramos: dict[str, Decimal] = defaultdict(lambda: CERO)
    otras: dict[str, Decimal] = defaultdict(lambda: CERO)

    facturas = db.scalars(_consulta(user, proveedor_id).limit(LIMITE * 5)).all()
    plazos = _plazos(db)
    for f in facturas:
        importe = dinero.total(((ln.cantidad, ln.precio_unitario) for ln in f.lineas), f.moneda)
        pagado = sum((dinero.decimal(p.importe) for p in f.pagos if p.estado == "PAGADO"), CERO)
        saldo = importe - pagado
        if saldo <= 0:
            continue
        if f.moneda != base:
            otras[f.moneda] += saldo
            continue
        prog = CERO
        for p in f.pagos:
            if p.estado == "PROGRAMADO":
                prog += dinero.decimal(p.importe)
                programado[max(_semana(p.fecha_programada), inicio)] += dinero.decimal(p.importe)
        resto = max(saldo - prog, CERO)
        vence = _vence(f, plazos)
        if resto > 0 and vence:
            sin_programar[max(_semana(vence), inicio)] += resto
        atraso = (hoy - vence).days if vence else 0
        tramo = "por_vencer" if atraso <= 0 else "1_15" if atraso <= 15 else "16_30" if atraso <= 30 else "mas_30"
        tramos[tramo] += saldo

    total = sum(tramos.values(), CERO)
    num_en = lambda v, m: dinero.numero(dinero.redondear(v, m))  # noqa: E731
    num = lambda v: num_en(v, base)  # noqa: E731
    return {
        "moneda": base,
        "semanas": [{"inicio": s, "programado": num(programado[s]), "sin_programar": num(sin_programar[s])} for s in semanas],
        "antiguedad": [{"tramo": k, "importe": num(tramos[k]),
                        "porcentaje": round(float(tramos[k] / total * 100), 1) if total else 0} for k, _ in TRAMOS],
        "saldo": num(total),
        "otras": [{"moneda": m, "valor": num_en(v, m)} for m, v in sorted(otras.items()) if v],
    }


# ---- Acciones ------------------------------------------------------------------

def _factura(db: Session, user: Usuario, factura_id: int, bloquear: bool = False) -> Factura:
    consulta = select(Factura).where(Factura.id == factura_id)
    f = db.scalar(consulta.with_for_update() if bloquear else consulta)
    if f is None:
        raise ErrorNegocio("Document not found.", 404, "no_encontrado")
    asegurar_proveedor(user, f.proveedor_id, f.sociedad)
    if f.estado != "FINALIZADA":
        raise ErrorNegocio("Only finalized invoices are paid.", 409, "estado_invalido")
    return f


def programar(db: Session, user: Usuario, factura_ids: list[int], fecha: date) -> dict:
    """Programa el pago del saldo sin programar de cada factura para la fecha."""
    exigir(user, "pago.gestionar")
    creados = 0
    for fid in dict.fromkeys(factura_ids):
        f = _factura(db, user, fid, bloquear=True)
        importe = dinero.total(((ln.cantidad, ln.precio_unitario) for ln in f.lineas), f.moneda)
        comprometido = sum((dinero.decimal(p.importe) for p in f.pagos if p.estado in ("PAGADO", "PROGRAMADO")), CERO)
        resto = importe - comprometido
        if resto <= 0:
            continue
        db.add(PagoProveedor(factura_id=f.id, importe=resto, fecha_programada=fecha, estado="PROGRAMADO",
                             creado_por=user.id))
        registrar(db, user, "factura", f.id, "pago_programado",
                  {"importe": dinero.numero(resto), "moneda": f.moneda, "fecha": fecha.isoformat()})
        creados += 1
    if not creados:
        raise ErrorNegocio("The selected invoices have nothing left to schedule.", 409, "sin_saldo")
    db.flush()
    return {"programados": creados}


def _pago(db: Session, user: Usuario, pago_id: int) -> PagoProveedor:
    p = db.scalar(select(PagoProveedor).where(PagoProveedor.id == pago_id).with_for_update())
    if p is None:
        raise ErrorNegocio("Document not found.", 404, "no_encontrado")
    asegurar_proveedor(user, p.factura.proveedor_id, p.factura.sociedad)
    if p.estado != "PROGRAMADO":
        raise ErrorNegocio("Only a scheduled payment can be changed.", 409, "estado_invalido")
    return p


def pagar(db: Session, user: Usuario, pago_id: int, fecha: date, referencia: str | None) -> dict:
    """Marca pagado un pago programado, con la fecha real y la referencia del banco."""
    exigir(user, "pago.gestionar")
    p = _pago(db, user, pago_id)
    p.estado, p.fecha_pago, p.referencia, p.actualizado_en = "PAGADO", fecha, (referencia or "").strip() or None, ahora()
    registrar(db, user, "factura", p.factura_id, "pago_pagado",
              {"importe": dinero.numero(dinero.decimal(p.importe)), "fecha": fecha.isoformat(), "referencia": p.referencia})
    return detalle(db, user, p.factura_id)


def anular(db: Session, user: Usuario, pago_id: int) -> dict:
    """Anula un pago programado (queda en el historial de la factura)."""
    exigir(user, "pago.gestionar")
    p = _pago(db, user, pago_id)
    p.estado, p.actualizado_en = "ANULADO", ahora()
    registrar(db, user, "factura", p.factura_id, "pago_anulado", {"importe": dinero.numero(dinero.decimal(p.importe))})
    return detalle(db, user, p.factura_id)


def cambiar_vence(db: Session, user: Usuario, factura_id: int, vence: date | None) -> dict:
    """Pone o quita (vuelve al plazo de la condición de pago) el vencimiento de la factura."""
    exigir(user, "pago.gestionar")
    f = _factura(db, user, factura_id, bloquear=True)
    f.vence = vence
    registrar(db, user, "factura", f.id, "vencimiento", {"vence": vence.isoformat() if vence else None})
    return detalle(db, user, f.id)
