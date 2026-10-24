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
from app.modelos.maestros import Articulo, ArticuloVersion, Atributo

CAMPOS_ARTICULO = ("sku", "descripcion", "unidad", "peso_unitario", "tipo")
CAMPOS_PRODUCTO = ("nombre", "codigo_generico")
# De su ficha de comercio exterior (producto_comex): la foto conserva las mismas claves
CAMPOS_COMEX = ("descripcion_comercial", "pais_origen", "tipo", "version_ficha", "ficha")


def foto(a: Articulo) -> dict:
    """Los datos del artículo que una versión conserva."""
    p, fam = a.producto, a.familia_efectiva
    return {
        "articulo": {**{k: getattr(a, k) for k in CAMPOS_ARTICULO},
                     "familia": fam.codigo if fam else None, "familia_nombre": fam.nombre if fam else None},
        "atributos": dict(sorted(a.variantes.items())),
        "codigos": sorted([c.tipo, c.valor] for c in a.codigos),
        "componentes": sorted(({"sku": c.componente.sku, "cantidad": c.cantidad} for c in a.componentes),
                              key=lambda x: x["sku"]),
        "producto": {"id": p.id, **{k: getattr(p, k) for k in CAMPOS_PRODUCTO},
                     **{k: getattr(p.comex, k) for k in CAMPOS_COMEX},
                     "atributos": dict(sorted(p.valores.items()))} if p else None,
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
            if obj.variante is None or obj not in db.new:
                obj.variante = _variante(db, obj, a, ya)
            if obj.atributos is None or obj not in db.new:
                obj.atributos = _atributos(db, obj, a)


def _variante(db: Session, obj, a: Articulo | None, ya: dict) -> dict | None:
    """Los valores de variante de la línea: los de la línea de la OC en una factura,
    si no los del artículo, en el orden de los atributos."""
    if isinstance(obj, FacturaLinea):
        p = obj.posicion_oc or (db.get(PosicionOC, obj.posicion_oc_id) if obj.posicion_oc_id else None)
        if p is not None and p.variante:
            return dict(p.variante)
    if a is None:
        return None
    if "orden" not in ya:
        ya["orden"] = [c for (c,) in db.execute(select(Atributo.codigo).order_by(Atributo.orden, Atributo.codigo))]
    valores = {k: v for k, v in a.variantes.items() if v not in (None, "")}
    orden = ya["orden"]
    return {**{k: valores[k] for k in orden if k in valores}, **{k: v for k, v in valores.items() if k not in orden}} or None


def _atributos(db: Session, obj, a: Articulo | None) -> dict | None:
    """Foto de los atributos del producto de la línea: los de la posición de la OC en una
    factura; si no, los del producto del artículo."""
    if isinstance(obj, FacturaLinea):
        p = obj.posicion_oc or (db.get(PosicionOC, obj.posicion_oc_id) if obj.posicion_oc_id else None)
        if p is not None and p.atributos:
            return dict(p.atributos)
    if a is None or a.producto is None:
        return None
    return dict(a.producto.valores) or None
