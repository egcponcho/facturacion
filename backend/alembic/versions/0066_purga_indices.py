"""Purga de tablas técnicas con índices y llaves

La limpieza periódica borra por fecha de vencimiento: sesiones, desafíos de
dos pasos, permisos de edición e idempotencia tienen índice en esa fecha.
idempotencia.usuario_id pasa a llave foránea (se borra con su usuario).

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-13 12:17:13.153030
"""
from alembic import op
import sqlalchemy as sa


revision = '0066'
down_revision = '0065'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('desafios_dos_pasos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_desafios_dos_pasos_expira'), ['expira'], unique=False)

    with op.batch_alter_table('ediciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ediciones_vence'), ['vence'], unique=False)

    # Claves de usuarios que ya no existen: no sirven a nadie
    op.execute("DELETE FROM idempotencia WHERE usuario_id NOT IN (SELECT id FROM usuarios)")
    with op.batch_alter_table('idempotencia', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_idempotencia_creada_en'), ['creada_en'], unique=False)
        batch_op.create_index(batch_op.f('ix_idempotencia_usuario_id'), ['usuario_id'], unique=False)
        batch_op.create_foreign_key('fk_idempotencia_usuario_id', 'usuarios', ['usuario_id'], ['id'], ondelete='CASCADE')

    with op.batch_alter_table('sesiones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sesiones_expira'), ['expira'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('sesiones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sesiones_expira'))

    with op.batch_alter_table('idempotencia', schema=None) as batch_op:
        batch_op.drop_constraint('fk_idempotencia_usuario_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_idempotencia_usuario_id'))
        batch_op.drop_index(batch_op.f('ix_idempotencia_creada_en'))

    with op.batch_alter_table('ediciones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ediciones_vence'))

    with op.batch_alter_table('desafios_dos_pasos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_desafios_dos_pasos_expira'))

