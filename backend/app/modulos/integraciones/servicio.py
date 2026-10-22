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
from sqlalchemy.exc import IntegrityError
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
            errores.append({"fila": fila.get("_fila"), "mensajes": [f"Missing required values: {', '.join(f'«{x}»' for x in faltan)}."]})
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


def _referencia(db: Session, x: Integracion, entidad: str, **filtro) -> ReferenciaExterna | None:
    q = select(ReferenciaExterna).where(ReferenciaExterna.integracion_id == x.id, ReferenciaExterna.entidad == entidad)
    for campo, valor in filtro.items():
        q = q.where(getattr(ReferenciaExterna, campo) == valor)
    return db.scalar(q)


def _referenciar(db: Session, x: Integracion, entidad: str, pares: list[tuple[int, str]],
                 ejecucion_id: int) -> tuple[int, list[dict]]:
    """Vincula cada registro tocado con su código externo. Nunca reasigna en silencio: si el
    código ya apunta a otro registro, o el registro ya tiene otro código, es un conflicto que
    queda en la ejecución y se resuelve desvinculando la referencia (con motivo). La unicidad
    la garantizan las llaves únicas de la base: si otra ejecución vinculó lo mismo al mismo
    tiempo, el alta falla y también queda como conflicto."""
    hechas, conflictos = 0, []
    for interno_id, codigo in pares:
        codigo = str(codigo)[:120]
        por_interno = _referencia(db, x, entidad, interno_id=interno_id)
        por_codigo = _referencia(db, x, entidad, codigo_externo=codigo)
        if por_interno is not None and por_interno is por_codigo:
            por_interno.ejecucion_id = ejecucion_id
            hechas += 1
            continue
        if por_codigo is not None:
            conflictos.append({"motivo": "codigo_ocupado", "codigo_externo": codigo, "interno_id": interno_id,
                               "vinculado_a": por_codigo.interno_id, "referencia_id": por_codigo.id})
            continue
        if por_interno is not None:
            conflictos.append({"motivo": "otro_codigo", "codigo_externo": codigo, "interno_id": interno_id,
                               "codigo_actual": por_interno.codigo_externo, "referencia_id": por_interno.id})
            continue
        try:
            with db.begin_nested():
                db.add(ReferenciaExterna(integracion_id=x.id, entidad=entidad, interno_id=interno_id,
                                         codigo_externo=codigo, ejecucion_id=ejecucion_id))
                db.flush()
        except IntegrityError:
            conflictos.append({"motivo": "simultaneo", "codigo_externo": codigo, "interno_id": interno_id})
            continue
        hechas += 1
    db.flush()
    return hechas, conflictos


def _errores_de_conflictos(conflictos: list[dict]) -> list[dict]:
    """Los conflictos de referencias como errores de la ejecución, con lo que hay que hacer."""
    res = []
    for c in conflictos:
        if c["motivo"] == "codigo_ocupado":
            m = (f"The external code {c['codigo_externo']} is already linked to another record (id {c['vinculado_a']}): "
                 "it was not reassigned. If the link is wrong, unlink it and run again.")
        elif c["motivo"] == "otro_codigo":
            m = (f"The record (id {c['interno_id']}) already has the external code {c['codigo_actual']}: "
                 f"{c['codigo_externo']} was not linked. If the code changed, unlink the current one and run again.")
        else:
            m = f"The external code {c['codigo_externo']} was linked by another run at the same time: it was not linked."
        res.append({"fila": None, "referencia": c["codigo_externo"], "mensajes": [m], "conflicto": c})
    return res


