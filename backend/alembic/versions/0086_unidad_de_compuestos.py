"""Compuestos genéricos: la unidad de los packs y kits se configura

- unidades_medida.compuesto: la unidad es solo para packs y kits (un artículo
  simple no la usa). La caja de prepack de fábrica (CJ) queda marcada; la
  empresa marca las suyas (display, estuche, set…).

Revision ID: 0086
Revises: 0085
Create Date: 2026-10-20 17:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0086'
down_revision = '0085'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('unidades_medida', schema=None) as b:
        b.add_column(sa.Column('compuesto', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.get_bind().execute(sa.text("UPDATE unidades_medida SET compuesto = :v WHERE codigo = 'CJ'"), {"v": True})


def downgrade() -> None:
    with op.batch_alter_table('unidades_medida', schema=None) as b:
        b.drop_column('compuesto')
