"""Integridad referencial: catálogos tipados, reglas de aprobación en tabla
y llaves foráneas en los códigos de los documentos

- monedas, unidades_medida, modos_transporte, incoterms y condiciones_pago
  salen de valores_lista a su propia tabla (con sus reglas: decimales de la
  moneda, cálculo del modo, plazo de la condición). valores_lista queda con
  las listas simples y pierde las columnas que solo usaban esas listas.
- reglas_aprobacion_oc: las reglas de aprobación de OCs salen del JSON de
  configuración a una tabla con llave foránea al rol que aprueba;
  aprobaciones_oc guarda además la regla (regla_id) y su paso es único.
- Llaves foráneas compuestas (organizacion_id, código) → catálogo de los
  códigos que guardan los documentos y maestros (app/modelos/referencias.py),
  y llave al país (ISO) de las columnas de país. Un país en uso que faltaba
  en el catálogo se agrega con su código como nombre.
- Coherencia de organización entre documentos padre e hijo: llaves
  (padre_id, organizacion_id) → padre(id, organizacion_id).
- Únicos que faltaban: línea de factura una vez por PL, código nacional y
  nota legal una vez por versión, conocimiento de clasificación por su huella.
- Índices en las llaves foráneas que no lo tenían.

Si un dato no cumple una de las nuevas reglas, la migración se detiene y dice
qué corregir (nunca se inventa ni se borra un dato de negocio).

Revision ID: 0053
Revises: 0052
Create Date: 2026-10-13 00:00:00
"""
import hashlib
import json
import re

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0053'
down_revision = '0052'
branch_labels = None
depends_on = None

