"""Entorno de Alembic: usa el mismo motor y modelos que la aplicación."""
from alembic import context
from app import modelos as models  # noqa: F401  (registra las tablas en Base.metadata)
from app.core.db import Base, engine
from app.instalacion.migraciones import sin_claves_foraneas

target_metadata = Base.metadata


def incluir(objeto, nombre, tipo, reflejado, _comparado) -> bool:
    """Las llaves de coherencia de organización (…_org) viven solo en la base
    (app/modelos/referencias.py): no se comparan con los modelos."""
    return not (tipo == "foreign_key_constraint" and reflejado and (nombre or "").endswith("_org"))


def run_migrations_offline() -> None:
    context.configure(url=str(engine.url), target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=engine.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexion = context.config.attributes.get("connection")
    if conexion is not None:
        _correr(conexion)
        return
    with engine.connect() as con, sin_claves_foraneas(con):
        _correr(con)


def _correr(con) -> None:
    # SQLite no altera columnas en el lugar: "batch" recrea la tabla
    context.configure(connection=con, target_metadata=target_metadata, render_as_batch=con.dialect.name == "sqlite",
                      compare_type=True, include_object=incluir)
    with context.begin_transaction():
        context.run_migrations()
    if con.in_transaction():
        con.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
