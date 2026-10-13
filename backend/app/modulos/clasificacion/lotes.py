"""Cargas oficiales por etapas: previa (staging) → diferencias → publicar.

La previa corre la misma carga del paquete (oficial.importar, con todas sus
validaciones) en una sesión aparte y anota cada registro nuevo, cambiado o
reemplazado con sus valores antes y después; luego deshace todo. Nada cambia
hasta publicar. Al publicar se vuelve a aplicar el mismo archivo. Las cargas
nunca borran lo publicado (solo se reemplazan las condiciones de una regla
cuando la hoja las trae completas).
"""
import hashlib
from datetime import date, datetime

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import FilaLoteOficial, LoteOficial, Usuario, VersionDataset, ahora
from app.modulos.acceso.permisos import exigir
from app.modulos.comun.historial import registrar

# Datos oficiales: de una versión publicada no se cambian (la configuración, como el control de capítulos, sí)
OFICIALES = {"incisos_nacionales", "regulaciones", "reglas_impuesto", "nodos_arancel"}
IGNORAR = {"id", "importado_en", "actualizado_en", "creado_en"}
MAX_FILAS = 5000
NOMBRE = {"fuentes_oficiales": "Sources", "versiones_dataset": "Versions", "paises_arancel": "Countries",
          "control_capitulos": "Chapters", "dominios_clasificacion": "Domains", "dominio_capitulos": "Domain chapters",
          "atributos_def": "Attributes", "atributo_opciones": "Attribute options", "atributo_ambitos": "Attribute scopes",
          "reglas_clasificacion": "Classification rules", "reglas_condiciones": "Rule conditions",
          "incisos_nacionales": "National codes", "regulaciones": "Regulations", "reglas_impuesto": "Taxes"}


def _valor(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bytes):
        return None
    return v


def _columnas(o) -> dict:
    return {a.key: _valor(getattr(o, a.key)) for a in inspect(o).mapper.column_attrs if a.key not in IGNORAR}


def _clave(o) -> str:
    """Clave natural legible (código, ISO, capítulo, código del padre…)."""
    partes, st = [], inspect(o)
    for padre in ("atributo", "regla", "dominio"):
        if padre in st.mapper.relationships:
            v = st.attrs[padre].loaded_value
            if hasattr(v, "codigo"):
                partes.append(v.codigo)
    for k in ("pais", "iso", "codigo", "capitulo", "tipo_ambito", "codigo_ambito", "campo"):
        v = getattr(o, k, None)
        if v not in (None, "") and str(v) not in partes:
            partes.append(str(v))
    return " · ".join(partes)[:120] or str(getattr(o, "id", ""))


def _diferencias(db: Session, contenido: bytes, nombre: str) -> tuple[dict, list[dict]]:
    """Corre la carga en una sesión aparte, anota los cambios y la deshace."""
    from app.modulos.clasificacion import oficial

    cambios: dict[int, dict] = {}

    def anotar(s, _ctx, _inst):
        with s.no_autoflush:
            for o in s.new:
                cambios[id(o)] = {"o": o, "accion": "NUEVO", "antes": None}
            for o in s.dirty:
                if id(o) in cambios or not s.is_modified(o, include_collections=False):
                    continue
                st = inspect(o)
                antes = {}
                for a in st.mapper.column_attrs:
                    if a.key in IGNORAR:
                        continue
                    h = st.attrs[a.key].history
                    if h.deleted and h.added and h.deleted[0] != h.added[0]:
                        antes[a.key] = _valor(h.deleted[0])
                if antes:
                    cambios[id(o)] = {"o": o, "accion": "CAMBIO", "antes": antes}
            for o in s.deleted:
                cambios[id(o)] = {"o": o, "accion": "ELIMINADO", "antes": _columnas(o), "despues": None}

    previa = Session(bind=db.get_bind(), autoflush=False)
    event.listen(previa, "before_flush", anotar)
    try:
        res = oficial.importar(previa, contenido, None, nombre)
        previa.flush()
        publicadas = {v.id: v.codigo for v in previa.scalars(select(VersionDataset).where(VersionDataset.estado == "PUBLICADA"))}
        # Los registros nuevos reciben ids que se descartan con la previa (y en
        # PostgreSQL la secuencia no retrocede): se nombran por su clave natural
        nuevos = {(c["o"].__tablename__, c["o"].id): _clave(c["o"]) for c in cambios.values() if c["accion"] == "NUEVO"}

        def natural(o, datos):
            if not datos:
                return datos
            datos = dict(datos)
            for a in inspect(o).mapper.column_attrs:
                for fk in a.columns[0].foreign_keys:
                    ref = (fk.column.table.name, datos.get(a.key))
                    if ref in nuevos:
                        datos[a.key] = f"{ref[0]}: {nuevos[ref]}"
            return datos

        filas = []
        for c in cambios.values():
            o = c["o"]
            tabla = o.__tablename__
            despues = natural(o, c.get("despues", _columnas(o))) if c["accion"] != "ELIMINADO" else None
            if c["accion"] == "CAMBIO":
                despues = {k: despues.get(k) for k in c["antes"]}
            aviso = None
            vid = getattr(o, "version_id", None)
            if c["accion"] in ("CAMBIO", "ELIMINADO") and vid in publicadas and tabla in OFICIALES:
                aviso = f"Changes a row of the published version {publicadas[vid]}: it should come as a new version or effective date."
            elif c["accion"] == "CAMBIO" and tabla == "versiones_dataset" and c["antes"].get("estado", getattr(o, "estado", "")) == "PUBLICADA" \
                    and set(c["antes"]) - {"vigente_hasta", "estado"}:
                aviso = f"Changes the published version {o.codigo}: only its end date can be set (or it can be archived)."
            filas.append({"tabla": tabla, "clave": _clave(o), "accion": c["accion"], "antes": c["antes"], "despues": despues,
                          "advertencia": aviso})
    finally:
        event.remove(previa, "before_flush", anotar)
        previa.rollback()
        previa.close()
    return res, filas


