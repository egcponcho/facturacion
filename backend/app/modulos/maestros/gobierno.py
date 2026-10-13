"""Gobierno de los datos maestros.

Cada catálogo puede tener responsables (los roles que lo mantienen) y datos
que la empresa vuelve obligatorios además de los del sistema. Se guarda en la
configuración de la organización:

    maestros: {<catalogo>: {"responsables": [rol_id, …], "obligatorios": [campo, …]}}

Sin responsables, lo mantiene cualquier rol con los permisos de datos
maestros. Los catálogos compartidos entre organizaciones (países, acuerdos)
los gobierna la plataforma y no se configuran aquí.

También vive aquí qué documentos usan el código de un registro (no tienen
llave foránea: guardan el código como foto del documento), para no borrar un
registro que todavía se usa.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.empresa import configuracion_actual
from app.core.errores import ErrorNegocio
from app.modelos import (
    Centro,
    Embarque,
    Factura,
    FacturaLinea,
    GrupoArticulo,
    OrdenCompra,
    Pais,
    PosicionOC,
    ReglaLeadTime,
    Rol,
    Sociedad,
    Usuario,
)
from app.modulos.acceso.permisos import CATALOGOS_COMPARTIDOS, edita_compartidos, exigir, tiene
from app.modulos.comun.historial import registrar

# Datos que no se pueden volver obligatorios: los sí/no y los que se arman aparte
TIPOS_NO_OBLIGABLES = {"bool", "regla_lt"}


def gobernable(tipo: str) -> bool:
    return tipo not in CATALOGOS_COMPARTIDOS


def _conf(tipo: str) -> dict:
    return ((configuracion_actual().get("maestros") or {}).get(tipo) or {}) if gobernable(tipo) else {}


def responsables(tipo: str) -> list[int]:
    return list(_conf(tipo).get("responsables") or [])


def obligatorios(tipo: str) -> set[str]:
    return set(_conf(tipo).get("obligatorios") or [])


def obligables(campos: list[dict]) -> list[dict]:
    """Datos del catálogo que la empresa puede volver obligatorios."""
    return [{"nombre": c["nombre"], "etiqueta": c["etiqueta"]} for c in campos
            if not c["obligatorio"] and not c.get("propio") and c["tipo"] not in TIPOS_NO_OBLIGABLES]


def es_responsable(user: Usuario, tipo: str) -> bool:
    roles = responsables(tipo)
    return not roles or user.rol_id in roles or tiene(user, "admin")


def exigir_responsable(db: Session, user: Usuario, tipo: str) -> None:
    if not es_responsable(user, tipo):
        nombres = [r.nombre for r in db.scalars(select(Rol).where(Rol.id.in_(responsables(tipo))).order_by(Rol.nombre))]
        raise ErrorNegocio(f"This catalog is maintained by: {', '.join(nombres) or '—'}.", 403, "sin_permiso",
                           {"responsables": nombres})


def puede(user: Usuario, tipo: str) -> dict:
    """Qué puede hacer el usuario en el catálogo (la pantalla lo usa para sus botones)."""
    compartido_ok = tipo not in CATALOGOS_COMPARTIDOS or edita_compartidos(user)
    duenio = compartido_ok and es_responsable(user, tipo)
    return {
        "crear": duenio and tiene(user, "catalogos.crear"),
        "editar": duenio and tiene(user, "catalogos.editar"),
        "eliminar": duenio and tiene(user, "catalogos.eliminar"),
        "gobernar": gobernable(tipo) and tiene(user, "admin"),
    }


def resumen(db: Session, tipo: str, campos: list[dict]) -> dict:
    """Lo que la pantalla muestra del gobierno del catálogo."""
    ids = responsables(tipo)
    roles = {r.id: r.nombre for r in db.scalars(select(Rol).where(Rol.id.in_(ids)))} if ids else {}
    return {"gobernable": gobernable(tipo), "responsables": [{"id": i, "nombre": roles[i]} for i in ids if i in roles],
            "obligatorios": sorted(obligatorios(tipo)), "obligables": obligables(campos)}


def guardar(db: Session, user: Usuario, tipo: str, campos: list[dict], datos: dict) -> dict:
    """Responsables y obligatorios de un catálogo (administración)."""
    from app.modulos.empresa.organizacion import actual

    exigir(user, "admin")
    if not gobernable(tipo):
        raise ErrorNegocio("This data is shared by every organization: only the platform administration changes it.",
                           403, "dato_compartido")
    ids = datos.get("responsables") or []
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise ErrorNegocio("Choose the roles that maintain this catalog.", 422, "validacion")
    activos = {r.id for r in db.scalars(select(Rol).where(Rol.id.in_(ids), Rol.activo.is_(True)))} if ids else set()
    if set(ids) - activos:
        raise ErrorNegocio("Choose active roles.", 422, "validacion")
    pedidos = datos.get("obligatorios") or []
    validos = [c["nombre"] for c in obligables(campos)]
    if not isinstance(pedidos, list) or set(pedidos) - set(validos):
        raise ErrorNegocio("Choose data of this catalog that can become required.", 422, "validacion")
    org = actual(db)
    conf = dict(org.configuracion or {})
    maestros = dict(conf.get("maestros") or {})
    antes = maestros.get(tipo) or {}
    nuevo = {"responsables": sorted(set(ids)), "obligatorios": [c for c in validos if c in pedidos]}
    if nuevo["responsables"] or nuevo["obligatorios"]:
        maestros[tipo] = nuevo
    else:
        maestros.pop(tipo, None)
    conf["maestros"] = maestros
    org.configuracion = conf
    registrar(db, user, "organizacion", org.id, "gobierno_maestros", {"catalogo": tipo, "antes": antes, "despues": nuevo})
    db.flush()
    return nuevo


# ---- Uso del código en los documentos --------------------------------------------
# catálogo → columnas que guardan su código. Los registros con llave foránea ya
# los protege la base de datos al borrar.
USOS_CODIGO = {
    "sociedades": [OrdenCompra.sociedad, Factura.sociedad],
    "centros": [OrdenCompra.centro, OrdenCompra.centro_destino, Factura.centro, Factura.centro_destino, Embarque.centro],
    "almacenes": [PosicionOC.almacen, FacturaLinea.almacen],
    "puertos": [OrdenCompra.puerto_despacho, Embarque.puerto_origen, Embarque.puerto_destino, Centro.puerto,
                ReglaLeadTime.puerto],
    "regiones": [Pais.region, ReglaLeadTime.region],
    "categorias": [GrupoArticulo.categoria],
}
# Valores de las listas que se guardan como código en los documentos
USOS_LISTA = {
    "moneda": [OrdenCompra.moneda, Factura.moneda, Sociedad.moneda],
    "incoterm": [OrdenCompra.incoterm, Factura.incoterm],
    "condicion_pago": [OrdenCompra.condicion_pago],
}


def exigir_sin_uso(db: Session, tipo: str, obj) -> None:
    """Un registro cuyo código usan los documentos no se borra: se desactiva."""
    columnas = USOS_LISTA.get(obj.lista, []) if tipo == "listas" else USOS_CODIGO.get(tipo, [])
    codigo = getattr(obj, "codigo", None)
    if not codigo:
        return
    for col in columnas:
        if db.scalar(select(col).where(col == codigo).limit(1)) is not None:
            raise ErrorNegocio(f"It cannot be deleted: {codigo} is used in documents or other records. Deactivate it instead.",
                               409, "en_uso")
