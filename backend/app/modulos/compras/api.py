from fastapi import APIRouter, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from app.modulos.compras import ordenes as svc
from app.modulos.compras import perfiles
from app.web.rutas import Clave, Db, User, ejecutar

router = APIRouter()


@router.get("/ordenes")
def listar(
    db: Db,
    user: User,
    proveedor_id: int | None = None,
    q: str | None = None,
    centro: str | None = None,
    sociedad: str | None = None,
    marca: str | None = None,
    liberacion: str | None = None,
    destino: str | None = None,
    puerto: str | None = None,
    orden: str | None = None,
    almacen: str | None = None,
    comercial: str | None = None,
    liberada: bool | None = None,
    solo_disponible: bool = True,
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=200),
):
    return svc.listar_ordenes(db, user, proveedor_id, q, centro, solo_disponible, page, size,
                              sociedad, marca, liberacion, destino, puerto, orden, almacen, comercial, liberada)


@router.get("/ordenes/filtros")
def filtros(db: Db, user: User, proveedor_id: int | None = None):
    return svc.filtros_ordenes(db, user, proveedor_id)


@router.get("/ordenes/{oc_id}/posiciones")
def posiciones(oc_id: int, db: Db, user: User):
    return svc.posiciones_oc(db, user, oc_id)


class EmpaqueIn(BaseModel):
    casepack: int | None = Field(None, ge=1)
    inner_pack: int | None = Field(None, ge=1)


@router.put("/ordenes/{oc_id}/posiciones/{posicion_id}/empaque")
def empaque(oc_id: int, posicion_id: int, datos: EmpaqueIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.empaque_posicion(db, user, oc_id, posicion_id, datos.casepack,
                                                                    datos.inner_pack))


class OrdenNueva(BaseModel):
    cabecera: dict = Field(default_factory=dict)
    lineas: list[dict] = Field(default_factory=list, max_length=500)


@router.get("/ordenes/plantilla")
def plantilla_oc(db: Db, user: User):
    from fastapi import Response

    contenido = svc.plantilla_oc(db, user)
    return Response(contenido, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="purchase_orders_template.xlsx"'})


@router.get("/ordenes/formulario")
def formulario(db: Db, user: User):
    return svc.opciones_formulario(db, user)


@router.get("/ordenes/formulario/articulos")
def formulario_articulos(db: Db, user: User, proveedor: str = "", q: str = ""):
    return svc.articulos_formulario(db, user, proveedor, q)


@router.post("/ordenes")
def crear(datos: OrdenNueva, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.crear_oc(db, user, datos.model_dump()))


@router.post("/ordenes/importar/previa")
async def importar_previa(db: Db, user: User, archivo: UploadFile = File(...), perfil_id: int | None = Form(None)):
    contenido = await archivo.read()
    res = svc.importar_previa(db, user, archivo.filename or "archivo.csv", contenido, perfil_id)
    db.commit()
    return res


# Perfiles de importación: cómo leer el archivo que exporta el ERP de la empresa
@router.get("/ordenes/importar/perfiles")
def perfiles_importacion(db: Db, user: User):
    return perfiles.listar(db, user)


@router.post("/ordenes/importar/perfiles")
def crear_perfil(datos: dict, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: perfiles.crear(db, user, datos))


@router.patch("/ordenes/importar/perfiles/{perfil_id}")
def actualizar_perfil(perfil_id: int, datos: dict, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: perfiles.actualizar(db, user, perfil_id, datos))


@router.delete("/ordenes/importar/perfiles/{perfil_id}")
def eliminar_perfil(perfil_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: perfiles.eliminar(db, user, perfil_id))


@router.post("/ordenes/importar/{importacion_id}/aplicar")
def importar_aplicar(importacion_id: int, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.importar_aplicar(db, user, importacion_id))
