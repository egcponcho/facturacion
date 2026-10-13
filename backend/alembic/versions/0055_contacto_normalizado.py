"""Contactos y direcciones normalizados

Los correos (listas separadas por coma), teléfonos, direcciones y personas de
contacto que se repetían en proveedores, transportistas, sociedades, centros
y contactos pasan a medios_contacto (uno por fila), direcciones (tipadas) y
contactos (la persona de contacto de un proveedor o transportista, ligada a
su tercero). Las columnas se eliminan; los modelos los siguen ofreciendo
como propiedades (modelos/comercial.py: ConContacto).

Revision ID: 0055
Revises: 0054
Create Date: 2026-10-13 00:00:00
"""
import re

from alembic import op
import sqlalchemy as sa


revision = '0055'
down_revision = '0054'
branch_labels = None
depends_on = None


def _correos(texto):
    vistos = []
    for x in re.split(r"[,;\s]+", texto or ""):
        x = x.strip().lower()
        if x and x not in vistos:
            vistos.append(x)
    return vistos


def _medio(con, org, dueno, did, tipo, valor, uso, principal):
    con.execute(sa.text(f"INSERT INTO medios_contacto ({dueno}, tipo, valor, uso, principal, organizacion_id) "
                        "VALUES (:d, :t, :v, :u, :p, :o)"),
                {"d": did, "t": tipo, "v": valor[:200], "u": uso, "p": principal, "o": org})


def _direccion(con, org, dueno, did, tipo, texto, pais):
    con.execute(sa.text(f"INSERT INTO direcciones ({dueno}, tipo, linea1, pais, principal, organizacion_id) "
                        "VALUES (:d, :t, :l, :p, :si, :o)"), {"d": did, "t": tipo, "l": texto[:300], "p": pais, "si": True, "o": org})


def upgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table('contactos', schema=None) as b:
        b.add_column(sa.Column('tercero_id', sa.Integer(), nullable=True))
        b.create_index(b.f('ix_contactos_tercero_id'), ['tercero_id'], unique=False)
        b.create_foreign_key('fk_contactos_tercero_id', 'terceros', ['tercero_id'], ['id'], ondelete='CASCADE')

    # Proveedores y transportistas: todo en su tercero (sin repetir lo que ya tenga)
    for tabla, cols in (("proveedores", "direccion, contacto, correos, telefono, pais"),
                        ("transportistas", "NULL AS direccion, contacto, correos, telefono, pais")):
        for f in con.execute(sa.text(f"SELECT organizacion_id, tercero_id, {cols} FROM {tabla} "
                                     "WHERE tercero_id IS NOT NULL ORDER BY id")).mappings().all():
            org, tid = f["organizacion_id"], f["tercero_id"]
            existentes = set(con.execute(sa.text("SELECT lower(valor) FROM medios_contacto WHERE tercero_id = :t"),
                                         {"t": tid}).scalars())
            for i, c in enumerate(_correos(f["correos"])):
                if c not in existentes:
                    _medio(con, org, "tercero_id", tid, "CORREO", c, None, i == 0 and not existentes)
                    existentes.add(c)
            if f["telefono"] and f["telefono"].strip().lower() not in existentes:
                _medio(con, org, "tercero_id", tid, "TELEFONO", f["telefono"].strip(), None, True)
            if f["direccion"] and f["direccion"].strip() and not con.execute(
                    sa.text("SELECT 1 FROM direcciones WHERE tercero_id = :t AND tipo = 'FISCAL'"), {"t": tid}).first():
                _direccion(con, org, "tercero_id", tid, "FISCAL", f["direccion"].strip(), f["pais"])
            if f["contacto"] and f["contacto"].strip() and not con.execute(
                    sa.text("SELECT 1 FROM contactos WHERE tercero_id = :t AND lower(nombre) = lower(:n)"),
                    {"t": tid, "n": f["contacto"].strip()}).first():
                con.execute(sa.text("INSERT INTO contactos (tercero_id, nombre, rol, activo, organizacion_id) "
                                    "VALUES (:t, :n, 'LOGISTICA', :si, :o)"),
                            {"t": tid, "n": f["contacto"].strip()[:120], "si": True, "o": org})
    # Sociedades (facturación) y centros (notify)
    for tabla, dueno, uso, tipo in (("sociedades", "sociedad_id", "FACTURACION", "FISCAL"),
                                    ("centros", "centro_id", "NOTIFY", "ENTREGA")):
        for f in con.execute(sa.text(f"SELECT id, organizacion_id, direccion, correos, pais FROM {tabla}")).mappings().all():
            for i, c in enumerate(_correos(f["correos"])):
                _medio(con, f["organizacion_id"], dueno, f["id"], "CORREO", c, uso, i == 0)
            if f["direccion"] and f["direccion"].strip():
                _direccion(con, f["organizacion_id"], dueno, f["id"], tipo, f["direccion"].strip(), f["pais"])
    for f in con.execute(sa.text("SELECT id, organizacion_id, correos, telefono FROM contactos")).mappings().all():
        for i, c in enumerate(_correos(f["correos"])):
            _medio(con, f["organizacion_id"], "contacto_id", f["id"], "CORREO", c, None, i == 0)
        if f["telefono"] and f["telefono"].strip():
            _medio(con, f["organizacion_id"], "contacto_id", f["id"], "TELEFONO", f["telefono"].strip(), None, True)

    for tabla, columnas in (("centros", ["correos", "direccion"]), ("contactos", ["correos", "telefono"]),
                            ("proveedores", ["correos", "telefono", "direccion", "contacto"]),
                            ("sociedades", ["correos", "direccion"]),
                            ("transportistas", ["correos", "telefono", "contacto"])):
        with op.batch_alter_table(tabla, schema=None) as b:
            for c in columnas:
                b.drop_column(c)


