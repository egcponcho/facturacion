"""Migraciones con Alembic.

- Datos reales (SEED_DEMO=0): al arrancar se aplican las migraciones
  pendientes. Una base creada antes de Alembic (con create_all) se marca en la
  migración base 0001 y desde ahí se actualiza; nunca se borra nada.
- Demo: las tablas se crean del modelo y se marcan en la última migración.
"""
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


def actualizar() -> None:
    """Aplica las migraciones pendientes (producción)."""
    cfg = _config()
    tablas = set(inspect(engine).get_table_names())
    with engine.begin() as con:
        cfg.attributes["connection"] = con
        if tablas and "alembic_version" not in tablas:
            command.stamp(cfg, BASE)
        command.upgrade(cfg, "head")


def marcar_actual() -> None:
    """La base se creó del modelo vigente: queda en la última migración."""
    cfg = _config()
    with engine.begin() as con:
        cfg.attributes["connection"] = con
        command.stamp(cfg, "head")
