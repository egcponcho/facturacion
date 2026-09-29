from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Centro,
    Embarque,
    EventoEmbarque,
    Factura,
    PackingList,
    Puerto,
    UnidadCarga,
    Usuario,
)
from .cantidades import nombre_factura, totales_pl
from .common import ErrorNegocio, exigir, registrar, requerir_motivo
from .partes import partes

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


def _exigir_planificado(e: Embarque, accion: str) -> None:
    """Después de la salida la carga está cerrada: lo que viaja ya viaja."""
    if _salio(e):
        raise ErrorNegocio(f"El embarque {e.codigo} ya salió; no se puede {accion}. La carga quedó cerrada al zarpar.",
                           409, "embarque_cerrado")


# Qué evento se puede registrar en cada estado, en orden
EVENTOS_PERMITIDOS = {
    "PLANIFICADO": {"RECOLECCION", "SALIDA", "OTRO"},
    "EN_TRANSITO": {"TRANSITO", "ARRIBO", "OTRO"},
    "ARRIBADO": {"LIBERACION", "ENTREGA", "OTRO"},
    "ENTREGADO": {"RECEPCION", "OTRO"},
    "RECIBIDO": {"OTRO"},
}


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
    tiendas = [pl_linea.factura_linea.posicion_oc.oc.fecha_tienda for pl in pls for pl_linea in pl.lineas
               if pl_linea.factura_linea.posicion_oc.oc.fecha_tienda]
    llegada = u.embarque.arribo_real or u.embarque.eta
    tienda = min(tiendas) if tiendas else None
    return {
        "id": u.id,
        "embarque_id": u.embarque_id,
        "fecha_tienda": tienda,
        # Días entre la llegada (real o estimada) y la primera fecha requerida en tienda
        "holgura_dias": (tienda - llegada).days if tienda and llegada else None,
        "marcas": sorted({pl_linea.factura_linea.marca for pl in pls for pl_linea in pl.lineas
                          if pl_linea.factura_linea.marca}),
        "recolectados": sum(1 for pl in pls if pl.recolectado_en),
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
        "centro": e.centro,
        "etd": e.etd,
        "eta": e.eta,
        "salida_real": e.salida_real,
        "arribo_real": e.arribo_real,
        "estado": e.estado,
        "observaciones": e.observaciones,
    }


def _ruta(db: Session, campos: dict, actual: Embarque | None = None) -> dict:
    """Puertos del catálogo y centro de llegada: el puerto de destino debe ser
    el del centro. Si falta el puerto de destino se toma el del centro."""
    for k in ("puerto_origen", "puerto_destino", "centro"):
        if isinstance(campos.get(k), str):
            campos[k] = campos[k].strip().upper() or None
    valor = lambda k: campos[k] if k in campos else (getattr(actual, k) if actual else None)  # noqa: E731
    errores = []
    for k, texto in (("puerto_origen", "El puerto de origen"), ("puerto_destino", "El puerto de destino")):
        if k in campos and campos[k] and not db.scalar(select(Puerto.id).where(Puerto.codigo == campos[k])):
            errores.append({"campo": k, "mensaje": f"{texto} {campos[k]} no está en el catálogo de puertos."})
    centro = valor("centro")
    if centro:
        c = db.scalar(select(Centro).where(Centro.codigo == centro))
        if not c:
            errores.append({"campo": "centro", "mensaje": f"El centro {centro} no existe."})
        elif c.puerto:
            if not valor("puerto_destino"):
                campos["puerto_destino"] = c.puerto
            elif valor("puerto_destino") != c.puerto:
                errores.append({"campo": "puerto_destino", "mensaje":
                                f"El centro {centro} recibe por {c.puerto}; el puerto de destino debe coincidir."})
    if errores:
        raise ErrorNegocio("Revisa la ruta del embarque.", 422, "validacion", errores)
    return campos


def crear_embarque(db: Session, user: Usuario, datos) -> dict:
    exigir(user, "transporte.gestionar")
    siguiente = (db.scalar(select(func.max(Embarque.id))) or 0) + 1
    e = Embarque(codigo=f"EMB-{siguiente:04d}", **_ruta(db, datos.model_dump()))
    db.add(e)
    db.flush()
    registrar(db, user, "embarque", e.id, "crear", {"codigo": e.codigo})
    return {"id": e.id, "codigo": e.codigo}