def firma(filas: list[dict]) -> str:
    """Huella canónica de la diferencia (tabla, clave, acción, antes y después)."""
    import json

    canon = sorted(json.dumps([f["tabla"], f["clave"], f["accion"], f["antes"], f["despues"]], sort_keys=True, default=str) for f in filas)
    return hashlib.sha256("\n".join(canon).encode()).hexdigest()


def _dict(x: LoteOficial, filas: bool = False) -> dict:
    d = {c: getattr(x, c) for c in ("id", "archivo", "checksum", "estado", "resumen", "errores", "creado_en", "publicado_en")}
    if filas:
        d["filas"] = [{"id": f.id, "tabla": f.tabla, "tabla_txt": NOMBRE.get(f.tabla, f.tabla), "clave": f.clave, "accion": f.accion,
                       "antes": f.antes, "despues": f.despues, "advertencia": f.advertencia} for f in x.filas]
    return d


def previa(db: Session, user: Usuario, contenido: bytes, nombre: str) -> dict:
    exigir(user, "aranceles.editar")
    res, filas = _diferencias(db, contenido, nombre)
    resumen: dict[str, dict] = {}
    for f in filas:
        r = resumen.setdefault(NOMBRE.get(f["tabla"], f["tabla"]), {"NUEVO": 0, "CAMBIO": 0, "ELIMINADO": 0, "advertencias": 0})
        r[f["accion"]] += 1
        r["advertencias"] += 1 if f["advertencia"] else 0
    lote = LoteOficial(archivo=nombre[:300] or "package.xlsx", checksum=hashlib.sha256(contenido).hexdigest(), contenido=contenido,
                       usuario_id=user.id, resumen={"tablas": resumen, "hojas": res["hojas"], "sin_cambio": sum(
                           h["actualizados"] for h in res["hojas"].values()) - sum(r["CAMBIO"] for r in resumen.values())},
                       errores=res["errores"][:500])
    lote.resumen["firma"] = firma(filas)
    lote.resumen["bloqueos"] = sum(1 for f in filas if f["advertencia"])
    lote.filas = [FilaLoteOficial(**f) for f in filas[:MAX_FILAS]]
    db.add(lote)
    db.flush()
    registrar(db, user, "aranceles", lote.id, "previa_oficial", {"archivo": lote.archivo, "cambios": len(filas), "errores": len(res["errores"])})
    return _dict(lote, True)


def lotes(db: Session, user: Usuario) -> list[dict]:
    exigir(user, "aranceles.ver")
    return [_dict(x) for x in db.scalars(select(LoteOficial).order_by(LoteOficial.id.desc()).limit(30))]


def lote(db: Session, user: Usuario, lote_id: int) -> dict:
    exigir(user, "aranceles.ver")
    x = db.get(LoteOficial, lote_id)
    if not x:
        raise ErrorNegocio("The load does not exist.", 404, "no_encontrado")
    return _dict(x, True)


def publicar(db: Session, user: Usuario, lote_id: int) -> dict:
    """Aplica la previa. Si lo vigente cambió desde la previa, se vuelve a
    calcular la diferencia para que nadie publique a ciegas."""
    from app.modulos.clasificacion import oficial

    exigir(user, "aranceles.editar")
    x = db.get(LoteOficial, lote_id)
    if not x:
        raise ErrorNegocio("The load does not exist.", 404, "no_encontrado")
    if x.estado != "PREVIA":
        raise ErrorNegocio("Only a load in preview can be published.", 422, "validacion")
    # Un lote con errores no se publica, ni en parte: se corrige el archivo y se vuelve a subir
    if x.errores:
        raise ErrorNegocio(f"The load has {len(x.errores)} rows with errors: nothing was published. Fix the file and upload it again.",
                           422, "lote_con_errores", x.errores[:100])
    _, filas = _diferencias(db, x.contenido, x.archivo)
    # Lo publicado es inmutable: un cambio a una versión publicada no se aplica
    bloqueos = [f for f in filas if f["advertencia"]]
    if bloqueos:
        raise ErrorNegocio(f"{len(bloqueos)} changes touch a published version, which is immutable. Load them as a new version "
                           "(or an effective date) and publish that.", 422, "version_publicada",
                           [{"fila": f"{f['tabla']} {f['clave']}", "mensaje": f["advertencia"]} for f in bloqueos[:50]])
    # La misma diferencia exacta que se revisó (no solo la misma cantidad)
    if firma(filas) != (x.resumen or {}).get("firma"):
        raise ErrorNegocio("The data changed since this preview. Upload the file again to review the current differences.", 409, "conflicto")
    res = oficial.importar(db, x.contenido, user, x.archivo)
    x.estado, x.publicado_en, x.publicado_por = "PUBLICADA", ahora(), user.id
    registrar(db, user, "aranceles", x.id, "publicar_oficial", {"archivo": x.archivo, "creados": res["creados"], "actualizados": res["actualizados"]})
    return {**_dict(x), "creados": res["creados"], "actualizados": res["actualizados"]}


def descartar(db: Session, user: Usuario, lote_id: int) -> dict:
    exigir(user, "aranceles.editar")
    x = db.get(LoteOficial, lote_id)
    if not x or x.estado != "PREVIA":
        raise ErrorNegocio("Only a load in preview can be discarded.", 422, "validacion")
    x.estado = "DESCARTADA"
    registrar(db, user, "aranceles", x.id, "descartar_oficial", {"archivo": x.archivo})
    return _dict(x)

