"""Versiones de un artículo: cómo era en cada momento que un documento lo usó
(app/modelos/versiones.py las crea) y qué cambió de una a la siguiente."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Articulo, ArticuloVersion, FacturaLinea, PosicionOC, Usuario
from app.modulos.acceso.permisos import exigir_alguno, proveedores_de


def _plano(d, prefijo: str = "") -> dict:
    """{«articulo.upc»: valor, «producto.ficha.uso»: valor…} para comparar dos fotos."""
    if isinstance(d, dict):
        res = {}
        for k, v in d.items():
            res.update(_plano(v, f"{prefijo}{k}."))
        return res
    return {prefijo[:-1]: d}


def cambios(antes: dict | None, despues: dict) -> list[dict]:
    if antes is None:
        return []
    a, b = _plano({k: v for k, v in antes.items() if k != "migracion"}), _plano({k: v for k, v in despues.items() if k != "migracion"})
    return [{"campo": k, "antes": a.get(k), "despues": b.get(k)} for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)][:200]


def cargar(db: Session, user: Usuario, articulo_id: int) -> Articulo:
    exigir_alguno(user, "catalogos.ver", "producto.ver")
    a = db.get(Articulo, articulo_id)
    permitidos = proveedores_de(user)
    if a is None or (permitidos is not None and a.proveedor_id not in permitidos):
        raise ErrorNegocio("The item does not exist.", 404, "no_encontrado")
    return a


def listar(db: Session, user: Usuario, articulo_id: int) -> list[dict]:
    """Las versiones del artículo (la más nueva primero), con cuántas líneas de OC y de
    factura usan cada una y qué cambió respecto de la anterior."""
    a = cargar(db, user, articulo_id)
    versiones = list(db.scalars(select(ArticuloVersion).where(ArticuloVersion.articulo_id == a.id)
                                .order_by(ArticuloVersion.numero)))
    ids = [v.id for v in versiones]

    def cuenta(modelo) -> dict:
        return dict(db.execute(select(modelo.articulo_version_id, func.count()).where(modelo.articulo_version_id.in_(ids))
                               .group_by(modelo.articulo_version_id)).all()) if ids else {}

    oc, fac = cuenta(PosicionOC), cuenta(FacturaLinea)
    res, anterior = [], None
    for v in versiones:
        res.append({"id": v.id, "numero": v.numero, "creada_en": v.creada_en, "migracion": bool(v.datos.get("migracion")),
                    "lineas_oc": oc.get(v.id, 0), "lineas_factura": fac.get(v.id, 0), "datos": v.datos,
                    "cambios": cambios(anterior, v.datos)})
        anterior = v.datos
    return res[::-1]
