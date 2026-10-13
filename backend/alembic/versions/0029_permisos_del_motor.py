"""Permisos propios del motor de clasificación y roles sugeridos

Los roles que editaban el arancel también configuraban el motor; ahora el
motor tiene sus permisos («clasificacion.ver» y «clasificacion.configurar»)
y se agregan los roles sugeridos de especialista y comprador.

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-07 19:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None

EQUIVALE = {"aranceles.ver": "clasificacion.ver", "aranceles.editar": "clasificacion.configurar"}
SUGERIDOS = [
    ("Classification specialist", "Configures product families, attributes and rules; reviews, approves and returns technical sheets.",
     ["oc.ver", "producto.ver", "producto.ficha", "producto.clasificar", "aranceles.ver", "clasificacion.ver",
      "clasificacion.configurar", "seguimiento.ver"]),
    ("Buyer", "Creates items and fills their technical sheets; sends them to review.",
     ["oc.ver", "producto.ver", "producto.ficha", "producto.crear", "seguimiento.ver"]),
]


def _lista(valor) -> list:
    if isinstance(valor, str):
        return json.loads(valor or "[]")
    return list(valor or [])


def upgrade() -> None:
    con = op.get_bind()
    roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("nombre", sa.String), sa.column("descripcion", sa.String),
                     sa.column("tipo", sa.String), sa.column("permisos", sa.JSON), sa.column("sistema", sa.Boolean),
                     sa.column("activo", sa.Boolean))
    nombres = set()
    for rid, nombre, permisos in con.execute(sa.select(roles.c.id, roles.c.nombre, roles.c.permisos)).all():
        nombres.add((nombre or "").lower())
        actuales = _lista(permisos)
        nuevos = sorted(set(actuales) | {EQUIVALE[p] for p in actuales if p in EQUIVALE})
        if nuevos != sorted(actuales):
            con.execute(roles.update().where(roles.c.id == rid).values(permisos=nuevos))
    for nombre, desc, permisos in SUGERIDOS:
        if nombre.lower() not in nombres:
            con.execute(roles.insert().values(nombre=nombre, descripcion=desc, tipo="interno", permisos=permisos,
                                              sistema=False, activo=True))


def downgrade() -> None:
    con = op.get_bind()
    roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("permisos", sa.JSON))
    for rid, permisos in con.execute(sa.select(roles.c.id, roles.c.permisos)).all():
        actuales = _lista(permisos)
        quitar = set(EQUIVALE.values())
        if quitar & set(actuales):
            con.execute(roles.update().where(roles.c.id == rid).values(permisos=[p for p in actuales if p not in quitar]))
