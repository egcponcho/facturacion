"""Etiquetado: ejecución duradera de los trabajos, idempotencia y coherencia
de organización (docs/ETIQUETADO_REDISENO.md §11)

- trabajos_etiqueta: ejecutor, arriendo_hasta, latido_en, intentos. El
  proceso que genera en segundo plano tiene el trabajo arrendado y renueva el
  arriendo; si se detiene, otro proceso (o instancia) lo retoma al vencer.
- generacion_items.trabajo_registro_id (único): un registro de un trabajo
  produce un solo grupo de etiquetas; una ejecución repetida falla en la base
  en vez de duplicar etiquetas. Los ítems ya generados no se enlazan (no hay
  una correspondencia segura con sus registros): la regla vale desde aquí.
- Llaves de coherencia de organización que faltaban (registros del trabajo,
  ítems y ejecuciones, reglas). Si una base ya tiene filas que las violan no
  se borran: en PostgreSQL la llave se crea NOT VALID (rige para lo nuevo) y
  en SQLite se omite; en ambos casos se avisa en el registro de la migración.

Revision ID: 0074
Revises: 0073
Create Date: 2026-10-15 09:00:00
"""
import logging

from alembic import op
import sqlalchemy as sa

revision = '0074'
down_revision = '0073'
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0074")
PADRES_NUEVOS = ["asignaciones_etiqueta", "trabajo_etiqueta_registros"]
COHERENCIA = {
    "trabajo_etiqueta_registros": [("oc_id", "ordenes_compra"), ("posicion_id", "posiciones_oc"), ("articulo_id", "articulos"),
                                   ("pl_id", "packing_lists"), ("plantilla_id", "plantillas_etiqueta"),
                                   ("version_id", "versiones_plantilla"), ("regla_id", "asignaciones_etiqueta")],
    "asignaciones_etiqueta": [("producto_id", "productos"), ("articulo_id", "articulos"), ("oc_id", "ordenes_compra")],
    "generacion_items": [("plantilla_id", "plantillas_etiqueta"), ("articulo_id", "articulos"), ("posicion_id", "posiciones_oc"),
                         ("familia_id", "familias_etiquetado"), ("trabajo_registro_id", "trabajo_etiqueta_registros")],
    "generaciones_etiqueta": [("oc_id", "ordenes_compra")],
}


def _violaciones(con, tabla: str, col: str, padre: str) -> int:
    return con.execute(sa.text(
        f"SELECT count(*) FROM {tabla} h WHERE h.{col} IS NOT NULL AND NOT EXISTS "
        f"(SELECT 1 FROM {padre} p WHERE p.id = h.{col} AND p.organizacion_id = h.organizacion_id)")).scalar() or 0


def upgrade() -> None:
    con = op.get_bind()
    pg = con.dialect.name == "postgresql"
    with op.batch_alter_table('trabajos_etiqueta', schema=None) as b:
        b.add_column(sa.Column('ejecutor', sa.String(length=80), nullable=True))
        b.add_column(sa.Column('arriendo_hasta', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('latido_en', sa.DateTime(), nullable=True))
        b.add_column(sa.Column('intentos', sa.Integer(), server_default='0', nullable=False))
        b.create_index(b.f('ix_trabajos_etiqueta_arriendo_hasta'), ['arriendo_hasta'], unique=False)
    for tabla in PADRES_NUEVOS:
        with op.batch_alter_table(tabla, schema=None) as b:
            b.create_unique_constraint(f'uq_{tabla}_id_org', ['id', 'organizacion_id'])
    with op.batch_alter_table('generacion_items', schema=None) as b:
        b.add_column(sa.Column('trabajo_registro_id', sa.Integer(), nullable=True))
        b.create_unique_constraint('uq_generacion_items_trabajo_registro_id', ['trabajo_registro_id'])
        b.create_foreign_key('fk_generacion_items_trabajo_registro_id_registros', 'trabajo_etiqueta_registros',
                             ['trabajo_registro_id'], ['id'], ondelete='SET NULL')
    for tabla, lista in COHERENCIA.items():
        validas = []
        for col, padre in lista:
            malas = _violaciones(con, tabla, col, padre)
            nombre = f"fk_{tabla}_{col}_org"
            if not malas:
                validas.append((col, padre))
                continue
            log.warning("%s.%s: %s filas apuntan a %s de otra organización; la llave %s rige solo para filas nuevas",
                        tabla, col, malas, padre, nombre)
            if pg:
                op.execute(f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} FOREIGN KEY ({col}, organizacion_id) "
                           f"REFERENCES {padre} (id, organizacion_id) NOT VALID")
        if validas:
            with op.batch_alter_table(tabla, schema=None) as b:
                for col, padre in validas:
                    b.create_foreign_key(f"fk_{tabla}_{col}_org", padre, [col, "organizacion_id"], ["id", "organizacion_id"])


def downgrade() -> None:
    con = op.get_bind()
    insp = sa.inspect(con)
    for tabla, lista in COHERENCIA.items():
        existentes = {f["name"] for f in insp.get_foreign_keys(tabla)}
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, _ in lista:
                if f"fk_{tabla}_{col}_org" in existentes:
                    b.drop_constraint(f"fk_{tabla}_{col}_org", type_='foreignkey')
    with op.batch_alter_table('generacion_items', schema=None) as b:
        b.drop_constraint('fk_generacion_items_trabajo_registro_id_registros', type_='foreignkey')
        b.drop_constraint('uq_generacion_items_trabajo_registro_id', type_='unique')
        b.drop_column('trabajo_registro_id')
    for tabla in PADRES_NUEVOS:
        with op.batch_alter_table(tabla, schema=None) as b:
            b.drop_constraint(f'uq_{tabla}_id_org', type_='unique')
    with op.batch_alter_table('trabajos_etiqueta', schema=None) as b:
        b.drop_index(b.f('ix_trabajos_etiqueta_arriendo_hasta'))
        for col in ('intentos', 'latido_en', 'arriendo_hasta', 'ejecutor'):
            b.drop_column(col)
