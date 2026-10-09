"""Organización (empresa cliente) de la petición en curso: aislamiento de datos.

Varias organizaciones comparten una instalación sin ver los datos de las
demás. El aislamiento lo aplica la capa de datos, no cada pantalla:

1. Cada tabla de negocio hereda `DeOrganizacion` (columna `organizacion_id`).
   Un registro nuevo toma la organización de la sesión de base de datos; un
   registro de otra organización no se puede guardar en ella.
2. Toda consulta del ORM (listas, `db.get`, relaciones, UPDATE/DELETE
   masivos) se limita a la organización de la sesión (`do_orm_execute`). Un id
   de otra organización simplemente «no existe».
3. En PostgreSQL, además, cada transacción fija `app.organizacion_id` y las
   políticas de seguridad por fila (RLS, migración 0047) rechazan cualquier
   lectura o escritura de otra organización, aun con SQL escrito a mano.

La organización vive en `db.info` (una sesión por petición, así la ven todos
los hilos de la petición) y, fuera de una petición, en una variable de
contexto (`en_organizacion`, para sembrar una organización nueva). Sin
organización (arranque, migraciones, tareas de mantenimiento, plataforma) no
se filtra.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.orm import Mapped, Session, declared_attr, mapped_column, with_loader_criteria
from sqlalchemy.schema import ForeignKey

from app.core.errores import ErrorNegocio

CLAVE = "organizacion_id"
USUARIO = "usuario_id"
PRINCIPAL = 1  # la organización de una instalación de una sola empresa
_contexto: ContextVar[int | None] = ContextVar("organizacion", default=None)


class ConOrganizacion:
    """La columna organizacion_id (con índice y llave foránea)."""

    @declared_attr
    def organizacion_id(cls) -> Mapped[int]:  # noqa: N805
        return mapped_column(ForeignKey("organizaciones.id"), index=True)


class DeOrganizacion(ConOrganizacion):
    """Mixin de las tablas que pertenecen a una organización."""


_PROPIOS: list[type] = []


class UsuarioDeOrganizacion(ConOrganizacion):
    """Mixin de la tabla de usuarios: como las demás, pero cada usuario ve
    siempre su propio registro, aunque trabaje en otra organización (quien
    administra la plataforma edita su perfil desde cualquiera)."""

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        _PROPIOS.append(cls)


def de_sesion(db: Session) -> int | None:
    """Organización con la que trabaja esta sesión de base de datos."""
    return db.info.get(CLAVE) or _contexto.get()


def fijar(db: Session, organizacion_id: int | None, usuario_id: int | None = None) -> None:
    """Deja la sesión trabajando en una organización (o en ninguna) y, si se
    indica, con el usuario de la petición."""
    if organizacion_id is None:
        db.info.pop(CLAVE, None)
    else:
        db.info[CLAVE] = int(organizacion_id)
    if usuario_id is not None:
        db.info[USUARIO] = int(usuario_id)
    # La transacción ya abierta también la ve (PostgreSQL: RLS)
    if db.in_transaction():
        _variable_bd(db.connection(), db.info.get(CLAVE), db.info.get(USUARIO))


@contextmanager
def en_organizacion(organizacion_id: int):
    """Trabaja dentro de una organización fuera de una petición (sembrar una
    organización nueva, tareas programadas)."""
    marca = _contexto.set(int(organizacion_id))
    try:
        yield
    finally:
        _contexto.reset(marca)


def _variable_bd(conexion, organizacion_id: int | None, usuario_id: int | None = None) -> None:
    if conexion.dialect.name == "postgresql":
        conexion.exec_driver_sql(
            "SELECT set_config('app.organizacion_id', %s, true), set_config('app.usuario_id', %s, true)",
            ("" if organizacion_id is None else str(organizacion_id), "" if usuario_id is None else str(usuario_id)))


@event.listens_for(Session, "after_begin")
def _al_empezar(db: Session, _transaccion, conexion) -> None:
    org = de_sesion(db)
    if org is not None:
        _variable_bd(conexion, org, db.info.get(USUARIO))


@event.listens_for(Session, "do_orm_execute")
def _solo_la_organizacion(estado) -> None:
    org = de_sesion(estado.session)
    if org is None or estado.is_column_load:
        return
    if estado.is_select or estado.is_update or estado.is_delete:
        yo = estado.session.info.get(USUARIO) or 0
        estado.statement = estado.statement.options(
            with_loader_criteria(DeOrganizacion, lambda cls: cls.organizacion_id == org, include_aliases=True),
            *(with_loader_criteria(clase, lambda cls: (cls.organizacion_id == org) | (cls.id == yo), include_aliases=True)
              for clase in _PROPIOS))


def _propio(db: Session, obj) -> bool:
    return isinstance(obj, UsuarioDeOrganizacion) and obj.id is not None and obj.id == db.info.get(USUARIO)


@event.listens_for(Session, "before_flush")
def _asignar_organizacion(db: Session, _contexto_flush, _instancias) -> None:
    org = de_sesion(db)
    for obj in db.new:
        if isinstance(obj, ConOrganizacion) and obj.organizacion_id is None:
            obj.organizacion_id = org or PRINCIPAL
    if org is None:
        return
    for obj in (*db.new, *db.dirty):
        if isinstance(obj, ConOrganizacion) and obj.organizacion_id != org and not _propio(db, obj):
            raise ErrorNegocio("A record of another organization cannot be saved here.", 403, "otra_organizacion")


@contextmanager
def trabajando_en(db: Session, organizacion_id: int | None):
    """La sesión trabaja un momento en otra organización (crearla y sembrarla
    desde la plataforma) y después vuelve a la suya."""
    anterior = db.info.get(CLAVE)
    db.flush()
    fijar(db, organizacion_id)
    try:
        yield
        db.flush()
    finally:
        fijar(db, anterior)


@contextmanager
def todas(db: Session):
    """Consulta de la plataforma sobre todas las organizaciones (contar usuarios
    por organización, revisar que un correo no exista en ninguna): sin filtro
    del ORM ni de RLS mientras dura. Solo para lecturas acotadas."""
    with trabajando_en(db, None):
        yield db
