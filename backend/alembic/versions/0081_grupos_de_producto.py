"""Grupos de producto: un solo árbol compartido en lugar de las familias y
categorías de etiquetado

- grupos_producto: cada nodo es una FAMILIA (con subfamilias sin límite) o una
  CATEGORIA dentro de una familia (condiciones para reconocerla sola).
- articulos, grupos_articulos y productos: grupo_producto_id. En el producto
  es su familia o, si tenía una categoría puesta a mano, esa categoría.
- usos_diseno y generacion_items: grupo_id (niveles FAMILIA y CATEGORIA).

Conversión (alternativa A, convivir): cada familia y cada categoría se copia
1:1 a grupos_producto y el nodo guarda de cuál salió (legado_familia_id,
legado_categoria_id). Las asignaciones y las reglas de etiquetado se
reapuntan con ese mapa y la celda de cada regla se vuelve a calcular. Las
tablas y columnas anteriores no se borran ni se tocan: quedan congeladas.

Una categoría cuyo código ya usa una familia de la misma empresa toma el
código con un sufijo (-C, -C2…).

El downgrade devuelve a las tablas anteriores lo que cambió mientras tanto
(nombres, árbol, condiciones, asignaciones, reglas; los nodos nuevos se
agregan a ellas) y quita lo agregado.

Revision ID: 0081
Revises: 0080
Create Date: 2026-10-19 23:00:00
"""
from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls

revision = '0081'
down_revision = '0080'
branch_labels = None
depends_on = None

ASIGNADOS = ('articulos', 'grupos_articulos', 'productos')
_en = lambda col, vals: f"{col} IN ({', '.join(repr(v) for v in vals)})"  # noqa: E731


def _solo(nivel, columna, cols):
    return "(" + " AND ".join([f"nivel = '{nivel}'"] + ([f"{columna} IS NOT NULL"] if columna else [])
                              + [f"{c} IS NULL" for c in cols if c != columna]) + ")"


def _destino(nuevo: bool) -> str:
    if nuevo:
        cols = ["grupo_id", "producto_id", "articulo_id", "tipo_empaque_id"]
        niveles = [("GENERAL", None), ("FAMILIA", "grupo_id"), ("CATEGORIA", "grupo_id")]
    else:
        cols = ["familia_id", "categoria_id", "producto_id", "articulo_id", "tipo_empaque_id"]
        niveles = [("GENERAL", None), ("FAMILIA", "familia_id"), ("CATEGORIA", "categoria_id")]
    niveles += [("PRODUCTO", "producto_id"), ("SKU", "articulo_id"), ("TIPO_EMPAQUE", "tipo_empaque_id")]
    return " OR ".join(_solo(n, c, cols) for n, c in niveles)


def _indice_normal(crear: bool) -> None:
    if crear:
        op.create_index('uq_usos_diseno_normal', 'usos_diseno', ['organizacion_id', 'celda'], unique=True,
                        sqlite_where=sa.text("contexto_tipo = 'NINGUNO' AND eliminado_en IS NULL"),
                        postgresql_where=sa.text("contexto_tipo = 'NINGUNO' AND eliminado_en IS NULL"))
    else:
        op.drop_index('uq_usos_diseno_normal', table_name='usos_diseno')


def _columna_grupo(tabla: str, col: str) -> None:
    with op.batch_alter_table(tabla, schema=None) as b:
        b.add_column(sa.Column(col, sa.Integer(), nullable=True))
        b.create_index(b.f(f'ix_{tabla}_{col}'), [col], unique=False)
        b.create_foreign_key(f'fk_{tabla}_{col}', 'grupos_producto', [col], ['id'])
        b.create_foreign_key(f'fk_{tabla}_{col}_org', 'grupos_producto', [col, 'organizacion_id'], ['id', 'organizacion_id'])


def _quitar_columna_grupo(tabla: str, col: str) -> None:
    with op.batch_alter_table(tabla, schema=None) as b:
        b.drop_constraint(f'fk_{tabla}_{col}_org', type_='foreignkey')
        b.drop_constraint(f'fk_{tabla}_{col}', type_='foreignkey')
        b.drop_index(b.f(f'ix_{tabla}_{col}'))
        b.drop_column(col)


