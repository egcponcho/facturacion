"""Los atributos del paquete 02 no son datos oficiales; términos de búsqueda

atributos_def.origen 'OFICIAL' (paquete 02 del motor) pasa a 'PAQUETE': los
atributos, opciones y ámbitos son configuración del motor, no dato arancelario
publicado. Las categorías técnicas de químicos y materias primas se agregan
al arrancar (motor_tecnico.json), sin pisar lo editado.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-08 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE atributos_def SET origen = 'PAQUETE' WHERE origen = 'OFICIAL'"))
    # Términos de búsqueda (palabras del texto oficial): solo ordenan candidatos
    with op.batch_alter_table('categorias_producto', schema=None) as b:
        b.add_column(sa.Column('terminos', sa.String(length=400), nullable=True))
    with op.batch_alter_table('atributo_opciones', schema=None) as b:
        b.add_column(sa.Column('terminos', sa.String(length=400), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('atributo_opciones', schema=None) as b:
        b.drop_column('terminos')
    with op.batch_alter_table('categorias_producto', schema=None) as b:
        b.drop_column('terminos')
    op.get_bind().execute(sa.text("UPDATE atributos_def SET origen = 'OFICIAL' WHERE origen = 'PAQUETE'"))
