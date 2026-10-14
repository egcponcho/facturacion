"""Quitar la facturación comercial aparte (documentos emitidos y recibidos,
pagos, aplicaciones, impuestos, cuotas, métodos de pago, tipos de cambio,
configuración fiscal, plantillas y facturación recurrente).

La facturación es la del proveedor contra la OC (facturas, listas de empaque).
Se conservan los terceros (identidad de proveedores y transportistas), sus
direcciones y medios de contacto, y las condiciones de pago de las OC.

Datos: se borran las series de numeración de documentos comerciales, los
permisos comercial.* de los roles y los estados personalizados de documentos,
cobros y pagos. El downgrade recrea las tablas vacías (no restaura datos).

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-14 12:00:00
"""
from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls

revision = '0069'
down_revision = '0068'
branch_labels = None
depends_on = None

TABLAS = ["aplicaciones", "documento_envios", "documento_vencimientos", "linea_impuestos", "documento_relaciones",
          "facturacion_recurrente", "documento_lineas", "pagos", "documentos", "plantillas_documento", "tipos_documento",
          "configuracion_fiscal", "tipos_cambio", "metodos_pago", "impuestos", "condicion_pago_cuotas"]
PERMISOS = {"comercial.ver", "comercial.editar", "comercial.emitir", "comercial.pagos"}


def _datos(con) -> None:
    import json

    series = "SELECT id FROM series_documentales WHERE objeto <> 'embarque'"
    con.execute(sa.text(f"DELETE FROM contadores_serie WHERE serie_id IN ({series})"))
    con.execute(sa.text(f"DELETE FROM series_documentales WHERE id IN ({series})"))
    con.execute(sa.text("DELETE FROM estados_documento WHERE documento IN ('documento', 'cobro', 'pago')"))
    for rid, permisos in con.execute(sa.text("SELECT id, permisos FROM roles")).all():
        lista = json.loads(permisos) if isinstance(permisos, str) else (permisos or [])
        limpia = [p for p in lista if p not in PERMISOS]
        if limpia != lista:
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(limpia), "i": rid})


