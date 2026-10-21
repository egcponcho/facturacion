"""Qué diseño lleva cada cosa: los usos de diseño (reglas.py los aplica).

La pantalla principal es la matriz «familia × tipo de etiqueta»; cada celda
se abre y se guarda entera (diseño normal + excepciones) con su firma, así
dos personas no se pisan. Antes de guardar se puede simular qué cambia.
También se crean usos sueltos desde otras pantallas: un diseño propio del
producto o de algunas tallas, o una excepción de una OC concreta.

Nada se borra: un uso se da de baja (`eliminado_en`) y cada alta, cambio o
baja queda en el historial (entidad uso_diseno).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errores import ErrorNegocio
from app.modelos import (
    Articulo,
    CategoriaEtiquetado,
    Centro,
    FamiliaEtiquetado,
    GrupoArticulo,
    OrdenCompra,
    Pais,
    PlantillaEtiqueta,
    PosicionOC,
    Producto,
    Proveedor,
    Sociedad,
    TipoEmpaque,
    TipoEtiqueta,
    TrabajoEtiquetas,
    TrabajoRegistro,
    UsoDiseno,
    Usuario,
)
from app.modelos.etiquetado import ACCIONES, ALCANCES_DE, CANTIDADES_REGLA, CONTEXTOS, DESTINO_DE, NIVELES_DE
from app.modulos.acceso.permisos import exigir, exigir_interno
from app.modulos.comun.historial import registrar
from app.modulos.etiquetado import reglas, tipos
from app.modulos.etiquetado.reglas import Resolvedor, Sujeto, celda_de, nombre_destino

MAX_VALORES = 50
MAX_SIMULACION = 20000  # artículos que se revisan al simular un cambio
OC_ABIERTAS = ("BORRADOR", "EN_APROBACION", "RECHAZADA", "APROBADA")
CON_VALORES = ("CENTRO_DESTINO", "PAIS_DESTINO", "SOCIEDAD", "PROVEEDOR")
_MODELO_DESTINO = {"FAMILIA": FamiliaEtiquetado, "CATEGORIA": CategoriaEtiquetado, "PRODUCTO": Producto, "SKU": Articulo,
                   "TIPO_EMPAQUE": TipoEmpaque}
# Cuántas puede decir una regla según lo que se etiqueta (por unidad solo en artículos)
CANTIDADES_DE_SUJETO = {"ARTICULO": CANTIDADES_REGLA, "DOCUMENTO": ("UNA", "MANUAL"), "BULTO": ("UNA", "MANUAL")}
MAX_PRIORIDAD = 1000


# ---- Lectura ---------------------------------------------------------------------------------
def campos_articulo(a: Articulo) -> dict:
    from app.modulos.etiquetado import campos

    return campos.valores_articulo(a)


def _nombre_p(u: UsoDiseno) -> str | None:
    """El diseño de una regla, o nada si dice que la etiqueta no va."""
    return u.plantilla.nombre if u.plantilla is not None else None


def _usuario(db: Session, uid: int | None) -> str | None:
    u = db.get(Usuario, uid) if uid else None
    return (u.nombre or u.email) if u else None


def _nombres_valores(db: Session, u: UsoDiseno) -> list[str]:
    """Lo que se lee de cada valor de una excepción (nombre del centro, del país…)."""
    vals = u.contexto_valores or []
    if u.contexto_tipo == "CENTRO_DESTINO":
        m = dict(db.execute(select(Centro.codigo, Centro.nombre).where(Centro.codigo.in_(vals))).all())
    elif u.contexto_tipo == "PAIS_DESTINO":
        m = dict(db.execute(select(Pais.codigo, Pais.nombre).where(Pais.codigo.in_(vals))).all())
    elif u.contexto_tipo == "SOCIEDAD":
        m = dict(db.execute(select(Sociedad.codigo, Sociedad.nombre).where(Sociedad.codigo.in_(vals))).all())
    elif u.contexto_tipo == "PROVEEDOR":
        ids = [int(v) for v in vals if str(v).isdigit()]
        m = {str(k): v for k, v in db.execute(select(Proveedor.id, Proveedor.nombre).where(Proveedor.id.in_(ids))).all()}
    else:
        m = {}
    return [m.get(str(v), str(v)) for v in vals]


def dict_uso(db: Session, u: UsoDiseno, hoy: date | None = None) -> dict:
    from app.core.empresa import hoy as hoy_empresa

    p = u.plantilla
    oc = db.get(OrdenCompra, u.oc_id) if u.oc_id else None
    return {"id": u.id, "tipo_etiqueta_id": u.tipo_etiqueta_id, "tipo": u.tipo.nombre if u.tipo else None,
            "plantilla_id": u.plantilla_id, "plantilla": p.nombre if p else None,
            "version_id": p.version_vigente_id if p else None, "aprobada": bool(p and p.version_vigente_id),
            "nivel": u.nivel, "destino_id": u.destino_id, "destino": nombre_destino(db, u.nivel, u.destino_id),
            "celda": u.celda, "contexto_tipo": u.contexto_tipo, "contexto_valores": u.contexto_valores or [],
            "contexto_nombres": _nombres_valores(db, u), "oc_id": u.oc_id, "oc": oc.numero if oc else None,
            "condiciones": u.condiciones or [], "vigente_desde": u.vigente_desde, "vigente_hasta": u.vigente_hasta,
            "vigente": reglas.vigente(u, hoy or hoy_empresa()), "motivo": u.motivo, "creado_por": _usuario(db, u.creado_por),
            "creado_en": u.creado_en, "actualizado_por": _usuario(db, u.actualizado_por), "actualizado_en": u.actualizado_en,
            "eliminado_en": u.eliminado_en, "eliminado_por": _usuario(db, u.eliminado_por), "version": u.version,
            "accion": u.accion or "USAR", "alcance": u.alcance, "cantidad": u.cantidad, "prioridad": u.prioridad or 0}


def cargar(db: Session, uso_id: int, bloquear: bool = False) -> UsoDiseno:
    c = select(UsoDiseno).where(UsoDiseno.id == uso_id)
    u = db.scalar(c.with_for_update() if bloquear else c)
    if not u:
        raise ErrorNegocio("The design use does not exist.", 404, "no_encontrado")
    return u


def listar(db: Session, user: Usuario, tipo_etiqueta_id=None, nivel=None, destino_id=None, oc_id=None, plantilla_id=None,
           contexto_tipo=None, bajas: bool = False) -> list[dict]:
    exigir_interno(user, "etiquetas.ver", "etiquetas.configurar")
    c = select(UsoDiseno).options(selectinload(UsoDiseno.plantilla), selectinload(UsoDiseno.tipo))
    if not bajas:
        c = c.where(UsoDiseno.eliminado_en.is_(None))
    if tipo_etiqueta_id:
        c = c.where(UsoDiseno.tipo_etiqueta_id == tipo_etiqueta_id)
    if nivel:
        c = c.where(UsoDiseno.nivel == nivel.upper())
        if destino_id and nivel.upper() in DESTINO_DE:
            c = c.where(getattr(UsoDiseno, DESTINO_DE[nivel.upper()]) == destino_id)
    if oc_id:
        c = c.where(UsoDiseno.oc_id == oc_id)
    if plantilla_id:
        c = c.where(UsoDiseno.plantilla_id == plantilla_id)
    if contexto_tipo:
        c = c.where(UsoDiseno.contexto_tipo == contexto_tipo.upper())
    return [dict_uso(db, u) for u in db.scalars(c.order_by(UsoDiseno.tipo_etiqueta_id, UsoDiseno.nivel, UsoDiseno.id))]


def historial(db: Session, user: Usuario, uso_id: int) -> list[dict]:
    from app.modelos import Historial

    exigir_interno(user, "etiquetas.ver", "etiquetas.configurar")
    cargar(db, uso_id)
    filas = db.scalars(select(Historial).where(Historial.entidad == "uso_diseno", Historial.entidad_id == uso_id)
                       .order_by(Historial.fecha.desc(), Historial.id.desc()))
    return [{"id": h.id, "fecha": h.fecha, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
             "usuario": _usuario(db, h.usuario_id)} for h in filas]


# Lo que la migración 0076 escribió en el historial (motivos y notas en inglés): aquí para que se traduzca en el informe
TEXTOS_0076 = (
    "The rule was inactive.",
    "The origin, unit or data mode of the rule no longer exist: the design applies to every origin.",
    "The package type {0} does not exist.",
    "The rule was limited to package types {0}: the limit no longer applies.",
    "Several rules gave a design to the same place; the one with the highest priority stays (rule {0}).",
    # «A package label cannot depend on a product…» se lee con sus partes traducibles
    "The labels of {0} cannot depend on {1}: add an exception with a condition if it is still needed.",
    "a package", "a document", "this kind", "a labeling family", "a product", "an item",
)
_DEPENDE = re.compile(r"^A (package|document|label) label cannot depend on an? (labeling family|product|item): ")


def _texto_0076(texto: str | None) -> str | None:
    m = _DEPENDE.match(texto or "")
    if not m:
        return texto
    que = {"package": "a package", "document": "a document"}.get(m[1], "this kind")
    donde = {"labeling family": "a labeling family", "product": "a product", "item": "an item"}[m[2]]
    return f"The labels of {que} cannot depend on {donde}: add an exception with a condition if it is still needed."


def informe_migracion(db: Session, user: Usuario) -> dict:
    """Cómo quedaron las reglas anteriores al pasar a usos de diseño (migración 0076): cada regla con su
    resultado (convertida o de baja, y por qué), sus notas (lo que ya no aplica) y si su uso sigue vigente
    hoy. Sale del historial que dejó la migración; sin reglas anteriores, vacío."""
    from app.modelos import Historial

    exigir(user, "etiquetas.configurar")
    filas = db.execute(select(Historial.entidad_id, Historial.detalle, Historial.fecha)
                       .where(Historial.entidad == "uso_diseno", Historial.accion == "migrar").order_by(Historial.id)).all()
    ids = [i for i, *_ in filas]
    usos_ = {u.id: u for u in db.scalars(select(UsoDiseno).where(UsoDiseno.id.in_(ids))
                                         .options(selectinload(UsoDiseno.plantilla), selectinload(UsoDiseno.tipo)))} if ids else {}
    res = []
    for uid, d, fecha in filas:
        d, u = d or {}, usos_.get(uid)
        res.append({"uso_id": uid, "regla": d.get("regla"), "nombre": d.get("nombre"), "ambito": d.get("ambito"),
                    "prioridad": d.get("prioridad"), "resultado": d.get("resultado"), "motivo_baja": _texto_0076(d.get("motivo_baja")),
                    "notas": d.get("notas") or [], "nivel": d.get("nivel"), "contexto_tipo": d.get("contexto_tipo"),
                    "tipo": u.tipo.nombre if u else None, "plantilla": u.plantilla.nombre if u else None,
                    "destino": nombre_destino(db, u.nivel, u.destino_id) if u else None,
                    "vigente": bool(u and u.eliminado_en is None), "fecha": fecha})
    return {"resumen": {"reglas": len({x["regla"] for x in res}), "convertidas": sum(x["resultado"] == "convertida" for x in res),
                        "de_baja": sum(x["resultado"] == "baja" for x in res), "con_notas": sum(bool(x["notas"]) for x in res),
                        "vigentes": sum(x["vigente"] for x in res)},
            "filas": res}


# ---- Validación ------------------------------------------------------------------------------
def _destino(db: Session, nivel: str, destino_id) -> int | None:
    if nivel == "GENERAL":
        return None
    try:
        did = int(destino_id)
    except (TypeError, ValueError):
        raise ErrorNegocio("Choose where the design applies.", 422, "validacion",
                           [{"campo": "destino_id", "mensaje": nivel}]) from None
    if not db.get(_MODELO_DESTINO[nivel], did):
        raise ErrorNegocio("Where the design applies does not exist.", 422, "validacion", [{"campo": "destino_id", "mensaje": nivel}])
    return did


def _fecha(v, campo: str) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ErrorNegocio("Write a valid date.", 422, "validacion", [{"campo": campo, "mensaje": str(v)}]) from None


def _valores(db: Session, contexto: str, valores) -> list[str]:
    if isinstance(valores, str):
        valores = [x.strip() for x in valores.split(",") if x.strip()]
    if not isinstance(valores, list) or not valores or len(valores) > MAX_VALORES:
        raise ErrorNegocio(f"Choose between 1 and {MAX_VALORES} values for the exception.", 422, "validacion",
                           [{"campo": "contexto_valores", "mensaje": contexto}])
    valores = list(dict.fromkeys(str(v).strip().upper() if contexto != "PROVEEDOR" else str(v).strip() for v in valores))
    modelo, col = {"CENTRO_DESTINO": (Centro, Centro.codigo), "PAIS_DESTINO": (Pais, Pais.codigo),
                   "SOCIEDAD": (Sociedad, Sociedad.codigo), "PROVEEDOR": (Proveedor, Proveedor.id)}[contexto]
    buscados = [int(v) for v in valores if v.isdigit()] if contexto == "PROVEEDOR" else valores
    existen = {str(x) for x in db.scalars(select(col).where(col.in_(buscados)))}
    faltan = [v for v in valores if v not in existen]
    if faltan:
        raise ErrorNegocio("Some values of the exception do not exist.", 422, "validacion",
                           [{"campo": "contexto_valores", "mensaje": ", ".join(faltan)}])
    return valores


def _limpiar(db: Session, user: Usuario, datos: dict, actual: UsoDiseno | None = None) -> dict:
    """Los datos de un uso validados; con `actual`, los que no vienen se toman de él."""
    from app.modulos.etiquetado import datos as svc_datos

    def dato(k, defecto=None):
        return datos[k] if k in datos else (getattr(actual, k) if actual is not None else defecto)

    tipo = tipos.cargar(db, int(dato("tipo_etiqueta_id") or 0))
    if not tipo.activo and actual is None:
        raise ErrorNegocio("The label type is not active.", 422, "validacion")
    # Qué decide la regla: usar un diseño o que esta etiqueta no va; dónde va, cuántas y su prioridad
    accion = str(dato("accion") or "USAR").upper()
    if accion not in ACCIONES:
        raise ErrorNegocio("Choose whether the label goes (with a design) or does not go.", 422, "validacion",
                           [{"campo": "accion", "mensaje": accion}])
    plantilla = None
    if accion == "USAR":
        plantilla = db.get(PlantillaEtiqueta, int(dato("plantilla_id") or 0))
        if plantilla is None or plantilla.tipo_etiqueta_id != tipo.id:
            raise ErrorNegocio("Choose a design of this label type.", 422, "validacion", [{"campo": "plantilla_id", "mensaje": tipo.nombre}])
        if plantilla.estado != "ACTIVA":
            raise ErrorNegocio("The design is archived.", 422, "validacion", [{"campo": "plantilla_id", "mensaje": plantilla.nombre}])
    alcance = (str(dato("alcance") or "").upper() or None) if accion == "USAR" else None
    if alcance and alcance not in ALCANCES_DE[tipo.sujeto]:
        raise ErrorNegocio("This label cannot go there: choose a place for what it labels.", 422, "validacion",
                           [{"campo": "alcance", "mensaje": ", ".join(ALCANCES_DE[tipo.sujeto])}])
    cantidad = (str(dato("cantidad") or "").upper() or None) if accion == "USAR" else None
    if cantidad and cantidad not in CANTIDADES_DE_SUJETO[tipo.sujeto]:
        raise ErrorNegocio("Choose how many labels: one, one per unit (items only) or by hand.", 422, "validacion",
                           [{"campo": "cantidad", "mensaje": ", ".join(CANTIDADES_DE_SUJETO[tipo.sujeto])}])
    try:
        prioridad = int(dato("prioridad") or 0)
    except (TypeError, ValueError):
        prioridad = None
    if prioridad is None or abs(prioridad) > MAX_PRIORIDAD:
        raise ErrorNegocio(f"The priority is a whole number between -{MAX_PRIORIDAD} and {MAX_PRIORIDAD}.", 422, "validacion",
                           [{"campo": "prioridad", "mensaje": str(dato("prioridad"))}])
    nivel = str(dato("nivel") or "GENERAL").upper()
    if nivel not in NIVELES_DE[tipo.sujeto]:
        raise ErrorNegocio("A design of this label type cannot go there.", 422, "validacion", [{"campo": "nivel", "mensaje": nivel}])
    destino = datos.get("destino_id") if "destino_id" in datos else (actual.destino_id if actual is not None else None)
    destino_id = _destino(db, nivel, destino)
    if nivel == "TIPO_EMPAQUE" and not tipos.aplica(tipos.empaques_de(db, tipo.id), destino_id):
        raise ErrorNegocio("This label type does not go on that package type (see the label type: «Goes on»).", 422, "validacion",
                           [{"campo": "destino_id", "mensaje": tipo.nombre}])
    contexto = str(dato("contexto_tipo") or "NINGUNO").upper()
    if contexto not in CONTEXTOS:
        raise ErrorNegocio("Unknown kind of exception.", 422, "validacion", [{"campo": "contexto_tipo", "mensaje": contexto}])
    condiciones = reglas.validar_condiciones(db, dato("condiciones") or [])
    desde, hasta = _fecha(dato("vigente_desde"), "vigente_desde"), _fecha(dato("vigente_hasta"), "vigente_hasta")
    if desde and hasta and hasta < desde:
        raise ErrorNegocio("The end date is before the start date.", 422, "validacion", [{"campo": "vigente_hasta", "mensaje": str(hasta)}])
    motivo = (dato("motivo") or "").strip()[:300] or None
    valores, oc_id = [], None
    if contexto == "NINGUNO":
        if condiciones or desde or hasta:
            raise ErrorNegocio("The normal design of a cell has no conditions or dates: add an exception instead.", 422,
                               "validacion")
    else:
        if not motivo:
            raise ErrorNegocio("Explain why this exception exists.", 422, "validacion", [{"campo": "motivo", "mensaje": "Required."}])
        if contexto == "OC":
            oc = svc_datos.cargar_oc(db, user, int(dato("oc_id") or 0))
            oc_id = oc.id
        elif contexto in CON_VALORES:
            valores = _valores(db, contexto, dato("contexto_valores"))
        elif contexto == "CONDICION" and not (condiciones or desde or hasta):
            raise ErrorNegocio("An exception by conditions needs at least one condition or a date range.", 422, "validacion",
                               [{"campo": "condiciones", "mensaje": "Required."}])
    col = DESTINO_DE.get(nivel)
    res = {"tipo_etiqueta_id": tipo.id, "plantilla_id": plantilla.id if plantilla else None, "nivel": nivel, "grupo_id": None,
           "producto_id": None, "articulo_id": None, "tipo_empaque_id": None,
           "celda": celda_de(tipo.id, nivel, destino_id), "contexto_tipo": contexto, "contexto_valores": valores, "oc_id": oc_id,
           "condiciones": condiciones, "vigente_desde": desde, "vigente_hasta": hasta, "motivo": motivo,
           "accion": accion, "alcance": alcance, "cantidad": cantidad, "prioridad": prioridad}
    if col:
        res[col] = destino_id
    return res


def _se_cruzan(a: UsoDiseno, b: UsoDiseno) -> bool:
    """Dos usos de la misma celda que podrían aplicar al mismo registro con el mismo peso."""
    if a.contexto_tipo != b.contexto_tipo:
        return False
    if a.contexto_tipo == "NINGUNO":
        return True
    if (a.prioridad or 0) != (b.prioridad or 0):  # la prioridad decide cuál vale
        return False
    fin_a, fin_b = a.vigente_hasta or date.max, b.vigente_hasta or date.max
    ini_a, ini_b = a.vigente_desde or date.min, b.vigente_desde or date.min
    if fin_a < ini_b or fin_b < ini_a:
        return False
    if a.contexto_tipo == "OC":
        return a.oc_id == b.oc_id and (a.condiciones or []) == (b.condiciones or [])
    if a.contexto_tipo in CON_VALORES:
        return bool({str(v) for v in a.contexto_valores or []} & {str(v) for v in b.contexto_valores or []}) \
            and (a.condiciones or []) == (b.condiciones or [])
    return (a.condiciones or []) == (b.condiciones or [])


def _usos_celda(db: Session, celda: str, bloquear: bool = False) -> list[UsoDiseno]:
    c = select(UsoDiseno).where(UsoDiseno.celda == celda, UsoDiseno.eliminado_en.is_(None)).order_by(UsoDiseno.id)
    return list(db.scalars(c.with_for_update() if bloquear else c))


def _revisar_cruces(db: Session, u: UsoDiseno) -> None:
    """Antes de escribir (así el choque se explica, no lo rechaza la base con un error genérico)."""
    for otro in _usos_celda(db, u.celda, bloquear=True):
        if otro.id != u.id and _se_cruzan(u, otro):
            if u.contexto_tipo == "NINGUNO":
                raise ErrorNegocio("This place already has a normal design: change it instead of adding another.", 409,
                                   "celda_ocupada", [{"campo": "uso", "mensaje": str(otro.id)}])
            raise ErrorNegocio("There is already an exception like this one in the same place.", 409, "excepcion_repetida",
                               [{"campo": "uso", "mensaje": f"{otro.id}: {reglas.texto_contexto(otro)}"}])


def _foto(u: UsoDiseno) -> dict:
    return {"plantilla_id": u.plantilla_id, "nivel": u.nivel, "destino_id": u.destino_id, "contexto_tipo": u.contexto_tipo,
            "contexto_valores": u.contexto_valores, "oc_id": u.oc_id, "condiciones": u.condiciones,
            "vigente_desde": u.vigente_desde, "vigente_hasta": u.vigente_hasta, "motivo": u.motivo,
            "accion": u.accion or "USAR", "alcance": u.alcance, "cantidad": u.cantidad, "prioridad": u.prioridad or 0}


# ---- Escritura -------------------------------------------------------------------------------
def _nuevo(db: Session, user: Usuario, datos: dict) -> UsoDiseno:
    u = UsoDiseno(**_limpiar(db, user, datos), creado_por=user.id, version=1)
    _revisar_cruces(db, u)
    db.add(u)
    db.flush()
    registrar(db, user, "uso_diseno", u.id, "crear", _foto(u), u.motivo)
    return u


def _editar(db: Session, user: Usuario, u: UsoDiseno, datos: dict) -> UsoDiseno:
    antes = _foto(u)
    for k, v in _limpiar(db, user, datos, u).items():
        setattr(u, k, v)
    cambios = {k: [antes[k], v] for k, v in _foto(u).items() if antes[k] != v}
    if not cambios:
        return u
    with db.no_autoflush:
        _revisar_cruces(db, u)
    u.version += 1
    u.actualizado_por, u.actualizado_en = user.id, datetime.now()
    db.flush()
    registrar(db, user, "uso_diseno", u.id, "editar", cambios, datos.get("motivo_cambio"))
    return u


def _baja(db: Session, user: Usuario, u: UsoDiseno, motivo: str | None) -> None:
    if u.eliminado_en is not None:
        return
    u.eliminado_en, u.eliminado_por = datetime.now(), user.id
    u.version += 1
    db.flush()
    registrar(db, user, "uso_diseno", u.id, "baja", _foto(u), (motivo or "").strip()[:500] or None)


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    """Un uso suelto (diseño propio de un producto o SKU, excepción de una OC…).
    Si la celda ya tiene diseño normal y se pide `reemplazar`, ese se cambia."""
    exigir(user, "etiquetas.configurar")
    contexto = str(datos.get("contexto_tipo") or "NINGUNO").upper()
    if contexto == "NINGUNO" and datos.get("reemplazar"):
        limpio = _limpiar(db, user, datos)
        actual = next((x for x in _usos_celda(db, limpio["celda"], bloquear=True) if x.contexto_tipo == "NINGUNO"), None)
        if actual is not None:
            return dict_uso(db, _editar(db, user, actual, {k: limpio[k] for k in ("plantilla_id", "accion", "alcance",
                                                                                   "cantidad", "prioridad")}))
    return dict_uso(db, _nuevo(db, user, datos))


def actualizar(db: Session, user: Usuario, uso_id: int, datos: dict) -> dict:
    exigir(user, "etiquetas.configurar")
    u = cargar(db, uso_id, bloquear=True)
    if u.eliminado_en is not None:
        raise ErrorNegocio("This design use was removed.", 409, "estado")
    if datos.get("version") is not None and int(datos["version"]) != u.version:
        raise ErrorNegocio("Someone else changed this design use: reload it before saving.", 409, "conflicto_version")
    return dict_uso(db, _editar(db, user, u, datos))


def baja(db: Session, user: Usuario, uso_id: int, motivo: str | None) -> dict:
    exigir(user, "etiquetas.configurar")
    u = cargar(db, uso_id, bloquear=True)
    _baja(db, user, u, motivo)
    return dict_uso(db, u)


def valores_contexto(db: Session, user: Usuario, contexto: str) -> list[dict]:
    """Los valores reales que puede tener una excepción: los países de los centros destino,
    los centros, las sociedades o los proveedores (valor, texto y detalle para buscar)."""
    exigir_interno(user, "etiquetas.configurar", "etiquetas.ver")
    contexto = (contexto or "").upper()
    if contexto == "PAIS_DESTINO":
        usados = {c for c in db.scalars(select(Centro.pais).where(Centro.pais.is_not(None)))}
        paises = db.execute(select(Pais.codigo, Pais.nombre).order_by(Pais.nombre)).all()
        # Primero los países con centros destino; después el resto (se puede preparar un destino nuevo)
        return [{"valor": c, "texto": n, "sub": c, "con_centros": c in usados}
                for c, n in sorted(paises, key=lambda x: (x[0] not in usados, x[1]))]
    if contexto == "CENTRO_DESTINO":
        return [{"valor": c.codigo, "texto": c.nombre, "sub": " · ".join(x for x in (c.codigo, c.pais) if x)}
                for c in db.scalars(select(Centro).where(Centro.activo.is_(True)).order_by(Centro.codigo))]
    if contexto == "SOCIEDAD":
        return [{"valor": s.codigo, "texto": s.nombre, "sub": s.codigo}
                for s in db.scalars(select(Sociedad).order_by(Sociedad.codigo))]
    if contexto == "PROVEEDOR":
        return [{"valor": str(p.id), "texto": p.nombre, "sub": " · ".join(x for x in (p.codigo, p.pais) if x)}
                for p in db.scalars(select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.nombre))]
    raise ErrorNegocio("This kind of exception has no list of values.", 422, "validacion", [{"campo": "contexto", "mensaje": contexto}])


# ---- Celda (lo que se abre desde la matriz) -----------------------------------------------------
def firma(usos: list[UsoDiseno]) -> str:
    return hashlib.sha1(",".join(f"{u.id}:{u.version}" for u in sorted(usos, key=lambda x: x.id)).encode()).hexdigest()[:16]


def _cadena(db: Session, nivel: str, destino_id: int | None) -> list[tuple[str, int | None]]:
    """Los niveles de los que hereda una celda, del más cercano al más general."""
    res: list[tuple[str, int | None]] = []
    if nivel == "SKU":
        a = db.get(Articulo, destino_id)
        if a is not None:
            if a.producto_id:
                res.append(("PRODUCTO", a.producto_id))
            cat = reglas.categoria_de(db, a, campos_articulo(a))
            if cat is not None:
                res.append(("CATEGORIA", cat.id))
            f = a.familia_efectiva
            res += [("FAMILIA", x.id) for x in reversed(f.ruta())] if f else []
    elif nivel == "PRODUCTO":
        p = db.get(Producto, destino_id)
        f = familia_producto(db, p) if p else None
        a = db.scalar(select(Articulo).where(Articulo.producto_id == destino_id).order_by(Articulo.id).limit(1)) if p else None
        cat = reglas.categoria_de(db, a, campos_articulo(a)) if a is not None else None
        if cat is not None:
            res.append(("CATEGORIA", cat.id))
        res += [("FAMILIA", x.id) for x in reversed(f.ruta())] if f else []
    elif nivel == "CATEGORIA":
        c = db.get(CategoriaEtiquetado, destino_id)
        res += [("FAMILIA", x.id) for x in reversed(c.familia.ruta())] if c else []
    elif nivel == "FAMILIA":
        f = db.get(FamiliaEtiquetado, destino_id)
        res += [("FAMILIA", x.id) for x in reversed(f.ruta()[:-1])] if f else []
    if nivel != "GENERAL":
        res.append(("GENERAL", None))
    return res


def familia_producto(db: Session, p: Producto) -> FamiliaEtiquetado | None:
    if p.familia_etiquetado_id:
        return db.get(FamiliaEtiquetado, p.familia_etiquetado_id)
    g = db.get(GrupoArticulo, p.grupo_id) if p.grupo_id else None
    return g.familia_etiquetado if g else None


def _normal(db: Session, tipo_id: int, nivel: str, destino_id: int | None) -> UsoDiseno | None:
    return next((u for u in _usos_celda(db, celda_de(tipo_id, nivel, destino_id)) if u.contexto_tipo == "NINGUNO"), None)


def hereda(db: Session, tipo_id: int, nivel: str, destino_id: int | None) -> dict | None:
    """El diseño normal que valdría en la celda si no tuviera uno propio, y de dónde viene."""
    for n, d in _cadena(db, nivel, destino_id):
        u = _normal(db, tipo_id, n, d)
        if u is not None:
            return {"uso_id": u.id, "plantilla_id": u.plantilla_id, "plantilla": _nombre_p(u),
                    "version_id": u.plantilla.version_vigente_id if u.plantilla else None, "nivel": n, "destino_id": d,
                    "destino": nombre_destino(db, n, d), "accion": u.accion or "USAR", "alcance": u.alcance, "cantidad": u.cantidad}
    return None


def _articulos_de(db: Session, nivel: str, destino_id: int | None, limite: int = MAX_SIMULACION) -> list[Articulo]:
    """Los artículos activos que caen en una celda (para simular y contar)."""
    c = select(Articulo).where(Articulo.activo.is_(True)).options(
        selectinload(Articulo.producto), selectinload(Articulo.grupo), selectinload(Articulo.familia_etiquetado))
    if nivel == "SKU":
        c = c.where(Articulo.id == destino_id)
    elif nivel == "PRODUCTO":
        c = c.where(Articulo.producto_id == destino_id)
    arts = list(db.scalars(c.order_by(Articulo.id).limit(limite)))
    if nivel == "FAMILIA":
        arts = [a for a in arts if a.familia_efectiva is not None and destino_id in {f.id for f in a.familia_efectiva.ruta()}]
    elif nivel == "CATEGORIA":
        cache: dict = {}
        arts = [a for a in arts if (c := reglas.categoria_de(db, a, campos_articulo(a), cache)) is not None and c.id == destino_id]
    return arts


def _propios(db: Session, tipo_id: int, nivel: str, destino_id: int | None) -> list[dict]:
    """Productos y SKU de la familia (o SKU del producto) con un diseño normal propio."""
    if nivel not in ("FAMILIA", "PRODUCTO", "GENERAL"):
        return []
    usos = list(db.scalars(select(UsoDiseno).where(
        UsoDiseno.tipo_etiqueta_id == tipo_id, UsoDiseno.eliminado_en.is_(None), UsoDiseno.contexto_tipo == "NINGUNO",
        UsoDiseno.nivel.in_(("PRODUCTO", "SKU") if nivel != "PRODUCTO" else ("SKU",)))))
    res = []
    for u in usos:
        if nivel == "PRODUCTO":
            a = db.get(Articulo, u.articulo_id)
            if a is None or a.producto_id != destino_id:
                continue
        elif nivel == "FAMILIA":
            f = familia_producto(db, db.get(Producto, u.producto_id)) if u.nivel == "PRODUCTO" else \
                db.get(Articulo, u.articulo_id).familia_efectiva
            if f is None or f.id != destino_id:
                continue
        elif nivel == "GENERAL":
            continue
        res.append({"uso_id": u.id, "nivel": u.nivel, "destino_id": u.destino_id, "destino": nombre_destino(db, u.nivel, u.destino_id),
                    "plantilla_id": u.plantilla_id, "plantilla": _nombre_p(u), "accion": u.accion or "USAR"})
    return res


def celda(db: Session, user: Usuario, tipo_id: int, nivel: str, destino_id: int | None) -> dict:
    exigir_interno(user, "etiquetas.ver", "etiquetas.configurar")
    tipo = tipos.cargar(db, tipo_id)
    nivel = nivel.upper()
    if nivel not in NIVELES_DE[tipo.sujeto]:
        raise ErrorNegocio("A design of this label type cannot go there.", 422, "validacion")
    destino_id = _destino(db, nivel, destino_id)
    usos = _usos_celda(db, celda_de(tipo.id, nivel, destino_id))
    normal = next((u for u in usos if u.contexto_tipo == "NINGUNO"), None)
    excepciones = sorted((u for u in usos if u.contexto_tipo != "NINGUNO"),
                         key=lambda u: (0 if u.contexto_tipo == "OC" else 1 + reglas.ORDEN_CONTEXTO.index(u.contexto_tipo), u.id))
    articulos = len(_articulos_de(db, nivel, destino_id)) if tipo.sujeto == "ARTICULO" else None
    return {"tipo": tipos.dict_tipo(db, tipo), "nivel": nivel, "destino_id": destino_id, "destino": nombre_destino(db, nivel, destino_id),
            "normal": dict_uso(db, normal) if normal else None, "hereda": hereda(db, tipo.id, nivel, destino_id),
            "excepciones": [dict_uso(db, u) for u in excepciones], "propios": _propios(db, tipo.id, nivel, destino_id),
            "articulos": articulos, "firma": firma(usos)}


def _pedido_celda(db: Session, datos: dict) -> tuple[TipoEtiqueta, str, int | None]:
    tipo = tipos.cargar(db, int(datos.get("tipo_etiqueta_id") or 0))
    nivel = str(datos.get("nivel") or "GENERAL").upper()
    if nivel not in NIVELES_DE[tipo.sujeto]:
        raise ErrorNegocio("A design of this label type cannot go there.", 422, "validacion")
    return tipo, nivel, _destino(db, nivel, datos.get("destino_id"))


def _datos_normal(n: dict | None) -> dict | None:
    """Lo que dice la regla normal de una celda: un diseño (con dónde va, cuántas
    y prioridad) o «no lleva»; None (o sin diseño) es heredar."""
    n = n or {}
    accion = str(n.get("accion") or "USAR").upper()
    if accion == "USAR" and not n.get("plantilla_id"):
        return None
    return {"accion": accion, "plantilla_id": n.get("plantilla_id") if accion == "USAR" else None,
            "alcance": n.get("alcance") or None, "cantidad": n.get("cantidad") or None, "prioridad": n.get("prioridad") or 0}


def guardar_celda(db: Session, user: Usuario, datos: dict) -> dict:
    """Guarda la celda entera: su regla normal (`normal`: {plantilla_id, alcance,
    cantidad, prioridad} o {accion: NO_LLEVA}; null para heredar), sus excepciones (con id, se editan; sin id, se agregan) y
    las que se quitan. `firma` es la que se leyó: si otro la cambió, 409."""
    exigir(user, "etiquetas.configurar")
    tipo, nivel, destino_id = _pedido_celda(db, datos)
    clave = celda_de(tipo.id, nivel, destino_id)
    usos = _usos_celda(db, clave, bloquear=True)
    if datos.get("firma") is not None and datos["firma"] != firma(usos):
        raise ErrorNegocio("Someone else changed this place while you had it open: open it again.", 409, "conflicto_version")
    base = {"tipo_etiqueta_id": tipo.id, "nivel": nivel, "destino_id": destino_id}
    por_id = {u.id: u for u in usos}
    motivo = datos.get("motivo_cambio")
    for uid in datos.get("quitar") or []:
        if int(uid) not in por_id:
            raise ErrorNegocio("The exception to remove is not in this place.", 422, "validacion")
        _baja(db, user, por_id[int(uid)], motivo)
    if "normal" in datos:
        actual = next((u for u in usos if u.contexto_tipo == "NINGUNO" and u.eliminado_en is None), None)
        n = _datos_normal(datos["normal"])
        if n is None:
            if actual is not None:
                _baja(db, user, actual, motivo)
        elif actual is None:
            _nuevo(db, user, {**base, **n, "contexto_tipo": "NINGUNO"})
        else:
            _editar(db, user, actual, {**n, "motivo_cambio": motivo})
    for x in datos.get("excepciones") or []:
        if x.get("id"):
            u = por_id.get(int(x["id"]))
            if u is None:
                raise ErrorNegocio("The exception is not in this place.", 422, "validacion")
            _editar(db, user, u, {**x, **base})
        else:
            if str(x.get("contexto_tipo") or "").upper() in ("", "NINGUNO"):
                raise ErrorNegocio("Choose the kind of exception.", 422, "validacion")
            _nuevo(db, user, {**x, **base})
    return celda(db, user, tipo.id, nivel, destino_id)


def lote(db: Session, user: Usuario, datos: dict) -> dict:
    """La misma excepción en varias celdas de un tipo («aplicar también a…»), en una sola operación."""
    exigir(user, "etiquetas.configurar")
    exc = datos.get("excepcion") or {}
    if str(exc.get("contexto_tipo") or "").upper() in ("", "NINGUNO"):
        raise ErrorNegocio("Choose the kind of exception.", 422, "validacion")
    celdas = datos.get("celdas") or []
    if not celdas or len(celdas) > 200:
        raise ErrorNegocio("Choose between 1 and 200 places.", 422, "validacion")
    creados = [_nuevo(db, user, {**exc, "tipo_etiqueta_id": datos.get("tipo_etiqueta_id"), "nivel": c.get("nivel"),
                                 "destino_id": c.get("destino_id")}) for c in celdas]
    return {"creados": [dict_uso(db, u) for u in creados]}


# ---- Simulación ------------------------------------------------------------------------------
def _propuesta(db: Session, user: Usuario, datos: dict) -> tuple[TipoEtiqueta, str, int | None, list[UsoDiseno], set[int]]:
    """La celda como quedaría (usos en memoria, sin guardar) y los ids que se reemplazan o quitan."""
    tipo, nivel, destino_id = _pedido_celda(db, datos)
    usos = _usos_celda(db, celda_de(tipo.id, nivel, destino_id))
    base = {"tipo_etiqueta_id": tipo.id, "nivel": nivel, "destino_id": destino_id}
    cambios, quitar = [], {int(x) for x in datos.get("quitar") or []}
    normal = next((u for u in usos if u.contexto_tipo == "NINGUNO"), None)
    if "normal" in datos:
        n = _datos_normal(datos["normal"])
        if n is None:
            if normal is not None:
                quitar.add(normal.id)
        else:
            u = UsoDiseno(**_limpiar(db, user, {**base, **n}))
            u.id = normal.id if normal is not None else None
            cambios.append(u)
    for i, x in enumerate(datos.get("excepciones") or []):
        u = UsoDiseno(**_limpiar(db, user, {**x, **base}))
        u.id = int(x["id"]) if x.get("id") else -(i + 1)
        cambios.append(u)
    for u in cambios:
        u.plantilla = db.get(PlantillaEtiqueta, u.plantilla_id) if u.plantilla_id else None
        u.tipo = tipo
    return tipo, nivel, destino_id, cambios, quitar


def simular(db: Session, user: Usuario, datos: dict) -> dict:
    """Qué cambiaría si se guardara la celda así (no guarda nada): cuántos
    artículos cambian de diseño, cuántos quedan sin diseño, cuántas líneas de
    OC abiertas cumplen cada excepción y cuántos trabajos abiertos se afectan."""
    exigir_interno(user, "etiquetas.configurar", "etiquetas.ver")
    tipo, nivel, destino_id, cambios, quitar = _propuesta(db, user, datos)
    from app.modulos.etiquetado import campos

    antes = Resolvedor(db, [tipo])
    despues = Resolvedor(db, [tipo], cambios=cambios, quitar=quitar)
    res = {"tipo_etiqueta_id": tipo.id, "sujeto": tipo.sujeto, "cambian": 0, "ejemplos": [], "sin_diseno": 0, "no_lleva": 0,
           "alcance": None, "excepciones": [], "trabajos": 0}
    if tipo.sujeto != "ARTICULO":
        res["alcance"] = "todos"
        return res
    arts = _articulos_de(db, nivel, destino_id)
    con_condiciones = any(u.condiciones for x in despues.celdas.values() for u in [x.normal, *x.excepciones] if u is not None)
    res["alcance"] = len(arts)
    for a in arts:
        valores = campos.valores_articulo(a) if con_condiciones else {}
        s = Sujeto("ARTICULO", articulo=a, valores=valores)
        e0, e1 = antes.elegir(s, tipo), despues.elegir(s, tipo)
        if e1.uso is None:
            res["sin_diseno"] += 1
        elif e1.no_lleva:
            res["no_lleva"] += 1
        if (e0.plantilla.id if e0.plantilla else None) != (e1.plantilla.id if e1.plantilla else None):
            res["cambian"] += 1
            if len(res["ejemplos"]) < 50:
                res["ejemplos"].append({"articulo_id": a.id, "sku": a.sku, "antes": e0.plantilla.nombre if e0.plantilla else None,
                                        "despues": e1.plantilla.nombre if e1.plantilla else None})
    # Líneas de OC abiertas de esos artículos que cumplen cada excepción nueva o editada
    excepciones = [u for u in cambios if u.contexto_tipo not in ("NINGUNO",)]
    if excepciones and arts:
        ids = [a.id for a in arts]
        lineas = list(db.scalars(select(PosicionOC).join(OrdenCompra, OrdenCompra.id == PosicionOC.oc_id)
                                 .where(PosicionOC.articulo_id.in_(ids), OrdenCompra.estado.in_(OC_ABIERTAS)).limit(MAX_SIMULACION)))
        for i, u in enumerate(excepciones):
            n = 0
            for p in lineas:
                s = Sujeto("ARTICULO", articulo=p.articulo, oc=p.oc,
                           valores=campos.valores_articulo(p.articulo) if u.condiciones else {})
                if u.contexto_tipo == "OC":
                    n += int(p.oc_id == u.oc_id and despues.coincide(u, s, despues.contexto(s)))
                else:
                    n += int(despues.coincide(u, s, despues.contexto(s)))
            res["excepciones"].append({"indice": i, "id": u.id, "coinciden": n})
        res["lineas_abiertas"] = len(lineas)
    res["trabajos"] = db.scalar(select(func.count(func.distinct(TrabajoRegistro.trabajo_id))).join(
        TrabajoEtiquetas, TrabajoEtiquetas.id == TrabajoRegistro.trabajo_id).where(
        TrabajoEtiquetas.estado.in_(("BORRADOR", "VALIDADO", "PARCIAL")), TrabajoRegistro.tipo_etiqueta_id == tipo.id,
        TrabajoRegistro.articulo_id.in_([a.id for a in arts]))) or 0
    return res


# ---- Matriz y cobertura ---------------------------------------------------------------------
def _articulos_por_familia(db: Session) -> dict:
    """Artículos activos por su familia efectiva (la propia, la del producto o la del grupo)."""
    f = func.coalesce(Articulo.familia_etiquetado_id, Producto.familia_etiquetado_id, GrupoArticulo.familia_etiquetado_id)
    filas = db.execute(select(f, func.count()).select_from(Articulo)
                       .outerjoin(Producto, Producto.id == Articulo.producto_id)
                       .outerjoin(GrupoArticulo, GrupoArticulo.id == Articulo.grupo_id)
                       .where(Articulo.activo.is_(True)).group_by(f)).all()
    return {k: n for k, n in filas}


def matriz(db: Session, user: Usuario, sujeto: str = "ARTICULO") -> dict:
    """Qué diseño lleva cada cosa: filas (toda la empresa, familias o tipos de
    empaque) × tipos de etiqueta del sujeto, con lo que hereda cada celda."""
    exigir_interno(user, "etiquetas.ver", "etiquetas.configurar")
    sujeto = sujeto.upper()
    if sujeto not in NIVELES_DE:
        raise ErrorNegocio("Unknown subject.", 422, "validacion")
    ts = [t for t in db.scalars(select(TipoEtiqueta).where(TipoEtiqueta.activo.is_(True), TipoEtiqueta.sujeto == sujeto)
                                .order_by(TipoEtiqueta.orden, TipoEtiqueta.id))]
    usos = list(db.scalars(select(UsoDiseno).where(UsoDiseno.eliminado_en.is_(None),
                                                   UsoDiseno.tipo_etiqueta_id.in_([t.id for t in ts]))
                           .options(selectinload(UsoDiseno.plantilla)))) if ts else []
    por_celda: dict = {}
    for u in usos:
        por_celda.setdefault(u.celda, []).append(u)
    filas: list[dict] = [{"nivel": "GENERAL", "id": None, "nombre": None, "padre_id": None, "profundidad": 0}]
    conteo = {}
    if sujeto == "ARTICULO":
        conteo = _articulos_por_familia(db)
        familias = list(db.scalars(select(FamiliaEtiquetado).where(FamiliaEtiquetado.activa.is_(True))
                                   .order_by(FamiliaEtiquetado.orden, FamiliaEtiquetado.nombre)))
        hijos: dict = {}
        for f in familias:
            hijos.setdefault(f.padre_id if f.padre_id in {x.id for x in familias} else None, []).append(f)

        cats_de: dict = {}
        for c in db.scalars(select(CategoriaEtiquetado).where(CategoriaEtiquetado.activa.is_(True))
                            .order_by(CategoriaEtiquetado.orden, CategoriaEtiquetado.id)):
            cats_de.setdefault(c.familia_id, []).append(c)
        por_cat = _articulos_por_categoria(db) if cats_de else {}

        def poner(padre, nivel):
            for f in hijos.get(padre, []):
                filas.append({"nivel": "FAMILIA", "id": f.id, "nombre": f.nombre, "codigo": f.codigo, "padre_id": f.padre_id,
                              "profundidad": nivel, "articulos": conteo.get(f.id, 0)})
                # Sus categorías, debajo de la familia (más específicas que ella)
                for c in cats_de.get(f.id, []):
                    filas.append({"nivel": "CATEGORIA", "id": c.id, "nombre": c.nombre, "codigo": c.codigo, "padre_id": f.id,
                                  "profundidad": nivel + 1, "articulos": por_cat.get(c.id, 0)})
                poner(f.id, nivel + 1)
        poner(None, 1)
        filas[0]["articulos"] = sum(conteo.values())
        filas.append({"nivel": "SIN_FAMILIA", "id": None, "nombre": None, "padre_id": None, "profundidad": 1,
                      "articulos": conteo.get(None, 0)})
    elif sujeto == "BULTO":
        for e in db.scalars(select(TipoEmpaque).where(TipoEmpaque.activo.is_(True)).order_by(TipoEmpaque.nivel.desc(),
                                                                                                TipoEmpaque.nombre)):
            filas.append({"nivel": "TIPO_EMPAQUE", "id": e.id, "nombre": e.nombre, "codigo": e.codigo, "padre_id": None,
                          "profundidad": 1})
    padres = {f["id"]: f for f in filas if f["nivel"] == "FAMILIA"}
    empaques = {t.id: set(tipos.empaques_de(db, t.id)) for t in ts} if sujeto == "BULTO" else {}
    propios_familia = _propios_por_familia(db, usos) if sujeto == "ARTICULO" else {}
    faltan_total = 0
    for fila in filas:
        fila["celdas"] = {}
        for t in ts:
            if fila["nivel"] == "TIPO_EMPAQUE" and not tipos.aplica(empaques.get(t.id), fila["id"]):
                # Este tipo de etiqueta no va en este empaque: ni hereda ni falta
                fila["celdas"][t.id] = {"normal": None, "hereda": None, "excepciones": 0, "propios": 0, "falta": False, "no_aplica": True}
                continue
            nivel = "GENERAL" if fila["nivel"] == "SIN_FAMILIA" else fila["nivel"]
            lista = por_celda.get(celda_de(t.id, nivel, fila["id"]), []) if fila["nivel"] != "SIN_FAMILIA" else []
            normal = next((u for u in lista if u.contexto_tipo == "NINGUNO"), None)
            efectivo, de = normal, None
            if efectivo is None:
                cadena = []
                p = padres.get(fila["id"]) if fila["nivel"] == "FAMILIA" else None
                if fila["nivel"] == "CATEGORIA":  # una categoría hereda de su familia y de las de arriba
                    p = padres.get(fila["padre_id"])
                    if p is not None:
                        cadena.append(("FAMILIA", p["id"], p["nombre"]))
                while p is not None and p.get("padre_id") in padres:
                    p = padres[p["padre_id"]]
                    cadena.append(("FAMILIA", p["id"], p["nombre"]))
                if fila["nivel"] != "GENERAL":
                    cadena.append(("GENERAL", None, None))
                for n, d, nombre in cadena:
                    x = next((u for u in por_celda.get(celda_de(t.id, n, d), []) if u.contexto_tipo == "NINGUNO"), None)
                    if x is not None:
                        efectivo, de = x, {"nivel": n, "destino_id": d, "destino": nombre}
                        break
            propios = propios_familia.get((t.id, fila["id"]), 0) if fila["nivel"] in ("FAMILIA", "SIN_FAMILIA") else 0
            if fila["nivel"] == "FAMILIA":  # los artículos de sus categorías con un diseño propio ya están cubiertos
                propios += sum(x.get("articulos", 0) for x in filas if x["nivel"] == "CATEGORIA" and x["padre_id"] == fila["id"]
                               and any(u.contexto_tipo == "NINGUNO" for u in por_celda.get(celda_de(t.id, "CATEGORIA", x["id"]), [])))
            sin_cubrir = max(fila.get("articulos", 0) - propios, 0) if sujeto == "ARTICULO" else 1
            falta = efectivo is None and t.obligatoria and fila["nivel"] != "GENERAL" and sin_cubrir > 0
            if falta and sujeto == "ARTICULO" and fila["nivel"] != "CATEGORIA":  # sus artículos ya cuentan en la familia
                faltan_total += sin_cubrir
            fila["celdas"][t.id] = {
                "normal": {"uso_id": normal.id, "plantilla_id": normal.plantilla_id, "plantilla": _nombre_p(normal),
                           "version_id": normal.plantilla.version_vigente_id if normal.plantilla else None,
                           "accion": normal.accion or "USAR", "alcance": normal.alcance, "cantidad": normal.cantidad} if normal else None,
                "hereda": {"plantilla_id": efectivo.plantilla_id, "plantilla": _nombre_p(efectivo),
                           "version_id": efectivo.plantilla.version_vigente_id if efectivo.plantilla else None,
                           "accion": efectivo.accion or "USAR", "alcance": efectivo.alcance, **de} if normal is None and efectivo else None,
                "excepciones": len([u for u in lista if u.contexto_tipo != "NINGUNO"]),
                "propios": propios,
                "falta": falta}
    if sujeto == "ARTICULO" and any(t.obligatoria for t in ts) and filas[0]["articulos"]:
        sin_general = [t for t in ts if t.obligatoria and filas[0]["celdas"][t.id]["normal"] is None]
        cobertura = {"total": filas[0]["articulos"], "sin_diseno": min(faltan_total, filas[0]["articulos"]),
                     "tipos_sin_general": [t.id for t in sin_general]}
    else:
        cobertura = None
    return {"sujeto": sujeto, "tipos": [tipos.dict_tipo(db, t) for t in ts], "filas": filas, "cobertura": cobertura}


def _articulos_por_categoria(db: Session) -> dict:
    """Artículos activos por su categoría de etiquetado (la puesta a mano o la que se reconoce)."""
    res: dict = {}
    cache: dict = {}
    for a in db.scalars(select(Articulo).where(Articulo.activo.is_(True)).options(
            selectinload(Articulo.producto), selectinload(Articulo.grupo), selectinload(Articulo.familia_etiquetado))):
        c = reglas.categoria_de(db, a, campos_articulo(a), cache)
        if c is not None:
            res[c.id] = res.get(c.id, 0) + 1
    return res


def _propios_por_familia(db: Session, usos: list[UsoDiseno]) -> dict:
    """(tipo, familia) → cuántos artículos tienen un diseño normal propio (por producto o SKU)."""
    res: dict = {}
    for u in usos:
        if u.contexto_tipo != "NINGUNO" or u.nivel not in ("PRODUCTO", "SKU"):
            continue
        if u.nivel == "SKU":
            a = db.get(Articulo, u.articulo_id)
            f, n = (a.familia_efectiva, 1) if a else (None, 0)
        else:
            p = db.get(Producto, u.producto_id)
            f = familia_producto(db, p) if p else None
            n = db.scalar(select(func.count()).select_from(Articulo).where(Articulo.producto_id == u.producto_id,
                                                                           Articulo.activo.is_(True))) or 0
        clave = (u.tipo_etiqueta_id, f.id if f else None)
        res[clave] = res.get(clave, 0) + n
    return res


# ---- Desde el producto ---------------------------------------------------------------------------
def de_producto(db: Session, user: Usuario, producto_id: int) -> dict:
    """La pestaña Etiquetas del producto: su familia, qué diseño le toca en cada
    tipo de etiqueta de artículo y por qué, las excepciones que pueden cambiarlo
    y sus tallas con diseño propio."""
    exigir_interno(user, "etiquetas.ver", "etiquetas.configurar", "etiquetas.generar")
    from app.modulos.acceso.permisos import proveedor_filtro

    p = db.get(Producto, producto_id)
    prov = proveedor_filtro(user)
    if not p or (prov is not None and p.proveedor_id not in prov):
        raise ErrorNegocio("The product does not exist.", 404, "no_encontrado")
    arts = list(db.scalars(select(Articulo).where(Articulo.producto_id == p.id, Articulo.activo.is_(True)).order_by(Articulo.sku)))
    r = Resolvedor(db)
    familia = familia_producto(db, p)
    cats: dict = {}
    for a in arts:
        c = r.categoria(Sujeto("ARTICULO", articulo=a))
        if c is not None:
            cats.setdefault(c.id, {"id": c.id, "nombre": c.nombre, "manual": c.id == p.categoria_etiquetado_id, "tallas": 0})["tallas"] += 1
    res = {"producto": {"id": p.id, "estilo": p.estilo, "color": p.color, "nombre": p.nombre},
           "categorias": list(cats.values()),
           "familia": {"id": familia.id, "nombre": familia.nombre,
                       "origen": "PRODUCTO" if p.familia_etiquetado_id else "GRUPO"} if familia else None,
           "articulos": [{"id": a.id, "sku": a.sku, "talla": a.talla, "familia_propia": a.familia_etiquetado_id is not None}
                         for a in arts], "tipos": []}
    for t in r.tipos_de("ARTICULO"):
        tallas, resto = [], []
        for a in arts:
            e = r.elegir(Sujeto("ARTICULO", articulo=a), t)
            if e.porque.get("nivel") == "SKU":
                tallas.append({"articulo_id": a.id, "sku": a.sku, "talla": a.talla, "uso_id": e.uso.id,
                               "plantilla_id": e.plantilla.id if e.plantilla else None,
                               "plantilla": e.plantilla.nombre if e.plantilla else None, "no_lleva": e.no_lleva})
            else:
                resto.append((a, e))
        # Lo del producto es lo que le toca a la mayoría de sus tallas; las que salen distinto
        # (por una categoría, por ejemplo) se listan aparte con su porqué
        clave = lambda e: (e.uso.id if e.uso else None, e.plantilla.id if e.plantilla else None)  # noqa: E731
        cuenta: dict = {}
        for _, e in resto:
            cuenta[clave(e)] = cuenta.get(clave(e), 0) + 1
        mayor = max(cuenta, key=lambda k: cuenta[k]) if cuenta else None
        base = next((e for _, e in resto if clave(e) == mayor), None)
        if base is None and arts:
            base = r.elegir(Sujeto("ARTICULO", articulo=arts[0]), t)
        distintas = [{"articulo_id": a.id, "sku": a.sku, "talla": a.talla, "eleccion": e.dict()} for a, e in resto if clave(e) != mayor]
        escalones = r.escalones(Sujeto("ARTICULO", articulo=arts[0])) if arts else [("PRODUCTO", p.id), ("GENERAL", None)]
        excepciones = []
        for nivel, sid in escalones:
            x = r.celdas.get((t.id, nivel, sid))
            for u in (x.excepciones if x else []):
                excepciones.append({**dict_uso(db, u), "texto": reglas.texto_contexto(u)})
        propio = next((u for u in db.scalars(select(UsoDiseno).where(
            UsoDiseno.celda == celda_de(t.id, "PRODUCTO", p.id), UsoDiseno.eliminado_en.is_(None),
            UsoDiseno.contexto_tipo == "NINGUNO"))), None)
        res["tipos"].append({"tipo": tipos.dict_tipo(db, t), "eleccion": base.dict() if base else None,
                             "propio": dict_uso(db, propio) if propio else None, "excepciones": excepciones, "tallas": tallas,
                             "distintas": distintas})
    return res


def resolver(db: Session, user: Usuario, articulo_id: int | None = None, oc_id: int | None = None,
             tipo_empaque_id: int | None = None, sujeto: str = "ARTICULO") -> dict:
    """Qué diseño de cada tipo lleva un artículo (con o sin OC), un bulto o un documento, y por qué."""
    from app.modulos.etiquetado import campos, datos

    exigir_interno(user, "etiquetas.ver", "etiquetas.generar")
    a = datos.cargar_articulo(db, user, articulo_id) if articulo_id else None
    oc = datos.cargar_oc(db, user, oc_id) if oc_id else None
    s = Sujeto(sujeto.upper(), articulo=a, oc=oc, tipo_empaque_id=tipo_empaque_id,
               valores={**(campos.valores_articulo(a) if a else {}), **(campos.valores_oc(db, oc) if oc else {})})
    r = Resolvedor(db)
    # En un bulto, los tipos que no van en ese empaque no se resuelven (no se imprimen ahí)
    ts = [t for t in r.tipos_de(s.sujeto) if s.sujeto != "BULTO" or tipo_empaque_id is None
          or tipos.aplica(tipos.empaques_de(db, t.id), tipo_empaque_id)]
    return {"elecciones": [r.elegir(s, t).dict() for t in ts]}
