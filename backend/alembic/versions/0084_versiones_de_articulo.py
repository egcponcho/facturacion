"""Versiones del artículo que usa cada documento

- articulo_versiones: la foto del artículo (datos, atributos de variante,
  campos propios, componentes del prepack y su producto con la ficha) con su
  huella; una versión nueva solo cuando la foto cambia.
- posiciones_oc.articulo_version_id y factura_lineas.articulo_version_id: la
  versión que usó la línea. Las líneas nuevas la toman solas
  (app/modelos/versiones.py).

Conversión: las líneas que ya existen no tienen cómo saber cómo era el
artículo cuando se crearon; se les da la versión 1, con los datos del artículo
al migrar (marcada «migracion»). La próxima línea que use el artículo crea la
versión 2 si su foto completa difiere.

El downgrade quita solo lo agregado.

Revision ID: 0084
Revises: 0083
Create Date: 2026-10-20 11:00:00
"""
import hashlib
import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls

revision = '0084'
down_revision = '0083'
branch_labels = None
depends_on = None

CAMPOS = ("sku", "sku_proveedor", "upc", "generico", "estilo", "color", "talla", "descripcion", "unidad", "peso_unitario",
          "tipo")


def upgrade() -> None:
    op.create_table('articulo_versiones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('articulo_id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('huella', sa.String(length=64), nullable=False),
    sa.Column('datos', sa.JSON(), nullable=False),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('creada_por', sa.Integer(), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('numero >= 1', name='ck_articulo_versiones_numero'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name='fk_articulo_versiones_organizacion_id_organizaciones'),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], name='fk_articulo_versiones_articulo_id_articulos'),
    sa.ForeignKeyConstraint(['creada_por'], ['usuarios.id'], name='fk_articulo_versiones_creada_por_usuarios'),
    sa.ForeignKeyConstraint(['articulo_id', 'organizacion_id'], ['articulos.id', 'articulos.organizacion_id'],
                            name='fk_articulo_versiones_articulo_id_org'),
    sa.PrimaryKeyConstraint('id', name='pk_articulo_versiones'),
    sa.UniqueConstraint('articulo_id', 'numero', name='uq_articulo_versiones_articulo_numero'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_articulo_versiones_id_org'),
    )
    with op.batch_alter_table('articulo_versiones', schema=None) as b:
        b.create_index(b.f('ix_articulo_versiones_articulo_id'), ['articulo_id'], unique=False)
        b.create_index(b.f('ix_articulo_versiones_huella'), ['huella'], unique=False)
        b.create_index(b.f('ix_articulo_versiones_organizacion_id'), ['organizacion_id'], unique=False)
    for tabla in ('posiciones_oc', 'factura_lineas'):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.add_column(sa.Column('articulo_version_id', sa.Integer(), nullable=True))
            b.create_index(b.f(f'ix_{tabla}_articulo_version_id'), ['articulo_version_id'], unique=False)
            b.create_foreign_key(f'fk_{tabla}_articulo_version_id_articulo_versiones', 'articulo_versiones',
                                 ['articulo_version_id'], ['id'])
            b.create_foreign_key(f'fk_{tabla}_articulo_version_id_org', 'articulo_versiones',
                                 ['articulo_version_id', 'organizacion_id'], ['id', 'organizacion_id'])
    rls(op, 'articulo_versiones')
    _convertir(op.get_bind())


def _json(v):
    return json.loads(v) if isinstance(v, str) else (v or {})


def _convertir(con) -> None:
    """Versión 1 de cada artículo que ya usan líneas de OC, con sus datos de hoy."""
    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    filas = con.execute(sa.text(
        "SELECT a.id, a.organizacion_id, a.extra, a.prepack_id, a.producto_id, " + ", ".join(f"a.{c}" for c in CAMPOS) +
        ", m.codigo AS marca, m.nombre AS marca_nombre, g.codigo AS grupo, g.nombre AS grupo_nombre, pp.codigo AS prepack "
        "FROM articulos a LEFT JOIN marcas m ON m.id = a.marca_id LEFT JOIN grupos_articulos g ON g.id = a.grupo_id "
        "LEFT JOIN prepacks pp ON pp.id = a.prepack_id "
        "WHERE a.id IN (SELECT articulo_id FROM posiciones_oc WHERE articulo_id IS NOT NULL)")).mappings().all()
    datos_param = sa.bindparam('d', type_=sa.JSON)
    for f in filas:
        atributos = dict(con.execute(sa.text(
            "SELECT v.codigo, x.valor FROM articulo_atributos x JOIN atributos_variante v ON v.id = x.atributo_id "
            "WHERE x.articulo_id = :a ORDER BY v.codigo"), {"a": f["id"]}).all())
        componentes = [{"sku": s, "cantidad": n} for s, n in con.execute(sa.text(
            "SELECT a.sku, c.cantidad FROM prepack_componentes c JOIN articulos a ON a.id = c.articulo_id "
            "WHERE c.prepack_id = :p ORDER BY a.sku"), {"p": f["prepack_id"]}).all()] if f["prepack_id"] else []
        producto = None
        if f["producto_id"]:
            p = con.execute(sa.text(
                "SELECT id, estilo, color, nombre, codigo_generico, descripcion_comercial, pais_origen, tipo, version_ficha, ficha "
                "FROM productos WHERE id = :p"), {"p": f["producto_id"]}).mappings().first()
            producto = {**dict(p), "ficha": _json(p["ficha"])} if p else None
        datos = {"articulo": {**{c: f[c] for c in CAMPOS}, "marca": f["marca"], "marca_nombre": f["marca_nombre"],
                              "grupo": f["grupo"], "grupo_nombre": f["grupo_nombre"], "prepack": f["prepack"]},
                 "atributos": atributos, "extra": _json(f["extra"]), "componentes": componentes, "producto": producto,
                 "migracion": True}
        huella = hashlib.sha256(json.dumps(datos, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
        con.execute(sa.text(
            "INSERT INTO articulo_versiones (articulo_id, numero, huella, datos, creada_en, organizacion_id) "
            "VALUES (:a, 1, :h, :d, :t, :o)").bindparams(datos_param),
            {"a": f["id"], "h": huella, "d": datos, "t": ahora, "o": f["organizacion_id"]})
    con.execute(sa.text(
        "UPDATE posiciones_oc SET articulo_version_id = (SELECT v.id FROM articulo_versiones v "
        "WHERE v.articulo_id = posiciones_oc.articulo_id AND v.numero = 1) WHERE articulo_id IS NOT NULL"))
    con.execute(sa.text(
        "UPDATE factura_lineas SET articulo_version_id = (SELECT p.articulo_version_id FROM posiciones_oc p "
        "WHERE p.id = factura_lineas.posicion_oc_id)"))


def downgrade() -> None:
    for tabla in ('factura_lineas', 'posiciones_oc'):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.drop_constraint(f'fk_{tabla}_articulo_version_id_org', type_='foreignkey')
            b.drop_constraint(f'fk_{tabla}_articulo_version_id_articulo_versiones', type_='foreignkey')
            b.drop_index(b.f(f'ix_{tabla}_articulo_version_id'))
            b.drop_column('articulo_version_id')
    op.drop_table('articulo_versiones')
