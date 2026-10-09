"""Alcance de los datos de cada usuario

Un usuario puede ver los datos de varios proveedores (p. ej. un agente que
representa a varios) y quedar limitado a algunas sociedades. Vacío: sin
límite, como hasta ahora.

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.add_column(sa.Column("alcance", sa.JSON(), nullable=True))
    op.execute("UPDATE usuarios SET alcance = '{}'")
    with op.batch_alter_table("usuarios") as b:
        b.alter_column("alcance", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as b:
        b.drop_column("alcance")
