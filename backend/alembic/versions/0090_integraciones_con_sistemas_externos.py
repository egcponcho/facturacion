"""Integración con sistemas externos (ERP u otros)

Capa de integración desacoplada del núcleo (docs/reestructuracion/02-arquitectura.md §4):

- integraciones: un sistema externo de la organización y el adaptador de
  formato con que se intercambia.
- integracion_mapeos: campo interno → campo externo, valores por defecto y
  traducción de códigos, por entidad y dirección; versionados (cada cambio
  crea una versión y la anterior queda como histórica).
- referencias_externas: el identificador de cada registro en el sistema
  externo (único por integración y entidad, en los dos sentidos).
- integracion_ejecuciones: la bitácora de cada intercambio con su huella, para
  no aplicar dos veces el mismo contenido.

Todas son de la organización: RLS en PostgreSQL y llaves de coherencia
(padre_id, organizacion_id) → integraciones(id, organizacion_id). No toca
datos de negocio; la vuelta atrás elimina las tablas.

Permisos nuevos (integraciones.ver, .configurar, .ejecutar): se agregan a los
roles de administrador de fábrica ya guardados, como hicieron 0070 y 0072; los
demás roles los reciben solo si un administrador los marca.

Revision ID: 0090
Revises: 0089
Create Date: 2026-10-22 11:00:00
"""
import json

import sqlalchemy as sa

from alembic import op
from app.instalacion.esquema import rls

revision = '0090'
down_revision = '0089'
branch_labels = None
depends_on = None

HIJAS = ('integracion_mapeos', 'integracion_ejecuciones', 'referencias_externas')
PERMISOS = ('integraciones.ver', 'integraciones.configurar', 'integraciones.ejecutar')


