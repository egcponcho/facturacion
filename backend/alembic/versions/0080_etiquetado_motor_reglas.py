"""Etiquetado como un motor de reglas (igual que la clasificación, sin base oficial)

La empresa decide todo: familias → categorías → reglas.

- categorias_etiquetado: categorías dentro de una familia (sandalias, botas…),
  reconocidas por condiciones sobre los datos del artículo o puestas a mano en
  el producto (productos.categoria_etiquetado_id).
- tipos_etiqueta.alcance: dónde va la etiqueta por defecto (línea, posición
  de la OC o de la lista de empaque, variante, artículo genérico, OC, lista de
  empaque o empaque). Vacío = lo de antes.
- usos_diseno (cada fila es una regla): nivel CATEGORIA (categoria_id);
  accion USAR / NO_LLEVA (con NO_LLEVA no hay diseño: plantilla_id vacío);
  alcance y cantidad propios de la regla (vacío = lo del tipo) y prioridad
  para desempatar reglas del mismo lugar.

Solo agrega: las reglas existentes quedan con accion USAR, sin alcance ni
cantidad propios y prioridad 0, así que se resuelven y se imprimen igual que
antes.

Revision ID: 0080
Revises: 0079
Create Date: 2026-10-21 09:00:00
"""
from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls

revision = '0080'
down_revision = '0079'
branch_labels = None
depends_on = None

ALCANCES = ('LINEA', 'POSICION_OC', 'POSICION_PL', 'ARTICULO', 'PRODUCTO', 'DOCUMENTO', 'OC', 'PL', 'EMPAQUE')
_en = lambda col, vals: f"{col} IN ({', '.join(repr(v) for v in vals)})"  # noqa: E731


def _solo(nivel: str, columna, con_categoria: bool) -> str:
    cols = ["familia_id"] + (["categoria_id"] if con_categoria else []) + ["producto_id", "articulo_id", "tipo_empaque_id"]
    return "(" + " AND ".join([f"nivel = '{nivel}'"] + ([f"{columna} IS NOT NULL"] if columna else [])
                              + [f"{c} IS NULL" for c in cols if c != columna]) + ")"


def _destino(con_categoria: bool) -> str:
    niveles = [("GENERAL", None), ("FAMILIA", "familia_id")] + ([("CATEGORIA", "categoria_id")] if con_categoria else []) + [
        ("PRODUCTO", "producto_id"), ("SKU", "articulo_id"), ("TIPO_EMPAQUE", "tipo_empaque_id")]
    return " OR ".join(_solo(n, c, con_categoria) for n, c in niveles)


def _indice_normal(crear: bool) -> None:
    if crear:
        op.create_index('uq_usos_diseno_normal', 'usos_diseno', ['organizacion_id', 'celda'], unique=True,
                        sqlite_where=sa.text("contexto_tipo = 'NINGUNO' AND eliminado_en IS NULL"),
                        postgresql_where=sa.text("contexto_tipo = 'NINGUNO' AND eliminado_en IS NULL"))
    else:
        op.drop_index('uq_usos_diseno_normal', table_name='usos_diseno')


