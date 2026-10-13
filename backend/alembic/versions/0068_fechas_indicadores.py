"""Fechas e índices que necesitan los indicadores (docs/AUDITORIA_KPIS.md §9)

- packing_lists.finalizado_en: cuándo se finalizó la lista de empaque (antes
  se usaba la última modificación). Se llena desde la bitácora.
- embarques.eta_comprometida: la ETA vigente al registrar la salida; la
  puntualidad se mide contra ella aunque la ETA se actualice en ruta.
- aplicaciones.fecha: fecha de negocio de la aplicación de un pago o crédito.
- Índices para filtrar por período: facturas (fecha, finalizado_en), OC
  (aprobada_en), embarques (eta, arribo_real), recepciones (fecha), eventos
  (fecha, tipo) y bitácora (entidad, acción, fecha).

Revision ID: 0068
Revises: 0067
Create Date: 2026-10-14 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0068'
down_revision = '0067'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('packing_lists', schema=None) as b:
        b.add_column(sa.Column('finalizado_en', sa.DateTime(), nullable=True))
        b.create_index(b.f('ix_packing_lists_finalizado_en'), ['finalizado_en'], unique=False)
    with op.batch_alter_table('embarques', schema=None) as b:
        b.add_column(sa.Column('eta_comprometida', sa.Date(), nullable=True))
        b.create_index(b.f('ix_embarques_eta'), ['eta'], unique=False)
        b.create_index(b.f('ix_embarques_arribo_real'), ['arribo_real'], unique=False)
    with op.batch_alter_table('aplicaciones', schema=None) as b:
        b.add_column(sa.Column('fecha', sa.Date(), nullable=True))
        b.create_index(b.f('ix_aplicaciones_fecha'), ['fecha'], unique=False)
    with op.batch_alter_table('facturas', schema=None) as b:
        b.create_index(b.f('ix_facturas_fecha'), ['fecha'], unique=False)
        b.create_index(b.f('ix_facturas_finalizado_en'), ['finalizado_en'], unique=False)
    with op.batch_alter_table('ordenes_compra', schema=None) as b:
        b.create_index(b.f('ix_ordenes_compra_aprobada_en'), ['aprobada_en'], unique=False)
    with op.batch_alter_table('recepciones', schema=None) as b:
        b.create_index(b.f('ix_recepciones_fecha'), ['fecha'], unique=False)
    with op.batch_alter_table('eventos_embarque', schema=None) as b:
        b.create_index('ix_eventos_embarque_fecha_tipo', ['fecha', 'tipo'], unique=False)
    with op.batch_alter_table('historial', schema=None) as b:
        b.create_index('ix_historial_entidad_accion_fecha', ['entidad', 'accion', 'fecha'], unique=False)

    # Datos existentes
    op.execute("""
        UPDATE packing_lists SET finalizado_en = COALESCE(
            (SELECT MAX(h.fecha) FROM historial h WHERE h.entidad = 'packing_list' AND h.entidad_id = packing_lists.id
             AND h.accion = 'finalizar'), actualizado_en)
        WHERE estado = 'FINALIZADO'""")
    op.execute("UPDATE embarques SET eta_comprometida = eta WHERE salida_real IS NOT NULL")
    op.execute("""
        UPDATE aplicaciones SET fecha = COALESCE(
            (SELECT p.fecha FROM pagos p WHERE p.id = aplicaciones.pago_id),
            (SELECT d.fecha FROM documentos d WHERE d.id = aplicaciones.credito_id))""")
    op.execute("UPDATE aplicaciones SET fecha = DATE(creado_en) WHERE fecha IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('historial', schema=None) as b:
        b.drop_index('ix_historial_entidad_accion_fecha')
    with op.batch_alter_table('eventos_embarque', schema=None) as b:
        b.drop_index('ix_eventos_embarque_fecha_tipo')
    with op.batch_alter_table('recepciones', schema=None) as b:
        b.drop_index(b.f('ix_recepciones_fecha'))
    with op.batch_alter_table('ordenes_compra', schema=None) as b:
        b.drop_index(b.f('ix_ordenes_compra_aprobada_en'))
    with op.batch_alter_table('facturas', schema=None) as b:
        b.drop_index(b.f('ix_facturas_finalizado_en'))
        b.drop_index(b.f('ix_facturas_fecha'))
    with op.batch_alter_table('aplicaciones', schema=None) as b:
        b.drop_index(b.f('ix_aplicaciones_fecha'))
        b.drop_column('fecha')
    with op.batch_alter_table('embarques', schema=None) as b:
        b.drop_index(b.f('ix_embarques_arribo_real'))
        b.drop_index(b.f('ix_embarques_eta'))
        b.drop_column('eta_comprometida')
    with op.batch_alter_table('packing_lists', schema=None) as b:
        b.drop_index(b.f('ix_packing_lists_finalizado_en'))
        b.drop_column('finalizado_en')
