"""Versiones del artículo que usa cada documento.

Un artículo cambia con el tiempo (otra descripción, otro UPC, otra ficha); una
OC o una factura vieja debe seguir mostrando el artículo como era cuando se
hizo. Cada línea de OC y de factura guarda la versión del artículo que usó
(`articulo_version_id`) y se fija sola al crear la línea (o al cambiarle el
artículo): este hook la busca o la crea antes de guardar.

Una versión es la foto de los datos del artículo, sus atributos de variante,
sus campos propios, los componentes de su prepack y su producto con la ficha
técnica. Solo hay versión nueva cuando la foto cambia (huella sha256 de los
datos); mientras el artículo no cambie, todas las líneas comparten la misma.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from app.modelos.compras import PosicionOC
from app.modelos.facturacion import FacturaLinea
from app.modelos.maestros import Articulo, ArticuloVersion

CAMPOS_ARTICULO = ("sku", "sku_proveedor", "upc", "generico", "estilo", "color", "talla", "descripcion", "unidad",
                   "peso_unitario", "tipo")
CAMPOS_PRODUCTO = ("estilo", "color", "nombre", "codigo_generico", "descripcion_comercial", "pais_origen", "tipo",
                   "version_ficha", "ficha")


def foto(a: Articulo) -> dict:
    """Los datos del artículo que una versión conserva."""
    p, fam = a.producto, a.familia_efectiva
    return {
        "articulo": {**{k: getattr(a, k) for k in CAMPOS_ARTICULO},
                     "marca": a.marca.codigo if a.marca else None, "marca_nombre": a.marca.nombre if a.marca else None,
                     "grupo": a.grupo.codigo if a.grupo else None, "grupo_nombre": a.grupo.nombre if a.grupo else None,
                     "prepack": a.prepack.codigo if a.prepack else None,
                     "familia": fam.codigo if fam else None, "familia_nombre": fam.nombre if fam else None},
        "atributos": dict(sorted(a.variantes.items())),
        "extra": dict(a.extra or {}),
        "componentes": sorted(({"sku": c.articulo.sku, "cantidad": c.cantidad} for c in a.prepack.componentes),
                              key=lambda x: x["sku"]) if a.prepack else [],
        "producto": {"id": p.id, **{k: getattr(p, k) for k in CAMPOS_PRODUCTO}} if p else None,
    }


def huella(datos: dict) -> str:
    return hashlib.sha256(json.dumps(datos, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def vigente(db: Session, a: Articulo, _ya: dict | None = None) -> ArticuloVersion:
    """La versión del artículo como está ahora: la última si nada cambió, si no una nueva."""
    datos = foto(a)
    h = huella(datos)
    if _ya is not None and (a.id, h) in _ya:
        return _ya[(a.id, h)]
    with db.no_autoflush:
        ultima = db.scalar(select(ArticuloVersion).where(ArticuloVersion.articulo_id == a.id)
                           .order_by(ArticuloVersion.numero.desc()).limit(1)) if a.id else None
    if ultima is not None and ultima.huella == h:
        v = ultima
    else:
        v = ArticuloVersion(articulo=a, numero=(ultima.numero + 1) if ultima else 1, huella=h, datos=datos,
                            organizacion_id=a.organizacion_id)
        db.add(v)
    if _ya is not None:
        _ya[(a.id, h)] = v
    return v


def _articulo(db: Session, obj) -> Articulo | None:
    if isinstance(obj, FacturaLinea):
        p = obj.posicion_oc or (db.get(PosicionOC, obj.posicion_oc_id) if obj.posicion_oc_id else None)
        return _articulo(db, p) if p is not None else None
    return obj.articulo or (db.get(Articulo, obj.articulo_id) if obj.articulo_id else None)


@event.listens_for(Session, "before_flush")
def _fijar_versiones(db: Session, _contexto, _instancias) -> None:
    """Línea nueva (o con otro artículo) sin versión → la versión vigente de su artículo."""
    ya: dict = {}
    with db.no_autoflush:
        for obj in [x for x in (*db.new, *db.dirty) if isinstance(x, (PosicionOC, FacturaLinea))]:
            estado = inspect(obj)
            if estado.attrs.articulo_version_id.history.has_changes() or "articulo_version" in estado.committed_state:
                continue  # la versión se eligió a mano (p. ej. «actualizar con el artículo actual»)
            if obj in db.new:
                if obj.articulo_version_id is not None or obj.articulo_version is not None:
                    continue
            elif not (isinstance(obj, PosicionOC) and estado.attrs.articulo_id.history.has_changes()):
                continue
            a = _articulo(db, obj)
            obj.articulo_version = vigente(db, a, ya) if a is not None else None