def actualizar_embarque(db: Session, user: Usuario, embarque_id: int, datos) -> dict:
    e = _embarque(db, user, embarque_id)
    campos = datos.model_dump(exclude_unset=True)
    motivo = campos.pop("motivo", None)
    if {"tipo_transporte", "modalidad"} & set(campos) and e.unidades:
        cambia = any(campos.get(k, getattr(e, k)) != getattr(e, k) for k in ("tipo_transporte", "modalidad"))
        if cambia:
            raise ErrorNegocio("No se puede cambiar el tipo de transporte de un embarque que ya tiene unidades.",
                               409, "embarque_con_unidades")
    if _salio(e):
        bloqueados = {"etd", "puerto_origen", "tipo_transporte", "modalidad", "transportista", "documento_numero",
                      "centro"}
        if e.estado != "PLANIFICADO" and e.arribo_real:
            bloqueados |= {"eta", "puerto_destino"}
        tocados = [k for k in campos if k in bloqueados and campos[k] != getattr(e, k)]
        if tocados:
            raise ErrorNegocio("Esos datos quedaron fijos al registrar la salida"
                               + (" y el arribo" if e.arribo_real else "") + ": " + ", ".join(tocados) + ".",
                               409, "embarque_cerrado")
    if {"puerto_origen", "puerto_destino", "centro"} & set(campos):
        if "centro" in campos and campos["centro"] and campos["centro"] != e.centro:
            otros = {pl.factura.centro for u in e.unidades for pl in u.packing_lists
                     if pl.estado != "CANCELADO"} - {campos["centro"].strip().upper()}
            if otros:
                raise ErrorNegocio(f"El embarque ya lleva carga para el centro {', '.join(sorted(otros))}.",
                                   409, "centro_distinto")
            campos.setdefault("puerto_destino", None)
        campos = _ruta(db, campos, e)
    etd = campos.get("etd", e.etd)
    eta = campos.get("eta", e.eta)
    if etd and eta and eta < etd:
        raise ErrorNegocio("La ETA no puede ser anterior a la ETD.", 422, "validacion")
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
        "notify": partes(db, None, e.centro)["notify"] if e.centro else None,
        "cerrado": _salio(e),
        "eventos_permitidos": sorted(EVENTOS_PERMITIDOS[e.estado]),
    }


def _documentos_salida(e: Embarque, pls: list[PackingList]) -> list[str]:
    """Datos que exige el documento de transporte (BL/AWB/carta de porte)."""
    faltan = []
    if not e.documento_numero:
        faltan.append("Número de BL, AWB o carta de porte.")
    if not e.transportista:
        faltan.append("Naviera o transportista.")
    if not e.puerto_origen or not e.puerto_destino:
        faltan.append("Origen y destino.")
    if not e.centro:
        faltan.append("Centro de llegada (notify party).")
    con_carga = {pl.unidad_carga_id for pl in pls}
    for u in e.unidades:
        if u.id not in con_carga:
            continue
        if not u.numero:
            faltan.append(f"{u.etiqueta}: número de contenedor o guía.")
        if e.tipo_transporte == "MARITIMO" and e.modalidad == "FCL" and not u.sello:
            faltan.append(f"{u.numero or u.etiqueta}: número de sello.")
    return faltan


