"""Etiquetado: familias de etiquetado, plantillas con versiones, asignaciones
y generaciones (docs/ETIQUETADO.md)

- Tablas nuevas, todas de la organización (RLS en PostgreSQL) y con llaves de
  coherencia de organización hacia su padre.
- articulos.familia_etiquetado_id: la familia de etiquetado del artículo
  (vacía en los existentes; no se deduce de la clasificación arancelaria).
- Permisos etiquetas.* para los roles de fábrica: administración todos;
  interno todos salvo aprobar; proveedor ver y generar.

Revertir: el downgrade borra las tablas del módulo (con sus diseños e
historial) y la columna del artículo.

Revision ID: 0070
Revises: 0069
Create Date: 2026-10-14 08:00:00
"""
import json

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0070'
down_revision = '0069'
branch_labels = None
depends_on = None

TABLAS = ["familias_etiquetado", "plantillas_etiqueta", "versiones_plantilla", "asignaciones_etiqueta",
          "generaciones_etiqueta", "generacion_items"]
# Coherencia de organización (copia de app/modelos/referencias.py: lo que agrega esta migración)
COHERENCIA = {
    "articulos": [("familia_etiquetado_id", "familias_etiquetado")],
    "plantillas_etiqueta": [("familia_id", "familias_etiquetado")],
    "versiones_plantilla": [("plantilla_id", "plantillas_etiqueta")],
    "asignaciones_etiqueta": [("plantilla_id", "plantillas_etiqueta"), ("familia_id", "familias_etiquetado")],
    "generacion_items": [("generacion_id", "generaciones_etiqueta"), ("version_id", "versiones_plantilla")],
}
PERMISOS = {
    "admin": ["etiquetas.ver", "etiquetas.generar", "etiquetas.disenar", "etiquetas.aprobar", "etiquetas.asignar",
              "etiquetas.familias"],
    "interno": ["etiquetas.ver", "etiquetas.generar", "etiquetas.disenar", "etiquetas.asignar", "etiquetas.familias"],
    "proveedor": ["etiquetas.ver", "etiquetas.generar"],
}


def _permisos(con) -> None:
    for rid, tipo, permisos in con.execute(sa.text("SELECT id, tipo, permisos FROM roles WHERE sistema = :si"),
                                           {"si": True}).all():
        lista = json.loads(permisos) if isinstance(permisos, str) else list(permisos or [])
        nuevos = sorted(set(lista) | set(PERMISOS.get(tipo, [])))
        if nuevos != sorted(lista):
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(nuevos), "i": rid})


