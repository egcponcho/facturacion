"""Etiquetado: familias, campos disponibles, plantillas y sus versiones,
asignaciones, generación y descargas (docs/ETIQUETADO.md)."""
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Query, Response, UploadFile

from app.core.errores import ErrorNegocio
from app.modulos.acceso.permisos import exigir_alguno
from app.modulos.etiquetado import asignaciones, campos, familias, generacion, masivo, plantillas, previa
from app.web.rutas import Clave, Db, User, ejecutar, leer_subida

router = APIRouter()


# ---- Campos dinámicos -------------------------------------------------------------------
@router.get("/etiquetas/campos")
def listar_campos(db: Db, user: User, modalidad: str | None = Query(None, pattern="^(ARTICULO|OC|OC_ARTICULO)$")):
    """Campos que se pueden poner en una etiqueta, por grupo, con su origen (tabla.columna) y un ejemplo."""
    exigir_alguno(user, "etiquetas.ver", "etiquetas.disenar")
    return {"grupos": campos.GRUPOS, "modalidades": {k: sorted(v) for k, v in campos.POR_MODALIDAD.items()},
            "campos": [campos.dict_campo(c) for c in campos.catalogo(db, modalidad)]}


# ---- Familias de etiquetado --------------------------------------------------------------
@router.get("/etiquetas/familias")
def listar_familias(db: Db, user: User, activas: bool | None = None):
    """Familias de etiquetado de la empresa con cuántos artículos y diseños tienen."""
    return familias.listar(db, user, activas)


@router.post("/etiquetas/familias")
def crear_familia(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Nueva familia: código, nombre, descripción, orden y campos habituales u obligatorios."""
    return ejecutar(db, user, clave, lambda: familias.crear(db, user, datos))


@router.put("/etiquetas/familias/orden")
def ordenar_familias(db: Db, user: User, ids: list[int] = Body(..., embed=True)):
    """Orden de las familias (todas, en el orden deseado)."""
    return ejecutar(db, user, None, lambda: familias.ordenar(db, user, ids))


@router.patch("/etiquetas/familias/{familia_id}")
def actualizar_familia(familia_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Cambia nombre, descripción, orden, campos o la desactiva (activa: false)."""
    return ejecutar(db, user, clave, lambda: familias.actualizar(db, user, familia_id, datos))


@router.delete("/etiquetas/familias/{familia_id}")
def eliminar_familia(familia_id: int, db: Db, user: User):
    """Borra una familia sin uso (si se usa, se desactiva)."""
    return ejecutar(db, user, None, lambda: familias.eliminar(db, user, familia_id))


@router.get("/etiquetas/articulos")
def articulos_familia(db: Db, user: User, q: str | None = None, familia: str | None = None, marca_id: int | None = None,
                      grupo_id: int | None = None, producto_id: int | None = None, ids: str | None = Query(None, pattern=r"^\d+(,\d+)*$"),
                      page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200), solo_ids: bool = False):
    """Artículos con su familia de etiquetado (familia=sin: los que no tienen; ids=1,2,3: solo esos;
    solo_ids: los números de todos los que cumplen el filtro, para elegirlos de una vez)."""
    return familias.articulos(db, user, q, familia, marca_id, grupo_id, producto_id, page, size,
                              [int(x) for x in ids.split(",")][:200] if ids else None, solo_ids)


@router.get("/etiquetas/grupos-articulos")
def grupos_familia(db: Db, user: User, q: str | None = None, familia: str | None = None):
    """Grupos de artículos con su familia de etiquetado (familia=sin: los que no tienen) y cuántos artículos tienen."""
    return familias.grupos(db, user, q, familia)


@router.post("/etiquetas/grupos-articulos/familia")
def asignar_familia_grupos(db: Db, user: User, familia_id: int | None = Body(None), grupo_ids: list[int] = Body(...)):
    """Pone la familia a varios grupos a la vez (o se la quita con familia vacía). Sus artículos la heredan,
    salvo los que tienen familia propia."""
    return ejecutar(db, user, None, lambda: familias.asignar_grupos(db, user, familia_id, grupo_ids))


@router.post("/etiquetas/articulos/familia")
def asignar_familia(db: Db, user: User, familia_id: int | None = Body(None), ids: list[int] | None = Body(None),
                    filtro: dict[str, Any] | None = Body(None), clave: Clave = None):
    """Pone la familia (o la quita, con familia_id vacío) a los artículos elegidos o a todos los del filtro."""
    return ejecutar(db, user, clave, lambda: familias.asignar_articulos(db, user, familia_id, ids, filtro))


