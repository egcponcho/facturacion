from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Embarque,
    EventoEmbarque,
    Factura,
    PackingList,
    UnidadCarga,
    Usuario,
)
from .cantidades import nombre_factura, totales_pl
from .common import ErrorNegocio, exigir, registrar, requerir_motivo

ESTADO_POR_EVENTO = {
    "SALIDA": "EN_TRANSITO",
    "ARRIBO": "ARRIBADO",
    "ENTREGA": "ENTREGADO",
    "RECEPCION": "RECIBIDO",
}


def _embarque(db: Session, user: Usuario, embarque_id: int) -> Embarque:
    exigir(user, "transporte.gestionar")
    e = db.get(Embarque, embarque_id)
    if not e:
        raise ErrorNegocio("El embarque no existe.", 404, "no_encontrado")
    return e


def _unidad(db: Session, user: Usuario, unidad_id: int) -> UnidadCarga:
    exigir(user, "transporte.gestionar")
    u = db.get(UnidadCarga, unidad_id)
    if not u:
        raise ErrorNegocio("La unidad de carga no existe.", 404, "no_encontrado")
    return u


def _salio(e: Embarque) -> bool:
    return e.estado != "PLANIFICADO"


def _capacidad(u: UnidadCarga) -> tuple[float | None, float | None]:
    cbm, kg = settings.CAPACIDADES.get(u.tipo, (None, None))
    return u.capacidad_cbm or cbm, u.capacidad_kg or kg


def resumen_unidad(u: UnidadCarga) -> dict:
    pls = [pl for pl in u.packing_lists if pl.estado != "CANCELADO"]
    cajas = 0
    bruto = cbm = 0.0
    for pl in pls:
        t = totales_pl(pl)
        cajas += t["cajas"]
        bruto += t["peso_bruto"]
        cbm += t["cbm"]
    cap_cbm, cap_kg = _capacidad(u)
    pct_cbm = round(cbm * 100 / cap_cbm, 1) if cap_cbm else None
    pct_kg = round(bruto * 100 / cap_kg, 1) if cap_kg else None
    alertas = []
    if pct_cbm and pct_cbm > 100:
        alertas.append(f"El volumen supera la capacidad nominal ({pct_cbm}%).")
    if pct_kg and pct_kg > 100:
        alertas.append(f"El peso supera la capacidad nominal ({pct_kg}%).")
    return {
        "id": u.id,
        "embarque_id": u.embarque_id,
        "tipo": u.tipo,
        "etiqueta": u.etiqueta,
        "numero": u.numero,
        "sello": u.sello,
        "nombre": u.numero or u.etiqueta,
        "facturas": len({pl.factura_id for pl in pls}),
        "proveedores": sorted({pl.factura.proveedor.nombre for pl in pls}),
        "packing_lists": len(pls),
        "tentativas": sum(1 for pl in pls if pl.asignacion == "TENTATIVA"),
        "cajas": cajas,
        "peso_bruto": round(bruto, 2),
        "cbm": round(cbm, 3),
        "capacidad_cbm": cap_cbm,
        "capacidad_kg": cap_kg,
        "pct_cbm": pct_cbm,
        "pct_kg": pct_kg,
        "alertas": alertas,
    }


# ---- Embarques --------------------------------------------------------------
def listar_embarques(db: Session, user: Usuario, estado: str | None = None, q: str | None = None) -> list[dict]:
    exigir(user, "transporte.gestionar")
    consulta = select(Embarque).order_by(Embarque.etd.desc().nullslast(), Embarque.id.desc())
    if estado:
        consulta = consulta.where(Embarque.estado == estado)
    if q:
        patron = f"%{q.strip()}%"
        consulta = consulta.where(Embarque.codigo.ilike(patron) | Embarque.documento_numero.ilike(patron))
    res = []
    for e in db.scalars(consulta).all():
        unidades = [resumen_unidad(u) for u in e.unidades]
        res.append({
            **_cabecera(e),
            "unidades": len(unidades),
            "packing_lists": sum(u["packing_lists"] for u in unidades),
            "tentativas": sum(u["tentativas"] for u in unidades),
            "cbm": round(sum(u["cbm"] for u in unidades), 3),
            "proveedores": sorted({p for u in unidades for p in u["proveedores"]}),
            "ocupacion": [{"id": u["id"], "nombre": u["nombre"], "tipo": u["tipo"], "pct_cbm": u["pct_cbm"],
                           "cbm": u["cbm"]} for u in unidades],
        })
    return res


