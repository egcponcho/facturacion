"""Una sola empresa por instalación

Deshace el aislamiento por empresa de la migración 0036 y conserva la tabla
`organizaciones` como la ficha de la empresa (nombre, logo, preferencias y
reglas de negocio):

- Quita organizacion_id de las tablas de negocio y de las sesiones.
- Los códigos vuelven a ser únicos en toda la base.
- Quita usuarios.plataforma.

Si la base ya tiene datos de una segunda empresa, la migración se detiene sin
cambiar nada: hay que separar esa empresa en su propia instalación antes.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-09 00:00:00
"""
import importlib.util
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = '0037'
down_revision = '0036'
branch_labels = None
depends_on = None

# Mismas tablas y únicos que la migración 0036
_ruta = Path(__file__).with_name("0036_varias_empresas.py")
_spec = importlib.util.spec_from_file_location("migracion_0036", _ruta)
_m0036 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m0036)
TABLAS, UNICOS = _m0036.TABLAS, _m0036.UNICOS


def _nombre_unico(tabla: str, col: str) -> str:
    return f"uq_{tabla}_{col}"


def upgrade() -> None:
    con = op.get_bind()
    otras = [t for t in TABLAS
             if con.execute(sa.text(f"SELECT 1 FROM {t} WHERE organizacion_id <> 1 LIMIT 1")).first()]
    if otras:
        raise RuntimeError(
            "La base tiene datos de más de una empresa (tablas: " + ", ".join(otras) + "). "
            "Cada instalación sirve a una sola empresa: separe las demás antes de actualizar.")
    con.execute(sa.text("DELETE FROM organizaciones WHERE id <> 1"))

    with op.batch_alter_table("sesiones", schema=None) as b:
        b.drop_constraint("fk_sesiones_organizacion", type_="foreignkey")
        b.drop_column("organizacion_id")
    with op.batch_alter_table("usuarios", schema=None) as b:
        b.drop_column("plataforma")
    for tabla in reversed(TABLAS):
        unico = UNICOS.get(tabla)
        with op.batch_alter_table(tabla, schema=None) as b:
            if unico:
                b.drop_constraint(f"uq_{tabla}_org_{unico}", type_="unique")
                b.create_unique_constraint(_nombre_unico(tabla, unico), [unico])
            if tabla == "productos":
                b.drop_constraint("uq_productos_org_codigo_generico", type_="unique")
                b.drop_index("ix_productos_codigo_generico")
                b.create_index("ix_productos_codigo_generico", ["codigo_generico"], unique=True)
            if tabla == "prepacks":
                b.drop_constraint("uq_prepacks_org_estilo_color_codigo", type_="unique")
                b.create_unique_constraint("uq_prepacks_estilo", ["estilo", "color", "codigo"])
            b.drop_index(f"ix_{tabla}_organizacion_id")
            b.drop_constraint(f"fk_{tabla}_organizacion", type_="foreignkey")
            b.drop_column("organizacion_id")


def downgrade() -> None:
    """Vuelve al esquema de la 0036 (todo queda en la empresa 1)."""
    for tabla in TABLAS:
        unico = UNICOS.get(tabla)
        with op.batch_alter_table(tabla, schema=None, naming_convention=_m0036.CONVENCION) as b:
            b.add_column(sa.Column("organizacion_id", sa.Integer(), nullable=False, server_default="1"))
            b.create_foreign_key(f"fk_{tabla}_organizacion", "organizaciones", ["organizacion_id"], ["id"])
            b.create_index(f"ix_{tabla}_organizacion_id", ["organizacion_id"], unique=False)
            if unico:
                b.drop_constraint(_nombre_unico(tabla, unico), type_="unique")
                b.create_unique_constraint(f"uq_{tabla}_org_{unico}", ["organizacion_id", unico])
            if tabla == "productos":
                b.drop_index("ix_productos_codigo_generico")
                b.create_index("ix_productos_codigo_generico", ["codigo_generico"], unique=False)
                b.create_unique_constraint("uq_productos_org_codigo_generico", ["organizacion_id", "codigo_generico"])
            if tabla == "prepacks":
                b.drop_constraint("uq_prepacks_estilo", type_="unique")
                b.create_unique_constraint("uq_prepacks_org_estilo_color_codigo",
                                           ["organizacion_id", "estilo", "color", "codigo"])
    with op.batch_alter_table("usuarios", schema=None) as b:
        b.add_column(sa.Column("plataforma", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("sesiones", schema=None) as b:
        b.add_column(sa.Column("organizacion_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_sesiones_organizacion", "organizaciones", ["organizacion_id"], ["id"])
