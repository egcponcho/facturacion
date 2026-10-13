"""Recepción por contenedor y bodega, hitos por contenedor y permisos nuevos

- recepcion_registros / recepcion_movimientos: cada recepción es un registro
  de una unidad de carga (contenedor, guía, camión) en una bodega o bodega
  fiscal, con la fecha en que se recibió, y sus movimientos por línea del PL
  (conteos parciales, ajustes con motivo, confirmación sin conteo).
  `recepciones` queda como la suma por línea.
- unidades_carga: bodega de llegada (centro), liberación, entrega y estado de
  su recepción (PENDIENTE, EN_RECEPCION, RECIBIDA) con su fecha.
- eventos_embarque.unidad_carga_id: hitos de un solo contenedor.
- recepciones: lo dañado no puede superar lo recibido.
- Permisos de existencias y costos logísticos para los roles de fábrica.

Las recepciones existentes pasan a un registro por contenedor (un conteo con
la fecha de la última recepción y la bodega del embarque o de la factura). Un
dañado mayor que lo recibido (dato imposible) se deja igual a lo recibido y
queda anotado en el movimiento: la migración no se detiene.

Revision ID: 0069
Revises: 0068
Create Date: 2026-10-14 00:00:00
"""
import json

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0069'
down_revision = '0068'
branch_labels = None
depends_on = None

PERMISOS = ("inventario.ver", "costos.ver", "costos.editar")


