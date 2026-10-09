"""Permisos por módulo, alcance de cada rol y filtros por proveedor.
"""
from app.core.empresa import regla
from app.core.errores import ErrorNegocio
from app.modelos import Usuario

TODOS = {"admin", "interno", "proveedor"}

INTERNOS = {"admin", "interno"}


# Catálogo de permisos por módulo: (clave, etiqueta, roles de fábrica que lo
# tienen, si un rol de proveedor puede tenerlo). Los roles se arman en Users
# and access marcando estos permisos; el proveedor sigue viendo solo lo suyo.
MODULOS = [
    ("Orders", [
        ("oc.ver", "See purchase orders", TODOS, True),
        ("oc.importar", "Import POs from the ERP", INTERNOS, False),
        ("oc.empaque", "Edit casepack and inner pack of a PO line", INTERNOS, False),
    ]),
    ("Invoices", [
        ("factura.editar", "Create and edit invoices", TODOS, True),
        ("factura.finalizar", "Finalize invoices", "finalizan", True),
        ("factura.reabrir", "Reopen finalized invoices", INTERNOS, False),
        ("factura.cancelar", "Cancel invoices", TODOS, True),
    ]),
    ("Packing lists", [
        ("pl.editar", "Create and edit packing lists", TODOS, True),
        ("pl.finalizar", "Finalize packing lists", "finalizan", True),
        ("pl.reabrir", "Reopen finalized packing lists", INTERNOS, False),
        ("pl.cancelar", "Cancel packing lists", TODOS, True),
        ("plantilla.editar", "Create and edit packing templates", TODOS, True),
    ]),
    ("Shipments", [
        ("transporte.gestionar", "See and manage shipments and load units", INTERNOS, False),
        ("recepcion.registrar", "Register warehouse receipts", INTERNOS, False),
    ]),
    ("Products", [
        ("producto.ver", "See products and technical sheets", TODOS, True),
        ("producto.ficha", "Edit technical sheets and send them to review", TODOS, True),
        ("producto.crear", "Create products", INTERNOS, False),
        ("producto.clasificar", "Classify, approve and return sheets", INTERNOS, False),
    ]),
    ("Tariff schedule", [
        ("aranceles.ver", "See the tariff schedule", INTERNOS, False),
        ("aranceles.editar", "Edit countries, SAC, notes and national codes", INTERNOS, False),
    ]),
    ("Classification engine", [
        ("clasificacion.ver", "See product families, attributes and rules", INTERNOS, False),
        ("clasificacion.configurar", "Configure product families, attributes and rules", INTERNOS, False),
    ]),
    ("Master data", [
        ("catalogos.ver", "See master data", INTERNOS, False),
        ("catalogos.crear", "Create and upload master data", INTERNOS, False),
        ("catalogos.editar", "Edit master data", INTERNOS, False),
        ("catalogos.eliminar", "Delete master data", INTERNOS, False),
    ]),
    ("Tracking", [
        ("seguimiento.ver", "See tracking and lead times", INTERNOS, True),
        ("alertas.ver", "See and resolve alerts", INTERNOS, False),
    ]),
    ("Administration", [
        ("admin", "Users, roles and suppliers", {"admin"}, False),
    ]),
]

PERMISOS = {k: (et, roles, prov) for _, ps in MODULOS for k, et, roles, prov in ps}


def _matriz() -> dict[str, set[str]]:
    finalizan = INTERNOS | ({"proveedor"} if regla("PROVEEDOR_PUEDE_FINALIZAR") else set())
    return {k: finalizan if roles == "finalizan" else roles for k, (_, roles, _) in PERMISOS.items()}


def permisos_fabrica(tipo: str) -> list[str]:
    return sorted(p for p, roles in _matriz().items() if tipo in roles)


def alcance(permisos, proveedor_id: int | None) -> str:
    """Qué datos ve el usuario. No lo define el rol sino el usuario: con un
    proveedor asignado solo ve lo de ese proveedor; sin proveedor es del equipo
    interno, y administra si su rol tiene el permiso de administración."""
    if proveedor_id:
        return "proveedor"
    return "admin" if "admin" in (permisos or []) else "interno"


def permisos_validos(permisos, proveedor_id: int | None = None) -> list[str]:
    """Permisos que aplican: un usuario de proveedor no recibe permisos de
    datos globales ni de administración aunque su rol los tenga."""
    return sorted({p for p in permisos or [] if p in PERMISOS and (not proveedor_id or (PERMISOS[p][2] and p != "admin"))})


