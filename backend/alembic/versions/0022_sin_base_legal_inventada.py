"""La base legal de un país no se arma con el nombre de su fuente

Antes, si el paquete no traía base legal, se escribía «dataset — autoridad»
de la fuente principal. Eso no es una base legal: se borra donde coincide
exactamente con ese texto armado.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-09 10:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    filas = con.execute(sa.text("SELECT p.id, p.base_legal, f.dataset, f.autoridad FROM paises_arancel p "
                                "JOIN fuentes_oficiales f ON f.id = p.fuente_id WHERE p.base_legal IS NOT NULL")).all()
    for pid, base, dataset, autoridad in filas:
        if base == f"{dataset} — {autoridad}"[:300]:
            con.execute(sa.text("UPDATE paises_arancel SET base_legal = NULL WHERE id = :i"), {"i": pid})


def downgrade() -> None:
    pass
