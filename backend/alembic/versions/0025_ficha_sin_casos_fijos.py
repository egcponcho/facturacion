"""La ficha sin casos escritos para una familia

- Las partes de la composición que solo describen (relleno, plantilla) quedan
  marcadas como informativas: el motor ya no las reconoce por su nombre.
- Los modos de lectura de una parte pasan a nombres genéricos: «superficie»
  (antes «corte») y «contacto» (antes «suela»).
- La composición genérica se pregunta a productos fuera de una familia
  configurada (sin dominio), no solo a los que no tienen categoría.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-07 14:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None

LECTURA = {"corte": "superficie", "suela": "contacto"}


def _json(v):
    if v is None or isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def upgrade() -> None:
    con = op.get_bind()
    con.execute(sa.text("UPDATE atributos_def SET informativo = :v, usado_clasificacion = :f "
                        "WHERE codigo IN ('comp.relleno', 'comp.plantilla') AND origen = 'MOTOR'"), {"v": True, "f": False})
    for i, deriv in con.execute(sa.text("SELECT id, derivacion FROM atributos_def WHERE derivacion IS NOT NULL")).all():
        d = _json(deriv)
        if isinstance(d, dict) and d.get("lectura") in LECTURA:
            d["lectura"] = LECTURA[d["lectura"]]
            con.execute(sa.text("UPDATE atributos_def SET derivacion = :d WHERE id = :i"), {"d": json.dumps(d, ensure_ascii=False), "i": i})
    vieja = [{"campo": "categoria", "operador": "EXISTS", "negado": True}]
    for i, cond in con.execute(sa.text("SELECT x.id, x.condicion FROM atributo_ambitos x JOIN atributos_def a ON a.id = x.atributo_id "
                                       "WHERE a.codigo = 'comp.material' AND x.tipo_ambito = 'SYSTEM'")).all():
        if _json(cond) == vieja:
            con.execute(sa.text("UPDATE atributo_ambitos SET condicion = :c WHERE id = :i"),
                        {"c": json.dumps([{"campo": "dominio", "operador": "EXISTS", "negado": True}]), "i": i})


def downgrade() -> None:
    pass
