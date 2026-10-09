"""Perfiles de importación de OCs

Cada empresa define cómo se llaman las columnas del archivo que exporta su
ERP (y la fila de los encabezados, el formato de las fechas y los valores por
defecto). Los nombres propios de un ERP salen del código: una instalación que
ya tiene órdenes de compra recibe un perfil con los nombres que el sistema
aceptaba hasta ahora, como predeterminado, para que sus archivos se sigan
leyendo igual.

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0041'
down_revision = '0040'
branch_labels = None
depends_on = None

ANTERIOR = {"codigo_sap": "sap_code, codigo_sap, sap"}


def upgrade() -> None:
    tabla = op.create_table(
        "perfiles_importacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("columnas", sa.JSON(), nullable=False),
        sa.Column("valores", sa.JSON(), nullable=False),
        sa.Column("fila_encabezado", sa.Integer(), nullable=False),
        sa.Column("formato_fecha", sa.String(12), nullable=True),
        sa.Column("predeterminado", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("codigo"),
    )
    con = op.get_bind()
    if con.execute(sa.text("SELECT COUNT(*) FROM posiciones_oc")).scalar():
        op.bulk_insert(tabla, [dict(codigo="ANTERIOR", nombre="Previous column names", columnas=ANTERIOR, valores={},
                                    fila_encabezado=1, formato_fecha=None, predeterminado=True, activo=True)])


def downgrade() -> None:
    op.drop_table("perfiles_importacion")
