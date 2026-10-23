"""Recepción en bodega por unidad de carga (contenedor, guía aérea, camión).

Cada unidad se recibe en una bodega o bodega fiscal (un centro) que se elige
al recibir, en una o varias partes: cada registro es un conteo con la fecha
en que se recibió (no la de captura) y queda en el historial. Lo recibido de
cada línea del PL es la suma de sus movimientos (tabla `recepciones`).

La unidad queda recibida cuando:
- los conteos completan lo enviado (sobrantes y daños quedan como diferencias),
- se confirma lo pendiente sin conteo (acción explícita, con permiso de
  recepción), o
- se cierra con faltantes, con motivo.

Después solo se corrige con ajustes, con motivo. Las diferencias abren una
sola alerta por unidad y proveedor, que se actualiza (no se repite). Con
todas sus unidades recibidas, el embarque pasa a recibido y el hito queda con
la fecha del último conteo.
"""
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.core.estados import EMBARQUE, RECEPCION
from app.modelos import (
    Alerta,
    Centro,
    Embarque,
    EventoEmbarque,
    PackingList,
    PLLinea,
    RecepcionLinea,
    RecepcionMovimiento,
    RecepcionRegistro,
    UnidadCarga,
    Usuario,
    ahora,
)
from app.modelos.base import cant
from app.modulos.acceso.permisos import exigir_alguno, tiene
from app.modulos.catalogo import servicio as catalogo
from app.modulos.comun.historial import registrar, requerir_motivo
from app.modulos.facturacion.cantidades import nombre_factura
from app.modulos.maestros.unidades import error_cantidad
from app.modulos.transporte.alcance import en_alcance

VER = ("recepcion.registrar", "transporte.gestionar", "inventario.ver")


def nombre_unidad(u: UnidadCarga) -> str:
    return u.numero or u.etiqueta


def pls_de(u: UnidadCarga) -> list[PackingList]:
    return [pl for pl in u.packing_lists if pl.estado != "CANCELADO"]


def lineas_de(u: UnidadCarga) -> list[PLLinea]:
    return [ln for pl in pls_de(u) for ln in pl.lineas]


def _recibido(ln: PLLinea) -> tuple[float, float]:
    r = ln.recepcion
    return (float(r.cantidad_recibida or 0), float(r.cantidad_danada or 0)) if r else (0.0, 0.0)


def ref_linea(ln: PLLinea) -> str:
    fl = ln.factura_linea
    variante = catalogo.texto(fl.variante)
    return f"{ln.pl.numero} · {fl.codigo_articulo}{' · ' + variante if variante else ''}"


def cargar_unidad(db: Session, user: Usuario, unidad_id: int, *permisos: str, bloquear: bool = False) -> UnidadCarga:
    exigir_alguno(user, *(permisos or VER))
    consulta = select(UnidadCarga).where(UnidadCarga.id == unidad_id)
    u = db.scalar(consulta.with_for_update() if bloquear else consulta)
    if not u or not en_alcance(db, user, u.embarque):
        raise ErrorNegocio("The load unit does not exist.", 404, "no_encontrado")
    return u


# ---- Estado ------------------------------------------------------------------
def totales(u: UnidadCarga) -> dict:
    enviado = recibido = danado = pendiente = 0.0
    for ln in lineas_de(u):
        r, d = _recibido(ln)
        enviado += float(ln.cantidad)
        recibido += r
        danado += d
        pendiente += max(float(ln.cantidad) - r, 0)
    return {"enviado": cant(enviado), "recibido": cant(recibido), "danado": cant(danado), "pendiente": cant(pendiente)}


