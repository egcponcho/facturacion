"""Importes exactos, numeración segura y restricciones CHECK

- Precios, tasas y umbrales pasan de FLOAT a NUMERIC: posiciones_oc.precio,
  factura_lineas.precio_unitario y precio_oc (18,6); reglas_impuesto.tasa
  (12,6) y sus umbrales (18,4). Los cálculos se hacen en Decimal
  (core/dinero.py).
- series_documentales y contadores_serie: numeración con el contador
  bloqueado. Los embarques usan la serie EMB; su contador arranca después
  del mayor código EMB-#### que ya existe en cada organización.
- packing_lists: número único dentro de su factura. Si una factura tenía dos
  PL con el mismo número (se numeraba contando), el repetido recibe el
  siguiente libre.
- Restricciones CHECK (modelos/restricciones.py): cantidades, precios y
  medidas no negativos, vigencias no invertidas y estados dentro de la
  máquina de estados de cada documento. Si algún dato no las cumple, la
  migración se detiene y dice qué filas corregir.

Revision ID: 0052
Revises: 0051
Create Date: 2026-10-13 00:00:00
"""
import re

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls, sin_violaciones


revision = '0052'
down_revision = '0051'
branch_labels = None
depends_on = None

# tabla → [(columna, tipo nuevo)]
NUMERICOS = {
    "posiciones_oc": [("precio", sa.Numeric(18, 6), True)],
    "factura_lineas": [("precio_unitario", sa.Numeric(18, 6), False), ("precio_oc", sa.Numeric(18, 6), False)],
    "reglas_impuesto": [("tasa", sa.Numeric(12, 6), True), ("umbral_desde", sa.Numeric(18, 4), True),
                        ("umbral_hasta", sa.Numeric(18, 4), True)],
}

ESTADOS = {
    "ordenes_compra": ("BORRADOR", "EN_APROBACION", "RECHAZADA", "APROBADA", "CERRADA", "CANCELADA"),
    "facturas": ("BORRADOR", "EN_CORRECCION", "FINALIZADA", "CANCELADA"),
    "packing_lists": ("BORRADOR", "EN_CORRECCION", "FINALIZADO", "CANCELADO"),
    "embarques": ("PLANIFICADO", "EN_TRANSITO", "ARRIBADO", "ENTREGADO", "RECIBIDO", "CANCELADO"),
}


def _en(columna, valores):
    return f"{columna} IN ({', '.join(repr(v) for v in valores)})"


def _no_negativo(*columnas):
    return [(c, f"{c} IS NULL OR {c} >= 0") for c in columnas]


VIGENCIA = ("vigencia", "vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde")
# Copia de modelos/restricciones.py al momento de esta migración
RESTRICCIONES = {
    "ordenes_compra": [("estado", _en("estado", ESTADOS["ordenes_compra"]))],
    "posiciones_oc": _no_negativo("cantidad", "precio", "casepack", "inner_pack", "unidades_por_caja"),
    "aprobaciones_oc": [("estado", _en("estado", ("PENDIENTE", "APROBADA", "RECHAZADA"))), ("paso", "paso >= 0")],
    "facturas": [("estado", _en("estado", ESTADOS["facturas"]))],
    "factura_lineas": _no_negativo("cantidad", "precio_unitario", "precio_oc", "casepack", "inner_pack",
                                   "unidades_por_caja"),
    "packing_lists": [("estado", _en("estado", ESTADOS["packing_lists"]))],
    "pl_lineas": _no_negativo("cantidad"),
    "grupos_cajas": _no_negativo("num_cajas", "largo", "ancho", "alto", "peso_neto_caja", "peso_bruto_caja", "tara",
                                 "neto_manual"),
    "grupo_cajas_items": _no_negativo("cantidad_por_caja"),
    "plantillas_caja": _no_negativo("cantidad_por_caja", "largo", "ancho", "alto", "tara"),
    "tipos_empaque": _no_negativo("largo", "ancho", "alto", "tara", "peso_max", "max_unidades", "max_contenido"),
    "recepciones": _no_negativo("cantidad_recibida", "cantidad_danada"),
    "embarques": [("estado", _en("estado", ESTADOS["embarques"]))],
    "reglas_impuesto": _no_negativo("tasa") + [
        VIGENCIA, ("umbral_desde_umbral_hasta", "umbral_hasta IS NULL OR umbral_desde IS NULL OR umbral_hasta >= umbral_desde")],
    "incisos_nacionales": [VIGENCIA],
    "nodos_arancel": [VIGENCIA],
    "notas_sac": [VIGENCIA],
    "overrides_arancel": [VIGENCIA],
    "regulaciones": [VIGENCIA],
    "versiones_dataset": [VIGENCIA],
    "producto_versiones": [("desde_hasta", "hasta IS NULL OR desde IS NULL OR hasta >= desde")],
}


def _tipos(postgres: bool) -> None:
    for tabla, columnas in NUMERICOS.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, tipo, nulo in columnas:
                kw = {"postgresql_using": f"round({col}::numeric, {tipo.scale})"} if postgres else {}
                b.alter_column(col, existing_type=sa.Float(), type_=tipo, existing_nullable=nulo, **kw)
        if not postgres:  # SQLite guarda lo que recibe: deja los valores ya redondeados a la escala
            for col, tipo, _ in columnas:
                op.execute(f"UPDATE {tabla} SET {col} = round({col}, {tipo.scale}) WHERE {col} IS NOT NULL")