def downgrade() -> None:
    con = op.get_bind()
    tipos = {"correos": sa.String(500), "telefono": sa.String(40), "direccion": sa.String(300), "contacto": sa.String(120)}
    for tabla, columnas in (("centros", ["correos", "direccion"]), ("contactos", ["correos", "telefono"]),
                            ("proveedores", ["correos", "telefono", "direccion", "contacto"]),
                            ("sociedades", ["correos", "direccion"]),
                            ("transportistas", ["correos", "telefono", "contacto"])):
        with op.batch_alter_table(tabla, schema=None) as b:
            for c in columnas:
                b.add_column(sa.Column(c, tipos[c], nullable=True))

    def medios(dueno, did, tipo):
        return [v for (v,) in con.execute(sa.text(f"SELECT valor FROM medios_contacto WHERE {dueno} = :d AND tipo = :t "
                                                  "ORDER BY principal DESC, id"), {"d": did, "t": tipo})]

    def direccion(dueno, did):
        return con.execute(sa.text(f"SELECT linea1 FROM direcciones WHERE {dueno} = :d ORDER BY principal DESC, id"),
                           {"d": did}).scalar()

    for tabla, dueno in (("sociedades", "sociedad_id"), ("centros", "centro_id")):
        for (i,) in con.execute(sa.text(f"SELECT id FROM {tabla}")).all():
            con.execute(sa.text(f"UPDATE {tabla} SET correos = :c, direccion = :d WHERE id = :i"),
                        {"c": ", ".join(medios(dueno, i, "CORREO"))[:500] or None, "d": direccion(dueno, i), "i": i})
    for (i,) in con.execute(sa.text("SELECT id FROM contactos WHERE tercero_id IS NULL")).all():
        con.execute(sa.text("UPDATE contactos SET correos = :c, telefono = :t WHERE id = :i"),
                    {"c": ", ".join(medios("contacto_id", i, "CORREO"))[:500] or None,
                     "t": next(iter(medios("contacto_id", i, "TELEFONO")), None), "i": i})
    for tabla in ("proveedores", "transportistas"):
        for i, tid in con.execute(sa.text(f"SELECT id, tercero_id FROM {tabla} WHERE tercero_id IS NOT NULL")).all():
            datos = {"c": ", ".join(medios("tercero_id", tid, "CORREO"))[:500] or None,
                     "t": next(iter(medios("tercero_id", tid, "TELEFONO")), None),
                     "n": con.execute(sa.text("SELECT nombre FROM contactos WHERE tercero_id = :t ORDER BY id"), {"t": tid}).scalar(),
                     "i": i}
            extra = ", direccion = :d" if tabla == "proveedores" else ""
            if tabla == "proveedores":
                datos["d"] = direccion("tercero_id", tid)
            con.execute(sa.text(f"UPDATE {tabla} SET correos = :c, telefono = :t, contacto = :n{extra} WHERE id = :i"), datos)
    con.execute(sa.text("DELETE FROM contactos WHERE tercero_id IS NOT NULL"))
    with op.batch_alter_table('contactos', schema=None) as b:
        b.drop_constraint('fk_contactos_tercero_id', type_='foreignkey')
        b.drop_index(b.f('ix_contactos_tercero_id'))
        b.drop_column('tercero_id')