def _cabecera(e: Embarque) -> dict:
    return {
        "id": e.id,
        "codigo": e.codigo,
        "tipo_transporte": e.tipo_transporte,
        "modalidad": e.modalidad,
        "documento_numero": e.documento_numero,
        "transportista": e.transportista,
        "puerto_origen": e.puerto_origen,
        "puerto_destino": e.puerto_destino,
        "etd": e.etd,
        "eta": e.eta,
        "salida_real": e.salida_real,
        "arribo_real": e.arribo_real,
        "estado": e.estado,
        "observaciones": e.observaciones,
    }


def crear_embarque(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "transporte.gestionar")
    siguiente = (db.scalar(select(func.max(Embarque.id))) or 0) + 1
    e = Embarque(codigo=f"EMB-{siguiente:04d}", **datos.model_dump())
    db.add(e)
    db.flush()
    registrar(db, user, "embarque", e.id, "crear", {"codigo": e.codigo})
    return {"id": e.id, "codigo": e.codigo}


def actualizar_embarque(db: Session, user: Usuario, embarque_id: int, datos) -> dict:
    e = _embarque(db, user, embarque_id)
    campos = datos.model_dump(exclude_unset=True)
    motivo = campos.pop("motivo", None)
    cambios = {}
    for k, v in campos.items():
        if isinstance(v, str):
            v = v.strip() or None
        if getattr(e, k) != v:
            cambios[k] = [getattr(e, k), v]
            setattr(e, k, v)
    if cambios:
        # Los cambios de fechas estimadas quedan en el historial
        registrar(db, user, "embarque", e.id, "editar", cambios, motivo)
    return {"cambios": list(cambios)}


def detalle_embarque(db: Session, user: Usuario, embarque_id: int) -> dict:
    from ..models import Historial

    e = _embarque(db, user, embarque_id)
    historial = db.scalars(
        select(Historial).where(Historial.entidad == "embarque", Historial.entidad_id == e.id)
        .order_by(Historial.fecha.desc())
    ).all()
    return {
        **_cabecera(e),
        "unidades": [resumen_unidad(u) for u in e.unidades],
        "eventos": [
            {"id": ev.id, "tipo": ev.tipo, "fecha": ev.fecha, "ubicacion": ev.ubicacion,
             "observacion": ev.observacion}
            for ev in e.eventos
        ],
        "historial": [
            {"fecha": h.fecha, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
             "usuario": h.usuario.nombre if h.usuario else None}
            for h in historial
        ],
        "tipos_unidad": list(settings.CAPACIDADES),
    }


def registrar_evento(db: Session, user: Usuario, embarque_id: int, datos) -> dict:
    e = _embarque(db, user, embarque_id)
    if datos.tipo == "SALIDA":
        pls = [pl for u in e.unidades for pl in u.packing_lists if pl.estado != "CANCELADO"]
        tentativas = [pl.numero for pl in pls if pl.asignacion == "TENTATIVA"]
        if tentativas:
            raise ErrorNegocio(
                f"Hay {len(tentativas)} packing lists con asignación tentativa. Confírmalos o quítalos antes de "
                "registrar la salida.", 409, "tentativas_pendientes")
        if not pls:
            raise ErrorNegocio("El embarque no tiene packing lists asignados.", 409, "sin_carga")
        e.salida_real = datos.fecha.date()
    if datos.tipo == "ARRIBO":
        e.arribo_real = datos.fecha.date()
    if datos.tipo in ESTADO_POR_EVENTO:
        e.estado = ESTADO_POR_EVENTO[datos.tipo]
    ev = EventoEmbarque(embarque_id=e.id, tipo=datos.tipo, fecha=datos.fecha,
                        ubicacion=datos.ubicacion, observacion=datos.observacion, usuario_id=user.id)
    db.add(ev)
    db.flush()
    registrar(db, user, "embarque", e.id, "evento", {"tipo": datos.tipo, "fecha": datos.fecha})
    return {"id": ev.id, "estado": e.estado}


# ---- Unidades de carga ------------------------------------------------------
def agregar_unidad(db: Session, user: Usuario, embarque_id: int, datos) -> dict:
    e = _embarque(db, user, embarque_id)
    if datos.tipo not in settings.CAPACIDADES:
        raise ErrorNegocio("Tipo de unidad no válido.", 422, "validacion")
    n = sum(1 for u in e.unidades if u.tipo == datos.tipo) + 1
    u = UnidadCarga(tipo=datos.tipo, etiqueta=f"{datos.tipo} #{n}",
                    numero=(datos.numero or "").strip() or None, sello=(datos.sello or "").strip() or None)
    e.unidades.append(u)
    db.flush()
    registrar(db, user, "embarque", e.id, "agregar_unidad", {"unidad": u.etiqueta})
    return {"id": u.id, "etiqueta": u.etiqueta}


