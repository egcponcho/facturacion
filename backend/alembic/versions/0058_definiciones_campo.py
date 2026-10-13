"""Campos propios: definiciones en tabla

Las definiciones de los campos propios estaban en
organizaciones.configuracion["campos_propios"] (JSON sin restricciones). Pasan a
definiciones_campo, con clave única por entidad, tipo y entidad acotados y
orden; los valores siguen en la columna `extra` de cada registro.

Revision ID: 0058
Revises: 0057
Create Date: 2026-10-13 00:00:00
"""
import json

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls

ENTIDADES = ('articulos', 'proveedores', 'sociedades', 'centros', 'marcas', 'transportistas', 'ordenes', 'facturas')
TIPOS = ('texto', 'numero', 'fecha', 'bool', 'opcion')


revision = '0058'
down_revision = '0057'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('definiciones_campo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('entidad', sa.String(length=20), nullable=False),
    sa.Column('clave', sa.String(length=30), nullable=False),
    sa.Column('etiqueta', sa.String(length=60), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('opciones', sa.JSON(), nullable=False),
    sa.Column('obligatorio', sa.Boolean(), nullable=False),
    sa.Column('indexado', sa.Boolean(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("entidad IN ('articulos', 'proveedores', 'sociedades', 'centros', 'marcas', 'transportistas', 'ordenes', 'facturas')", name='ck_definiciones_campo_entidad'),
    sa.CheckConstraint("tipo IN ('texto', 'numero', 'fecha', 'bool', 'opcion')", name='ck_definiciones_campo_tipo'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'entidad', 'clave', name='uq_definiciones_campo_org_entidad_clave')
    )
    with op.batch_alter_table('definiciones_campo', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_definiciones_campo_entidad'), ['entidad'], unique=False)
        batch_op.create_index(batch_op.f('ix_definiciones_campo_organizacion_id'), ['organizacion_id'], unique=False)
    rls(op, 'definiciones_campo')

    con = op.get_bind()
    tabla = sa.table('definiciones_campo', *(sa.column(c) for c in (
        'organizacion_id', 'entidad', 'clave', 'etiqueta', 'tipo', 'obligatorio', 'indexado', 'orden')),
        sa.column('opciones', sa.JSON()))
    for org_id, conf in con.execute(sa.text("SELECT id, configuracion FROM organizaciones")).all():
        conf = json.loads(conf) if isinstance(conf, str) else (conf or {})
        definiciones = conf.pop('campos_propios', None) or {}
        filas = []
        for entidad, campos in definiciones.items():
            if entidad not in ENTIDADES:
                continue
            vistas = set()
            for i, c in enumerate(campos or [], start=1):
                clave = str(c.get('clave') or '')[:30]
                if not clave or clave in vistas or c.get('tipo') not in TIPOS:
                    continue
                vistas.add(clave)
                filas.append({'organizacion_id': org_id, 'entidad': entidad, 'clave': clave,
                              'etiqueta': str(c.get('etiqueta') or clave)[:60], 'tipo': c['tipo'],
                              'opciones': list(c.get('opciones') or []) if c['tipo'] == 'opcion' else [],
                              'obligatorio': bool(c.get('obligatorio')), 'indexado': False, 'orden': i})
        if filas:
            op.bulk_insert(tabla, filas)
        if definiciones:
            con.execute(sa.text("UPDATE organizaciones SET configuracion = :c WHERE id = :i"),
                        {"c": json.dumps(conf), "i": org_id})


def downgrade() -> None:
    con = op.get_bind()
    por_org: dict = {}
    for fila in con.execute(sa.text("SELECT organizacion_id, entidad, clave, etiqueta, tipo, opciones, obligatorio "
                                     "FROM definiciones_campo ORDER BY organizacion_id, entidad, orden, id")).mappings():
        opciones = json.loads(fila['opciones']) if isinstance(fila['opciones'], str) else (fila['opciones'] or [])
        por_org.setdefault(fila['organizacion_id'], {}).setdefault(fila['entidad'], []).append(
            {'clave': fila['clave'], 'etiqueta': fila['etiqueta'], 'tipo': fila['tipo'], 'obligatorio': bool(fila['obligatorio']),
             **({'opciones': opciones} if fila['tipo'] == 'opcion' else {})})
    for org_id, definiciones in por_org.items():
        conf = con.execute(sa.text("SELECT configuracion FROM organizaciones WHERE id = :i"), {"i": org_id}).scalar()
        conf = json.loads(conf) if isinstance(conf, str) else (conf or {})
        conf['campos_propios'] = definiciones
        con.execute(sa.text("UPDATE organizaciones SET configuracion = :c WHERE id = :i"), {"c": json.dumps(conf), "i": org_id})
    with op.batch_alter_table('definiciones_campo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_definiciones_campo_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_definiciones_campo_entidad'))

    op.drop_table('definiciones_campo')
