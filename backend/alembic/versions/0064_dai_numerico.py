"""DAI numérico

El derecho arancelario (DAI, %) se guardaba como texto en incisos_nacionales,
nodos_arancel y partidas_pais: no se podía sumar, comparar ni filtrar por
rango. Pasa a NUMERIC. Lo que no es un número se conserva aparte: en el árbol
regional («Parte II»: lo fija cada país) en nodos_arancel.dai_nota; en un
inciso, en su nota.

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-13 00:00:00
"""
from decimal import Decimal, InvalidOperation

from alembic import op
import sqlalchemy as sa

import app.modelos.base


revision = '0064'
down_revision = '0063'
branch_labels = None
depends_on = None

TABLAS = {'incisos_nacionales': 10, 'nodos_arancel': 12, 'partidas_pais': 10}


def _numero(texto: str) -> str | None:
    t = (texto or "").replace("%", "").replace(" ", "").strip()
    if t.count(",") == 1 and "." not in t:
        t = t.replace(",", ".")
    try:
        return format(Decimal(t).normalize(), "f") if t else None
    except InvalidOperation:
        return None


def upgrade() -> None:
    con = op.get_bind()
    postgres = con.dialect.name == "postgresql"
    with op.batch_alter_table('nodos_arancel', schema=None) as b:
        b.add_column(sa.Column('dai_nota', sa.String(length=20), nullable=True))
    for tabla in TABLAS:
        for (valor,) in con.execute(sa.text(f"SELECT DISTINCT dai FROM {tabla} WHERE dai IS NOT NULL")).all():
            numero = _numero(valor)
            if numero is not None:
                if numero != valor:
                    con.execute(sa.text(f"UPDATE {tabla} SET dai = :n WHERE dai = :v"), {"n": numero, "v": valor})
                continue
            if tabla == 'nodos_arancel':
                con.execute(sa.text("UPDATE nodos_arancel SET dai_nota = :t, dai = NULL WHERE dai = :v"),
                            {"t": valor.strip()[:20], "v": valor})
            elif tabla == 'incisos_nacionales':
                con.execute(sa.text("UPDATE incisos_nacionales SET nota = substr(COALESCE(nota || ' · ', '') || :t, 1, 300), "
                                    "dai = NULL WHERE dai = :v"), {"t": f"DAI: {valor.strip()}", "v": valor})
            else:
                con.execute(sa.text(f"UPDATE {tabla} SET dai = NULL WHERE dai = :v"), {"v": valor})
        with op.batch_alter_table(tabla, schema=None) as b:
            kw = {"postgresql_using": "dai::numeric(12,6)"} if postgres else {}
            b.alter_column('dai', existing_type=sa.String(length=TABLAS[tabla]),
                           type_=app.modelos.base.Tasa(precision=12, scale=6), existing_nullable=True, **kw)


def downgrade() -> None:
    con = op.get_bind()
    postgres = con.dialect.name == "postgresql"
    for tabla, largo in TABLAS.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            kw = {"postgresql_using": "rtrim(rtrim(dai::text, '0'), '.')"} if postgres else {}
            b.alter_column('dai', existing_type=app.modelos.base.Tasa(precision=12, scale=6),
                           type_=sa.String(length=largo), existing_nullable=True, **kw)
    con.execute(sa.text("UPDATE nodos_arancel SET dai = dai_nota WHERE dai IS NULL AND dai_nota IS NOT NULL"))
    with op.batch_alter_table('nodos_arancel', schema=None) as b:
        b.drop_column('dai_nota')
