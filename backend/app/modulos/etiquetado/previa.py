"""Vista previa exacta (la dibuja el servidor con el mismo motor que la
descarga), miniaturas para las listas y la consulta de qué diseño se usaría."""
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Usuario
from app.modulos.acceso.permisos import exigir, exigir_alguno
from app.modulos.etiquetado import asignaciones, campos, datos, plantillas, salidas
from app.modulos.etiquetado import diseno as svc_diseno


def _numeracion(n: int = 1, total: int = 1) -> dict:
    return {"etiqueta.numero": n, "etiqueta.total": total, "etiqueta.numero_lote": n, "etiqueta.total_lote": total}


def vista_previa(db: Session, user: Usuario, pedido: dict) -> dict:
    exigir_alguno(user, "etiquetas.ver", "etiquetas.disenar")
    if pedido.get("version_id"):
        v = plantillas.cargar_version(db, pedido["version_id"])
        modalidad, contenido = v.plantilla.modalidad, v.diseno
    else:
        exigir(user, "etiquetas.disenar")
        modalidad = (pedido.get("modalidad") or "").upper()
        if modalidad not in campos.POR_MODALIDAD:
            raise ErrorNegocio("Choose the data mode.", 422, "validacion")
        contenido = plantillas.validar_contenido(db, user, modalidad, pedido.get("diseno") or {})
    reales = any(pedido.get(k) for k in ("articulo_id", "oc_id", "posicion_id"))
    valores = None
    if reales:
        posicion = datos.cargar_posicion(db, user, pedido["posicion_id"]) if pedido.get("posicion_id") else None
        oc = datos.cargar_oc(db, user, pedido.get("oc_id") or posicion.oc_id) if (pedido.get("oc_id") or posicion) else None
        articulo = datos.cargar_articulo(db, user, pedido["articulo_id"]) if pedido.get("articulo_id") else \
            (posicion.articulo if posicion else None)
        bulto = None
        if pedido.get("bulto") and oc:
            lista = campos.bultos(db, oc.id)
            n = int(pedido["bulto"])
            if not 1 <= n <= len(lista):
                raise ErrorNegocio("That package does not exist in the PO's packing lists.", 422, "validacion")
            bulto = lista[n - 1]
        valores = {**datos.valores(db, modalidad, articulo, oc, posicion, bulto), **_numeracion(),
                   **svc_diseno.valores_manuales(contenido, pedido.get("manuales"), ejemplo=True)}
    lz = plantillas.revisar(db, modalidad, contenido, valores, prueba=bool(pedido.get("prueba")))
    usados = svc_diseno.campos_usados(contenido)
    mostrados = valores if valores is not None else {**campos.ejemplos(db, modalidad), **_numeracion(),
                                                     **svc_diseno.valores_manuales(contenido, ejemplo=True)}
    return {"svg": salidas.svg(lz), "ancho": lz.ancho, "alto": lz.alto, "problemas": lz.problemas,
            "datos": "reales" if reales else "ejemplo",
            "valores": {k: mostrados.get(k) for k in sorted(usados) if not str(k).endswith(".logo")}}


def miniatura(db: Session, user: Usuario, version_id: int) -> str:
    exigir(user, "etiquetas.ver")
    v = plantillas.cargar_version(db, version_id)
    return salidas.svg(plantillas.revisar(db, v.plantilla.modalidad, v.diseno))


def resolver(db: Session, user: Usuario, modalidad: str, articulo_id: int | None, oc_id: int | None) -> dict:
    exigir_alguno(user, "etiquetas.ver", "etiquetas.generar")
    articulo = datos.cargar_articulo(db, user, articulo_id) if articulo_id else None
    oc = datos.cargar_oc(db, user, oc_id) if oc_id else None
    return asignaciones.resolver(db, modalidad, articulo, oc).dict()


