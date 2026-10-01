from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from ..config import settings
from ..models import (
    Centro,
    Embarque,
    EventoEmbarque,
    Factura,
    PackingList,
    Puerto,
    TipoUnidad,
    Transportista,
    UnidadCarga,
    Usuario,
)
from .cantidades import nombre_factura, totales_pl
from .common import ErrorNegocio, exigir, registrar, requerir_motivo, filtro_texto
from .leadtimes import Estandares, _riesgo, limite_puerto
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
        raise ErrorNegocio("The shipment does not exist.", 404, "no_encontrado")
    return e


def _unidad(db: Session, user: Usuario, unidad_id: int) -> UnidadCarga:
    exigir(user, "transporte.gestionar")
    u = db.get(UnidadCarga, unidad_id)
    if not u:
        raise ErrorNegocio("The load unit does not exist.", 404, "no_encontrado")
    return u


def _salio(e: Embarque) -> bool:
    return e.estado != "PLANIFICADO"


def _exigir_planificado(e: Embarque, accion: str) -> None:
    """Después de la salida la carga está cerrada: lo que viaja ya viaja."""
    if _salio(e):
        raise ErrorNegocio(f"Shipment {e.codigo} has already departed; you cannot {accion}. The load was closed at departure.",
                           409, "embarque_cerrado")


# Qué evento se puede registrar en cada estado, en orden
EVENTOS_PERMITIDOS = {
    "PLANIFICADO": {"RECOLECCION", "SALIDA", "OTRO"},
    "EN_TRANSITO": {"TRANSITO", "ARRIBO", "OTRO"},
    "ARRIBADO": {"LIBERACION", "ENTREGA", "OTRO"},
    "ENTREGADO": {"RECEPCION", "OTRO"},
    "RECIBIDO": {"OTRO"},
}


MODO_TXT = {"MARITIMO": "ocean", "AEREO": "air", "TERRESTRE": "road"}


def _tipo(db: Session, codigo: str) -> TipoUnidad | None:
    return db.scalar(select(TipoUnidad).where(TipoUnidad.codigo == codigo))


def _capacidad(u: UnidadCarga) -> tuple[float | None, float | None]:
    t = _tipo(object_session(u), u.tipo)
    return u.capacidad_cbm or (t.capacidad_cbm if t else None), u.capacidad_kg or (t.capacidad_kg if t else None)


