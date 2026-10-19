"""Etiquetado: anular una ejecución y reimprimir, con motivo

- generaciones_etiqueta.anulada_en / anulada_por / motivo_anulacion: la
  ejecución se anuló (etiquetas dañadas, datos equivocados…). Ya no se
  descarga ni se confirma como impresa, y sus registros del trabajo vuelven a
  quedar pendientes para generarlos de nuevo. Sus números de serie quedan
  usados (no se reutilizan).
- generaciones_etiqueta.reimpresiones: cada reimpresión (copias idénticas de
  todo el lote o de algunos grupos y rangos) con quién, cuándo, cuántas y por qué.

Solo agrega columnas: los lotes existentes quedan vigentes y sin reimpresiones.

Revision ID: 0078
Revises: 0077
Create Date: 2026-10-19 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0078'
down_revision = '0077'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('generaciones_etiqueta', schema=None) as b:
        b.add_column(sa.Column('anulada_en', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('anulada_por', sa.Integer(), nullable=True))
        b.add_column(sa.Column('motivo_anulacion', sa.String(length=300), nullable=True))
        b.add_column(sa.Column('reimpresiones', sa.JSON(), nullable=True))
        b.create_foreign_key('fk_generaciones_etiqueta_anulada_por_usuarios', 'usuarios', ['anulada_por'], ['id'])
        b.create_check_constraint('ck_generaciones_etiqueta_anulada',
                                  '(anulada_en IS NULL) = (motivo_anulacion IS NULL)')


def downgrade() -> None:
    with op.batch_alter_table('generaciones_etiqueta', schema=None) as b:
        b.drop_constraint('ck_generaciones_etiqueta_anulada', type_='check')
        b.drop_constraint('fk_generaciones_etiqueta_anulada_por_usuarios', type_='foreignkey')
        b.drop_column('reimpresiones')
        b.drop_column('motivo_anulacion')
        b.drop_column('anulada_por')
        b.drop_column('anulada_en')
