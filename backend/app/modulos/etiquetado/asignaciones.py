"""Reglas de etiquetado: alta, cambios, prueba y conflictos.

La tabla asignaciones_etiqueta guarda las reglas (ver reglas.py, el motor que
elige el diseño de cada registro). Una regla tiene un destino opcional
(organización, familia y subfamilias, producto, artículo, excepción de una OC
o ninguno), condiciones declarativas, contexto, vigencia y prioridad. Al
guardar se avisa de los conflictos que crea (misma prioridad, diseños
distintos y registros que pueden cumplir ambas).
"""
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    AsignacionEtiqueta,
    FamiliaEtiquetado,
    OrdenCompra,
    PlantillaEtiqueta,
    Producto,
    Usuario,
)
from app.modelos.etiquetado import AMBITOS
from app.modulos.acceso.permisos import exigir, exigir_alguno
from app.modulos.comun.historial import registrar
from app.modulos.etiquetado import reglas
from app.modulos.etiquetado.reglas import (  # noqa: F401 (API del módulo)
    DESTINO,
    MODALIDADES_DE,
    PRIORIDAD,
    Eleccion,
    resolver,
)


def _destino_txt(db: Session, a: AsignacionEtiqueta) -> str | None:
    if a.ambito == "FAMILIA" and a.familia_id:
        f = db.get(FamiliaEtiquetado, a.familia_id)
        return f.nombre if f else None
    if a.ambito == "PRODUCTO" and a.producto_id:
        p = db.get(Producto, a.producto_id)
        return (p.nombre or p.estilo) if p else None
    if a.ambito == "ARTICULO" and a.articulo_id:
        art = db.get(Articulo, a.articulo_id)
        return art.sku if art else None
    if a.ambito == "OC" and a.oc_id:
        oc = db.get(OrdenCompra, a.oc_id)
        return oc.numero if oc else None
    return None


def dict_asignacion(db: Session, a: AsignacionEtiqueta, avisos: list | None = None) -> dict:
    p = a.plantilla
    hoy = date.today()
    vigente = (a.vigente_desde is None or a.vigente_desde <= hoy) and (a.vigente_hasta is None or a.vigente_hasta >= hoy)
    r = {"id": a.id, "plantilla_id": a.plantilla_id, "plantilla": p.nombre, "modalidad": p.modalidad, "ambito": a.ambito,
         "familia_id": a.familia_id, "producto_id": a.producto_id, "articulo_id": a.articulo_id, "oc_id": a.oc_id,
         "destino": _destino_txt(db, a), "predeterminada": a.predeterminada, "activa": a.activa, "motivo": a.motivo,
         "creada_en": a.creada_en, "version_vigente": p.vigente.numero if p.vigente else None,
         "nombre": reglas.regla_nombre(a), "prioridad": a.prioridad, "condiciones": a.condiciones or [],
         "contexto": a.contexto or {}, "vigente_desde": a.vigente_desde, "vigente_hasta": a.vigente_hasta, "vigente": vigente,
         "version": a.version, "actualizada_en": a.actualizada_en}
    if avisos is not None:
        r["conflictos"] = avisos
    return r


def listar(db: Session, user: Usuario, plantilla_id=None, ambito=None, familia_id=None, producto_id=None, articulo_id=None,
           oc_id=None, activas: bool | None = True) -> list[dict]:
    exigir(user, "etiquetas.ver")
    c = select(AsignacionEtiqueta).order_by(AsignacionEtiqueta.prioridad.desc(), AsignacionEtiqueta.ambito, AsignacionEtiqueta.id)
    for col, v in (("plantilla_id", plantilla_id), ("familia_id", familia_id), ("producto_id", producto_id),
                   ("articulo_id", articulo_id), ("oc_id", oc_id)):
        if v:
            c = c.where(getattr(AsignacionEtiqueta, col) == v)
    if ambito:
        c = c.where(AsignacionEtiqueta.ambito == ambito.upper())
    if activas is not None:
        c = c.where(AsignacionEtiqueta.activa.is_(activas))
    return [dict_asignacion(db, a) for a in db.scalars(c)]