def upgrade() -> None:
    op.create_table(
        'categorias_etiquetado',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('familia_id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=20), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('descripcion', sa.String(length=300), nullable=True),
        sa.Column('condiciones', sa.JSON(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('activa', sa.Boolean(), nullable=False),
        sa.Column('creada_en', sa.DateTime(), nullable=False),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name='fk_categorias_etiquetado_organizacion_id_organizaciones'),
        sa.ForeignKeyConstraint(['familia_id'], ['familias_etiquetado.id'], name='fk_categorias_etiquetado_familia_id_familias_etiquetado'),
        sa.ForeignKeyConstraint(['familia_id', 'organizacion_id'], ['familias_etiquetado.id', 'familias_etiquetado.organizacion_id'],
                                name='fk_categorias_etiquetado_familia_id_org'),
        sa.PrimaryKeyConstraint('id', name='pk_categorias_etiquetado'),
        sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_categorias_etiquetado_org_codigo'),
        sa.UniqueConstraint('id', 'organizacion_id', name='uq_categorias_etiquetado_id_org'),
    )
    with op.batch_alter_table('categorias_etiquetado', schema=None) as b:
        b.create_index(b.f('ix_categorias_etiquetado_organizacion_id'), ['organizacion_id'], unique=False)
        b.create_index(b.f('ix_categorias_etiquetado_familia_id'), ['familia_id'], unique=False)
    rls(op, 'categorias_etiquetado')

    with op.batch_alter_table('tipos_etiqueta', schema=None) as b:
        b.add_column(sa.Column('alcance', sa.String(length=12), nullable=True))
        b.create_check_constraint('ck_tipos_etiqueta_alcance', "alcance IS NULL OR " + _en('alcance', ALCANCES))

    with op.batch_alter_table('productos', schema=None) as b:
        b.add_column(sa.Column('categoria_etiquetado_id', sa.Integer(), nullable=True))
        b.create_index(b.f('ix_productos_categoria_etiquetado_id'), ['categoria_etiquetado_id'], unique=False)
        b.create_foreign_key('fk_productos_categoria_etiquetado_id', 'categorias_etiquetado', ['categoria_etiquetado_id'], ['id'])
        b.create_foreign_key('fk_productos_categoria_etiquetado_id_org', 'categorias_etiquetado',
                             ['categoria_etiquetado_id', 'organizacion_id'], ['id', 'organizacion_id'])

    _indice_normal(False)
    with op.batch_alter_table('usos_diseno', schema=None) as b:
        b.add_column(sa.Column('categoria_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('accion', sa.String(length=8), nullable=False, server_default='USAR'))
        b.add_column(sa.Column('alcance', sa.String(length=12), nullable=True))
        b.add_column(sa.Column('cantidad', sa.String(length=10), nullable=True))
        b.add_column(sa.Column('prioridad', sa.Integer(), nullable=False, server_default='0'))
        b.alter_column('plantilla_id', existing_type=sa.Integer(), nullable=True)
        b.create_index(b.f('ix_usos_diseno_categoria_id'), ['categoria_id'], unique=False)
        b.create_foreign_key('fk_usos_diseno_categoria_id_categorias_etiquetado', 'categorias_etiquetado', ['categoria_id'], ['id'])
        b.create_foreign_key('fk_usos_diseno_categoria_id_org', 'categorias_etiquetado',
                             ['categoria_id', 'organizacion_id'], ['id', 'organizacion_id'])
        b.drop_constraint('ck_usos_diseno_nivel', type_='check')
        b.drop_constraint('ck_usos_diseno_destino', type_='check')
        b.create_check_constraint('ck_usos_diseno_nivel', _en('nivel', ('SKU', 'PRODUCTO', 'CATEGORIA', 'FAMILIA', 'TIPO_EMPAQUE', 'GENERAL')))
        b.create_check_constraint('ck_usos_diseno_destino', _destino(True))
        b.create_check_constraint('ck_usos_diseno_accion', _en('accion', ('USAR', 'NO_LLEVA')))
        b.create_check_constraint('ck_usos_diseno_plantilla', "(accion = 'USAR') = (plantilla_id IS NOT NULL)")
        b.create_check_constraint('ck_usos_diseno_alcance', "alcance IS NULL OR " + _en('alcance', ALCANCES))
        b.create_check_constraint('ck_usos_diseno_cantidad', "cantidad IS NULL OR " + _en('cantidad', ('UNA', 'POR_UNIDAD', 'MANUAL')))
    _indice_normal(True)


def downgrade() -> None:
    con = op.get_bind()
    quedan = con.execute(sa.text("SELECT count(*) FROM usos_diseno WHERE nivel = 'CATEGORIA' OR accion <> 'USAR'")).scalar()
    if quedan:
        raise RuntimeError(f"Hay {quedan} reglas por categoría o «no lleva»: no caben en el esquema anterior. Quítelas antes de volver.")
    _indice_normal(False)
    with op.batch_alter_table('usos_diseno', schema=None) as b:
        for ck in ('ck_usos_diseno_cantidad', 'ck_usos_diseno_alcance', 'ck_usos_diseno_plantilla', 'ck_usos_diseno_accion',
                   'ck_usos_diseno_destino', 'ck_usos_diseno_nivel'):
            b.drop_constraint(ck, type_='check')
        b.create_check_constraint('ck_usos_diseno_nivel', _en('nivel', ('SKU', 'PRODUCTO', 'FAMILIA', 'TIPO_EMPAQUE', 'GENERAL')))
        b.create_check_constraint('ck_usos_diseno_destino', _destino(False))
        b.drop_constraint('fk_usos_diseno_categoria_id_org', type_='foreignkey')
        b.drop_constraint('fk_usos_diseno_categoria_id_categorias_etiquetado', type_='foreignkey')
        b.drop_index(b.f('ix_usos_diseno_categoria_id'))
        b.alter_column('plantilla_id', existing_type=sa.Integer(), nullable=False)
        for col in ('prioridad', 'cantidad', 'alcance', 'accion', 'categoria_id'):
            b.drop_column(col)
    _indice_normal(True)
    with op.batch_alter_table('productos', schema=None) as b:
        b.drop_constraint('fk_productos_categoria_etiquetado_id_org', type_='foreignkey')
        b.drop_constraint('fk_productos_categoria_etiquetado_id', type_='foreignkey')
        b.drop_index(b.f('ix_productos_categoria_etiquetado_id'))
        b.drop_column('categoria_etiquetado_id')
    with op.batch_alter_table('tipos_etiqueta', schema=None) as b:
        b.drop_constraint('ck_tipos_etiqueta_alcance', type_='check')
        b.drop_column('alcance')
    op.drop_table('categorias_etiquetado')
