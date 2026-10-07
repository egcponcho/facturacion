"""Género y «para quién es» por familia, no categoría por categoría

Se preguntaban obligatoriamente en 56 categorías escritas una por una (también
en cajas, ganchos, etiquetas o botellas) y una categoría nueva no los
heredaba. Pasan a un ámbito por dominio (ropa y calzado), opcionales en los
accesorios personales y fuera de empaques, camping y similares. Solo se tocan
los ámbitos sembrados (obligatorios y sin condición); lo editado se respeta.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-07 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None

PERSONALES = ("cinturon", "accesorio_pelo", "peleteria", "mochila", "bolso_viaje", "bolso_mano", "maleta", "billetera", "lentes_sol",
              "reloj", "bisuteria", "correa_reloj")
NUEVOS = {
    "edadNac": [("DOMAIN", "APPAREL", "REQUIRE"), ("DOMAIN", "FOOTWEAR", "REQUIRE"), ("CATEGORY", "gorra", "REQUIRE")]
    + [("CATEGORY", c, "SHOW") for c in PERSONALES],
    "genero": [("DOMAIN", "APPAREL", "REQUIRE"), ("CATEGORY", "calzado", "REQUIRE"), ("CATEGORY", "gorra", "REQUIRE")],
}


def upgrade() -> None:
    con = op.get_bind()
    for cod, nuevos in NUEVOS.items():
        fila = con.execute(sa.text("SELECT id FROM atributos_def WHERE codigo = :c AND origen = 'MOTOR'"), {"c": cod}).first()
        if not fila:
            continue
        aid = fila[0]
        quedan = {(t, c) for t, c, m in nuevos if m == "REQUIRE"}
        for i, t, c in con.execute(sa.text("SELECT id, tipo_ambito, codigo_ambito FROM atributo_ambitos WHERE atributo_id = :a "
                                           "AND tipo_ambito = 'CATEGORY' AND modo = 'REQUIRE' AND condicion IS NULL"), {"a": aid}).all():
            if (t, c) not in quedan:
                con.execute(sa.text("DELETE FROM atributo_ambitos WHERE id = :i"), {"i": i})
        existen = {(t, c) for t, c in con.execute(sa.text("SELECT tipo_ambito, codigo_ambito FROM atributo_ambitos WHERE atributo_id = :a"),
                                                  {"a": aid}).all()}
        for t, c, m in nuevos:
            if (t, c) not in existen:
                con.execute(sa.text("INSERT INTO atributo_ambitos (atributo_id, tipo_ambito, codigo_ambito, modo, prioridad, activo) "
                                    "VALUES (:a, :t, :c, :m, 500, :v)"), {"a": aid, "t": t, "c": c, "m": m, "v": True})


def downgrade() -> None:
    pass
