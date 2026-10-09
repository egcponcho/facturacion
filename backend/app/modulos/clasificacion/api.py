from datetime import date

from fastapi import APIRouter, File, Query, Request, UploadFile

from app import esquemas as s
from app.modulos.clasificacion import aranceles as svc
from app.web.rutas import Clave, Db, Formato, User, descarga, ejecutar, leer_subida, plantilla_o_vista

router = APIRouter()
XLSX = "xlsx"


def _filtros(request: Request, claves: tuple) -> dict:
    return {k: v for k, v in request.query_params.items() if k in claves and v != ""}


F_INC = ("pais", "q", "capitulo", "fuente", "activo")
F_SAC = ("q", "capitulo", "nivel", "fuente")


@router.get("/aranceles/opciones")
def opciones(db: Db, user: User):
    return svc.opciones(db, user)


@router.get("/aranceles/paises")
def paises(db: Db, user: User):
    return svc.paises(db, user)


@router.post("/aranceles/paises")
def crear_pais(datos: s.PaisArancelIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_pais(db, user, datos))


@router.put("/aranceles/paises/{pais_id}")
def editar_pais(pais_id: int, datos: s.PaisArancelIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_pais(db, user, datos, pais_id))


@router.delete("/aranceles/paises/{pais_id}")
def borrar_pais(pais_id: int, db: Db, user: User):
    svc.borrar_pais(db, user, pais_id)
    db.commit()
    return {"ok": True}


@router.get("/aranceles/sac")
def sac(request: Request, db: Db, user: User, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=500)):
    return svc.listar_sac(db, user, _filtros(request, F_SAC), page, size)


@router.get("/aranceles/sac/exportar")
def sac_exportar(request: Request, db: Db, user: User, formato: Formato = "xlsx"):
    return descarga(svc.exportar_sac(db, user, _filtros(request, F_SAC), formato), f"sac_{date.today():%Y%m%d}", formato)


@router.get("/aranceles/sac/plantilla")
def sac_plantilla(user: User, vista: bool = False):
    return plantilla_o_vista(svc.plantilla_sac(), "template_sac", vista)


@router.post("/aranceles/sac/importar")
async def sac_importar(db: Db, user: User, archivo: UploadFile = File(...)):
    r = svc.importar_sac(db, user, archivo.filename or "", await leer_subida(archivo))
    db.commit()
    return r


@router.post("/aranceles/sac")
def crear_sac(datos: s.PartidaSACIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_sac(db, user, datos))


@router.put("/aranceles/sac/{sac_id}")
def editar_sac(sac_id: int, datos: s.PartidaSACIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_sac(db, user, datos, sac_id))


@router.delete("/aranceles/sac/{sac_id}")
def borrar_sac(sac_id: int, db: Db, user: User):
    svc.borrar_sac(db, user, sac_id)
    db.commit()
    return {"ok": True}


@router.get("/aranceles/condiciones")
def condiciones(db: Db, user: User, pais: str | None = None, codigo: str | None = None):
    """Condiciones que aplican a un código nacional según el país y la subpartida."""
    return svc.condiciones_aplicables(db, user, pais, codigo)


@router.get("/aranceles/notas")
def notas(request: Request, db: Db, user: User):
    """Notas legales del SAC que el sistema tiene en cuenta al clasificar."""
    return svc.listar_notas(db, user, dict(request.query_params))


@router.get("/aranceles/notas/plantilla")
def notas_plantilla(user: User, vista: bool = False):
    return plantilla_o_vista(svc.plantilla_notas(), "template_sac_notes", vista)


@router.get("/aranceles/notas/exportar")
def notas_exportar(request: Request, db: Db, user: User, formato: Formato = "xlsx"):
    return descarga(svc.exportar_notas(db, user, dict(request.query_params), formato), f"sac_notes_{date.today():%Y%m%d}", formato)


@router.post("/aranceles/notas/importar")
async def notas_importar(db: Db, user: User, archivo: UploadFile = File(...)):
    r = svc.importar_notas(db, user, archivo.filename or "", await leer_subida(archivo))
    db.commit()
    return r


@router.post("/aranceles/notas")
def crear_nota(datos: s.NotaSACIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_nota(db, user, datos))


