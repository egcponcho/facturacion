"""Asignación siempre confirmada y recepción coherente con el embarque

- Solo se asignan listas de empaque finalizadas, así que la asignación
  «tentativa» ya no existe (el camino estaba sin uso): las que quedaran en
  ese estado pasan a confirmadas.
- Un embarque recibido tiene la recepción de cada línea de sus listas de
  empaque (docs/FLUJOS.md §3). Los que se marcaron recibidos solo con el hito
  quedan recibidos sin novedad, línea por línea.

Revision ID: 0049
Revises: 0048
Create Date: 2026-10-09 00:00:00
"""
from alembic import op


revision = '0049'
down_revision = '0048'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE packing_lists SET asignacion = 'CONFIRMADA' WHERE asignacion = 'TENTATIVA'")
    op.execute("""
        INSERT INTO recepciones (pl_linea_id, cantidad_recibida, cantidad_danada, observacion, fecha, organizacion_id)
        SELECT l.id, l.cantidad, 0, 'Received without differences (shipment milestone)', CURRENT_TIMESTAMP, l.organizacion_id
        FROM pl_lineas l
        JOIN packing_lists p ON p.id = l.pl_id
        JOIN unidades_carga u ON u.id = p.unidad_carga_id
        JOIN embarques e ON e.id = u.embarque_id
        WHERE e.estado = 'RECIBIDO' AND p.estado <> 'CANCELADO'
          AND NOT EXISTS (SELECT 1 FROM recepciones r WHERE r.pl_linea_id = l.id)
    """)


def downgrade() -> None:
    pass
