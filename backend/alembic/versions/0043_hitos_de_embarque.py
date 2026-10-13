"""Hitos del embarque configurables

Los eventos de un embarque (recolección, salida, arribo, entrega…) pasan a la
lista de valores evento_embarque, con los estados en que se pueden registrar.
Los de sistema conservan sus reglas; cada empresa puede agregar los suyos.

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0043'
down_revision = '0042'
branch_labels = None
depends_on = None

HITOS = [
    {'lista': 'evento_embarque', 'codigo': 'RECOLECCION', 'nombre': 'Pickup', 'orden': 1, 'activo': True, 'estados': 'PLANIFICADO'},
    {'lista': 'evento_embarque', 'codigo': 'SALIDA', 'nombre': 'Departure', 'orden': 2, 'activo': True, 'estados': 'PLANIFICADO'},
    {'lista': 'evento_embarque', 'codigo': 'TRANSITO', 'nombre': 'In transit', 'orden': 3, 'activo': True, 'estados': 'EN_TRANSITO'},
    {'lista': 'evento_embarque', 'codigo': 'ARRIBO', 'nombre': 'Arrival', 'orden': 4, 'activo': True, 'estados': 'EN_TRANSITO'},
    {'lista': 'evento_embarque', 'codigo': 'LIBERACION', 'nombre': 'Customs release', 'orden': 5, 'activo': True, 'estados': 'ARRIBADO'},
    {'lista': 'evento_embarque', 'codigo': 'ENTREGA', 'nombre': 'Delivery', 'orden': 6, 'activo': True, 'estados': 'ARRIBADO'},
    {'lista': 'evento_embarque', 'codigo': 'RECEPCION', 'nombre': 'Warehouse receipt', 'orden': 7, 'activo': True, 'estados': 'ENTREGADO'},
    {'lista': 'evento_embarque', 'codigo': 'OTRO', 'nombre': 'Other', 'orden': 8, 'activo': True, 'estados': 'PLANIFICADO,EN_TRANSITO,ARRIBADO,ENTREGADO,RECIBIDO'},
]


def upgrade() -> None:
    with op.batch_alter_table("valores_lista") as b:
        b.add_column(sa.Column("estados", sa.String(120), nullable=True))
    tabla = sa.table("valores_lista", sa.column("lista", sa.String), sa.column("codigo", sa.String),
                     sa.column("nombre", sa.String), sa.column("orden", sa.Integer), sa.column("activo", sa.Boolean),
                     sa.column("estados", sa.String))
    op.bulk_insert(tabla, HITOS)


def downgrade() -> None:
    op.execute("DELETE FROM valores_lista WHERE lista = 'evento_embarque'")
    with op.batch_alter_table("valores_lista") as b:
        b.drop_column("estados")
