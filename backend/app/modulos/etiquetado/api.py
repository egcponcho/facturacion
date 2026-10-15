"""Etiquetado: tipos de etiqueta, familias, campos disponibles, diseños y sus
versiones, qué diseño lleva cada cosa (usos), trabajos de etiquetado,
historial y descargas (docs/ETIQUETADO.md)."""
from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Query, Response, UploadFile

from app.core.errores import ErrorNegocio
from app.modulos.acceso.permisos import exigir_alguno
from app.modulos.etiquetado import (
    buscadores,
    campos,
    campos_logicos,
    familias,
    generacion,
    plantillas,
    previa,
    tipos,
    trabajos,
    usos,
)
from app.web.rutas import Clave, Db, User, ejecutar, leer_subida

router = APIRouter()


# ---- Campos dinámicos -------------------------------------------------------------------
SUJETO = Query(None, pattern="^(ARTICULO|BULTO|DOCUMENTO)$")


@router.get("/etiquetas/catalogos")
def catalogos(db: Db, user: User):
    """Lo que la interfaz necesita para armar sus formularios: qué se etiqueta, cuántas salen,
    niveles y excepciones posibles, operadores de las condiciones, simbologías y tamaños."""
    from app.modelos.etiquetado import CANTIDADES_DE, CONTEXTOS, NIVELES_DE
    from app.modulos.etiquetado import codigos, reglas

    exigir_alguno(user, "etiquetas.ver", "etiquetas.generar", "etiquetas.disenar", "etiquetas.configurar")
    return {"sujetos": list(CANTIDADES_DE), "cantidades": CANTIDADES_DE, "niveles": NIVELES_DE, "contextos": list(CONTEXTOS),
            "orden_contexto": list(reglas.ORDEN_CONTEXTO), "operadores": list(reglas.OPERADORES),
            "operadores_simples": list(reglas.OPERADORES_SIMPLES), "simbologias": codigos.catalogo(),
            "tamanos": plantillas.tamanos(), "sugeridos": tipos.SUGERIDOS, "origenes": dict(trabajos.SUJETOS_DE),
            "completables": list(trabajos.COMPLETABLES)}


@router.get("/etiquetas/campos")
def listar_campos(db: Db, user: User, sujeto: str | None = SUJETO):
    """Campos que se pueden poner en una etiqueta, por grupo, con su origen (tabla.columna) y un ejemplo."""
    exigir_alguno(user, "etiquetas.ver", "etiquetas.disenar")
    propios = campos.personalizados()
    return {"grupos": campos.GRUPOS, "sujetos": {k: sorted(v) for k, v in campos.POR_SUJETO.items()},
            "campos": [campos.dict_campo(c, propios) for c in campos.catalogo(db, sujeto)],
            "colecciones": [campos.dict_coleccion(c) for c in campos.colecciones(sujeto, db)]}


@router.put("/etiquetas/campos/propios")
def guardar_campos_propios(db: Db, user: User, campos_: dict[str, dict[str, Any]] = Body(..., alias="campos", embed=True)):
    """Nombres propios de la empresa para los campos y los que se ocultan al diseñar ({clave: {nombre, oculto}})."""
    return ejecutar(db, user, None, lambda: campos.guardar_personalizados(db, user, campos_))


@router.put("/etiquetas/tamanos")
def guardar_tamanos(db: Db, user: User, tamanos: list[dict[str, Any]] = Body(..., embed=True)):
    """Los tamaños de etiqueta que se ofrecen al crear un diseño (nombre, ancho y alto en mm)."""
    return ejecutar(db, user, None, lambda: plantillas.guardar_tamanos(db, user, tamanos))


# ---- Tipos de etiqueta -------------------------------------------------------------------
@router.get("/etiquetas/tipos")
def listar_tipos(db: Db, user: User, todos: bool = False):
    """Tipos de etiqueta activos de la empresa (qué se etiqueta, cuántas salen, si son obligatorios); `todos` suma los inactivos."""
    return tipos.listar(db, user, None if todos else True)


