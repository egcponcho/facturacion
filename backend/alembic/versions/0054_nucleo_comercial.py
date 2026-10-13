"""Núcleo comercial genérico: terceros, documentos, impuestos, pagos

- terceros (con roles, direcciones y medios de contacto): una identidad
  fiscal por persona o empresa; proveedores y transportistas quedan ligados
  a su tercero (tercero_id) y se crea uno por cada uno existente.
- tipos_documento, impuestos (con jurisdicción y vigencia), cuotas de las
  condiciones de pago, métodos de pago, tipos de cambio, configuración fiscal
  por sociedad y plantillas de impresión.
- documentos (facturas emitidas y recibidas, notas de crédito y débito,
  proformas) con líneas, impuestos aplicados, vencimientos, relaciones entre
  documentos, envíos a sistemas externos y facturación recurrente.
- pagos (cobros y pagos) y aplicaciones (de un pago o de una nota de crédito a
  un documento, parciales o a varios documentos).
- Las facturas de proveedor ya finalizadas quedan registradas como
  documentos recibidos (cuentas por pagar) con su total.
- Los roles de fábrica de administración y equipo interno reciben los
  permisos del módulo.

Revision ID: 0054
Revises: 0053
Create Date: 2026-10-13 00:00:00
"""
import json
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0054'
down_revision = '0053'
branch_labels = None
depends_on = None

NUEVAS = ["terceros", "tercero_roles", "direcciones", "medios_contacto", "tipos_documento", "impuestos",
          "condicion_pago_cuotas", "metodos_pago", "tipos_cambio", "configuracion_fiscal", "plantillas_documento",
          "documentos", "documento_lineas", "linea_impuestos", "documento_vencimientos", "documento_relaciones",
          "documento_envios", "facturacion_recurrente", "pagos", "aplicaciones"]
# Coherencia de organización (copia de app/modelos/referencias.py: lo que agrega esta migración)
COHERENCIA = {
    "tercero_roles": [("tercero_id", "terceros")],
    "documentos": [("tercero_id", "terceros")],
    "documento_lineas": [("documento_id", "documentos")],
    "linea_impuestos": [("linea_id", "documento_lineas")],
    "documento_vencimientos": [("documento_id", "documentos")],
    "documento_relaciones": [("origen_id", "documentos"), ("destino_id", "documentos")],
    "pagos": [("tercero_id", "terceros")],
    "aplicaciones": [("documento_id", "documentos"), ("pago_id", "pagos"), ("credito_id", "documentos")],
}
TIPOS = [("FACTURA", "Invoice", "FACTURA", "EMITIDO", 1, True, False),
         ("NOTA_CREDITO", "Credit note", "NOTA_CREDITO", "EMITIDO", -1, True, True),
         ("NOTA_DEBITO", "Debit note", "NOTA_DEBITO", "EMITIDO", 1, True, True),
         ("PROFORMA", "Proforma invoice", "PROFORMA", "EMITIDO", 1, False, False),
         ("FACTURA_PROVEEDOR", "Supplier invoice", "FACTURA", "RECIBIDO", 1, True, False),
         ("NC_PROVEEDOR", "Supplier credit note", "NOTA_CREDITO", "RECIBIDO", -1, True, True)]
METODOS = [("TRANSFERENCIA", "Bank transfer"), ("CHEQUE", "Check"), ("EFECTIVO", "Cash"), ("TARJETA", "Card"),
           ("COMPENSACION", "Offsetting")]
