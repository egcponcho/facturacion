"""Integraciones: configuración, mapeos versionados, ejecución y bitácora.

Flujo de ENTRADA (p. ej. OCs que exporta el ERP):
  contenido → adaptador.leer (nombres externos) → traducir_entrada (mapeo
  vigente: nombres internos, valores por defecto, códigos, fechas) → vista
  previa del servicio del núcleo → aplicar → referencias externas.
  La huella (sha256) del contenido impide aplicar dos veces lo mismo.

Flujo de SALIDA (p. ej. facturas finalizadas hacia el ERP):
  filas del núcleo → traducir_salida (nombres y códigos externos) →
  adaptador.escribir → archivo, con su ejecución y la referencia de lo enviado.

Permisos: `integraciones.configurar` para crear integraciones y mapeos;
`integraciones.ejecutar` (más el permiso de la entidad en el núcleo, p. ej.
`oc.importar`) para intercambiar datos; `integraciones.ver` para la bitácora.
"""
import hashlib
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import EjecucionIntegracion, Integracion, IntegracionMapeo, ReferenciaExterna, Usuario
from app.modelos.base import ahora
from app.modulos.acceso.permisos import exigir
from app.modulos.acceso.preferencias import FORMATOS_FECHA
from app.modulos.comun.historial import registrar
from app.modulos.integraciones import adaptadores, entidades

MAX_ERRORES = 200  # errores por fila que guarda la bitácora (el resumen los cuenta todos)


# ---- Integraciones --------------------------------------------------------------
def _dict(db: Session, x: Integracion) -> dict:
    mapeos = [m for m in x.mapeos if m.vigente]
    ultima = db.scalar(select(EjecucionIntegracion).where(EjecucionIntegracion.integracion_id == x.id)
                       .order_by(EjecucionIntegracion.id.desc()).limit(1))
    return {"id": x.id, "codigo": x.codigo, "nombre": x.nombre, "sistema": x.sistema, "adaptador": x.adaptador,
            "parametros": x.parametros or {}, "activa": x.activa,
            "mapeos": [_mapeo(m) for m in sorted(mapeos, key=lambda m: (m.entidad, m.direccion))],
            "ultima_ejecucion": _ejecucion(ultima) if ultima else None}


def _mapeo(m: IntegracionMapeo) -> dict:
    return {"id": m.id, "entidad": m.entidad, "direccion": m.direccion, "version": m.version, "vigente": m.vigente,
            "campos": m.campos or {}, "valores": m.valores or {}, "codigos": m.codigos or {},
            "formato_fecha": m.formato_fecha, "creado_en": m.creado_en}


def _ejecucion(e: EjecucionIntegracion, con_filas: bool = False) -> dict:
    d = {"id": e.id, "integracion_id": e.integracion_id, "entidad": e.entidad, "direccion": e.direccion,
         "estado": e.estado, "archivo": e.archivo, "resumen": e.resumen or {}, "errores": (e.errores or [])[:MAX_ERRORES],
         "usuario_id": e.usuario_id, "iniciada_en": e.iniciada_en, "terminada_en": e.terminada_en,
         "mapeo_id": e.mapeo_id}
    if con_filas:
        d["filas"] = e.filas or []
    return d


def listar(db: Session, user: Usuario) -> dict:
    exigir(user, "integraciones.ver")
    return {"integraciones": [_dict(db, x) for x in db.scalars(select(Integracion).order_by(Integracion.nombre))],
            "adaptadores": adaptadores.catalogo(), "entidades": entidades.catalogo(),
            "formatos_fecha": list(FORMATOS_FECHA)}


def _integracion(db: Session, integracion_id: int) -> Integracion:
    x = db.get(Integracion, integracion_id)
    if x is None:
        raise ErrorNegocio("The integration does not exist.", 404, "no_encontrado")
    return x