@router.post("/etiquetas/tipos")
def crear_tipo(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Nuevo tipo: codigo, nombre, descripcion, sujeto (ARTICULO, BULTO, DOCUMENTO), cantidad, obligatoria, orden."""
    return ejecutar(db, user, clave, lambda: tipos.crear(db, user, datos))


@router.post("/etiquetas/tipos/sugeridos")
def crear_tipos_sugeridos(db: Db, user: User, codigos: list[str] = Body(..., embed=True)):
    """Primer uso: crea los tipos sugeridos elegidos (colgante, precio, caja, contenido de OC)."""
    return ejecutar(db, user, None, lambda: tipos.crear_sugeridos(db, user, codigos))


@router.patch("/etiquetas/tipos/{tipo_id}")
def actualizar_tipo(tipo_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Cambia el tipo (con `version`); `activo: false` lo retira de las pantallas."""
    return ejecutar(db, user, None, lambda: tipos.actualizar(db, user, tipo_id, datos))


# ---- Qué diseño lleva cada cosa (usos de diseño) -------------------------------------------
@router.get("/etiquetas/matriz")
def matriz(db: Db, user: User, sujeto: str = Query("ARTICULO", pattern="^(ARTICULO|BULTO|DOCUMENTO)$")):
    """Familias (o tipos de empaque) × tipos de etiqueta: el diseño de cada celda, lo que hereda y la cobertura."""
    return usos.matriz(db, user, sujeto)


@router.get("/etiquetas/celda")
def ver_celda(db: Db, user: User, tipo: int, nivel: str = Query(..., pattern="^(GENERAL|FAMILIA|PRODUCTO|SKU|TIPO_EMPAQUE)$"),
              destino_id: int | None = None):
    """Una celda: su diseño normal, lo que heredaría, sus excepciones, los productos con diseño propio y su firma."""
    return usos.celda(db, user, tipo, nivel, destino_id)


@router.put("/etiquetas/usos/celda")
def guardar_celda(db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Guarda la celda entera (normal, excepciones nuevas o editadas y las que se quitan) con la firma que se leyó."""
    return ejecutar(db, user, None, lambda: usos.guardar_celda(db, user, datos))


@router.post("/etiquetas/usos/simular")
def simular(db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Qué cambiaría si la celda se guardara así (no guarda nada)."""
    return usos.simular(db, user, datos)


@router.post("/etiquetas/usos/lote")
def lote_usos(db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """La misma excepción en varias celdas de un tipo («aplicar también a…»)."""
    return ejecutar(db, user, None, lambda: usos.lote(db, user, datos))


@router.get("/etiquetas/usos/valores")
def valores_contexto(db: Db, user: User, contexto: str = Query(..., pattern="^(PAIS_DESTINO|CENTRO_DESTINO|SOCIEDAD|PROVEEDOR)$")):
    """Los valores que puede tener una excepción (países de los centros destino, centros, sociedades, proveedores)."""
    return usos.valores_contexto(db, user, contexto)


@router.get("/etiquetas/usos")
def listar_usos(db: Db, user: User, tipo_etiqueta_id: int | None = None, nivel: str | None = None, destino_id: int | None = None,
                oc_id: int | None = None, plantilla_id: int | None = None, contexto_tipo: str | None = None, bajas: bool = False):
    """Usos de diseño (con filtros); `bajas` incluye los dados de baja."""
    return usos.listar(db, user, tipo_etiqueta_id, nivel, destino_id, oc_id, plantilla_id, contexto_tipo, bajas)


@router.post("/etiquetas/usos")
def crear_uso(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Un uso suelto: diseño propio de un producto o SKU (`reemplazar` cambia el que había) o una excepción de una OC."""
    return ejecutar(db, user, clave, lambda: usos.crear(db, user, datos))


@router.patch("/etiquetas/usos/{uso_id}")
def actualizar_uso(uso_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Cambia cualquier dato del uso (diseño, lugar, excepción, vigencia) con `version`."""
    return ejecutar(db, user, None, lambda: usos.actualizar(db, user, uso_id, datos))


@router.post("/etiquetas/usos/{uso_id}/baja")
def baja_uso(uso_id: int, db: Db, user: User, motivo: str | None = Body(None, embed=True)):
    """Da de baja el uso (no se borra: queda en el historial)."""
    return ejecutar(db, user, None, lambda: usos.baja(db, user, uso_id, motivo))


@router.get("/etiquetas/usos/{uso_id}/historial")
def historial_uso(uso_id: int, db: Db, user: User):
    """Cada alta, cambio y baja del uso, con autor y fecha."""
    return usos.historial(db, user, uso_id)


@router.get("/etiquetas/resolver")
def resolver(db: Db, user: User, sujeto: str = Query("ARTICULO", pattern="^(ARTICULO|BULTO|DOCUMENTO)$"),
             articulo_id: int | None = None, oc_id: int | None = None, tipo_empaque_id: int | None = None):
    """Qué diseño de cada tipo lleva un artículo (con o sin OC), un bulto o un documento, y por qué."""
    return usos.resolver(db, user, articulo_id, oc_id, tipo_empaque_id, sujeto)


@router.get("/etiquetas/productos/{producto_id}")
def etiquetas_producto(producto_id: int, db: Db, user: User):
    """La pestaña Etiquetas del producto: familia, diseño de cada tipo y por qué, excepciones y tallas con diseño propio."""
    return usos.de_producto(db, user, producto_id)


@router.get("/etiquetas/resumen")
def resumen(db: Db, user: User, origen: str = Query(..., pattern="^(OC|PACKING|PRODUCTO)$"), id: int = Query(...)):
    """Lo que se imprimiría desde una OC, una lista de empaque o un producto: por tipo, cuántas, con qué diseños y qué falta."""
    return generacion.resumen(db, user, origen, id)


# ---- Campos lógicos (precedencia de fuentes) ----------------------------------------------
@router.get("/etiquetas/campos-logicos")
def listar_campos_logicos(db: Db, user: User):
    """Campos lógicos: de qué fuentes sale cada uno, en qué orden y qué hacer si no coinciden."""
    return campos_logicos.listar(db, user)


@router.post("/etiquetas/campos-logicos")
def crear_campo_logico(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """clave, etiqueta, tipo, fuentes (en orden), politica (PRIMERA, ADVERTIR, BLOQUEAR) y sujetos."""
    return ejecutar(db, user, clave, lambda: campos_logicos.crear(db, user, datos))


@router.patch("/etiquetas/campos-logicos/{campo_id}")
def actualizar_campo_logico(campo_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Cambia el campo lógico (con `version` para no pisar el cambio de otro)."""
    return ejecutar(db, user, None, lambda: campos_logicos.actualizar(db, user, campo_id, datos))


@router.delete("/etiquetas/campos-logicos/{campo_id}")
def eliminar_campo_logico(campo_id: int, db: Db, user: User):
    """Borra un campo lógico que ningún diseño usa (si se usa, se desactiva)."""
    return ejecutar(db, user, None, lambda: campos_logicos.eliminar(db, user, campo_id))


# ---- Familias de etiquetado --------------------------------------------------------------
@router.get("/etiquetas/familias")
def listar_familias(db: Db, user: User, activas: bool | None = None):
    """Familias de etiquetado de la empresa con cuántos artículos y diseños tienen."""
    return familias.listar(db, user, activas)


@router.post("/etiquetas/familias")
def crear_familia(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Nueva familia: código, nombre, descripción, orden y campos habituales u obligatorios."""
    return ejecutar(db, user, clave, lambda: familias.crear(db, user, datos))


@router.post("/etiquetas/familias/desde-grupos")
def familias_desde_grupos(db: Db, user: User):
    """Primer uso: una familia por cada grupo de artículos sin familia (el grupo queda en ella)."""
    return ejecutar(db, user, None, lambda: familias.desde_grupos(db, user))


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


@router.get("/etiquetas/productos")
def productos_familia(db: Db, user: User, q: str | None = None, familia: str | None = None, page: int = Query(1, ge=1),
                      size: int = Query(50, ge=1, le=200)):
    """Productos (estilo-color) con su familia de etiquetado (familia=sin: los que no tienen)."""
    return familias.productos(db, user, q, familia, page, size)


@router.post("/etiquetas/productos/familia")
def asignar_familia_productos(db: Db, user: User, familia_id: int | None = Body(None), ids: list[int] = Body(...)):
    """Pone la familia a varios productos (o se la quita): la heredan sus tallas sin familia propia."""
    return ejecutar(db, user, None, lambda: familias.asignar_productos(db, user, familia_id, ids))


@router.post("/etiquetas/articulos/familia")
def asignar_familia(db: Db, user: User, familia_id: int | None = Body(None), ids: list[int] | None = Body(None),
                    filtro: dict[str, Any] | None = Body(None), clave: Clave = None):
    """Pone la familia (o la quita, con familia_id vacío) a los artículos elegidos o a todos los del filtro."""
    return ejecutar(db, user, clave, lambda: familias.asignar_articulos(db, user, familia_id, ids, filtro))


# ---- Plantillas y versiones ---------------------------------------------------------------
@router.get("/etiquetas/plantillas")
def listar_plantillas(db: Db, user: User, q: str | None = None, tipo_etiqueta_id: int | None = None, sujeto: str | None = SUJETO,
                      estado: str | None = "ACTIVA", estado_version: str | None = None, page: int = Query(1, ge=1),
                      size: int = Query(50, ge=1, le=200)):
    """Diseños con su tipo de etiqueta, tamaño, versión vigente, última versión y dónde se usan."""
    return plantillas.listar(db, user, q, tipo_etiqueta_id, sujeto, estado, estado_version, page, size)


@router.post("/etiquetas/plantillas")
def crear_plantilla(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Diseño nuevo (nombre, descripción, tipo de etiqueta, tamaño) con su versión 1 en borrador."""
    return ejecutar(db, user, clave, lambda: plantillas.crear(db, user, datos))


@router.get("/etiquetas/plantillas/{plantilla_id}")
def ver_plantilla(plantilla_id: int, db: Db, user: User):
    """Diseño con todas sus versiones y dónde se usa."""
    return plantillas.detalle(db, user, plantilla_id)


@router.get("/etiquetas/plantillas/{plantilla_id}/bitacora")
def bitacora_plantilla(plantilla_id: int, db: Db, user: User):
    """Bitácora del diseño: cada acción sobre él y sus versiones, con autor, fecha y motivo."""
    return plantillas.bitacora(db, user, plantilla_id)


@router.patch("/etiquetas/plantillas/{plantilla_id}")
def actualizar_plantilla(plantilla_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Nombre, descripción y tipo de etiqueta (otro tipo del mismo sujeto, mientras no esté en uso)."""
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
    Recibe version_id o un diseño sin guardar (con su tipo_etiqueta_id) y, opcionalmente, articulo_id, oc_id,
    posicion_id y bulto (número de caja)."""
    return previa.vista_previa(db, user, datos)


@router.get("/etiquetas/versiones/{version_id}/miniatura.svg")
def miniatura(version_id: int, db: Db, user: User):
    """La versión con datos de ejemplo, para las listas."""
    return Response(previa.miniatura(db, user, version_id), media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=60"})


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
@router.get("/etiquetas/generaciones")
def historial(db: Db, user: User, desde: date | None = None, hasta: date | None = None, usuario_id: int | None = None,
              oc_id: int | None = None, articulo_id: int | None = None, familia_id: int | None = None,
              plantilla_id: int | None = None, version_id: int | None = None, estado: str | None = None,
              page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    """Lotes generados con filtros por fecha, usuario, OC, artículo, familia, plantilla, versión y estado."""
    return generacion.listar(db, user, desde, hasta, usuario_id, oc_id, articulo_id, familia_id, plantilla_id, version_id,
                             estado, page, size)


# ---- Búsquedas del asistente ------------------------------------------------------------------
@router.get("/etiquetas/ordenes")
def ordenes(db: Db, user: User, familia_id: int | None = None, q: str | None = None, estado: str | None = None,
            page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200), solo_ids: bool = False):
    """Órdenes de compra con artículos de la familia (líneas y artículos distintos de la familia, bultos y lotes ya generados)."""
    return buscadores.ordenes_familia(db, user, familia_id, q, estado, page, size, solo_ids)


@router.get("/etiquetas/packing")
def buscar_packing(db: Db, user: User, q: str | None = None):
    """Listas de empaque para generar etiquetas (y si ya admiten etiquetas reales)."""
    return buscadores.buscar_packing(db, user, q)


@router.get("/etiquetas/packing/{pl_id}")
def packing(pl_id: int, db: Db, user: User):
    """Una lista de empaque con sus niveles de empaque (tarimas, cajas, inner…) y cuántas unidades tiene cada uno."""
    return buscadores.packing(db, user, pl_id)


# ---- Trabajos de etiquetado (asistente único) ---------------------------------------------------------
@router.get("/etiquetas/trabajos")
def listar_trabajos(db: Db, user: User, estado: str | None = None, q: str | None = None, page: int = Query(1, ge=1),
                    size: int = Query(25, ge=1, le=200)):
    """Trabajos de etiquetado (borradores para retomar, generados, parciales…)."""
    return trabajos.listar(db, user, estado, q, page, size)


@router.post("/etiquetas/trabajos")
def crear_trabajo(db: Db, user: User, datos: dict[str, Any] = Body(...), clave: Clave = None):
    """Nuevo trabajo: origen (OC, ARTICULOS, PACKING), parametros (oc_ids, posiciones, articulos, pl_id, tipos, prueba…),
    nombre y paso. Sin tipos, los obligatorios que aplican al origen."""
    return ejecutar(db, user, clave, lambda: trabajos.crear(db, user, datos))


@router.get("/etiquetas/trabajos/{trabajo_id}")
def ver_trabajo(trabajo_id: int, db: Db, user: User):
    """El trabajo con sus parámetros, registros validados, ejecuciones y resumen."""
    return trabajos.detalle(db, user, trabajo_id)


@router.patch("/etiquetas/trabajos/{trabajo_id}")
def guardar_trabajo(trabajo_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Guarda el borrador: nombre, paso del asistente y parámetros (con `version`)."""
    return ejecutar(db, user, None, lambda: trabajos.actualizar(db, user, trabajo_id, datos))


@router.post("/etiquetas/trabajos/{trabajo_id}/validar")
def validar_trabajo(trabajo_id: int, db: Db, user: User):
    """Arma y revisa cada registro en el servidor: diseño y por qué, datos, empaque, códigos (leídos con el lector)."""
    return ejecutar(db, user, None, lambda: trabajos.validar(db, user, trabajo_id))


@router.post("/etiquetas/trabajos/{trabajo_id}/completar")
def completar_trabajo(trabajo_id: int, db: Db, user: User, campo: str = Body(..., max_length=80),
                      valores: dict[str, Any] = Body(...)):
    """Completa en el maestro de artículos el dato que falta ({articulo_id: valor}: UPC, SKU del proveedor, peso,
    unidad) y vuelve a revisar el trabajo."""
    return ejecutar(db, user, None, lambda: trabajos.completar(db, user, trabajo_id, campo, valores))


@router.get("/etiquetas/trabajos/{trabajo_id}/registros/{registro_id}/vista-previa")
def vista_previa_registro(trabajo_id: int, registro_id: int, db: Db, user: User):
    """Un registro dibujado por el servidor con sus datos reales, su diseño y la procedencia de sus valores."""
    return trabajos.vista_previa(db, user, trabajo_id, registro_id)


@router.post("/etiquetas/trabajos/{trabajo_id}/generar")
def generar_trabajo(trabajo_id: int, db: Db, user: User, datos: dict[str, Any] = Body({}), clave: Clave = None):
    """Genera lo pendiente (formato, aceptar_advertencias, parcial). Si es grande, en segundo plano: consultar /estado."""
    r = ejecutar(db, user, clave, lambda: trabajos.generar(db, user, trabajo_id, datos))
    if r.get("asincrono") and r.get("estado") == "EN_PROCESO":
        trabajos.lanzar(trabajo_id)  # si otro ejecutor ya lo tomó (petición repetida, otra instancia), no hace nada
    return r


@router.get("/etiquetas/trabajos/{trabajo_id}/estado")
def estado_trabajo(trabajo_id: int, db: Db, user: User):
    """Estado y avance (etiquetas dibujadas de cuántas) de un trabajo."""
    return trabajos.estado(db, user, trabajo_id)


@router.post("/etiquetas/trabajos/{trabajo_id}/cancelar")
def cancelar_trabajo(trabajo_id: int, db: Db, user: User):
    """Cancela un trabajo que no se está generando (lo ya generado sigue en el historial)."""
    return ejecutar(db, user, None, lambda: trabajos.cancelar(db, user, trabajo_id))


@router.get("/etiquetas/trabajos/{trabajo_id}/archivo")
def archivo_trabajo(trabajo_id: int, db: Db, user: User, contenido: str | None = Query(None, pattern="^(PDF|PNG|SVG)$")):
    """ZIP con las etiquetas de todas las ejecuciones en las carpetas y con los nombres configurados, más el resumen."""
    datos_, nombre = trabajos.archivo(db, user, trabajo_id, contenido)
    db.commit()
    return Response(datos_, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/etiquetas/generaciones/{generacion_id}/impresion")
def confirmar_impresion(generacion_id: int, db: Db, user: User, datos: dict[str, Any] = Body(...)):
    """Confirma que las etiquetas se imprimieron (confirmo, cantidad, impresora, observacion si no fueron todas)."""
    return ejecutar(db, user, None, lambda: trabajos.confirmar_impresion(db, user, generacion_id, datos))


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
