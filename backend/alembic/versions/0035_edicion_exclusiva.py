"""Edición exclusiva: quién está editando cada documento

Revision ID: 0035
Revises: 0034
Create Date: 2026-10-08 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0035'
down_revision = '0034'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ediciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entidad", sa.String(30), nullable=False),
        sa.Column("entidad_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("desde", sa.DateTime(), nullable=False),
        sa.Column("vence", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("entidad", "entidad_id"),
    )
    op.create_index("ix_ediciones_usuario_id", "ediciones", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_ediciones_usuario_id", "ediciones")
    op.drop_table("ediciones")