def guardar(db: Session, user: Usuario, datos: dict, integracion_id: int | None = None) -> dict:
    """Crea o modifica una integración. El código es único en la organización."""
    exigir(user, "integraciones.configurar")
    codigo = str(datos.get("codigo") or "").strip().upper()[:20]
    nombre = str(datos.get("nombre") or "").strip()[:100]
    if not codigo or not nombre:
        raise ErrorNegocio("Write the code and the name of the integration.", 422, "validacion")
    adaptador = str(datos.get("adaptador") or "")
    parametros = adaptadores.validar_parametros(adaptador, datos.get("parametros"))
    x = _integracion(db, integracion_id) if integracion_id else None
    otra = db.scalar(select(Integracion).where(Integracion.codigo == codigo))
    if otra is not None and otra is not x:
        raise ErrorNegocio(f"Another integration already has the code {codigo}.", 409, "duplicado")
    if x is None:
        x = Integracion(codigo=codigo)
        db.add(x)
    x.codigo, x.nombre, x.adaptador, x.parametros = codigo, nombre, adaptador, parametros
    x.sistema = str(datos.get("sistema") or "").strip()[:60] or None
    x.activa = bool(datos.get("activa", True))
    db.flush()
    registrar(db, user, "integracion", x.id, "guardar", {"codigo": codigo, "adaptador": adaptador})
    return _dict(db, x)


# ---- Mapeos versionados ---------------------------------------------------------
def mapeo_vigente(db: Session, x: Integracion, entidad: str, direccion: str) -> IntegracionMapeo | None:
    return db.scalar(select(IntegracionMapeo).where(
        IntegracionMapeo.integracion_id == x.id, IntegracionMapeo.entidad == entidad,
        IntegracionMapeo.direccion == direccion, IntegracionMapeo.vigente.is_(True)))


def guardar_mapeo(db: Session, user: Usuario, integracion_id: int, entidad: str, direccion: str, datos: dict) -> dict:
    """Guarda el mapeo como una versión nueva (la anterior queda como histórica).
    Solo acepta campos internos de la entidad; en una entrada, cada campo
    obligatorio debe tener columna externa o valor por defecto."""
    exigir(user, "integraciones.configurar")
    x = _integracion(db, integracion_id)
    e = entidades.de(entidad, direccion)
    internos = {c["campo"]: c for c in e["campos"]()}
    campos = {k: str(v).strip()[:120] for k, v in (datos.get("campos") or {}).items() if str(v or "").strip()}
    valores = {k: str(v).strip()[:120] for k, v in (datos.get("valores") or {}).items() if str(v or "").strip()}
    codigos = {k: {str(a).strip(): str(b).strip() for a, b in (v or {}).items() if str(a).strip() and str(b).strip()}
               for k, v in (datos.get("codigos") or {}).items()}
    codigos = {k: v for k, v in codigos.items() if v}
    desconocidos = sorted((set(campos) | set(valores) | set(codigos)) - set(internos))
    if desconocidos:
        raise ErrorNegocio(f"Unknown fields for {entidad}: {', '.join(desconocidos)}.", 422, "validacion",
                           {"desconocidos": desconocidos})
    formato = datos.get("formato_fecha") or None
    if formato and formato not in FORMATOS_FECHA:
        raise ErrorNegocio("Unknown date format.", 422, "validacion")
    if direccion == "ENTRADA":
        # Un campo obligatorio sin columna se busca con su nombre interno; un valor por
        # defecto no puede reemplazar lo que identifica la línea
        from app.modulos.compras.perfiles import SIN_DEFECTO

        fijos = sorted(c for c in valores if c in SIN_DEFECTO)
        if entidad == "ordenes_compra" and fijos:
            raise ErrorNegocio(f"These fields identify the line and cannot have a default value: {', '.join(fijos)}.",
                               422, "validacion")
    actual = mapeo_vigente(db, x, entidad, direccion)
    nuevo = {"campos": campos, "valores": valores, "codigos": codigos, "formato_fecha": formato}
    if actual is not None and {k: getattr(actual, k) or ({} if k != "formato_fecha" else None) for k in nuevo} == nuevo:
        return _mapeo(actual)  # sin cambios: no se crea otra versión
    version = 1
    if actual is not None:
        actual.vigente = False
        version = actual.version + 1
        db.flush()
    m = IntegracionMapeo(integracion_id=x.id, entidad=entidad, direccion=direccion, version=version, vigente=True,
                         creado_por=user.id, **nuevo)
    db.add(m)
    db.flush()
    registrar(db, user, "integracion", x.id, "mapeo", {"entidad": entidad, "direccion": direccion, "version": version})
    return _mapeo(m)


