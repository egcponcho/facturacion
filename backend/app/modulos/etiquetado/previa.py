"""Vista previa exacta (la dibuja el servidor con el mismo motor que la
descarga) y miniaturas para las listas."""
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import TipoEtiqueta, Usuario
from app.modulos.acceso.permisos import exigir, exigir_alguno
from app.modulos.etiquetado import campos, datos, plantillas, salidas
from app.modulos.etiquetado import diseno as svc_diseno


def _numeracion(n: int = 1, total: int = 1) -> dict:
    return {"etiqueta.numero": n, "etiqueta.total": total, "etiqueta.numero_lote": n, "etiqueta.total_lote": total}


def vista_previa(db: Session, user: Usuario, pedido: dict) -> dict:
    """Recibe version_id o un diseño sin guardar (con su tipo_etiqueta_id) y,
    opcionalmente, un registro real: articulo_id, oc_id, posicion_id o bulto (número de caja de la OC)."""
    exigir_alguno(user, "etiquetas.ver", "etiquetas.disenar")
    if pedido.get("version_id"):
        v = plantillas.cargar_version(db, pedido["version_id"])
        sujeto, contenido = v.plantilla.tipo.sujeto, v.diseno
    else:
        exigir(user, "etiquetas.disenar")
        tipo = db.get(TipoEtiqueta, int(pedido.get("tipo_etiqueta_id") or 0))
        if tipo is None:
            raise ErrorNegocio("Choose the label type.", 422, "validacion")
        sujeto = tipo.sujeto
        contenido = plantillas.validar_contenido(db, user, sujeto, pedido.get("diseno") or {})
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
        valores = {**datos.valores(db, sujeto, articulo, oc, posicion, bulto), **_numeracion(),
                   **svc_diseno.valores_manuales(contenido, pedido.get("manuales"), ejemplo=True)}
    lz = plantillas.revisar(db, sujeto, contenido, valores, prueba=bool(pedido.get("prueba")), user=user)
    usados = svc_diseno.campos_usados(contenido)
    mostrados = valores if valores is not None else {**campos.ejemplos(db, sujeto, user), **_numeracion(),
                                                     **svc_diseno.valores_manuales(contenido, ejemplo=True)}
    return {"svg": salidas.svg(lz), "ancho": lz.ancho, "alto": lz.alto, "problemas": lz.problemas,
            "datos": "reales" if reales else "ejemplo",
            "valores": {k: mostrados.get(k) for k in sorted(usados) if not str(k).endswith(".logo")}}


def miniatura(db: Session, user: Usuario, version_id: int) -> str:
    exigir(user, "etiquetas.ver")
    v = plantillas.cargar_version(db, version_id)
    return salidas.svg(plantillas.revisar(db, v.plantilla.tipo.sujeto, v.diseno, user=user))