def registrar_evento(db: Session, user: Usuario, embarque_id: int, datos) -> dict:
    e = _embarque(db, user, embarque_id)
    nombres = {"RECOLECCION": "recolección", "SALIDA": "salida", "TRANSITO": "tránsito", "ARRIBO": "arribo",
               "LIBERACION": "liberación", "ENTREGA": "entrega", "RECEPCION": "recepción", "OTRO": "evento"}
    if datos.tipo not in EVENTOS_PERMITIDOS[e.estado]:
        raise ErrorNegocio(f"No se puede registrar {nombres[datos.tipo]} con el embarque en estado "
                           f"{e.estado.replace('_', ' ').lower()}. Sigue el orden: recolección, salida, arribo, "
                           "entrega y recepción.", 409, "orden_eventos")
    ultimo = max((ev.fecha for ev in e.eventos), default=None)
    if ultimo and datos.fecha < ultimo and datos.tipo != "OTRO":
        raise ErrorNegocio(f"La fecha no puede ser anterior al último evento ({ultimo:%d/%m/%Y %H:%M}).",
                           422, "fecha_evento")
    if datos.fecha.date() > date.today() + timedelta(days=1):
        raise ErrorNegocio("No se registran eventos con fecha futura; usa ETD y ETA para lo planificado.",
                           422, "fecha_evento")
    if datos.tipo == "SALIDA":
        pls = [pl for u in e.unidades for pl in u.packing_lists if pl.estado != "CANCELADO"]
        tentativas = [pl.numero for pl in pls if pl.asignacion == "TENTATIVA"]
        if tentativas:
            raise ErrorNegocio(
                f"Hay {len(tentativas)} packing lists con asignación tentativa. Confírmalos o quítalos antes de "
                "registrar la salida.", 409, "tentativas_pendientes")
        if not pls:
            raise ErrorNegocio("El embarque no tiene packing lists asignados.", 409, "sin_carga")
        faltan = _documentos_salida(e, pls)
        if faltan:
            raise ErrorNegocio("Faltan datos obligatorios del transporte para registrar la salida.", 422,
                               "datos_transporte", [{"mensaje": m} for m in faltan])
        e.salida_real = datos.fecha.date()
        # Lo que zarpó ya fue recolectado: se completa la fecha si faltaba
        for pl in pls:
            if not pl.recolectado_en:
                pl.recolectado_en = datos.fecha.date()
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
    _exigir_planificado(e, "agregar contenedores")
    if e.tipo_transporte != "MARITIMO" and datos.tipo in ("20GP", "40GP", "40HC"):
        raise ErrorNegocio("Un contenedor marítimo solo va en un embarque marítimo.", 422, "validacion")
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
    if any(campos.get(k) != getattr(u, k) for k in campos):
        _exigir_planificado(u.embarque, "cambiar el contenedor, su número o su sello")
    if campos.get("tipo") and campos["tipo"] != u.tipo and any(pl.estado != "CANCELADO" for pl in u.packing_lists):
        raise ErrorNegocio("No se puede cambiar el tipo de un contenedor con carga.", 409, "con_carga")
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
    _exigir_planificado(u.embarque, "eliminar contenedores")
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
        "recolectado_en": pl.recolectado_en,
        "marcas": sorted({x.factura_linea.marca for x in pl.lineas if x.factura_linea.marca}),
        "ocs": sorted({x.factura_linea.oc_numero for x in pl.lineas}),
        "fecha_xf": min((x.factura_linea.posicion_oc.oc.fecha_xf for x in pl.lineas
                         if x.factura_linea.posicion_oc.oc.fecha_xf), default=None),
        "fecha_tienda": min((x.factura_linea.posicion_oc.oc.fecha_tienda for x in pl.lineas
                             if x.factura_linea.posicion_oc.oc.fecha_tienda), default=None),
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
    """PL sin unidad, agrupados por factura, para asignar completos o parciales.
    Si el embarque ya tiene centro, solo lo que va a ese centro."""
    u = _unidad(db, user, unidad_id)
    consulta = (
        select(PackingList)
        .join(Factura, Factura.id == PackingList.factura_id)
        .where(PackingList.unidad_carga_id.is_(None), PackingList.estado != "CANCELADO",
               Factura.estado != "CANCELADA")
        .order_by(Factura.id, PackingList.id)
    )
    if proveedor_id:
        consulta = consulta.where(Factura.proveedor_id == proveedor_id)
    if u.embarque.centro:
        consulta = consulta.where(Factura.centro == u.embarque.centro)
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
            "centro": pl.factura.centro,
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
    _exigir_planificado(u.embarque, "agregar carga")
    pls = _cargar_pls(db, datos.pl_ids)
    e = u.embarque
    if not e.centro:
        # Sin centro todavía: lo define la primera carga, y no se mezclan centros
        centros = {pl.factura.centro for pl in pls} | {
            x.factura.centro for un in e.unidades for x in un.packing_lists if x.estado != "CANCELADO"}
        centros.discard(None)
        if len(centros) > 1:
            raise ErrorNegocio("Un embarque llega a un solo centro; la selección va a "
                               + ", ".join(sorted(centros)) + ".", 422, "centro_distinto")
        if centros:
            ruta = _ruta(db, {"centro": centros.pop()}, e)
            e.centro = ruta["centro"]
            e.puerto_destino = ruta.get("puerto_destino", e.puerto_destino)
    motivo = (datos.motivo or "").strip() or None
    errores = []
    ids = set(datos.pl_ids)
    for pl in pls:
        ref = f"{nombre_factura(pl.factura)} / {pl.numero}"
        if pl.estado == "CANCELADO":
            errores.append({"pl_id": pl.id, "mensaje": f"{ref}: está cancelado."})
            continue
        if pl.factura.estado == "CANCELADA":
            errores.append({"pl_id": pl.id, "mensaje": f"{ref}: la factura está cancelada."})
            continue
        if u.embarque.centro and pl.factura.centro != u.embarque.centro:
            errores.append({"pl_id": pl.id, "mensaje":
                f"{ref} va al centro {pl.factura.centro}; el embarque llega al centro {u.embarque.centro}."})
            continue
        anterior = pl.unidad
        if anterior and anterior.id != u.id:
            if _salio(anterior.embarque):
                errores.append({"pl_id": pl.id, "mensaje":
                    f"{ref} ya viaja en {anterior.numero or anterior.etiqueta} ({anterior.embarque.codigo})."})
                continue
            if pl.asignacion == "CONFIRMADA" and not motivo:
                errores.append({"pl_id": pl.id, "mensaje":
                    f"{ref} está confirmado en {anterior.numero or anterior.etiqueta}. Indica el motivo para moverlo."})
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
    # Capacidad nominal: no se asigna más volumen ni peso del que cabe
    nuevos = [pl for pl in pls if pl.unidad_carga_id != u.id]
    actual = resumen_unidad(u)
    extra = [totales_pl(pl) for pl in nuevos]
    cbm = actual["cbm"] + sum(t["cbm"] for t in extra)
    kg = actual["peso_bruto"] + sum(t["peso_bruto"] for t in extra)
    excesos = []
    if actual["capacidad_cbm"] and cbm > actual["capacidad_cbm"]:
        excesos.append(f"volumen {cbm:.2f} de {actual['capacidad_cbm']:.0f} m³")
    if actual["capacidad_kg"] and kg > actual["capacidad_kg"]:
        excesos.append(f"peso {kg:,.0f} de {actual['capacidad_kg']:,.0f} kg")
    if excesos:
        raise ErrorNegocio(f"No cabe en {u.numero or u.etiqueta}: " + " y ".join(excesos)
                           + ". Usa otro contenedor para el resto.", 422, "capacidad")
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
    _exigir_planificado(u.embarque, "confirmar carga")
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
    _exigir_planificado(u.embarque, "quitar carga")
    pls = _cargar_pls(db, datos.pl_ids)
    motivo = None
    if any(pl.asignacion == "CONFIRMADA" for pl in pls):
        motivo = requerir_motivo(datos.motivo, "quitar packing lists confirmados")
    for pl in pls:
        if pl.unidad_carga_id != u.id:
            raise ErrorNegocio(f"{pl.numero} no está en esta unidad.", 422, "validacion")
    for pl in pls:
        pl.unidad_carga_id = None
        pl.asignacion = None
        pl.recolectado_en = None
        registrar(db, user, "packing_list", pl.id, "quitar_unidad",
                  {"unidad": u.numero or u.etiqueta}, motivo, factura_id=pl.factura_id)
    return {"quitados": len(pls)}


