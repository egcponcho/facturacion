"""Llaves foráneas de los códigos de unidad que no la tenían

- unidades_medida.base → unidades_medida(organizacion_id, codigo): la unidad
  a la que se convierte otra (una docena → unidad) debe existir.
- atributos_variante.unidad → unidades_medida(organizacion_id, codigo): la
  unidad de un atributo numérico (220 V, 500 ml).

Antes de crear las llaves, un código que no existe en el catálogo de su
organización se deja vacío (con su equivalencia, que sin base no tiene
sentido): no hay otra forma de saber a qué unidad se refería. La migración
informa cuántos se limpiaron.

Revision ID: 0089
Revises: 0088
Create Date: 2026-10-22 10:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = '0089'
down_revision = '0088'
branch_labels = None
depends_on = None

HUERFANOS_BASE = """
    FROM unidades_medida u WHERE u.base IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM unidades_medida b WHERE b.organizacion_id = u.organizacion_id AND b.codigo = u.base)"""
HUERFANOS_ATRIBUTO = """
    FROM atributos_variante a WHERE a.unidad IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM unidades_medida b WHERE b.organizacion_id = a.organizacion_id AND b.codigo = a.unidad)"""


def upgrade() -> None:
    con = op.get_bind()
    n_base = con.execute(sa.text("SELECT count(*)" + HUERFANOS_BASE)).scalar() or 0
    n_atr = con.execute(sa.text("SELECT count(*)" + HUERFANOS_ATRIBUTO)).scalar() or 0
    if n_base:
        con.execute(sa.text("UPDATE unidades_medida SET base = NULL, equivale = NULL WHERE id IN (SELECT u.id"
                            + HUERFANOS_BASE + ")"))
    if n_atr:
        con.execute(sa.text("UPDATE atributos_variante SET unidad = NULL WHERE id IN (SELECT a.id" + HUERFANOS_ATRIBUTO + ")"))
    if n_base or n_atr:
        print(f"0089: {n_base} unidades sin su unidad base y {n_atr} atributos sin su unidad quedaron vacíos")
    with op.batch_alter_table('unidades_medida', schema=None) as b:
        b.create_foreign_key('fk_unidades_medida_base', 'unidades_medida', ['organizacion_id', 'base'],
                             ['organizacion_id', 'codigo'])
    with op.batch_alter_table('atributos_variante', schema=None) as b:
        b.create_foreign_key('fk_atributos_variante_unidad', 'unidades_medida', ['organizacion_id', 'unidad'],
                             ['organizacion_id', 'codigo'])


def downgrade() -> None:
    with op.batch_alter_table('atributos_variante', schema=None) as b:
        b.drop_constraint('fk_atributos_variante_unidad', type_='foreignkey')
    with op.batch_alter_table('unidades_medida', schema=None) as b:
        b.drop_constraint('fk_unidades_medida_base', type_='foreignkey')