def modalidad_embarque(e: Embarque) -> str | None:
    """La modalidad es de cada unidad (FCL, LCL…); un embarque puede ser mixto."""
    db = object_session(e)
    mods = {t.modalidad for u in e.unidades if (t := _tipo(db, u.tipo))}
    return None if not mods else mods.pop() if len(mods) == 1 else "MIXTO"


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
    t = _tipo(object_session(u), u.tipo)
    pct_cbm = round(cbm * 100 / cap_cbm, 1) if cap_cbm else None
    pct_kg = round(bruto * 100 / cap_kg, 1) if cap_kg else None
    alertas = []
    if pct_cbm and pct_cbm > 100:
        alertas.append(f"The volume exceeds the nominal capacity ({pct_cbm}%).")
    if pct_kg and pct_kg > 100:
        alertas.append(f"The weight exceeds the nominal capacity ({pct_kg}%).")
    ocs = {pl_linea.factura_linea.posicion_oc.oc for pl in pls for pl_linea in pl.lineas}
    grupos: dict[int, set] = {}
    for pl in pls:
        for pl_linea in pl.lineas:
            pos = pl_linea.factura_linea.posicion_oc
            grupos.setdefault(pos.oc_id, set()).add(pos.grupo)
    tiendas = [o.fecha_tienda for o in ocs if o.fecha_tienda]
    e = u.embarque
    ests = Estandares(object_session(u)) if ocs else None
    # Llegada: real, ETA o la salida (real o ETD) más el tránsito estándar de su origen
    salida = e.salida_real or e.etd
    transito = max((ests.de(o.pais_origen)["dias_transito"] for o in ocs), default=0) if ests else 0
    llegada = e.arribo_real or e.eta or (salida + timedelta(days=transito) if salida else None)
    tienda = min(tiendas) if tiendas else None
    # Fecha límite de arribo: la fecha en tienda menos puerto→bodega, ingreso, reexportación
    # y los días extra del tipo de producto, según su origen
    limites = [limite_puerto(o.fecha_tienda, ests.de(o.pais_origen, grupos.get(o.id))) for o in ocs if o.fecha_tienda]
    limite = min(limites) if limites else None
    return {
        "id": u.id,
        "embarque_id": u.embarque_id,
        "fecha_tienda": tienda,
        "limite_puerto": limite,
        # Días entre la llegada al puerto (real o estimada) y la fecha límite de arribo
        "holgura_dias": (limite - llegada).days if limite and llegada else None,
        # En tiempo / en riesgo / atrasado frente a la fecha en tienda (None: faltan fechas)
        "estado_tiempo": _riesgo((limite - llegada).days) if limite and llegada else None,
        "llegada_estimada": llegada,
        "marcas": sorted({pl_linea.factura_linea.marca for pl in pls for pl_linea in pl.lineas
                          if pl_linea.factura_linea.marca}),
        "recolectados": sum(1 for pl in pls if pl.recolectado_en),
        "tipo": u.tipo,
        "tipo_nombre": t.nombre if t else u.tipo,
        "modalidad": t.modalidad if t else None,
        "requiere_sello": bool(t and t.requiere_sello),
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
def tiempo_embarque(unidades: list[dict]) -> dict:
    """Estado del embarque frente a la fecha en tienda: el peor de sus unidades
    (atrasado > en riesgo > en tiempo); sin fechas suficientes queda pendiente."""
    estados = [u["estado_tiempo"] for u in unidades if u.get("estado_tiempo")]
    holguras = [u["holgura_dias"] for u in unidades if u.get("holgura_dias") is not None]
    tiendas = [u["fecha_tienda"] for u in unidades if u.get("fecha_tienda")]
    peor = next((x for x in ("ATRASO", "JUSTO", "A_TIEMPO") if x in estados), None)
    return {"estado_tiempo": peor, "holgura_dias": min(holguras) if holguras else None,
            "fecha_tienda": min(tiendas) if tiendas else None}


def listar_embarques(db: Session, user: Usuario, estado: str | None = None, q: str | None = None) -> list[dict]:
    exigir(user, "transporte.gestionar")
    consulta = select(Embarque).order_by(Embarque.etd.desc().nullslast(), Embarque.id.desc())
    if estado:
        consulta = consulta.where(Embarque.estado == estado)
    if q:
        consulta = consulta.where(filtro_texto(q, lambda p: [Embarque.codigo.ilike(p), Embarque.documento_numero.ilike(p)]))
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
            **tiempo_embarque(unidades),
            "ocupacion": [{"id": u["id"], "nombre": u["nombre"], "tipo": u["tipo"], "pct_cbm": u["pct_cbm"],
                           "cbm": u["cbm"]} for u in unidades],
        })
    return res


