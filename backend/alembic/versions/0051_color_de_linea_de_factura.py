"""Color de la línea de factura tan largo como el de la línea de OC

La línea de factura copia el color de la posición de la OC (60 caracteres),
pero lo guardaba en 40: en PostgreSQL, facturar una posición con un color
más largo fallaba. Pasa a 60.

Revision ID: 0051
Revises: 0050
Create Date: 2026-10-10 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0051'
down_revision = '0050'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('factura_lineas', schema=None) as batch_op:
        batch_op.alter_column('color', existing_type=sa.String(length=40), type_=sa.String(length=60), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('factura_lineas', schema=None) as batch_op:
        batch_op.alter_column('color', existing_type=sa.String(length=60), type_=sa.String(length=40), existing_nullable=True)
