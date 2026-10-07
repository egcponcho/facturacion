"""Un solo vocabulario de atributos

El paquete del motor traía atributos que repetían los de la ficha con otro
código (material del corte, tipo de calzado, tejido, país destino…): la ficha
los preguntaba dos veces y ninguna regla los usaba. Se agrega AtributoDef.alias
(los otros códigos de un mismo atributo) y se quitan esos duplicados; un valor
ya capturado en uno que tiene equivalente pasa al atributo de la ficha.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-07 12:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None

QUITAR = ("commercial_description", "primary_function", "material_main", "destination_country", "upper_material",
          "outer_sole_material", "footwear_type", "covers_ankle", "protective_toe", "knitted_or_crocheted", "garment_type",
          "fiber_composition", "target_user", "article_type", "part_or_accessory_of", "decorative_function", "wearable",
          "fastening_type", "material_composition")
# Atributo duplicado → (atributo de la ficha, parte de la composición si es una)
EQUIVALE = {"material_composition": ("comp.material", "material"), "upper_material": ("comp.corte", "corte"),
            "outer_sole_material": ("comp.suela", "suela"), "fiber_composition": ("comp.exterior", "exterior")}


def _json(v):
    if v is None or isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def upgrade() -> None:
    with op.batch_alter_table("atributos_def") as b:
        b.add_column(sa.Column("alias", sa.JSON(), nullable=True))
    con = op.get_bind()
    usados = {r[0] for r in con.execute(sa.text("SELECT DISTINCT campo FROM reglas_condiciones"))}
    for cod in QUITAR:
        fila = con.execute(sa.text("SELECT id FROM atributos_def WHERE codigo = :c AND origen = 'PAQUETE'"), {"c": cod}).first()
        if not fila:
            continue
        if cod in usados:  # una regla propia lo usa: se apaga en vez de borrarlo
            con.execute(sa.text("UPDATE atributos_def SET activo = :f WHERE id = :i"), {"f": False, "i": fila[0]})
            continue
        for t in ("atributo_opciones", "atributo_ambitos"):
            con.execute(sa.text(f"DELETE FROM {t} WHERE atributo_id = :i"), {"i": fila[0]})
        con.execute(sa.text("DELETE FROM atributos_def WHERE id = :i"), {"i": fila[0]})
    for cod, (canonico, _) in EQUIVALE.items():
        con.execute(sa.text("UPDATE atributos_def SET alias = :a WHERE codigo = :c"), {"a": json.dumps([cod]), "c": canonico})
    # Las fichas: lo capturado en un duplicado con equivalente pasa a la ficha; el resto (nada lo usaba) se quita
    for pid, ficha in con.execute(sa.text("SELECT id, ficha FROM productos")).all():
        f = _json(ficha)
        if not isinstance(f, dict) or not any(k in f for k in QUITAR):
            continue
        comp = f.get("comp") if isinstance(f.get("comp"), dict) else {}
        for cod in QUITAR:
            if cod not in f:
                continue
            v = f.pop(cod)
            if cod in EQUIVALE and isinstance(v, str) and v.strip() and not comp.get(EQUIVALE[cod][1]):
                comp[EQUIVALE[cod][1]] = v
        if comp:
            f["comp"] = comp
        con.execute(sa.text("UPDATE productos SET ficha = :f WHERE id = :i"), {"f": json.dumps(f, ensure_ascii=False), "i": pid})


def downgrade() -> None:
    with op.batch_alter_table("atributos_def") as b:
        b.drop_column("alias")