def _cabecera(e: Embarque) -> dict:
    return {
        "id": e.id,
        "codigo": e.codigo,
        "tipo_transporte": e.tipo_transporte,
        "modalidad": modalidad_embarque(e),
        "documento_numero": e.documento_numero,
        "transportista_id": e.transportista_id,
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
    """Ruta coherente con el modo de transporte:
    - los puertos son del catálogo y del tipo del embarque (puerto marítimo,
      aeropuerto, aduana terrestre);
    - el destino es uno de los puertos de llegada del centro que recibe: se
      sugiere el principal y se puede cambiar por otro de sus puertos;
    - el transportista es del modo y trabaja con la sociedad del centro."""
    for k in ("puerto_origen", "puerto_destino", "centro"):
        if isinstance(campos.get(k), str):
            campos[k] = campos[k].strip().upper() or None
    valor = lambda k: campos[k] if k in campos else (getattr(actual, k) if actual else None)  # noqa: E731
    modo = valor("tipo_transporte") or "MARITIMO"
    errores = []
    for k, texto in (("puerto_origen", "The origin port"), ("puerto_destino", "The destination port")):
        if k in campos and campos[k]:
            pto = db.scalar(select(Puerto).where(Puerto.codigo == campos[k]))
            if not pto:
                errores.append({"campo": k, "mensaje": f"{texto} {campos[k]} is not in the port catalog."})
            elif pto.tipo != modo:
                errores.append({"campo": k, "mensaje": f"{texto} {pto.codigo} is {MODO_TXT.get(pto.tipo, pto.tipo)}; "
                                                       f"the shipment is {MODO_TXT[modo]}."})
    centro = valor("centro")
    c = db.scalar(select(Centro).where(Centro.codigo == centro)) if centro else None
    if centro and not c:
        errores.append({"campo": "centro", "mensaje": f"Center {centro} does not exist."})
    elif c:
        permitidos = puertos_centro(db, c, modo)
        if permitidos:
            if not valor("puerto_destino"):
                campos["puerto_destino"] = permitidos[0]
            elif valor("puerto_destino") not in permitidos:
                errores.append({"campo": "puerto_destino", "mensaje":
                                f"Center {centro} receives through {', '.join(permitidos)}; choose one of those ports."})
    if "transportista_id" in campos or ("centro" in campos and valor("transportista_id")):
        tid = valor("transportista_id")
        t = db.get(Transportista, tid) if tid else None
        if tid and (not t or not t.activo):
            errores.append({"campo": "transportista_id", "mensaje": "The carrier does not exist or is inactive."})
        elif t:
            if t.tipo not in (modo, "MULTIMODAL"):
                errores.append({"campo": "transportista_id", "mensaje":
                                f"{t.nombre} is {MODO_TXT.get(t.tipo, t.tipo)}; the shipment is {MODO_TXT[modo]}."})
            if c and t.sociedades and c.sociedad_id not in {x.id for x in t.sociedades}:
                errores.append({"campo": "transportista_id", "mensaje":
                                f"{t.nombre} does not work with company {c.sociedad.codigo}."})
            campos["transportista"] = t.nombre
        else:
            campos["transportista"] = None
    if errores:
        raise ErrorNegocio("Check the shipment route.", 422, "validacion", errores)
    return campos


def puertos_centro(db: Session, c: Centro, modo: str) -> list[str]:
    """Puertos de llegada del centro para ese modo: primero el principal."""
    todos = ([c.puerto] if c.puerto else []) + [p.codigo for p in c.puertos if p.codigo != c.puerto]
    tipos = {p.codigo: p.tipo for p in db.scalars(select(Puerto).where(Puerto.codigo.in_(todos)))}
    return [x for x in todos if tipos.get(x) == modo]


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
    if "tipo_transporte" in campos and e.unidades:
        if campos["tipo_transporte"] != e.tipo_transporte:
            raise ErrorNegocio("The transport mode of a shipment that already has units cannot be changed.",
                               409, "embarque_con_unidades")
    if _salio(e):
        bloqueados = {"etd", "puerto_origen", "tipo_transporte", "transportista_id", "documento_numero", "centro"}
        if e.estado != "PLANIFICADO" and e.arribo_real:
            bloqueados |= {"eta", "puerto_destino"}
        tocados = [k for k in campos if k in bloqueados and campos[k] != getattr(e, k)]
        if tocados:
            raise ErrorNegocio("Those fields were locked when the departure was recorded"
                               + (" and the arrival" if e.arribo_real else "") + ": " + ", ".join(tocados) + ".",
                               409, "embarque_cerrado")
    if {"puerto_origen", "puerto_destino", "centro", "transportista_id", "tipo_transporte"} & set(campos):
        if "centro" in campos and campos["centro"] and campos["centro"] != e.centro:
            otros = {pl.factura.centro for u in e.unidades for pl in u.packing_lists
                     if pl.estado != "CANCELADO"} - {campos["centro"].strip().upper()}
            if otros:
                raise ErrorNegocio(f"The shipment already carries cargo for center {', '.join(sorted(otros))}.",
                                   409, "centro_distinto")
            campos.setdefault("puerto_destino", None)
        campos = _ruta(db, campos, e)
    etd = campos.get("etd", e.etd)
    eta = campos.get("eta", e.eta)
    if etd and eta and eta < etd:
        raise ErrorNegocio("The ETA cannot be before the ETD.", 422, "validacion")
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
    unidades = [resumen_unidad(u) for u in e.unidades]
    return {
        **_cabecera(e),
        "unidades": unidades,
        **tiempo_embarque(unidades),
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
        # Solo las unidades del modo del embarque (marítimo: contenedores y LCL…)
        "tipos_unidad": [
            {"codigo": t.codigo, "nombre": t.nombre, "modalidad": t.modalidad, "capacidad_cbm": t.capacidad_cbm,
             "capacidad_kg": t.capacidad_kg, "requiere_sello": t.requiere_sello}
            for t in db.scalars(select(TipoUnidad).where(TipoUnidad.modo == e.tipo_transporte,
                                                         TipoUnidad.activo.is_(True)).order_by(TipoUnidad.codigo))],
        "puertos_sugeridos": puertos_centro(db, c, e.tipo_transporte) if (c := db.scalar(
            select(Centro).where(Centro.codigo == e.centro))) else [],
        "notify": partes(db, None, e.centro)["notify"] if e.centro else None,
        "cerrado": _salio(e),
        "eventos_permitidos": sorted(EVENTOS_PERMITIDOS[e.estado]),
    }


def _documentos_salida(e: Embarque, pls: list[PackingList]) -> list[str]:
    """Datos que exige el documento de transporte (BL/AWB/carta de porte)."""
    faltan = []
    if not e.documento_numero:
        faltan.append("BL, AWB or waybill number.")
    if not e.transportista:
        faltan.append("Shipping line or carrier.")
    if not e.puerto_origen or not e.puerto_destino:
        faltan.append("Origin and destination.")
    if not e.centro:
        faltan.append("Arrival center (notify party).")
    con_carga = {pl.unidad_carga_id for pl in pls}
    for u in e.unidades:
        if u.id not in con_carga:
            continue
        if not u.numero:
            faltan.append(f"{u.etiqueta}: container or air waybill number.")
        t = _tipo(object_session(e), u.tipo)
        if t and t.requiere_sello and not u.sello:
            faltan.append(f"{u.numero or u.etiqueta}: seal number.")
    return faltan


def registrar_evento(db: Session, user: Usuario, embarque_id: int, datos) -> dict:
    e = _embarque(db, user, embarque_id)
    nombres = {"RECOLECCION": "pickup", "SALIDA": "departure", "TRANSITO": "transit", "ARRIBO": "arrival",
               "LIBERACION": "release", "ENTREGA": "delivery", "RECEPCION": "receipt", "OTRO": "event"}
    if datos.tipo not in EVENTOS_PERMITIDOS[e.estado]:
        raise ErrorNegocio(f"{nombres[datos.tipo].capitalize()} cannot be recorded with the shipment in status "
                           f"{e.estado.replace('_', ' ').lower()}. Follow the order: pickup, departure, arrival, "
                           "delivery and receipt.", 409, "orden_eventos")
    ultimo = max((ev.fecha for ev in e.eventos), default=None)
    if ultimo and datos.fecha < ultimo and datos.tipo != "OTRO":
        raise ErrorNegocio(f"The date cannot be before the last event ({ultimo:%m/%d/%Y %H:%M}).",
                           422, "fecha_evento")
    if datos.fecha.date() > date.today() + timedelta(days=1):
        raise ErrorNegocio("Events with a future date are not recorded; use ETD and ETA for planned dates.",
                           422, "fecha_evento")
    if datos.tipo == "SALIDA":
        pls = [pl for u in e.unidades for pl in u.packing_lists if pl.estado != "CANCELADO"]
        tentativas = [pl.numero for pl in pls if pl.asignacion == "TENTATIVA"]
        if tentativas:
            raise ErrorNegocio(
                f"{len(tentativas)} packing lists are assigned tentatively. Confirm or remove them before "
                "recording the departure.", 409, "tentativas_pendientes")
        if not pls:
            raise ErrorNegocio("The shipment has no packing lists assigned.", 409, "sin_carga")
        faltan = _documentos_salida(e, pls)
        if faltan:
            raise ErrorNegocio("Required transport data is missing to record the departure.", 422,
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
def _validar_tipo(db: Session, e: Embarque, codigo: str) -> TipoUnidad:
    t = _tipo(db, codigo)
    if not t or not t.activo:
        raise ErrorNegocio(f"Unit type {codigo} does not exist or is inactive.", 422, "validacion")
    if t.modo != e.tipo_transporte:
        raise ErrorNegocio(f"{t.nombre} is {MODO_TXT[t.modo]} transport; the shipment is "
                           f"{MODO_TXT[e.tipo_transporte]}.", 422, "validacion")
    return t



def agregar_unidad(db: Session, user: Usuario, embarque_id: int, datos) -> dict:
    e = _embarque(db, user, embarque_id)
    _exigir_planificado(e, "add containers")
    _validar_tipo(db, e, datos.tipo)
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
        _exigir_planificado(u.embarque, "change the container, its number or its seal")
    if campos.get("tipo") and campos["tipo"] != u.tipo and any(pl.estado != "CANCELADO" for pl in u.packing_lists):
        raise ErrorNegocio("The type of a loaded container cannot be changed.", 409, "con_carga")
    if campos.get("tipo"):
        _validar_tipo(db, u.embarque, campos["tipo"])
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
    _exigir_planificado(u.embarque, "remove containers")
    if any(pl.estado != "CANCELADO" for pl in u.packing_lists):
        raise ErrorNegocio("The unit has packing lists assigned; remove them first.", 409, "con_carga")
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
            pend.append("invoice not finalized")
        if pl.estado != "FINALIZADO":
            pend.append("PL not finalized")
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
    Solo PL finalizados de facturas finalizadas; si el embarque ya tiene
    centro, solo lo que va a ese centro."""
    u = _unidad(db, user, unidad_id)
    consulta = (
        select(PackingList)
        .join(Factura, Factura.id == PackingList.factura_id)
        .where(PackingList.unidad_carga_id.is_(None), PackingList.estado == "FINALIZADO",
               Factura.estado == "FINALIZADA")
        .order_by(Factura.id, PackingList.id)
    )
    if proveedor_id:
        consulta = consulta.where(Factura.proveedor_id == proveedor_id)
    if u.embarque.centro:
        consulta = consulta.where(Factura.centro == u.embarque.centro)
    if q:
        consulta = consulta.where(filtro_texto(q, lambda p: [Factura.numero.ilike(p)]))
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
        raise ErrorNegocio("Some packing lists no longer exist. Reload.", 404, "no_encontrado")
    return pls


def _listo(pl: PackingList) -> bool:
    return pl.estado == "FINALIZADO" and pl.factura.estado == "FINALIZADA"


def asignar(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    u = _unidad(db, user, unidad_id)
    _exigir_planificado(u.embarque, "add cargo")
    pls = _cargar_pls(db, datos.pl_ids)
    e = u.embarque
    if not e.centro:
        # Sin centro todavía: lo define la primera carga, y no se mezclan centros
        centros = {pl.factura.centro for pl in pls} | {
            x.factura.centro for un in e.unidades for x in un.packing_lists if x.estado != "CANCELADO"}
        centros.discard(None)
        if len(centros) > 1:
            raise ErrorNegocio("A shipment arrives at a single center; the selection goes to "
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
            errores.append({"pl_id": pl.id, "mensaje": f"{ref}: it is cancelled."})
            continue
        if pl.factura.estado == "CANCELADA":
            errores.append({"pl_id": pl.id, "mensaje": f"{ref}: the invoice is cancelled."})
            continue
        if u.embarque.centro and pl.factura.centro != u.embarque.centro:
            errores.append({"pl_id": pl.id, "mensaje":
                f"{ref} goes to center {pl.factura.centro}; the shipment arrives at center {u.embarque.centro}."})
            continue
        anterior = pl.unidad
        if anterior and anterior.id != u.id:
            if _salio(anterior.embarque):
                errores.append({"pl_id": pl.id, "mensaje":
                    f"{ref} is already traveling on {anterior.numero or anterior.etiqueta} ({anterior.embarque.codigo})."})
                continue
            if pl.asignacion == "CONFIRMADA" and not motivo:
                errores.append({"pl_id": pl.id, "mensaje":
                    f"{ref} is confirmed on {anterior.numero or anterior.etiqueta}. Enter the reason to move it."})
        if not _listo(pl):
            errores.append({"pl_id": pl.id, "mensaje":
                f"{ref}: only finalized invoices and packing lists go on a shipment."})
        if settings.FACTURA_EN_UNA_SOLA_UNIDAD:
            otras = {x.unidad_carga_id for x in pl.factura.packing_lists
                     if x.id not in ids and x.unidad_carga_id and x.estado != "CANCELADO"}
            otras.discard(u.id)
            if otras:
                errores.append({"pl_id": pl.id, "mensaje":
                    f"{ref}: other PLs of the same invoice are on another unit (rule: one invoice, one unit)."})
    if errores:
        raise ErrorNegocio("It could not be assigned.", 422, "validacion", errores)
    # Capacidad nominal: no se asigna más volumen ni peso del que cabe
    nuevos = [pl for pl in pls if pl.unidad_carga_id != u.id]
    actual = resumen_unidad(u)
    extra = [totales_pl(pl) for pl in nuevos]
    cbm = actual["cbm"] + sum(t["cbm"] for t in extra)
    kg = actual["peso_bruto"] + sum(t["peso_bruto"] for t in extra)
    excesos = []
    if actual["capacidad_cbm"] and cbm > actual["capacidad_cbm"]:
        excesos.append(f"volume {cbm:.2f} of {actual['capacidad_cbm']:.0f} m³")
    if actual["capacidad_kg"] and kg > actual["capacidad_kg"]:
        excesos.append(f"weight {kg:,.0f} of {actual['capacidad_kg']:,.0f} kg")
    if excesos:
        raise ErrorNegocio(f"It does not fit in {u.numero or u.etiqueta}: " + " and ".join(excesos)
                           + ". Use another container for the rest.", 422, "capacidad")
    confirmados = 0
    for pl in pls:
        anterior = pl.unidad
        modo = "CONFIRMADA"
        confirmados += 1
        pl.unidad = u
        pl.asignacion = modo
        registrar(db, user, "packing_list", pl.id, "asignar_unidad", {
            "unidad": u.numero or u.etiqueta, "embarque": u.embarque.codigo, "modo": modo,
            "anterior": (anterior.numero or anterior.etiqueta) if anterior and anterior.id != u.id else None,
        }, motivo, factura_id=pl.factura_id)
    return {"asignados": len(pls), "confirmados": confirmados, "tentativos": len(pls) - confirmados}


def confirmar(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    u = _unidad(db, user, unidad_id)
    _exigir_planificado(u.embarque, "confirm cargo")
    pls = _cargar_pls(db, datos.pl_ids)
    errores = []
    for pl in pls:
        ref = f"{nombre_factura(pl.factura)} / {pl.numero}"
        if pl.unidad_carga_id != u.id:
            errores.append({"pl_id": pl.id, "mensaje": f"{ref} is not on this unit."})
        elif not _listo(pl):
            errores.append({"pl_id": pl.id, "mensaje": f"{ref}: the invoice and the PL must be finalized."})
    if errores:
        raise ErrorNegocio("None were confirmed; fix these pending items.", 422, "validacion", errores)
    for pl in pls:
        if pl.asignacion != "CONFIRMADA":
            pl.asignacion = "CONFIRMADA"
            registrar(db, user, "packing_list", pl.id, "confirmar_unidad",
                      {"unidad": u.numero or u.etiqueta}, factura_id=pl.factura_id)
    return {"confirmados": len(pls)}


def desasignar(db: Session, user: Usuario, unidad_id: int, datos) -> dict:
    u = _unidad(db, user, unidad_id)
    _exigir_planificado(u.embarque, "remove cargo")
    pls = _cargar_pls(db, datos.pl_ids)
    motivo = None
    if any(pl.asignacion == "CONFIRMADA" for pl in pls):
        motivo = requerir_motivo(datos.motivo, "remove confirmed packing lists")
    for pl in pls:
        if pl.unidad_carga_id != u.id:
            raise ErrorNegocio(f"{pl.numero} is not on this unit.", 422, "validacion")
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
            errores.append({"mensaje": f"{ref}: only finalized packing lists are picked up."})
        elif not pl.unidad:
            errores.append({"mensaje": f"{ref}: assign it to a container first."})
        elif _salio(pl.unidad.embarque):
            errores.append({"mensaje": f"{ref}: the shipment has already departed."})
    if datos.fecha and datos.fecha > date.today():
        errores.append({"mensaje": "The pickup date cannot be in the future."})
    if errores:
        raise ErrorNegocio("The pickup could not be recorded.", 422, "validacion", errores)
    for pl in pls:
        pl.recolectado_en = datos.fecha
        registrar(db, user, "packing_list", pl.id, "recoleccion", {"fecha": datos.fecha}, factura_id=pl.factura_id)
    return {"actualizados": len(pls)}
