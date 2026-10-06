"""Tipo de fuente de las notas: texto oficial vs guía

La columna notas_sac.fuente (oficial | resumen | base | manual | archivo)
mezclaba texto legal con resúmenes propios. La reemplaza tipo_fuente:
OFFICIAL_LEGAL | OFFICIAL_TARIFF | OFFICIAL_NATIONAL (texto publicado),
CLASSIFIER_GUIDANCE (resúmenes del clasificador), INTERNAL_GUIDANCE (notas
propias o archivos sin fuente oficial) y COMPANY_HISTORY.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-07 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('notas_sac', schema=None) as b:
        b.add_column(sa.Column('tipo_fuente', sa.String(length=24), nullable=True))
    con = op.get_bind()
    con.execute(sa.text("UPDATE notas_sac SET tipo_fuente = CASE "
                        "WHEN fuente = 'oficial' THEN 'OFFICIAL_LEGAL' "
                        "WHEN fuente IN ('resumen', 'guia') OR ambito = 'explicativa' THEN 'CLASSIFIER_GUIDANCE' "
                        "ELSE 'INTERNAL_GUIDANCE' END"))
    with op.batch_alter_table('notas_sac', schema=None) as b:
        b.alter_column('tipo_fuente', existing_type=sa.String(length=24), nullable=False)
        b.drop_column('fuente')


def downgrade() -> None:
    with op.batch_alter_table('notas_sac', schema=None) as b:
        b.add_column(sa.Column('fuente', sa.String(length=12), nullable=True))
    con = op.get_bind()
    con.execute(sa.text("UPDATE notas_sac SET fuente = CASE WHEN tipo_fuente LIKE 'OFFICIAL_%' THEN 'oficial' "
                        "WHEN tipo_fuente = 'CLASSIFIER_GUIDANCE' THEN 'resumen' ELSE 'manual' END"))
    with op.batch_alter_table('notas_sac', schema=None) as b:
        b.alter_column('fuente', existing_type=sa.String(length=12), nullable=False)
        b.drop_column('tipo_fuente')
