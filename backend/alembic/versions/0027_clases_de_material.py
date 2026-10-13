"""Clases de material configurables

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-07 16:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clases_material",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nombre", sa.String(length=80), nullable=False),
        sa.Column("palabras", sa.String(length=1000), nullable=True),
        sa.Column("texto_aduana", sa.String(length=60), nullable=True),
        sa.Column("origen", sa.String(length=10), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )


def downgrade() -> None:
    op.drop_table("clases_material")