# ---- Plantillas y versiones ---------------------------------------------------------------
@router.get("/etiquetas/plantillas")
def listar_plantillas(db: Db, user: User, q: str | None = None, modalidad: str | None = None, familia_id: int | None = None,
                      estado: str | None = "ACTIVA", estado_version: str | None = None, page: int = Query(1, ge=1),
                      size: int = Query(50, ge=1, le=200)):
    """Diseños con su modalidad, familia, tamaño, versión vigente, última versión y asignaciones."""
    return plantillas.listar(db, user, q, modalidad, familia_id, estado, estado_version, page, size)


@router.post("/etiquetas/plantillas")
def crear_plantilla(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Diseño nuevo (nombre, descripción, modalidad, unidad, familia) con su versión 1 en borrador."""
    return ejecutar(db, user, clave, lambda: plantillas.crear(db, user, datos))


@router.get("/etiquetas/plantillas/{plantilla_id}")
def ver_plantilla(plantilla_id: int, db: Db, user: User):
    """Diseño con todas sus versiones y asignaciones."""
    return plantillas.detalle(db, user, plantilla_id)


@router.get("/etiquetas/plantillas/{plantilla_id}/bitacora")
def bitacora_plantilla(plantilla_id: int, db: Db, user: User):
    """Bitácora del diseño: cada acción sobre él y sus versiones, con autor, fecha y motivo."""
    return plantillas.bitacora(db, user, plantilla_id)


@router.patch("/etiquetas/plantillas/{plantilla_id}")
def actualizar_plantilla(plantilla_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Nombre, descripción, unidad, familia (y la modalidad, mientras no tenga una versión aprobada)."""
    return ejecutar(db, user, clave, lambda: plantillas.actualizar(db, user, plantilla_id, datos))


@router.post("/etiquetas/plantillas/{plantilla_id}/duplicar")
def duplicar_plantilla(plantilla_id: int, db: Db, user: User, datos: dict[str, Any] = Body({}), clave: Clave = None):
    """Diseño nuevo e independiente desde una versión (la vigente si no se indica)."""
    return ejecutar(db, user, clave, lambda: plantillas.duplicar(db, user, plantilla_id, datos))


@router.post("/etiquetas/plantillas/{plantilla_id}/archivar")
def archivar_plantilla(plantilla_id: int, db: Db, user: User, datos: dict[str, Any] = Body({})):
    """Retira el diseño (no se elige para etiquetas nuevas; lo generado no cambia)."""
    return ejecutar(db, user, None, lambda: plantillas.archivar(db, user, plantilla_id, True, datos.get("motivo")))


@router.post("/etiquetas/plantillas/{plantilla_id}/reactivar")
def reactivar_plantilla(plantilla_id: int, db: Db, user: User):
    """Vuelve a poner en uso un diseño archivado."""
    return ejecutar(db, user, None, lambda: plantillas.archivar(db, user, plantilla_id, False))


@router.post("/etiquetas/plantillas/{plantilla_id}/versiones")
def nueva_version(plantilla_id: int, db: Db, user: User, desde_id: int | None = Body(None, embed=True)):
    """Versión borrador basada en la vigente (o en la indicada); si ya hay una abierta, la devuelve."""
    return ejecutar(db, user, None, lambda: plantillas.nueva_version(db, user, plantilla_id, desde_id))


@router.get("/etiquetas/versiones/{version_id}")
def ver_version(version_id: int, db: Db, user: User):
    """Una versión con su diseño completo."""
    return plantillas.detalle_version(db, user, version_id)


@router.put("/etiquetas/versiones/{version_id}/diseno")
def guardar_diseno(version_id: int, db: Db, user: User, diseno: dict[str, Any] = Body(...), version: int | None = Body(None)):
    """Guarda el diseño de un borrador (una versión aprobada no se modifica)."""
    return ejecutar(db, user, None, lambda: plantillas.guardar_diseno(db, user, version_id, diseno, version))


ACCIONES_VERSION = {"enviar", "retirar", "aprobar", "rechazar", "archivar", "usar"}


@router.post("/etiquetas/versiones/{version_id}/{accion}")
def accion_version(version_id: int, accion: str, db: Db, user: User, datos: dict[str, Any] = Body({})):
    """enviar a aprobación · retirar de la aprobación · aprobar · rechazar (con comentario) · archivar · usar (volver a una aprobada anterior)."""
    if accion not in ACCIONES_VERSION:
        raise ErrorNegocio("Unknown action.", 404, "no_encontrado")
    comentario = datos.get("comentario")
    fn = {"enviar": lambda: plantillas.enviar(db, user, version_id), "retirar": lambda: plantillas.retirar(db, user, version_id),
          "aprobar": lambda: plantillas.aprobar(db, user, version_id, comentario),
          "rechazar": lambda: plantillas.rechazar(db, user, version_id, comentario),
          "archivar": lambda: plantillas.archivar_version(db, user, version_id, comentario),
          "usar": lambda: plantillas.usar_version(db, user, version_id, comentario)}[accion]
    return ejecutar(db, user, None, fn)


@router.post("/etiquetas/vista-previa")
def vista_previa(db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """La etiqueta dibujada por el servidor (SVG exacto) con datos de ejemplo o reales, y sus problemas.
    Recibe version_id o un diseño sin guardar (con su modalidad) y, opcionalmente, articulo_id, oc_id,
    posicion_id y bulto (número de caja)."""
    return previa.vista_previa(db, user, datos)


@router.get("/etiquetas/versiones/{version_id}/miniatura.svg")
def miniatura(version_id: int, db: Db, user: User):
    """La versión con datos de ejemplo, para las listas."""
    return Response(previa.miniatura(db, user, version_id), media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=60"})


# ---- Asignaciones ------------------------------------------------------------------------
@router.get("/etiquetas/asignaciones")
def listar_asignaciones(db: Db, user: User, plantilla_id: int | None = None, ambito: str | None = None,
                        familia_id: int | None = None, producto_id: int | None = None, articulo_id: int | None = None,
                        oc_id: int | None = None, activas: bool | None = True):
    """Dónde se aplica cada diseño (general, familia, producto, artículo o excepción de una OC)."""
    return asignaciones.listar(db, user, plantilla_id, ambito, familia_id, producto_id, articulo_id, oc_id, activas)


@router.post("/etiquetas/asignaciones")
def crear_asignacion(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Asigna un diseño: plantilla_id, ambito y su destino (familia_id, producto_id, articulo_id u oc_id con motivo)."""
    return ejecutar(db, user, clave, lambda: asignaciones.crear(db, user, datos))


@router.patch("/etiquetas/asignaciones/{asignacion_id}")
def actualizar_asignacion(asignacion_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Predeterminada, activa o motivo de una asignación."""
    return ejecutar(db, user, None, lambda: asignaciones.actualizar(db, user, asignacion_id, datos))


@router.delete("/etiquetas/asignaciones/{asignacion_id}")
def eliminar_asignacion(asignacion_id: int, db: Db, user: User):
    """Quita una asignación (el diseño y lo generado no cambian)."""
    return ejecutar(db, user, None, lambda: asignaciones.eliminar(db, user, asignacion_id))


@router.get("/etiquetas/resolver")
def resolver(db: Db, user: User, modalidad: str = Query(..., pattern="^(ARTICULO|OC|OC_ARTICULO)$"),
             articulo_id: int | None = None, oc_id: int | None = None):
    """Qué diseño (y versión) se usaría para este artículo u OC, en qué nivel y por qué."""
    return previa.resolver(db, user, modalidad, articulo_id, oc_id)


# ---- Imágenes y fuentes ---------------------------------------------------------------------
@router.post("/etiquetas/imagenes")
async def subir_imagen(db: Db, user: User, archivo: UploadFile):
    """Logotipo o ícono para los diseños (PNG, JPEG o WebP, hasta 2 MB y 4000 px)."""
    contenido = await leer_subida(archivo)
    return ejecutar(db, user, None, lambda: plantillas.subir_imagen(db, user, archivo.filename, contenido))


@router.get("/etiquetas/imagenes/{adjunto_id}")
def ver_imagen(adjunto_id: int, db: Db, user: User):
    """Una imagen subida para los diseños."""
    datos, tipo = plantillas.leer_imagen(db, user, adjunto_id)
    return Response(datos, media_type=tipo, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/etiquetas/fuentes/{archivo}")
def fuente(archivo: str, user: User):
    """Las fuentes de las etiquetas, para que el editor mida y dibuje igual que el servidor."""
    from app.modulos.etiquetado.fuentes import FUENTES

    exigir_alguno(user, "etiquetas.ver", "etiquetas.disenar")
    ruta = FUENTES / archivo
    if not archivo.endswith(".ttf") or "/" in archivo or not ruta.is_file():
        raise ErrorNegocio("The font does not exist.", 404, "no_encontrado")
    return Response(ruta.read_bytes(), media_type="font/ttf", headers={"Cache-Control": "public, max-age=604800"})


# ---- Generación e historial -----------------------------------------------------------------
@router.get("/etiquetas/oc/{oc_id}")
def resumen_oc(oc_id: int, db: Db, user: User):
    """Líneas de la OC con su artículo, familia y el diseño que se usaría; bultos y etiquetas ya generadas."""
    return generacion.resumen_oc(db, user, oc_id)


@router.post("/etiquetas/plan")
def plan(db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Qué se generaría: grupos con su plantilla y versión, cantidad de etiquetas y problemas (sin generar nada).
    modalidad, unidad (ORDEN, LINEA, UNIDAD, BULTO, MANUAL), oc_id, posiciones, cantidades, articulos, elegidas, prueba."""
    return generacion._publico(generacion.plan(db, user, datos))


@router.post("/etiquetas/generaciones")
def generar(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Genera el lote (formato PDF, PNG, SVG o ZIP): se detiene ante errores y pide aceptar_advertencias."""
    return ejecutar(db, user, clave, lambda: generacion.generar(db, user, datos))


@router.get("/etiquetas/generaciones")
def historial(db: Db, user: User, desde: date | None = None, hasta: date | None = None, usuario_id: int | None = None,
              oc_id: int | None = None, articulo_id: int | None = None, familia_id: int | None = None,
              plantilla_id: int | None = None, version_id: int | None = None, estado: str | None = None,
              page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    """Lotes generados con filtros por fecha, usuario, OC, artículo, familia, plantilla, versión y estado."""
    return generacion.listar(db, user, desde, hasta, usuario_id, oc_id, articulo_id, familia_id, plantilla_id, version_id,
                             estado, page, size)


# ---- Generación masiva ----------------------------------------------------------------------------
@router.get("/etiquetas/masivo/ordenes")
def ordenes_masivo(db: Db, user: User, familia_id: int | None = None, q: str | None = None, estado: str | None = None,
                   page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200), solo_ids: bool = False):
    """Órdenes de compra con artículos de la familia (líneas y artículos distintos de la familia, bultos y lotes ya generados)."""
    return masivo.ordenes_familia(db, user, familia_id, q, estado, page, size, solo_ids)


@router.get("/etiquetas/masivo/packing")
def buscar_packing(db: Db, user: User, q: str | None = None):
    """Listas de empaque para generar etiquetas de sus empaques."""
    return masivo.buscar_packing(db, user, q)


@router.get("/etiquetas/masivo/packing/{pl_id}")
def packing_masivo(pl_id: int, db: Db, user: User):
    """Una lista de empaque con sus niveles de empaque (tarimas, cajas, inner…) y cuántas unidades tiene cada uno."""
    return masivo.packing(db, user, pl_id)


@router.post("/etiquetas/masivo/plan")
def plan_masivo(db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Qué se generaría: un lote por OC (o uno de artículos o de la lista de empaque) con sus problemas."""
    return masivo.ver_plan(db, user, datos)


@router.post("/etiquetas/masivo")
def generar_masivo(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Genera los lotes con una etiqueta por página (tipo: ordenes, articulos o packing; plantilla_id; formato PDF o PNG)."""
    return ejecutar(db, user, clave, lambda: masivo.generar(db, user, datos))


@router.get("/etiquetas/masivo/{lote}/archivo")
def archivo_masivo(lote: str, db: Db, user: User, formato: str | None = Query(None, pattern="^(PDF|PNG)$")):
    """Los archivos de la generación masiva: un PDF (o ZIP de imágenes), o un ZIP con un PDF por OC."""
    contenido, nombre, mime = masivo.archivo(db, user, lote, formato)
    db.commit()
    return Response(contenido, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/etiquetas/generaciones/{generacion_id}")
def ver_generacion(generacion_id: int, db: Db, user: User):
    """Un lote con sus grupos, versiones exactas y los valores usados."""
    return generacion.dict_generacion(db, generacion.cargar(db, user, generacion_id), completo=True)


@router.get("/etiquetas/generaciones/{generacion_id}/archivo")
def archivo_generacion(generacion_id: int, db: Db, user: User, formato: str | None = Query(None, pattern="^(PDF|PNG|SVG|ZIP)$")):
    """El archivo del lote, dibujado de nuevo con la versión y los valores originales (X-Identico: si coincide con el original)."""
    contenido, nombre, mime, identico = generacion.archivo(db, user, generacion_id, formato)
    db.commit()
    return Response(contenido, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{nombre}"',
                                                         "X-Identico": "1" if identico else "0"})
