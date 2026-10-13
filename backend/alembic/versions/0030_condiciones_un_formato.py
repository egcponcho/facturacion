"""Un solo formato de condiciones

Los ámbitos y bloqueos guardados con el formato anterior (lista de
alternativas {atributo: valor}) pasan al formato del motor
[{grupo, campo, operador, valor}]; el motor ya no lee el anterior.

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-07 20:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def _lista(valor):
    if isinstance(valor, str):
        return json.loads(valor or "null")
    return valor


def _nuevas(cond):
    if not cond or all(isinstance(c, dict) and "campo" in c for c in cond):
        return cond
    return [{"grupo": i, "campo": k, "operador": "IN" if isinstance(v, list) else "EQUAL", "valor": v}
            for i, alt in enumerate(cond, start=1) for k, v in (alt or {}).items()]


def _bloqueos(bloqueo):
    if not bloqueo:
        return bloqueo
    return [{**b, "condiciones": _nuevas(b.get("condiciones"))} if isinstance(b, dict) else b for b in bloqueo]


def _convertir(tabla: str, columna: str, fn) -> None:
    con = op.get_bind()
    t = sa.table(tabla, sa.column("id", sa.Integer), sa.column(columna, sa.JSON))
    for id_, valor in con.execute(sa.select(t.c.id, t.c[columna])).all():
        antes = _lista(valor)
        despues = fn(antes)
        if despues != antes:
            con.execute(t.update().where(t.c.id == id_).values({columna: despues}))


def upgrade() -> None:
    _convertir("atributo_ambitos", "condicion", _nuevas)
    _convertir("atributos_def", "bloqueo", _bloqueos)
    _convertir("atributo_opciones", "bloqueo", _bloqueos)


def downgrade() -> None:
    pass  # el formato del motor también era válido antes
