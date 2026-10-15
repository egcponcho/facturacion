"""Etiquetado: lo que se revisó de cada registro del trabajo

- trabajo_etiqueta_registros.revisado: los valores que lee su diseño (más la
  versión del diseño y la cantidad) cuando se revisó el trabajo. Al generar se
  comparan con los actuales: si lo que se va a imprimir cambió desde la
  revisión (un UPC, el contenido de una caja, el diseño), se avisa con la
  diferencia en vez de imprimir algo distinto de lo revisado.

Revision ID: 0077
Revises: 0076
Create Date: 2026-10-18 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0077'
down_revision = '0076'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('trabajo_etiqueta_registros', schema=None) as b:
        b.add_column(sa.Column('revisado', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('trabajo_etiqueta_registros', schema=None) as b:
        b.drop_column('revisado')
