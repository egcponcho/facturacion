"""Atributos de variante configurables y kits

- atributos_variante: las dimensiones que distinguen las variantes de un
  artículo. Talla y color son de sistema (columnas del artículo, se pueden
  renombrar); la empresa agrega las suyas (material, capacidad, voltaje…).
- articulo_atributos: el valor de cada atributo propio en el artículo, uno
  por fila, de la misma organización que el artículo y el atributo.
- prepacks.tipo: CURVA (tallas de un estilo-color, como hasta ahora) o KIT
  (artículos de cualquier estilo).

Revision ID: 0063
Revises: 0062
Create Date: 2026-10-13 08:45:20.121319
"""
from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0063'
down_revision = '0062'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('atributos_variante',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=60), nullable=False),
    sa.Column('columna', sa.String(length=10), nullable=True),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("columna IS NULL OR columna IN ('talla', 'color')", name='ck_atributos_variante_columna'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_atributos_variante_id_org'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_atributos_variante_org_codigo')
    )
    with op.batch_alter_table('atributos_variante', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_atributos_variante_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('articulo_atributos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('articulo_id', sa.Integer(), nullable=False),
    sa.Column('atributo_id', sa.Integer(), nullable=False),
    sa.Column('valor', sa.String(length=60), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['atributo_id'], ['atributos_variante.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('articulo_id', 'atributo_id', name='uq_articulo_atributos_articulo_atributo')
    )
    with op.batch_alter_table('articulo_atributos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_articulo_atributos_articulo_id'), ['articulo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_articulo_atributos_atributo_id'), ['atributo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_articulo_atributos_organizacion_id'), ['organizacion_id'], unique=False)

    with op.batch_alter_table('articulos', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_articulos_id_org', ['id', 'organizacion_id'])

    with op.batch_alter_table('prepacks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tipo', sa.String(length=10), server_default='CURVA', nullable=False))
        batch_op.create_check_constraint('ck_prepacks_tipo', "tipo IN ('CURVA', 'KIT')")
    with op.batch_alter_table('articulo_atributos', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_articulo_atributos_articulo_id_org', 'articulos', ['articulo_id', 'organizacion_id'],
                                    ['id', 'organizacion_id'])
        batch_op.create_foreign_key('fk_articulo_atributos_atributo_id_org', 'atributos_variante',
                                    ['atributo_id', 'organizacion_id'], ['id', 'organizacion_id'])
    rls(op, 'atributos_variante', 'articulo_atributos')
    # Talla y color, atributos de sistema de cada empresa
    con = op.get_bind()
    for (org,) in con.execute(sa.text("SELECT id FROM organizaciones")).all():
        for codigo, nombre, columna, orden in (("TALLA", "Size", "talla", 1), ("COLOR", "Color", "color", 2)):
            con.execute(sa.text("INSERT INTO atributos_variante (codigo, nombre, columna, orden, activo, organizacion_id) "
                                "VALUES (:c, :n, :col, :o, :a, :org)"), {"c": codigo, "n": nombre, "col": columna, "o": orden,
                                                                          "a": True, "org": org})



def downgrade() -> None:
    with op.batch_alter_table('prepacks', schema=None) as batch_op:
        batch_op.drop_constraint('ck_prepacks_tipo', type_='check')
        batch_op.drop_column('tipo')

    with op.batch_alter_table('articulos', schema=None) as batch_op:
        batch_op.drop_constraint('uq_articulos_id_org', type_='unique')

    with op.batch_alter_table('articulo_atributos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_articulo_atributos_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_articulo_atributos_atributo_id'))
        batch_op.drop_index(batch_op.f('ix_articulo_atributos_articulo_id'))

    op.drop_table('articulo_atributos')
    with op.batch_alter_table('atributos_variante', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_atributos_variante_organizacion_id'))

    op.drop_table('atributos_variante')
