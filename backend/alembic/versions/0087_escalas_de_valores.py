"""Escalas de valores de cualquier atributo de variante

- escalas_talla.atributo: el atributo de variante cuyos valores ordena la
  escala (tallas, presentaciones, concentraciones…). Las existentes son de
  talla (TALLA).

Revision ID: 0087
Revises: 0086
Create Date: 2026-10-21 09:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0087'
down_revision = '0086'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('escalas_talla', schema=None) as b:
        b.add_column(sa.Column('atributo', sa.String(length=20), server_default='TALLA', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('escalas_talla', schema=None) as b:
        b.drop_column('atributo')