def _aplicada(db: Session, integracion_id: int, entidad: str, huella: str, mapeo_id: int | None,
              distinta_de: int | None = None) -> int | None:
    """La ejecución que ya aplicó este contenido con esta versión del mapeo, si la hay."""
    q = select(EjecucionIntegracion.id).where(
        EjecucionIntegracion.integracion_id == integracion_id, EjecucionIntegracion.entidad == entidad,
        EjecucionIntegracion.huella == huella, EjecucionIntegracion.estado.in_(("APLICADA", "CON_ERRORES")),
        EjecucionIntegracion.mapeo_id.is_(None) if mapeo_id is None else EjecucionIntegracion.mapeo_id == mapeo_id)
    if distinta_de is not None:
        q = q.where(EjecucionIntegracion.id != distinta_de)
    return db.scalar(q.limit(1))


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
    mapeo = mapeo_vigente(db, x, entidad, "ENTRADA")
    # El mismo contenido con la misma versión del mapeo no se aplica dos veces; con otro mapeo
    # (se corrigió cómo se lee) sí se puede volver a cargar: el núcleo no repite lo que ya está
    previa = _aplicada(db, x.id, entidad, huella, mapeo.id if mapeo else None)
    if previa is not None:
        raise ErrorNegocio("This same content was already applied by this integration.", 409, "ya_aplicada",
                           {"ejecucion_id": previa})
    externas = adaptadores.de(x.adaptador).leer(contenido, archivo, x.parametros or {})
    if not externas:
        raise ErrorNegocio("The content has no rows with data.", 422, "archivo_vacio")
    campos = e["campos"]()
    validas, errores = traducir_entrada(externas, mapeo, campos)
    ejec = EjecucionIntegracion(integracion_id=x.id, mapeo_id=mapeo.id if mapeo else None, entidad=entidad,
                                direccion="ENTRADA", estado="PREVIA", archivo=archivo[:300], huella=huella,
                                usuario_id=user.id, filas=validas)
    db.add(ejec)
    db.flush()
    previa_nucleo = entidades.previa_ordenes(db, user, validas, archivo) if validas else {"resumen": {}, "filas": []}
    # Lo que el núcleo no aplicará (error o conflicto) también es un rechazo de la ejecución
    errores += [{"fila": f.get("fila"), "mensajes": f.get("mensajes") or []}
                for f in previa_nucleo["filas"] if f.get("estado") in ("error", "conflicto")]
    ejec.errores = _con_fila_original(errores, externas)
    ejec.importacion_oc_id = previa_nucleo.get("importacion_oc_id")
    rechazadas_nucleo = len([f for f in previa_nucleo["filas"] if f.get("estado") in ("error", "conflicto")])
    ejec.resumen = {**previa_nucleo["resumen"], "leidas": len(externas), "rechazadas": len(errores) - rechazadas_nucleo,
                    "aplicables": len(validas) - rechazadas_nucleo}
    db.flush()
    return {**_ejecucion(ejec), "filas": previa_nucleo["filas"], "estructura": estructura(externas, mapeo, campos)}


def _con_fila_original(errores: list[dict], externas: list[dict]) -> list[dict]:
    """Los errores (como mucho MAX_ERRORES) con la fila tal como vino, para descargarlos,
    corregirlos y volver a subirlos. No se guarda nada más del archivo."""
    por_fila = {f.get("_fila"): f for f in externas}
    res = []
    for err in sorted(errores, key=lambda x: (x.get("fila") is None, x.get("fila") or 0))[:MAX_ERRORES]:
        original = por_fila.get(err.get("fila"))
        res.append({**err, "datos": {k: v for k, v in original.items() if k != "_fila"} if original else {}})
    return res


def estructura(externas: list[dict], mapeo: IntegracionMapeo | None, campos: list[dict]) -> dict:
    """Las columnas que trae el contenido y, por cada campo del sistema, la columna que se busca,
    si está y si tiene valor por defecto: lo que hay que corregir en el mapeo antes de aplicar."""
    columnas = []
    for f in externas:
        for k in f:
            if k != "_fila" and k not in columnas:
                columnas.append(k)
    presentes = {_clave(c) for c in columnas}
    m_campos = (mapeo.campos if mapeo else None) or {}
    m_valores = (mapeo.valores if mapeo else None) or {}
    res = []
    for c in campos:
        columna = m_campos.get(c["campo"]) or c["campo"]
        res.append({"campo": c["campo"], "etiqueta": c.get("etiqueta"), "requerido": bool(c.get("requerido")),
                    "columna": columna, "encontrada": _clave(columna) in presentes,
                    "por_defecto": m_valores.get(c["campo"])})
    usadas = {_clave(x["columna"]) for x in res}
    return {"columnas": columnas, "campos": res, "sin_usar": [c for c in columnas if _clave(c) not in usadas],
            "faltan": [x["campo"] for x in res if x["requerido"] and not x["encontrada"] and not x["por_defecto"]]}


