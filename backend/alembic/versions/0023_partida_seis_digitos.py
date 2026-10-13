"""La OC y la factura llevan la subpartida de 6 dígitos

El país destino de la OC es solo una proyección de a dónde irá la mercancía,
no el destino real. Las líneas de factura que ya tenían una línea nacional
(8 o más dígitos) se dejan en su subpartida de 6 dígitos, que son sus primeros
seis dígitos.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-07 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    filas = con.execute(sa.text("SELECT id, partida_arancelaria FROM factura_lineas "
                                "WHERE partida_arancelaria IS NOT NULL")).all()
    for i, partida in filas:
        d = "".join(c for c in partida if c.isdigit())
        if len(d) > 6:
            con.execute(sa.text("UPDATE factura_lineas SET partida_arancelaria = :p WHERE id = :i"),
                        {"p": f"{d[:4]}.{d[4:6]}", "i": i})


def downgrade() -> None:
    pass
