"""Versiones de datos por tabla: cuántas veces cambió cada tabla (por
organización; 0 = compartido). Con ellas el servidor responde 304 sin
consultar cuando nada de lo que lee una pantalla cambió, y el canal de
cambios avisa solo de lo que cambió (app/core/cambios.py). Tabla técnica,
sin datos de negocio: empieza vacía (sin versión = 0).

Revision ID: 0075
Revises: 0074
Create Date: 2026-10-16 09:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0075'
down_revision = '0074'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'versiones_datos',
        sa.Column('tabla', sa.String(length=80), nullable=False),
        sa.Column('ambito', sa.Integer(), nullable=False),
        sa.Column('version', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('tabla', 'ambito', name='pk_versiones_datos'),
    )


def downgrade() -> None:
    op.drop_table('versiones_datos')