def _cargar(db: Session, asignacion_id: int) -> AsignacionEtiqueta:
    a = db.get(AsignacionEtiqueta, asignacion_id)
    if not a:
        raise ErrorNegocio("The assignment does not exist.", 404, "no_encontrado")
    return a


def _hermanas(db: Session, a: AsignacionEtiqueta):
    """Reglas activas del mismo destino, prioridad y modalidad (compiten entre sí)."""
    c = select(AsignacionEtiqueta).join(PlantillaEtiqueta).where(
        AsignacionEtiqueta.ambito == a.ambito, AsignacionEtiqueta.activa.is_(True), AsignacionEtiqueta.id != a.id,
        AsignacionEtiqueta.prioridad == a.prioridad, PlantillaEtiqueta.modalidad == a.plantilla.modalidad)
    if a.ambito in DESTINO:
        c = c.where(getattr(AsignacionEtiqueta, DESTINO[a.ambito]) == getattr(a, DESTINO[a.ambito]))
    return db.scalars(c)


def _fecha(v, campo: str):
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ErrorNegocio("Check the dates of the rule.", 422, "validacion", [{"campo": campo, "mensaje": "Not a date."}]) from None


def _datos_regla(db: Session, datos: dict, actual: AsignacionEtiqueta | None) -> dict:
    """Nombre, prioridad, condiciones, contexto y vigencia validados."""
    limpio = {}
    if "nombre" in datos or actual is None:
        limpio["nombre"] = (datos.get("nombre") or "").strip()[:120] or None
    if "prioridad" in datos and datos["prioridad"] not in (None, ""):
        try:
            prioridad = int(datos["prioridad"])
        except (TypeError, ValueError):
            prioridad = -1
        if not 0 <= prioridad <= 100000:
            raise ErrorNegocio("The priority is a whole number from 0 to 100000.", 422, "validacion",
                               [{"campo": "prioridad", "mensaje": "From 0 to 100000."}])
        limpio["prioridad"] = prioridad
    if "condiciones" in datos or actual is None:
        limpio["condiciones"] = reglas.validar_condiciones(db, datos.get("condiciones"))
    if "contexto" in datos or actual is None:
        limpio["contexto"] = reglas.validar_contexto(datos.get("contexto"))
    for k in ("vigente_desde", "vigente_hasta"):
        if k in datos:
            limpio[k] = _fecha(datos.get(k), k)
    desde = limpio.get("vigente_desde", actual.vigente_desde if actual else None)
    hasta = limpio.get("vigente_hasta", actual.vigente_hasta if actual else None)
    if desde and hasta and hasta < desde:
        raise ErrorNegocio("The rule ends before it starts.", 422, "validacion", [{"campo": "vigente_hasta", "mensaje": "Before the start."}])
    return limpio


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "etiquetas.asignar")
    from app.modulos.etiquetado.plantillas import cargar as cargar_plantilla

    p = cargar_plantilla(db, datos.get("plantilla_id") or 0)
    ambito = (datos.get("ambito") or "").upper()
    if ambito not in AMBITOS:
        raise ErrorNegocio("Choose where the design applies.", 422, "validacion")
    if p.estado != "ACTIVA":
        raise ErrorNegocio("The design is archived.", 422, "validacion")
    if p.modalidad not in MODALIDADES_DE[ambito]:
        raise ErrorNegocio("This design's data mode does not apply there (a PO design has no item, an item design has no PO).",
                           422, "validacion")
    destino = {}
    if ambito in DESTINO:
        col = DESTINO[ambito]
        valor = datos.get(col)
        modelo = {"familia_id": FamiliaEtiquetado, "producto_id": Producto, "articulo_id": Articulo, "oc_id": OrdenCompra}[col]
        if not valor or not db.get(modelo, valor):
            raise ErrorNegocio("Choose where the design applies.", 422, "validacion", [{"campo": col, "mensaje": "It does not exist."}])
        destino[col] = valor
    limpio = _datos_regla(db, datos, None)
    if ambito == "REGLA" and not limpio["condiciones"] and not limpio["contexto"]:
        raise ErrorNegocio("A rule without a fixed target needs at least one condition or context.", 422, "validacion",
                           [{"campo": "condiciones", "mensaje": "Required."}])
    limpio.setdefault("prioridad", PRIORIDAD[ambito])
    for otra in db.scalars(select(AsignacionEtiqueta).where(
            AsignacionEtiqueta.plantilla_id == p.id, AsignacionEtiqueta.ambito == ambito, AsignacionEtiqueta.activa.is_(True),
            *[getattr(AsignacionEtiqueta, k) == v for k, v in destino.items()])):
        if (otra.condiciones or []) == limpio["condiciones"] and (otra.contexto or {}) == limpio["contexto"]:
            raise ErrorNegocio("The design is already assigned there.", 409, "repetida")
    motivo = (datos.get("motivo") or "").strip()[:300] or None
    if ambito == "OC" and not motivo:
        raise ErrorNegocio("Explain why this PO is an exception.", 422, "validacion", [{"campo": "motivo", "mensaje": "Required."}])
    a = AsignacionEtiqueta(plantilla_id=p.id, ambito=ambito, predeterminada=bool(datos.get("predeterminada")), activa=True,
                           motivo=motivo, creada_por=user.id, version=1, **destino, **limpio)
    db.add(a)
    db.flush()
    db.refresh(a)
    if a.predeterminada:
        for otra in _hermanas(db, a):
            otra.predeterminada = False
    db.flush()
    registrar(db, user, "plantilla_etiqueta", p.id, "asignar",
              {"regla": a.id, "ambito": ambito, **destino, "prioridad": a.prioridad, "condiciones": a.condiciones,
               "contexto": a.contexto, "predeterminada": a.predeterminada}, motivo)
    return dict_asignacion(db, a, reglas.conflictos(db, a))