TIPADAS = {  # lista → (tabla, columnas propias, valores por defecto)
    "moneda": ("monedas", ["simbolo", "decimales", "letras_en", "letras_es"], {"decimales": 2}),
    "unidad": ("unidades_medida", ["nombre_plural", "alias", "contable"], {"contable": True}),
    "modo_transporte": ("modos_transporte", ["calculo", "factor", "icono", "documento", "etiqueta_puerto",
                                             "etiqueta_transportista", "etiqueta_unidad"], {"calculo": "VOLUMEN"}),
    "incoterm": ("incoterms", [], {}),
    "condicion_pago": ("condiciones_pago", ["alias"], {}),
}
LARGO_CODIGO = {"moneda": 3, "unidad": 10, "incoterm": 10, "modo_transporte": 20, "condicion_pago": 20}
COLUMNAS_LISTA = [  # columnas de valores_lista que solo usaban las listas con tabla propia
    ("nombre_plural", sa.String(120)), ("alias", sa.String(300)), ("contable", sa.Boolean()), ("simbolo", sa.String(5)),
    ("decimales", sa.Integer()), ("letras_en", sa.String(120)), ("letras_es", sa.String(120)),
    ("calculo", sa.String(20)), ("factor", sa.Float()), ("icono", sa.String(20)), ("documento", sa.String(40)),
    ("etiqueta_puerto", sa.String(40)), ("etiqueta_transportista", sa.String(40)), ("etiqueta_unidad", sa.String(80)),
]
INDICES = {
    'articulos': ['prepack_id'], 'atributos_def': ['version_id'], 'centro_puertos': ['puerto_id'],
    'control_capitulos': ['version_id'], 'grupos_cajas': ['plantilla_id', 'tipo_empaque_id'],
    'nodos_arancel': ['padre_id'], 'partidas_pais': ['inciso_id'], 'plantillas_caja': ['tipo_empaque_id'],
    'prepack_componentes': ['articulo_id'], 'productos': ['grupo_id'], 'proveedor_marcas': ['marca_id'],
    'proveedor_sociedades': ['sociedad_id'], 'reglas_clasificacion': ['version_id'], 'reglas_impuesto': ['version_id'],
    'regulaciones': ['version_id'], 'tipo_empaque_contiene': ['hijo_id'], 'transportista_sociedades': ['sociedad_id'],
    'usuarios': ['proveedor_id'],
}
# Copia de app/modelos/referencias.py al momento de esta migración
REFERENCIAS = {
    "ordenes_compra": [("sociedad", "sociedades"), ("centro", "centros"), ("centro_destino", "centros"),
                       ("puerto_despacho", "puertos"), ("moneda", "monedas"), ("incoterm", "incoterms"),
                       ("condicion_pago", "condiciones_pago"), ("pais_origen", "paises"),
                       ("pais_procedencia", "paises")],
    "posiciones_oc": [("almacen", "almacenes"), ("marca", "marcas"), ("grupo", "grupos_articulos"),
                      ("categoria", "categorias_articulo"), ("unidad", "unidades_medida"), ("pais_origen", "paises")],
    "facturas": [("sociedad", "sociedades"), ("centro", "centros"), ("centro_destino", "centros"),
                 ("moneda", "monedas"), ("incoterm", "incoterms")],
    "factura_lineas": [("pais_origen", "paises")],
    "embarques": [("centro", "centros"), ("puerto_origen", "puertos"), ("puerto_destino", "puertos"),
                  ("tipo_transporte", "modos_transporte")],
    "sociedades": [("moneda", "monedas"), ("pais", "paises")],
    "centros": [("puerto", "puertos"), ("pais", "paises")],
    "puertos": [("tipo", "modos_transporte"), ("pais", "paises")],
    "proveedores": [("pais", "paises")],
    "transportistas": [("pais", "paises")],
    "organizaciones": [("pais", "paises")],
    "grupos_articulos": [("categoria", "categorias_articulo")],
    "escalas_talla": [("categoria", "categorias_articulo")],
    "articulos": [("unidad", "unidades_medida")],
    "plantillas_caja": [("unidad", "unidades_medida")],
    "tipos_unidad": [("modo", "modos_transporte")],
    "reglas_leadtime": [("region", "regiones_leadtime"), ("pais", "paises"), ("puerto", "puertos")],
}
COHERENCIA = {
    "posiciones_oc": [("oc_id", "ordenes_compra")],
    "aprobaciones_oc": [("oc_id", "ordenes_compra")],
    "ordenes_compra": [("proveedor_id", "proveedores")],
    "facturas": [("proveedor_id", "proveedores")],
    "factura_lineas": [("factura_id", "facturas"), ("posicion_oc_id", "posiciones_oc")],
    "packing_lists": [("factura_id", "facturas"), ("unidad_carga_id", "unidades_carga")],
    "pl_lineas": [("pl_id", "packing_lists"), ("factura_linea_id", "factura_lineas")],
    "grupos_cajas": [("pl_id", "packing_lists")],
    "grupo_cajas_items": [("grupo_id", "grupos_cajas"), ("pl_linea_id", "pl_lineas")],
    "recepciones": [("pl_linea_id", "pl_lineas")],
    "unidades_carga": [("embarque_id", "embarques")],
    "eventos_embarque": [("embarque_id", "embarques")],
}
PADRES = sorted({p for lista in COHERENCIA.values() for _, p in lista})


def _detener(mensaje: str, filas) -> None:
    filas = list(filas)
    if filas:
        raise RuntimeError(f"{mensaje}: {filas[:10]}")


