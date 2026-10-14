"""Plantillas de etiqueta y sus versiones (docs/ETIQUETADO.md §Versiones).

Reglas:
1. Una plantilla nace con la versión 1 en borrador.
2. Un borrador (o una versión rechazada) se edita y se guarda cuantas veces
   haga falta; se envía a aprobación cuando está lista.
3. Una versión aprobada no se modifica nunca: los cambios van en una versión
   nueva (borrador) basada en ella.
4. Solo una versión aprobada se usa en producción (la vigente de la
   plantilla); la versión nueva no la reemplaza hasta aprobarse.
5. Las versiones anteriores aprobadas se pueden volver a usar (vigente)
   sin borrar el historial; archivar no borra nada ni cambia lo generado.
6. Cada acción importante queda en la bitácora con su autor.

A lo sumo hay una versión abierta (borrador, pendiente o rechazada) por
plantilla: así nadie edita dos ramas del mismo diseño a la vez.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import archivos
from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.modelos import (
    Adjunto,
    AsignacionEtiqueta,
    FamiliaEtiquetado,
    PlantillaEtiqueta,
    Usuario,
    VersionPlantilla,
    ahora,
)
from app.modelos.etiquetado import MODALIDADES, UNIDADES
from app.modulos.acceso.permisos import exigir, exigir_alguno, tiene
from app.modulos.comun.historial import registrar, requerir_motivo
from app.modulos.comun.texto import filtro_texto
from app.modulos.etiquetado import campos as svc_campos
from app.modulos.etiquetado import diseno as svc_diseno
from app.modulos.etiquetado import render

ABIERTAS = ("BORRADOR", "PENDIENTE", "RECHAZADA")
EDITABLES = ("BORRADOR", "RECHAZADA")
# Qué representa cada etiqueta según la modalidad de datos
UNIDADES_VALIDAS = {"ARTICULO": {"UNIDAD", "MANUAL"}, "OC": {"ORDEN", "BULTO", "MANUAL"},
                    "OC_ARTICULO": {"LINEA", "ARTICULO", "UNIDAD", "BULTO", "MANUAL"}}


def _nombre_usuario(db: Session, uid: int | None) -> str | None:
    if not uid:
        return None
    u = db.get(Usuario, uid)
    return (u.nombre or u.email) if u else None


def dict_version(db: Session, v: VersionPlantilla, con_diseno: bool = False) -> dict:
    r = {"id": v.id, "plantilla_id": v.plantilla_id, "numero": v.numero, "estado": v.estado, "ancho_mm": v.ancho_mm,
         "alto_mm": v.alto_mm, "cambios": v.cambios, "basada_en_id": v.basada_en_id, "comentario": v.comentario,
         "creada_por": _nombre_usuario(db, v.creada_por), "creada_en": v.creada_en, "actualizada_en": v.actualizada_en,
         "enviada_por": _nombre_usuario(db, v.enviada_por), "enviada_en": v.enviada_en,
         "revisada_por": _nombre_usuario(db, v.revisada_por), "revisada_en": v.revisada_en,
         "aprobada_por": _nombre_usuario(db, v.aprobada_por), "aprobada_en": v.aprobada_en,
         "vigente": v.plantilla.version_vigente_id == v.id, "version": v.version}
    if con_diseno:
        r["diseno"] = v.diseno
    return r


def dict_plantilla(db: Session, p: PlantillaEtiqueta, completo: bool = False) -> dict:
    ultima = p.versiones[-1] if p.versiones else None
    r = {"id": p.id, "nombre": p.nombre, "descripcion": p.descripcion, "modalidad": p.modalidad, "unidad": p.unidad,
         "familia_id": p.familia_id, "familia": p.familia.nombre if p.familia else None, "estado": p.estado,
         "origen_id": p.origen_id, "creada_en": p.creada_en, "actualizada_en": p.actualizada_en,
         "vigente": {"id": p.vigente.id, "numero": p.vigente.numero, "ancho_mm": p.vigente.ancho_mm, "alto_mm": p.vigente.alto_mm}
         if p.vigente else None,
         "ultima": {"id": ultima.id, "numero": ultima.numero, "estado": ultima.estado, "ancho_mm": ultima.ancho_mm,
                    "alto_mm": ultima.alto_mm} if ultima else None,
         "asignaciones": len([a for a in _asignaciones(db, p.id) if a.activa])}
    if completo:
        r["versiones"] = [dict_version(db, v) for v in reversed(p.versiones)]
        from app.modulos.etiquetado.asignaciones import dict_asignacion

        r["lista_asignaciones"] = [dict_asignacion(db, a) for a in _asignaciones(db, p.id)]
    return r


def _asignaciones(db: Session, plantilla_id: int) -> list[AsignacionEtiqueta]:
    return list(db.scalars(select(AsignacionEtiqueta).where(AsignacionEtiqueta.plantilla_id == plantilla_id)
                           .order_by(AsignacionEtiqueta.id)))


def cargar(db: Session, plantilla_id: int) -> PlantillaEtiqueta:
    p = db.get(PlantillaEtiqueta, plantilla_id)
    if not p:
        raise ErrorNegocio("The label design does not exist.", 404, "no_encontrado")
    return p


def cargar_version(db: Session, version_id: int, bloquear: bool = False) -> VersionPlantilla:
    c = select(VersionPlantilla).where(VersionPlantilla.id == version_id)
    v = db.scalar(c.with_for_update() if bloquear else c)
    if not v:
        raise ErrorNegocio("The design version does not exist.", 404, "no_encontrado")
    return v


def listar(db: Session, user: Usuario, q=None, modalidad=None, familia_id=None, estado="ACTIVA", estado_version=None,
           page: int = 1, size: int = 50) -> dict:
    exigir(user, "etiquetas.ver")
    c = select(PlantillaEtiqueta)
    if estado:
        c = c.where(PlantillaEtiqueta.estado == estado.upper())
    if modalidad:
        c = c.where(PlantillaEtiqueta.modalidad == modalidad.upper())
    if familia_id:
        c = c.where(PlantillaEtiqueta.familia_id == familia_id)
    if estado_version:
        c = c.where(PlantillaEtiqueta.id.in_(select(VersionPlantilla.plantilla_id)
                                             .where(VersionPlantilla.estado == estado_version.upper())))
    if q and q.strip():
        c = c.where(filtro_texto(q, lambda p: [PlantillaEtiqueta.nombre.ilike(p), PlantillaEtiqueta.descripcion.ilike(p)]))
    total = db.scalar(select(func.count()).select_from(c.subquery())) or 0
    filas = db.scalars(c.order_by(PlantillaEtiqueta.nombre).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "items": [dict_plantilla(db, p) for p in filas]}


def detalle(db: Session, user: Usuario, plantilla_id: int) -> dict:
    exigir(user, "etiquetas.ver")
    return dict_plantilla(db, cargar(db, plantilla_id), completo=True)


def detalle_version(db: Session, user: Usuario, version_id: int) -> dict:
    exigir(user, "etiquetas.ver")
    v = cargar_version(db, version_id)
    return {**dict_version(db, v, con_diseno=True), "plantilla": dict_plantilla(db, v.plantilla)}


def bitacora(db: Session, user: Usuario, plantilla_id: int) -> list[dict]:
    """Quién hizo qué con el diseño y sus versiones (crear, guardar versión, enviar, aprobar, rechazar...)."""
    from app.modelos import Historial

    exigir(user, "etiquetas.ver")
    p = cargar(db, plantilla_id)
    filas = db.scalars(select(Historial).where(Historial.entidad == "plantilla_etiqueta", Historial.entidad_id == p.id)
                       .order_by(Historial.fecha.desc(), Historial.id.desc()).limit(200)).all()
    return [{"id": h.id, "fecha": h.fecha, "accion": h.accion, "detalle": h.detalle, "motivo": h.motivo,
             "usuario": _nombre_usuario(db, h.usuario_id)} for h in filas]


# ---- Validación del contenido -------------------------------------------------------------------
def _validar_meta(db: Session, datos: dict, actual: PlantillaEtiqueta | None) -> dict:
    errores, limpio = [], {}
    if "nombre" in datos or actual is None:
        nombre = (datos.get("nombre") or "").strip()
        if not nombre or len(nombre) > 120:
            errores.append({"campo": "nombre", "mensaje": "Enter the name (up to 120 characters)."})
        elif db.scalar(select(PlantillaEtiqueta.id).where(func.lower(PlantillaEtiqueta.nombre) == nombre.lower(),
                                                          PlantillaEtiqueta.id != (actual.id if actual else 0))):
            errores.append({"campo": "nombre", "mensaje": "Another label design has this name."})
        limpio["nombre"] = nombre
    if "descripcion" in datos:
        limpio["descripcion"] = (datos.get("descripcion") or "").strip()[:500] or None
    if "modalidad" in datos or actual is None:
        modalidad = (datos.get("modalidad") or "").upper()
        if modalidad not in MODALIDADES:
            errores.append({"campo": "modalidad", "mensaje": "Choose where the data comes from: item, PO or PO and item."})
        elif actual and modalidad != actual.modalidad and actual.version_vigente_id:
            errores.append({"campo": "modalidad", "mensaje": "An approved design keeps its data mode: duplicate it to change it."})
        limpio["modalidad"] = modalidad
    modalidad = limpio.get("modalidad") or (actual.modalidad if actual else None)
    if "unidad" in datos or actual is None:
        unidad = (datos.get("unidad") or ("UNIDAD" if modalidad == "ARTICULO" else "ORDEN" if modalidad == "OC" else "LINEA")).upper()
        if unidad not in UNIDADES or (modalidad in UNIDADES_VALIDAS and unidad not in UNIDADES_VALIDAS[modalidad]):
            errores.append({"campo": "unidad", "mensaje": "That label unit does not apply to this data mode."})
        limpio["unidad"] = unidad
    if "familia_id" in datos:
        fid = datos.get("familia_id")
        if fid and not db.get(FamiliaEtiquetado, fid):
            errores.append({"campo": "familia_id", "mensaje": "The labeling family does not exist."})
        limpio["familia_id"] = fid or None
    if errores:
        raise ErrorNegocio("Check the label design.", 422, "validacion", errores)
    return limpio


def validar_contenido(db: Session, user: Usuario, modalidad: str, diseno: dict) -> dict:
    """Diseño limpio cuyos campos existen en la modalidad y cuyas imágenes son de la organización."""
    limpio = svc_diseno.validar(diseno)
    disponibles = {c.clave for c in svc_campos.catalogo(db, modalidad)} | {f"manual.{v['clave']}" for v in limpio["variables"]}
    ajenos = sorted(c for c in svc_diseno.campos_usados(limpio) if c not in disponibles)
    if ajenos:
        raise ErrorNegocio("The design uses fields that this data mode does not have.", 422, "validacion",
                           [{"campo": "elementos", "mensaje": f"Not available for this data mode: {', '.join(ajenos)}."}])
    for e in limpio["elementos"]:
        if e["tipo"] == "imagen" and e.get("fuente_imagen") == "adjunto" and not db.get(Adjunto, e["adjunto_id"]):
            raise ErrorNegocio("An image of the design does not exist.", 422, "validacion")
        if e["tipo"] == "imagen" and e.get("fuente_imagen") == "datos":
            archivos.imagen_data_url(e["datos"], 500 * 1024)
    return limpio


def imagen_adjunta(db: Session):
    """Lector de las imágenes subidas para el motor (solo las de la organización de la sesión)."""
    from app.core import almacen

    def leer(adjunto_id: int) -> bytes | None:
        a = db.get(Adjunto, adjunto_id)
        if not a or not a.tipo_mime.startswith("image/"):
            return None
        try:
            return almacen.leer(a.clave)
        except OSError:
            return None
    return leer


def revisar(db: Session, modalidad: str, diseno: dict, valores: dict | None = None, prueba: bool = False) -> render.Lienzo:
    """La etiqueta con datos reales o, sin ellos, con los valores de ejemplo de cada campo."""
    tipos = {c.clave: c.tipo for c in svc_campos.catalogo(db, modalidad)}
    if valores is None:
        valores = {**svc_campos.ejemplos(db, modalidad), "etiqueta.numero": 1, "etiqueta.total": 1, "etiqueta.numero_lote": 1,
                   "etiqueta.total_lote": 1}
        valores.update(svc_campos.valores_organizacion(db))
        valores.update(svc_diseno.valores_manuales(diseno, ejemplo=True))
    return render.componer(diseno, valores, tipos, imagen_adjunta(db), prueba)


# ---- Plantillas ---------------------------------------------------------------------------
def crear(db: Session, user: Usuario, datos: dict) -> dict:
    exigir(user, "etiquetas.disenar")
    limpio = _validar_meta(db, datos, None)
    contenido = validar_contenido(db, user, limpio["modalidad"], datos.get("diseno") or svc_diseno.inicial())
    p = PlantillaEtiqueta(creada_por=user.id, estado="ACTIVA", **limpio)
    db.add(p)
    db.flush()
    v = VersionPlantilla(plantilla_id=p.id, numero=1, estado="BORRADOR", diseno=contenido, ancho_mm=contenido["ancho"],
                         alto_mm=contenido["alto"], creada_por=user.id)
    db.add(v)
    db.flush()
    db.refresh(p)
    registrar(db, user, "plantilla_etiqueta", p.id, "crear", {"nombre": p.nombre, "modalidad": p.modalidad})
    return dict_plantilla(db, p, completo=True)


def actualizar(db: Session, user: Usuario, plantilla_id: int, datos: dict) -> dict:
    exigir(user, "etiquetas.disenar")
    p = cargar(db, plantilla_id)
    limpio = _validar_meta(db, datos, p)
    antes = {k: getattr(p, k) for k in limpio}
    for k, v in limpio.items():
        setattr(p, k, v)
    p.actualizada_en = ahora()
    db.flush()
    cambios = {k: [antes[k], v] for k, v in limpio.items() if antes[k] != v}
    if cambios:
        registrar(db, user, "plantilla_etiqueta", p.id, "editar", cambios)
    return dict_plantilla(db, p, completo=True)


def duplicar(db: Session, user: Usuario, plantilla_id: int, datos: dict) -> dict:
    """Plantilla nueva e independiente con el diseño de una versión (la vigente,
    o la elegida); el original no cambia."""
    exigir(user, "etiquetas.disenar")
    origen = cargar(db, plantilla_id)
    v = cargar_version(db, datos["version_id"]) if datos.get("version_id") else (origen.vigente or origen.versiones[-1])
    if v.plantilla_id != origen.id:
        raise ErrorNegocio("The version is not of this design.", 422, "validacion")
    nombre = (datos.get("nombre") or "").strip() or f"{origen.nombre} (copy)"
    nueva = crear(db, user, {"nombre": nombre, "descripcion": datos.get("descripcion", origen.descripcion),
                             "modalidad": origen.modalidad, "unidad": origen.unidad,
                             "familia_id": datos.get("familia_id", origen.familia_id), "diseno": v.diseno})
    copia = cargar(db, nueva["id"])
    copia.origen_id = origen.id
    db.flush()
    registrar(db, user, "plantilla_etiqueta", copia.id, "duplicar", {"de": origen.nombre, "version": v.numero})
    return dict_plantilla(db, copia, completo=True)


def archivar(db: Session, user: Usuario, plantilla_id: int, archivar_: bool = True, motivo: str | None = None) -> dict:
    """Retira (o reactiva) una plantilla: deja de elegirse para nuevas etiquetas;
    lo ya generado y su historial no cambian."""
    exigir_alguno(user, "etiquetas.aprobar", "etiquetas.disenar")
    p = cargar(db, plantilla_id)
    p.estado = "ARCHIVADA" if archivar_ else "ACTIVA"
    p.actualizada_en = ahora()
    db.flush()
    registrar(db, user, "plantilla_etiqueta", p.id, "archivar" if archivar_ else "reactivar", None, motivo)
    return dict_plantilla(db, p, completo=True)


# ---- Versiones ----------------------------------------------------------------------------
def nueva_version(db: Session, user: Usuario, plantilla_id: int, desde_id: int | None = None) -> dict:
    """Versión borrador basada en la vigente (o en la elegida). Si ya hay una
    versión abierta, se devuelve esa: una sola rama de cambios a la vez."""
    exigir(user, "etiquetas.disenar")
    p = cargar(db, plantilla_id)
    abierta = next((v for v in p.versiones if v.estado in ABIERTAS), None)
    if abierta and not desde_id:
        return dict_version(db, abierta, con_diseno=True)
    if abierta:
        raise ErrorNegocio(f"Version {abierta.numero} is still open: finish or archive it first.", 409, "version_abierta")
    base = cargar_version(db, desde_id) if desde_id else (p.vigente or p.versiones[-1])
    if base.plantilla_id != p.id:
        raise ErrorNegocio("The version is not of this design.", 422, "validacion")
    numero = (db.scalar(select(func.max(VersionPlantilla.numero)).where(VersionPlantilla.plantilla_id == p.id)) or 0) + 1
    v = VersionPlantilla(plantilla_id=p.id, numero=numero, estado="BORRADOR", diseno=base.diseno, ancho_mm=base.ancho_mm,
                         alto_mm=base.alto_mm, basada_en_id=base.id, creada_por=user.id, cambios="no changes")
    db.add(v)
    db.flush()
    registrar(db, user, "plantilla_etiqueta", p.id, "nueva_version", {"version": numero, "basada_en": base.numero})
    return dict_version(db, v, con_diseno=True)


def guardar_diseno(db: Session, user: Usuario, version_id: int, diseno: dict, version: int | None) -> dict:
    """Guarda el diseño de un borrador (o de una versión rechazada, que vuelve a borrador)."""
    from app.modulos.comun.historial import verificar_version

    exigir(user, "etiquetas.disenar")
    v = cargar_version(db, version_id, bloquear=True)
    verificar_version(v, version, "design version")
    if v.estado not in EDITABLES:
        raise ErrorNegocio("Only a draft can be edited: an approved version never changes, create a new version.",
                           409, "no_editable")
    contenido = validar_contenido(db, user, v.plantilla.modalidad, diseno)
    base = db.get(VersionPlantilla, v.basada_en_id) if v.basada_en_id else None
    v.diseno, v.ancho_mm, v.alto_mm = contenido, contenido["ancho"], contenido["alto"]
    v.cambios = svc_diseno.resumen_cambios(base.diseno if base else None, contenido)
    v.estado, v.actualizada_en = "BORRADOR", ahora()
    v.version += 1
    v.plantilla.actualizada_en = ahora()
    db.flush()
    registrar(db, user, "plantilla_etiqueta", v.plantilla_id, "guardar_diseno", {"version": v.numero, "cambios": v.cambios})
    return dict_version(db, v, con_diseno=True)


def _bloqueantes(db: Session, v: VersionPlantilla) -> list[dict]:
    lz = revisar(db, v.plantilla.modalidad, v.diseno)
    return [p for p in lz.problemas if p["nivel"] == "error"]


def enviar(db: Session, user: Usuario, version_id: int) -> dict:
    exigir(user, "etiquetas.disenar")
    v = cargar_version(db, version_id, bloquear=True)
    if v.estado != "BORRADOR":
        raise ErrorNegocio("Only a draft is sent to approval.", 409, "transicion_invalida")
    errores = _bloqueantes(db, v)
    if errores:
        raise ErrorNegocio("The design has errors: fix them before sending it to approval.", 422, "diseno_con_errores",
                           [{"campo": p.get("elemento") or "diseno", "mensaje": p["mensaje"]} for p in errores])
    v.estado, v.enviada_por, v.enviada_en, v.comentario = "PENDIENTE", user.id, ahora(), None
    db.flush()
    registrar(db, user, "plantilla_etiqueta", v.plantilla_id, "enviar_aprobacion", {"version": v.numero})
    return dict_version(db, v)


def retirar(db: Session, user: Usuario, version_id: int) -> dict:
    """Quien diseña retira su versión de la aprobación y vuelve a editarla."""
    exigir(user, "etiquetas.disenar")
    v = cargar_version(db, version_id, bloquear=True)
    if v.estado != "PENDIENTE":
        raise ErrorNegocio("Only a version pending approval can be withdrawn.", 409, "transicion_invalida")
    v.estado = "BORRADOR"
    db.flush()
    registrar(db, user, "plantilla_etiqueta", v.plantilla_id, "retirar_aprobacion", {"version": v.numero})
    return dict_version(db, v)


def aprobar(db: Session, user: Usuario, version_id: int, comentario: str | None) -> dict:
    exigir(user, "etiquetas.aprobar")
    v = cargar_version(db, version_id, bloquear=True)
    if v.estado != "PENDIENTE":
        raise ErrorNegocio("Only a version pending approval can be approved.", 409, "transicion_invalida")
    if regla("ETIQUETAS_CUATRO_OJOS") and user.id in (v.creada_por, v.enviada_por):
        raise ErrorNegocio("Another person must approve this version (four-eyes rule).", 409, "cuatro_ojos")
    errores = _bloqueantes(db, v)
    if errores:
        raise ErrorNegocio("The design has errors: it cannot be approved.", 422, "diseno_con_errores",
                           [{"campo": p.get("elemento") or "diseno", "mensaje": p["mensaje"]} for p in errores])
    anterior = v.plantilla.vigente
    v.estado, v.revisada_por, v.revisada_en, v.comentario = "APROBADA", user.id, ahora(), (comentario or "").strip()[:1000] or None
    v.aprobada_por, v.aprobada_en = user.id, v.revisada_en
    v.plantilla.version_vigente_id = v.id
    v.plantilla.actualizada_en = ahora()
    db.flush()
    registrar(db, user, "plantilla_etiqueta", v.plantilla_id, "aprobar",
              {"version": v.numero, "reemplaza": anterior.numero if anterior else None}, comentario)
    return dict_version(db, v)


def rechazar(db: Session, user: Usuario, version_id: int, comentario: str | None) -> dict:
    exigir(user, "etiquetas.aprobar")
    comentario = requerir_motivo(comentario, "reject the version")
    v = cargar_version(db, version_id, bloquear=True)
    if v.estado != "PENDIENTE":
        raise ErrorNegocio("Only a version pending approval can be rejected.", 409, "transicion_invalida")
    v.estado, v.revisada_por, v.revisada_en, v.comentario = "RECHAZADA", user.id, ahora(), comentario[:1000]
    db.flush()
    registrar(db, user, "plantilla_etiqueta", v.plantilla_id, "rechazar", {"version": v.numero}, comentario)
    return dict_version(db, v)


def archivar_version(db: Session, user: Usuario, version_id: int, motivo: str | None) -> dict:
    """Archiva una versión que no está en uso (borrador, rechazada o aprobada
    no vigente). La vigente se reemplaza primero por otra aprobada."""
    exigir_alguno(user, "etiquetas.aprobar", "etiquetas.disenar")
    v = cargar_version(db, version_id, bloquear=True)
    if v.plantilla.version_vigente_id == v.id:
        raise ErrorNegocio("It is the version in use: choose another approved version first, or archive the design.",
                           409, "version_vigente")
    if v.estado == "ARCHIVADA":
        return dict_version(db, v)
    if v.estado == "APROBADA" and not tiene(user, "etiquetas.aprobar"):
        raise ErrorNegocio("You do not have permission for this action.", 403, "sin_permiso")
    v.estado = "ARCHIVADA"
    db.flush()
    registrar(db, user, "plantilla_etiqueta", v.plantilla_id, "archivar_version", {"version": v.numero}, motivo)
    return dict_version(db, v)


def usar_version(db: Session, user: Usuario, version_id: int, motivo: str | None) -> dict:
    """Vuelve a poner en uso una versión aprobada anterior (sin borrar las
    demás): las etiquetas nuevas usarán esa versión."""
    exigir(user, "etiquetas.aprobar")
    v = cargar_version(db, version_id, bloquear=True)
    if v.estado not in ("APROBADA", "ARCHIVADA") or v.aprobada_en is None:
        raise ErrorNegocio("Only a version that was approved can be put back in use.", 409, "transicion_invalida")
    anterior = v.plantilla.vigente
    v.estado = "APROBADA"
    v.plantilla.version_vigente_id = v.id
    db.flush()
    registrar(db, user, "plantilla_etiqueta", v.plantilla_id, "usar_version",
              {"version": v.numero, "reemplaza": anterior.numero if anterior else None}, motivo)
    return dict_version(db, v)


# ---- Imágenes del diseño --------------------------------------------------------------------
MAX_IMAGEN = 2 * 1024 * 1024


def subir_imagen(db: Session, user: Usuario, nombre: str, contenido: bytes) -> dict:
    """Logotipo o ícono para un diseño: PNG, JPEG o WebP de hasta 2 MB y 4000 px."""
    from PIL import Image

    from app.modulos.comun import adjuntos

    exigir(user, "etiquetas.disenar")
    tipo = archivos.tipo_imagen(contenido)
    if not tipo:
        raise ErrorNegocio("Upload a PNG, JPEG or WebP image.", 422, "validacion")
    if len(contenido) > MAX_IMAGEN:
        raise ErrorNegocio("The image is larger than 2 MB.", 413, "archivo_grande")
    import io

    with Image.open(io.BytesIO(contenido)) as im:
        ancho, alto = im.size
    if max(ancho, alto) > 4000:
        raise ErrorNegocio("The image is larger than 4000 px.", 422, "validacion")
    a = adjuntos.crear(db, user, adjuntos.nombre_seguro(nombre, f"imagen.{tipo}"), contenido, "etiquetas", tipo,
                       archivos.MIME[tipo])
    registrar(db, user, "plantilla_etiqueta", 0, "subir_imagen", {"adjunto": a.id, "nombre": a.nombre})
    return {"id": a.id, "nombre": a.nombre, "ancho_px": ancho, "alto_px": alto, "tipo_mime": a.tipo_mime}


def leer_imagen(db: Session, user: Usuario, adjunto_id: int) -> tuple[bytes, str]:
    exigir(user, "etiquetas.ver")
    a = db.get(Adjunto, adjunto_id)
    datos = imagen_adjunta(db)(adjunto_id)
    if not a or datos is None:
        raise ErrorNegocio("The image does not exist.", 404, "no_encontrado")
    return datos, a.tipo_mime
