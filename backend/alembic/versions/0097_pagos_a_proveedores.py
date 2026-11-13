"""Pagos a proveedores: vencimiento de la factura y sus pagos programados y pagados

- facturas.vence: el vencimiento para pagarla (sin fecha, se calcula con la
  condición de pago de su OC).
- pagos_proveedor: cada pago de una factura, programado para una fecha y
  después pagado o anulado.
- Permisos pago.ver y pago.gestionar para los roles internos de fábrica.

Revision ID: 0097
Revises: 0096
Create Date: 2026-11-13 00:00:00
"""
import json

import sqlalchemy as sa

from alembic import op
from app.instalacion.esquema import rls

revision = '0097'
down_revision = '0096'
branch_labels = None
depends_on = None

PERMISOS = ("pago.ver", "pago.gestionar")


def _permisos(con) -> None:
    for rid, permisos in con.execute(sa.text("SELECT id, permisos FROM roles WHERE sistema = :si AND tipo IN ('admin', 'interno')"),
                                     {"si": True}).all():
        lista = json.loads(permisos) if isinstance(permisos, str) else list(permisos or [])
        nuevos = sorted(set(lista) | set(PERMISOS))
        if nuevos != sorted(lista):
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(nuevos), "i": rid})


def upgrade() -> None:
    with op.batch_alter_table('facturas', schema=None) as b:
        b.add_column(sa.Column('vence', sa.Date(), nullable=True))
        b.create_index(b.f('ix_facturas_vence'), ['vence'], unique=False)

    op.create_table(
        'pagos_proveedor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('factura_id', sa.Integer(), nullable=False),
        sa.Column('importe', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('fecha_programada', sa.Date(), nullable=False),
        sa.Column('fecha_pago', sa.Date(), nullable=True),
        sa.Column('referencia', sa.String(length=80), nullable=True),
        sa.Column('estado', sa.String(length=12), nullable=False),
        sa.Column('creado_por', sa.Integer(), nullable=True),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(), nullable=False),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("estado IN ('PROGRAMADO', 'PAGADO', 'ANULADO')", name='ck_pagos_proveedor_estado'),
        sa.CheckConstraint("importe > 0", name='ck_pagos_proveedor_importe'),
        sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['factura_id'], ['facturas.id'], ),
        sa.ForeignKeyConstraint(['factura_id', 'organizacion_id'], ['facturas.id', 'facturas.organizacion_id'],
                                name='fk_pagos_proveedor_factura_id_org'),
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
        sa.PrimaryKeyConstraint('id'))
    with op.batch_alter_table('pagos_proveedor', schema=None) as b:
        b.create_index(b.f('ix_pagos_proveedor_factura_id'), ['factura_id'], unique=False)
        b.create_index(b.f('ix_pagos_proveedor_fecha_programada'), ['fecha_programada'], unique=False)
        b.create_index(b.f('ix_pagos_proveedor_estado'), ['estado'], unique=False)
        b.create_index(b.f('ix_pagos_proveedor_organizacion_id'), ['organizacion_id'], unique=False)
    rls(op, 'pagos_proveedor')
    _permisos(op.get_bind())


def downgrade() -> None:
    op.drop_table('pagos_proveedor')
    with op.batch_alter_table('facturas', schema=None) as b:
        b.drop_index(b.f('ix_facturas_vence'))
        b.drop_column('vence')
