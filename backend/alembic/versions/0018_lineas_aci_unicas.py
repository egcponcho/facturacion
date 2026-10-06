"""Una línea del ACI por código

El ACI remite 519 líneas a la Parte II (DAI distinto por país) y la extracción
las trajo repetidas con las tasas de la Parte II sin su país. Se deja un solo
nodo por código en cada versión y una sola línea nacional por país, código y
versión; el DAI de la Parte II queda vacío (no se asigna la tasa de otro país).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-08 09:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    # Nodos repetidos: queda el primero (el de la Parte I); los hijos apuntan a él
    for vid, cod, keep in con.execute(sa.text(
            "SELECT version_id, codigo_norm, MIN(id) FROM nodos_arancel WHERE nivel = 'INCISO' "
            "GROUP BY version_id, codigo_norm HAVING COUNT(*) > 1")).all():
        otros = [r[0] for r in con.execute(sa.text("SELECT id FROM nodos_arancel WHERE version_id = :v AND codigo_norm = :c AND id <> :k"),
                                           {"v": vid, "c": cod, "k": keep})]
        for o in otros:
            con.execute(sa.text("UPDATE nodos_arancel SET padre_id = :k WHERE padre_id = :o"), {"k": keep, "o": o})
            con.execute(sa.text("DELETE FROM nodos_arancel WHERE id = :o"), {"o": o})
    # Líneas nacionales repetidas: queda la primera; decisiones y reglas pasan a ella
    for pais, cod, vid, keep in con.execute(sa.text(
            "SELECT pais, codigo, version_id, MIN(id) FROM incisos_nacionales "
            "GROUP BY pais, codigo, version_id HAVING COUNT(*) > 1")).all():
        otros = [r[0] for r in con.execute(sa.text(
            "SELECT id FROM incisos_nacionales WHERE pais = :p AND codigo = :c AND "
            "(version_id = :v OR (version_id IS NULL AND :v IS NULL)) AND id <> :k"), {"p": pais, "c": cod, "v": vid, "k": keep})]
        for o in otros:
            con.execute(sa.text("UPDATE partidas_pais SET inciso_id = :k WHERE inciso_id = :o"), {"k": keep, "o": o})
            regla = con.execute(sa.text("SELECT id FROM reglas_clasificacion WHERE inciso_id = :o"), {"o": o}).scalar()
            if regla:
                con.execute(sa.text("DELETE FROM reglas_condiciones WHERE regla_id = :r"), {"r": regla})
                con.execute(sa.text("DELETE FROM reglas_clasificacion WHERE id = :r"), {"r": regla})
            con.execute(sa.text("DELETE FROM overrides_arancel WHERE tipo = 'INCISO' AND objetivo = :o"), {"o": str(o)})
            con.execute(sa.text("DELETE FROM incisos_nacionales WHERE id = :o"), {"o": o})
    # DAI de la Parte II: por país, no regional
    con.execute(sa.text("UPDATE incisos_nacionales SET dai = NULL WHERE UPPER(dai) LIKE 'PARTE II%'"))
    con.execute(sa.text("UPDATE incisos_nacionales SET dai = NULL WHERE id IN (SELECT i.id FROM incisos_nacionales i "
                        "JOIN nodos_arancel n ON n.version_id = i.version_id AND n.codigo_norm = i.codigo AND n.nivel = 'INCISO' "
                        "WHERE UPPER(n.dai) LIKE 'PARTE II%')"))


def downgrade() -> None:
    pass  # los duplicados no se recrean
