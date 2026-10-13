"""Datos de partida de una organización nueva.

Una organización empieza con lo mínimo para trabajar, igual que la primera
instalación (migraciones 0039, 0040 y 0043): roles de fábrica y sugeridos,
listas de valores (unidades, monedas, incoterms, modos de transporte, hitos
del embarque…), estados de liberación de las OCs y categorías de artículo.
Todo se puede cambiar después en sus pantallas; no hay datos de ejemplo.

Se siembra en la organización con la que trabaja la sesión
(`core.organizacion.trabajando_en`).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import CategoriaArticulo, DominioClasificacion, EstadoLiberacion

# Estados de liberación de fábrica: (tipo, código, nombre, libera, con cambios,
# predeterminado, alias en archivos, orden)
LIBERACIONES = [
    ("COMERCIAL", "C", "Released by commercial", True, False, True, "released, liberada, yes, si, y, s, 1, true, ok", 1),
    ("COMERCIAL", "P", "Pending commercial", False, False, False, "pending, pendiente, not released, no, n, 0, false, bloqueada", 2),
    ("LOGISTICA", "300", "Released by logistics", True, False, False, "released, liberada, liberado, yes, si, y, s, 1, true, ok", 1),
    ("LOGISTICA", "301", "Released with later changes", True, True, False,
     "changed, released changed, released with changes, modificada, cambiada, liberada con cambios", 2),
    ("LOGISTICA", "304", "Not released by logistics", False, False, True,
     "not released, no liberada, pending, pendiente, no, n, 0, false, bloqueada", 3),
]
CATEGORIAS = [("CALZADO", "Footwear", "FOOTWEAR"), ("ROPA", "Apparel", "APPAREL"), ("ACCESORIO", "Accessories", "ACCESSORIES"),
              ("OTRO", "Other", None)]


def sembrar(db: Session) -> None:
    from app.modulos.acceso.roles import crear_roles_fabrica, crear_roles_sugeridos

    crear_roles_fabrica(db)
    crear_roles_sugeridos(db)
    from app.modulos.maestros.listas import sembrar as sembrar_listas

    sembrar_listas(db)
    from app.modulos.comercial.documentos import sembrar as sembrar_comercial

    sembrar_comercial(db)
    if not db.scalar(select(EstadoLiberacion.id).limit(1)):
        for t, c, n, li, cc, p, a, o in LIBERACIONES:
            db.add(EstadoLiberacion(tipo=t, codigo=c, nombre=n, libera=li, con_cambios=cc, predeterminado=p, alias=a,
                                    orden=o, activo=True))
    if not db.scalar(select(CategoriaArticulo.id).limit(1)):
        dominios = set(db.scalars(select(DominioClasificacion.codigo)))
        for c, n, d in CATEGORIAS:
            db.add(CategoriaArticulo(codigo=c, nombre=n, dominio=d if d in dominios else None, activo=True))
    db.flush()


def vincular_dominios(db: Session) -> None:
    """Las líneas de fábrica sin dominio toman el suyo cuando los dominios de
    clasificación ya están cargados (la empresa puede crearse antes)."""
    from app.core.organizacion import todas

    dominios = set(db.scalars(select(DominioClasificacion.codigo)))
    por_codigo = {c: d for c, _, d in CATEGORIAS if d in dominios}
    with todas(db):
        for cat in db.scalars(select(CategoriaArticulo).where(CategoriaArticulo.dominio.is_(None),
                                                              CategoriaArticulo.codigo.in_(por_codigo))):
            cat.dominio = por_codigo[cat.codigo]
