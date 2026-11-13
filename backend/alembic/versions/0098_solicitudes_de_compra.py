"""Solicitudes de compra: lo que piden las áreas antes de la orden de compra

- solicitudes_compra y solicitud_lineas (pendiente → aprobada o rechazada →
  convertida en OC; o cancelada).
- Permisos solicitud.ver, solicitud.crear y solicitud.aprobar para los roles
  internos de fábrica.

Revision ID: 0098
Revises: 0097
Create Date: 2026-11-13 00:00:00
"""
import json

import sqlalchemy as sa

from alembic import op
from app.instalacion.esquema import rls

revision = '0098'
down_revision = '0097'
branch_labels = None
depends_on = None

PERMISOS = ("solicitud.ver", "solicitud.crear", "solicitud.aprobar")


def _permisos(con) -> None:
    for rid, permisos in con.execute(sa.text("SELECT id, permisos FROM roles WHERE sistema = :si AND tipo IN ('admin', 'interno')"),
                                     {"si": True}).all():
        lista = json.loads(permisos) if isinstance(permisos, str) else list(permisos or [])
        nuevos = sorted(set(lista) | set(PERMISOS))
        if nuevos != sorted(lista):
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(nuevos), "i": rid})


def upgrade() -> None:
    op.create_table(
        'solicitudes_compra',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('numero', sa.String(length=30), nullable=False),
        sa.Column('area', sa.String(length=80), nullable=False),
        sa.Column('centro', sa.String(length=10), nullable=True),
        sa.Column('solicitante_id', sa.Integer(), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('fecha_requerida', sa.Date(), nullable=True),
        sa.Column('prioridad', sa.String(length=10), nullable=False),
        sa.Column('estado', sa.String(length=12), nullable=False),
        sa.Column('proveedor_id', sa.Integer(), nullable=True),
        sa.Column('moneda', sa.String(length=3), nullable=True),
        sa.Column('motivo', sa.String(length=500), nullable=True),
        sa.Column('comentario_revision', sa.String(length=500), nullable=True),
        sa.Column('revisada_por', sa.Integer(), nullable=True),
        sa.Column('revisada_en', sa.DateTime(), nullable=True),
        sa.Column('oc_id', sa.Integer(), nullable=True),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(), nullable=False),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("estado IN ('PENDIENTE', 'APROBADA', 'RECHAZADA', 'CONVERTIDA', 'CANCELADA')",
                           name='ck_solicitudes_compra_estado'),
        sa.CheckConstraint("prioridad IN ('NORMAL', 'URGENTE')", name='ck_solicitudes_compra_prioridad'),
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
        sa.ForeignKeyConstraint(['solicitante_id'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['revisada_por'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['proveedor_id'], ['proveedores.id'], ),
        sa.ForeignKeyConstraint(['oc_id'], ['ordenes_compra.id'], ),
        sa.ForeignKeyConstraint(['organizacion_id', 'centro'], ['centros.organizacion_id', 'centros.codigo'],
                                name='fk_solicitudes_compra_centro'),
        sa.ForeignKeyConstraint(['organizacion_id', 'moneda'], ['monedas.organizacion_id', 'monedas.codigo'],
                                name='fk_solicitudes_compra_moneda'),
        sa.ForeignKeyConstraint(['proveedor_id', 'organizacion_id'], ['proveedores.id', 'proveedores.organizacion_id'],
                                name='fk_solicitudes_compra_proveedor_id_org'),
        sa.ForeignKeyConstraint(['oc_id', 'organizacion_id'], ['ordenes_compra.id', 'ordenes_compra.organizacion_id'],
                                name='fk_solicitudes_compra_oc_id_org'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organizacion_id', 'numero', name='uq_solicitudes_compra_org_numero'),
        sa.UniqueConstraint('id', 'organizacion_id', name='uq_solicitudes_compra_id_org'))
    with op.batch_alter_table('solicitudes_compra', schema=None) as b:
        for col in ('estado', 'organizacion_id', 'oc_id', 'fecha', 'proveedor_id'):
            b.create_index(b.f(f'ix_solicitudes_compra_{col}'), [col], unique=False)

    op.create_table(
        'solicitud_lineas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('solicitud_id', sa.Integer(), nullable=False),
        sa.Column('codigo_articulo', sa.String(length=40), nullable=True),
        sa.Column('descripcion', sa.String(length=300), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column('unidad', sa.String(length=5), nullable=True),
        sa.Column('precio_estimado', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("cantidad > 0", name='ck_solicitud_lineas_cantidad'),
        sa.CheckConstraint("precio_estimado IS NULL OR precio_estimado >= 0", name='ck_solicitud_lineas_precio_estimado'),
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
        sa.ForeignKeyConstraint(['solicitud_id'], ['solicitudes_compra.id'], ),
        sa.ForeignKeyConstraint(['solicitud_id', 'organizacion_id'], ['solicitudes_compra.id', 'solicitudes_compra.organizacion_id'],
                                name='fk_solicitud_lineas_solicitud_id_org'),
        sa.ForeignKeyConstraint(['organizacion_id', 'unidad'], ['unidades_medida.organizacion_id', 'unidades_medida.codigo'],
                                name='fk_solicitud_lineas_unidad'),
        sa.PrimaryKeyConstraint('id'))
    with op.batch_alter_table('solicitud_lineas', schema=None) as b:
        b.create_index(b.f('ix_solicitud_lineas_solicitud_id'), ['solicitud_id'], unique=False)
        b.create_index(b.f('ix_solicitud_lineas_organizacion_id'), ['organizacion_id'], unique=False)
    rls(op, 'solicitudes_compra', 'solicitud_lineas')
    _permisos(op.get_bind())


def downgrade() -> None:
    op.drop_table('solicitud_lineas')
    op.drop_table('solicitudes_compra')
