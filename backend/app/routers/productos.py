from datetime import date

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import FileResponse

from .. import schemas as s
from ..services import especialista
from ..services import productos as svc
from .base import Clave, Db, Formato, User, descarga, ejecutar

router = APIRouter()


@router.get("/productos")
def listar(db: Db, user: User, q: str | None = None, proveedor_id: int | None = None, marca_id: str | None = None,
           grupo_id: int | None = None, estado: str | None = None, tipo: str | None = None, orden: str | None = None,
           page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=200)):
    filtros = {"q": q, "proveedor_id": proveedor_id, "marca_id": marca_id, "grupo_id": grupo_id, "estado": estado,
               "tipo": tipo}
    return svc.listar(db, user, filtros, page, size, orden)


@router.get("/productos/exportar")
def exportar(db: Db, user: User, q: str | None = None, proveedor_id: int | None = None, marca_id: str | None = None,
             estado: str | None = None, tipo: str | None = None, orden: str | None = None, formato: Formato = "xlsx"):
    filtros = {"q": q, "proveedor_id": proveedor_id, "marca_id": marca_id, "estado": estado, "tipo": tipo}
    return descarga(svc.exportar_lista(db, user, filtros, orden, formato), f"productos_{date.today():%Y%m%d}", formato)


@router.get("/productos/opciones")
def opciones(db: Db, user: User):
    return {**svc.opciones(db, user), "especialista": especialista.disponible()}


@router.get("/clasificacion/contexto")
def contexto(db: Db, user: User, proveedor_id: int | None = None):
    return {**svc.contexto(db, user, proveedor_id), "especialista": especialista.disponible()}


@router.get("/productos/fotos/{foto_id}")
def foto(foto_id: int, db: Db, user: User):
    f = svc.obtener_foto(db, user, foto_id)
    return FileResponse(f.ruta, media_type=f.tipo_mime, headers={"Cache-Control": "private, max-age=3600"})


@router.get("/productos/{producto_id}")
def detalle(producto_id: int, db: Db, user: User):
    return svc.detalle(db, user, producto_id)


@router.get("/productos/{producto_id}/pdf")
def ficha_pdf(producto_id: int, db: Db, user: User, version: int | None = None):
    contenido, nombre = svc.exportar_ficha(db, user, producto_id, "pdf", version)
    return descarga(contenido, nombre, "pdf")


@router.get("/productos/{producto_id}/ficha")
def ficha_archivo(producto_id: int, db: Db, user: User, formato: str = Query("pdf", pattern="^(pdf|xlsx)$"),
                  version: int | None = None):
    contenido, nombre = svc.exportar_ficha(db, user, producto_id, formato, version)
    return descarga(contenido, nombre, formato)


@router.get("/productos/{producto_id}/versiones/{version}")
def ver_version(producto_id: int, version: int, db: Db, user: User):
    return svc.ver_version(db, user, producto_id, version)


@router.put("/productos/{producto_id}/ficha")
def guardar_ficha(producto_id: int, datos: s.FichaIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_ficha(db, user, producto_id, datos))


@router.post("/productos/clasificar")
def clasificar_lote(datos: s.ClasificarLote, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.clasificar_lote(db, user, datos.items))


@router.post("/productos/aprobar")
def aprobar_lote(datos: s.AprobarLote, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.aprobar_lote(db, user, datos.ids))


@router.post("/productos/enviar")
def enviar_revision(datos: s.AprobarLote, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.enviar_revision(db, user, datos.ids))


@router.post("/productos/{producto_id}/retirar")
def retirar_revision(producto_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.retirar_revision(db, user, producto_id))


@router.post("/productos/{producto_id}/aprobar")
def aprobar(producto_id: int, datos: s.AprobarIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.aprobar(db, user, producto_id, datos))


@router.post("/productos/{producto_id}/observar")
def observar(producto_id: int, datos: s.ObservarIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.observar(db, user, producto_id, datos))


@router.post("/productos/{producto_id}/versiones")
def nueva_version(producto_id: int, datos: s.NuevaVersionIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.nueva_version(db, user, producto_id, datos))


@router.post("/productos/{producto_id}/analizar")
def analizar(producto_id: int, datos: s.AnalizarIn, db: Db, user: User):
    r = especialista.analizar(db, user, producto_id, datos)
    db.commit()
    return r


@router.post("/productos/{producto_id}/fotos")
async def subir_foto(producto_id: int, db: Db, user: User, archivo: UploadFile = File(...)):
    r = svc.subir_foto(db, user, producto_id, archivo.filename or "photo", archivo.content_type or "", await archivo.read())
    db.commit()
    return r


@router.delete("/productos/{producto_id}/fotos/{foto_id}")
def borrar_foto(producto_id: int, foto_id: int, db: Db, user: User):
    svc.borrar_foto(db, user, producto_id, foto_id)
    db.commit()
    return {"ok": True}


@router.post("/clasificacion/incisos")
def ensenar_inciso(datos: s.IncisoIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.ensenar_inciso(db, user, datos))


@router.delete("/clasificacion/incisos/{inciso_id}")
def borrar_inciso(inciso_id: int, db: Db, user: User):
    svc.borrar_inciso(db, user, inciso_id)
    db.commit()
    return {"ok": True}


@router.post("/clasificacion/palabras")
def ensenar_palabra(datos: s.PalabraIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.ensenar_palabra(db, user, datos))


@router.post("/clasificacion/sinonimos")
def ensenar_sinonimo(datos: s.SinonimoIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.ensenar_sinonimo(db, user, datos))