def catalogo_permisos() -> list[dict]:
    return [{"modulo": m, "permisos": [{"clave": k, "etiqueta": et, "proveedor": prov} for k, et, _, prov in ps]}
            for m, ps in MODULOS]


def permisos_de(user: Usuario) -> list[str]:
    r = user.rol_ref
    if r is not None:
        permisos = permisos_validos(r.permisos, user.proveedor_id) if r.activo else []
    else:
        # Usuarios sin rol asignado (datos anteriores): permisos de fábrica de su tipo
        permisos = permisos_fabrica(user.rol)
    return _segun_flujo(user, permisos)


def _segun_flujo(user: Usuario, permisos: list[str]) -> list[str]:
    """El flujo de clasificación decide si el proveedor o el equipo interno
    llenan las fichas, aunque su rol tenga el permiso."""
    from sqlalchemy.orm import object_session

    from app.modulos.productos.flujo import captura_permitida

    db = object_session(user)
    if db is None or "producto.ficha" not in permisos or captura_permitida(db, user.proveedor_id):
        return permisos
    return [p for p in permisos if p != "producto.ficha"]


def tiene(user: Usuario, permiso: str) -> bool:
    return permiso in permisos_de(user)


def exigir(user: Usuario, permiso: str) -> None:
    if not tiene(user, permiso):
        raise ErrorNegocio("You do not have permission for this action.", 403, "sin_permiso")


def es_interno(user: Usuario) -> bool:
    return user.rol in INTERNOS


# ---- Alcance de los datos ---------------------------------------------------
# Qué datos ve cada usuario (Usuarios y accesos → Usuario → Alcance):
# - Un proveedor ve lo suyo y lo de los demás proveedores que representa
#   (p. ej. un agente con varios proveedores).
# - Un interno ve todo, o solo los proveedores que se le asignen.
# - Cualquiera puede quedar limitado a algunas sociedades (empresas que se
#   facturan), p. ej. el equipo de un país.
# - Un agente de carga o transportista (un rol con solo los permisos de
#   transporte) ve únicamente los embarques de sus transportistas.
# Los filtros devuelven un conjunto (o None: sin límite); un conjunto que no
# coincide con nada se representa con {-1} para no confundirse con «todos».
NADA = frozenset({-1})


def proveedores_de(user: Usuario) -> frozenset | None:
    extra = {int(x) for x in ((user.alcance or {}).get("proveedores") or [])}
    if user.rol == "proveedor":
        return frozenset({user.proveedor_id, *extra} - {None}) or NADA
    return frozenset(extra) or None


def un_proveedor(prov: frozenset | None) -> int | None:
    """El proveedor si el filtro es de uno solo (p. ej. para crear algo suyo)."""
    return next(iter(prov)) if prov and len(prov) == 1 and prov != NADA else None


def sociedades_de(user: Usuario) -> frozenset | None:
    return frozenset((user.alcance or {}).get("sociedades") or []) or None


def transportistas_de(user: Usuario) -> frozenset | None:
    return frozenset(int(x) for x in (user.alcance or {}).get("transportistas") or []) or None


def proveedor_filtro(user: Usuario, proveedor_id: int | None = None) -> frozenset | None:
    """Proveedores cuyos datos se muestran: el elegido (si está en el alcance
    del usuario) o todos los de su alcance (None: todos)."""
    if isinstance(proveedor_id, frozenset):  # ya filtrado (p. ej. por el tablero)
        return proveedor_id
    permitidos = proveedores_de(user)
    elegido = frozenset({int(proveedor_id)}) if proveedor_id else None
    if elegido and (permitidos is None or elegido <= permitidos):
        return elegido
    return permitidos


def sociedad_filtro(user: Usuario, col) -> list:
    """Condición SQL para limitar a las sociedades del usuario (vacía si no tiene límite)."""
    soc = sociedades_de(user)
    return [col.in_(soc)] if soc else []


def asegurar_proveedor(user: Usuario, proveedor_id: int, sociedad: str | None = None) -> None:
    """Un documento fuera del alcance del usuario no existe para él (404, para
    no revelar que existe)."""
    permitidos, soc = proveedores_de(user), sociedades_de(user)
    if (permitidos is not None and proveedor_id not in permitidos) or (soc and sociedad not in soc):
        raise ErrorNegocio("Document not found.", 404, "no_encontrado")
