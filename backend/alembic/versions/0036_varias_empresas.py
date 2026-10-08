"""Varias empresas en una instalación

- Tabla organizaciones; los datos actuales quedan en la empresa 1.
- organizacion_id en cada tabla de negocio (con su índice y clave foránea).
- Los códigos que eran únicos en toda la base (proveedor, sociedad, centro,
  SKU, embarque, rol…) pasan a ser únicos dentro de cada empresa.
- usuarios.plataforma: administra la plataforma (los administradores actuales).
- sesiones.organizacion_id: empresa en la que trabaja esa sesión.

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-08 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0036'
down_revision = '0035'
branch_labels = None
depends_on = None

TABLAS = [
    "proveedores", "transportistas", "tipos_unidad", "roles", "usuarios", "sociedades", "centros", "almacenes",
    "contactos", "regiones_leadtime", "pasos_leadtime", "reglas_leadtime", "marcas", "escalas_talla",
    "grupos_articulos", "prepacks", "productos", "articulos", "ordenes_compra", "posiciones_oc", "facturas",
    "factura_lineas", "archivos", "packing_lists", "pl_lineas", "grupos_cajas", "grupo_cajas_items", "tipos_empaque",
    "plantillas_caja", "recepciones", "embarques", "unidades_carga", "eventos_embarque", "historial", "alertas",
    "importaciones_oc", "partidas_pais", "producto_fotos", "producto_documentos", "producto_versiones",
    "prepack_componentes", "historial_clasificacion", "overrides_arancel",
]
# Únicos en toda la base → únicos por empresa
UNICOS = {
    "proveedores": "codigo", "transportistas": "codigo", "tipos_unidad": "codigo", "roles": "nombre",
    "sociedades": "codigo", "centros": "codigo", "almacenes": "codigo", "regiones_leadtime": "codigo",
    "pasos_leadtime": "codigo", "marcas": "codigo", "escalas_talla": "codigo", "grupos_articulos": "codigo",
    "tipos_empaque": "codigo", "embarques": "codigo", "articulos": "sku",
}
CONVENCION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _nombre_unico(tabla: str, col: str) -> str:
    # SQLite: el único sin nombre se reconoce con la convención; PostgreSQL le dio <tabla>_<col>_key
    return f"uq_{tabla}_{col}" if op.get_bind().dialect.name == "sqlite" else f"{tabla}_{col}_key"


def upgrade() -> None:
    op.create_table(
        "organizaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(200), nullable=False),
        sa.Column("razon_social", sa.String(200), nullable=True),
        sa.Column("id_fiscal", sa.String(40), nullable=True),
        sa.Column("pais", sa.String(2), nullable=True),
        sa.Column("logo", sa.Text(), nullable=True),
        sa.Column("configuracion", sa.JSON(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("creada_en", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("codigo"),
    )
    con = op.get_bind()
    nombre = con.execute(sa.text("SELECT empresa FROM usuarios WHERE empresa IS NOT NULL AND rol IN ('admin', 'interno') "
                                 "ORDER BY id LIMIT 1")).scalar() or "Main company"
    con.execute(sa.text("INSERT INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en) "
                        "VALUES (1, 'MAIN', :n, '{}', :a, CURRENT_TIMESTAMP)"), {"n": nombre, "a": True})

    for tabla in TABLAS:
        unico = UNICOS.get(tabla)
        with op.batch_alter_table(tabla, schema=None, naming_convention=CONVENCION) as b:
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
                b.drop_constraint(_nombre_prepacks(), type_="unique")
                b.create_unique_constraint("uq_prepacks_org_estilo_color_codigo",
                                           ["organizacion_id", "estilo", "color", "codigo"])

    with op.batch_alter_table("usuarios", schema=None) as b:
        b.add_column(sa.Column("plataforma", sa.Boolean(), nullable=False, server_default=sa.false()))
    con.execute(sa.text("UPDATE usuarios SET plataforma = :v WHERE rol = 'admin'"), {"v": True})
    with op.batch_alter_table("sesiones", schema=None) as b:
        b.add_column(sa.Column("organizacion_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_sesiones_organizacion", "organizaciones", ["organizacion_id"], ["id"])


def _nombre_prepacks() -> str:
    return "uq_prepacks_estilo" if op.get_bind().dialect.name == "sqlite" else "prepacks_estilo_color_codigo_key"


def downgrade() -> None:
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
                b.create_unique_constraint(f"uq_{tabla}_{unico}", [unico])
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
    op.drop_table("organizaciones")