def upgrade() -> None:
    _datos(op.get_bind())
    with op.batch_alter_table('series_documentales', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_series_documentales_tipo_documento_id'))
        batch_op.drop_constraint('fk_series_documentales_tipo_documento_id', type_='foreignkey')
        batch_op.drop_column('tipo_documento_id')
    for tabla in TABLAS:  # primero las hijas
        op.drop_table(tabla)


def downgrade() -> None:
    op.create_table('condicion_pago_cuotas',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('condicion_id', sa.INTEGER(), nullable=False),
    sa.Column('numero', sa.INTEGER(), nullable=False),
    sa.Column('porcentaje', sa.NUMERIC(precision=12, scale=6), nullable=False),
    sa.Column('dias', sa.INTEGER(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint('dias >= 0', name=op.f('ck_condicion_pago_cuotas_dias')),
    sa.CheckConstraint('porcentaje > 0 AND porcentaje <= 100', name=op.f('ck_condicion_pago_cuotas_porcentaje')),
    sa.ForeignKeyConstraint(['condicion_id'], ['condiciones_pago.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('condicion_id', 'numero', name=op.f('uq_condicion_pago_cuotas_numero'))
    )
    with op.batch_alter_table('condicion_pago_cuotas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_condicion_pago_cuotas_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_condicion_pago_cuotas_condicion_id'), ['condicion_id'], unique=False)

    op.create_table('impuestos',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('codigo', sa.VARCHAR(length=20), nullable=False),
    sa.Column('nombre', sa.VARCHAR(length=120), nullable=False),
    sa.Column('tipo', sa.VARCHAR(length=12), nullable=False),
    sa.Column('tasa', sa.NUMERIC(precision=12, scale=6), nullable=False),
    sa.Column('pais', sa.VARCHAR(length=2), nullable=True),
    sa.Column('es_retencion', sa.BOOLEAN(), nullable=False),
    sa.Column('vigente_desde', sa.DATE(), nullable=True),
    sa.Column('vigente_hasta', sa.DATE(), nullable=True),
    sa.Column('activo', sa.BOOLEAN(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint("tipo IN ('PORCENTAJE', 'FIJO')", name=op.f('ck_impuestos_tipo')),
    sa.CheckConstraint('tasa >= 0', name=op.f('ck_impuestos_tasa')),
    sa.CheckConstraint('vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde', name=op.f('ck_impuestos_vigencia')),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pais'], ['paises.codigo'], name=op.f('fk_impuestos_pais')),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', 'vigente_desde', name=op.f('uq_impuestos_org_codigo_desde'))
    )
    with op.batch_alter_table('impuestos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_impuestos_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('metodos_pago',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('codigo', sa.VARCHAR(length=20), nullable=False),
    sa.Column('nombre', sa.VARCHAR(length=120), nullable=False),
    sa.Column('orden', sa.INTEGER(), nullable=False),
    sa.Column('activo', sa.BOOLEAN(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name=op.f('uq_metodos_pago_org_codigo'))
    )
    with op.batch_alter_table('metodos_pago', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_metodos_pago_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('tipos_cambio',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('moneda_origen', sa.VARCHAR(length=3), nullable=False),
    sa.Column('moneda_destino', sa.VARCHAR(length=3), nullable=False),
    sa.Column('fecha', sa.DATE(), nullable=False),
    sa.Column('tasa', sa.NUMERIC(precision=18, scale=8), nullable=False),
    sa.Column('fuente', sa.VARCHAR(length=80), nullable=True),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint('moneda_origen <> moneda_destino', name=op.f('ck_tipos_cambio_monedas')),
    sa.CheckConstraint('tasa > 0', name=op.f('ck_tipos_cambio_tasa')),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda_destino'], ['monedas.organizacion_id', 'monedas.codigo'], name=op.f('fk_tipos_cambio_moneda_destino')),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda_origen'], ['monedas.organizacion_id', 'monedas.codigo'], name=op.f('fk_tipos_cambio_moneda_origen')),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'moneda_origen', 'moneda_destino', 'fecha', name=op.f('uq_tipos_cambio_dia'))
    )
    with op.batch_alter_table('tipos_cambio', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tipos_cambio_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tipos_cambio_fecha'), ['fecha'], unique=False)

    op.create_table('configuracion_fiscal',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('sociedad_id', sa.INTEGER(), nullable=False),
    sa.Column('pais', sa.VARCHAR(length=2), nullable=True),
    sa.Column('regimen', sa.VARCHAR(length=80), nullable=True),
    sa.Column('redondeo', sa.VARCHAR(length=10), nullable=False),
    sa.Column('sin_huecos', sa.BOOLEAN(), nullable=False),
    sa.Column('impuestos_defecto', sa.VARCHAR(length=200), nullable=True),
    sa.Column('proveedor_electronico', sa.VARCHAR(length=60), nullable=True),
    sa.Column('datos', sa.JSON(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint("redondeo IN ('LINEA', 'DOCUMENTO')", name=op.f('ck_configuracion_fiscal_redondeo')),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pais'], ['paises.codigo'], name=op.f('fk_configuracion_fiscal_pais')),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sociedad_id', name=op.f('uq_configuracion_fiscal_sociedad'))
    )
    with op.batch_alter_table('configuracion_fiscal', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_configuracion_fiscal_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('tipos_documento',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('codigo', sa.VARCHAR(length=20), nullable=False),
    sa.Column('nombre', sa.VARCHAR(length=120), nullable=False),
    sa.Column('clase', sa.VARCHAR(length=15), nullable=False),
    sa.Column('direccion', sa.VARCHAR(length=10), nullable=False),
    sa.Column('signo', sa.INTEGER(), nullable=False),
    sa.Column('afecta_saldo', sa.BOOLEAN(), nullable=False),
    sa.Column('requiere_origen', sa.BOOLEAN(), nullable=False),
    sa.Column('orden', sa.INTEGER(), nullable=False),
    sa.Column('activo', sa.BOOLEAN(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint("clase IN ('FACTURA', 'NOTA_CREDITO', 'NOTA_DEBITO', 'PROFORMA')", name=op.f('ck_tipos_documento_clase')),
    sa.CheckConstraint("direccion IN ('EMITIDO', 'RECIBIDO')", name=op.f('ck_tipos_documento_direccion')),
    sa.CheckConstraint('signo IN (1, -1)', name=op.f('ck_tipos_documento_signo')),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name=op.f('uq_tipos_documento_org_codigo'))
    )
    with op.batch_alter_table('tipos_documento', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tipos_documento_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('plantillas_documento',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('tipo_documento_id', sa.INTEGER(), nullable=False),
    sa.Column('idioma', sa.VARCHAR(length=5), nullable=False),
    sa.Column('titulo', sa.VARCHAR(length=120), nullable=True),
    sa.Column('encabezado', sa.TEXT(), nullable=True),
    sa.Column('pie', sa.TEXT(), nullable=True),
    sa.Column('activo', sa.BOOLEAN(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['tipo_documento_id'], ['tipos_documento.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tipo_documento_id', 'idioma', name=op.f('uq_plantillas_documento_tipo_idioma'))
    )
    with op.batch_alter_table('plantillas_documento', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plantillas_documento_tipo_documento_id'), ['tipo_documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_plantillas_documento_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('documentos',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('extra', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('tipo_documento_id', sa.INTEGER(), nullable=False),
    sa.Column('serie_id', sa.INTEGER(), nullable=True),
    sa.Column('numero', sa.VARCHAR(length=40), nullable=True),
    sa.Column('referencia_externa', sa.VARCHAR(length=60), nullable=True),
    sa.Column('estado', sa.VARCHAR(length=10), nullable=False),
    sa.Column('sociedad_id', sa.INTEGER(), nullable=False),
    sa.Column('tercero_id', sa.INTEGER(), nullable=False),
    sa.Column('fecha', sa.DATE(), nullable=True),
    sa.Column('fecha_vencimiento', sa.DATE(), nullable=True),
    sa.Column('moneda', sa.VARCHAR(length=3), nullable=False),
    sa.Column('tipo_cambio', sa.NUMERIC(precision=18, scale=8), nullable=False),
    sa.Column('condicion_pago', sa.VARCHAR(length=20), nullable=True),
    sa.Column('notas', sa.TEXT(), nullable=True),
    sa.Column('subtotal', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('descuentos', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('impuestos', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('retenciones', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('total', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('copia', sa.JSON(), nullable=False),
    sa.Column('factura_id', sa.INTEGER(), nullable=True),
    sa.Column('version', sa.INTEGER(), nullable=False),
    sa.Column('creado_por', sa.INTEGER(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('emitido_en', sa.DateTime(), nullable=True),
    sa.Column('anulado_en', sa.DateTime(), nullable=True),
    sa.Column('motivo_anulacion', sa.VARCHAR(length=500), nullable=True),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint("estado = 'BORRADOR' OR (fecha IS NOT NULL AND (numero IS NOT NULL OR referencia_externa IS NOT NULL))", name=op.f('ck_documentos_emitido_numerado')),
    sa.CheckConstraint("estado IN ('BORRADOR', 'EMITIDO', 'ANULADO')", name=op.f('ck_documentos_estado')),
    sa.CheckConstraint('fecha_vencimiento IS NULL OR fecha IS NULL OR fecha_vencimiento >= fecha', name=op.f('ck_documentos_vencimiento')),
    sa.CheckConstraint('tipo_cambio > 0', name=op.f('ck_documentos_tipo_cambio')),
    sa.CheckConstraint('total >= 0 AND subtotal >= 0 AND impuestos >= 0 AND retenciones >= 0 AND descuentos >= 0', name=op.f('ck_documentos_importes')),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['factura_id'], ['facturas.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id', 'condicion_pago'], ['condiciones_pago.organizacion_id', 'condiciones_pago.codigo'], name=op.f('fk_documentos_condicion_pago')),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda'], ['monedas.organizacion_id', 'monedas.codigo'], name=op.f('fk_documentos_moneda')),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['serie_id'], ['series_documentales.id'], ),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ),
    sa.ForeignKeyConstraint(['tercero_id', 'organizacion_id'], ['terceros.id', 'terceros.organizacion_id'], name=op.f('fk_documentos_tercero_id_org')),
    sa.ForeignKeyConstraint(['tercero_id'], ['terceros.id'], ),
    sa.ForeignKeyConstraint(['tipo_documento_id'], ['tipos_documento.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('factura_id', name=op.f('uq_documentos_factura')),
    sa.UniqueConstraint('id', 'organizacion_id', name=op.f('uq_documentos_id_org')),
    sa.UniqueConstraint('serie_id', 'numero', name=op.f('uq_documentos_serie_numero'))
    )
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ux_documentos_recibido'), ['organizacion_id', 'tercero_id', 'tipo_documento_id', 'referencia_externa'], unique=True, sqlite_where=sa.text("referencia_externa IS NOT NULL AND estado <> 'ANULADO'"), postgresql_where=sa.text("referencia_externa IS NOT NULL AND estado <> 'ANULADO'"))
        batch_op.create_index(batch_op.f('ix_documentos_tipo_documento_id'), ['tipo_documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_tercero_id'), ['tercero_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_sociedad_id'), ['sociedad_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_serie_id'), ['serie_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_fecha_vencimiento'), ['fecha_vencimiento'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_estado'), ['estado'], unique=False)

    op.create_table('documento_relaciones',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('origen_id', sa.INTEGER(), nullable=False),
    sa.Column('destino_id', sa.INTEGER(), nullable=False),
    sa.Column('tipo', sa.VARCHAR(length=15), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint("tipo IN ('RECTIFICA', 'ANULA', 'SUSTITUYE', 'GENERADO_DESDE')", name=op.f('ck_documento_relaciones_tipo')),
    sa.CheckConstraint('origen_id <> destino_id', name=op.f('ck_documento_relaciones_distintos')),
    sa.ForeignKeyConstraint(['destino_id', 'organizacion_id'], ['documentos.id', 'documentos.organizacion_id'], name=op.f('fk_documento_relaciones_destino_id_org')),
    sa.ForeignKeyConstraint(['destino_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['origen_id', 'organizacion_id'], ['documentos.id', 'documentos.organizacion_id'], name=op.f('fk_documento_relaciones_origen_id_org')),
    sa.ForeignKeyConstraint(['origen_id'], ['documentos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('origen_id', 'destino_id', 'tipo', name=op.f('uq_documento_relaciones'))
    )
    with op.batch_alter_table('documento_relaciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documento_relaciones_origen_id'), ['origen_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_relaciones_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_relaciones_destino_id'), ['destino_id'], unique=False)

    op.create_table('documento_lineas',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('documento_id', sa.INTEGER(), nullable=False),
    sa.Column('orden', sa.INTEGER(), nullable=False),
    sa.Column('articulo_id', sa.INTEGER(), nullable=True),
    sa.Column('posicion_oc_id', sa.INTEGER(), nullable=True),
    sa.Column('factura_linea_id', sa.INTEGER(), nullable=True),
    sa.Column('codigo', sa.VARCHAR(length=40), nullable=True),
    sa.Column('descripcion', sa.VARCHAR(length=300), nullable=False),
    sa.Column('cantidad', sa.NUMERIC(precision=14, scale=3), nullable=False),
    sa.Column('unidad', sa.VARCHAR(length=10), nullable=True),
    sa.Column('precio_unitario', sa.NUMERIC(precision=18, scale=6), nullable=False),
    sa.Column('descuento_pct', sa.NUMERIC(precision=12, scale=6), nullable=False),
    sa.Column('descuento', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('subtotal', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('impuestos', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('retenciones', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('total', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('impuestos_codigos', sa.VARCHAR(length=200), nullable=True),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint('cantidad > 0', name=op.f('ck_documento_lineas_cantidad')),
    sa.CheckConstraint('descuento_pct >= 0 AND descuento_pct <= 100', name=op.f('ck_documento_lineas_descuento')),
    sa.CheckConstraint('precio_unitario >= 0', name=op.f('ck_documento_lineas_precio')),
    sa.CheckConstraint('subtotal >= 0 AND impuestos >= 0 AND total >= 0', name=op.f('ck_documento_lineas_importes')),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], ),
    sa.ForeignKeyConstraint(['documento_id', 'organizacion_id'], ['documentos.id', 'documentos.organizacion_id'], name=op.f('fk_documento_lineas_documento_id_org')),
    sa.ForeignKeyConstraint(['documento_id'], ['documentos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['factura_linea_id'], ['factura_lineas.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id', 'unidad'], ['unidades_medida.organizacion_id', 'unidades_medida.codigo'], name=op.f('fk_documento_lineas_unidad')),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['posicion_oc_id'], ['posiciones_oc.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name=op.f('uq_documento_lineas_id_org'))
    )
    with op.batch_alter_table('documento_lineas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documento_lineas_posicion_oc_id'), ['posicion_oc_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_lineas_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_lineas_factura_linea_id'), ['factura_linea_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_lineas_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_lineas_articulo_id'), ['articulo_id'], unique=False)

    op.create_table('linea_impuestos',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('linea_id', sa.INTEGER(), nullable=False),
    sa.Column('impuesto_id', sa.INTEGER(), nullable=True),
    sa.Column('codigo', sa.VARCHAR(length=20), nullable=False),
    sa.Column('nombre', sa.VARCHAR(length=120), nullable=False),
    sa.Column('tipo', sa.VARCHAR(length=12), nullable=False),
    sa.Column('tasa', sa.NUMERIC(precision=12, scale=6), nullable=False),
    sa.Column('base', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('importe', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('es_retencion', sa.BOOLEAN(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint('base >= 0 AND importe >= 0 AND tasa >= 0', name=op.f('ck_linea_impuestos_importes')),
    sa.ForeignKeyConstraint(['impuesto_id'], ['impuestos.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['linea_id', 'organizacion_id'], ['documento_lineas.id', 'documento_lineas.organizacion_id'], name=op.f('fk_linea_impuestos_linea_id_org')),
    sa.ForeignKeyConstraint(['linea_id'], ['documento_lineas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('linea_id', 'codigo', name=op.f('uq_linea_impuestos_linea_codigo'))
    )
    with op.batch_alter_table('linea_impuestos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_linea_impuestos_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_linea_impuestos_linea_id'), ['linea_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_linea_impuestos_impuesto_id'), ['impuesto_id'], unique=False)

    op.create_table('documento_vencimientos',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('documento_id', sa.INTEGER(), nullable=False),
    sa.Column('numero', sa.INTEGER(), nullable=False),
    sa.Column('fecha', sa.DATE(), nullable=False),
    sa.Column('importe', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint('importe >= 0', name=op.f('ck_documento_vencimientos_importe')),
    sa.ForeignKeyConstraint(['documento_id', 'organizacion_id'], ['documentos.id', 'documentos.organizacion_id'], name=op.f('fk_documento_vencimientos_documento_id_org')),
    sa.ForeignKeyConstraint(['documento_id'], ['documentos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('documento_id', 'numero', name=op.f('uq_documento_vencimientos_numero'))
    )
    with op.batch_alter_table('documento_vencimientos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documento_vencimientos_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_vencimientos_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_vencimientos_documento_id'), ['documento_id'], unique=False)

    op.create_table('documento_envios',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('documento_id', sa.INTEGER(), nullable=False),
    sa.Column('sistema', sa.VARCHAR(length=40), nullable=False),
    sa.Column('estado', sa.VARCHAR(length=10), nullable=False),
    sa.Column('identificador_externo', sa.VARCHAR(length=120), nullable=True),
    sa.Column('acuse', sa.JSON(), nullable=False),
    sa.Column('error', sa.VARCHAR(length=500), nullable=True),
    sa.Column('intentos', sa.INTEGER(), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint("estado IN ('PENDIENTE', 'ENVIADO', 'ACEPTADO', 'RECHAZADO', 'ERROR')", name=op.f('ck_documento_envios_estado')),
    sa.CheckConstraint('intentos >= 0', name=op.f('ck_documento_envios_intentos')),
    sa.ForeignKeyConstraint(['documento_id'], ['documentos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('documento_id', 'sistema', name=op.f('uq_documento_envios_sistema'))
    )
    with op.batch_alter_table('documento_envios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documento_envios_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_envios_documento_id'), ['documento_id'], unique=False)

    op.create_table('facturacion_recurrente',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('nombre', sa.VARCHAR(length=120), nullable=False),
    sa.Column('modelo_id', sa.INTEGER(), nullable=False),
    sa.Column('frecuencia', sa.VARCHAR(length=12), nullable=False),
    sa.Column('proxima', sa.DATE(), nullable=False),
    sa.Column('dia', sa.INTEGER(), nullable=False),
    sa.Column('hasta', sa.DATE(), nullable=True),
    sa.Column('emitir', sa.BOOLEAN(), nullable=False),
    sa.Column('activo', sa.BOOLEAN(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint("frecuencia IN ('SEMANAL', 'MENSUAL', 'TRIMESTRAL', 'ANUAL')", name=op.f('ck_facturacion_recurrente_frecuencia')),
    sa.CheckConstraint('NOT activo OR hasta IS NULL OR hasta >= proxima', name=op.f('ck_facturacion_recurrente_vigencia')),
    sa.ForeignKeyConstraint(['modelo_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('facturacion_recurrente', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_facturacion_recurrente_proxima'), ['proxima'], unique=False)
        batch_op.create_index(batch_op.f('ix_facturacion_recurrente_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_facturacion_recurrente_modelo_id'), ['modelo_id'], unique=False)

    op.create_table('pagos',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('direccion', sa.VARCHAR(length=5), nullable=False),
    sa.Column('estado', sa.VARCHAR(length=10), nullable=False),
    sa.Column('tercero_id', sa.INTEGER(), nullable=False),
    sa.Column('sociedad_id', sa.INTEGER(), nullable=False),
    sa.Column('fecha', sa.DATE(), nullable=False),
    sa.Column('moneda', sa.VARCHAR(length=3), nullable=False),
    sa.Column('tipo_cambio', sa.NUMERIC(precision=18, scale=8), nullable=False),
    sa.Column('importe', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('metodo_pago_id', sa.INTEGER(), nullable=True),
    sa.Column('referencia', sa.VARCHAR(length=80), nullable=True),
    sa.Column('notas', sa.VARCHAR(length=500), nullable=True),
    sa.Column('creado_por', sa.INTEGER(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('anulado_en', sa.DateTime(), nullable=True),
    sa.Column('motivo_anulacion', sa.VARCHAR(length=500), nullable=True),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.CheckConstraint("direccion IN ('COBRO', 'PAGO')", name=op.f('ck_pagos_direccion')),
    sa.CheckConstraint("estado IN ('REGISTRADO', 'ANULADO')", name=op.f('ck_pagos_estado')),
    sa.CheckConstraint('importe > 0', name=op.f('ck_pagos_importe')),
    sa.CheckConstraint('tipo_cambio > 0', name=op.f('ck_pagos_tipo_cambio')),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['metodo_pago_id'], ['metodos_pago.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda'], ['monedas.organizacion_id', 'monedas.codigo'], name=op.f('fk_pagos_moneda')),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ),
    sa.ForeignKeyConstraint(['tercero_id', 'organizacion_id'], ['terceros.id', 'terceros.organizacion_id'], name=op.f('fk_pagos_tercero_id_org')),
    sa.ForeignKeyConstraint(['tercero_id'], ['terceros.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name=op.f('uq_pagos_id_org'))
    )
    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pagos_tercero_id'), ['tercero_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_sociedad_id'), ['sociedad_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_metodo_pago_id'), ['metodo_pago_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_estado'), ['estado'], unique=False)

    op.create_table('aplicaciones',
    sa.Column('id', sa.INTEGER(), nullable=False),
    sa.Column('pago_id', sa.INTEGER(), nullable=True),
    sa.Column('credito_id', sa.INTEGER(), nullable=True),
    sa.Column('documento_id', sa.INTEGER(), nullable=False),
    sa.Column('vencimiento_id', sa.INTEGER(), nullable=True),
    sa.Column('importe', sa.NUMERIC(precision=18, scale=4), nullable=False),
    sa.Column('activa', sa.BOOLEAN(), nullable=False),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.INTEGER(), nullable=False),
    sa.Column('fecha', sa.DATE(), nullable=True),
    sa.CheckConstraint('(CASE WHEN pago_id IS NULL THEN 0 ELSE 1 END + CASE WHEN credito_id IS NULL THEN 0 ELSE 1 END) = 1', name=op.f('ck_aplicaciones_origen')),
    sa.CheckConstraint('credito_id IS NULL OR credito_id <> documento_id', name=op.f('ck_aplicaciones_distintos')),
    sa.CheckConstraint('importe > 0', name=op.f('ck_aplicaciones_importe')),
    sa.ForeignKeyConstraint(['credito_id', 'organizacion_id'], ['documentos.id', 'documentos.organizacion_id'], name=op.f('fk_aplicaciones_credito_id_org')),
    sa.ForeignKeyConstraint(['credito_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['documento_id', 'organizacion_id'], ['documentos.id', 'documentos.organizacion_id'], name=op.f('fk_aplicaciones_documento_id_org')),
    sa.ForeignKeyConstraint(['documento_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pago_id', 'organizacion_id'], ['pagos.id', 'pagos.organizacion_id'], name=op.f('fk_aplicaciones_pago_id_org')),
    sa.ForeignKeyConstraint(['pago_id'], ['pagos.id'], ),
    sa.ForeignKeyConstraint(['vencimiento_id'], ['documento_vencimientos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('aplicaciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_aplicaciones_vencimiento_id'), ['vencimiento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_pago_id'), ['pago_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_credito_id'), ['credito_id'], unique=False)

    with op.batch_alter_table('series_documentales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tipo_documento_id', sa.INTEGER(), nullable=True))
        batch_op.create_foreign_key('fk_series_documentales_tipo_documento_id', 'tipos_documento', ['tipo_documento_id'], ['id'])
        batch_op.create_index(batch_op.f('ix_series_documentales_tipo_documento_id'), ['tipo_documento_id'], unique=False)
    rls(op, *TABLAS)  # las llaves de coherencia (_org) van en cada create_table
