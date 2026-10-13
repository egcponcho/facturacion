"""Datos ocultos por rol

roles.datos_ocultos: grupos de datos que el rol no ve (precios, códigos
internos, fechas internas, liberaciones, impuestos, contactos). El rol de
fábrica del proveedor deja de ver las fechas en tienda, el detalle de las
liberaciones y las tasas de impuestos; se puede cambiar en Usuarios y accesos.

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-09 00:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("roles", schema=None) as b:
        b.add_column(sa.Column("datos_ocultos", sa.JSON(), nullable=True))
    con = op.get_bind()
    con.execute(sa.text("UPDATE roles SET datos_ocultos = :v"), {"v": "[]"})
    con.execute(sa.text("UPDATE roles SET datos_ocultos = :v WHERE tipo = 'proveedor' AND sistema = :s"),
                {"v": json.dumps(["fechas_internas", "liberaciones", "impuestos"]), "s": True})
    with op.batch_alter_table("roles", schema=None) as b:
        b.alter_column("datos_ocultos", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("roles", schema=None) as b:
        b.drop_column("datos_ocultos")
