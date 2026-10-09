"""Campos propios de la empresa

Columna extra (JSON) en los registros que pueden llevar campos propios:
artículos, proveedores, sociedades, centros, marcas, transportistas, órdenes
de compra y facturas. Las definiciones viven en la configuración de la
empresa.

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0045'
down_revision = '0044'
branch_labels = None
depends_on = None

TABLAS = ("articulos", "proveedores", "sociedades", "centros", "marcas", "transportistas", "ordenes_compra", "facturas")


def upgrade() -> None:
    for tabla in TABLAS:
        with op.batch_alter_table(tabla) as b:
            b.add_column(sa.Column("extra", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    for tabla in TABLAS:
        with op.batch_alter_table(tabla) as b:
            b.drop_column("extra")
