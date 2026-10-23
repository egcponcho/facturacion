"""Los valores reales de una etiqueta: se leen de la OC, la línea, el
artículo, el bulto y la organización en el momento de generar, dentro del
alcance del usuario (un proveedor solo ve lo suyo)."""

from sqlalchemy.orm import Session

from app.core.empresa import hoy
from app.core.errores import ErrorNegocio
from app.modelos import OrdenCompra, PosicionOC, Usuario
from app.modulos.acceso.permisos import asegurar_proveedor, proveedor_filtro
from app.modulos.catalogo import servicio as catalogo
from app.modulos.etiquetado import campos


def cargar_oc(db: Session, user: Usuario, oc_id: int) -> OrdenCompra:
    oc = db.get(OrdenCompra, oc_id)
    if not oc:
        raise ErrorNegocio("The purchase order does not exist.", 404, "no_encontrado")
    asegurar_proveedor(user, oc.proveedor_id, oc.sociedad)
    return oc


def cargar_articulo(db: Session, user: Usuario, articulo_id: int) -> catalogo.FichaArticulo:
    a = catalogo.articulo(db, articulo_id)
    prov = proveedor_filtro(user)
    if not a or (prov is not None and a.proveedor_id not in prov):
        raise ErrorNegocio("The item does not exist.", 404, "no_encontrado")
    return a


def cargar_posicion(db: Session, user: Usuario, posicion_id: int) -> PosicionOC:
    p = db.get(PosicionOC, posicion_id)
    if not p:
        raise ErrorNegocio("The PO line does not exist.", 404, "no_encontrado")
    cargar_oc(db, user, p.oc_id)
    return p


def valores(db: Session, sujeto: str, articulo: catalogo.FichaArticulo | None = None, oc: OrdenCompra | None = None,
            posicion: PosicionOC | None = None, bulto: campos.Bulto | None = None, organizacion: dict | None = None,
            pl=None, de_oc: dict | None = None) -> dict:
    """Todos los valores de una etiqueta (sin la numeración, que pone la generación).
    El artículo lleva sus datos siempre y los de la OC y su línea si viene de una
    (el mismo artículo, con o sin OC, es la misma etiqueta: solo cambian esos
    datos). `de_oc`: los valores de la OC ya leídos (una vez por OC, no por registro)."""
    v = dict(organizacion if organizacion is not None else campos.valores_organizacion(db))
    grupos = campos.POR_SUJETO[sujeto]
    if oc is not None and "oc" in grupos:
        v.update(de_oc if de_oc is not None else campos.valores_oc(db, oc))
    if posicion is not None and "linea" in grupos:
        v.update(campos.valores_linea(posicion))
    if articulo is not None and "articulo" in grupos:
        v.update(campos.valores_articulo(db, articulo))
    if pl is not None and "pl" in grupos:
        v.update(campos.valores_pl(pl))
    if bulto is not None:
        v.update(bulto.valores)
    v["etiqueta.fecha"] = hoy().isoformat()
    return v
