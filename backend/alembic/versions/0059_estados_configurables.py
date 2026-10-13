"""Estados configurables por empresa

Cada empresa decide cómo se leen los estados de sus documentos (etiqueta),
su color y su orden en filtros y listas. Los códigos siguen siendo fijos: el
sistema decide con ellos (core/estados.py).

Revision ID: 0059
Revises: 0058
Create Date: 2026-10-13 07:41:22.930461
"""
from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0059'
down_revision = '0058'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('estados_documento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('documento', sa.String(length=20), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('etiqueta', sa.String(length=60), nullable=True),
    sa.Column('tono', sa.String(length=10), nullable=True),
    sa.Column('orden', sa.Integer(), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("documento IN ('oc', 'avance', 'factura', 'pl', 'embarque', 'producto', 'documento', 'cobro', 'pago')", name='ck_estados_documento_documento'),
    sa.CheckConstraint("tono IS NULL OR tono IN ('neutro', 'info', 'ok', 'aviso', 'error')", name='ck_estados_documento_tono'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'documento', 'codigo', name='uq_estados_documento_org_documento_codigo')
    )
    with op.batch_alter_table('estados_documento', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_estados_documento_organizacion_id'), ['organizacion_id'], unique=False)
    rls(op, 'estados_documento')



def downgrade() -> None:
    with op.batch_alter_table('estados_documento', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_estados_documento_organizacion_id'))

    op.drop_table('estados_documento')