PERMISOS = ["comercial.ver", "comercial.editar", "comercial.emitir", "comercial.pagos"]


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _esquema() -> None:
    op.create_table('impuestos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('tipo', sa.String(length=12), nullable=False),
    sa.Column('tasa', sa.Numeric(12, 6), nullable=False),
    sa.Column('pais', sa.String(length=2), nullable=True),
    sa.Column('es_retencion', sa.Boolean(), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=True),
    sa.Column('vigente_hasta', sa.Date(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("tipo IN ('PORCENTAJE', 'FIJO')", name='ck_impuestos_tipo'),
    sa.CheckConstraint('tasa >= 0', name='ck_impuestos_tasa'),
    sa.CheckConstraint('vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde', name='ck_impuestos_vigencia'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pais'], ['paises.codigo'], name='fk_impuestos_pais'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', 'vigente_desde', name='uq_impuestos_org_codigo_desde')
    )
    with op.batch_alter_table('impuestos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_impuestos_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('metodos_pago',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_metodos_pago_org_codigo')
    )
    with op.batch_alter_table('metodos_pago', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_metodos_pago_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('tipos_documento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('clase', sa.String(length=15), nullable=False),
    sa.Column('direccion', sa.String(length=10), nullable=False),
    sa.Column('signo', sa.Integer(), nullable=False),
    sa.Column('afecta_saldo', sa.Boolean(), nullable=False),
    sa.Column('requiere_origen', sa.Boolean(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("clase IN ('FACTURA', 'NOTA_CREDITO', 'NOTA_DEBITO', 'PROFORMA')", name='ck_tipos_documento_clase'),
    sa.CheckConstraint("direccion IN ('EMITIDO', 'RECIBIDO')", name='ck_tipos_documento_direccion'),
    sa.CheckConstraint('signo IN (1, -1)', name='ck_tipos_documento_signo'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_tipos_documento_org_codigo')
    )
    with op.batch_alter_table('tipos_documento', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tipos_documento_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('condicion_pago_cuotas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('condicion_id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('porcentaje', sa.Numeric(12, 6), nullable=False),
    sa.Column('dias', sa.Integer(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('dias >= 0', name='ck_condicion_pago_cuotas_dias'),
    sa.CheckConstraint('porcentaje > 0 AND porcentaje <= 100', name='ck_condicion_pago_cuotas_porcentaje'),
    sa.ForeignKeyConstraint(['condicion_id'], ['condiciones_pago.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('condicion_id', 'numero', name='uq_condicion_pago_cuotas_numero')
    )
    with op.batch_alter_table('condicion_pago_cuotas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_condicion_pago_cuotas_condicion_id'), ['condicion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_condicion_pago_cuotas_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('plantillas_documento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo_documento_id', sa.Integer(), nullable=False),
    sa.Column('idioma', sa.String(length=5), nullable=False),
    sa.Column('titulo', sa.String(length=120), nullable=True),
    sa.Column('encabezado', sa.Text(), nullable=True),
    sa.Column('pie', sa.Text(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['tipo_documento_id'], ['tipos_documento.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tipo_documento_id', 'idioma', name='uq_plantillas_documento_tipo_idioma')
    )
    with op.batch_alter_table('plantillas_documento', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_plantillas_documento_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_plantillas_documento_tipo_documento_id'), ['tipo_documento_id'], unique=False)

    op.create_table('terceros',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('extra', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('tipo_persona', sa.String(length=10), nullable=False),
    sa.Column('nombre', sa.String(length=200), nullable=False),
    sa.Column('razon_social', sa.String(length=200), nullable=True),
    sa.Column('tipo_identificacion', sa.String(length=20), nullable=True),
    sa.Column('id_fiscal', sa.String(length=40), nullable=True),
    sa.Column('pais', sa.String(length=2), nullable=True),
    sa.Column('moneda', sa.String(length=3), nullable=True),
    sa.Column('condicion_pago', sa.String(length=20), nullable=True),
    sa.Column('limite_credito', sa.Numeric(18, 4), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("tipo_persona IN ('JURIDICA', 'NATURAL')", name='ck_terceros_tipo_persona'),
    sa.ForeignKeyConstraint(['organizacion_id', 'condicion_pago'], ['condiciones_pago.organizacion_id', 'condiciones_pago.codigo'], name='fk_terceros_condicion_pago'),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda'], ['monedas.organizacion_id', 'monedas.codigo'], name='fk_terceros_moneda'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pais'], ['paises.codigo'], name='fk_terceros_pais'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_terceros_id_org'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_terceros_org_codigo')
    )
    with op.batch_alter_table('terceros', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_terceros_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index('ux_terceros_id_fiscal', ['organizacion_id', 'pais', 'id_fiscal'], unique=True, sqlite_where=sa.text('id_fiscal IS NOT NULL'), postgresql_where=sa.text('id_fiscal IS NOT NULL'))

    op.create_table('tipos_cambio',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('moneda_origen', sa.String(length=3), nullable=False),
    sa.Column('moneda_destino', sa.String(length=3), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('tasa', sa.Numeric(precision=18, scale=8), nullable=False),
    sa.Column('fuente', sa.String(length=80), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('moneda_origen <> moneda_destino', name='ck_tipos_cambio_monedas'),
    sa.CheckConstraint('tasa > 0', name='ck_tipos_cambio_tasa'),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda_destino'], ['monedas.organizacion_id', 'monedas.codigo'], name='fk_tipos_cambio_moneda_destino'),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda_origen'], ['monedas.organizacion_id', 'monedas.codigo'], name='fk_tipos_cambio_moneda_origen'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organizacion_id', 'moneda_origen', 'moneda_destino', 'fecha', name='uq_tipos_cambio_dia')
    )
    with op.batch_alter_table('tipos_cambio', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tipos_cambio_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_tipos_cambio_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('configuracion_fiscal',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sociedad_id', sa.Integer(), nullable=False),
    sa.Column('pais', sa.String(length=2), nullable=True),
    sa.Column('regimen', sa.String(length=80), nullable=True),
    sa.Column('redondeo', sa.String(length=10), nullable=False),
    sa.Column('sin_huecos', sa.Boolean(), nullable=False),
    sa.Column('impuestos_defecto', sa.String(length=200), nullable=True),
    sa.Column('proveedor_electronico', sa.String(length=60), nullable=True),
    sa.Column('datos', sa.JSON(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("redondeo IN ('LINEA', 'DOCUMENTO')", name='ck_configuracion_fiscal_redondeo'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pais'], ['paises.codigo'], name='fk_configuracion_fiscal_pais'),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sociedad_id', name='uq_configuracion_fiscal_sociedad')
    )
    with op.batch_alter_table('configuracion_fiscal', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_configuracion_fiscal_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('tercero_roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tercero_id', sa.Integer(), nullable=False),
    sa.Column('rol', sa.String(length=15), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("rol IN ('CLIENTE', 'PROVEEDOR', 'TRANSPORTISTA', 'AGENTE')", name='ck_tercero_roles_rol'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['tercero_id'], ['terceros.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tercero_id', 'rol', name='uq_tercero_roles_tercero_rol')
    )
    with op.batch_alter_table('tercero_roles', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tercero_roles_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_tercero_roles_tercero_id'), ['tercero_id'], unique=False)

    op.create_table('direcciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tercero_id', sa.Integer(), nullable=True),
    sa.Column('sociedad_id', sa.Integer(), nullable=True),
    sa.Column('centro_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('linea1', sa.String(length=300), nullable=False),
    sa.Column('linea2', sa.String(length=300), nullable=True),
    sa.Column('ciudad', sa.String(length=100), nullable=True),
    sa.Column('region', sa.String(length=100), nullable=True),
    sa.Column('codigo_postal', sa.String(length=20), nullable=True),
    sa.Column('pais', sa.String(length=2), nullable=True),
    sa.Column('principal', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("tipo IN ('FISCAL', 'ENTREGA', 'RECOGIDA', 'OTRA')", name='ck_direcciones_tipo'),
    sa.CheckConstraint('(CASE WHEN tercero_id IS NULL THEN 0 ELSE 1 END + CASE WHEN sociedad_id IS NULL THEN 0 ELSE 1 END + CASE WHEN centro_id IS NULL THEN 0 ELSE 1 END) = 1', name='ck_direcciones_dueno'),
    sa.ForeignKeyConstraint(['centro_id'], ['centros.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pais'], ['paises.codigo'], name='fk_direcciones_pais'),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tercero_id'], ['terceros.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('direcciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_direcciones_centro_id'), ['centro_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_direcciones_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_direcciones_sociedad_id'), ['sociedad_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_direcciones_tercero_id'), ['tercero_id'], unique=False)

    op.create_table('medios_contacto',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tercero_id', sa.Integer(), nullable=True),
    sa.Column('sociedad_id', sa.Integer(), nullable=True),
    sa.Column('centro_id', sa.Integer(), nullable=True),
    sa.Column('contacto_id', sa.Integer(), nullable=True),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('valor', sa.String(length=200), nullable=False),
    sa.Column('uso', sa.String(length=20), nullable=True),
    sa.Column('principal', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("tipo IN ('CORREO', 'TELEFONO', 'MOVIL', 'WEB', 'OTRO')", name='ck_medios_contacto_tipo'),
    sa.CheckConstraint('(CASE WHEN tercero_id IS NULL THEN 0 ELSE 1 END + CASE WHEN sociedad_id IS NULL THEN 0 ELSE 1 END + CASE WHEN centro_id IS NULL THEN 0 ELSE 1 END + CASE WHEN contacto_id IS NULL THEN 0 ELSE 1 END) = 1', name='ck_medios_contacto_dueno'),
    sa.ForeignKeyConstraint(['centro_id'], ['centros.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['contacto_id'], ['contactos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tercero_id'], ['terceros.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('medios_contacto', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_medios_contacto_centro_id'), ['centro_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_medios_contacto_contacto_id'), ['contacto_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_medios_contacto_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_medios_contacto_sociedad_id'), ['sociedad_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_medios_contacto_tercero_id'), ['tercero_id'], unique=False)

    op.create_table('pagos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('direccion', sa.String(length=5), nullable=False),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('tercero_id', sa.Integer(), nullable=False),
    sa.Column('sociedad_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('moneda', sa.String(length=3), nullable=False),
    sa.Column('tipo_cambio', sa.Numeric(precision=18, scale=8), nullable=False),
    sa.Column('importe', sa.Numeric(18, 4), nullable=False),
    sa.Column('metodo_pago_id', sa.Integer(), nullable=True),
    sa.Column('referencia', sa.String(length=80), nullable=True),
    sa.Column('notas', sa.String(length=500), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('anulado_en', sa.DateTime(), nullable=True),
    sa.Column('motivo_anulacion', sa.String(length=500), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("direccion IN ('COBRO', 'PAGO')", name='ck_pagos_direccion'),
    sa.CheckConstraint("estado IN ('REGISTRADO', 'ANULADO')", name='ck_pagos_estado'),
    sa.CheckConstraint('importe > 0', name='ck_pagos_importe'),
    sa.CheckConstraint('tipo_cambio > 0', name='ck_pagos_tipo_cambio'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['metodo_pago_id'], ['metodos_pago.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda'], ['monedas.organizacion_id', 'monedas.codigo'], name='fk_pagos_moneda'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ),
    sa.ForeignKeyConstraint(['tercero_id'], ['terceros.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_pagos_id_org')
    )
    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pagos_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_metodo_pago_id'), ['metodo_pago_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_sociedad_id'), ['sociedad_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_pagos_tercero_id'), ['tercero_id'], unique=False)

    op.create_table('documentos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('extra', sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.Column('tipo_documento_id', sa.Integer(), nullable=False),
    sa.Column('serie_id', sa.Integer(), nullable=True),
    sa.Column('numero', sa.String(length=40), nullable=True),
    sa.Column('referencia_externa', sa.String(length=60), nullable=True),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('sociedad_id', sa.Integer(), nullable=False),
    sa.Column('tercero_id', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=True),
    sa.Column('fecha_vencimiento', sa.Date(), nullable=True),
    sa.Column('moneda', sa.String(length=3), nullable=False),
    sa.Column('tipo_cambio', sa.Numeric(precision=18, scale=8), nullable=False),
    sa.Column('condicion_pago', sa.String(length=20), nullable=True),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('subtotal', sa.Numeric(18, 4), nullable=False),
    sa.Column('descuentos', sa.Numeric(18, 4), nullable=False),
    sa.Column('impuestos', sa.Numeric(18, 4), nullable=False),
    sa.Column('retenciones', sa.Numeric(18, 4), nullable=False),
    sa.Column('total', sa.Numeric(18, 4), nullable=False),
    sa.Column('copia', sa.JSON(), nullable=False),
    sa.Column('factura_id', sa.Integer(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('emitido_en', sa.DateTime(), nullable=True),
    sa.Column('anulado_en', sa.DateTime(), nullable=True),
    sa.Column('motivo_anulacion', sa.String(length=500), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("estado = 'BORRADOR' OR (fecha IS NOT NULL AND (numero IS NOT NULL OR referencia_externa IS NOT NULL))", name='ck_documentos_emitido_numerado'),
    sa.CheckConstraint("estado IN ('BORRADOR', 'EMITIDO', 'ANULADO')", name='ck_documentos_estado'),
    sa.CheckConstraint('fecha_vencimiento IS NULL OR fecha IS NULL OR fecha_vencimiento >= fecha', name='ck_documentos_vencimiento'),
    sa.CheckConstraint('tipo_cambio > 0', name='ck_documentos_tipo_cambio'),
    sa.CheckConstraint('total >= 0 AND subtotal >= 0 AND impuestos >= 0 AND retenciones >= 0 AND descuentos >= 0', name='ck_documentos_importes'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], ),
    sa.ForeignKeyConstraint(['factura_id'], ['facturas.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id', 'condicion_pago'], ['condiciones_pago.organizacion_id', 'condiciones_pago.codigo'], name='fk_documentos_condicion_pago'),
    sa.ForeignKeyConstraint(['organizacion_id', 'moneda'], ['monedas.organizacion_id', 'monedas.codigo'], name='fk_documentos_moneda'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['serie_id'], ['series_documentales.id'], ),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ),
    sa.ForeignKeyConstraint(['tercero_id'], ['terceros.id'], ),
    sa.ForeignKeyConstraint(['tipo_documento_id'], ['tipos_documento.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('factura_id', name='uq_documentos_factura'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_documentos_id_org'),
    sa.UniqueConstraint('serie_id', 'numero', name='uq_documentos_serie_numero')
    )
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documentos_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_fecha_vencimiento'), ['fecha_vencimiento'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_serie_id'), ['serie_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_sociedad_id'), ['sociedad_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_tercero_id'), ['tercero_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documentos_tipo_documento_id'), ['tipo_documento_id'], unique=False)
        batch_op.create_index('ux_documentos_recibido', ['organizacion_id', 'tercero_id', 'tipo_documento_id', 'referencia_externa'], unique=True, sqlite_where=sa.text("referencia_externa IS NOT NULL AND estado <> 'ANULADO'"), postgresql_where=sa.text("referencia_externa IS NOT NULL AND estado <> 'ANULADO'"))

    op.create_table('documento_envios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('documento_id', sa.Integer(), nullable=False),
    sa.Column('sistema', sa.String(length=40), nullable=False),
    sa.Column('estado', sa.String(length=10), nullable=False),
    sa.Column('identificador_externo', sa.String(length=120), nullable=True),
    sa.Column('acuse', sa.JSON(), nullable=False),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('intentos', sa.Integer(), nullable=False),
    sa.Column('actualizado_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("estado IN ('PENDIENTE', 'ENVIADO', 'ACEPTADO', 'RECHAZADO', 'ERROR')", name='ck_documento_envios_estado'),
    sa.CheckConstraint('intentos >= 0', name='ck_documento_envios_intentos'),
    sa.ForeignKeyConstraint(['documento_id'], ['documentos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('documento_id', 'sistema', name='uq_documento_envios_sistema')
    )
    with op.batch_alter_table('documento_envios', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documento_envios_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_envios_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('documento_relaciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('origen_id', sa.Integer(), nullable=False),
    sa.Column('destino_id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=15), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("tipo IN ('RECTIFICA', 'ANULA', 'SUSTITUYE', 'GENERADO_DESDE')", name='ck_documento_relaciones_tipo'),
    sa.CheckConstraint('origen_id <> destino_id', name='ck_documento_relaciones_distintos'),
    sa.ForeignKeyConstraint(['destino_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['origen_id'], ['documentos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('origen_id', 'destino_id', 'tipo', name='uq_documento_relaciones')
    )
    with op.batch_alter_table('documento_relaciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documento_relaciones_destino_id'), ['destino_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_relaciones_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_relaciones_origen_id'), ['origen_id'], unique=False)

    op.create_table('documento_vencimientos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('documento_id', sa.Integer(), nullable=False),
    sa.Column('numero', sa.Integer(), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('importe', sa.Numeric(18, 4), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('importe >= 0', name='ck_documento_vencimientos_importe'),
    sa.ForeignKeyConstraint(['documento_id'], ['documentos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('documento_id', 'numero', name='uq_documento_vencimientos_numero')
    )
    with op.batch_alter_table('documento_vencimientos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documento_vencimientos_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_vencimientos_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_vencimientos_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('facturacion_recurrente',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('modelo_id', sa.Integer(), nullable=False),
    sa.Column('frecuencia', sa.String(length=12), nullable=False),
    sa.Column('proxima', sa.Date(), nullable=False),
    sa.Column('dia', sa.Integer(), nullable=False),
    sa.Column('hasta', sa.Date(), nullable=True),
    sa.Column('emitir', sa.Boolean(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("frecuencia IN ('SEMANAL', 'MENSUAL', 'TRIMESTRAL', 'ANUAL')", name='ck_facturacion_recurrente_frecuencia'),
    sa.CheckConstraint('NOT activo OR hasta IS NULL OR hasta >= proxima', name='ck_facturacion_recurrente_vigencia'),
    sa.ForeignKeyConstraint(['modelo_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('facturacion_recurrente', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_facturacion_recurrente_modelo_id'), ['modelo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_facturacion_recurrente_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_facturacion_recurrente_proxima'), ['proxima'], unique=False)

    op.create_table('aplicaciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pago_id', sa.Integer(), nullable=True),
    sa.Column('credito_id', sa.Integer(), nullable=True),
    sa.Column('documento_id', sa.Integer(), nullable=False),
    sa.Column('vencimiento_id', sa.Integer(), nullable=True),
    sa.Column('importe', sa.Numeric(18, 4), nullable=False),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('(CASE WHEN pago_id IS NULL THEN 0 ELSE 1 END + CASE WHEN credito_id IS NULL THEN 0 ELSE 1 END) = 1', name='ck_aplicaciones_origen'),
    sa.CheckConstraint('credito_id IS NULL OR credito_id <> documento_id', name='ck_aplicaciones_distintos'),
    sa.CheckConstraint('importe > 0', name='ck_aplicaciones_importe'),
    sa.ForeignKeyConstraint(['credito_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['documento_id'], ['documentos.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pago_id'], ['pagos.id'], ),
    sa.ForeignKeyConstraint(['vencimiento_id'], ['documento_vencimientos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('aplicaciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_aplicaciones_credito_id'), ['credito_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_pago_id'), ['pago_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_vencimiento_id'), ['vencimiento_id'], unique=False)

    op.create_table('documento_lineas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('documento_id', sa.Integer(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('articulo_id', sa.Integer(), nullable=True),
    sa.Column('posicion_oc_id', sa.Integer(), nullable=True),
    sa.Column('factura_linea_id', sa.Integer(), nullable=True),
    sa.Column('codigo', sa.String(length=40), nullable=True),
    sa.Column('descripcion', sa.String(length=300), nullable=False),
    sa.Column('cantidad', sa.Numeric(14, 3), nullable=False),
    sa.Column('unidad', sa.String(length=10), nullable=True),
    sa.Column('precio_unitario', sa.Numeric(18, 6), nullable=False),
    sa.Column('descuento_pct', sa.Numeric(12, 6), nullable=False),
    sa.Column('descuento', sa.Numeric(18, 4), nullable=False),
    sa.Column('subtotal', sa.Numeric(18, 4), nullable=False),
    sa.Column('impuestos', sa.Numeric(18, 4), nullable=False),
    sa.Column('retenciones', sa.Numeric(18, 4), nullable=False),
    sa.Column('total', sa.Numeric(18, 4), nullable=False),
    sa.Column('impuestos_codigos', sa.String(length=200), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('cantidad > 0', name='ck_documento_lineas_cantidad'),
    sa.CheckConstraint('descuento_pct >= 0 AND descuento_pct <= 100', name='ck_documento_lineas_descuento'),
    sa.CheckConstraint('precio_unitario >= 0', name='ck_documento_lineas_precio'),
    sa.CheckConstraint('subtotal >= 0 AND impuestos >= 0 AND total >= 0', name='ck_documento_lineas_importes'),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], ),
    sa.ForeignKeyConstraint(['documento_id'], ['documentos.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['factura_linea_id'], ['factura_lineas.id'], ),
    sa.ForeignKeyConstraint(['organizacion_id', 'unidad'], ['unidades_medida.organizacion_id', 'unidades_medida.codigo'], name='fk_documento_lineas_unidad'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['posicion_oc_id'], ['posiciones_oc.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_documento_lineas_id_org')
    )
    with op.batch_alter_table('documento_lineas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documento_lineas_articulo_id'), ['articulo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_lineas_documento_id'), ['documento_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_lineas_factura_linea_id'), ['factura_linea_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_lineas_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_documento_lineas_posicion_oc_id'), ['posicion_oc_id'], unique=False)

    op.create_table('linea_impuestos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('linea_id', sa.Integer(), nullable=False),
    sa.Column('impuesto_id', sa.Integer(), nullable=True),
    sa.Column('codigo', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('tipo', sa.String(length=12), nullable=False),
    sa.Column('tasa', sa.Numeric(12, 6), nullable=False),
    sa.Column('base', sa.Numeric(18, 4), nullable=False),
    sa.Column('importe', sa.Numeric(18, 4), nullable=False),
    sa.Column('es_retencion', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('base >= 0 AND importe >= 0 AND tasa >= 0', name='ck_linea_impuestos_importes'),
    sa.ForeignKeyConstraint(['impuesto_id'], ['impuestos.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['linea_id'], ['documento_lineas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('linea_id', 'codigo', name='uq_linea_impuestos_linea_codigo')
    )
    with op.batch_alter_table('linea_impuestos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_linea_impuestos_impuesto_id'), ['impuesto_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_linea_impuestos_linea_id'), ['linea_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_linea_impuestos_organizacion_id'), ['organizacion_id'], unique=False)

    with op.batch_alter_table('proveedores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tercero_id', sa.Integer(), nullable=True))
        batch_op.create_unique_constraint('uq_proveedores_tercero', ['tercero_id'])
        batch_op.create_foreign_key('fk_proveedores_tercero_id', 'terceros', ['tercero_id'], ['id'])

    with op.batch_alter_table('series_documentales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tipo_documento_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_series_documentales_tipo_documento_id'), ['tipo_documento_id'], unique=False)
        batch_op.create_foreign_key('fk_series_documentales_tipo_documento_id', 'tipos_documento', ['tipo_documento_id'], ['id'])

    with op.batch_alter_table('transportistas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tercero_id', sa.Integer(), nullable=True))
        batch_op.create_unique_constraint('uq_transportistas_tercero', ['tercero_id'])
        batch_op.create_foreign_key('fk_transportistas_tercero_id', 'terceros', ['tercero_id'], ['id'])


def _coherencia() -> None:
    for tabla, lista in COHERENCIA.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, padre in lista:
                b.create_foreign_key(f"fk_{tabla}_{col}_org", padre, [col, "organizacion_id"], ["id", "organizacion_id"])


def _terceros(con) -> None:
    """Un tercero por proveedor y transportista (el mismo si comparten país e identificación fiscal)."""
    usados: dict[tuple, set] = {}
    for org, codigo in con.execute(sa.text("SELECT organizacion_id, codigo FROM terceros")):
        usados.setdefault(org, set()).add(codigo)
    por_id_fiscal: dict[tuple, int] = {}
    for tabla, rol in (("proveedores", "PROVEEDOR"), ("transportistas", "TRANSPORTISTA")):
        cols = "id, organizacion_id, codigo, nombre, id_fiscal, pais" + (", razon_social" if tabla == "proveedores" else "")
        for f in con.execute(sa.text(f"SELECT {cols} FROM {tabla} ORDER BY id")).mappings().all():
            clave = (f["organizacion_id"], f["pais"], (f["id_fiscal"] or "").upper()) if f["id_fiscal"] else None
            tid = por_id_fiscal.get(clave) if clave else None
            if tid is None:
                base, codigo, n = f["codigo"][:26], f["codigo"][:30], 1
                while codigo in usados.setdefault(f["organizacion_id"], set()):
                    n += 1
                    codigo = f"{base}-{n}"
                usados[f["organizacion_id"]].add(codigo)
                con.execute(sa.text(
                    "INSERT INTO terceros (extra, codigo, tipo_persona, nombre, razon_social, id_fiscal, pais, activo, creado_en, "
                    "organizacion_id) VALUES ('{}', :c, 'JURIDICA', :n, :r, :i, :p, :a, :t, :o)"),
                    {"c": codigo, "n": f["nombre"], "r": f.get("razon_social"), "i": f["id_fiscal"], "p": f["pais"], "a": True,
                     "t": _ahora(), "o": f["organizacion_id"]})
                tid = con.execute(sa.text("SELECT id FROM terceros WHERE organizacion_id = :o AND codigo = :c"),
                                  {"o": f["organizacion_id"], "c": codigo}).scalar()
                if clave:
                    por_id_fiscal[clave] = tid
            if not con.execute(sa.text("SELECT 1 FROM tercero_roles WHERE tercero_id = :t AND rol = :r"),
                               {"t": tid, "r": rol}).first():
                con.execute(sa.text("INSERT INTO tercero_roles (tercero_id, rol, organizacion_id) VALUES (:t, :r, :o)"),
                            {"t": tid, "r": rol, "o": f["organizacion_id"]})
            con.execute(sa.text(f"UPDATE {tabla} SET tercero_id = :t WHERE id = :i"), {"t": tid, "i": f["id"]})


def _catalogos(con) -> None:
    for (org,) in con.execute(sa.text("SELECT id FROM organizaciones")).all():
        for i, (c, n, cl, d, s, a, o) in enumerate(TIPOS, start=1):
            con.execute(sa.text(
                "INSERT INTO tipos_documento (codigo, nombre, clase, direccion, signo, afecta_saldo, requiere_origen, orden, "
                "activo, organizacion_id) VALUES (:c, :n, :cl, :d, :s, :a, :o, :i, :si, :org)"),
                {"c": c, "n": n, "cl": cl, "d": d, "s": s, "a": a, "o": o, "i": i, "si": True, "org": org})
        for i, (c, n) in enumerate(METODOS, start=1):
            con.execute(sa.text("INSERT INTO metodos_pago (codigo, nombre, orden, activo, organizacion_id) "
                                "VALUES (:c, :n, :i, :si, :org)"), {"c": c, "n": n, "i": i, "si": True, "org": org})


def _permisos(con) -> None:
    for rid, permisos in con.execute(sa.text("SELECT id, permisos FROM roles WHERE sistema = :si AND tipo IN ('admin', 'interno')"),
                                     {"si": True}).all():
        lista = json.loads(permisos) if isinstance(permisos, str) else list(permisos or [])
        nuevos = sorted(set(lista) | set(PERMISOS))
        if nuevos != sorted(lista):
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(nuevos), "i": rid})


def _cuentas_por_pagar(con) -> None:
    """Las facturas de proveedor finalizadas como documentos recibidos emitidos, con su total."""
    sqlite = con.dialect.name == "sqlite"

    def n(v):  # SQLite no recibe Decimal: el valor ya va redondeado a la escala de la columna
        return float(v) if sqlite else v

    decimales = {(o, c): d for o, c, d in con.execute(sa.text("SELECT organizacion_id, codigo, decimales FROM monedas"))}
    for f in con.execute(sa.text(
            "SELECT f.id, f.organizacion_id, f.numero, f.fecha, f.moneda, f.condiciones, f.finalizado_en, p.tercero_id, "
            "s.id AS sociedad_id FROM facturas f JOIN proveedores p ON p.id = f.proveedor_id "
            "JOIN sociedades s ON s.organizacion_id = f.organizacion_id AND s.codigo = f.sociedad "
            "WHERE f.estado = 'FINALIZADA' ORDER BY f.id")).mappings().all():
        tipo = con.execute(sa.text("SELECT id FROM tipos_documento WHERE organizacion_id = :o AND codigo = 'FACTURA_PROVEEDOR'"),
                           {"o": f["organizacion_id"]}).scalar()
        cuantos = Decimal(1).scaleb(-decimales.get((f["organizacion_id"], f["moneda"]), 2))
        lineas = con.execute(sa.text(
            "SELECT l.id, l.posicion_oc_id, l.codigo_sap, l.descripcion, l.descripcion_comercial, l.cantidad, l.unidad, "
            "l.precio_unitario, p.articulo_id FROM factura_lineas l JOIN posiciones_oc p ON p.id = l.posicion_oc_id "
            "WHERE l.factura_id = :f ORDER BY l.id"), {"f": f["id"]}).mappings().all()
        importes = [(Decimal(str(x["cantidad"])) * Decimal(str(x["precio_unitario"]))).quantize(cuantos, ROUND_HALF_UP)
                    for x in lineas]
        total = sum(importes, Decimal(0))
        fecha = f["fecha"] or (f["finalizado_en"].date() if hasattr(f["finalizado_en"], "date") else None)
        con.execute(sa.text(
            "INSERT INTO documentos (extra, tipo_documento_id, referencia_externa, estado, sociedad_id, tercero_id, fecha, "
            "fecha_vencimiento, moneda, tipo_cambio, notas, subtotal, descuentos, impuestos, retenciones, total, copia, "
            "factura_id, version, creado_en, emitido_en, organizacion_id) VALUES ('{}', :t, :r, 'EMITIDO', :s, :te, :fe, "
            ":fe, :m, 1, :n, :tot, 0, 0, 0, :tot, '{}', :f, 1, :ahora, :em, :o)"),
            {"t": tipo, "r": f["numero"] or f"#{f['id']}", "s": f["sociedad_id"], "te": f["tercero_id"], "fe": fecha,
             "m": f["moneda"], "n": f["condiciones"], "tot": n(total), "f": f["id"], "ahora": _ahora(),
             "em": f["finalizado_en"] or _ahora(), "o": f["organizacion_id"]})
        did = con.execute(sa.text("SELECT id FROM documentos WHERE factura_id = :f"), {"f": f["id"]}).scalar()
        unidades = {u for (u,) in con.execute(sa.text("SELECT codigo FROM unidades_medida WHERE organizacion_id = :o"),
                                              {"o": f["organizacion_id"]})}
        for i, (x, imp) in enumerate(zip(lineas, importes, strict=True), start=1):
            con.execute(sa.text(
                "INSERT INTO documento_lineas (documento_id, orden, articulo_id, posicion_oc_id, factura_linea_id, codigo, "
                "descripcion, cantidad, unidad, precio_unitario, descuento_pct, descuento, subtotal, impuestos, retenciones, "
                "total, organizacion_id) VALUES (:d, :i, :a, :p, :l, :c, :de, :q, :u, :pr, 0, 0, :imp, 0, 0, :imp, :o)"),
                {"d": did, "i": i, "a": x["articulo_id"], "p": x["posicion_oc_id"], "l": x["id"], "c": x["codigo_sap"],
                 "de": (x["descripcion_comercial"] or x["descripcion"] or x["codigo_sap"])[:300], "q": x["cantidad"],
                 "u": x["unidad"] if x["unidad"] in unidades else None, "pr": x["precio_unitario"], "imp": n(imp),
                 "o": f["organizacion_id"]})
        if fecha:
            con.execute(sa.text("INSERT INTO documento_vencimientos (documento_id, numero, fecha, importe, organizacion_id) "
                                "VALUES (:d, 1, :fe, :tot, :o)"), {"d": did, "fe": fecha, "tot": n(total), "o": f["organizacion_id"]})


def upgrade() -> None:
    con = op.get_bind()
    _esquema()
    rls(op, *NUEVAS)
    _coherencia()
    _catalogos(con)
    _terceros(con)
    _permisos(con)
    _cuentas_por_pagar(con)


def downgrade() -> None:
    for tabla, lista in COHERENCIA.items():
        with op.batch_alter_table(tabla, schema=None) as b:
            for col, _ in lista:
                b.drop_constraint(f"fk_{tabla}_{col}_org", type_="foreignkey")
    with op.batch_alter_table('transportistas', schema=None) as batch_op:
        batch_op.drop_constraint('fk_transportistas_tercero_id', type_='foreignkey')
        batch_op.drop_constraint('uq_transportistas_tercero', type_='unique')
        batch_op.drop_column('tercero_id')

    with op.batch_alter_table('series_documentales', schema=None) as batch_op:
        batch_op.drop_constraint('fk_series_documentales_tipo_documento_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_series_documentales_tipo_documento_id'))
        batch_op.drop_column('tipo_documento_id')

    with op.batch_alter_table('proveedores', schema=None) as batch_op:
        batch_op.drop_constraint('fk_proveedores_tercero_id', type_='foreignkey')
        batch_op.drop_constraint('uq_proveedores_tercero', type_='unique')
        batch_op.drop_column('tercero_id')

    with op.batch_alter_table('linea_impuestos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_linea_impuestos_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_linea_impuestos_linea_id'))
        batch_op.drop_index(batch_op.f('ix_linea_impuestos_impuesto_id'))

    op.drop_table('linea_impuestos')
    with op.batch_alter_table('documento_lineas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documento_lineas_posicion_oc_id'))
        batch_op.drop_index(batch_op.f('ix_documento_lineas_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_documento_lineas_factura_linea_id'))
        batch_op.drop_index(batch_op.f('ix_documento_lineas_documento_id'))
        batch_op.drop_index(batch_op.f('ix_documento_lineas_articulo_id'))

    op.drop_table('documento_lineas')
    with op.batch_alter_table('aplicaciones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_aplicaciones_vencimiento_id'))
        batch_op.drop_index(batch_op.f('ix_aplicaciones_pago_id'))
        batch_op.drop_index(batch_op.f('ix_aplicaciones_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_aplicaciones_documento_id'))
        batch_op.drop_index(batch_op.f('ix_aplicaciones_credito_id'))

    op.drop_table('aplicaciones')
    with op.batch_alter_table('facturacion_recurrente', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_facturacion_recurrente_proxima'))
        batch_op.drop_index(batch_op.f('ix_facturacion_recurrente_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_facturacion_recurrente_modelo_id'))

    op.drop_table('facturacion_recurrente')
    with op.batch_alter_table('documento_vencimientos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documento_vencimientos_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_documento_vencimientos_fecha'))
        batch_op.drop_index(batch_op.f('ix_documento_vencimientos_documento_id'))

    op.drop_table('documento_vencimientos')
    with op.batch_alter_table('documento_relaciones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documento_relaciones_origen_id'))
        batch_op.drop_index(batch_op.f('ix_documento_relaciones_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_documento_relaciones_destino_id'))

    op.drop_table('documento_relaciones')
    with op.batch_alter_table('documento_envios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documento_envios_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_documento_envios_documento_id'))

    op.drop_table('documento_envios')
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.drop_index('ux_documentos_recibido', sqlite_where=sa.text("referencia_externa IS NOT NULL AND estado <> 'ANULADO'"), postgresql_where=sa.text("referencia_externa IS NOT NULL AND estado <> 'ANULADO'"))
        batch_op.drop_index(batch_op.f('ix_documentos_tipo_documento_id'))
        batch_op.drop_index(batch_op.f('ix_documentos_tercero_id'))
        batch_op.drop_index(batch_op.f('ix_documentos_sociedad_id'))
        batch_op.drop_index(batch_op.f('ix_documentos_serie_id'))
        batch_op.drop_index(batch_op.f('ix_documentos_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_documentos_fecha_vencimiento'))
        batch_op.drop_index(batch_op.f('ix_documentos_fecha'))
        batch_op.drop_index(batch_op.f('ix_documentos_estado'))

    op.drop_table('documentos')
    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pagos_tercero_id'))
        batch_op.drop_index(batch_op.f('ix_pagos_sociedad_id'))
        batch_op.drop_index(batch_op.f('ix_pagos_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_pagos_metodo_pago_id'))
        batch_op.drop_index(batch_op.f('ix_pagos_fecha'))
        batch_op.drop_index(batch_op.f('ix_pagos_estado'))

    op.drop_table('pagos')
    with op.batch_alter_table('medios_contacto', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_medios_contacto_tercero_id'))
        batch_op.drop_index(batch_op.f('ix_medios_contacto_sociedad_id'))
        batch_op.drop_index(batch_op.f('ix_medios_contacto_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_medios_contacto_contacto_id'))
        batch_op.drop_index(batch_op.f('ix_medios_contacto_centro_id'))

    op.drop_table('medios_contacto')
    with op.batch_alter_table('direcciones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_direcciones_tercero_id'))
        batch_op.drop_index(batch_op.f('ix_direcciones_sociedad_id'))
        batch_op.drop_index(batch_op.f('ix_direcciones_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_direcciones_centro_id'))

    op.drop_table('direcciones')
    with op.batch_alter_table('tercero_roles', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tercero_roles_tercero_id'))
        batch_op.drop_index(batch_op.f('ix_tercero_roles_organizacion_id'))

    op.drop_table('tercero_roles')
    with op.batch_alter_table('configuracion_fiscal', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_configuracion_fiscal_organizacion_id'))

    op.drop_table('configuracion_fiscal')
    with op.batch_alter_table('tipos_cambio', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tipos_cambio_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_tipos_cambio_fecha'))

    op.drop_table('tipos_cambio')
    with op.batch_alter_table('terceros', schema=None) as batch_op:
        batch_op.drop_index('ux_terceros_id_fiscal', sqlite_where=sa.text('id_fiscal IS NOT NULL'), postgresql_where=sa.text('id_fiscal IS NOT NULL'))
        batch_op.drop_index(batch_op.f('ix_terceros_organizacion_id'))

    op.drop_table('terceros')
    with op.batch_alter_table('plantillas_documento', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_plantillas_documento_tipo_documento_id'))
        batch_op.drop_index(batch_op.f('ix_plantillas_documento_organizacion_id'))

    op.drop_table('plantillas_documento')
    with op.batch_alter_table('condicion_pago_cuotas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_condicion_pago_cuotas_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_condicion_pago_cuotas_condicion_id'))

    op.drop_table('condicion_pago_cuotas')
    with op.batch_alter_table('tipos_documento', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tipos_documento_organizacion_id'))

    op.drop_table('tipos_documento')
    with op.batch_alter_table('metodos_pago', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_metodos_pago_organizacion_id'))

    op.drop_table('metodos_pago')
    with op.batch_alter_table('impuestos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_impuestos_organizacion_id'))

    op.drop_table('impuestos')