def upgrade() -> None:
    op.create_table('familias_etiquetado',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('descripcion', sa.String(length=300), nullable=True),
    sa.Column('campos', sa.JSON(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_familias_etiquetado_id_org'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_familias_etiquetado_org_codigo')
    )
    with op.batch_alter_table('familias_etiquetado', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_familias_etiquetado_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('plantillas_etiqueta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('descripcion', sa.String(length=500), nullable=True),
    sa.Column('modalidad', sa.String(length=12), nullable=False),
    sa.Column('unidad', sa.String(length=10), nullable=False),
    sa.Column('familia_id', sa.Integer(), nullable=True),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('version_vigente_id', sa.Integer(), nullable=True),
    sa.Column('origen_id', sa.Integer(), nullable=True),
    sa.Column('creada_por', sa.Integer(), nullable=True),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('actualizada_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("estado IN ('ACTIVA', 'ARCHIVADA')", name='ck_plantillas_etiqueta_estado'),
    sa.CheckConstraint("modalidad IN ('ARTICULO', 'OC', 'OC_ARTICULO')", name='ck_plantillas_etiqueta_modalidad'),
    sa.CheckConstraint("unidad IN ('ORDEN', 'LINEA', 'UNIDAD', 'BULTO', 'MANUAL')", name='ck_plantillas_etiqueta_unidad'),
    sa.ForeignKeyConstraint(['creada_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['familia_id'], ['familias_etiquetado.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['origen_id'], ['plantillas_etiqueta.id'], name='fk_plantillas_etiqueta_origen_id'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_plantillas_etiqueta_id_org'),
    sa.UniqueConstraint('organizacion_id', 'nombre', name='uq_plantillas_etiqueta_org_nombre')
    )
    with op.batch_alter_table('plantillas_etiqueta', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plantillas_etiqueta_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_plantillas_etiqueta_familia_id'), ['familia_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_plantillas_etiqueta_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('asignaciones_etiqueta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plantilla_id', sa.Integer(), nullable=False),
    sa.Column('ambito', sa.String(length=10), nullable=False),
    sa.Column('familia_id', sa.Integer(), nullable=True),
    sa.Column('producto_id', sa.Integer(), nullable=True),
    sa.Column('articulo_id', sa.Integer(), nullable=True),
    sa.Column('oc_id', sa.Integer(), nullable=True),
    sa.Column('predeterminada', sa.Boolean(), nullable=False),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('motivo', sa.String(length=300), nullable=True),
    sa.Column('creada_por', sa.Integer(), nullable=True),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("(ambito = 'GENERAL' AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL) OR (ambito = 'FAMILIA' AND familia_id IS NOT NULL AND producto_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL) OR (ambito = 'PRODUCTO' AND producto_id IS NOT NULL AND familia_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL) OR (ambito = 'ARTICULO' AND articulo_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL AND oc_id IS NULL) OR (ambito = 'OC' AND oc_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL)", name='ck_asignaciones_etiqueta_destino'),
    sa.CheckConstraint("ambito IN ('GENERAL', 'FAMILIA', 'PRODUCTO', 'ARTICULO', 'OC')", name='ck_asignaciones_etiqueta_ambito'),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], ),
    sa.ForeignKeyConstraint(['creada_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['familia_id'], ['familias_etiquetado.id'], ),
    sa.ForeignKeyConstraint(['oc_id'], ['ordenes_compra.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['plantilla_id'], ['plantillas_etiqueta.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('asignaciones_etiqueta', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_asignaciones_etiqueta_articulo_id'), ['articulo_id'], unique=False)
        batch_op.create_index('ix_asignaciones_etiqueta_destino', ['ambito', 'familia_id', 'producto_id', 'articulo_id', 'oc_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_asignaciones_etiqueta_familia_id'), ['familia_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_asignaciones_etiqueta_oc_id'), ['oc_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_asignaciones_etiqueta_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_asignaciones_etiqueta_plantilla_id'), ['plantilla_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_asignaciones_etiqueta_producto_id'), ['producto_id'], unique=False)

    op.create_table('generaciones_etiqueta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('oc_id', sa.Integer(), nullable=True),
    sa.Column('modalidad', sa.String(length=12), nullable=False),
    sa.Column('unidad', sa.String(length=10), nullable=False),
    sa.Column('formato', sa.String(length=4), nullable=False),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('parametros', sa.JSON(), nullable=False),
    sa.Column('advertencias', sa.JSON(), nullable=False),
    sa.Column('archivo', sa.String(length=200), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('creada_por', sa.Integer(), nullable=True),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("estado IN ('GENERADA', 'PRUEBA')", name='ck_generaciones_etiqueta_estado'),
    sa.CheckConstraint("formato IN ('PDF', 'PNG', 'SVG', 'ZIP')", name='ck_generaciones_etiqueta_formato'),
    sa.CheckConstraint('total >= 0', name='ck_generaciones_etiqueta_total'),
    sa.ForeignKeyConstraint(['creada_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['oc_id'], ['ordenes_compra.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_generaciones_etiqueta_id_org')
    )
    with op.batch_alter_table('generaciones_etiqueta', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_generaciones_etiqueta_creada_en'), ['creada_en'], unique=False)
        batch_op.create_index(batch_op.f('ix_generaciones_etiqueta_creada_por'), ['creada_por'], unique=False)
        batch_op.create_index(batch_op.f('ix_generaciones_etiqueta_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_generaciones_etiqueta_oc_id'), ['oc_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generaciones_etiqueta_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('versiones_plantilla',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plantilla_id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('diseno', sa.JSON(), nullable=False),
    sa.Column('ancho_mm', sa.Float(), nullable=False),
    sa.Column('alto_mm', sa.Float(), nullable=False),
    sa.Column('cambios', sa.Text(), nullable=True),
    sa.Column('basada_en_id', sa.Integer(), nullable=True),
    sa.Column('creada_por', sa.Integer(), nullable=True),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('actualizada_en', sa.DateTime(), nullable=False),
    sa.Column('enviada_por', sa.Integer(), nullable=True),
    sa.Column('enviada_en', sa.DateTime(), nullable=True),
    sa.Column('revisada_por', sa.Integer(), nullable=True),
    sa.Column('revisada_en', sa.DateTime(), nullable=True),
    sa.Column('aprobada_por', sa.Integer(), nullable=True),
    sa.Column('aprobada_en', sa.DateTime(), nullable=True),
    sa.Column('comentario', sa.String(length=1000), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("estado IN ('BORRADOR', 'PENDIENTE', 'APROBADA', 'RECHAZADA', 'ARCHIVADA')", name='ck_versiones_plantilla_estado'),
    sa.CheckConstraint('ancho_mm > 0 AND alto_mm > 0', name='ck_versiones_plantilla_medidas'),
    sa.ForeignKeyConstraint(['basada_en_id'], ['versiones_plantilla.id'], name='fk_versiones_plantilla_basada_en_id'),
    sa.ForeignKeyConstraint(['creada_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['enviada_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['plantilla_id'], ['plantillas_etiqueta.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['revisada_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['aprobada_por'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_versiones_plantilla_id_org'),
    sa.UniqueConstraint('plantilla_id', 'numero', name='uq_versiones_plantilla_plantilla_numero')
    )
    with op.batch_alter_table('versiones_plantilla', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_versiones_plantilla_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_versiones_plantilla_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_versiones_plantilla_plantilla_id'), ['plantilla_id'], unique=False)

    op.create_table('generacion_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('generacion_id', sa.Integer(), nullable=False),
    sa.Column('plantilla_id', sa.Integer(), nullable=False),
    sa.Column('version_id', sa.Integer(), nullable=False),
    sa.Column('articulo_id', sa.Integer(), nullable=True),
    sa.Column('posicion_id', sa.Integer(), nullable=True),
    sa.Column('familia_id', sa.Integer(), nullable=True),
    sa.Column('referencia', sa.String(length=120), nullable=True),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('valores', sa.JSON(), nullable=False),
    sa.Column('motivo', sa.String(length=200), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('cantidad >= 1', name='ck_generacion_items_cantidad'),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], ),
    sa.ForeignKeyConstraint(['familia_id'], ['familias_etiquetado.id'], ),
    sa.ForeignKeyConstraint(['generacion_id'], ['generaciones_etiqueta.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['plantilla_id'], ['plantillas_etiqueta.id'], ),
    sa.ForeignKeyConstraint(['posicion_id'], ['posiciones_oc.id'], ),
    sa.ForeignKeyConstraint(['version_id'], ['versiones_plantilla.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('generacion_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_generacion_items_articulo_id'), ['articulo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generacion_items_familia_id'), ['familia_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generacion_items_generacion_id'), ['generacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generacion_items_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generacion_items_plantilla_id'), ['plantilla_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generacion_items_posicion_id'), ['posicion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_generacion_items_version_id'), ['version_id'], unique=False)

    with op.batch_alter_table('articulos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('familia_etiquetado_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_articulos_familia_etiquetado_id'), ['familia_etiquetado_id'], unique=False)
        batch_op.create_foreign_key('fk_articulos_familia_etiquetado_id', 'familias_etiquetado', ['familia_etiquetado_id'], ['id'])

    # La versión vigente apunta a una tabla creada después (referencia circular)
    with op.batch_alter_table('plantillas_etiqueta', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_plantillas_etiqueta_version_vigente_id', 'versiones_plantilla',
                                    ['version_vigente_id'], ['id'])
    rls(op, *TABLAS)
    for tabla, lista in COHERENCIA.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, padre in lista:
                b.create_foreign_key(f"fk_{tabla}_{col}_org", padre, [col, "organizacion_id"], ["id", "organizacion_id"])
    _permisos(op.get_bind())


def downgrade() -> None:
    with op.batch_alter_table('plantillas_etiqueta', schema=None) as batch_op:
        batch_op.drop_constraint('fk_plantillas_etiqueta_version_vigente_id', type_='foreignkey')
    with op.batch_alter_table('articulos', schema=None) as batch_op:
        batch_op.drop_constraint('fk_articulos_familia_etiquetado_id_org', type_='foreignkey')
        batch_op.drop_constraint('fk_articulos_familia_etiquetado_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_articulos_familia_etiquetado_id'))
        batch_op.drop_column('familia_etiquetado_id')

    with op.batch_alter_table('generacion_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_generacion_items_version_id'))
        batch_op.drop_index(batch_op.f('ix_generacion_items_posicion_id'))
        batch_op.drop_index(batch_op.f('ix_generacion_items_plantilla_id'))
        batch_op.drop_index(batch_op.f('ix_generacion_items_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_generacion_items_generacion_id'))
        batch_op.drop_index(batch_op.f('ix_generacion_items_familia_id'))
        batch_op.drop_index(batch_op.f('ix_generacion_items_articulo_id'))

    op.drop_table('generacion_items')
    with op.batch_alter_table('versiones_plantilla', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_versiones_plantilla_plantilla_id'))
        batch_op.drop_index(batch_op.f('ix_versiones_plantilla_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_versiones_plantilla_estado'))

    op.drop_table('versiones_plantilla')
    with op.batch_alter_table('generaciones_etiqueta', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_generaciones_etiqueta_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_generaciones_etiqueta_oc_id'))
        batch_op.drop_index(batch_op.f('ix_generaciones_etiqueta_estado'))
        batch_op.drop_index(batch_op.f('ix_generaciones_etiqueta_creada_por'))
        batch_op.drop_index(batch_op.f('ix_generaciones_etiqueta_creada_en'))

    op.drop_table('generaciones_etiqueta')
    with op.batch_alter_table('asignaciones_etiqueta', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_asignaciones_etiqueta_producto_id'))
        batch_op.drop_index(batch_op.f('ix_asignaciones_etiqueta_plantilla_id'))
        batch_op.drop_index(batch_op.f('ix_asignaciones_etiqueta_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_asignaciones_etiqueta_oc_id'))
        batch_op.drop_index(batch_op.f('ix_asignaciones_etiqueta_familia_id'))
        batch_op.drop_index('ix_asignaciones_etiqueta_destino')
        batch_op.drop_index(batch_op.f('ix_asignaciones_etiqueta_articulo_id'))

    op.drop_table('asignaciones_etiqueta')
    with op.batch_alter_table('plantillas_etiqueta', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plantillas_etiqueta_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_plantillas_etiqueta_familia_id'))
        batch_op.drop_index(batch_op.f('ix_plantillas_etiqueta_estado'))

    op.drop_table('plantillas_etiqueta')
    with op.batch_alter_table('familias_etiquetado', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_familias_etiquetado_organizacion_id'))

    op.drop_table('familias_etiquetado')
