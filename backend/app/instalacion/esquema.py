"""Ayudas de las migraciones: seguridad por fila de una tabla nueva y
verificaciones de datos antes de agregar una restricción."""
import sqlalchemy as sa

CONDICION_RLS = ("coalesce(current_setting('app.organizacion_id', true), '') = '' "
                 "OR organizacion_id = nullif(current_setting('app.organizacion_id', true), '')::integer")


def rls(op, *tablas: str) -> None:
    """PostgreSQL: la tabla solo deja leer y escribir filas de la organización de la transacción (ver 0047)."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in tablas:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY; ALTER TABLE {t} FORCE ROW LEVEL SECURITY; "
                   f"CREATE POLICY aislamiento_organizacion ON {t} USING ({CONDICION_RLS}) WITH CHECK ({CONDICION_RLS})")


def sin_violaciones(con, tabla: str, condicion: str, que: str) -> None:
    """Antes de agregar una restricción: si hay filas que no la cumplen, la
    migración se detiene y dice cuáles (no se corrige un dato a ciegas)."""
    filas = con.execute(sa.text(f"SELECT id FROM {tabla} WHERE NOT ({condicion}) ORDER BY id LIMIT 20")).scalars().all()
    if filas:
        raise RuntimeError(f"No se puede agregar la regla «{que}» a {tabla}: corrija primero las filas con id {filas}.")
