"""Regla del código de variante por empresa

Hasta ahora una variante sin escala de valores tomaba su código con una regla
fija (valor × 10 en 3 dígitos: la de las tallas de calzado). Ahora es una
opción de cada empresa (configuracion.productos.codigo_variante) y la de
fábrica es consecutiva. Para que nada cambie en las empresas que ya tienen
artículos, se les guarda la regla que usaban; las demás toman la de fábrica.

No borra nada; la vuelta atrás quita la opción guardada.

Revision ID: 0093
Revises: 0092
Create Date: 2026-10-23 10:00:00
"""
import json

import sqlalchemy as sa

from alembic import op

revision = '0093'
down_revision = '0092'
branch_labels = None
depends_on = None

REGLA_ANTERIOR = {"regla": "MULTIPLICAR", "factor": 10, "longitud": 3}


def _conf(v) -> dict:
    if isinstance(v, dict):
        return dict(v)
    return json.loads(v) if v else {}


def _organizaciones(con) -> sa.Table:
    return sa.Table('organizaciones', sa.MetaData(), autoload_with=con)


def upgrade() -> None:
    con = op.get_bind()
    t = _organizaciones(con)
    con_articulos = {r[0] for r in con.execute(sa.text("SELECT DISTINCT organizacion_id FROM articulos"))}
    for oid, conf in con.execute(sa.select(t.c.id, t.c.configuracion)).all():
        conf = _conf(conf)
        productos = dict(conf.get("productos") or {})
        if oid not in con_articulos or "codigo_variante" in productos:
            continue
        conf["productos"] = {**productos, "codigo_variante": REGLA_ANTERIOR}
        con.execute(t.update().where(t.c.id == oid).values(configuracion=conf))


def downgrade() -> None:
    con = op.get_bind()
    t = _organizaciones(con)
    for oid, conf in con.execute(sa.select(t.c.id, t.c.configuracion)).all():
        conf = _conf(conf)
        if "productos" not in conf:
            continue
        conf["productos"] = {k: v for k, v in (conf["productos"] or {}).items() if k != "codigo_variante"}
        if not conf["productos"]:
            conf.pop("productos")
        con.execute(t.update().where(t.c.id == oid).values(configuracion=conf))