def actualizar(db: Session, user: Usuario, asignacion_id: int, datos: dict) -> dict:
    exigir(user, "etiquetas.asignar")
    a = _cargar(db, asignacion_id)
    if datos.get("version") is not None and int(datos["version"]) != a.version:
        raise ErrorNegocio("Someone else changed this rule: reload it before saving.", 409, "conflicto_version")
    antes = dict_asignacion(db, a)
    limpio = _datos_regla(db, datos, a)
    for k, v in limpio.items():
        setattr(a, k, v)
    if "activa" in datos:
        a.activa = bool(datos["activa"])
    if "predeterminada" in datos:
        a.predeterminada = bool(datos["predeterminada"])
    if "motivo" in datos:
        a.motivo = (datos.get("motivo") or "").strip()[:300] or None
    if a.ambito == "REGLA" and not a.condiciones and not a.contexto:
        raise ErrorNegocio("A rule without a fixed target needs at least one condition or context.", 422, "validacion")
    if a.predeterminada:
        for otra in _hermanas(db, a):
            otra.predeterminada = False
    a.version += 1
    a.actualizada_por, a.actualizada_en = user.id, datetime.now()
    db.flush()
    despues = dict_asignacion(db, a)
    cambios = {k: [antes.get(k), despues.get(k)] for k in ("nombre", "prioridad", "condiciones", "contexto", "vigente_desde",
                                                          "vigente_hasta", "activa", "predeterminada", "motivo")
               if antes.get(k) != despues.get(k)}
    registrar(db, user, "plantilla_etiqueta", a.plantilla_id, "editar_asignacion", {"regla": a.id, **cambios})
    return dict_asignacion(db, a, reglas.conflictos(db, a))


def eliminar(db: Session, user: Usuario, asignacion_id: int) -> dict:
    exigir(user, "etiquetas.asignar")
    a = _cargar(db, asignacion_id)
    registrar(db, user, "plantilla_etiqueta", a.plantilla_id, "quitar_asignacion",
              {"regla": a.id, "ambito": a.ambito, "destino": _destino_txt(db, a), "nombre": a.nombre})
    db.delete(a)
    db.flush()
    return {"ok": True}


def conflictos(db: Session, user: Usuario) -> list[dict]:
    exigir_alguno(user, "etiquetas.ver", "etiquetas.asignar")
    return reglas.conflictos(db)