def rechazadas(db: Session, user: Usuario, ejecucion_id: int) -> tuple[bytes, str]:
    """Las filas rechazadas de una ejecución en CSV, con sus columnas originales y el motivo."""
    import csv
    import io

    from app.modulos.documentos.idioma_doc import L, armado

    exigir(user, "integraciones.ver")
    x = db.get(EjecucionIntegracion, ejecucion_id)
    if x is None:
        raise ErrorNegocio("The run does not exist.", 404, "no_encontrado")
    filas = [err for err in (x.errores or []) if err.get("fila") is not None]
    if not filas:
        raise ErrorNegocio("This run has no rejected rows.", 404, "sin_rechazadas")
    columnas = []
    for err in filas:
        for k in err.get("datos") or {}:
            if k not in columnas:
                columnas.append(k)
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow([L("Row"), *columnas, L("Reason")])
    for err in filas:
        datos = err.get("datos") or {}
        w.writerow([err.get("fila"), *[datos.get(c, "") for c in columnas], " ".join(armado(m) for m in err.get("mensajes") or [])])
    nombre = (x.archivo or "run").rsplit(".", 1)[0][:80]
    return salida.getvalue().encode("utf-8-sig"), f"{nombre}_rejected.csv"


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
    if not (ejec.resumen or {}).get("aplicables", len(ejec.filas or [])):
        raise ErrorNegocio("There are no valid rows to apply: fix the file or the mapping and upload it again.", 422,
                           "sin_filas_validas")
    otra = _aplicada(db, x.id, ejec.entidad, ejec.huella, ejec.mapeo_id, distinta_de=ejec.id)
    if otra:
        raise ErrorNegocio("This same content was already applied by this integration.", 409, "ya_aplicada",
                           {"ejecucion_id": otra})
    res = {"resumen": {}, "referencias": []}
    if ejec.importacion_oc_id:
        res = entidades.aplicar_ordenes(db, user, ejec.importacion_oc_id)
    referenciadas, conflictos = _referenciar(db, x, ejec.entidad, res.get("referencias", []), ejec.id)
    if conflictos:
        ejec.errores = [*(ejec.errores or []), *_errores_de_conflictos(conflictos)][:MAX_ERRORES]
    ejec.resumen = {**(ejec.resumen or {}), **res.get("resumen", {}), "aplicadas": res.get("aplicadas", 0),
                    "referencias": referenciadas, "conflictos": len(conflictos)}
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
    _, conflictos = _referenciar(db, x, entidad, enviadas, ejec.id)
    if conflictos:
        ejec.errores = _errores_de_conflictos(conflictos)[:MAX_ERRORES]
        ejec.estado = "CON_ERRORES"
        ejec.resumen = {**ejec.resumen, "conflictos": len(conflictos)}
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
    return [{"id": r.id, "entidad": r.entidad, "interno_id": r.interno_id, "codigo_externo": r.codigo_externo,
             "ejecucion_id": r.ejecucion_id, "actualizado_en": r.actualizado_en}
            for r in db.scalars(q.order_by(ReferenciaExterna.actualizado_en.desc()).limit(500))]


def desvincular(db: Session, user: Usuario, integracion_id: int, referencia_id: int, datos: dict) -> dict:
    """Quita el vínculo de un registro con su código externo (la forma autorizada de resolver un
    conflicto): pide motivo y queda en el historial; la próxima ejecución vuelve a vincular."""
    exigir(user, "integraciones.configurar")
    x = _integracion(db, integracion_id)
    motivo = str(datos.get("motivo") or "").strip()[:300]
    if len(motivo) < 3:
        raise ErrorNegocio("Write why the link is removed.", 422, "validacion", [{"campo": "motivo", "mensaje": "Required."}])
    r = db.get(ReferenciaExterna, referencia_id)
    if r is None or r.integracion_id != x.id:
        raise ErrorNegocio("The external reference does not exist.", 404, "no_encontrado")
    detalle = {"entidad": r.entidad, "interno_id": r.interno_id, "codigo_externo": r.codigo_externo}
    db.delete(r)
    db.flush()
    registrar(db, user, "integracion", x.id, "desvincular", detalle, motivo)
    return {"ok": True, **detalle}
