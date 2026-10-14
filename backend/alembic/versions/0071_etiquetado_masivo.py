"""Etiquetado: familias por grupo de artículos y generación masiva.

- grupos_articulos.familia_etiquetado_id: la familia de todos los artículos
  del grupo (un artículo con familia propia la conserva).
- generaciones_etiqueta.pl_id: lote generado desde una lista de empaque.
- generaciones_etiqueta.lote: los lotes de una generación masiva (uno por OC)
  comparten este código.
- plantillas_etiqueta.unidad admite ARTICULO: una etiqueta por artículo
  distinto de la OC aunque se repita en varias líneas.
"""
from alembic import op
import sqlalchemy as sa

revision = '0071'
down_revision = '0070'
branch_labels = None
depends_on = None

UNIDADES_ANTES = "unidad IN ('ORDEN', 'LINEA', 'UNIDAD', 'BULTO', 'MANUAL')"
UNIDADES_AHORA = "unidad IN ('ORDEN', 'LINEA', 'ARTICULO', 'UNIDAD', 'BULTO', 'MANUAL')"


def upgrade() -> None:
    with op.batch_alter_table('grupos_articulos', schema=None) as b:
        b.add_column(sa.Column('familia_etiquetado_id', sa.Integer(), nullable=True))
        b.create_index(b.f('ix_grupos_articulos_familia_etiquetado_id'), ['familia_etiquetado_id'], unique=False)
        b.create_foreign_key('fk_grupos_articulos_familia_etiquetado_id', 'familias_etiquetado', ['familia_etiquetado_id'], ['id'])
        b.create_foreign_key('fk_grupos_articulos_familia_etiquetado_id_org', 'familias_etiquetado',
                             ['familia_etiquetado_id', 'organizacion_id'], ['id', 'organizacion_id'])
    with op.batch_alter_table('generaciones_etiqueta', schema=None) as b:
        b.add_column(sa.Column('pl_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('lote', sa.String(length=36), nullable=True))
        b.create_index(b.f('ix_generaciones_etiqueta_pl_id'), ['pl_id'], unique=False)
        b.create_index(b.f('ix_generaciones_etiqueta_lote'), ['lote'], unique=False)
        b.create_foreign_key('fk_generaciones_etiqueta_pl_id', 'packing_lists', ['pl_id'], ['id'])
        b.create_foreign_key('fk_generaciones_etiqueta_pl_id_org', 'packing_lists', ['pl_id', 'organizacion_id'], ['id', 'organizacion_id'])
    with op.batch_alter_table('plantillas_etiqueta', schema=None) as b:
        b.drop_constraint('ck_plantillas_etiqueta_unidad', type_='check')
        b.create_check_constraint('ck_plantillas_etiqueta_unidad', UNIDADES_AHORA)


def downgrade() -> None:
    op.execute("UPDATE plantillas_etiqueta SET unidad = 'LINEA' WHERE unidad = 'ARTICULO'")
    with op.batch_alter_table('plantillas_etiqueta', schema=None) as b:
        b.drop_constraint('ck_plantillas_etiqueta_unidad', type_='check')
        b.create_check_constraint('ck_plantillas_etiqueta_unidad', UNIDADES_ANTES)
    with op.batch_alter_table('generaciones_etiqueta', schema=None) as b:
        b.drop_constraint('fk_generaciones_etiqueta_pl_id_org', type_='foreignkey')
        b.drop_constraint('fk_generaciones_etiqueta_pl_id', type_='foreignkey')
        b.drop_index(b.f('ix_generaciones_etiqueta_lote'))
        b.drop_index(b.f('ix_generaciones_etiqueta_pl_id'))
        b.drop_column('lote')
        b.drop_column('pl_id')
    with op.batch_alter_table('grupos_articulos', schema=None) as b:
        b.drop_constraint('fk_grupos_articulos_familia_etiquetado_id_org', type_='foreignkey')
        b.drop_constraint('fk_grupos_articulos_familia_etiquetado_id', type_='foreignkey')
        b.drop_index(b.f('ix_grupos_articulos_familia_etiquetado_id'))
        b.drop_column('familia_etiquetado_id')