def recoleccion(db: Session, user: Usuario, datos) -> dict:
    """Marca los PL como recolectados en la bodega del proveedor (o quita la
    marca). Solo PL finalizados, en un embarque que todavía no sale."""
    exigir(user, "transporte.gestionar")
    pls = _cargar_pls(db, datos.pl_ids)
    errores = []
    for pl in pls:
        ref = f"{nombre_factura(pl.factura)} / {pl.numero}"
        if pl.estado != "FINALIZADO":
            errores.append({"mensaje": f"{ref}: solo se recolectan packing lists finalizados."})
        elif not pl.unidad:
            errores.append({"mensaje": f"{ref}: asígnalo primero a un contenedor."})
        elif _salio(pl.unidad.embarque):
            errores.append({"mensaje": f"{ref}: el embarque ya salió."})
    if datos.fecha and datos.fecha > date.today():
        errores.append({"mensaje": "La fecha de recolección no puede ser futura."})
    if errores:
        raise ErrorNegocio("No se pudo registrar la recolección.", 422, "validacion", errores)
    for pl in pls:
        pl.recolectado_en = datos.fecha
        registrar(db, user, "packing_list", pl.id, "recoleccion", {"fecha": datos.fecha}, factura_id=pl.factura_id)
    return {"actualizados": len(pls)}