def versiones_mapeo(db: Session, user: Usuario, integracion_id: int, entidad: str, direccion: str) -> list[dict]:
    exigir(user, "integraciones.ver")
    return [_mapeo(m) for m in db.scalars(select(IntegracionMapeo).where(
        IntegracionMapeo.integracion_id == integracion_id, IntegracionMapeo.entidad == entidad,
        IntegracionMapeo.direccion == direccion).order_by(IntegracionMapeo.version.desc()))]


# ---- Traducción -----------------------------------------------------------------
def _clave(texto: str) -> str:
    return " ".join(str(texto).strip().lower().split())


def traducir_entrada(filas: list[dict], mapeo: IntegracionMapeo | None, campos: list[dict]) -> tuple[list[dict], list[dict]]:
    """Filas externas → filas con los campos internos. Sin mapeo para un campo,
    se busca una columna con su nombre interno. Devuelve (filas válidas, errores)."""
    from app.modulos.compras.perfiles import fecha_iso

    m_campos = (mapeo.campos if mapeo else None) or {}
    m_valores = (mapeo.valores if mapeo else None) or {}
    m_codigos = (mapeo.codigos if mapeo else None) or {}
    formato = mapeo.formato_fecha if mapeo else None
    validas, errores = [], []
    for fila in filas:
        por_clave = {_clave(k): v for k, v in fila.items() if k != "_fila"}
        interna, faltan = {"_fila": fila.get("_fila")}, []
        for c in campos:
            nombre = c["campo"]
            valor = por_clave.get(_clave(m_campos.get(nombre) or nombre), "")
            valor = str(valor).strip() if valor is not None else ""
            if not valor:
                valor = m_valores.get(nombre, "")
            if valor and nombre in m_codigos:
                valor = m_codigos[nombre].get(valor, valor)
            if valor and formato and c.get("fecha"):
                valor = fecha_iso(valor, formato)
            if valor:
                interna[nombre] = valor
            elif c.get("requerido"):
                faltan.append(m_campos.get(nombre) or nombre)
        if faltan:
            errores.append({"fila": fila.get("_fila"), "mensajes": [f"Missing required values: {', '.join(faltan)}."]})
        else:
            validas.append(interna)
    return validas, errores


def traducir_salida(filas: list[dict], mapeo: IntegracionMapeo | None, campos: list[dict]) -> tuple[list[dict], list[str]]:
    """Filas internas → filas con los nombres y códigos externos. Sin mapeo, salen
    todos los campos con su nombre interno; con mapeo, solo los mapeados."""
    m_campos = (mapeo.campos if mapeo else None) or {}
    m_codigos = (mapeo.codigos if mapeo else None) or {}
    inverso = {k: {b: a for a, b in v.items()} for k, v in m_codigos.items()}
    elegidos = [c["campo"] for c in campos if not m_campos or c["campo"] in m_campos]
    columnas = [m_campos.get(c) or c for c in elegidos]
    res = []
    for f in filas:
        fila = {}
        for c, col in zip(elegidos, columnas, strict=True):
            v = f.get(c)
            if v is not None and c in inverso:
                v = inverso[c].get(str(v), v)
            fila[col] = v
        res.append(fila)
    return res, columnas


