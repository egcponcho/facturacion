"""Varias organizaciones en una instalación, con aislamiento de datos

- organizacion_id (con índice y llave foránea) en las 48 tablas de negocio,
  configuración, usuarios y roles. Los datos actuales quedan en la
  organización 1.
- Los códigos que eran únicos en toda la base (proveedor, sociedad, centro,
  SKU, embarque, rol, valores de las listas…) pasan a ser únicos dentro de
  cada organización. El correo del usuario sigue siendo único en toda la
  plataforma: al entrar identifica su organización.
- usuarios.plataforma: administra la plataforma (los administradores actuales).
- sesiones.organizacion_id: organización en la que trabaja la sesión.
- PostgreSQL: seguridad por fila (RLS) en esas tablas. Con
  `app.organizacion_id` fijado (cada transacción de una petición), solo se
  leen y escriben filas de esa organización, aun con SQL escrito a mano. Sin
  fijarlo (migraciones, arranque, plataforma) no se limita.

Los datos compartidos (países, acuerdos comerciales, arancel oficial y motor
de clasificación) no llevan organización: los mantiene la plataforma.

Revision ID: 0047
Revises: 0046
Create Date: 2026-10-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0047'
down_revision = '0046'
branch_labels = None
depends_on = None

TABLAS = [
    "proveedores", "sociedades", "centros", "almacenes", "contactos", "marcas", "escalas_talla", "grupos_articulos",
    "categorias_articulo", "articulos", "prepacks", "prepack_componentes", "valores_lista", "estados_liberacion",
    "productos", "partidas_pais", "producto_fotos", "producto_documentos", "producto_versiones", "transportistas",
    "tipos_unidad", "puertos", "regiones_leadtime", "pasos_leadtime", "reglas_leadtime", "tipos_empaque",
    "plantillas_caja", "perfiles_importacion", "ordenes_compra", "posiciones_oc", "importaciones_oc", "facturas",
    "factura_lineas", "archivos", "packing_lists", "pl_lineas", "grupos_cajas", "grupo_cajas_items", "recepciones",
    "embarques", "unidades_carga", "eventos_embarque", "roles", "usuarios", "historial", "alertas",
    "historial_clasificacion", "overrides_arancel",
]
# Únicos en toda la base → únicos por organización: tabla → columnas
UNICOS = {
    "proveedores": ["codigo"], "sociedades": ["codigo"], "centros": ["codigo"], "almacenes": ["codigo"],
    "marcas": ["codigo"], "escalas_talla": ["codigo"], "grupos_articulos": ["codigo"], "categorias_articulo": ["codigo"],
    "articulos": ["sku"], "transportistas": ["codigo"], "tipos_unidad": ["codigo"], "puertos": ["codigo"],
    "regiones_leadtime": ["codigo"], "pasos_leadtime": ["codigo"], "tipos_empaque": ["codigo"], "embarques": ["codigo"],
    "roles": ["nombre"], "perfiles_importacion": ["codigo"],
    "valores_lista": ["lista", "codigo"], "estados_liberacion": ["tipo", "codigo"], "prepacks": ["estilo", "color", "codigo"],
}
NOMBRES_NUEVOS = {"valores_lista": "uq_valores_lista_org_lista_codigo",
                  "estados_liberacion": "uq_estados_liberacion_org_tipo_codigo",
                  "prepacks": "uq_prepacks_org_estilo_color_codigo"}
# Nombres que tenían antes de esta migración (los restaura la bajada)
NOMBRES_ANTERIORES = {"valores_lista": "uq_valores_lista_lista_codigo",
                      "estados_liberacion": "uq_estados_liberacion_tipo_codigo", "prepacks": "uq_prepacks_estilo"}
# SQLite no guarda el nombre de un único declarado en la columna: con esta
# convención el modo batch lo reconoce como uq_<tabla>_<columna>
CONVENCION = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def _nombre_nuevo(tabla: str) -> str:
    return NOMBRES_NUEVOS.get(tabla) or f"uq_{tabla}_org_{UNICOS[tabla][0]}"


def _unico_actual(insp, tabla: str, columnas: list[str]) -> str:
    for u in insp.get_unique_constraints(tabla):
        if u["column_names"] == columnas:
            return u["name"] or f"uq_{tabla}_{columnas[0]}"
    raise RuntimeError(f"No se encontró el único {columnas} de {tabla}")


def _politica(tabla: str) -> str:
    # nullif: PostgreSQL no evalúa el OR en orden, y ''::integer fallaría
    condicion = ("coalesce(current_setting('app.organizacion_id', true), '') = '' "
                 "OR organizacion_id = nullif(current_setting('app.organizacion_id', true), '')::integer")
    if tabla == "usuarios":  # cada usuario ve siempre su propio registro
        condicion += " OR id = nullif(current_setting('app.usuario_id', true), '')::integer"
    return (f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY; ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY; "
            f"CREATE POLICY aislamiento_organizacion ON {tabla} USING ({condicion}) WITH CHECK ({condicion})")


def upgrade() -> None:
    con = op.get_bind()
    postgres = con.dialect.name == "postgresql"
    insp = sa.inspect(con)
    if not con.execute(sa.text("SELECT 1 FROM organizaciones WHERE id = 1")).first():
        con.execute(sa.text("INSERT INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en) "
                            "VALUES (1, 'MAIN', 'My company', '{}', :a, CURRENT_TIMESTAMP)"), {"a": True})
    elif postgres:
        con.execute(sa.text("SELECT setval(pg_get_serial_sequence('organizaciones', 'id'), "
                            "(SELECT max(id) FROM organizaciones))"))

    for tabla in TABLAS:
        columnas = UNICOS.get(tabla)
        viejo = _unico_actual(insp, tabla, columnas) if columnas else None
        with op.batch_alter_table(tabla, schema=None, naming_convention=CONVENCION) as b:
            b.add_column(sa.Column("organizacion_id", sa.Integer(), nullable=False, server_default="1"))
            b.create_foreign_key(f"fk_{tabla}_organizacion_id_organizaciones", "organizaciones",
                                 ["organizacion_id"], ["id"])
            b.create_index(f"ix_{tabla}_organizacion_id", ["organizacion_id"], unique=False)
            if columnas:
                b.drop_constraint(viejo, type_="unique")
                b.create_unique_constraint(_nombre_nuevo(tabla), ["organizacion_id", *columnas])
            if tabla == "productos":
                b.drop_index("ix_productos_codigo_generico")
                b.create_index("ix_productos_codigo_generico", ["codigo_generico"], unique=False)
                b.create_unique_constraint("uq_productos_org_codigo_generico", ["organizacion_id", "codigo_generico"])
        # Los registros nuevos toman la organización de la aplicación, no un valor fijo
        with op.batch_alter_table(tabla, schema=None) as b:
            b.alter_column("organizacion_id", server_default=None)

    with op.batch_alter_table("usuarios", schema=None) as b:
        b.add_column(sa.Column("plataforma", sa.Boolean(), nullable=False, server_default=sa.false()))
    con.execute(sa.text("UPDATE usuarios SET plataforma = :si WHERE rol = 'admin'"), {"si": True})
    with op.batch_alter_table("sesiones", schema=None) as b:
        b.add_column(sa.Column("organizacion_id", sa.Integer(), nullable=True))
        b.create_foreign_key("fk_sesiones_organizacion_id_organizaciones", "organizaciones", ["organizacion_id"], ["id"])

    if postgres:
        for tabla in TABLAS:
            op.execute(_politica(tabla))


def downgrade() -> None:
    con = op.get_bind()
    postgres = con.dialect.name == "postgresql"
    otras = [t for t in TABLAS if con.execute(sa.text(f"SELECT 1 FROM {t} WHERE organizacion_id <> 1 LIMIT 1")).first()]
    if otras:
        raise RuntimeError("La base tiene datos de más de una organización (tablas: " + ", ".join(otras) + "). "
                           "Sepárelas antes de volver a una sola empresa por instalación.")
    if postgres:
        for tabla in TABLAS:
            op.execute(f"DROP POLICY IF EXISTS aislamiento_organizacion ON {tabla}; "
                       f"ALTER TABLE {tabla} NO FORCE ROW LEVEL SECURITY; ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")
    with op.batch_alter_table("sesiones", schema=None) as b:
        b.drop_constraint("fk_sesiones_organizacion_id_organizaciones", type_="foreignkey")
        b.drop_column("organizacion_id")
    with op.batch_alter_table("usuarios", schema=None) as b:
        b.drop_column("plataforma")
    for tabla in reversed(TABLAS):
        columnas = UNICOS.get(tabla)
        with op.batch_alter_table(tabla, schema=None) as b:
            if tabla == "productos":
                b.drop_constraint("uq_productos_org_codigo_generico", type_="unique")
                b.drop_index("ix_productos_codigo_generico")
                b.create_index("ix_productos_codigo_generico", ["codigo_generico"], unique=True)
            if columnas:
                b.drop_constraint(_nombre_nuevo(tabla), type_="unique")
                b.create_unique_constraint(NOMBRES_ANTERIORES.get(tabla) or f"uq_{tabla}_{columnas[0]}", columnas)
            b.drop_index(f"ix_{tabla}_organizacion_id")
            b.drop_constraint(f"fk_{tabla}_organizacion_id_organizaciones", type_="foreignkey")
            b.drop_column("organizacion_id")
