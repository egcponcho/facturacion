"""Familias de producto en borrador

Una familia nueva nace en borrador: se arma y se prueba sin que la ficha la
ofrezca ni cambie artículos reales, y se publica cuando está lista. Las que ya
existen quedan publicadas.

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-07 22:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dominios_clasificacion") as t:
        t.add_column(sa.Column("estado", sa.String(length=10), nullable=False, server_default="PUBLICADA"))


def downgrade() -> None:
    with op.batch_alter_table("dominios_clasificacion") as t:
        t.drop_column("estado")