def _huella(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def _referenciar(db: Session, x: Integracion, entidad: str, pares: list[tuple[int, str]], ejecucion_id: int) -> int:
    """Guarda o actualiza la referencia externa de cada registro tocado."""
    n = 0
    for interno_id, codigo in pares:
        codigo = str(codigo)[:120]
        ref = db.scalar(select(ReferenciaExterna).where(
            ReferenciaExterna.integracion_id == x.id, ReferenciaExterna.entidad == entidad,
            ReferenciaExterna.interno_id == interno_id))
        if ref is None:
            ref = db.scalar(select(ReferenciaExterna).where(
                ReferenciaExterna.integracion_id == x.id, ReferenciaExterna.entidad == entidad,
                ReferenciaExterna.codigo_externo == codigo))
        if ref is None:
            ref = ReferenciaExterna(integracion_id=x.id, entidad=entidad, interno_id=interno_id, codigo_externo=codigo)
            db.add(ref)
        ref.interno_id, ref.codigo_externo, ref.ejecucion_id = interno_id, codigo, ejecucion_id
        n += 1
    db.flush()
    return n


def _activa(db: Session, integracion_id: int) -> Integracion:
    x = _integracion(db, integracion_id)
    if not x.activa:
        raise ErrorNegocio("The integration is inactive.", 409, "inactiva")
    return x


# ---- Entrada ----------------------------------------------------------------------
def entrada_previa(db: Session, user: Usuario, integracion_id: int, entidad: str, archivo: str, contenido: bytes) -> dict:
    exigir(user, "integraciones.ejecutar")
    e = entidades.de(entidad, "ENTRADA")
    exigir(user, e["permiso"])
    x = _activa(db, integracion_id)
    huella = _huella(contenido)
    previa = db.scalar(select(EjecucionIntegracion).where(
        EjecucionIntegracion.integracion_id == x.id, EjecucionIntegracion.entidad == entidad,
        EjecucionIntegracion.huella == huella, EjecucionIntegracion.estado.in_(("APLICADA", "CON_ERRORES"))))
    if previa is not None:
        raise ErrorNegocio("This same content was already applied by this integration.", 409, "ya_aplicada",
                           {"ejecucion_id": previa.id})
    mapeo = mapeo_vigente(db, x, entidad, "ENTRADA")
    externas = adaptadores.de(x.adaptador).leer(contenido, archivo, x.parametros or {})
    if not externas:
        raise ErrorNegocio("The content has no rows with data.", 422, "archivo_vacio")
    validas, errores = traducir_entrada(externas, mapeo, e["campos"]())
    ejec = EjecucionIntegracion(integracion_id=x.id, mapeo_id=mapeo.id if mapeo else None, entidad=entidad,
                                direccion="ENTRADA", estado="PREVIA", archivo=archivo[:300], huella=huella,
                                usuario_id=user.id, filas=validas, errores=errores[:MAX_ERRORES])
    db.add(ejec)
    db.flush()
    previa_nucleo = entidades.previa_ordenes(db, user, validas, archivo) if validas else {"resumen": {}, "filas": []}
    ejec.importacion_oc_id = previa_nucleo.get("importacion_oc_id")
    ejec.resumen = {**previa_nucleo["resumen"], "leidas": len(externas), "rechazadas": len(errores)}
    db.flush()
    return {**_ejecucion(ejec), "filas": previa_nucleo["filas"]}


def entrada_aplicar(db: Session, user: Usuario, ejecucion_id: int) -> dict:
    exigir(user, "integraciones.ejecutar")
    ejec = db.get(EjecucionIntegracion, ejecucion_id)
    if ejec is None or ejec.direccion != "ENTRADA":
        raise ErrorNegocio("The run does not exist.", 404, "no_encontrado")
    e = entidades.de(ejec.entidad, "ENTRADA")
    exigir(user, e["permiso"])
    if ejec.estado in ("APLICADA", "CON_ERRORES"):
        return {**_ejecucion(ejec), "ya_aplicada": True}
    x = _activa(db, ejec.integracion_id)
    otra = db.scalar(select(EjecucionIntegracion.id).where(
        EjecucionIntegracion.integracion_id == x.id, EjecucionIntegracion.entidad == ejec.entidad,
        EjecucionIntegracion.huella == ejec.huella, EjecucionIntegracion.id != ejec.id,
        EjecucionIntegracion.estado.in_(("APLICADA", "CON_ERRORES"))))
    if otra:
        raise ErrorNegocio("This same content was already applied by this integration.", 409, "ya_aplicada",
                           {"ejecucion_id": otra})
    res = {"resumen": {}, "referencias": []}
    if ejec.importacion_oc_id:
        res = entidades.aplicar_ordenes(db, user, ejec.importacion_oc_id)
    referenciadas = _referenciar(db, x, ejec.entidad, res.get("referencias", []), ejec.id)
    ejec.resumen = {**(ejec.resumen or {}), **res.get("resumen", {}), "aplicadas": res.get("aplicadas", 0),
                    "referencias": referenciadas}
    ejec.estado = "CON_ERRORES" if ejec.errores or (res.get("resumen") or {}).get("error") else "APLICADA"
    ejec.terminada_en = ahora()
    db.flush()
    registrar(db, user, "integracion", x.id, "entrada", {"ejecucion": ejec.id, "entidad": ejec.entidad, **ejec.resumen})
    return _ejecucion(ejec)


# ---- Salida -----------------------------------------------------------------------
def salida(db: Session, user: Usuario, integracion_id: int, entidad: str, solo_nuevas: bool = True,
           desde: date | None = None) -> tuple[bytes, str, str, dict]:
    """Arma el contenido para el sistema externo y deja la ejecución y las
    referencias de lo enviado. Devuelve (contenido, tipo, nombre, ejecución)."""
    exigir(user, "integraciones.ejecutar")
    e = entidades.de(entidad, "SALIDA")
    exigir(user, e["permiso"])
    x = _activa(db, integracion_id)
    excluir = set()
    if solo_nuevas:
        excluir = set(db.scalars(select(ReferenciaExterna.interno_id).where(
            ReferenciaExterna.integracion_id == x.id, ReferenciaExterna.entidad == entidad)))
    filas, enviadas = entidades.filas_facturas(db, excluir, desde)
    mapeo = mapeo_vigente(db, x, entidad, "SALIDA")
    externas, columnas = traducir_salida(filas, mapeo, e["campos"]())
    contenido, tipo, extension = adaptadores.de(x.adaptador).escribir(externas, columnas, x.parametros or {})
    nombre = f"{x.codigo.lower()}_{entidad}_{date.today().isoformat()}.{extension}"
    ejec = EjecucionIntegracion(integracion_id=x.id, mapeo_id=mapeo.id if mapeo else None, entidad=entidad,
                                direccion="SALIDA", estado="APLICADA", archivo=nombre, huella=_huella(contenido),
                                usuario_id=user.id, resumen={"registros": len(enviadas), "filas": len(filas)},
                                terminada_en=ahora())
    db.add(ejec)
    db.flush()
    _referenciar(db, x, entidad, enviadas, ejec.id)
    registrar(db, user, "integracion", x.id, "salida", {"ejecucion": ejec.id, "entidad": entidad, **ejec.resumen})
    return contenido, tipo, nombre, _ejecucion(ejec)


# ---- Bitácora y referencias ------------------------------------------------------
def ejecuciones(db: Session, user: Usuario, integracion_id: int, page: int = 1, size: int = 25) -> dict:
    exigir(user, "integraciones.ver")
    _integracion(db, integracion_id)
    q = select(EjecucionIntegracion).where(EjecucionIntegracion.integracion_id == integracion_id)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = db.scalars(q.order_by(EjecucionIntegracion.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {"items": [_ejecucion(x) for x in items], "total": total, "page": page, "size": size}


def ejecucion(db: Session, user: Usuario, ejecucion_id: int) -> dict:
    exigir(user, "integraciones.ver")
    x = db.get(EjecucionIntegracion, ejecucion_id)
    if x is None:
        raise ErrorNegocio("The run does not exist.", 404, "no_encontrado")
    return _ejecucion(x, con_filas=True)


def referencias(db: Session, user: Usuario, integracion_id: int, entidad: str | None = None) -> list[dict]:
    exigir(user, "integraciones.ver")
    q = select(ReferenciaExterna).where(ReferenciaExterna.integracion_id == integracion_id)
    if entidad:
        q = q.where(ReferenciaExterna.entidad == entidad)
    return [{"entidad": r.entidad, "interno_id": r.interno_id, "codigo_externo": r.codigo_externo,
             "ejecucion_id": r.ejecucion_id, "actualizado_en": r.actualizado_en}
            for r in db.scalars(q.order_by(ReferenciaExterna.actualizado_en.desc()).limit(500))]
