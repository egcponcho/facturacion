"""Datos de partida de una organización nueva.

Una organización empieza con lo mínimo para trabajar, igual que la primera
instalación (migraciones 0039, 0040 y 0043): roles de fábrica y sugeridos,
listas de valores (unidades, monedas, incoterms, modos de transporte, hitos
del embarque…) y estados de liberación de las OCs. Los atributos de sus
productos (de cualquier rubro) los define la empresa: no se siembra ninguno.
Todo se puede cambiar después en sus pantallas; no hay datos de ejemplo.

Se siembra en la organización con la que trabaja la sesión
(`core.organizacion.trabajando_en`).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos import EstadoLiberacion

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


def sembrar(db: Session) -> None:
    from app.modulos.acceso.roles import crear_roles_fabrica, crear_roles_sugeridos

    crear_roles_fabrica(db)
    crear_roles_sugeridos(db)
    from app.modulos.maestros.listas import sembrar as sembrar_listas

    sembrar_listas(db)
    if not db.scalar(select(EstadoLiberacion.id).limit(1)):
        for t, c, n, li, cc, p, a, o in LIBERACIONES:
            db.add(EstadoLiberacion(tipo=t, codigo=c, nombre=n, libera=li, con_cambios=cc, predeterminado=p, alias=a,
                                    orden=o, activo=True))
    db.flush()