def _org(tabla: str) -> list:
    return [sa.Column('organizacion_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name=f'fk_{tabla}_organizacion_id_organizaciones')]


def _de_integracion(tabla: str) -> list:
    return [sa.Column('integracion_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['integracion_id'], ['integraciones.id'], ondelete='CASCADE',
                                    name=f'fk_{tabla}_integracion_id_integraciones'),
            sa.ForeignKeyConstraint(['integracion_id', 'organizacion_id'], ['integraciones.id', 'integraciones.organizacion_id'],
                                    name=f'fk_{tabla}_integracion_id_org')]


def upgrade() -> None:
    op.create_table(
        'integraciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=20), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('sistema', sa.String(length=60), nullable=True),
        sa.Column('adaptador', sa.String(length=30), nullable=False),
        sa.Column('parametros', sa.JSON(), nullable=False),
        sa.Column('activa', sa.Boolean(), nullable=False),
        sa.Column('creada_en', sa.DateTime(), nullable=False),
        *_org('integraciones'),
        sa.PrimaryKeyConstraint('id', name='pk_integraciones'),
        sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_integraciones_org_codigo'),
        sa.UniqueConstraint('id', 'organizacion_id', name='uq_integraciones_id_org'),
    )
    op.create_table(
        'integracion_mapeos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entidad', sa.String(length=30), nullable=False),
        sa.Column('direccion', sa.String(length=10), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('vigente', sa.Boolean(), nullable=False),
        sa.Column('campos', sa.JSON(), nullable=False),
        sa.Column('valores', sa.JSON(), nullable=False),
        sa.Column('codigos', sa.JSON(), nullable=False),
        sa.Column('formato_fecha', sa.String(length=12), nullable=True),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.Column('creado_por', sa.Integer(), nullable=True),
        *_org('integracion_mapeos'), *_de_integracion('integracion_mapeos'),
        sa.CheckConstraint("direccion IN ('ENTRADA', 'SALIDA')", name='ck_integracion_mapeos_direccion'),
        sa.CheckConstraint('version >= 1', name='ck_integracion_mapeos_version'),
        sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], name='fk_integracion_mapeos_creado_por_usuarios'),
        sa.PrimaryKeyConstraint('id', name='pk_integracion_mapeos'),
        sa.UniqueConstraint('integracion_id', 'entidad', 'direccion', 'version', name='uq_integracion_mapeos_version'),
    )
    op.create_table(
        'integracion_ejecuciones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mapeo_id', sa.Integer(), nullable=True),
        sa.Column('entidad', sa.String(length=30), nullable=False),
        sa.Column('direccion', sa.String(length=10), nullable=False),
        sa.Column('estado', sa.String(length=12), nullable=False),
        sa.Column('archivo', sa.String(length=300), nullable=True),
        sa.Column('huella', sa.String(length=64), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('filas', sa.JSON(), nullable=False),
        sa.Column('resumen', sa.JSON(), nullable=False),
        sa.Column('errores', sa.JSON(), nullable=False),
        sa.Column('importacion_oc_id', sa.Integer(), nullable=True),
        sa.Column('iniciada_en', sa.DateTime(), nullable=False),
        sa.Column('terminada_en', sa.DateTime(), nullable=True),
        *_org('integracion_ejecuciones'), *_de_integracion('integracion_ejecuciones'),
        sa.CheckConstraint("direccion IN ('ENTRADA', 'SALIDA')", name='ck_integracion_ejecuciones_direccion'),
        sa.CheckConstraint("estado IN ('PREVIA', 'APLICADA', 'CON_ERRORES', 'FALLIDA')", name='ck_integracion_ejecuciones_estado'),
        sa.ForeignKeyConstraint(['importacion_oc_id'], ['importaciones_oc.id'], name='fk_integracion_ejecuciones_importacion_oc_id_importaciones_oc'),
        sa.ForeignKeyConstraint(['mapeo_id'], ['integracion_mapeos.id'], name='fk_integracion_ejecuciones_mapeo_id_integracion_mapeos'),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name='fk_integracion_ejecuciones_usuario_id_usuarios'),
        sa.PrimaryKeyConstraint('id', name='pk_integracion_ejecuciones'),
    )
    op.create_table(
        'referencias_externas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entidad', sa.String(length=30), nullable=False),
        sa.Column('interno_id', sa.Integer(), nullable=False),
        sa.Column('codigo_externo', sa.String(length=120), nullable=False),
        sa.Column('ejecucion_id', sa.Integer(), nullable=True),
        sa.Column('actualizado_en', sa.DateTime(), nullable=False),
        *_org('referencias_externas'), *_de_integracion('referencias_externas'),
        sa.ForeignKeyConstraint(['ejecucion_id'], ['integracion_ejecuciones.id'], name='fk_referencias_externas_ejecucion_id_integracion_ejecuciones'),
        sa.PrimaryKeyConstraint('id', name='pk_referencias_externas'),
        sa.UniqueConstraint('integracion_id', 'entidad', 'codigo_externo', name='uq_referencias_externas_codigo'),
        sa.UniqueConstraint('integracion_id', 'entidad', 'interno_id', name='uq_referencias_externas_interno'),
    )
    with op.batch_alter_table('integraciones', schema=None) as b:
        b.create_index(b.f('ix_integraciones_organizacion_id'), ['organizacion_id'], unique=False)
    for tabla in HIJAS:
        with op.batch_alter_table(tabla, schema=None) as b:
            b.create_index(b.f(f'ix_{tabla}_organizacion_id'), ['organizacion_id'], unique=False)
            b.create_index(b.f(f'ix_{tabla}_integracion_id'), ['integracion_id'], unique=False)
    with op.batch_alter_table('integracion_ejecuciones', schema=None) as b:
        b.create_index('ix_integracion_ejecuciones_huella', ['integracion_id', 'entidad', 'huella'], unique=False)
    rls(op, 'integraciones', *HIJAS)
    _permisos(op.get_bind(), agregar=True)


def _permisos(con, agregar: bool) -> None:
    for rid, permisos in con.execute(sa.text("SELECT id, permisos FROM roles WHERE sistema = :si AND tipo = 'admin'"),
                                     {"si": True}).all():
        lista = json.loads(permisos) if isinstance(permisos, str) else list(permisos or [])
        nuevos = sorted(set(lista) | set(PERMISOS)) if agregar else sorted(set(lista) - set(PERMISOS))
        if nuevos != sorted(lista):
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(nuevos), "i": rid})


def downgrade() -> None:
    _permisos(op.get_bind(), agregar=False)
    for tabla in ('referencias_externas', 'integracion_ejecuciones', 'integracion_mapeos', 'integraciones'):
        op.drop_table(tabla)