def diferencias(u: UnidadCarga) -> list[dict]:
    """Faltantes, sobrantes y daños de las líneas de la unidad frente a lo enviado."""
    res = []
    for ln in lineas_de(u):
        r, d = _recibido(ln)
        enviado = float(ln.cantidad)
        tipo = "FALTANTE" if r < enviado else "SOBRANTE" if r > enviado else None
        if tipo or d:
            res.append({"pl_linea_id": ln.id, "pl_id": ln.pl_id, "proveedor_id": ln.pl.factura.proveedor_id,
                        "fila": ref_linea(ln), "esperado": cant(enviado), "recibido": cant(r), "danado": cant(d),
                        "diferencia": cant(r - enviado), "tipo": tipo or "DANO"})
    return res


def resumen(u: UnidadCarga) -> dict:
    """Recepción de una unidad para el embarque y sus listas."""
    return {"recepcion_estado": u.recepcion_estado, "recibida_en": u.recibida_en, "centro": u.centro,
            "liberada_en": u.liberada_en, "entregada_en": u.entregada_en, "recepcion": totales(u)}


# ---- Validaciones ----------------------------------------------------------------
def _exigir_recibible(u: UnidadCarga) -> None:
    e = u.embarque
    if not EMBARQUE.puede("recibir", e.estado):
        raise ErrorNegocio(f"Shipment {e.codigo} has not arrived yet: its load units are received after the arrival.",
                           409, "embarque_no_llego")
    if not pls_de(u):
        raise ErrorNegocio(f"{nombre_unidad(u)} has no cargo to receive.", 409, "sin_carga")


def _fecha(u: UnidadCarga, fecha: date) -> date:
    if fecha > date.today():
        raise ErrorNegocio("The receipt date cannot be in the future.", 422, "fecha_recepcion")
    if u.embarque.arribo_real and fecha < u.embarque.arribo_real:
        raise ErrorNegocio(f"The receipt date cannot be before the arrival ({u.embarque.arribo_real:%m/%d/%Y}).",
                           422, "fecha_recepcion")
    return fecha


def bodegas(db: Session, u: UnidadCarga) -> list[Centro]:
    """Bodegas y bodegas fiscales donde se puede recibir: los centros activos
    de la sociedad del centro del embarque (o todos, si el embarque no tiene)."""
    consulta = select(Centro).where(Centro.activo.is_(True)).order_by(Centro.codigo)
    destino = db.scalar(select(Centro).where(Centro.codigo == u.embarque.centro)) if u.embarque.centro else None
    if destino:
        consulta = consulta.where(Centro.sociedad_id == destino.sociedad_id)
    return list(db.scalars(consulta))


def _centro(db: Session, u: UnidadCarga, codigo: str | None) -> str:
    codigo = (codigo or u.centro or u.embarque.centro or "").strip().upper()
    if not codigo:
        raise ErrorNegocio("Choose the warehouse or bonded warehouse that receives.", 422, "validacion")
    if codigo not in {c.codigo for c in bodegas(db, u)}:
        raise ErrorNegocio(f"{codigo} is not an active warehouse of the company that receives this shipment.",
                           422, "validacion")
    return codigo


def _acumular(ln: PLLinea, cantidad: float, danada: float, fecha: date, user: Usuario, observacion: str | None) -> None:
    rec = ln.recepcion
    if rec is None:
        # Desde el padre: en SQLAlchemy 2 asignar el padre en el hijo no lo agrega a la sesión
        rec = ln.recepcion = RecepcionLinea(cantidad_recibida=0, cantidad_danada=0)
    recibido = cant(float(rec.cantidad_recibida or 0) + cantidad)
    danado = cant(float(rec.cantidad_danada or 0) + danada)
    if recibido < 0 or danado < 0:
        raise ErrorNegocio(f"{ref_linea(ln)}: the adjustment leaves a negative quantity.", 422, "validacion")
    if danado > recibido:
        raise ErrorNegocio(f"{ref_linea(ln)}: damaged ({danado}) cannot exceed received ({recibido}); damaged units "
                           "are part of what was received.", 422, "validacion")
    rec.cantidad_recibida, rec.cantidad_danada = recibido, danado
    if observacion:
        rec.observacion = observacion[:300]
    rec.usuario_id = user.id
    momento = datetime.combine(fecha, time())
    if not rec.fecha or momento > rec.fecha:
        rec.fecha = momento


