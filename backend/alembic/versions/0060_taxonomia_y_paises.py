"""Taxonomía única y países del arancel ligados al catálogo ISO

- categorias_articulo.dominio → dominios_clasificacion.codigo: la línea
  comercial (calzado, ropa…) dice qué dominio de clasificación ofrece primero
  la ficha técnica. Las líneas de fábrica toman el suyo por nombre.
- categorias_producto.dominio pasa a ser llave foránea (antes texto libre);
  un dominio inexistente se crea como borrador para no perder el dato.
- paises_arancel.iso → paises.codigo: el país del arancel es una extensión
  1:1 del país ISO; un código que no esté en el catálogo se agrega.

Revision ID: 0060
Revises: 0059
Create Date: 2026-10-13 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0060'
down_revision = '0059'
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    # Países del arancel que no estén en el catálogo ISO
    con.execute(sa.text("INSERT INTO paises (codigo, nombre, activo) SELECT pa.iso, pa.nombre, :t FROM paises_arancel pa "
                        "WHERE NOT EXISTS (SELECT 1 FROM paises p WHERE p.codigo = pa.iso)"), {"t": True})
    # Dominios citados por categorías de producto que no existan
    for (dominio,) in con.execute(sa.text(
            "SELECT DISTINCT dominio FROM categorias_producto c WHERE dominio IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM dominios_clasificacion d WHERE d.codigo = c.dominio)")).all():
        con.execute(sa.text("INSERT INTO dominios_clasificacion (codigo, nombre, modo, orden, activo, estado) "
                            "VALUES (:c, :c, 'AUTO', 999, :f, 'BORRADOR')"), {"c": dominio, "f": False})

    with op.batch_alter_table('categorias_articulo', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dominio', sa.String(length=30), nullable=True))
        batch_op.create_index(batch_op.f('ix_categorias_articulo_dominio'), ['dominio'], unique=False)
        batch_op.create_foreign_key('fk_categorias_articulo_dominio', 'dominios_clasificacion', ['dominio'], ['codigo'], onupdate='CASCADE')
    # Líneas de artículo → dominio del mismo nombre (Footwear → FOOTWEAR…)
    con.execute(sa.text("UPDATE categorias_articulo SET dominio = (SELECT d.codigo FROM dominios_clasificacion d "
                        "WHERE lower(d.nombre) = lower(categorias_articulo.nombre) ORDER BY d.id LIMIT 1) "
                        "WHERE dominio IS NULL"))

    with op.batch_alter_table('categorias_producto', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_categorias_producto_dominio', 'dominios_clasificacion', ['dominio'], ['codigo'], onupdate='CASCADE')

    with op.batch_alter_table('paises_arancel', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_paises_arancel_iso', 'paises', ['iso'], ['codigo'], onupdate='CASCADE')


def downgrade() -> None:
    with op.batch_alter_table('paises_arancel', schema=None) as batch_op:
        batch_op.drop_constraint('fk_paises_arancel_iso', type_='foreignkey')

    with op.batch_alter_table('categorias_producto', schema=None) as batch_op:
        batch_op.drop_constraint('fk_categorias_producto_dominio', type_='foreignkey')

    with op.batch_alter_table('categorias_articulo', schema=None) as batch_op:
        batch_op.drop_constraint('fk_categorias_articulo_dominio', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_categorias_articulo_dominio'))
        batch_op.drop_column('dominio')
