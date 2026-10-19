"""Etiquetado: a qué tipos de empaque se aplica un tipo de etiqueta de bulto

- tipos_etiqueta_empaques (tipo_etiqueta_id, tipo_empaque_id): la etiqueta
  del inner no es la de la caja ni la del pallet. Un tipo sin filas se aplica
  a todos los empaques, como hasta ahora.

Solo agrega una tabla vacía: ningún dato existente cambia ni se convierte.

Revision ID: 0079
Revises: 0078
Create Date: 2026-10-20 09:00:00
"""
from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls

revision = '0079'
down_revision = '0078'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tipos_etiqueta_empaques',
        sa.Column('tipo_etiqueta_id', sa.Integer(), nullable=False),
        sa.Column('tipo_empaque_id', sa.Integer(), nullable=False),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name='fk_tipos_etiqueta_empaques_organizacion_id_organizaciones'),
        sa.ForeignKeyConstraint(['tipo_etiqueta_id'], ['tipos_etiqueta.id'], name='fk_tipos_etiqueta_empaques_tipo_etiqueta_id_tipos_etiqueta',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tipo_empaque_id'], ['tipos_empaque.id'], name='fk_tipos_etiqueta_empaques_tipo_empaque_id_tipos_empaque',
                                ondelete='CASCADE'),
        # El tipo de etiqueta y el de empaque son de la misma organización que la fila
        sa.ForeignKeyConstraint(['tipo_etiqueta_id', 'organizacion_id'], ['tipos_etiqueta.id', 'tipos_etiqueta.organizacion_id'],
                                name='fk_tipos_etiqueta_empaques_tipo_etiqueta_id_org', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tipo_empaque_id', 'organizacion_id'], ['tipos_empaque.id', 'tipos_empaque.organizacion_id'],
                                name='fk_tipos_etiqueta_empaques_tipo_empaque_id_org', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('tipo_etiqueta_id', 'tipo_empaque_id', name='pk_tipos_etiqueta_empaques'),
    )
    with op.batch_alter_table('tipos_etiqueta_empaques', schema=None) as b:
        b.create_index(b.f('ix_tipos_etiqueta_empaques_organizacion_id'), ['organizacion_id'], unique=False)
        b.create_index(b.f('ix_tipos_etiqueta_empaques_tipo_empaque_id'), ['tipo_empaque_id'], unique=False)
    rls(op, 'tipos_etiqueta_empaques')


def downgrade() -> None:
    op.drop_table('tipos_etiqueta_empaques')
