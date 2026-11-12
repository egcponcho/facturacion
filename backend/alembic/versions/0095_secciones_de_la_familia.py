"""Secciones de la familia

La familia del catálogo (grupos_producto) es una sola; cada módulo guarda lo
suyo de ella en su propia tabla:

- familia_logistica: los días extra que sus productos suman a la fecha estimada
  en tienda (antes grupos_producto.dias_extra, que se mueve y se borra);
- familia_etiquetado: los campos que esperan sus etiquetas (se copian de
  grupos_producto.campos, que queda como los datos que el catálogo exige a sus
  productos; desde ahora cada lista se cambia por separado).

La vuelta atrás devuelve los días extra a grupos_producto y borra las tablas.

Revision ID: 0095
Revises: 0094
Create Date: 2026-10-23 20:00:00
"""
import json

import sqlalchemy as sa

from alembic import op
from app.instalacion.esquema import rls

revision = '0095'
down_revision = '0094'
branch_labels = None
depends_on = None


def _tabla(con, nombre: str) -> sa.Table:
    return sa.Table(nombre, sa.MetaData(), autoload_with=con)


def _lista(v) -> list:
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) if v else []
    except (TypeError, ValueError):
        return []


def _seccion(nombre: str, *columnas) -> None:
    op.create_table(
        nombre,
        sa.Column('familia_id', sa.Integer(), nullable=False),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        *columnas,
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name=f'fk_{nombre}_organizacion_id_organizaciones'),
        sa.ForeignKeyConstraint(['familia_id', 'organizacion_id'], ['grupos_producto.id', 'grupos_producto.organizacion_id'],
                                ondelete='CASCADE', name=f'fk_{nombre}_familia_org'),
        sa.PrimaryKeyConstraint('familia_id', name=f'pk_{nombre}'))
    op.create_index(f'ix_{nombre}_organizacion_id', nombre, ['organizacion_id'], unique=False)


def upgrade() -> None:
    con = op.get_bind()
    _seccion('familia_logistica', sa.Column('dias_extra', sa.Integer(), nullable=True))
    _seccion('familia_etiquetado', sa.Column('campos', sa.JSON(), nullable=False, server_default='[]'))
    rls(op, 'familia_logistica', 'familia_etiquetado')

    grupos = _tabla(con, 'grupos_producto')
    filas = con.execute(sa.select(grupos.c.id, grupos.c.organizacion_id, grupos.c.dias_extra, grupos.c.campos)).all()
    logistica = [{'familia_id': g.id, 'organizacion_id': g.organizacion_id, 'dias_extra': g.dias_extra}
                 for g in filas if g.dias_extra is not None]
    etiquetado = [{'familia_id': g.id, 'organizacion_id': g.organizacion_id, 'campos': _lista(g.campos)}
                  for g in filas if _lista(g.campos)]
    if logistica:
        con.execute(_tabla(con, 'familia_logistica').insert(), logistica)
    if etiquetado:
        con.execute(_tabla(con, 'familia_etiquetado').insert(), etiquetado)
    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.drop_column('dias_extra')


def downgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.add_column(sa.Column('dias_extra', sa.Integer(), nullable=True))
    grupos = _tabla(con, 'grupos_producto')
    for f in con.execute(sa.text("SELECT familia_id, dias_extra FROM familia_logistica")).all():
        con.execute(grupos.update().where(grupos.c.id == f.familia_id).values(dias_extra=f.dias_extra))
    for nombre in ('familia_etiquetado', 'familia_logistica'):
        op.drop_index(f'ix_{nombre}_organizacion_id', table_name=nombre)
        op.drop_table(nombre)
