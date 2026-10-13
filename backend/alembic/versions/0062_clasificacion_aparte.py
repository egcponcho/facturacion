"""Productos: el trabajo de clasificación en su propia tabla

productos guardaba en la misma fila la ficha técnica, el resultado aprobado y
todo el trabajo de clasificar (sugerencias del motor, propuesta del
proveedor, evidencia, análisis, opinión de la IA, revisión). Ese trabajo pasa
a clasificaciones_producto (1:1, misma organización que el producto); en el
producto quedan la ficha, el HS6 y la línea SAC aprobados.

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-13 00:00:00
"""
from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0062'
down_revision = '0061'
branch_labels = None
depends_on = None

CAMPOS = ('sugerido', 'propuesta', 'sac_sugerido', 'version_arancel_id', 'evidencia', 'confianza', 'fuente', 'perfil',
          'analisis', 'alertas_ok', 'observaciones', 'resolucion', 'opinion_ia', 'revisado_por_id', 'revisado_en')


def upgrade() -> None:
    op.create_table('clasificaciones_producto',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('producto_id', sa.Integer(), nullable=False),
    sa.Column('sugerido', sa.String(length=14), nullable=True),
    sa.Column('propuesta', sa.String(length=14), nullable=True),
    sa.Column('sac_sugerido', sa.String(length=10), nullable=True),
    sa.Column('version_arancel_id', sa.Integer(), nullable=True),
    sa.Column('evidencia', sa.JSON(), nullable=True),
    sa.Column('confianza', sa.String(length=10), nullable=True),
    sa.Column('fuente', sa.String(length=12), nullable=True),
    sa.Column('perfil', sa.String(length=200), nullable=True),
    sa.Column('analisis', sa.JSON(), nullable=True),
    sa.Column('alertas_ok', sa.JSON(), nullable=False),
    sa.Column('observaciones', sa.String(length=2000), nullable=True),
    sa.Column('resolucion', sa.String(length=200), nullable=True),
    sa.Column('opinion_ia', sa.JSON(), nullable=True),
    sa.Column('revisado_por_id', sa.Integer(), nullable=True),
    sa.Column('revisado_en', sa.DateTime(), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], name='fk_clasificaciones_producto_producto_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['revisado_por_id'], ['usuarios.id'], name='fk_clasificaciones_producto_revisado_por'),
    sa.ForeignKeyConstraint(['version_arancel_id'], ['versiones_dataset.id'], name='fk_clasificaciones_producto_version'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('clasificaciones_producto', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_clasificaciones_producto_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_clasificaciones_producto_perfil'), ['perfil'], unique=False)
        batch_op.create_index(batch_op.f('ix_clasificaciones_producto_producto_id'), ['producto_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_clasificaciones_producto_revisado_en'), ['revisado_en'], unique=False)
        batch_op.create_index(batch_op.f('ix_clasificaciones_producto_revisado_por_id'), ['revisado_por_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_clasificaciones_producto_version_arancel_id'), ['version_arancel_id'], unique=False)

    columnas = ", ".join(CAMPOS)
    op.execute(f"INSERT INTO clasificaciones_producto (producto_id, organizacion_id, {columnas}) "
               f"SELECT id, organizacion_id, {', '.join('COALESCE(alertas_ok, ' + repr('[]') + ')' if c == 'alertas_ok' else c for c in CAMPOS)} "
               f"FROM productos")

    with op.batch_alter_table('productos', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_productos_id_org', ['id', 'organizacion_id'])
    with op.batch_alter_table('clasificaciones_producto', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_clasificaciones_producto_producto_id_org', 'productos', ['producto_id', 'organizacion_id'],
                                    ['id', 'organizacion_id'])
    rls(op, 'clasificaciones_producto')

    with op.batch_alter_table('productos', schema=None) as batch_op:
        batch_op.drop_constraint('fk_productos_version', type_='foreignkey')
        for c in CAMPOS:
            batch_op.drop_column(c)


def downgrade() -> None:
    with op.batch_alter_table('productos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('sugerido', sa.String(length=14), nullable=True))
        batch_op.add_column(sa.Column('propuesta', sa.String(length=14), nullable=True))
        batch_op.add_column(sa.Column('sac_sugerido', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('version_arancel_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('evidencia', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('confianza', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('fuente', sa.String(length=12), nullable=True))
        batch_op.add_column(sa.Column('perfil', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('analisis', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('alertas_ok', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('observaciones', sa.String(length=2000), nullable=True))
        batch_op.add_column(sa.Column('resolucion', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('opinion_ia', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('revisado_por_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('revisado_en', sa.DateTime(), nullable=True))
    for c in CAMPOS:
        op.execute(f"UPDATE productos SET {c} = (SELECT x.{c} FROM clasificaciones_producto x WHERE x.producto_id = productos.id)")
    op.execute("UPDATE productos SET alertas_ok = '[]' WHERE alertas_ok IS NULL")
    with op.batch_alter_table('productos', schema=None) as batch_op:
        batch_op.alter_column('alertas_ok', existing_type=sa.JSON(), nullable=False)
        batch_op.create_foreign_key('fk_productos_version', 'versiones_dataset', ['version_arancel_id'], ['id'])
        batch_op.create_foreign_key('fk_productos_revisado_por_id', 'usuarios', ['revisado_por_id'], ['id'])
    op.drop_table('clasificaciones_producto')
    with op.batch_alter_table('productos', schema=None) as batch_op:
        batch_op.drop_constraint('uq_productos_id_org', type_='unique')