def _nuevo_registro(db: Session, user: Usuario, u: UnidadCarga, tipo: str, centro: str, fecha: date,
                    observacion: str | None) -> RecepcionRegistro:
    reg = RecepcionRegistro(unidad_carga_id=u.id, centro=centro, fecha=fecha, tipo=tipo,
                            observacion=(observacion or "").strip()[:500] or None, usuario_id=user.id)
    db.add(reg)
    u.centro = centro
    return reg


# ---- Acciones ----------------------------------------------------------------
def registrar_conteo(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    """Conteo (parcial o completo) o ajuste de la recepción de una unidad."""
    u = cargar_unidad(db, user, unidad_id, "recepcion.registrar", bloquear=True)
    _exigir_recibible(u)
    ajuste = datos.tipo == "AJUSTE"
    RECEPCION.exigir("ajustar" if ajuste else "contar", u.recepcion_estado,
                     "recepcion_cerrada" if not ajuste else "transicion_invalida")
    motivo = requerir_motivo(datos.observacion, "adjust a receipt") if ajuste else datos.observacion
    fecha = _fecha(u, datos.fecha)
    centro = _centro(db, u, datos.centro)
    lineas = {ln.id: ln for ln in lineas_de(u)}
    vistos, movimientos, errores = set(), [], []
    for item in datos.lineas:
        ln = lineas.get(item.pl_linea_id)
        if not ln:
            raise ErrorNegocio("A line does not belong to this load unit. Reload.", 422, "validacion")
        if item.pl_linea_id in vistos:
            raise ErrorNegocio(f"{ref_linea(ln)} appears twice.", 422, "validacion")
        vistos.add(item.pl_linea_id)
        cantidad, danada = cant(item.cantidad or 0), cant(item.danada or 0)
        if not cantidad and not danada:
            continue
        unidad = ln.factura_linea.unidad
        for valor in (cantidad, danada):
            if valor and (msg := error_cantidad(abs(valor), unidad)):
                errores.append({"pl_linea_id": ln.id, "mensaje": f"{ref_linea(ln)}: {msg}"})
        if not ajuste:
            if cantidad < 0 or danada < 0:
                errores.append({"pl_linea_id": ln.id, "mensaje": f"{ref_linea(ln)}: a count cannot be negative; "
                                                                  "record an adjustment to correct it."})
            elif danada > cantidad:
                errores.append({"pl_linea_id": ln.id, "mensaje": f"{ref_linea(ln)}: damaged ({danada}) cannot exceed "
                                                                  f"what is counted now ({cantidad})."})
            recibido = _recibido(ln)[0] + cantidad
            if recibido > float(ln.cantidad) and not ((item.observacion or "").strip() or (motivo or "").strip()):
                errores.append({"pl_linea_id": ln.id, "mensaje": f"{ref_linea(ln)}: {cant(recibido)} received of "
                                                                  f"{cant(ln.cantidad)} shipped; explain the surplus."})
        movimientos.append((ln, cantidad, danada, (item.observacion or "").strip() or None))
    if errores:
        raise ErrorNegocio("Check the receipt.", 422, "validacion", errores)
    if not movimientos:
        raise ErrorNegocio("Enter at least one received quantity.", 422, "validacion")
    reg = _nuevo_registro(db, user, u, datos.tipo, centro, fecha, motivo)
    for ln, cantidad, danada, obs in movimientos:
        reg.movimientos.append(RecepcionMovimiento(pl_linea_id=ln.id, cantidad=cantidad, danada=danada, observacion=obs))
        _acumular(ln, cantidad, danada, fecha, user, obs)
    if u.recepcion_estado == "PENDIENTE":
        u.recepcion_estado = "EN_RECEPCION"
    db.flush()
    registrar(db, user, "embarque", u.embarque_id, "recepcion_ajuste" if ajuste else "recepcion_conteo",
              {"unidad": nombre_unidad(u), "bodega": centro, "fecha": fecha, "lineas": len(movimientos)},
              motivo if ajuste else None)
    if u.recepcion_estado == "RECIBIDA":
        _alertas(db, u)  # el ajuste cambia las diferencias
    elif all(_recibido(ln)[0] >= float(ln.cantidad) for ln in lineas.values()):
        _cerrar(db, user, u)  # todo lo enviado ya se contó
    return detalle(db, user, u.id)


def _sin_conteo(db: Session, user: Usuario, u: UnidadCarga, centro: str, fecha: date, observacion: str | None,
                completar: bool = True) -> RecepcionRegistro | None:
    """Lo pendiente de cada línea queda recibido completo y sin daños."""
    pendientes = [(ln, cant(float(ln.cantidad) - _recibido(ln)[0])) for ln in lineas_de(u)]
    pendientes = [(ln, p) for ln, p in pendientes if p > 0]
    reg = None
    if pendientes:
        reg = _nuevo_registro(db, user, u, "SIN_CONTEO", centro, fecha,
                              observacion or f"Pending quantities confirmed without counting by {user.nombre}.")
        for ln, p in pendientes:
            reg.movimientos.append(RecepcionMovimiento(pl_linea_id=ln.id, cantidad=p, danada=0))
            _acumular(ln, p, 0, fecha, user, None)
    db.flush()
    _cerrar(db, user, u, completar=completar)
    return reg


def confirmar_sin_conteo(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    """Confirma lo pendiente de la unidad como recibido completo, sin conteo
    (acción explícita: queda quién lo hizo y en qué bodega)."""
    u = cargar_unidad(db, user, unidad_id, "recepcion.registrar", bloquear=True)
    _exigir_recibible(u)
    RECEPCION.exigir("sin_conteo", u.recepcion_estado, "recepcion_cerrada")
    centro = _centro(db, u, datos.centro)
    fecha = _fecha(u, datos.fecha)
    _sin_conteo(db, user, u, centro, fecha, (datos.observacion or "").strip() or None)
    registrar(db, user, "embarque", u.embarque_id, "recepcion_sin_conteo",
              {"unidad": nombre_unidad(u), "bodega": centro, "fecha": fecha})
    return detalle(db, user, u.id)


def cerrar(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    """Da por terminada la recepción de la unidad: lo que falta queda como
    faltante definitivo (con motivo)."""
    u = cargar_unidad(db, user, unidad_id, "recepcion.registrar", bloquear=True)
    RECEPCION.exigir("cerrar", u.recepcion_estado, "recepcion_cerrada")
    faltan = [d for d in diferencias(u) if d["tipo"] == "FALTANTE"]
    motivo = requerir_motivo(datos.motivo, "close the receipt with shortages") if faltan else (datos.motivo or None)
    _cerrar(db, user, u)
    registrar(db, user, "embarque", u.embarque_id, "recepcion_cierre",
              {"unidad": nombre_unidad(u), "faltantes": len(faltan)}, motivo)
    return detalle(db, user, u.id)


def _cerrar(db: Session, user: Usuario, u: UnidadCarga, completar: bool = True) -> None:
    u.recepcion_estado = "RECIBIDA"
    fechas = list(db.scalars(select(RecepcionRegistro.fecha).where(RecepcionRegistro.unidad_carga_id == u.id)))
    u.recibida_en = max(fechas, default=None) or date.today()
    db.flush()
    _alertas(db, u)
    if completar:
        completar_embarque(db, user, u.embarque)


def completar_embarque(db: Session, user: Usuario, e: Embarque) -> bool:
    """Con todas sus unidades con carga recibidas, el embarque pasa a recibido
    y el hito queda con la fecha del último conteo."""
    unidades = [u for u in e.unidades if pls_de(u)]
    if e.estado == "RECIBIDO" or not unidades or any(u.recepcion_estado != "RECIBIDA" for u in unidades):
        return False
    e.estado = "RECIBIDO"
    ultima = max(u.recibida_en for u in unidades if u.recibida_en)
    momento = ahora() if ultima >= date.today() else datetime.combine(ultima, time(23, 59))
    previo = max((ev.fecha for ev in e.eventos), default=None)
    if previo and momento < previo:
        momento = previo
    db.add(EventoEmbarque(embarque_id=e.id, tipo="RECEPCION", fecha=momento, usuario_id=user.id,
                          observacion="Every load unit was received."))
    registrar(db, user, "embarque", e.id, "evento", {"tipo": "RECEPCION", "automatico": True})
    return True


def _alertas(db: Session, u: UnidadCarga) -> None:
    """Una alerta abierta por unidad y proveedor con sus diferencias; se
    actualiza con cada cambio y se resuelve sola si ya no hay diferencias."""
    por_proveedor: dict[int, list[dict]] = {}
    for d in diferencias(u):
        por_proveedor.setdefault(d["proveedor_id"], []).append(d)
    abiertas = [a for a in db.scalars(select(Alerta).where(Alerta.tipo == "recepcion_diferencia",
                                                             Alerta.resuelta.is_(False)))
                if (a.referencia or {}).get("unidad_id") == u.id]
    for a in abiertas:
        if a.proveedor_id not in por_proveedor:
            a.resuelta = True
    actuales = {a.proveedor_id: a for a in abiertas}
    for prov, difs in por_proveedor.items():
        cuenta = {t: sum(1 for d in difs if d["tipo"] == t) for t in ("FALTANTE", "SOBRANTE", "DANO")}
        partes = [f"{n} {texto}" for n, texto in ((cuenta["FALTANTE"], "short"), (cuenta["SOBRANTE"], "over"),
                                                  (cuenta["DANO"], "damaged")) if n]
        mensaje = f"{nombre_unidad(u)} ({u.embarque.codigo}): lines received with differences: {', '.join(partes)}."
        referencia = {"unidad_id": u.id, "embarque_id": u.embarque_id,
                      "diferencias": [{k: v for k, v in d.items() if k != "proveedor_id"} for d in difs[:50]]}
        a = actuales.get(prov)
        if a is None:
            db.add(Alerta(proveedor_id=prov, tipo="recepcion_diferencia", mensaje=mensaje[:500], referencia=referencia))
        else:
            a.mensaje, a.referencia = mensaje[:500], referencia
    db.flush()


# ---- Consulta ----------------------------------------------------------------
def _acciones(user: Usuario, u: UnidadCarga) -> dict:
    """Qué se puede hacer y, si no, por qué (la pantalla lo muestra junto al botón)."""
    e = u.embarque

    def motivo(accion: str) -> str | None:
        if not tiene(user, "recepcion.registrar"):
            return "You do not have permission to register warehouse receipts."
        if not EMBARQUE.puede("recibir", e.estado):
            return f"Shipment {e.codigo} has not arrived yet."
        if not pls_de(u):
            return "The load unit has no cargo."
        if not RECEPCION.puede(accion, u.recepcion_estado):
            return {"contar": "The receipt is closed: correct it with an adjustment.",
                    "ajustar": "Nothing has been received yet.",
                    "sin_conteo": "The receipt is closed.",
                    "cerrar": "Record a count first."}[accion]
        return None

    return {a: {"permitida": motivo(a) is None, "motivo": motivo(a)} for a in ("contar", "ajustar", "sin_conteo", "cerrar")}


def detalle(db: Session, user: Usuario, unidad_id: int) -> dict:
    u = cargar_unidad(db, user, unidad_id)
    e = u.embarque
    registros = db.scalars(select(RecepcionRegistro).where(RecepcionRegistro.unidad_carga_id == u.id)
                           .order_by(RecepcionRegistro.fecha.desc(), RecepcionRegistro.id.desc())).all()
    nombres = {c.codigo: c for c in bodegas(db, u)}
    usuarios = _usuarios(db, registros)
    filas = []
    for ln in lineas_de(u):
        fl = ln.factura_linea
        r, d = _recibido(ln)
        filas.append({
            "pl_linea_id": ln.id, "pl_id": ln.pl_id, "pl": ln.pl.numero, "factura_id": ln.pl.factura_id,
            "factura": nombre_factura(ln.pl.factura), "proveedor": ln.pl.factura.proveedor.nombre,
            "oc": fl.oc_numero, "codigo": fl.codigo_articulo, "variante": catalogo.texto(fl.variante),
            "descripcion": fl.descripcion_comercial or fl.descripcion, "unidad": fl.unidad,
            "enviado": cant(ln.cantidad), "recibido": cant(r), "danado": cant(d),
            "pendiente": cant(max(float(ln.cantidad) - r, 0)), "diferencia": cant(r - float(ln.cantidad)),
            "observacion": ln.recepcion.observacion if ln.recepcion else None,
        })
    return {
        "unidad": {
            "id": u.id, "nombre": nombre_unidad(u), "tipo": u.tipo, "sello": u.sello, **resumen(u),
            "centro_nombre": nombres[u.centro].nombre if u.centro in nombres else None,
            "embarque": {"id": e.id, "codigo": e.codigo, "estado": e.estado, "tipo_transporte": e.tipo_transporte,
                         "arribo_real": e.arribo_real, "centro": e.centro, "documento_numero": e.documento_numero},
        },
        "lineas": filas,
        "totales": totales(u),
        # Lo que falta solo es faltante cuando la recepción se cerró; antes es pendiente
        "diferencias": [{k: v for k, v in d.items() if k != "proveedor_id"} for d in diferencias(u)
                        if d["tipo"] != "FALTANTE" or u.recepcion_estado == "RECIBIDA"],
        "registros": [{
            "id": g.id, "fecha": g.fecha, "tipo": g.tipo, "centro": g.centro,
            "centro_nombre": nombres[g.centro].nombre if g.centro in nombres else None,
            "observacion": g.observacion, "usuario": usuarios.get(g.usuario_id),
            "creado_en": g.creado_en, "lineas": len(g.movimientos),
            "cantidad": cant(sum(float(m.cantidad) for m in g.movimientos)),
            "danada": cant(sum(float(m.danada) for m in g.movimientos)),
            "movimientos": [{"pl_linea_id": m.pl_linea_id, "cantidad": cant(m.cantidad), "danada": cant(m.danada),
                             "observacion": m.observacion} for m in g.movimientos],
        } for g in registros],
        "bodegas": [{"codigo": c.codigo, "nombre": c.nombre, "tipo": c.tipo} for c in nombres.values()],
        "acciones": _acciones(user, u),
    }


def _usuarios(db: Session, registros) -> dict[int, str]:
    ids = {g.usuario_id for g in registros if g.usuario_id}
    if not ids:
        return {}
    return {i: n for i, n in db.execute(select(Usuario.id, Usuario.nombre).where(Usuario.id.in_(ids)))}


def de_pl(db: Session, user: Usuario, pl: PackingList) -> dict | None:
    """Recepción del PL (para su pantalla): la de su unidad y sus líneas."""
    u = pl.unidad
    if not u:
        return None
    return {"unidad_id": u.id, "unidad": nombre_unidad(u), "embarque_id": u.embarque_id, "embarque": u.embarque.codigo,
            **resumen(u), "puede_registrar": _acciones(user, u)["contar"]["permitida"]}
