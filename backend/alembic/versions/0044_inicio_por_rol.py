"""Página de inicio por rol

Cada rol puede ocultar paneles de la página de inicio (indicadores, envíos,
desempeño…). Vacío: los ve todos, como hasta ahora.

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0044'
down_revision = '0043'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("roles") as b:
        b.add_column(sa.Column("inicio_oculto", sa.JSON(), nullable=True))
    op.execute("UPDATE roles SET inicio_oculto = '[]'")
    with op.batch_alter_table("roles") as b:
        b.alter_column("inicio_oculto", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("roles") as b:
        b.drop_column("inicio_oculto")
