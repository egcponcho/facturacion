"""Nombres técnicos neutros

- posiciones_oc.codigo_sap y factura_lineas.codigo_sap → codigo_articulo: el
  nombre técnico no nombra un ERP. Lo que ve el usuario sigue siendo
  configurable con la terminología. Las claves guardadas en JSON (perfiles de
  importación, reportes guardados, borradores de OC, preferencias de tablas y
  configuración) se actualizan; los archivos que traen «codigo_sap» se siguen
  leyendo como alias.
- historial.factura_id → raiz_tipo y raiz_id: la bitácora genérica ya no
  tiene una columna de un solo módulo; el documento raíz puede ser cualquiera.

Revision ID: 0056
Revises: 0055
Create Date: 2026-10-13 00:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None

# (tabla, columna JSON) donde pueden estar guardadas claves de campos
JSONS = [("perfiles_importacion", "columnas"), ("perfiles_importacion", "valores"), ("reportes", "definicion"),
         ("ordenes_compra", "borrador"), ("usuarios", "preferencias"), ("organizaciones", "configuracion"),
         ("roles", "datos_ocultos")]


def _reemplazar(con, viejo: str, nuevo: str) -> None:
    for tabla, col in JSONS:
        for i, v in con.execute(sa.text(f"SELECT id, {col} FROM {tabla} WHERE {col} IS NOT NULL")).all():
            texto = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
            if f'"{viejo}"' in texto:
                con.execute(sa.text(f"UPDATE {tabla} SET {col} = :v WHERE id = :i"),
                            {"v": texto.replace(f'"{viejo}"', f'"{nuevo}"'), "i": i})


def upgrade() -> None:
    con = op.get_bind()
    for tabla in ("posiciones_oc", "factura_lineas"):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.alter_column("codigo_sap", new_column_name="codigo_articulo", existing_type=sa.String(40), existing_nullable=False)
    _reemplazar(con, "codigo_sap", "codigo_articulo")
    with op.batch_alter_table("historial", schema=None) as b:
        b.add_column(sa.Column("raiz_tipo", sa.String(30), nullable=True))
        b.add_column(sa.Column("raiz_id", sa.Integer(), nullable=True))
    con.execute(sa.text("UPDATE historial SET raiz_tipo = 'factura', raiz_id = factura_id WHERE factura_id IS NOT NULL"))
    with op.batch_alter_table("historial", schema=None) as b:
        b.drop_index("ix_historial_factura_id")
        b.drop_column("factura_id")
        b.create_index("ix_historial_raiz", ["raiz_tipo", "raiz_id"], unique=False)


def downgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table("historial", schema=None) as b:
        b.drop_index("ix_historial_raiz")
        b.add_column(sa.Column("factura_id", sa.Integer(), nullable=True))
        b.create_index("ix_historial_factura_id", ["factura_id"], unique=False)
    con.execute(sa.text("UPDATE historial SET factura_id = raiz_id WHERE raiz_tipo = 'factura'"))
    with op.batch_alter_table("historial", schema=None) as b:
        b.drop_column("raiz_id")
        b.drop_column("raiz_tipo")
    _reemplazar(con, "codigo_articulo", "codigo_sap")
    for tabla in ("posiciones_oc", "factura_lineas"):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.alter_column("codigo_articulo", new_column_name="codigo_sap", existing_type=sa.String(40), existing_nullable=False)