def upgrade() -> None:
    con = op.get_bind()
    op.create_table(
        'grupos_producto',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clase', sa.String(length=10), nullable=False),
        sa.Column('codigo', sa.String(length=20), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('descripcion', sa.String(length=300), nullable=True),
        sa.Column('padre_id', sa.Integer(), nullable=True),
        sa.Column('condiciones', sa.JSON(), nullable=False),
        sa.Column('campos', sa.JSON(), nullable=False),
        sa.Column('orden', sa.Integer(), nullable=False),
        sa.Column('activa', sa.Boolean(), nullable=False),
        sa.Column('creada_en', sa.DateTime(), nullable=False),
        sa.Column('legado_familia_id', sa.Integer(), nullable=True),
        sa.Column('legado_categoria_id', sa.Integer(), nullable=True),
        sa.Column('organizacion_id', sa.Integer(), nullable=False),
        sa.CheckConstraint("clase IN ('FAMILIA', 'CATEGORIA')", name='ck_grupos_producto_clase'),
        sa.CheckConstraint("clase = 'FAMILIA' OR padre_id IS NOT NULL", name='ck_grupos_producto_categoria_padre'),
        sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name='fk_grupos_producto_organizacion_id_organizaciones'),
        sa.ForeignKeyConstraint(['padre_id'], ['grupos_producto.id'], name='fk_grupos_producto_padre_id_grupos_producto'),
        sa.ForeignKeyConstraint(['padre_id', 'organizacion_id'], ['grupos_producto.id', 'grupos_producto.organizacion_id'],
                                name='fk_grupos_producto_padre_id_org'),
        sa.PrimaryKeyConstraint('id', name='pk_grupos_producto'),
        sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_grupos_producto_org_codigo'),
        sa.UniqueConstraint('id', 'organizacion_id', name='uq_grupos_producto_id_org'),
    )
    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.create_index(b.f('ix_grupos_producto_organizacion_id'), ['organizacion_id'], unique=False)
        b.create_index(b.f('ix_grupos_producto_padre_id'), ['padre_id'], unique=False)
    _copiar(con)

    _columna_grupo('articulos', 'grupo_producto_id')
    _columna_grupo('grupos_articulos', 'grupo_producto_id')
    _columna_grupo('productos', 'grupo_producto_id')
    _asignar(con)

    _indice_normal(False)
    with op.batch_alter_table('usos_diseno', schema=None) as b:
        b.add_column(sa.Column('grupo_id', sa.Integer(), nullable=True))
        b.create_index(b.f('ix_usos_diseno_grupo_id'), ['grupo_id'], unique=False)
        b.create_foreign_key('fk_usos_diseno_grupo_id_grupos_producto', 'grupos_producto', ['grupo_id'], ['id'])
        b.create_foreign_key('fk_usos_diseno_grupo_id_org', 'grupos_producto', ['grupo_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
        b.drop_constraint('ck_usos_diseno_destino', type_='check')
    con.execute(sa.text(
        "UPDATE usos_diseno SET grupo_id = (SELECT g.id FROM grupos_producto g WHERE g.legado_familia_id = usos_diseno.familia_id) "
        "WHERE nivel = 'FAMILIA'"))
    con.execute(sa.text(
        "UPDATE usos_diseno SET grupo_id = (SELECT g.id FROM grupos_producto g "
        "WHERE g.legado_categoria_id = usos_diseno.categoria_id) WHERE nivel = 'CATEGORIA'"))
    _celdas(con, 'grupo_id')
    with op.batch_alter_table('usos_diseno', schema=None) as b:
        b.create_check_constraint('ck_usos_diseno_destino', _destino(True))
    _indice_normal(True)

    with op.batch_alter_table('generacion_items', schema=None) as b:
        b.add_column(sa.Column('grupo_id', sa.Integer(), nullable=True))
        b.create_index(b.f('ix_generacion_items_grupo_id'), ['grupo_id'], unique=False)
        b.create_foreign_key('fk_generacion_items_grupo_id_grupos_producto', 'grupos_producto', ['grupo_id'], ['id'])
        b.create_foreign_key('fk_generacion_items_grupo_id_org', 'grupos_producto', ['grupo_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
    con.execute(sa.text(
        "UPDATE generacion_items SET grupo_id = (SELECT g.id FROM grupos_producto g "
        "WHERE g.legado_familia_id = generacion_items.familia_id) WHERE familia_id IS NOT NULL"))
    rls(op, 'grupos_producto')


def _copiar(con) -> None:
    """Cada familia y cada categoría, 1:1, con el mapa en legado_*."""
    con.execute(sa.text(
        "INSERT INTO grupos_producto (clase, codigo, nombre, descripcion, padre_id, condiciones, campos, orden, activa, "
        "creada_en, legado_familia_id, organizacion_id) "
        "SELECT 'FAMILIA', codigo, nombre, descripcion, NULL, '[]', campos, orden, activa, creada_en, id, organizacion_id "
        "FROM familias_etiquetado"))
    con.execute(sa.text(
        "UPDATE grupos_producto SET padre_id = (SELECT p.id FROM familias_etiquetado f "
        "JOIN grupos_producto p ON p.legado_familia_id = f.padre_id WHERE f.id = grupos_producto.legado_familia_id) "
        "WHERE legado_familia_id IS NOT NULL"))
    usados: dict = {}
    for org, codigo in con.execute(sa.text("SELECT organizacion_id, codigo FROM grupos_producto")).all():
        usados.setdefault(org, set()).add(codigo.upper())
    for cid, org, codigo in con.execute(sa.text(
            "SELECT id, organizacion_id, codigo FROM categorias_etiquetado ORDER BY id")).all():
        nuevo, n = codigo, 1
        while nuevo.upper() in usados.setdefault(org, set()):
            sufijo = "-C" if n == 1 else f"-C{n}"
            nuevo, n = codigo[:20 - len(sufijo)] + sufijo, n + 1
        usados[org].add(nuevo.upper())
        con.execute(sa.text(
            "INSERT INTO grupos_producto (clase, codigo, nombre, descripcion, padre_id, condiciones, campos, orden, activa, "
            "creada_en, legado_categoria_id, organizacion_id) "
            "SELECT 'CATEGORIA', :codigo, c.nombre, c.descripcion, g.id, c.condiciones, '[]', c.orden, c.activa, c.creada_en, "
            "c.id, c.organizacion_id FROM categorias_etiquetado c JOIN grupos_producto g ON g.legado_familia_id = c.familia_id "
            "WHERE c.id = :id"), {"codigo": nuevo, "id": cid})


def _asignar(con) -> None:
    """Artículos y grupos: su familia. Producto: su categoría a mano si es de su
    familia (o de una superior), si no su familia."""
    for tabla in ('articulos', 'grupos_articulos'):
        con.execute(sa.text(
            f"UPDATE {tabla} SET grupo_producto_id = (SELECT g.id FROM grupos_producto g "
            f"WHERE g.legado_familia_id = {tabla}.familia_etiquetado_id) WHERE familia_etiquetado_id IS NOT NULL"))
    con.execute(sa.text(
        "UPDATE productos SET grupo_producto_id = (SELECT g.id FROM grupos_producto g "
        "WHERE g.legado_familia_id = productos.familia_etiquetado_id) WHERE familia_etiquetado_id IS NOT NULL"))
    padres = dict(con.execute(sa.text("SELECT id, padre_id FROM familias_etiquetado")).all())
    de_grupo = dict(con.execute(sa.text("SELECT id, familia_etiquetado_id FROM grupos_articulos")).all())
    cat_familia = dict(con.execute(sa.text("SELECT id, familia_id FROM categorias_etiquetado")).all())
    nodo_cat = dict(con.execute(sa.text(
        "SELECT legado_categoria_id, id FROM grupos_producto WHERE legado_categoria_id IS NOT NULL")).all())
    for pid, fam, cat, grupo in con.execute(sa.text(
            "SELECT id, familia_etiquetado_id, categoria_etiquetado_id, grupo_id FROM productos "
            "WHERE categoria_etiquetado_id IS NOT NULL")).all():
        efectiva, ruta = fam or de_grupo.get(grupo), set()
        while efectiva is not None and efectiva not in ruta:
            ruta.add(efectiva)
            efectiva = padres.get(efectiva)
        if cat_familia.get(cat) in ruta and cat in nodo_cat:
            con.execute(sa.text("UPDATE productos SET grupo_producto_id = :g WHERE id = :id"), {"g": nodo_cat[cat], "id": pid})


def _celdas(con, col: str) -> None:
    """La celda de cada regla de familia o categoría (tipo:nivel:destino) con su destino actual."""
    for uid, tipo, nivel, destino in con.execute(sa.text(
            f"SELECT id, tipo_etiqueta_id, nivel, {col} FROM usos_diseno WHERE nivel IN ('FAMILIA', 'CATEGORIA')")).all():
        con.execute(sa.text("UPDATE usos_diseno SET celda = :c WHERE id = :id"), {"c": f"{tipo}:{nivel}:{destino or 0}", "id": uid})


def downgrade() -> None:
    con = op.get_bind()
    _devolver(con)
    for tabla, col in (('articulos', 'familia_etiquetado_id'), ('grupos_articulos', 'familia_etiquetado_id'),
                       ('productos', 'familia_etiquetado_id')):
        con.execute(sa.text(
            f"UPDATE {tabla} SET {col} = (SELECT CASE WHEN g.clase = 'FAMILIA' THEN g.legado_familia_id "
            f"ELSE (SELECT p.legado_familia_id FROM grupos_producto p WHERE p.id = g.padre_id) END "
            f"FROM grupos_producto g WHERE g.id = {tabla}.grupo_producto_id)"))
    con.execute(sa.text(
        "UPDATE productos SET categoria_etiquetado_id = (SELECT g.legado_categoria_id FROM grupos_producto g "
        "WHERE g.id = productos.grupo_producto_id AND g.clase = 'CATEGORIA')"))
    for tabla in ASIGNADOS:
        _quitar_columna_grupo(tabla, 'grupo_producto_id')

    _indice_normal(False)
    with op.batch_alter_table('usos_diseno', schema=None) as b:
        b.drop_constraint('ck_usos_diseno_destino', type_='check')
    con.execute(sa.text(
        "UPDATE usos_diseno SET familia_id = (SELECT g.legado_familia_id FROM grupos_producto g WHERE g.id = usos_diseno.grupo_id) "
        "WHERE nivel = 'FAMILIA'"))
    con.execute(sa.text(
        "UPDATE usos_diseno SET categoria_id = (SELECT g.legado_categoria_id FROM grupos_producto g "
        "WHERE g.id = usos_diseno.grupo_id) WHERE nivel = 'CATEGORIA'"))
    con.execute(sa.text("UPDATE usos_diseno SET familia_id = NULL WHERE nivel <> 'FAMILIA'"))
    con.execute(sa.text("UPDATE usos_diseno SET categoria_id = NULL WHERE nivel <> 'CATEGORIA'"))
    _celdas_anteriores(con)
    with op.batch_alter_table('usos_diseno', schema=None) as b:
        b.drop_constraint('fk_usos_diseno_grupo_id_org', type_='foreignkey')
        b.drop_constraint('fk_usos_diseno_grupo_id_grupos_producto', type_='foreignkey')
        b.drop_index(b.f('ix_usos_diseno_grupo_id'))
        b.drop_column('grupo_id')
        b.create_check_constraint('ck_usos_diseno_destino', _destino(False))
    _indice_normal(True)

    con.execute(sa.text(
        "UPDATE generacion_items SET familia_id = (SELECT g.legado_familia_id FROM grupos_producto g "
        "WHERE g.id = generacion_items.grupo_id AND g.clase = 'FAMILIA') WHERE familia_id IS NULL AND grupo_id IS NOT NULL"))
    with op.batch_alter_table('generacion_items', schema=None) as b:
        b.drop_constraint('fk_generacion_items_grupo_id_org', type_='foreignkey')
        b.drop_constraint('fk_generacion_items_grupo_id_grupos_producto', type_='foreignkey')
        b.drop_index(b.f('ix_generacion_items_grupo_id'))
        b.drop_column('grupo_id')
    op.drop_table('grupos_producto')


def _celdas_anteriores(con) -> None:
    for uid, tipo, nivel, fam, cat in con.execute(sa.text(
            "SELECT id, tipo_etiqueta_id, nivel, familia_id, categoria_id FROM usos_diseno "
            "WHERE nivel IN ('FAMILIA', 'CATEGORIA')")).all():
        destino = fam if nivel == 'FAMILIA' else cat
        con.execute(sa.text("UPDATE usos_diseno SET celda = :c WHERE id = :id"), {"c": f"{tipo}:{nivel}:{destino or 0}", "id": uid})


def _devolver(con) -> None:
    """Lo que cambió en el árbol vuelve a las tablas anteriores; los nodos nuevos se agregan a ellas."""
    for clase, tabla, legado in (('FAMILIA', 'familias_etiquetado', 'legado_familia_id'),
                                 ('CATEGORIA', 'categorias_etiquetado', 'legado_categoria_id')):
        nuevos = con.execute(sa.text(
            f"SELECT id, organizacion_id, codigo FROM grupos_producto WHERE clase = :c AND {legado} IS NULL ORDER BY id"),
            {"c": clase}).all()
        for gid, org, codigo in nuevos:
            existente = con.execute(sa.text(
                f"SELECT t.id FROM {tabla} t WHERE t.organizacion_id = :o AND t.codigo = :cod "
                f"AND NOT EXISTS (SELECT 1 FROM grupos_producto g WHERE g.{legado} = t.id)"), {"o": org, "cod": codigo}).scalar()
            if existente is None:
                if clase == 'FAMILIA':
                    con.execute(sa.text(
                        "INSERT INTO familias_etiquetado (codigo, nombre, descripcion, campos, orden, activa, creada_en, "
                        "organizacion_id) SELECT codigo, nombre, descripcion, campos, orden, activa, creada_en, organizacion_id "
                        "FROM grupos_producto WHERE id = :g"), {"g": gid})
                else:
                    con.execute(sa.text(
                        "INSERT INTO categorias_etiquetado (familia_id, codigo, nombre, descripcion, condiciones, orden, activa, "
                        "creada_en, organizacion_id) SELECT p.legado_familia_id, g.codigo, g.nombre, g.descripcion, g.condiciones, "
                        "g.orden, g.activa, g.creada_en, g.organizacion_id FROM grupos_producto g "
                        "JOIN grupos_producto p ON p.id = g.padre_id WHERE g.id = :g"), {"g": gid})
                existente = con.execute(sa.text(f"SELECT id FROM {tabla} WHERE organizacion_id = :o AND codigo = :cod"),
                                        {"o": org, "cod": codigo}).scalar()
            con.execute(sa.text(f"UPDATE grupos_producto SET {legado} = :t WHERE id = :g"), {"t": existente, "g": gid})
    con.execute(sa.text(
        "UPDATE familias_etiquetado SET (codigo, nombre, descripcion, campos, orden, activa) = "
        "(SELECT g.codigo, g.nombre, g.descripcion, g.campos, g.orden, g.activa FROM grupos_producto g "
        "WHERE g.legado_familia_id = familias_etiquetado.id) "
        "WHERE EXISTS (SELECT 1 FROM grupos_producto g WHERE g.legado_familia_id = familias_etiquetado.id)"))
    con.execute(sa.text(
        "UPDATE familias_etiquetado SET padre_id = (SELECT p.legado_familia_id FROM grupos_producto g "
        "JOIN grupos_producto p ON p.id = g.padre_id WHERE g.legado_familia_id = familias_etiquetado.id) "
        "WHERE EXISTS (SELECT 1 FROM grupos_producto g WHERE g.legado_familia_id = familias_etiquetado.id)"))
    con.execute(sa.text(
        "UPDATE categorias_etiquetado SET (familia_id, codigo, nombre, descripcion, condiciones, orden, activa) = "
        "(SELECT p.legado_familia_id, g.codigo, g.nombre, g.descripcion, g.condiciones, g.orden, g.activa "
        "FROM grupos_producto g JOIN grupos_producto p ON p.id = g.padre_id WHERE g.legado_categoria_id = categorias_etiquetado.id) "
        "WHERE EXISTS (SELECT 1 FROM grupos_producto g WHERE g.legado_categoria_id = categorias_etiquetado.id)"))
    # Lo que se borró del árbol queda inactivo en las tablas anteriores
    con.execute(sa.text("UPDATE familias_etiquetado SET activa = :f WHERE NOT EXISTS "
                        "(SELECT 1 FROM grupos_producto g WHERE g.legado_familia_id = familias_etiquetado.id)"), {"f": False})
    con.execute(sa.text("UPDATE categorias_etiquetado SET activa = :f WHERE NOT EXISTS "
                        "(SELECT 1 FROM grupos_producto g WHERE g.legado_categoria_id = categorias_etiquetado.id)"), {"f": False})
