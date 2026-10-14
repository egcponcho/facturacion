"""Etiquetado genérico: subfamilias, reglas declarativas, campos lógicos y
trabajos de etiquetado (docs/ETIQUETADO_REDISENO.md)

- familias_etiquetado.padre_id: subfamilias (las existentes quedan como raíz).
- asignaciones_etiqueta pasa a ser una regla: nombre, prioridad numérica,
  condiciones, contexto, vigencia y control de concurrencia. Cada asignación
  existente se convierte en la regla equivalente: prioridad por ámbito
  (OC 500, artículo 400, producto 300, familia 200, general 100), sin
  condiciones ni contexto, con su `predeterminada`: se sigue eligiendo el
  mismo diseño para los mismos datos. El ámbito REGLA no tiene destino fijo.
- campos_etiqueta: campos lógicos con precedencia de fuentes.
- trabajos_etiqueta y trabajo_etiqueta_registros: borradores del asistente,
  registros validados y su resultado.
- generaciones_etiqueta: ejecución de un trabajo y su descarga e impresión.
- Permiso etiquetas.campos para los roles de sistema admin e interno.

Revertir: el downgrade borra las tablas nuevas y las columnas agregadas; las
reglas con ámbito REGLA (sin destino) se borran porque antes no existían.

Revision ID: 0073
Revises: 0072
Create Date: 2026-10-14 18:00:00
"""
import json

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0073'
down_revision = '0072'
branch_labels = None
depends_on = None

PRIORIDAD = {"OC": 500, "ARTICULO": 400, "PRODUCTO": 300, "FAMILIA": 200, "GENERAL": 100}
AMBITOS_ANTES = "ambito IN ('GENERAL', 'FAMILIA', 'PRODUCTO', 'ARTICULO', 'OC')"
AMBITOS_AHORA = "ambito IN ('GENERAL', 'FAMILIA', 'PRODUCTO', 'ARTICULO', 'OC', 'REGLA')"
_RESTO = (" OR (ambito = 'FAMILIA' AND familia_id IS NOT NULL AND producto_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL)"
          " OR (ambito = 'PRODUCTO' AND producto_id IS NOT NULL AND familia_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL)"
          " OR (ambito = 'ARTICULO' AND articulo_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL AND oc_id IS NULL)"
          " OR (ambito = 'OC' AND oc_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL)")
DESTINO_ANTES = ("(ambito = 'GENERAL' AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL AND oc_id IS NULL)"
                 + _RESTO)
DESTINO_AHORA = ("(ambito IN ('GENERAL', 'REGLA') AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL"
                 " AND oc_id IS NULL)" + _RESTO)
PERMISOS = {"admin": ["etiquetas.campos"], "interno": ["etiquetas.campos"]}
NUEVAS = ["campos_etiqueta", "trabajos_etiqueta", "trabajo_etiqueta_registros"]


def _org(tabla: str) -> list:
    return [sa.Column('organizacion_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name=f'fk_{tabla}_organizacion_id_organizaciones')]


def _permisos(con) -> None:
    for rid, tipo, permisos in con.execute(sa.text("SELECT id, tipo, permisos FROM roles WHERE sistema = :si"),
                                           {"si": True}).all():
        lista = json.loads(permisos) if isinstance(permisos, str) else list(permisos or [])
        nuevos = sorted(set(lista) | set(PERMISOS.get(tipo, [])))
        if nuevos != sorted(lista):
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(nuevos), "i": rid})


def _nombres_reglas(con) -> None:
    """Nombre legible y prioridad equivalente de cada asignación existente."""
    for aid, ambito, plantilla in con.execute(sa.text(
            "SELECT a.id, a.ambito, p.nombre FROM asignaciones_etiqueta a JOIN plantillas_etiqueta p ON p.id = a.plantilla_id")).all():
        con.execute(sa.text("UPDATE asignaciones_etiqueta SET prioridad = :p, nombre = :n, condiciones = :c, contexto = :x,"
                            " version = 1 WHERE id = :i"),
                    {"p": PRIORIDAD.get(ambito, 100), "n": f"{ambito.capitalize()} · {plantilla}"[:120], "c": "[]", "x": "{}",
                     "i": aid})


def upgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table('familias_etiquetado', schema=None) as b:
        b.add_column(sa.Column('padre_id', sa.Integer(), nullable=True))
        b.create_index(b.f('ix_familias_etiquetado_padre_id'), ['padre_id'], unique=False)
        b.create_foreign_key('fk_familias_etiquetado_padre_id_familias_etiquetado', 'familias_etiquetado', ['padre_id'], ['id'])
        b.create_foreign_key('fk_familias_etiquetado_padre_id_org', 'familias_etiquetado',
                             ['padre_id', 'organizacion_id'], ['id', 'organizacion_id'])

    with op.batch_alter_table('asignaciones_etiqueta', schema=None) as b:
        b.add_column(sa.Column('nombre', sa.String(length=120), nullable=True))
        b.add_column(sa.Column('prioridad', sa.Integer(), server_default='100', nullable=False))
        b.add_column(sa.Column('condiciones', sa.JSON(), nullable=True))
        b.add_column(sa.Column('contexto', sa.JSON(), nullable=True))
        b.add_column(sa.Column('vigente_desde', sa.Date(), nullable=True))
        b.add_column(sa.Column('vigente_hasta', sa.Date(), nullable=True))
        b.add_column(sa.Column('actualizada_por', sa.Integer(), nullable=True))
        b.add_column(sa.Column('actualizada_en', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('version', sa.Integer(), server_default='1', nullable=False))
        b.create_index(b.f('ix_asignaciones_etiqueta_prioridad'), ['prioridad'], unique=False)
        b.create_foreign_key('fk_asignaciones_etiqueta_actualizada_por_usuarios', 'usuarios', ['actualizada_por'], ['id'])
        b.drop_constraint('ck_asignaciones_etiqueta_ambito', type_='check')
        b.drop_constraint('ck_asignaciones_etiqueta_destino', type_='check')
        b.create_check_constraint('ck_asignaciones_etiqueta_ambito', AMBITOS_AHORA)
        b.create_check_constraint('ck_asignaciones_etiqueta_destino', DESTINO_AHORA)
        b.create_check_constraint('ck_asignaciones_etiqueta_vigencia',
                                  'vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde')
        b.create_check_constraint('ck_asignaciones_etiqueta_prioridad', 'prioridad BETWEEN 0 AND 100000')
    _nombres_reglas(con)
    with op.batch_alter_table('asignaciones_etiqueta', schema=None) as b:
        b.alter_column('condiciones', existing_type=sa.JSON(), nullable=False)
        b.alter_column('contexto', existing_type=sa.JSON(), nullable=False)

    op.create_table('campos_etiqueta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('clave', sa.String(length=40), nullable=False),
    sa.Column('etiqueta', sa.String(length=80), nullable=False),
    sa.Column('descripcion', sa.String(length=300), nullable=True),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('fuentes', sa.JSON(), nullable=False),
    sa.Column('politica', sa.String(length=10), nullable=False),
    sa.Column('modalidades', sa.JSON(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    *_org('campos_etiqueta'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], name='fk_campos_etiqueta_creado_por_usuarios'),
    sa.PrimaryKeyConstraint('id', name='pk_campos_etiqueta'),
    sa.UniqueConstraint('organizacion_id', 'clave', name='uq_campos_etiqueta_org_clave'),
    sa.CheckConstraint("tipo IN ('texto', 'numero', 'fecha')", name='ck_campos_etiqueta_tipo'),
    sa.CheckConstraint("politica IN ('PRIMERA', 'ADVERTIR', 'BLOQUEAR')", name='ck_campos_etiqueta_politica'),
    )
    with op.batch_alter_table('campos_etiqueta', schema=None) as b:
        b.create_index(b.f('ix_campos_etiqueta_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('trabajos_etiqueta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('origen', sa.String(length=10), nullable=False),
    sa.Column('estado', sa.String(length=12), nullable=False),
    sa.Column('paso', sa.Integer(), nullable=False),
    sa.Column('parametros', sa.JSON(), nullable=False),
    sa.Column('resumen', sa.JSON(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('progreso', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(), nullable=False),
    sa.Column('validado_en', sa.DateTime(), nullable=True),
    sa.Column('generado_en', sa.DateTime(), nullable=True),
    *_org('trabajos_etiqueta'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], name='fk_trabajos_etiqueta_creado_por_usuarios'),
    sa.PrimaryKeyConstraint('id', name='pk_trabajos_etiqueta'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_trabajos_etiqueta_id_org'),
    sa.CheckConstraint("origen IN ('OC', 'ARTICULOS', 'PACKING')", name='ck_trabajos_etiqueta_origen'),
    sa.CheckConstraint("estado IN ('BORRADOR', 'VALIDADO', 'EN_PROCESO', 'GENERADO', 'PARCIAL', 'ERROR', 'CANCELADO')",
                       name='ck_trabajos_etiqueta_estado'),
    sa.CheckConstraint('total IS NULL OR total >= 0', name='ck_trabajos_etiqueta_total'),
    sa.CheckConstraint('progreso IS NULL OR progreso >= 0', name='ck_trabajos_etiqueta_progreso'),
    sa.CheckConstraint('paso IS NULL OR paso >= 0', name='ck_trabajos_etiqueta_paso'),
    )
    with op.batch_alter_table('trabajos_etiqueta', schema=None) as b:
        b.create_index(b.f('ix_trabajos_etiqueta_organizacion_id'), ['organizacion_id'], unique=False)
        b.create_index(b.f('ix_trabajos_etiqueta_estado'), ['estado'], unique=False)
        b.create_index(b.f('ix_trabajos_etiqueta_creado_por'), ['creado_por'], unique=False)
        b.create_index(b.f('ix_trabajos_etiqueta_creado_en'), ['creado_en'], unique=False)

    with op.batch_alter_table('generaciones_etiqueta', schema=None) as b:
        b.add_column(sa.Column('trabajo_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('descargas', sa.Integer(), server_default='0', nullable=False))
        b.add_column(sa.Column('descargada_en', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('impresa_en', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('impresa_por', sa.Integer(), nullable=True))
        b.add_column(sa.Column('impresion', sa.JSON(), nullable=True))
        b.create_index(b.f('ix_generaciones_etiqueta_trabajo_id'), ['trabajo_id'], unique=False)
        b.create_foreign_key('fk_generaciones_etiqueta_trabajo_id_trabajos_etiqueta', 'trabajos_etiqueta', ['trabajo_id'], ['id'])
        b.create_foreign_key('fk_generaciones_etiqueta_trabajo_id_org', 'trabajos_etiqueta',
                             ['trabajo_id', 'organizacion_id'], ['id', 'organizacion_id'])
        b.create_foreign_key('fk_generaciones_etiqueta_impresa_por_usuarios', 'usuarios', ['impresa_por'], ['id'])
        b.create_check_constraint('ck_generaciones_etiqueta_descargas', 'descargas IS NULL OR descargas >= 0')

    op.create_table('trabajo_etiqueta_registros',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('trabajo_id', sa.Integer(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('clave', sa.String(length=80), nullable=False),
    sa.Column('referencia', sa.String(length=160), nullable=True),
    sa.Column('oc_id', sa.Integer(), nullable=True),
    sa.Column('posicion_id', sa.Integer(), nullable=True),
    sa.Column('articulo_id', sa.Integer(), nullable=True),
    sa.Column('pl_id', sa.Integer(), nullable=True),
    sa.Column('plantilla_id', sa.Integer(), nullable=True),
    sa.Column('version_id', sa.Integer(), nullable=True),
    sa.Column('regla_id', sa.Integer(), nullable=True),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('estado', sa.String(length=12), nullable=False),
    sa.Column('problemas', sa.JSON(), nullable=False),
    sa.Column('motivo', sa.String(length=300), nullable=True),
    sa.Column('generacion_id', sa.Integer(), nullable=True),
    *_org('trabajo_etiqueta_registros'),
    sa.ForeignKeyConstraint(['trabajo_id'], ['trabajos_etiqueta.id'], ondelete='CASCADE',
                            name='fk_trabajo_etiqueta_registros_trabajo_id_trabajos_etiqueta'),
    sa.ForeignKeyConstraint(['oc_id'], ['ordenes_compra.id'], name='fk_trabajo_etiqueta_registros_oc_id_ordenes_compra'),
    sa.ForeignKeyConstraint(['posicion_id'], ['posiciones_oc.id'], name='fk_trabajo_etiqueta_registros_posicion_id_posiciones_oc'),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], name='fk_trabajo_etiqueta_registros_articulo_id_articulos'),
    sa.ForeignKeyConstraint(['pl_id'], ['packing_lists.id'], name='fk_trabajo_etiqueta_registros_pl_id_packing_lists'),
    sa.ForeignKeyConstraint(['plantilla_id'], ['plantillas_etiqueta.id'],
                            name='fk_trabajo_etiqueta_registros_plantilla_id_plantillas_etiqueta'),
    sa.ForeignKeyConstraint(['version_id'], ['versiones_plantilla.id'],
                            name='fk_trabajo_etiqueta_registros_version_id_versiones_plantilla'),
    sa.ForeignKeyConstraint(['regla_id'], ['asignaciones_etiqueta.id'], ondelete='SET NULL',
                            name='fk_trabajo_etiqueta_registros_regla_id_asignaciones_etiqueta'),
    sa.ForeignKeyConstraint(['generacion_id'], ['generaciones_etiqueta.id'], ondelete='SET NULL',
                            name='fk_trabajo_etiqueta_registros_generacion_id_generaciones_etiqueta'),
    sa.ForeignKeyConstraint(['trabajo_id', 'organizacion_id'], ['trabajos_etiqueta.id', 'trabajos_etiqueta.organizacion_id'],
                            name='fk_trabajo_etiqueta_registros_trabajo_id_org'),
    sa.ForeignKeyConstraint(['generacion_id', 'organizacion_id'],
                            ['generaciones_etiqueta.id', 'generaciones_etiqueta.organizacion_id'],
                            name='fk_trabajo_etiqueta_registros_generacion_id_org'),
    sa.PrimaryKeyConstraint('id', name='pk_trabajo_etiqueta_registros'),
    sa.UniqueConstraint('trabajo_id', 'clave', name='uq_trabajo_etiqueta_registros_trabajo_clave'),
    sa.CheckConstraint("estado IN ('LISTO', 'ADVERTENCIA', 'ERROR', 'GENERADO', 'OMITIDO')",
                       name='ck_trabajo_etiqueta_registros_estado'),
    sa.CheckConstraint('cantidad IS NULL OR cantidad >= 0', name='ck_trabajo_etiqueta_registros_cantidad'),
    )
    with op.batch_alter_table('trabajo_etiqueta_registros', schema=None) as b:
        for col in ('organizacion_id', 'trabajo_id', 'oc_id', 'posicion_id', 'articulo_id', 'pl_id', 'plantilla_id', 'version_id',
                    'regla_id', 'estado', 'generacion_id'):
            b.create_index(b.f(f'ix_trabajo_etiqueta_registros_{col}'), [col], unique=False)

    rls(op, *NUEVAS)
    _permisos(con)


def downgrade() -> None:
    op.drop_table('trabajo_etiqueta_registros')
    with op.batch_alter_table('generaciones_etiqueta', schema=None) as b:
        b.drop_constraint('ck_generaciones_etiqueta_descargas', type_='check')
        b.drop_constraint('fk_generaciones_etiqueta_impresa_por_usuarios', type_='foreignkey')
        b.drop_constraint('fk_generaciones_etiqueta_trabajo_id_org', type_='foreignkey')
        b.drop_constraint('fk_generaciones_etiqueta_trabajo_id_trabajos_etiqueta', type_='foreignkey')
        b.drop_index(b.f('ix_generaciones_etiqueta_trabajo_id'))
        for col in ('impresion', 'impresa_por', 'impresa_en', 'descargada_en', 'descargas', 'trabajo_id'):
            b.drop_column(col)
    op.drop_table('trabajos_etiqueta')
    op.drop_table('campos_etiqueta')
    op.execute("DELETE FROM asignaciones_etiqueta WHERE ambito = 'REGLA'")
    with op.batch_alter_table('asignaciones_etiqueta', schema=None) as b:
        b.drop_constraint('ck_asignaciones_etiqueta_prioridad', type_='check')
        b.drop_constraint('ck_asignaciones_etiqueta_vigencia', type_='check')
        b.drop_constraint('ck_asignaciones_etiqueta_destino', type_='check')
        b.drop_constraint('ck_asignaciones_etiqueta_ambito', type_='check')
        b.create_check_constraint('ck_asignaciones_etiqueta_ambito', AMBITOS_ANTES)
        b.create_check_constraint('ck_asignaciones_etiqueta_destino', DESTINO_ANTES)
        b.drop_constraint('fk_asignaciones_etiqueta_actualizada_por_usuarios', type_='foreignkey')
        b.drop_index(b.f('ix_asignaciones_etiqueta_prioridad'))
        for col in ('version', 'actualizada_en', 'actualizada_por', 'vigente_hasta', 'vigente_desde', 'contexto', 'condiciones',
                    'prioridad', 'nombre'):
            b.drop_column(col)
    with op.batch_alter_table('familias_etiquetado', schema=None) as b:
        b.drop_constraint('fk_familias_etiquetado_padre_id_org', type_='foreignkey')
        b.drop_constraint('fk_familias_etiquetado_padre_id_familias_etiquetado', type_='foreignkey')
        b.drop_index(b.f('ix_familias_etiquetado_padre_id'))
        b.drop_column('padre_id')
