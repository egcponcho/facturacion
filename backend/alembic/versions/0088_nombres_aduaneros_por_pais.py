"""Nombres aduaneros por país

- paises_arancel.nomenclatura y paises_arancel.nombre_derecho: cómo llama el
  país a su nomenclatura arancelaria y a su derecho de importación en los
  documentos. Hasta ahora estaban fijos («SAC», «DAI»); los países que ya
  están cargados los conservan.
- paises.nombre_id_fiscal: cómo se llama la identificación fiscal en el país
  (antes el documento decía «NIT / RUC» para todos). Se completa para los
  países de Centroamérica y Panamá, los únicos que la demostración y los
  documentos usaban.

Revision ID: 0088
Revises: 0087
Create Date: 2026-10-22 09:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0088'
down_revision = '0087'
branch_labels = None
depends_on = None

ID_FISCAL = {"GT": "NIT", "SV": "NIT", "HN": "RTN", "NI": "RUC", "CR": "Cédula jurídica", "PA": "RUC"}


def upgrade() -> None:
    with op.batch_alter_table('paises_arancel', schema=None) as b:
        b.add_column(sa.Column('nomenclatura', sa.String(length=20), nullable=True))
        b.add_column(sa.Column('nombre_derecho', sa.String(length=20), nullable=True))
    with op.batch_alter_table('paises', schema=None) as b:
        b.add_column(sa.Column('nombre_id_fiscal', sa.String(length=30), nullable=True))
    # Lo que los documentos mostraban fijo, ahora como dato de los países ya cargados
    op.execute("UPDATE paises_arancel SET nomenclatura = 'SAC', nombre_derecho = 'DAI'")
    paises = sa.table('paises', sa.column('codigo', sa.String), sa.column('nombre_id_fiscal', sa.String))
    for codigo, nombre in ID_FISCAL.items():
        op.execute(paises.update().where(paises.c.codigo == codigo).values(nombre_id_fiscal=nombre))


def downgrade() -> None:
    with op.batch_alter_table('paises', schema=None) as b:
        b.drop_column('nombre_id_fiscal')
    with op.batch_alter_table('paises_arancel', schema=None) as b:
        b.drop_column('nombre_derecho')
        b.drop_column('nomenclatura')