def probar(db: Session, user: Usuario, datos: dict) -> dict:
    """Qué diseño se elegiría para un registro (real o de muestra) y por qué,
    regla por regla. Puede incluir una regla en borrador (sin guardarla) para
    ver su efecto antes de crearla."""
    from app.modulos.etiquetado import campos, generacion
    from app.modulos.etiquetado import datos as svc_datos

    exigir_alguno(user, "etiquetas.asignar", "etiquetas.ver")
    modalidad = (datos.get("modalidad") or "").upper()
    if modalidad not in campos.POR_MODALIDAD:
        raise ErrorNegocio("Choose the data mode.", 422, "validacion")
    posicion = svc_datos.cargar_posicion(db, user, datos["posicion_id"]) if datos.get("posicion_id") else None
    oc = svc_datos.cargar_oc(db, user, datos.get("oc_id") or posicion.oc_id) if (datos.get("oc_id") or posicion) else None
    articulo = svc_datos.cargar_articulo(db, user, datos["articulo_id"]) if datos.get("articulo_id") else \
        (posicion.articulo if posicion else None)
    bulto = None
    if datos.get("pl_id"):
        pl = generacion.cargar_pl(db, user, int(datos["pl_id"]))
        tipo = datos.get("tipo_empaque_id")
        unidades = campos.unidades_pl(pl, int(tipo) if tipo else None, superiores=not tipo)
        n = int(datos.get("bulto") or 1)
        if not 1 <= n <= len(unidades):
            raise ErrorNegocio("That package does not exist in the packing list.", 422, "validacion")
        bulto = unidades[n - 1]
    contexto = {"modalidad": modalidad, "origen": datos.get("origen") or ("PACKING" if bulto else ("OC" if oc else "ARTICULOS")),
                "unidad": datos.get("unidad") or ("BULTO" if bulto else "LINEA")}
    valores, procedencia, problemas = generacion.valores_registro(db, modalidad, articulo, oc, posicion, bulto,
                                                                  campos.valores_organizacion(db), contexto)
    valores.update({str(k): v for k, v in (datos.get("valores") or {}).items()})  # valores de muestra escritos a mano
    hoy = _fecha(datos.get("fecha"), "fecha") or date.today()
    extra = []
    if datos.get("regla"):
        extra.append(_borrador(db, datos["regla"]))
    motor = reglas.Motor(db, modalidad, hoy, extra)
    registro = reglas.Registro(modalidad, articulo, oc, valores, contexto["origen"], contexto["unidad"],
                               bulto.valores.get("bulto.tipo_codigo") if bulto else None)
    eleccion = motor.resolver(registro, datos.get("elegida_id"))
    usados = {c["campo"] for e in eleccion.evaluaciones for c in (e.regla.condiciones or [])}
    return {**eleccion.dict(explicar=True), "fecha": hoy, "contexto": contexto,
            "valores": {k: (f"[{len(v)}]" if isinstance(v, list) else v) for k, v in sorted(valores.items())
                        if k in usados or k.startswith("logico.")},
            "procedencia": {k: v for k, v in procedencia.items() if v}, "problemas": problemas}


def _borrador(db: Session, datos: dict) -> AsignacionEtiqueta:
    """Una regla sin guardar, validada igual que al crearla, para probarla."""
    from app.modulos.etiquetado.plantillas import cargar as cargar_plantilla

    p = cargar_plantilla(db, datos.get("plantilla_id") or 0)
    ambito = (datos.get("ambito") or "REGLA").upper()
    if ambito not in AMBITOS:
        raise ErrorNegocio("Choose where the design applies.", 422, "validacion")
    limpio = _datos_regla(db, datos, None)
    limpio.setdefault("prioridad", PRIORIDAD[ambito])
    a = AsignacionEtiqueta(ambito=ambito, plantilla_id=p.id, predeterminada=bool(datos.get("predeterminada")), activa=True,
                           **{k: datos.get(k) for k in DESTINO.values() if datos.get(k)}, **limpio)
    a.plantilla = p
    a.nombre = (a.nombre or "Draft rule")
    return a