def actualizar_unidad(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    u = _unidad(db, user, unidad_id)
    campos = datos.model_dump(exclude_unset=True)
    if "tipo" in campos and campos["tipo"] not in settings.CAPACIDADES:
        raise ErrorNegocio("Tipo de unidad no válido.", 422, "validacion")
    cambios = {}
    for k, v in campos.items():
        v = (v or "").strip() or None if isinstance(v, str) or v is None else v
        if k == "tipo" and not v:
            continue
        if getattr(u, k) != v:
            cambios[k] = [getattr(u, k), v]
            setattr(u, k, v)
    if cambios:
        registrar(db, user, "embarque", u.embarque_id, "editar_unidad", {"unidad": u.etiqueta, **cambios})
    return {"ok": True}


def eliminar_unidad(db: Session, user: Usuario, unidad_id: int) -> dict:
    u = _unidad(db, user, unidad_id)
    if any(pl.estado != "CANCELADO" for pl in u.packing_lists):
        raise ErrorNegocio("La unidad tiene packing lists asignados; quítalos primero.", 409, "con_carga")
    for pl in list(u.packing_lists):
        pl.unidad_carga_id = None
        pl.asignacion = None
    e = u.embarque
    e.unidades.remove(u)
    registrar(db, user, "embarque", e.id, "eliminar_unidad", {"unidad": u.etiqueta})
    return {"ok": True}


def _fila_pl(pl: PackingList) -> dict:
    t = totales_pl(pl)
    f = pl.factura
    puede_confirmar = _listo(pl)
    motivo = None
    if not puede_confirmar:
        pend = []
        if f.estado != "FINALIZADA":
            pend.append("factura sin finalizar")
        if pl.estado != "FINALIZADO":
            pend.append("PL sin finalizar")
        motivo = ", ".join(pend).capitalize() + "."
    return {
        "id": pl.id,
        "numero": pl.numero,
        "estado": pl.estado,
        "asignacion": pl.asignacion,
        "factura_id": f.id,
        "factura": nombre_factura(f),
        "factura_estado": f.estado,
        "proveedor": f.proveedor.nombre,
        "cajas": t["cajas"],
        "peso_bruto": t["peso_bruto"],
        "cbm": t["cbm"],
        "por_unidad": t["por_unidad"],
        "puede_confirmar": puede_confirmar,
        "motivo_no_confirmable": motivo,
    }


def detalle_unidad(db: Session, user: Usuario, unidad_id: int) -> dict:
    u = _unidad(db, user, unidad_id)
    e = u.embarque
    return {
        **resumen_unidad(u),
        "embarque": {**_cabecera(e), "salio": _salio(e)},
        "otras_unidades": [
            {"id": x.id, "nombre": x.numero or x.etiqueta} for x in e.unidades if x.id != u.id
        ],
        "asignados": [_fila_pl(pl) for pl in u.packing_lists if pl.estado != "CANCELADO"],
    }


def disponibles(db: Session, user: Usuario, unidad_id: int, proveedor_id: int | None = None,
                q: str | None = None, solo_listos: bool = False) -> list[dict]:
    """PL sin unidad, agrupados por factura, para asignar completos o parciales."""
    _unidad(db, user, unidad_id)
    consulta = (
        select(PackingList)
        .join(Factura, Factura.id == PackingList.factura_id)
        .where(PackingList.unidad_carga_id.is_(None), PackingList.estado != "CANCELADO",
               Factura.estado != "CANCELADA")
        .order_by(Factura.id, PackingList.id)
    )
    if proveedor_id:
        consulta = consulta.where(Factura.proveedor_id == proveedor_id)
    if q:
        consulta = consulta.where(Factura.numero.ilike(f"%{q.strip()}%"))
    grupos: dict[int, dict] = {}
    for pl in db.scalars(consulta).all():
        fila = _fila_pl(pl)
        if solo_listos and not fila["puede_confirmar"]:
            continue
        g = grupos.setdefault(pl.factura_id, {
            "factura_id": pl.factura_id,
            "factura": fila["factura"],
            "factura_estado": fila["factura_estado"],
            "proveedor": fila["proveedor"],
            "packing_lists": [],
        })
        g["packing_lists"].append(fila)
    res = list(grupos.values())
    for g in res:
        g["cajas"] = sum(p["cajas"] for p in g["packing_lists"])
        g["cbm"] = round(sum(p["cbm"] for p in g["packing_lists"]), 3)
        g["peso_bruto"] = round(sum(p["peso_bruto"] for p in g["packing_lists"]), 2)
        g["todos_confirmables"] = all(p["puede_confirmar"] for p in g["packing_lists"])
    return res


def _cargar_pls(db: Session, ids: list[int]) -> list[PackingList]:
    pls = list(db.scalars(select(PackingList).where(PackingList.id.in_(ids)).with_for_update()).all())
    if len(pls) != len(set(ids)):
        raise ErrorNegocio("Algunos packing lists ya no existen. Recarga.", 404, "no_encontrado")
    return pls


def _listo(pl: PackingList) -> bool:
    return pl.estado == "FINALIZADO" and pl.factura.estado == "FINALIZADA"


def asignar(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    u = _unidad(db, user, unidad_id)
    pls = _cargar_pls(db, datos.pl_ids)
    motivo = (datos.motivo or "").strip() or None
    errores = []
    ids = set(datos.pl_ids)
    for pl in pls:
        ref = f"{nombre_factura(pl.factura)} / {pl.numero}"
        if pl.estado == "CANCELADO":
            errores.append({"pl_id": pl.id, "mensaje": f"{ref}: está cancelado."})
            continue
        anterior = pl.unidad
        if anterior and anterior.id != u.id:
            requiere = pl.asignacion == "CONFIRMADA" or _salio(anterior.embarque)
            if requiere and not motivo:
                errores.append({"pl_id": pl.id, "mensaje":
                    f"{ref} ya está en {anterior.numero or anterior.etiqueta}. Indica el motivo para moverlo."})
        if _salio(u.embarque) and not motivo:
            errores.append({"pl_id": pl.id, "mensaje": f"{ref}: el embarque ya salió; indica el motivo."})
        if datos.modo == "CONFIRMADA" and not _listo(pl):
            errores.append({"pl_id": pl.id, "mensaje":
                f"{ref}: para confirmar, la factura y el PL deben estar finalizados. Puedes asignarlo como tentativo."})
        if settings.FACTURA_EN_UNA_SOLA_UNIDAD:
            otras = {x.unidad_carga_id for x in pl.factura.packing_lists
                     if x.id not in ids and x.unidad_carga_id and x.estado != "CANCELADO"}
            otras.discard(u.id)
            if otras:
                errores.append({"pl_id": pl.id, "mensaje":
                    f"{ref}: otros PL de la misma factura están en otra unidad (regla: una factura, una unidad)."})
    if errores:
        raise ErrorNegocio("No se pudo asignar.", 422, "validacion", errores)
    confirmados = 0
    for pl in pls:
        anterior = pl.unidad
        modo = datos.modo if datos.modo != "AUTO" else ("CONFIRMADA" if _listo(pl) else "TENTATIVA")
        confirmados += modo == "CONFIRMADA"
        pl.unidad = u
        pl.asignacion = modo
        registrar(db, user, "packing_list", pl.id, "asignar_unidad", {
            "unidad": u.numero or u.etiqueta, "embarque": u.embarque.codigo, "modo": modo,
            "anterior": (anterior.numero or anterior.etiqueta) if anterior and anterior.id != u.id else None,
        }, motivo, factura_id=pl.factura_id)
    return {"asignados": len(pls), "confirmados": confirmados, "tentativos": len(pls) - confirmados}


def confirmar(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    u = _unidad(db, user, unidad_id)
    pls = _cargar_pls(db, datos.pl_ids)
    errores = []
    for pl in pls:
        ref = f"{nombre_factura(pl.factura)} / {pl.numero}"
        if pl.unidad_carga_id != u.id:
            errores.append({"pl_id": pl.id, "mensaje": f"{ref} no está en esta unidad."})
        elif not _listo(pl):
            errores.append({"pl_id": pl.id, "mensaje": f"{ref}: la factura y el PL deben estar finalizados."})
    if errores:
        raise ErrorNegocio("No se confirmó ninguno; corrige estos pendientes.", 422, "validacion", errores)
    for pl in pls:
        if pl.asignacion != "CONFIRMADA":
            pl.asignacion = "CONFIRMADA"
            registrar(db, user, "packing_list", pl.id, "confirmar_unidad",
                      {"unidad": u.numero or u.etiqueta}, factura_id=pl.factura_id)
    return {"confirmados": len(pls)}


def desasignar(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    u = _unidad(db, user, unidad_id)
    pls = _cargar_pls(db, datos.pl_ids)
    motivo = None
    if _salio(u.embarque) or any(pl.asignacion == "CONFIRMADA" for pl in pls):
        motivo = requerir_motivo(datos.motivo, "quitar packing lists confirmados o de un embarque que ya salió")
    for pl in pls:
        if pl.unidad_carga_id != u.id:
            raise ErrorNegocio(f"{pl.numero} no está en esta unidad.", 422, "validacion")
    for pl in pls:
        pl.unidad_carga_id = None
        pl.asignacion = None
        registrar(db, user, "packing_list", pl.id, "quitar_unidad",
                  {"unidad": u.numero or u.etiqueta}, motivo, factura_id=pl.factura_id)
    return {"quitados": len(pls)}
