"""Reglas de la ficha: tipo_fuente MOTOR_JS pasa a SHEET_RULES

El clasificador del navegador (motor.js) ya no existe; sus reglas son datos
del motor único con su propio tipo de fuente.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-07 09:00:00
"""
from alembic import op


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE reglas_clasificacion SET tipo_fuente = 'SHEET_RULES' WHERE tipo_fuente = 'MOTOR_JS'")


def downgrade() -> None:
    op.execute("UPDATE reglas_clasificacion SET tipo_fuente = 'MOTOR_JS' WHERE tipo_fuente = 'SHEET_RULES'")
