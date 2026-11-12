"""Producto genérico: marca, grupo y proveedor dejan de ser obligatorios

Un producto de cualquier rubro se crea con su código, su nombre y su unidad.
La marca y el grupo de artículos del artículo, y el proveedor del producto,
pasan a ser opcionales en la base: los pide la empresa (Datos maestros →
Artículos → datos obligatorios) o la familia del producto (sus campos
obligatorios) cuando los necesita.

Solo cambia la nulabilidad: no se mueve ni se borra ningún dato. La vuelta
atrás exige que no haya filas sin esos datos (si las hay, se detiene y lo
dice: completar un dato inventado no es una conversión segura).

Revision ID: 0091
Revises: 0090
Create Date: 2026-10-22 16:00:00
"""
import sqlalchemy as sa

from alembic import op

revision = '0091'
down_revision = '0090'
branch_labels = None
depends_on = None

COLUMNAS = (('articulos', 'marca_id'), ('articulos', 'grupo_id'), ('productos', 'proveedor_id'))


def upgrade() -> None:
    for tabla in ('articulos', 'productos'):
        with op.batch_alter_table(tabla, schema=None) as b:
            for t, columna in COLUMNAS:
                if t == tabla:
                    b.alter_column(columna, existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    con = op.get_bind()
    vacias = [f"{t}.{c}" for t, c in COLUMNAS if con.execute(sa.text(f"SELECT 1 FROM {t} WHERE {c} IS NULL LIMIT 1")).first()]
    if vacias:
        raise RuntimeError(f"No se puede volver atrás: hay filas sin {', '.join(vacias)}. Complételas antes.")
    for tabla in ('articulos', 'productos'):
        with op.batch_alter_table(tabla, schema=None) as b:
            for t, columna in COLUMNAS:
                if t == tabla:
                    b.alter_column(columna, existing_type=sa.Integer(), nullable=False)
