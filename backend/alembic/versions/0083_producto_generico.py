"""Producto genérico: unidades que convierten y atributos de variante con tipo

- unidades_medida.base / equivale: una unidad convierte a una base de la lista
  (docena = 12 UN, gramo = 0.001 KG, mililitro = 0.001 L). Sirve para
  cualquier magnitud sin tocar el código. Se llenan solo las de fábrica que
  la empresa conserva con su código y cuya base existe.
- atributos_variante.tipo / opciones / unidad: el valor de un atributo propio
  es texto libre, un número en su unidad (220 V, 500 ml) o una de sus
  opciones. Los existentes quedan como texto (como hoy).

Revision ID: 0083
Revises: 0082
Create Date: 2026-10-20 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0083'
down_revision = '0082'
branch_labels = None
depends_on = None

FABRICA = (("DOC", "UN", 12), ("G", "KG", 0.001), ("ML", "L", 0.001))


def upgrade() -> None:
    with op.batch_alter_table('unidades_medida', schema=None) as b:
        b.add_column(sa.Column('base', sa.String(length=10), nullable=True))
        b.add_column(sa.Column('equivale', sa.Float(), nullable=True))
        b.create_check_constraint('ck_unidades_medida_base_equivale', '(base IS NULL) = (equivale IS NULL)')
        b.create_check_constraint('ck_unidades_medida_equivale', 'equivale IS NULL OR equivale > 0')
        b.create_check_constraint('ck_unidades_medida_base', 'base IS NULL OR base <> codigo')
    with op.batch_alter_table('atributos_variante', schema=None) as b:
        b.add_column(sa.Column('tipo', sa.String(length=10), server_default='texto', nullable=False))
        b.add_column(sa.Column('opciones', sa.String(length=500), nullable=True))
        b.add_column(sa.Column('unidad', sa.String(length=10), nullable=True))
        b.create_check_constraint('ck_atributos_variante_tipo', "tipo IN ('texto', 'numero', 'opcion')")
    con = op.get_bind()
    for codigo, base, equivale in FABRICA:
        con.execute(sa.text(
            "UPDATE unidades_medida SET base = :b, equivale = :e WHERE codigo = :c AND base IS NULL AND EXISTS "
            "(SELECT 1 FROM unidades_medida u WHERE u.organizacion_id = unidades_medida.organizacion_id AND u.codigo = :b)"),
            {"b": base, "e": equivale, "c": codigo})


def downgrade() -> None:
    with op.batch_alter_table('atributos_variante', schema=None) as b:
        b.drop_constraint('ck_atributos_variante_tipo', type_='check')
        b.drop_column('unidad')
        b.drop_column('opciones')
        b.drop_column('tipo')
    with op.batch_alter_table('unidades_medida', schema=None) as b:
        b.drop_constraint('ck_unidades_medida_base', type_='check')
        b.drop_constraint('ck_unidades_medida_equivale', type_='check')
        b.drop_constraint('ck_unidades_medida_base_equivale', type_='check')
        b.drop_column('equivale')
        b.drop_column('base')
