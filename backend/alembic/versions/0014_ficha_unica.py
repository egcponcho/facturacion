"""Ficha única: sin ficha_motor; las fichas genéricas pasan a su categoría

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-06 21:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None

# Claves de la ficha genérica del navegador que ya no existen (eran evidencia
# o estado de esa pantalla; el motor del servidor guarda su propia evidencia)
VIEJAS = ("gen", "genCand", "genReglas", "genReq", "genConf", "codigoGen", "sacGen", "categoria", "dominio")


def _json(v):
    if v is None or isinstance(v, (dict, list)):
        return v
    return json.loads(v)


def upgrade() -> None:
    con = op.get_bind()
    productos = sa.table("productos", sa.column("id", sa.Integer), sa.column("tipo", sa.String), sa.column("ficha", sa.JSON),
                         sa.column("propuesta", sa.String))
    for pid, tipo, ficha, propuesta in con.execute(sa.select(productos.c.id, productos.c.tipo, productos.c.ficha, productos.c.propuesta)).all():
        f = dict(_json(ficha) or {})
        nuevo_tipo = tipo
        cambio = False
        if tipo == "generico":
            # La ficha genérica tenía la categoría y los atributos aparte: todo pasa a la ficha única
            nuevo_tipo = f.get("categoria") or "otro"
            for k, v in (f.get("gen") or {}).items():
                f.setdefault(k, v)
            cod = "".join(ch for ch in str(f.get("sacGen") or f.get("codigoGen") or "") if ch.isdigit())
            if cod and not propuesta:
                propuesta = cod
            cambio = True
        for k in VIEJAS:
            if k in f:
                f.pop(k)
                cambio = True
        if f.get("edad") == "bebe" and not f.get("edadNac"):
            f["edadNac"] = "bebe"
            cambio = True
        if cambio:
            con.execute(productos.update().where(productos.c.id == pid).values(tipo=nuevo_tipo, ficha=f, propuesta=propuesta))
    with op.batch_alter_table('categorias_producto', schema=None) as batch_op:
        batch_op.drop_column('ficha_motor')


def downgrade() -> None:
    with op.batch_alter_table('categorias_producto', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ficha_motor', sa.Boolean(), nullable=True))
