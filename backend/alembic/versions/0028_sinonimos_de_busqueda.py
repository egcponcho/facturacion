"""Sinónimos de búsqueda en el texto oficial del arancel

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-07 17:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sinonimos_busqueda",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("palabra", sa.String(length=60), nullable=False),
        sa.Column("equivale", sa.String(length=300), nullable=False),
        sa.Column("origen", sa.String(length=10), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("palabra"),
    )


def downgrade() -> None:
    op.drop_table("sinonimos_busqueda")
