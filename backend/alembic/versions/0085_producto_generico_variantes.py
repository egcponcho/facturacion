"""Producto genérico: código propio, variantes por atributos y ejes por familia

- productos: el estilo es opcional y deja de ser la identidad (se quita el
  único proveedor + estilo + color); el producto se identifica por su código
  (codigo_generico, único en la empresa). articulos.estilo y prepacks.estilo
  también son opcionales.
- grupos_producto.ejes_variante: con qué atributos se distinguen las
  variantes de los productos de la familia (heredado en el árbol).
- posiciones_oc.variante y factura_lineas.variante: los valores de variante de
  la línea ({"COLOR": "BLACK", "TALLA": "9.5"}).

Conversión: talla y color pasan a ser valores de variante como cualquier otro
atributo: se crea su fila en articulo_atributos (los atributos de sistema TALLA
y COLOR de la empresa) desde las columnas, que se conservan como copia. En un
prepack la talla es su ID de prepack: no se copia. Las líneas de OC y de
factura reciben su variante con los valores de la línea (talla y color) y los
demás atributos del artículo.

Revision ID: 0085
Revises: 0084
Create Date: 2026-10-20 15:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = '0085'
down_revision = '0084'
branch_labels = None
depends_on = None


def _unico_estilo(con) -> str | None:
    for u in sa.inspect(con).get_unique_constraints('productos'):
        if set(u['column_names']) == {'proveedor_id', 'estilo', 'color'}:
            return u['name'] or 'uq_productos_proveedor_id'
    return None


def upgrade() -> None:
    con = op.get_bind()
    nombre = _unico_estilo(con)
    with op.batch_alter_table('productos', schema=None,
                              naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"}) as b:
        if nombre:
            b.drop_constraint(nombre, type_='unique')
        b.alter_column('estilo', existing_type=sa.String(length=40), nullable=True)
    for tabla in ('articulos', 'prepacks'):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.alter_column('estilo', existing_type=sa.String(length=40), nullable=True)
    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.add_column(sa.Column('ejes_variante', sa.JSON(), server_default='[]', nullable=False))
    for tabla in ('posiciones_oc', 'factura_lineas'):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.add_column(sa.Column('variante', sa.JSON(), nullable=True))
    _convertir(con)


def _convertir(con) -> None:
    sistema = con.execute(sa.text(
        "SELECT organizacion_id, columna, id, codigo FROM atributos_variante WHERE columna IS NOT NULL")).all()
    for org, columna, atributo_id, _codigo in sistema:
        filtro = "AND a.tipo <> 'PREPACK'" if columna == 'talla' else ""
        con.execute(sa.text(
            f"INSERT INTO articulo_atributos (organizacion_id, articulo_id, atributo_id, valor) "
            f"SELECT a.organizacion_id, a.id, :atr, SUBSTR(a.{columna}, 1, 60) FROM articulos a "
            f"WHERE a.organizacion_id = :o AND a.{columna} IS NOT NULL AND a.{columna} <> '' {filtro} "
            f"AND NOT EXISTS (SELECT 1 FROM articulo_atributos x WHERE x.articulo_id = a.id AND x.atributo_id = :atr)"),
            {"atr": atributo_id, "o": org})
    # Orden de los atributos de cada empresa y sus atributos de sistema
    orden: dict = {}
    for org, codigo, columna in con.execute(sa.text(
            "SELECT organizacion_id, codigo, columna FROM atributos_variante ORDER BY orden, codigo")).all():
        orden.setdefault(org, []).append((codigo, columna))
    propios: dict = {}
    for articulo_id, codigo, valor in con.execute(sa.text(
            "SELECT x.articulo_id, v.codigo, x.valor FROM articulo_atributos x JOIN atributos_variante v "
            "ON v.id = x.atributo_id WHERE v.columna IS NULL")).all():
        propios.setdefault(articulo_id, {})[codigo] = valor
    param = sa.bindparam('v', type_=sa.JSON)
    filas = con.execute(sa.text(
        "SELECT p.id, p.organizacion_id, p.articulo_id, p.talla, p.color, a.tipo FROM posiciones_oc p "
        "LEFT JOIN articulos a ON a.id = p.articulo_id")).all()
    for pid, org, articulo_id, talla, color, tipo in filas:
        de_linea = {"talla": talla if tipo != 'PREPACK' else None, "color": color}
        valores = {}
        for codigo, columna in orden.get(org, []):
            v = de_linea.get(columna) if columna else propios.get(articulo_id, {}).get(codigo)
            if v not in (None, ""):
                valores[codigo] = v
        if valores:
            con.execute(sa.text("UPDATE posiciones_oc SET variante = :v WHERE id = :i").bindparams(param),
                        {"v": valores, "i": pid})
    con.execute(sa.text(
        "UPDATE factura_lineas SET variante = (SELECT p.variante FROM posiciones_oc p WHERE p.id = factura_lineas.posicion_oc_id)"))


def downgrade() -> None:
    for tabla in ('factura_lineas', 'posiciones_oc'):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.drop_column('variante')
    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.drop_column('ejes_variante')
    con = op.get_bind()
    # Las filas de talla y color vuelven a vivir solo en sus columnas
    con.execute(sa.text("DELETE FROM articulo_atributos WHERE atributo_id IN "
                        "(SELECT id FROM atributos_variante WHERE columna IS NOT NULL)"))
    for tabla in ('prepacks', 'articulos'):
        con.execute(sa.text(f"UPDATE {tabla} SET estilo = '-' WHERE estilo IS NULL"))
        with op.batch_alter_table(tabla, schema=None) as b:
            b.alter_column('estilo', existing_type=sa.String(length=40), nullable=False)
    con.execute(sa.text("UPDATE productos SET estilo = COALESCE(codigo_generico, '-') WHERE estilo IS NULL"))
    with op.batch_alter_table('productos', schema=None) as b:
        b.alter_column('estilo', existing_type=sa.String(length=40), nullable=False)
        b.create_unique_constraint('uq_productos_proveedor_id', ['proveedor_id', 'estilo', 'color'])
