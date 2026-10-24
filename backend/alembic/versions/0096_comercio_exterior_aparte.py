"""Productos: la ficha de comercio exterior en su propia tabla

productos guardaba en la misma fila el producto del catálogo (código, nombre,
unidad, familia, proveedor) y su ficha de comercio exterior (tipo, ficha
técnica, descripciones aduanera y comercial, origen y procedencia, estado de
revisión, versión de la ficha, HS6 y línea SAC aprobados, notas). La ficha
pasa a producto_comex (1:1, misma organización que el producto); en productos
queda solo lo del catálogo. Como 0062 hizo con el trabajo de clasificación.

Además, familia_comex: la sección de comercio exterior de la familia (la
categoría aduanera con que empiezan las fichas de sus productos).

Revision ID: 0096
Revises: 0095
Create Date: 2026-10-24 00:00:00
"""
import sqlalchemy as sa

from alembic import op
from app.instalacion.esquema import rls

revision = '0096'
down_revision = '0095'
branch_labels = None
depends_on = None

CAMPOS = ('tipo', 'ficha', 'descripcion_aduana', 'descripcion_comercial', 'pais_origen', 'pais_procedencia',
          'ficha_completa', 'faltan', 'version_ficha', 'vigente_desde', 'estado', 'codigo', 'sac_codigo', 'notas')


def _columnas():
    return [sa.Column('tipo', sa.String(length=30), nullable=True),
            sa.Column('ficha', sa.JSON(), nullable=False),
            sa.Column('descripcion_aduana', sa.String(length=400), nullable=True),
            sa.Column('descripcion_comercial', sa.String(length=300), nullable=True),
            sa.Column('pais_origen', sa.String(length=2), nullable=True),
            sa.Column('pais_procedencia', sa.String(length=2), nullable=True),
            sa.Column('ficha_completa', sa.Boolean(), nullable=False),
            sa.Column('faltan', sa.JSON(), nullable=False),
            sa.Column('version_ficha', sa.Integer(), nullable=False),
            sa.Column('vigente_desde', sa.Date(), nullable=True),
            sa.Column('estado', sa.String(length=12), nullable=False),
            sa.Column('codigo', sa.String(length=14), nullable=True),
            sa.Column('sac_codigo', sa.String(length=10), nullable=True),
            sa.Column('notas', sa.String(length=1000), nullable=True)]


def upgrade() -> None:
    op.create_table(
        'producto_comex',
        sa.Column('producto_id', sa.Integer(), autoincrement=False, nullable=False),
        *_columnas(),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], name='fk_producto_comex_producto_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('producto_id'))
    with op.batch_alter_table('producto_comex', schema=None) as b:
        b.create_index(b.f('ix_producto_comex_organizacion_id'), ['organizacion_id'], unique=False)
        b.create_index(b.f('ix_producto_comex_estado'), ['estado'], unique=False)

    op.execute(
        f"INSERT INTO producto_comex (producto_id, organizacion_id, {', '.join(CAMPOS)}) "
        "SELECT id, organizacion_id, tipo, COALESCE(ficha, '{}'), descripcion_aduana, descripcion_comercial, pais_origen, "
        "pais_procedencia, COALESCE(ficha_completa, " + ("false" if op.get_bind().dialect.name == "postgresql" else "0") + "), "
        "COALESCE(faltan, '[]'), COALESCE(version_ficha, 1), vigente_desde, COALESCE(estado, 'borrador'), codigo, "
        "sac_codigo, notas FROM productos")

    with op.batch_alter_table('producto_comex', schema=None) as b:
        b.create_foreign_key('fk_producto_comex_producto_id_org', 'productos', ['producto_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
    rls(op, 'producto_comex')

    # La sección de comercio exterior de la familia: la categoría aduanera con que empiezan sus fichas
    op.create_table(
        'familia_comex',
        sa.Column('familia_id', sa.Integer(), nullable=False),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        sa.Column('categoria', sa.String(length=40), nullable=True),
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name='fk_familia_comex_organizacion_id_organizaciones'),
        sa.ForeignKeyConstraint(['familia_id', 'organizacion_id'], ['grupos_producto.id', 'grupos_producto.organizacion_id'],
                                ondelete='CASCADE', name='fk_familia_comex_familia_org'),
        sa.ForeignKeyConstraint(['categoria'], ['categorias_producto.codigo'], name='fk_familia_comex_categoria',
                                onupdate='CASCADE', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('familia_id', name='pk_familia_comex'))
    op.create_index('ix_familia_comex_organizacion_id', 'familia_comex', ['organizacion_id'], unique=False)
    rls(op, 'familia_comex')

    indices = {i['name'] for i in sa.inspect(op.get_bind()).get_indexes('productos')}
    with op.batch_alter_table('productos', schema=None) as b:
        if 'ix_productos_estado' in indices:
            b.drop_index('ix_productos_estado')
        for c in CAMPOS:
            b.drop_column(c)


def downgrade() -> None:
    op.drop_index('ix_familia_comex_organizacion_id', table_name='familia_comex')
    op.drop_table('familia_comex')
    with op.batch_alter_table('productos', schema=None) as b:
        for c in _columnas():
            c.nullable = True
            b.add_column(c)
    for c in CAMPOS:
        op.execute(f"UPDATE productos SET {c} = (SELECT x.{c} FROM producto_comex x WHERE x.producto_id = productos.id)")
    op.execute("UPDATE productos SET ficha = '{}' WHERE ficha IS NULL")
    op.execute("UPDATE productos SET faltan = '[]' WHERE faltan IS NULL")
    op.execute("UPDATE productos SET estado = 'borrador' WHERE estado IS NULL")
    op.execute("UPDATE productos SET version_ficha = 1 WHERE version_ficha IS NULL")
    op.execute(sa.text("UPDATE productos SET ficha_completa = :no WHERE ficha_completa IS NULL").bindparams(no=False))
    tipos = {c.name: c.type for c in _columnas()}
    with op.batch_alter_table('productos', schema=None) as b:
        for c in ('ficha', 'faltan', 'estado', 'version_ficha', 'ficha_completa'):
            b.alter_column(c, existing_type=tipos[c], nullable=False)
        b.create_index('ix_productos_estado', ['estado'], unique=False)
    op.drop_table('producto_comex')
