"""Rutas de las integraciones con sistemas externos (Configuración → Integraciones)."""
from datetime import date

from fastapi import APIRouter, Body, File, Query, Response, UploadFile

from app.modulos.integraciones import servicio
from app.web.rutas import Clave, Db, User, ejecutar, leer_subida

router = APIRouter()


@router.get("/integraciones")
def listar(db: Db, user: User):
    """Integraciones de la organización con sus mapeos vigentes, más los adaptadores y entidades disponibles."""
    return servicio.listar(db, user)


@router.post("/integraciones")
def crear(db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Crea una integración: código, nombre, sistema (descriptivo), adaptador y sus parámetros."""
    return ejecutar(db, user, clave, lambda: servicio.guardar(db, user, datos))


@router.put("/integraciones/{integracion_id}")
def editar(integracion_id: int, db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Modifica una integración (o la desactiva con activa=false)."""
    return ejecutar(db, user, clave, lambda: servicio.guardar(db, user, datos, integracion_id))


@router.put("/integraciones/{integracion_id}/mapeos/{entidad}/{direccion}")
def guardar_mapeo(integracion_id: int, entidad: str, direccion: str, db: Db, user: User, datos: dict = Body(...),
                  clave: Clave = None):
    """Guarda el mapeo de una entidad y dirección como una versión nueva; la anterior queda como histórica."""
    return ejecutar(db, user, clave, lambda: servicio.guardar_mapeo(db, user, integracion_id, entidad, direccion.upper(), datos))


@router.get("/integraciones/{integracion_id}/mapeos/{entidad}/{direccion}")
def versiones_mapeo(integracion_id: int, entidad: str, direccion: str, db: Db, user: User):
    """Todas las versiones del mapeo, de la más reciente a la más antigua."""
    return servicio.versiones_mapeo(db, user, integracion_id, entidad, direccion.upper())


@router.post("/integraciones/{integracion_id}/entrada/{entidad}")
async def entrada_previa(integracion_id: int, entidad: str, db: Db, user: User, archivo: UploadFile = File(...)):
    """Lee el contenido con el adaptador y el mapeo vigente y muestra qué se aplicaría, sin aplicar nada."""
    contenido = await leer_subida(archivo)
    res = servicio.entrada_previa(db, user, integracion_id, entidad, archivo.filename or "contenido", contenido)
    db.commit()
    return res


@router.post("/integraciones/ejecuciones/{ejecucion_id}/aplicar")
def entrada_aplicar(ejecucion_id: int, db: Db, user: User, clave: Clave = None):
    """Aplica una entrada previsualizada por los servicios del núcleo; el mismo contenido no se aplica dos veces."""
    return ejecutar(db, user, clave, lambda: servicio.entrada_aplicar(db, user, ejecucion_id))


@router.post("/integraciones/{integracion_id}/salida/{entidad}")
def salida(integracion_id: int, entidad: str, db: Db, user: User, solo_nuevas: bool = True,
           desde: date | None = None):
    """Arma el archivo para el sistema externo (p. ej. facturas finalizadas) y registra lo enviado."""
    contenido, tipo, nombre, ejec = servicio.salida(db, user, integracion_id, entidad, solo_nuevas, desde)
    db.commit()
    return Response(contenido, media_type=tipo, headers={
        "Content-Disposition": f'attachment; filename="{nombre}"', "X-Ejecucion-Id": str(ejec["id"]),
        "X-Registros": str(ejec["resumen"].get("registros", 0))})


@router.get("/integraciones/{integracion_id}/ejecuciones")
def ejecuciones(integracion_id: int, db: Db, user: User, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    """Bitácora de la integración: cada intercambio con su resultado."""
    return servicio.ejecuciones(db, user, integracion_id, page, size)


@router.get("/integraciones/ejecuciones/{ejecucion_id}")
def ejecucion(ejecucion_id: int, db: Db, user: User):
    """Una ejecución con sus filas traducidas y sus errores por fila."""
    return servicio.ejecucion(db, user, ejecucion_id)


@router.get("/integraciones/ejecuciones/{ejecucion_id}/rechazadas")
def rechazadas(ejecucion_id: int, db: Db, user: User):
    """Las filas rechazadas de una ejecución (CSV con sus columnas originales y el motivo), para corregirlas."""
    contenido, nombre = servicio.rechazadas(db, user, ejecucion_id)
    return Response(contenido, media_type="text/csv",  # text/*: Starlette agrega charset=utf-8
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/integraciones/{integracion_id}/referencias")
def referencias(integracion_id: int, db: Db, user: User, entidad: str | None = None):
    """Identificadores externos de los registros intercambiados por la integración."""
    return servicio.referencias(db, user, integracion_id, entidad)


@router.post("/integraciones/{integracion_id}/referencias/{referencia_id}/desvincular")
def desvincular(integracion_id: int, referencia_id: int, db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Quita el vínculo de un registro con su código externo, con motivo (resuelve un conflicto de referencias)."""
    return ejecutar(db, user, clave, lambda: servicio.desvincular(db, user, integracion_id, referencia_id, datos))
