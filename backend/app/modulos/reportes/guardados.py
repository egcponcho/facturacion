"""Reportes guardados: los propios y los que otros compartieron con la
organización (solo si se puede ver su fuente). Los cambia o borra quien lo
creó o la administración. Además, los reportes fijos del sistema (operativos)."""
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errores import ErrorNegocio
from app.modelos import Reporte, Usuario, ahora
from app.modulos.acceso.permisos import es_interno, tiene
from app.modulos.comun.historial import registrar
from app.modulos.reportes import generador
from app.modulos.reportes.fuentes import FUENTES

# Reportes fijos de Seguimiento (operativos, con sus filtros propios en esa pantalla)
SISTEMA = [
    {"clave": "ordenes", "titulo": "Purchase order tracking", "permiso": "seguimiento.ver",
     "descripcion": "Releases, invoicing progress and arrival against the in-store date.", "ruta": "/seguimiento"},
    {"clave": "embarques", "titulo": "Shipment tracking", "permiso": "seguimiento.ver",
     "descripcion": "Transport documents, load units and arrivals.", "ruta": "/seguimiento?vista=embarques"},
    {"clave": "documentos", "titulo": "Invoicing and packing list tracking", "permiso": "seguimiento.ver",
     "descripcion": "Invoices and packing lists by stage.", "ruta": "/seguimiento?vista=documentos"},
]


def _visible(user: Usuario, r: Reporte) -> bool:
    f = FUENTES.get((r.definicion or {}).get("fuente"))
    return bool(f) and tiene(user, f.permiso) and (r.creado_por == user.id or r.compartido)


def _dict(user: Usuario, r: Reporte) -> dict:
    return {"id": r.id, "nombre": r.nombre, "descripcion": r.descripcion, "tipo": r.tipo, "compartido": r.compartido,
            "fuente": (r.definicion or {}).get("fuente"), "definicion": r.definicion, "propio": r.creado_por == user.id,
            "puede_editar": r.creado_por == user.id or tiene(user, "admin"),
            "autor": r.autor.nombre if r.autor else None, "actualizado_en": r.actualizado_en}


def listar(db: Session, user: Usuario) -> dict:
    filas = db.scalars(select(Reporte).where(or_(Reporte.creado_por == user.id, Reporte.compartido.is_(True)))
                       .order_by(Reporte.nombre)).all()
    propios = [_dict(user, r) for r in filas if _visible(user, r)]
    return {"operativos": [r for r in propios if r["tipo"] == "operativo"],
            "analiticos": [r for r in propios if r["tipo"] == "analitico"],
            "sistema": [s for s in SISTEMA if tiene(user, s["permiso"])]}


def cargar(db: Session, user: Usuario, reporte_id: int) -> Reporte:
    r = db.get(Reporte, reporte_id)
    if not r or not _visible(user, r):
        raise ErrorNegocio("The report does not exist.", 404, "no_encontrado")
    return r


def _datos(user: Usuario, datos: dict) -> dict:
    nombre = " ".join(str(datos.get("nombre") or "").split())[:120]
    if not nombre:
        raise ErrorNegocio("The report needs a name.", 422, "validacion", [{"campo": "nombre", "mensaje": "The report needs a name."}])
    definicion = generador.validar(user, datos.get("definicion"))
    compartido = bool(datos.get("compartido"))
    if compartido and not es_interno(user):
        raise ErrorNegocio("Suppliers cannot share reports with the organization.", 403, "sin_permiso")
    return {"nombre": nombre, "descripcion": str(datos.get("descripcion") or "").strip()[:300] or None,
            "definicion": definicion, "tipo": definicion["tipo"], "compartido": compartido}


def crear(db: Session, user: Usuario, datos: dict) -> dict:
    r = Reporte(**_datos(user, datos), creado_por=user.id)
    try:
        with db.begin_nested():
            db.add(r)
            db.flush()
    except IntegrityError:
        raise ErrorNegocio("You already have a report with that name.", 409, "duplicado") from None
    registrar(db, user, "reporte", r.id, "crear", {"nombre": r.nombre, "fuente": r.definicion["fuente"]})
    return _dict(user, r)


def actualizar(db: Session, user: Usuario, reporte_id: int, datos: dict) -> dict:
    r = cargar(db, user, reporte_id)
    if r.creado_por != user.id and not tiene(user, "admin"):
        raise ErrorNegocio("Only whoever created the report can change it.", 403, "sin_permiso")
    for k, v in _datos(user, {"nombre": r.nombre, "definicion": r.definicion, "compartido": r.compartido,
                              "descripcion": r.descripcion, **datos}).items():
        setattr(r, k, v)
    r.actualizado_en = ahora()
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise ErrorNegocio("You already have a report with that name.", 409, "duplicado") from None
    registrar(db, user, "reporte", r.id, "editar", {"nombre": r.nombre})
    return _dict(user, r)


def eliminar(db: Session, user: Usuario, reporte_id: int) -> dict:
    r = cargar(db, user, reporte_id)
    if r.creado_por != user.id and not tiene(user, "admin"):
        raise ErrorNegocio("Only whoever created the report can delete it.", 403, "sin_permiso")
    registrar(db, user, "reporte", r.id, "eliminar", {"nombre": r.nombre})
    db.delete(r)
    return {"ok": True}
