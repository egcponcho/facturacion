"""Traducciones de los textos del catálogo

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-08 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "traducciones_catalogo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("texto", sa.String(length=400), nullable=False),
        sa.Column("idioma", sa.String(length=5), nullable=False),
        sa.Column("traduccion", sa.String(length=400), nullable=False),
        sa.Column("origen", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("texto", "idioma"),
    )
    op.create_index(op.f("ix_traducciones_catalogo_idioma"), "traducciones_catalogo", ["idioma"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_traducciones_catalogo_idioma"), table_name="traducciones_catalogo")
    op.drop_table("traducciones_catalogo")
