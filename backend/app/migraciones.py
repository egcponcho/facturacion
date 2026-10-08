"""Migraciones con Alembic.

Al arrancar (demostración y producción por igual) se aplican las migraciones
pendientes. Una base creada antes de Alembic (con create_all) se marca en la
migración base 0001 y desde ahí se actualiza; nunca se borra nada.
"""
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from .db import engine

BASE = "0001"


def _config() -> Config:
    raiz = Path(__file__).resolve().parent.parent
    cfg = Config(str(raiz / "alembic.ini"))
    cfg.set_main_option("script_location", str(raiz / "alembic"))
    return cfg


@contextmanager
def sin_claves_foraneas(con):
    """SQLite: el modo batch de Alembic recrea la tabla (copia, borra y
    renombra). Con las claves foráneas activas, borrar la tabla vieja borraría
    en cascada sus hijos (p. ej. las reglas de cada código nacional). Se
    apagan mientras se migra y al final se verifica que no quede ninguna
    referencia rota."""
    sqlite = con.dialect.name == "sqlite"
    if sqlite:
        con.exec_driver_sql("PRAGMA foreign_keys=OFF")  # fuera de transacción: SQLite lo ignora dentro de una
        con.commit()
    try:
        yield con
    finally:
        if sqlite:
            rotas = con.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            con.exec_driver_sql("PRAGMA foreign_keys=ON")
            con.commit()
            if rotas:
                raise RuntimeError(f"The migration left broken references: {rotas[:5]}")


def actualizar() -> None:
    """Aplica las migraciones pendientes y pone al día los datos incluidos."""
    cfg = _config()
    tablas = set(inspect(engine).get_table_names())
    with engine.connect() as con, sin_claves_foraneas(con):
        with con.begin():
            cfg.attributes["connection"] = con
            if tablas and "alembic_version" not in tablas:
                command.stamp(cfg, BASE)
            command.upgrade(cfg, "head")
    # Motor y datos oficiales incluidos (lo oficial solo en una base sin datos
    # oficiales); nunca la demostración
    from .cargas import cargar_base
    from .db import SessionLocal

    with SessionLocal() as db:
        cargar_base(db)
        db.commit()
