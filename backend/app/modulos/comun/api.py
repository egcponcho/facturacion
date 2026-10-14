"""Rutas comunes: edición exclusiva de documentos y bitácora general.
"""
import asyncio
import json
import time
from datetime import date

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from app.modulos.comun import auditoria as bitacora
from app.modulos.comun import edicion, tabla
from app.web.rutas import Db, User

router = APIRouter()


# Canal de cambios (app/core/cambios.py): avisa qué tablas cambiaron en la
# organización, para que la pantalla abierta vuelva a pedir solo lo suyo
@router.get("/cambios", response_class=StreamingResponse)
async def canal_cambios(request: Request, db: Db, user: User, max_seg: int = Query(3300, ge=1, le=3600)):
    """Server-Sent Events: `data: {"tablas": [...]}` cada vez que cambian datos de la organización del usuario
    (o compartidos). Un comentario cada 25 s mantiene viva la conexión; tras `max_seg` se cierra y el navegador
    vuelve a conectarse solo."""
    from app.core.cambios import difusor
    from app.core.organizacion import de_sesion

    org = de_sesion(db)
    db.close()  # la conexión de la base no se queda tomada mientras el canal siga abierto
    cliente = await difusor.conectar(org)

    async def eventos():
        fin = time.monotonic() + max_seg
        try:
            yield "retry: 5000\n\n"
            while time.monotonic() < fin and not await request.is_disconnected():
                try:
                    tablas = await asyncio.wait_for(cliente.cola.get(), timeout=min(25, max(0.1, fin - time.monotonic())))
                except TimeoutError:
                    yield ": sigue\n\n"
                    continue
                yield f"data: {json.dumps({'tablas': tablas})}\n\n"
        finally:
            difusor.desconectar(cliente)

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# Edición exclusiva: una persona edita el documento y las demás lo leen
@router.get("/edicion/{entidad}/{entidad_id}")
def estado_edicion(entidad: str, entidad_id: int, db: Db, user: User):
    """Quién edita el documento en este momento, si alguien lo hace, y si es el propio usuario."""
    return edicion.estado(db, user, entidad, entidad_id)


@router.post("/edicion/{entidad}/{entidad_id}")
def tomar_edicion(entidad: str, entidad_id: int, db: Db, user: User):
    """Toma o renueva la edición exclusiva del documento (vence a los 2 min); 423 si otro lo edita."""
    r = edicion.tomar(db, user, entidad, entidad_id)
    db.commit()
    return r


@router.delete("/edicion/{entidad}/{entidad_id}")
def liberar_edicion(entidad: str, entidad_id: int, db: Db, user: User, forzar: bool = False):
    """Suelta la edición del documento; con forzar, un administrador libera la de otra persona."""
    r = edicion.liberar(db, user, entidad, entidad_id, forzar)
    db.commit()
    return r


# Bitácora general (administración)
@router.get("/auditoria")
def auditoria(
    db: Db,
    user: User,
    entidad: str | None = None,
    entidad_id: int | None = None,
    usuario_id: int | None = None,
    accion: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    orden: str | None = None,
    f: str | None = None,
):
    """Bitácora general (quién hizo qué y cuándo) con filtros, filtros por columna, orden y paginación. Requiere administración."""
    return bitacora.consultar(db, user, entidad, entidad_id, usuario_id, accion, desde, hasta, page, size, orden, tabla.leer(f))


@router.get("/auditoria/valores")
def auditoria_valores(
    db: Db,
    user: User,
    columna: str,
    buscar: str | None = None,
    f: str | None = None,
    entidad: str | None = None,
    entidad_id: int | None = None,
    usuario_id: int | None = None,
    accion: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
):
    """Valores únicos de una columna de la bitácora (con cuántos cambios tienen cada uno) bajo los demás filtros. Requiere administración."""
    return bitacora.valores(db, user, columna, buscar, tabla.leer(f), entidad, entidad_id, usuario_id, accion, desde, hasta)


@router.get("/auditoria/opciones")
def auditoria_opciones(db: Db, user: User):
    """Entidades y usuarios que aparecen en la bitácora, para sus filtros. Requiere administración."""
    return bitacora.opciones(db, user)
