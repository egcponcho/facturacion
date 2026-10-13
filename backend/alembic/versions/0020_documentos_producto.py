"""Fichas técnicas del producto (SDS, TDS, COA)

Evidencia técnica de la capa de la empresa: sus datos son hechos para la
ficha, nunca una fuente arancelaria.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-08 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'producto_documentos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(length=4), nullable=False),
        sa.Column('nombre', sa.String(length=300), nullable=False),
        sa.Column('ruta', sa.String(length=500), nullable=False),
        sa.Column('tipo_mime', sa.String(length=60), nullable=False),
        sa.Column('tamano', sa.Integer(), nullable=False),
        sa.Column('emisor', sa.String(length=200), nullable=True),
        sa.Column('fecha_documento', sa.Date(), nullable=True),
        sa.Column('datos', sa.JSON(), nullable=False),
        sa.Column('subido_por', sa.Integer(), nullable=True),
        sa.Column('subido_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subido_por'], ['usuarios.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('producto_documentos', schema=None) as b:
        b.create_index('ix_producto_documentos_producto_id', ['producto_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('producto_documentos', schema=None) as b:
        b.drop_index('ix_producto_documentos_producto_id')
    op.drop_table('producto_documentos')
