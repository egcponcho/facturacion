"""Cobros y pagos y su aplicación a documentos.

Un cobro (de un cliente) salda documentos emitidos; un pago (a un proveedor),
documentos recibidos. Un pago puede repartirse entre varios documentos y un
documento puede saldarse con varios pagos (parciales). Lo que no se aplica
queda como saldo a favor del tercero (anticipo) para aplicarlo después.
Nunca se aplica más que el saldo de un documento ni más que lo que queda del
pago: el documento se bloquea mientras se aplica (dos cobros a la vez no
pueden pasar su saldo).
"""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import dinero
from app.core.errores import ErrorNegocio
from app.modelos import Aplicacion, Documento, MetodoPago, Moneda, Pago, Sociedad, Tercero, Usuario, Vencimiento, ahora
from app.modulos.acceso.permisos import exigir, sociedades_de
from app.modulos.comercial import documentos as docs
from app.modulos.comercial import terceros as svc_terceros
from app.modulos.comun import tabla
from app.modulos.comun.historial import registrar, requerir_motivo
from app.modulos.comun.texto import filtro_texto

CERO = dinero.CERO


def aplicado(db: Session, p: Pago) -> Decimal:
    return dinero.decimal(db.scalar(select(func.coalesce(func.sum(Aplicacion.importe), 0))
                                    .where(Aplicacion.pago_id == p.id, Aplicacion.activa.is_(True))))


def sin_aplicar(db: Session, p: Pago) -> Decimal:
    return CERO if p.estado != "REGISTRADO" else max(dinero.decimal(p.importe) - aplicado(db, p), CERO)


def dict_pago(db: Session, p: Pago, completo: bool = False) -> dict:
    metodo = db.get(MetodoPago, p.metodo_pago_id) if p.metodo_pago_id else None
    r = {"id": p.id, "direccion": p.direccion, "estado": p.estado, "tercero_id": p.tercero_id, "tercero": p.tercero.nombre,
         "sociedad": db.get(Sociedad, p.sociedad_id).codigo, "fecha": p.fecha, "moneda": p.moneda,
         "tipo_cambio": dinero.numero(dinero.decimal(p.tipo_cambio)), "importe": dinero.numero(dinero.decimal(p.importe)),
         "aplicado": dinero.numero(aplicado(db, p)), "sin_aplicar": dinero.numero(sin_aplicar(db, p)),
         "metodo_pago": metodo.codigo if metodo else None, "metodo_pago_nombre": metodo.nombre if metodo else None,
         "referencia": p.referencia, "notas": p.notas, "motivo_anulacion": p.motivo_anulacion}
    if completo:
        r["aplicaciones"] = []
        for a in db.scalars(select(Aplicacion).where(Aplicacion.pago_id == p.id).order_by(Aplicacion.id)):
            d = db.get(Documento, a.documento_id)
            r["aplicaciones"].append({"id": a.id, "documento_id": d.id, "documento": d.numero or d.referencia_externa,
                                      "importe": dinero.numero(dinero.decimal(a.importe)), "activa": a.activa,
                                      "vencimiento_id": a.vencimiento_id})
    return r


COLUMNAS = {"direccion": Pago.direccion, "estado": Pago.estado, "tercero": Tercero.nombre, "moneda": Pago.moneda,
            "fecha": Pago.fecha, "sociedad": Sociedad.codigo}


def _consulta(user: Usuario, direccion=None, estado=None, q=None, tercero_id=None):
    exigir(user, "comercial.ver")
    c = select(Pago).join(Tercero, Tercero.id == Pago.tercero_id).join(Sociedad, Sociedad.id == Pago.sociedad_id)
    if direccion:
        c = c.where(Pago.direccion == direccion.upper())
    if estado:
        c = c.where(Pago.estado == estado.upper())
    if tercero_id:
        c = c.where(Pago.tercero_id == tercero_id)
    if q and q.strip():
        c = c.where(filtro_texto(q, Pago.referencia, Tercero.nombre, Tercero.codigo))
    permitidas = sociedades_de(user)
    if permitidas:
        c = c.where(Sociedad.codigo.in_(permitidas))
    return c


def listar(db: Session, user: Usuario, direccion=None, estado=None, q=None, tercero_id=None, page=1, size=25, orden=None,
           filtros=None) -> dict:
    c = tabla.aplicar(_consulta(user, direccion, estado, q, tercero_id), COLUMNAS, filtros or {})
    col, _, dirc = (orden or "").partition(":")
    expr = {**COLUMNAS, "importe": Pago.importe}.get(col)
    c = c.order_by((expr.desc() if dirc == "desc" else expr.asc()) if expr is not None else Pago.fecha.desc(), Pago.id.desc())
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    return {"items": [dict_pago(db, p) for p in db.scalars(c.offset((page - 1) * size).limit(size))], "total": total}


def valores(db: Session, user: Usuario, columna: str, buscar=None, filtros=None, **kw) -> list[dict]:
    expr = tabla.columna_valida(COLUMNAS, columna)
    c = tabla.aplicar(_consulta(user, **kw), COLUMNAS, filtros or {}, excepto=columna)
    return tabla.valores(db, c, expr, buscar)


def cargar(db: Session, user: Usuario, pago_id: int) -> Pago:
    p = db.scalar(select(Pago).where(Pago.id == pago_id).with_for_update())
    if not p:
        raise ErrorNegocio("The payment does not exist.", 404, "no_encontrado")
    permitidas = sociedades_de(user)
    if permitidas and db.get(Sociedad, p.sociedad_id).codigo not in permitidas:
        raise ErrorNegocio("The payment does not exist.", 404, "no_encontrado")
    return p