@router.put("/aranceles/notas/{nota_id}")
def editar_nota(nota_id: int, datos: s.NotaSACIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_nota(db, user, datos, nota_id))


@router.delete("/aranceles/notas/{nota_id}")
def borrar_nota(nota_id: int, db: Db, user: User):
    svc.borrar_nota(db, user, nota_id)
    db.commit()
    return {"ok": True}


@router.get("/aranceles/codigos")
def codigos(request: Request, db: Db, user: User, orden: str | None = None, page: int = Query(1, ge=1),
            size: int = Query(50, ge=1, le=500)):
    return svc.listar_incisos(db, user, _filtros(request, F_INC), page, size, orden)


@router.get("/aranceles/codigos/exportar")
def codigos_exportar(request: Request, db: Db, user: User, orden: str | None = None, formato: Formato = "xlsx"):
    return descarga(svc.exportar_incisos(db, user, _filtros(request, F_INC), orden, formato),
                    f"national_codes_{date.today():%Y%m%d}", formato)


@router.get("/aranceles/codigos/plantilla")
def codigos_plantilla(db: Db, user: User, pais: str | None = None, vista: bool = False):
    return plantilla_o_vista(svc.plantilla_incisos(db, pais), f"template_national_codes{'_' + pais if pais else ''}", vista)


@router.post("/aranceles/codigos/importar")
async def codigos_importar(db: Db, user: User, archivo: UploadFile = File(...), pais: str | None = None,
                           reemplazar: bool = False, fuente: str | None = None, version: str | None = None,
                           vigente_desde: date | None = None):
    r = svc.importar_incisos(db, user, archivo.filename or "", await leer_subida(archivo), pais, reemplazar, fuente, version, vigente_desde)
    db.commit()
    return r


@router.post("/aranceles/codigos")
def crear_codigo(datos: s.IncisoEditIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_inciso(db, user, datos))


@router.put("/aranceles/codigos/{inciso_id}")
def editar_codigo(inciso_id: int, datos: s.IncisoEditIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.guardar_inciso(db, user, datos, inciso_id))


@router.patch("/aranceles/codigos/{inciso_id}/override")
def codigo_override(inciso_id: int, datos: s.IncisoOverrideIn, db: Db, user: User, clave: Clave = None):
    """Capa custom de una línea nacional oficial (no se edita el dato oficial)."""
    from app.core.errores import ErrorNegocio
    from app.modelos import IncisoNacional
    from app.modulos.acceso.permisos import exigir

    def correr():
        exigir(user, "aranceles.editar")
        x = db.get(IncisoNacional, inciso_id)
        if not x:
            raise ErrorNegocio("The code does not exist.", 404, "no_encontrado")
        return svc.guardar_override_inciso(db, user, x, datos.model_dump(include={"descripcion", "nota", "activo"}), datos.motivo,
                                           datos.vigente_desde, datos.vigente_hasta)

    return ejecutar(db, user, clave, correr)


@router.delete("/aranceles/codigos/{inciso_id}/override")
def codigo_override_quitar(inciso_id: int, db: Db, user: User):
    r = svc.quitar_override_inciso(db, user, inciso_id)
    db.commit()
    return r


@router.post("/aranceles/codigos/borrar")
def borrar_codigos(datos: s.IdsIn, db: Db, user: User, clave: Clave = None):
    return ejecutar(db, user, clave, lambda: svc.borrar_incisos(db, user, datos.ids))


# ---- Capa oficial: fuentes, versiones, capítulos y dominios ------------------------
@router.get("/aranceles/oficial/integridad")
def oficial_integridad(db: Db, user: User):
    """Auditor de integridad: dato oficial sin fuente, contaminación de la empresa, versiones…"""
    from app.modulos.clasificacion import integridad

    return integridad.auditar(db, user)


@router.post("/aranceles/oficial/fuentes/{fuente_id}/verificar")
def oficial_fuente_verificar(fuente_id: int, datos: s.VerificarFuenteIn, db: Db, user: User, clave: Clave = None):
    """Registra la verificación de una fuente contra su publicación oficial."""
    from app.modulos.clasificacion import oficial

    return ejecutar(db, user, clave, lambda: oficial.verificar_fuente(db, user, fuente_id, datos.model_dump(exclude_unset=True)))