def _series(con) -> None:
    op.create_table('series_documentales',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('objeto', sa.String(length=30), nullable=False),
    sa.Column('sociedad_id', sa.Integer(), nullable=True),
    sa.Column('prefijo', sa.String(length=20), nullable=False),
    sa.Column('digitos', sa.Integer(), nullable=False),
    sa.Column('reinicio', sa.String(length=10), nullable=False),
    sa.Column('predeterminada', sa.Boolean(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=True),
    sa.Column('vigente_hasta', sa.Date(), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("reinicio IN ('NUNCA', 'ANUAL')", name='ck_series_documentales_reinicio'),
    sa.CheckConstraint('digitos BETWEEN 1 AND 12', name='ck_series_documentales_digitos'),
    sa.CheckConstraint('vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde', name='ck_series_documentales_vigencia'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_series_documentales_org_codigo')
    )
    with op.batch_alter_table('series_documentales', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_series_documentales_objeto'), ['objeto'], unique=False)
        batch_op.create_index(batch_op.f('ix_series_documentales_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_series_documentales_sociedad_id'), ['sociedad_id'], unique=False)

    op.create_table('contadores_serie',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('serie_id', sa.Integer(), nullable=False),
    sa.Column('periodo', sa.String(length=10), nullable=False),
    sa.Column('siguiente', sa.Integer(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('siguiente >= 1', name='ck_contadores_serie_siguiente'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['serie_id'], ['series_documentales.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('serie_id', 'periodo', name='uq_contadores_serie_serie_periodo')
    )
    with op.batch_alter_table('contadores_serie', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_contadores_serie_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_contadores_serie_serie_id'), ['serie_id'], unique=False)
    rls(op, "series_documentales", "contadores_serie")

    # Serie de embarques de cada organización que ya tiene embarques
    mayor: dict[int, int] = {}
    for org, codigo in con.execute(sa.text("SELECT organizacion_id, codigo FROM embarques")):
        m = re.fullmatch(r"EMB-(\d+)", codigo or "")
        mayor[org] = max(mayor.get(org, 0), int(m.group(1)) if m else 0)
    for org, n in mayor.items():
        con.execute(sa.text(
            "INSERT INTO series_documentales (codigo, nombre, objeto, prefijo, digitos, reinicio, predeterminada, activo, "
            "organizacion_id) VALUES ('EMB', 'Shipments', 'embarque', 'EMB-', 4, 'NUNCA', :si, :si, :org)"),
            {"si": True, "org": org})
        serie = con.execute(sa.text("SELECT id FROM series_documentales WHERE organizacion_id = :org AND codigo = 'EMB'"),
                            {"org": org}).scalar()
        con.execute(sa.text("INSERT INTO contadores_serie (serie_id, periodo, siguiente, organizacion_id) "
                            "VALUES (:s, '', :n, :org)"), {"s": serie, "n": n + 1, "org": org})


def _numeros_pl(con) -> None:
    """Un PL repetido dentro de su factura toma el siguiente número libre."""
    usados: dict[int, set] = {}
    for pid, fid, numero in con.execute(sa.text("SELECT id, factura_id, numero FROM packing_lists ORDER BY id")).all():
        nums = usados.setdefault(fid, set())
        if numero not in nums:
            nums.add(numero)
            continue
        n = 1
        while f"PL-{n:03d}" in nums:
            n += 1
        nums.add(f"PL-{n:03d}")
        con.execute(sa.text("UPDATE packing_lists SET numero = :n WHERE id = :i"), {"n": f"PL-{n:03d}", "i": pid})
    with op.batch_alter_table('packing_lists', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_packing_lists_factura_numero', ['factura_id', 'numero'])


def _restricciones(con) -> None:
    for tabla, lista in RESTRICCIONES.items():
        for sufijo, condicion in lista:
            sin_violaciones(con, tabla, condicion, sufijo)
        with op.batch_alter_table(tabla, schema=None) as b:
            for sufijo, condicion in lista:
                b.create_check_constraint(f"ck_{tabla}_{sufijo}", condicion)


def upgrade() -> None:
    con = op.get_bind()
    _tipos(con.dialect.name == "postgresql")
    _series(con)
    _numeros_pl(con)
    _restricciones(con)


def downgrade() -> None:
    for tabla, lista in RESTRICCIONES.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for sufijo, _ in lista:
                b.drop_constraint(f"ck_{tabla}_{sufijo}", type_="check")
    with op.batch_alter_table('packing_lists', schema=None) as batch_op:
        batch_op.drop_constraint('uq_packing_lists_factura_numero', type_='unique')
    with op.batch_alter_table('contadores_serie', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_contadores_serie_serie_id'))
        batch_op.drop_index(batch_op.f('ix_contadores_serie_organizacion_id'))
    op.drop_table('contadores_serie')
    with op.batch_alter_table('series_documentales', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_series_documentales_sociedad_id'))
        batch_op.drop_index(batch_op.f('ix_series_documentales_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_series_documentales_objeto'))
    op.drop_table('series_documentales')
    for tabla, columnas in NUMERICOS.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, tipo, nulo in columnas:
                b.alter_column(col, existing_type=tipo, type_=sa.Float(), existing_nullable=nulo)