def _esquema() -> None:
    op.create_table('recepcion_registros',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('unidad_carga_id', sa.Integer(), nullable=False),
    sa.Column('centro', sa.String(length=10), nullable=False),
    sa.Column('fecha', sa.Date(), nullable=False),
    sa.Column('tipo', sa.String(length=12), nullable=False),
    sa.Column('observacion', sa.String(length=500), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("tipo IN ('CONTEO', 'AJUSTE', 'SIN_CONTEO')", name='ck_recepcion_registros_tipo'),
    sa.ForeignKeyConstraint(['organizacion_id', 'centro'], ['centros.organizacion_id', 'centros.codigo'], name='fk_recepcion_registros_centro'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['unidad_carga_id'], ['unidades_carga.id'], ),
    sa.ForeignKeyConstraint(['unidad_carga_id', 'organizacion_id'], ['unidades_carga.id', 'unidades_carga.organizacion_id'],
                            name='fk_recepcion_registros_unidad_carga_id_org'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_recepcion_registros_id_org')
    )
    with op.batch_alter_table('recepcion_registros', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recepcion_registros_centro'), ['centro'], unique=False)
        batch_op.create_index(batch_op.f('ix_recepcion_registros_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_recepcion_registros_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recepcion_registros_unidad_carga_id'), ['unidad_carga_id'], unique=False)

    op.create_table('recepcion_movimientos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('registro_id', sa.Integer(), nullable=False),
    sa.Column('pl_linea_id', sa.Integer(), nullable=False),
    sa.Column('cantidad', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('danada', sa.Numeric(precision=14, scale=3), nullable=False),
    sa.Column('observacion', sa.String(length=300), nullable=True),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['pl_linea_id'], ['pl_lineas.id'], ),
    sa.ForeignKeyConstraint(['registro_id'], ['recepcion_registros.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['registro_id', 'organizacion_id'], ['recepcion_registros.id', 'recepcion_registros.organizacion_id'],
                            name='fk_recepcion_movimientos_registro_id_org'),
    sa.ForeignKeyConstraint(['pl_linea_id', 'organizacion_id'], ['pl_lineas.id', 'pl_lineas.organizacion_id'],
                            name='fk_recepcion_movimientos_pl_linea_id_org'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('recepcion_movimientos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recepcion_movimientos_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recepcion_movimientos_pl_linea_id'), ['pl_linea_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_recepcion_movimientos_registro_id'), ['registro_id'], unique=False)

    with op.batch_alter_table('eventos_embarque', schema=None) as batch_op:
        batch_op.add_column(sa.Column('unidad_carga_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_eventos_embarque_unidad_carga_id'), ['unidad_carga_id'], unique=False)
        batch_op.create_foreign_key('fk_eventos_embarque_unidad_carga_id', 'unidades_carga', ['unidad_carga_id'], ['id'])
        batch_op.create_foreign_key('fk_eventos_embarque_unidad_carga_id_org', 'unidades_carga',
                                    ['unidad_carga_id', 'organizacion_id'], ['id', 'organizacion_id'])

    with op.batch_alter_table('unidades_carga', schema=None) as batch_op:
        batch_op.add_column(sa.Column('centro', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('liberada_en', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('entregada_en', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('recepcion_estado', sa.String(length=12), server_default='PENDIENTE', nullable=False))
        batch_op.add_column(sa.Column('recibida_en', sa.Date(), nullable=True))
        batch_op.create_foreign_key('fk_unidades_carga_centro', 'centros', ['organizacion_id', 'centro'], ['organizacion_id', 'codigo'])
        batch_op.create_check_constraint('ck_unidades_carga_recepcion_estado',
                                         "recepcion_estado IN ('PENDIENTE', 'EN_RECEPCION', 'RECIBIDA')")
    rls(op, 'recepcion_registros', 'recepcion_movimientos')


def _fecha(v):
    """SQLite devuelve texto; PostgreSQL, fechas."""
    return None if v is None else (v[:10] if isinstance(v, str) else v.date() if hasattr(v, "date") else v)


def _datos(con) -> None:
    """Un registro de recepción por contenedor con lo ya recibido de sus líneas."""
    eventos: dict[tuple[int, str], object] = {}
    for emb_id, tipo, fecha in con.execute(sa.text(
            "SELECT embarque_id, tipo, MAX(fecha) FROM eventos_embarque GROUP BY embarque_id, tipo")):
        eventos[(emb_id, tipo)] = _fecha(fecha)
    unidades = con.execute(sa.text(
        "SELECT u.id, u.organizacion_id, u.embarque_id, e.centro, e.estado FROM unidades_carga u "
        "JOIN embarques e ON e.id = u.embarque_id")).mappings().all()
    for u in unidades:
        lineas = con.execute(sa.text(
            "SELECT l.id, l.cantidad, f.centro AS centro_factura, r.id AS rec_id, r.cantidad_recibida, r.cantidad_danada, "
            "r.observacion, r.usuario_id, r.fecha FROM pl_lineas l JOIN packing_lists p ON p.id = l.pl_id "
            "JOIN facturas f ON f.id = p.factura_id LEFT JOIN recepciones r ON r.pl_linea_id = l.id "
            "WHERE p.unidad_carga_id = :u AND p.estado <> 'CANCELADO'"), {"u": u["id"]}).mappings().all()
        recibidas = [x for x in lineas if x["rec_id"] is not None]
        centro = u["centro"] or next((x["centro_factura"] for x in lineas if x["centro_factura"]), None)
        entregada = eventos.get((u["embarque_id"], "ENTREGA")) if u["estado"] in ("ENTREGADO", "RECIBIDO") else None
        liberada = eventos.get((u["embarque_id"], "LIBERACION"))
        if not recibidas or not centro:
            con.execute(sa.text("UPDATE unidades_carga SET centro = :c, entregada_en = :e, liberada_en = :l WHERE id = :u"),
                        {"c": centro, "e": entregada, "l": liberada, "u": u["id"]})
            continue
        # La fecha del hito de recepción (operativa) antes que la de captura
        fecha = eventos.get((u["embarque_id"], "RECEPCION")) or max(_fecha(x["fecha"]) for x in recibidas)
        usuario = next((x["usuario_id"] for x in sorted(recibidas, key=lambda x: str(x["fecha"]), reverse=True)
                        if x["usuario_id"]), None)
        con.execute(sa.text(
            "INSERT INTO recepcion_registros (unidad_carga_id, centro, fecha, tipo, observacion, usuario_id, creado_en, "
            "organizacion_id) VALUES (:u, :c, :f, 'CONTEO', :o, :us, CURRENT_TIMESTAMP, :org)"),
            {"u": u["id"], "c": centro, "f": fecha, "o": "Receipt recorded before the per-container receipt.",
             "us": usuario, "org": u["organizacion_id"]})
        reg_id = con.execute(sa.text("SELECT MAX(id) FROM recepcion_registros WHERE unidad_carga_id = :u"),
                             {"u": u["id"]}).scalar()
        for x in recibidas:
            recibido, danado = float(x["cantidad_recibida"] or 0), float(x["cantidad_danada"] or 0)
            nota = x["observacion"]
            if danado > recibido:
                nota = f"Damaged {danado:g} above received {recibido:g}: set to {recibido:g} when migrating."[:300]
                danado = recibido
                con.execute(sa.text("UPDATE recepciones SET cantidad_danada = :d WHERE id = :i"), {"d": danado, "i": x["rec_id"]})
            con.execute(sa.text(
                "INSERT INTO recepcion_movimientos (registro_id, pl_linea_id, cantidad, danada, observacion, organizacion_id) "
                "VALUES (:r, :l, :c, :d, :o, :org)"),
                {"r": reg_id, "l": x["id"], "c": recibido, "d": danado, "o": nota, "org": u["organizacion_id"]})
        completa = len(recibidas) == len(lineas)
        recibida_en = eventos.get((u["embarque_id"], "RECEPCION")) or fecha
        con.execute(sa.text(
            "UPDATE unidades_carga SET centro = :c, recepcion_estado = :s, recibida_en = :r, entregada_en = :e, "
            "liberada_en = :l WHERE id = :u"),
            {"c": centro, "s": "RECIBIDA" if completa else "EN_RECEPCION", "r": recibida_en if completa else None,
             "e": entregada or (fecha if completa else None), "l": liberada, "u": u["id"]})


def _permisos(con) -> None:
    for rid, permisos in con.execute(sa.text("SELECT id, permisos FROM roles WHERE sistema = :si AND tipo IN ('admin', 'interno')"),
                                     {"si": True}).all():
        lista = json.loads(permisos) if isinstance(permisos, str) else list(permisos or [])
        nuevos = sorted(set(lista) | set(PERMISOS))
        if nuevos != sorted(lista):
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(nuevos), "i": rid})


def upgrade() -> None:
    con = op.get_bind()
    _esquema()
    _datos(con)
    with op.batch_alter_table('recepciones', schema=None) as b:
        b.create_check_constraint('ck_recepciones_danada_hasta_recibida',
                                  "cantidad_danada IS NULL OR cantidad_danada <= cantidad_recibida")
    _permisos(con)


def downgrade() -> None:
    with op.batch_alter_table('recepciones', schema=None) as b:
        b.drop_constraint('ck_recepciones_danada_hasta_recibida', type_='check')
    with op.batch_alter_table('unidades_carga', schema=None) as batch_op:
        batch_op.drop_constraint('ck_unidades_carga_recepcion_estado', type_='check')
        batch_op.drop_constraint('fk_unidades_carga_centro', type_='foreignkey')
        batch_op.drop_column('recibida_en')
        batch_op.drop_column('recepcion_estado')
        batch_op.drop_column('entregada_en')
        batch_op.drop_column('liberada_en')
        batch_op.drop_column('centro')
    with op.batch_alter_table('eventos_embarque', schema=None) as batch_op:
        batch_op.drop_constraint('fk_eventos_embarque_unidad_carga_id_org', type_='foreignkey')
        batch_op.drop_constraint('fk_eventos_embarque_unidad_carga_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_eventos_embarque_unidad_carga_id'))
        batch_op.drop_column('unidad_carga_id')
    with op.batch_alter_table('recepcion_movimientos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recepcion_movimientos_registro_id'))
        batch_op.drop_index(batch_op.f('ix_recepcion_movimientos_pl_linea_id'))
        batch_op.drop_index(batch_op.f('ix_recepcion_movimientos_organizacion_id'))
    op.drop_table('recepcion_movimientos')
    with op.batch_alter_table('recepcion_registros', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recepcion_registros_unidad_carga_id'))
        batch_op.drop_index(batch_op.f('ix_recepcion_registros_organizacion_id'))
        batch_op.drop_index(batch_op.f('ix_recepcion_registros_fecha'))
        batch_op.drop_index(batch_op.f('ix_recepcion_registros_centro'))
    op.drop_table('recepcion_registros')
