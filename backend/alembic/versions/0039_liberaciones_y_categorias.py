"""Estados de liberación y categorías de artículo como datos

- estados_liberacion: los códigos de la liberación comercial y logística
  según el ERP de la empresa (antes fijos en el código: C/P y 300/301/304).
  Se siembran los de SAP, que son los que ya tienen las OCs.
- categorias_articulo: categorías de los grupos de artículos y escalas de
  tallas (antes fijas: CALZADO/ROPA/ACCESORIO). Se siembran las que ya se usan.
- Los códigos de liberación de las OC admiten hasta 10 caracteres.

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0039'
down_revision = '0038'
branch_labels = None
depends_on = None

LIBERACIONES = [
    ("COMERCIAL", "C", "Released by commercial", True, False, True, "released, liberada, yes, si, y, s, 1, true, ok", 1),
    ("COMERCIAL", "P", "Pending commercial", False, False, False, "pending, pendiente, not released, no, n, 0, false, bloqueada", 2),
    ("LOGISTICA", "300", "Released by logistics", True, False, False, "released, liberada, liberado, yes, si, y, s, 1, true, ok", 1),
    ("LOGISTICA", "301", "Released with later changes", True, True, False,
     "changed, released changed, released with changes, modificada, cambiada, liberada con cambios", 2),
    ("LOGISTICA", "304", "Not released by logistics", False, False, True,
     "not released, no liberada, pending, pendiente, no, n, 0, false, bloqueada", 3),
]
CATEGORIAS = [("CALZADO", "Footwear"), ("ROPA", "Apparel"), ("ACCESORIO", "Accessories"), ("OTRO", "Other")]


def upgrade() -> None:
    lib = op.create_table(
        "estados_liberacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("codigo", sa.String(10), nullable=False),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("libera", sa.Boolean(), nullable=False),
        sa.Column("con_cambios", sa.Boolean(), nullable=False),
        sa.Column("predeterminado", sa.Boolean(), nullable=False),
        sa.Column("alias", sa.String(300), nullable=True),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("tipo", "codigo", name="uq_estados_liberacion_tipo_codigo"),
    )
    op.bulk_insert(lib, [dict(tipo=t, codigo=c, nombre=n, libera=li, con_cambios=cc, predeterminado=p, alias=a, orden=o, activo=True)
                         for t, c, n, li, cc, p, a, o in LIBERACIONES])
    cat = op.create_table(
        "categorias_articulo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(10), nullable=False),
        sa.Column("nombre", sa.String(100), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("codigo"),
    )
    op.bulk_insert(cat, [dict(codigo=c, nombre=n, activo=True) for c, n in CATEGORIAS])
    with op.batch_alter_table("ordenes_compra", schema=None) as b:
        b.alter_column("liberacion_comercial", existing_type=sa.String(1), type_=sa.String(10), existing_nullable=False)
        b.alter_column("liberacion_logistica", existing_type=sa.String(3), type_=sa.String(10), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("ordenes_compra", schema=None) as b:
        b.alter_column("liberacion_logistica", existing_type=sa.String(10), type_=sa.String(3), existing_nullable=False)
        b.alter_column("liberacion_comercial", existing_type=sa.String(10), type_=sa.String(1), existing_nullable=False)
    op.drop_table("categorias_articulo")
    op.drop_table("estados_liberacion")