def _tablas_tipadas() -> None:

    op.create_table('condiciones_pago',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('alias', sa.String(length=300), nullable=True),
    sa.Column('dias', sa.Integer(), nullable=True),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('dias IS NULL OR dias >= 0', name='ck_condiciones_pago_dias'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_condiciones_pago_org_codigo')
    )
    with op.batch_alter_table('condiciones_pago', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_condiciones_pago_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('incoterms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_incoterms_org_codigo')
    )
    with op.batch_alter_table('incoterms', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_incoterms_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('modos_transporte',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('calculo', sa.String(length=20), nullable=False),
    sa.Column('factor', sa.Float(), nullable=True),
    sa.Column('icono', sa.String(length=20), nullable=True),
    sa.Column('documento', sa.String(length=40), nullable=True),
    sa.Column('etiqueta_puerto', sa.String(length=40), nullable=True),
    sa.Column('etiqueta_transportista', sa.String(length=40), nullable=True),
    sa.Column('etiqueta_unidad', sa.String(length=80), nullable=True),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("calculo IN ('VOLUMEN', 'PESO_COBRABLE')", name='ck_modos_transporte_calculo'),
    sa.CheckConstraint('factor IS NULL OR factor > 0', name='ck_modos_transporte_factor'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_modos_transporte_org_codigo')
    )
    with op.batch_alter_table('modos_transporte', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_modos_transporte_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('monedas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=3), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('simbolo', sa.String(length=5), nullable=True),
    sa.Column('decimales', sa.Integer(), nullable=False),
    sa.Column('letras_en', sa.String(length=120), nullable=True),
    sa.Column('letras_es', sa.String(length=120), nullable=True),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('decimales BETWEEN 0 AND 4', name='ck_monedas_decimales'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_monedas_org_codigo')
    )
    with op.batch_alter_table('monedas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_monedas_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('unidades_medida',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('nombre_plural', sa.String(length=120), nullable=True),
    sa.Column('alias', sa.String(length=300), nullable=True),
    sa.Column('contable', sa.Boolean(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_unidades_medida_org_codigo')
    )
    with op.batch_alter_table('unidades_medida', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_unidades_medida_organizacion_id'), ['organizacion_id'], unique=False)


def _mover_listas(con) -> None:
    for lista, largo in LARGO_CODIGO.items():
        _detener(f"Hay códigos de la lista {lista} de más de {largo} caracteres; acórtelos antes de migrar",
                 con.execute(sa.text("SELECT codigo FROM valores_lista WHERE lista = :l AND length(codigo) > :n"),
                             {"l": lista, "n": largo}).scalars())
    for lista, (tabla, columnas, defecto) in TIPADAS.items():
        filas = con.execute(sa.text(
            f"SELECT organizacion_id, codigo, nombre, orden, activo{''.join(', ' + c for c in columnas)} "
            "FROM valores_lista WHERE lista = :l"), {"l": lista}).mappings().all()
        for f in filas:
            datos = {k: (f[k] if f[k] is not None else defecto.get(k)) for k in f.keys()}
            if lista == "condicion_pago":
                m = re.fullmatch(r"(?:NETO|NET|N)(\d+)", f["codigo"])
                datos["dias"] = int(m.group(1)) if m else (0 if f["codigo"] == "ANTICIPO" else None)
            cols = list(datos)
            con.execute(sa.text(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"),
                        datos)
        con.execute(sa.text("DELETE FROM valores_lista WHERE lista = :l"), {"l": lista})
    with op.batch_alter_table("valores_lista", schema=None) as b:
        for col, _ in COLUMNAS_LISTA:
            b.drop_column(col)


def _reglas_aprobacion(con) -> None:
    op.create_table('reglas_aprobacion_oc',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=80), nullable=False),
    sa.Column('monto_minimo', sa.Numeric(18, 4), nullable=False),
    sa.Column('moneda', sa.String(length=3), nullable=False),
    sa.Column('sociedad', sa.String(length=10), nullable=True),
    sa.Column('rol_id', sa.Integer(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('monto_minimo >= 0', name='ck_reglas_aprobacion_oc_monto_minimo'),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda'], ['monedas.organizacion_id', 'monedas.codigo'], name='fk_reglas_aprobacion_oc_moneda'),
    sa.ForeignKeyConstraint(['organizacion_id', 'sociedad'], ['sociedades.organizacion_id', 'sociedades.codigo'], name='fk_reglas_aprobacion_oc_sociedad'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['rol_id'], ['roles.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('reglas_aprobacion_oc', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reglas_aprobacion_oc_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reglas_aprobacion_oc_rol_id'), ['rol_id'], unique=False)
    rls(op, "reglas_aprobacion_oc")
    roles = set(con.execute(sa.text("SELECT id FROM roles")).scalars())
    for org, conf in con.execute(sa.text("SELECT id, configuracion FROM organizaciones")).all():
        conf = json.loads(conf) if isinstance(conf, str) else dict(conf or {})
        reglas = conf.pop("aprobaciones_oc", None) or []
        for i, r in enumerate(reglas, start=1):
            if r.get("rol_id") not in roles:
                raise RuntimeError(f"La regla de aprobación «{r.get('nombre')}» de la organización {org} usa un rol que "
                                   "ya no existe: corríjala en Configuración → Empresa antes de migrar.")
            con.execute(sa.text("INSERT INTO reglas_aprobacion_oc (nombre, monto_minimo, moneda, sociedad, rol_id, orden, "
                                "activo, organizacion_id) VALUES (:n, :m, :mo, :s, :r, :o, :a, :org)"),
                        {"n": r["nombre"], "m": r["monto_minimo"], "mo": r["moneda"], "s": r.get("sociedad"),
                         "r": r["rol_id"], "o": i, "a": True, "org": org})
        con.execute(sa.text("UPDATE organizaciones SET configuracion = :c WHERE id = :i"),
                    {"c": json.dumps(conf, ensure_ascii=False), "i": org})
    _detener("Hay OCs con dos pasos de aprobación con el mismo número",
             con.execute(sa.text("SELECT oc_id, paso FROM aprobaciones_oc GROUP BY oc_id, paso HAVING count(*) > 1")))
    with op.batch_alter_table('aprobaciones_oc', schema=None) as batch_op:
        batch_op.add_column(sa.Column('regla_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_aprobaciones_oc_regla_id'), ['regla_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aprobaciones_oc_rol_id'), ['rol_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aprobaciones_oc_usuario_id'), ['usuario_id'], unique=False)
        batch_op.create_unique_constraint('uq_aprobaciones_oc_oc_paso', ['oc_id', 'paso'])
        batch_op.create_foreign_key('fk_aprobaciones_oc_regla_id', 'reglas_aprobacion_oc', ['regla_id'], ['id'],
                                    ondelete='SET NULL')


def _huella(pais, codigo, origen, categoria, producto_id, condiciones) -> str:
    clave = json.dumps([pais or "", codigo, origen, categoria or "", producto_id or 0, condiciones or {}],
                       sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(clave.encode()).hexdigest()


def _unicos(con) -> None:
    _detener("Hay líneas de factura repetidas dentro de un PL",
             con.execute(sa.text("SELECT pl_id, factura_linea_id FROM pl_lineas GROUP BY pl_id, factura_linea_id "
                                 "HAVING count(*) > 1")))
    with op.batch_alter_table('pl_lineas', schema=None) as b:
        b.create_unique_constraint('uq_pl_lineas_pl_factura_linea', ['pl_id', 'factura_linea_id'])
    for tabla, cols in (("incisos_nacionales", ["pais", "codigo"]), ("notas_sac", ["ambito", "codigo", "numero"])):
        lista = ", ".join(cols)
        _detener(f"Hay registros repetidos en {tabla}",
                 con.execute(sa.text(f"SELECT {lista}, version_id FROM {tabla} GROUP BY {lista}, version_id HAVING count(*) > 1")))
        _detener(f"Hay registros repetidos sin versión en {tabla}",
                 con.execute(sa.text(f"SELECT {lista} FROM {tabla} WHERE version_id IS NULL GROUP BY {lista} HAVING count(*) > 1")))
        with op.batch_alter_table(tabla, schema=None) as b:
            b.create_index(f'ux_{tabla}_version', [*cols, 'version_id'], unique=True)
            b.create_index(f'ux_{tabla}_sin_version', cols, unique=True, sqlite_where=sa.text('version_id IS NULL'),
                           postgresql_where=sa.text('version_id IS NULL'))
    # Conocimiento de clasificación: huella de su clave natural; los repetidos se juntan sumando su respaldo
    with op.batch_alter_table('historial_clasificacion', schema=None) as b:
        b.add_column(sa.Column('huella', sa.String(length=64), nullable=True))
    vistos: dict[tuple, int] = {}
    for f in con.execute(sa.text("SELECT id, organizacion_id, pais, codigo, origen, categoria, producto_id, condiciones, conteo "
                                 "FROM historial_clasificacion ORDER BY id")).mappings().all():
        cond = json.loads(f["condiciones"]) if isinstance(f["condiciones"], str) else (f["condiciones"] or {})
        h = _huella(f["pais"], f["codigo"], f["origen"], f["categoria"], f["producto_id"], cond)
        clave = (f["organizacion_id"], h)
        if clave in vistos:
            con.execute(sa.text("UPDATE historial_clasificacion SET conteo = conteo + :c WHERE id = :i"),
                        {"c": f["conteo"] or 0, "i": vistos[clave]})
            con.execute(sa.text("DELETE FROM historial_clasificacion WHERE id = :i"), {"i": f["id"]})
        else:
            vistos[clave] = f["id"]
            con.execute(sa.text("UPDATE historial_clasificacion SET huella = :h WHERE id = :i"), {"h": h, "i": f["id"]})
    with op.batch_alter_table('historial_clasificacion', schema=None) as b:
        b.alter_column('huella', existing_type=sa.String(length=64), nullable=False)
        b.create_index(b.f('ix_historial_clasificacion_producto_id'), ['producto_id'], unique=False)
        b.create_unique_constraint('uq_historial_clasificacion_org_huella', ['organizacion_id', 'huella'])
    for tabla, cols in INDICES.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for c in cols:
                b.create_index(f"ix_{tabla}_{c}", [c], unique=False)


def _referencias(con) -> None:
    # Un código vacío no es un código: queda sin valor (solo en columnas que lo admiten)
    insp = sa.inspect(con)
    for tabla, refs in REFERENCIAS.items():
        nulas = {c["name"] for c in insp.get_columns(tabla) if c["nullable"]}
        for col, _ in refs:
            if col in nulas:
                con.execute(sa.text(f"UPDATE {tabla} SET {col} = NULL WHERE trim({col}) = ''"))
    # Países en uso que faltan en el catálogo compartido
    usados = set()
    for tabla, refs in REFERENCIAS.items():
        for col, cat in refs:
            if cat == "paises":
                usados |= set(con.execute(sa.text(f"SELECT DISTINCT {col} FROM {tabla} WHERE {col} IS NOT NULL")).scalars())
    existentes = set(con.execute(sa.text("SELECT codigo FROM paises")).scalars())
    for iso in sorted(usados - existentes):
        if not re.fullmatch(r"[A-Z]{2}", iso):
            raise RuntimeError(f"El país «{iso}» no es un código ISO de 2 letras: corríjalo antes de migrar.")
        con.execute(sa.text("INSERT INTO paises (codigo, nombre, activo) VALUES (:c, :c, :a)"), {"c": iso, "a": True})
    for tabla, refs in REFERENCIAS.items():
        for col, cat in refs:
            if cat == "paises":
                malos = con.execute(sa.text(f"SELECT DISTINCT {col} FROM {tabla} x WHERE {col} IS NOT NULL "
                                            f"AND NOT EXISTS (SELECT 1 FROM paises p WHERE p.codigo = x.{col})"))
            else:
                malos = con.execute(sa.text(
                    f"SELECT DISTINCT {col} FROM {tabla} x WHERE {col} IS NOT NULL AND NOT EXISTS "
                    f"(SELECT 1 FROM {cat} p WHERE p.organizacion_id = x.organizacion_id AND p.codigo = x.{col})"))
            _detener(f"{tabla}.{col} tiene códigos que no existen en {cat}; créelos en el catálogo antes de migrar", malos.scalars())
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, cat in refs:
                if cat == "paises":
                    b.create_foreign_key(f"fk_{tabla}_{col}", "paises", [col], ["codigo"])
                else:
                    b.create_foreign_key(f"fk_{tabla}_{col}", cat, ["organizacion_id", col], ["organizacion_id", "codigo"])


def _coherencia(con) -> None:
    for padre in PADRES:
        with op.batch_alter_table(padre, schema=None) as b:
            b.create_unique_constraint(f"uq_{padre}_id_org", ["id", "organizacion_id"])
    for tabla, lista in COHERENCIA.items():
        for col, padre in lista:
            _detener(f"{tabla}.{col} apunta a registros de otra organización",
                     con.execute(sa.text(f"SELECT x.id FROM {tabla} x JOIN {padre} p ON p.id = x.{col} "
                                         "WHERE p.organizacion_id <> x.organizacion_id")).scalars())
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, padre in lista:
                b.create_foreign_key(f"fk_{tabla}_{col}_org", padre, [col, "organizacion_id"], ["id", "organizacion_id"])


def upgrade() -> None:
    con = op.get_bind()
    _tablas_tipadas()
    rls(op, *[t for t, _, _ in TIPADAS.values()])
    _mover_listas(con)
    _reglas_aprobacion(con)
    _unicos(con)
    _referencias(con)
    _coherencia(con)


def downgrade() -> None:
    con = op.get_bind()
    for tabla, lista in COHERENCIA.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, _ in lista:
                b.drop_constraint(f"fk_{tabla}_{col}_org", type_="foreignkey")
    for padre in PADRES:
        with op.batch_alter_table(padre, schema=None) as b:
            b.drop_constraint(f"uq_{padre}_id_org", type_="unique")
    for tabla, refs in REFERENCIAS.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, _ in refs:
                b.drop_constraint(f"fk_{tabla}_{col}", type_="foreignkey")
    for tabla, cols in INDICES.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for c in cols:
                b.drop_index(f"ix_{tabla}_{c}")
    with op.batch_alter_table('historial_clasificacion', schema=None) as b:
        b.drop_constraint('uq_historial_clasificacion_org_huella', type_='unique')
        b.drop_index(b.f('ix_historial_clasificacion_producto_id'))
        b.drop_column('huella')
    for tabla in ("incisos_nacionales", "notas_sac"):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.drop_index(f'ux_{tabla}_sin_version')
            b.drop_index(f'ux_{tabla}_version')
    with op.batch_alter_table('pl_lineas', schema=None) as b:
        b.drop_constraint('uq_pl_lineas_pl_factura_linea', type_='unique')
    with op.batch_alter_table('aprobaciones_oc', schema=None) as b:
        b.drop_constraint('fk_aprobaciones_oc_regla_id', type_='foreignkey')
        b.drop_constraint('uq_aprobaciones_oc_oc_paso', type_='unique')
        b.drop_index(b.f('ix_aprobaciones_oc_usuario_id'))
        b.drop_index(b.f('ix_aprobaciones_oc_rol_id'))
        b.drop_index(b.f('ix_aprobaciones_oc_regla_id'))
        b.drop_column('regla_id')
    # Reglas de aprobación de vuelta al JSON de configuración
    por_org: dict[int, list] = {}
    for f in con.execute(sa.text("SELECT organizacion_id, nombre, monto_minimo, moneda, sociedad, rol_id FROM reglas_aprobacion_oc "
                                 "ORDER BY orden, id")).mappings():
        por_org.setdefault(f["organizacion_id"], []).append(
            {"nombre": f["nombre"], "monto_minimo": float(f["monto_minimo"]), "moneda": f["moneda"],
             "sociedad": f["sociedad"], "rol_id": f["rol_id"]})
    for org, conf in con.execute(sa.text("SELECT id, configuracion FROM organizaciones")).all():
        if org in por_org:
            conf = json.loads(conf) if isinstance(conf, str) else dict(conf or {})
            conf["aprobaciones_oc"] = por_org[org]
            con.execute(sa.text("UPDATE organizaciones SET configuracion = :c WHERE id = :i"),
                        {"c": json.dumps(conf, ensure_ascii=False), "i": org})
    with op.batch_alter_table('reglas_aprobacion_oc', schema=None) as b:
        b.drop_index(b.f('ix_reglas_aprobacion_oc_rol_id'))
        b.drop_index(b.f('ix_reglas_aprobacion_oc_organizacion_id'))
    op.drop_table('reglas_aprobacion_oc')
    # Listas tipadas de vuelta a valores_lista
    with op.batch_alter_table("valores_lista", schema=None) as b:
        for col, tipo in COLUMNAS_LISTA:
            b.add_column(sa.Column(col, tipo, nullable=True))
    for lista, (tabla, columnas, _) in TIPADAS.items():
        cols = ["organizacion_id", "codigo", "nombre", "orden", "activo", *columnas]
        for f in con.execute(sa.text(f"SELECT {', '.join(cols)} FROM {tabla}")).mappings().all():
            datos = {**dict(f), "lista": lista}
            con.execute(sa.text(f"INSERT INTO valores_lista ({', '.join(datos)}) VALUES ({', '.join(':' + c for c in datos)})"),
                        datos)
        with op.batch_alter_table(tabla, schema=None) as b:
            b.drop_index(b.f(f'ix_{tabla}_organizacion_id'))
        op.drop_table(tabla)