def detalle(db: Session, user: Usuario, pago_id: int) -> dict:
    exigir(user, "comercial.ver")
    return dict_pago(db, cargar(db, user, pago_id), completo=True)


def _aplicar(db: Session, user: Usuario, p: Pago, aplicaciones) -> None:
    disponible = sin_aplicar(db, p)
    errores = []
    for i, a in enumerate(aplicaciones, start=1):
        d = docs.cargar(db, user, a.documento_id, bloquear=True)
        importe = dinero.redondear(a.importe, p.moneda)
        esperado = "EMITIDO" if p.direccion == "COBRO" else "RECIBIDO"
        if d.estado != "EMITIDO" or not d.tipo.afecta_saldo or d.tipo.signo < 0 or d.tipo.direccion != esperado:
            errores.append({"campo": f"aplicaciones.{i}", "mensaje": f"{d.numero or d.referencia_externa or d.id}: a "
                            f"{'collection' if p.direccion == 'COBRO' else 'payment'} only settles issued "
                            f"{'sales' if p.direccion == 'COBRO' else 'received'} invoices and debit notes."})
            continue
        if d.tercero_id != p.tercero_id or d.moneda != p.moneda:
            errores.append({"campo": f"aplicaciones.{i}", "mensaje": f"{d.numero or d.referencia_externa}: "
                            "it is of another business partner or currency."})
            continue
        pendiente = docs.saldo(db, d)
        if importe > pendiente:
            errores.append({"campo": f"aplicaciones.{i}", "mensaje": f"{d.numero or d.referencia_externa}: its balance is "
                            f"{dinero.numero(pendiente)}; {dinero.numero(importe)} cannot be applied."})
            continue
        if importe > disponible:
            errores.append({"campo": f"aplicaciones.{i}", "mensaje": "The applied amounts exceed the payment."})
            continue
        if a.vencimiento_id and not db.scalar(select(Vencimiento.id).where(Vencimiento.id == a.vencimiento_id,
                                                                           Vencimiento.documento_id == d.id)):
            errores.append({"campo": f"aplicaciones.{i}", "mensaje": "The installment is not of that document."})
            continue
        db.add(Aplicacion(pago_id=p.id, documento_id=d.id, vencimiento_id=a.vencimiento_id, importe=importe, activa=True))
        db.flush()
        disponible -= importe
    if errores:
        raise ErrorNegocio("The payment could not be applied.", 422, "validacion", errores)


def registrar_pago(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "comercial.pagos")
    if datos.direccion not in ("COBRO", "PAGO"):
        raise ErrorNegocio("Choose collection or payment.", 422, "validacion")
    t = svc_terceros.cargar(db, datos.tercero_id)
    soc = docs._sociedad(db, user, datos.sociedad)
    moneda = datos.moneda.upper()
    if not db.scalar(select(Moneda.id).where(Moneda.codigo == moneda)):
        raise ErrorNegocio(f"The currency {moneda} is not in the catalog.", 422, "validacion")
    metodo = None
    if datos.metodo_pago:
        metodo = db.scalar(select(MetodoPago).where(MetodoPago.codigo == datos.metodo_pago.upper(), MetodoPago.activo.is_(True)))
        if not metodo:
            raise ErrorNegocio(f"The payment method {datos.metodo_pago} is not in the catalog.", 422, "validacion")
    p = Pago(direccion=datos.direccion, estado="REGISTRADO", tercero_id=t.id, sociedad_id=soc.id, fecha=datos.fecha,
             moneda=moneda, tipo_cambio=datos.tipo_cambio or 1, importe=dinero.redondear(datos.importe, moneda),
             metodo_pago_id=metodo.id if metodo else None, referencia=(datos.referencia or "").strip() or None,
             notas=datos.notas, creado_por=user.id)
    db.add(p)
    db.flush()
    _aplicar(db, user, p, datos.aplicaciones)
    registrar(db, user, "pago", p.id, "registrar", {"importe": dinero.numero(dinero.decimal(p.importe)), "moneda": moneda,
                                                    "aplicaciones": len(datos.aplicaciones)})
    return dict_pago(db, p, completo=True)


def aplicar(db: Session, user: Usuario, pago_id: int, datos) -> dict:
    exigir(user, "comercial.pagos")
    p = cargar(db, user, pago_id)
    if p.estado != "REGISTRADO":
        raise ErrorNegocio("A voided payment cannot be applied.", 409, "transicion_invalida")
    _aplicar(db, user, p, datos.aplicaciones)
    registrar(db, user, "pago", p.id, "aplicar", {"aplicaciones": len(datos.aplicaciones)})
    return dict_pago(db, p, completo=True)


def anular(db: Session, user: Usuario, pago_id: int, motivo: str | None) -> dict:
    exigir(user, "comercial.pagos")
    motivo = requerir_motivo(motivo, "void the payment")
    p = cargar(db, user, pago_id)
    if p.estado != "REGISTRADO":
        raise ErrorNegocio("The payment is already voided.", 409, "transicion_invalida")
    for a in db.scalars(select(Aplicacion).where(Aplicacion.pago_id == p.id, Aplicacion.activa.is_(True))):
        a.activa = False
    p.estado, p.anulado_en, p.motivo_anulacion = "ANULADO", ahora(), motivo[:500]
    db.flush()
    registrar(db, user, "pago", p.id, "anular", None, motivo)
    return dict_pago(db, p, completo=True)
