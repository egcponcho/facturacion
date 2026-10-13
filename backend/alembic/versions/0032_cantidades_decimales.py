"""Cantidades con decimales

Lo que se mide (kg, litros, metros…) lleva hasta 3 decimales; lo que se
cuenta (pares, unidades, cajas) sigue entero: lo valida el servidor según la
unidad de la posición.

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-07 23:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None

COLUMNAS = [("posiciones_oc", "cantidad"), ("factura_lineas", "cantidad"), ("pl_lineas", "cantidad"),
            ("grupo_cajas_items", "cantidad_por_caja"), ("plantillas_caja", "cantidad_por_caja"),
            ("recepciones", "cantidad_recibida"), ("recepciones", "cantidad_danada")]


def upgrade() -> None:
    for tabla, col in COLUMNAS:
        with op.batch_alter_table(tabla) as t:
            t.alter_column(col, type_=sa.Numeric(14, 3), existing_type=sa.Integer())


def downgrade() -> None:
    for tabla, col in COLUMNAS:
        with op.batch_alter_table(tabla) as t:
            t.alter_column(col, type_=sa.Integer(), existing_type=sa.Numeric(14, 3))