@router.get("/aranceles/oficial/fuentes")
def oficial_fuentes(db: Db, user: User):
    from app.modulos.clasificacion import oficial

    return oficial.fuentes_y_versiones(db, user)


@router.get("/aranceles/oficial/capitulos")
def oficial_capitulos(db: Db, user: User, q: str | None = None, estado: str | None = None, dominio: str | None = None):
    from app.modulos.clasificacion import oficial

    return oficial.capitulos(db, user, q, estado, dominio)


@router.patch("/aranceles/oficial/capitulos")
def oficial_capitulos_editar(datos: s.CapitulosPatch, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import oficial

    return ejecutar(db, user, clave, lambda: oficial.actualizar_capitulos(
        db, user, datos.ids, datos.model_dump(exclude={"ids"})))


@router.get("/aranceles/oficial/dominios")
def oficial_dominios(db: Db, user: User):
    from app.modulos.clasificacion import oficial

    return oficial.dominios(db, user)


@router.get("/familias")
def familias_resumen(db: Db, user: User):
    """Cada familia de producto con lo que tiene configurado, lo que le falta y cómo le va."""
    from app.modulos.clasificacion import familias

    return familias.resumen(db, user)


@router.get("/familias/{codigo}")
def familia_detalle(codigo: str, db: Db, user: User):
    from app.modulos.clasificacion import familias

    return familias.detalle(db, user, codigo)


@router.get("/i18n/catalogo/{idioma}")
def catalogo_traducido(idioma: str, db: Db, user: User):
    """Traducciones de los textos del catálogo: el frontend las suma a su diccionario."""
    from app.modulos.clasificacion import traducciones

    return traducciones.catalogo(db, idioma)


@router.get("/familias/traducciones/{idioma}")
def traducciones_lista(idioma: str, db: Db, user: User, q: str | None = None, pendientes: bool = False):
    from app.modulos.clasificacion import traducciones

    return traducciones.listar(db, user, idioma, q, pendientes)


@router.put("/familias/traducciones/{idioma}")
def traduccion_guardar(idioma: str, datos: dict, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import traducciones

    return ejecutar(db, user, clave, lambda: traducciones.guardar(db, user, idioma, datos.get("texto"), datos.get("traduccion")))


@router.post("/familias/{codigo}/probar")
def familia_probar(codigo: str, datos: dict, db: Db, user: User):
    """Clasifica un artículo de ejemplo con la familia (aunque esté en borrador); no guarda nada."""
    from app.modulos.clasificacion import familias

    return familias.probar(db, user, codigo, datos)


@router.post("/familias/{codigo}/publicar")
def familia_publicar(codigo: str, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import familias

    return ejecutar(db, user, clave, lambda: familias.publicar(db, user, codigo))


@router.post("/familias/{codigo}/despublicar")
def familia_despublicar(codigo: str, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import familias

    return ejecutar(db, user, clave, lambda: familias.despublicar(db, user, codigo))


@router.post("/aranceles/oficial/dominios")
@router.patch("/aranceles/oficial/dominios/{dominio_id}")
def oficial_dominio_guardar(datos: s.DominioIn, db: Db, user: User, dominio_id: int | None = None, clave: Clave = None):
    from app.modulos.clasificacion import categorias

    return ejecutar(db, user, clave, lambda: categorias.guardar_dominio(db, user, dominio_id, datos.model_dump(exclude_unset=True)))


@router.get("/aranceles/categorias")
def categorias_lista(db: Db, user: User, todas: bool = False):
    from app.modulos.acceso.permisos import exigir
    from app.modulos.clasificacion import categorias

    exigir(user, "producto.ver")
    return categorias.categorias(db, not todas)


@router.post("/aranceles/categorias")
@router.patch("/aranceles/categorias/{cat_id}")
def categorias_guardar(datos: s.CategoriaIn, db: Db, user: User, cat_id: int | None = None, clave: Clave = None):
    from app.modulos.clasificacion import categorias

    return ejecutar(db, user, clave, lambda: categorias.guardar_categoria(db, user, cat_id, datos.model_dump(exclude_unset=True)))


@router.put("/aranceles/oficial/dominios/{dominio_id}/capitulos/{capitulo}")
def oficial_dominio_capitulo(dominio_id: int, capitulo: str, datos: s.DominioCapituloIn, db: Db, user: User,
                             clave: Clave = None):
    from app.modulos.clasificacion import oficial

    return ejecutar(db, user, clave, lambda: oficial.guardar_dominio_capitulo(
        db, user, dominio_id, capitulo, datos.relevancia, datos.habilitado, datos.quitar))


@router.get("/aranceles/oficial/paquete/{numero}")
def oficial_paquete(numero: int, user: User, vista: bool = False):
    """Descarga el paquete Excel oficial incluido (01 catálogos, 02 motor, 03 nacional)."""
    from app.modulos.clasificacion import oficial

    ruta = next((r for r in oficial.PAQUETES if r.name.startswith(f"{numero:02d}_")), None)
    if not ruta or not ruta.exists():
        from app.core.errores import ErrorNegocio

        raise ErrorNegocio("The package does not exist.", 404, "no_encontrado")
    return plantilla_o_vista(ruta.read_bytes(), ruta.stem, vista)


@router.post("/aranceles/oficial/importar")
async def oficial_importar(db: Db, user: User, archivo: UploadFile = File(...)):
    """Carga un paquete oficial (fuentes, versiones, países, capítulos, dominios y atributos)."""
    from app.modulos.acceso.permisos import exigir
    from app.modulos.clasificacion import lotes

    exigir(user, "aranceles.editar")
    # También pasa por la previa: así se validan la inmutabilidad y la diferencia exacta
    lote = lotes.previa(db, user, await leer_subida(archivo), archivo.filename or "")
    db.commit()  # la previa queda guardada (y libera la escritura) antes de publicar
    if lote["filas"] or lote["errores"]:  # con errores, publicar lo rechaza (nunca se descarta en silencio)
        lotes.publicar(db, user, lote["id"])
    else:
        lotes.descartar(db, user, lote["id"])
    db.commit()
    hojas = lote["resumen"]["hojas"]
    return {"hojas": hojas, "errores": lote["errores"], "lote_id": lote["id"],
            "creados": sum(h["creados"] for h in hojas.values()), "actualizados": sum(h["actualizados"] for h in hojas.values())}


# ---- Cargas oficiales por etapas: previa → diferencias → publicar ------------------------
@router.post("/aranceles/oficial/previa")
async def oficial_previa(db: Db, user: User, archivo: UploadFile = File(...)):
    """Sube un paquete a una previa: valida y muestra qué cambiaría, sin aplicar nada."""
    from app.modulos.clasificacion import lotes

    r = lotes.previa(db, user, await leer_subida(archivo), archivo.filename or "")
    db.commit()
    return r


@router.get("/aranceles/oficial/lotes")
def oficial_lotes(db: Db, user: User):
    from app.modulos.clasificacion import lotes

    return lotes.lotes(db, user)


@router.get("/aranceles/oficial/lotes/{lote_id}")
def oficial_lote(lote_id: int, db: Db, user: User):
    from app.modulos.clasificacion import lotes

    return lotes.lote(db, user, lote_id)


@router.post("/aranceles/oficial/lotes/{lote_id}/publicar")
def oficial_publicar(lote_id: int, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import lotes

    return ejecutar(db, user, clave, lambda: lotes.publicar(db, user, lote_id))


@router.post("/aranceles/oficial/lotes/{lote_id}/descartar")
def oficial_descartar(lote_id: int, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import lotes

    return ejecutar(db, user, clave, lambda: lotes.descartar(db, user, lote_id))


# ---- Atributos de la ficha (definición, opciones y ámbitos) ------------------------
@router.get("/aranceles/atributos")
def atributos_lista(db: Db, user: User, q: str | None = None, dominio: str | None = None, origen: str | None = None):
    from app.modulos.clasificacion import atributos

    return atributos.listar(db, user, q, dominio, origen)


@router.post("/aranceles/reglas/motor")
def reglas_motor(db: Db, user: User, clave: Clave = None):
    """Pone al día las reglas de las familias (data/motor/familias); no pisa las editadas."""
    from app.modulos.acceso.permisos import exigir
    from app.modulos.clasificacion import reglas

    def correr():
        exigir(user, "clasificacion.configurar")
        return reglas.cargar_reglas_ficha(db)

    return ejecutar(db, user, clave, correr)


@router.post("/aranceles/atributos/motor")
def atributos_motor(db: Db, user: User, clave: Clave = None):
    """Agrega los atributos de la ficha del motor que aún no están en la base."""
    from app.modulos.acceso.permisos import exigir
    from app.modulos.clasificacion import atributos

    def correr():
        exigir(user, "clasificacion.configurar")
        return {"nuevos": atributos.cargar_motor(db)}

    return ejecutar(db, user, clave, correr)


@router.get("/aranceles/atributos/{atributo_id}")
def atributos_detalle(atributo_id: int, db: Db, user: User):
    from app.modulos.clasificacion import atributos

    return atributos.detalle(db, user, atributo_id)


@router.get("/aranceles/materiales")
def materiales_lista(db: Db, user: User):
    """Clases de material de la composición (de base y configuradas)."""
    from app.modulos.clasificacion import materiales

    return materiales.listar(db, user)


@router.post("/aranceles/materiales")
@router.patch("/aranceles/materiales/{clase_id}")
def materiales_guardar(datos: s.ClaseMaterialIn, db: Db, user: User, clase_id: int | None = None, clave: Clave = None):
    from app.modulos.clasificacion import materiales

    return ejecutar(db, user, clave, lambda: materiales.guardar(db, user, clase_id, datos.model_dump(exclude_unset=True)))


@router.get("/aranceles/busqueda")
def busqueda_lista(db: Db, user: User):
    """Vocabulario de búsqueda en el texto oficial (palabra → equivalentes)."""
    from app.modulos.clasificacion import busqueda

    return busqueda.listar(db, user)


@router.post("/aranceles/busqueda")
@router.patch("/aranceles/busqueda/{sid}")
def busqueda_guardar(datos: s.SinonimoBusquedaIn, db: Db, user: User, sid: int | None = None, clave: Clave = None):
    from app.modulos.clasificacion import busqueda

    return ejecutar(db, user, clave, lambda: busqueda.guardar(db, user, sid, datos.model_dump(exclude_unset=True)))


@router.post("/aranceles/atributos")
def atributos_crear(datos: s.AtributoIn, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import atributos

    return ejecutar(db, user, clave, lambda: atributos.guardar(db, user, None, datos.model_dump(exclude_unset=True)))


@router.patch("/aranceles/atributos/{atributo_id}")
def atributos_editar(atributo_id: int, datos: s.AtributoIn, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import atributos

    return ejecutar(db, user, clave, lambda: atributos.guardar(db, user, atributo_id, datos.model_dump(exclude_unset=True)))


@router.post("/aranceles/atributos/{atributo_id}/opciones")
@router.patch("/aranceles/atributos/{atributo_id}/opciones/{opcion_id}")
def atributos_opcion(atributo_id: int, datos: s.AtributoOpcionIn, db: Db, user: User, opcion_id: int | None = None,
                     clave: Clave = None):
    from app.modulos.clasificacion import atributos

    return ejecutar(db, user, clave, lambda: atributos.guardar_opcion(db, user, atributo_id, opcion_id,
                                                                      datos.model_dump(exclude_unset=True)))


@router.post("/aranceles/atributos/{atributo_id}/ambitos")
@router.patch("/aranceles/atributos/{atributo_id}/ambitos/{ambito_id}")
def atributos_ambito(atributo_id: int, datos: s.AtributoAmbitoIn, db: Db, user: User, ambito_id: int | None = None,
                     clave: Clave = None):
    from app.modulos.clasificacion import atributos

    return ejecutar(db, user, clave, lambda: atributos.guardar_ambito(db, user, atributo_id, ambito_id,
                                                                      datos.model_dump(exclude_unset=True)))


# ---- Reglas de clasificación ------------------------------------------------------------
@router.get("/aranceles/reglas")
def reglas_lista(db: Db, user: User, q: str | None = None, tipo: str | None = None, pais: str | None = None,
                 fuente: str | None = None, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)):
    from app.modulos.clasificacion import reglas

    return reglas.listar(db, user, q, tipo, pais, page, size, fuente)


@router.post("/aranceles/reglas")
def reglas_crear(datos: s.ReglaIn, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import reglas

    return ejecutar(db, user, clave, lambda: reglas.crear(db, user, datos.model_dump(exclude_unset=True)))


@router.post("/aranceles/reglas/simular")
def reglas_simular(datos: s.ReglaIn, db: Db, user: User, regla_id: int | None = None):
    """Qué artículos cambiarían de subpartida con esta regla (no guarda nada)."""
    from app.modulos.clasificacion import impacto

    return impacto.simular(db, user, datos.model_dump(exclude_unset=True), regla_id)


@router.get("/aranceles/reglas/desde-producto/{producto_id}")
def reglas_desde_producto(producto_id: int, db: Db, user: User):
    """Borrador de regla a partir de la decisión de aduanas sobre un artículo."""
    from app.modulos.clasificacion import impacto

    return impacto.desde_producto(db, user, producto_id)


@router.patch("/aranceles/reglas/{regla_id}")
def reglas_editar(regla_id: int, datos: s.ReglaIn, db: Db, user: User, clave: Clave = None):
    from app.modulos.clasificacion import reglas

    return ejecutar(db, user, clave, lambda: reglas.guardar(db, user, regla_id, datos.model_dump(exclude_unset=True)))


# ---- Regulaciones e impuestos por país ----------------------------------------------
@router.get("/aranceles/regulaciones")
def regulaciones_lista(db: Db, user: User, q: str | None = None, pais: str | None = None):
    from app.modulos.clasificacion import nacional

    return nacional.regulaciones(db, user, q, pais)


@router.post("/aranceles/regulaciones")
@router.patch("/aranceles/regulaciones/{reg_id}")
def regulaciones_guardar(datos: s.RegulacionIn, db: Db, user: User, reg_id: int | None = None, clave: Clave = None):
    from app.modulos.clasificacion import nacional

    return ejecutar(db, user, clave, lambda: nacional.guardar_regulacion(db, user, reg_id, datos.model_dump(exclude_unset=True)))


@router.get("/aranceles/impuestos")
def impuestos_lista(db: Db, user: User, q: str | None = None, pais: str | None = None):
    from app.modulos.clasificacion import nacional

    return nacional.impuestos(db, user, q, pais)


@router.post("/aranceles/impuestos")
@router.patch("/aranceles/impuestos/{imp_id}")
def impuestos_guardar(datos: s.ImpuestoIn, db: Db, user: User, imp_id: int | None = None, clave: Clave = None):
    from app.modulos.clasificacion import nacional

    return ejecutar(db, user, clave, lambda: nacional.guardar_impuesto(db, user, imp_id, datos.model_dump(exclude_unset=True)))


@router.get("/aranceles/requisitos")
def requisitos(db: Db, user: User, pais: str, codigo: str):
    """DAI, impuestos y regulaciones que aplican hoy a un código en un país."""
    from app.modulos.acceso.permisos import exigir
    from app.modulos.clasificacion import nacional

    exigir(user, "producto.ver")
    return nacional.requisitos(db, pais.upper(), codigo)


# ---- Árbol arancelario oficial ---------------------------------------------------
@router.get("/aranceles/arbol")
def arbol_hijos(db: Db, user: User, padre_id: int | None = None, version: str | None = None, q: str | None = None):
    """Sin `q`: hijos de un nodo (o los capítulos). Con `q`: búsqueda por código o texto."""
    from app.modulos.clasificacion import arbol

    if q:
        return arbol.buscar(db, user, q, version)
    return arbol.hijos(db, user, padre_id, version)


@router.get("/aranceles/arbol/resumen")
def arbol_resumen(db: Db, user: User, version: str | None = None):
    from app.modulos.clasificacion import arbol

    return arbol.resumen(db, user, version)


@router.get("/aranceles/arbol/{nodo_id}")
def arbol_nodo(nodo_id: int, db: Db, user: User):
    from app.modulos.clasificacion import arbol

    return arbol.nodo(db, user, nodo_id)
