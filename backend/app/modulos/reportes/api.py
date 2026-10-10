"""Rutas del generador de reportes."""
from typing import Annotated

from fastapi import APIRouter, Body, Query
from fastapi.responses import Response

from app.modulos.reportes import fuentes, generador, guardados
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()
FormatoReporte = Annotated[str, Query(pattern="^(csv|xlsx|pdf)$")]
TIPOS_ARCHIVO = {"csv": "text/csv", "pdf": "application/pdf",  # text/*: Starlette agrega charset=utf-8
                 "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _archivo(contenido: bytes, nombre: str, formato: str) -> Response:
    nombre = "".join(ch for ch in nombre if ch.isalnum() or ch in " -_.").strip()[:80] or "reporte"
    return Response(contenido, media_type=TIPOS_ARCHIVO[formato],
                    headers={"Content-Disposition": f'attachment; filename="{nombre}.{formato}"'})


@router.get("/reportes/fuentes")
def fuentes_disponibles(user: User):
    """Fuentes de datos que el usuario puede consultar, con sus campos visibles."""
    return [fuentes.describir(f) for f in fuentes.disponibles(user)]


@router.post("/reportes/vista")
def vista_previa(db: Db, user: User, definicion: dict = Body(..., embed=True)):
    """Ejecuta una definición (hasta 500 filas) sin guardarla."""
    return generador.ejecutar(db, user, definicion)


@router.post("/reportes/exportar")
def exportar_definicion(db: Db, user: User, formato: FormatoReporte, definicion: dict = Body(..., embed=True),
                        titulo: str | None = Body(None, embed=True)):
    """Descarga una definición sin guardarla, en CSV, Excel o PDF (hasta 10 000 filas)."""
    contenido, nombre = generador.exportar(db, user, definicion, formato, titulo)
    return _archivo(contenido, nombre, formato)


@router.get("/reportes")
def listar(db: Db, user: User):
    """Reportes guardados (operativos y analíticos) y reportes fijos del sistema."""
    return guardados.listar(db, user)


@router.post("/reportes")
def crear(db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Guarda un reporte operativo o analítico; solo los usuarios internos pueden compartirlo."""
    return ejecutar(db, user, clave, lambda: guardados.crear(db, user, datos))


@router.get("/reportes/{reporte_id}")
def detalle(reporte_id: int, db: Db, user: User):
    """Reporte guardado con su definición y el resultado de ejecutarlo (hasta 500 filas)."""
    r = guardados.cargar(db, user, reporte_id)
    return {**guardados._dict(user, r), "resultado": generador.ejecutar(db, user, r.definicion)}


@router.patch("/reportes/{reporte_id}")
def actualizar(reporte_id: int, db: Db, user: User, datos: dict = Body(...), clave: Clave = None):
    """Cambia nombre, descripción, definición o si se comparte un reporte; solo su autor o administración."""
    return ejecutar(db, user, clave, lambda: guardados.actualizar(db, user, reporte_id, datos))


@router.delete("/reportes/{reporte_id}")
def eliminar(reporte_id: int, db: Db, user: User, clave: Clave = None):
    """Elimina un reporte guardado; solo su autor o la administración."""
    return ejecutar(db, user, clave, lambda: guardados.eliminar(db, user, reporte_id))


@router.get("/reportes/{reporte_id}/exportar")
def exportar_guardado(reporte_id: int, db: Db, user: User, formato: FormatoReporte):
    """Descarga un reporte guardado en CSV, Excel o PDF (hasta 10 000 filas)."""
    r = guardados.cargar(db, user, reporte_id)
    contenido, nombre = generador.exportar(db, user, r.definicion, formato, r.nombre)
    return _archivo(contenido, nombre, formato)
