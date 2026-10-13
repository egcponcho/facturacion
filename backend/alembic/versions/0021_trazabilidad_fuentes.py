"""Trazabilidad de las fuentes oficiales

fuentes_oficiales gana documento (el documento o dataset oficial exacto),
verificado_en y verificado_por. La fecha se toma del texto de verificación ya
cargado («Verified 2026-10-01»); sin fecha la fuente queda sin verificar y no
respalda datos oficiales hasta que alguien la verifique.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-08 18:00:00
"""
import re
from datetime import date

from alembic import op
import sqlalchemy as sa


revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('fuentes_oficiales', schema=None) as b:
        b.add_column(sa.Column('documento', sa.String(length=300), nullable=True))
        b.add_column(sa.Column('verificado_en', sa.Date(), nullable=True))
        b.add_column(sa.Column('verificado_por', sa.String(length=120), nullable=True))
    con = op.get_bind()
    for fid, texto in con.execute(sa.text("SELECT id, verificacion FROM fuentes_oficiales")).all():
        m = re.search(r"(\d{4}-\d{2}-\d{2})", texto or "")
        if m:
            con.execute(sa.text("UPDATE fuentes_oficiales SET verificado_en = :d WHERE id = :i"),
                        {"d": date.fromisoformat(m.group(1)), "i": fid})


def downgrade() -> None:
    with op.batch_alter_table('fuentes_oficiales', schema=None) as b:
        b.drop_column('verificado_por')
        b.drop_column('verificado_en')
        b.drop_column('documento')
