"""Empaque: recetas de N niveles y reglas de empaque

- recetas_empaque + receta_niveles: cómo se empaca un artículo (inner ⊂
  master ⊂ pallet…), armado con los tipos de empaque del catálogo.
- reglas_empaque: «para [destino] si [condiciones] → usar [receta]».
- posiciones_oc y factura_lineas: la receta elegida y una foto congelada de
  sus niveles (receta_origen: MANUAL, REGLA o DATOS en la posición).

Conversión (alternativa A, convivir): por cada combinación distinta de
casepack e inner pack de las posiciones de sólidos se crea una receta
automática con los tipos del catálogo de la empresa (el bulto que lleva
producto y, si hay inner, el empaque interior que puede ir dentro) y se enlaza
a sus posiciones y líneas de factura con origen DATOS. Las columnas casepack e
inner_pack no se tocan: el empaque y los documentos siguen leyéndolas. Una
combinación que no cierra (casepack no múltiplo del inner) o una empresa sin
tipos de empaque se deja sin receta, como hoy.

El downgrade quita solo lo agregado: casepack e inner_pack siguen intactos.

Revision ID: 0081
Revises: 0080
Create Date: 2026-10-19 21:00:00
"""
from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls

revision = '0081'
down_revision = '0080'
branch_labels = None
depends_on = None


def _fk(tabla, col, ref, ondelete=None):
    return sa.ForeignKeyConstraint([col], [f'{ref}.id'], name=f'fk_{tabla}_{col}_{ref}', ondelete=ondelete)


def _fk_org(tabla, col, ref, ondelete=None):
    return sa.ForeignKeyConstraint([col, 'organizacion_id'], [f'{ref}.id', f'{ref}.organizacion_id'],
                                   name=f'fk_{tabla}_{col}_org', ondelete=ondelete)


def upgrade() -> None:
    con = op.get_bind()
    op.create_table('recetas_empaque',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nombre', sa.String(length=100), nullable=False),
    sa.Column('descripcion', sa.String(length=300), nullable=True),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('automatica', sa.Boolean(), nullable=False),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('actualizada_en', sa.DateTime(), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    _fk('recetas_empaque', 'organizacion_id', 'organizaciones'),
    sa.PrimaryKeyConstraint('id', name='pk_recetas_empaque'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_recetas_empaque_id_org'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_recetas_empaque_org_codigo'),
    )
    with op.batch_alter_table('recetas_empaque', schema=None) as b:
        b.create_index(b.f('ix_recetas_empaque_organizacion_id'), ['organizacion_id'], unique=False)

    op.create_table('receta_niveles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('receta_id', sa.Integer(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('tipo_empaque_id', sa.Integer(), nullable=False),
    sa.Column('cantidad', sa.Integer(), nullable=False),
    sa.Column('largo', sa.Float(), nullable=True),
    sa.Column('ancho', sa.Float(), nullable=True),
    sa.Column('alto', sa.Float(), nullable=True),
    sa.Column('tara', sa.Float(), nullable=True),
    sa.Column('opcional', sa.Boolean(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('alto IS NULL OR alto >= 0', name='ck_receta_niveles_alto'),
    sa.CheckConstraint('ancho IS NULL OR ancho >= 0', name='ck_receta_niveles_ancho'),
    sa.CheckConstraint('cantidad >= 1', name='ck_receta_niveles_cantidad'),
    sa.CheckConstraint('largo IS NULL OR largo >= 0', name='ck_receta_niveles_largo'),
    sa.CheckConstraint('orden >= 1', name='ck_receta_niveles_orden'),
    sa.CheckConstraint('tara IS NULL OR tara >= 0', name='ck_receta_niveles_tara'),
    _fk('receta_niveles', 'organizacion_id', 'organizaciones'),
    _fk('receta_niveles', 'receta_id', 'recetas_empaque', 'CASCADE'),
    _fk('receta_niveles', 'tipo_empaque_id', 'tipos_empaque'),
    _fk_org('receta_niveles', 'receta_id', 'recetas_empaque', 'CASCADE'),
    _fk_org('receta_niveles', 'tipo_empaque_id', 'tipos_empaque'),
    sa.PrimaryKeyConstraint('id', name='pk_receta_niveles'),
    sa.UniqueConstraint('receta_id', 'orden', name='uq_receta_niveles_receta_orden'),
    )
    with op.batch_alter_table('receta_niveles', schema=None) as b:
        b.create_index(b.f('ix_receta_niveles_organizacion_id'), ['organizacion_id'], unique=False)
        b.create_index(b.f('ix_receta_niveles_receta_id'), ['receta_id'], unique=False)
        b.create_index(b.f('ix_receta_niveles_tipo_empaque_id'), ['tipo_empaque_id'], unique=False)

    op.create_table('reglas_empaque',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('receta_id', sa.Integer(), nullable=False),
    sa.Column('destino', sa.String(length=10), nullable=False),
    sa.Column('familia_id', sa.Integer(), nullable=True),
    sa.Column('producto_id', sa.Integer(), nullable=True),
    sa.Column('articulo_id', sa.Integer(), nullable=True),
    sa.Column('condiciones', sa.JSON(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=True),
    sa.Column('vigente_hasta', sa.Date(), nullable=True),
    sa.Column('motivo', sa.String(length=300), nullable=True),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('creada_por', sa.Integer(), nullable=True),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('actualizada_por', sa.Integer(), nullable=True),
    sa.Column('actualizada_en', sa.DateTime(), nullable=True),
    sa.Column('eliminada_por', sa.Integer(), nullable=True),
    sa.Column('eliminada_en', sa.DateTime(), nullable=True),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("(destino = 'EMPRESA' AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL)"
                       " OR (destino = 'FAMILIA' AND familia_id IS NOT NULL AND producto_id IS NULL AND articulo_id IS NULL)"
                       " OR (destino = 'PRODUCTO' AND producto_id IS NOT NULL AND familia_id IS NULL AND articulo_id IS NULL)"
                       " OR (destino = 'ARTICULO' AND articulo_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL)",
                       name='ck_reglas_empaque_destino_unico'),
    sa.CheckConstraint("destino IN ('EMPRESA', 'FAMILIA', 'PRODUCTO', 'ARTICULO')", name='ck_reglas_empaque_destino'),
    sa.CheckConstraint('vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde',
                       name='ck_reglas_empaque_vigencia'),
    _fk('reglas_empaque', 'organizacion_id', 'organizaciones'),
    _fk('reglas_empaque', 'receta_id', 'recetas_empaque'),
    _fk('reglas_empaque', 'familia_id', 'familias_etiquetado'),
    _fk('reglas_empaque', 'producto_id', 'productos'),
    _fk('reglas_empaque', 'articulo_id', 'articulos'),
    _fk('reglas_empaque', 'creada_por', 'usuarios'),
    _fk('reglas_empaque', 'actualizada_por', 'usuarios'),
    _fk('reglas_empaque', 'eliminada_por', 'usuarios'),
    _fk_org('reglas_empaque', 'receta_id', 'recetas_empaque'),
    _fk_org('reglas_empaque', 'familia_id', 'familias_etiquetado'),
    _fk_org('reglas_empaque', 'producto_id', 'productos'),
    _fk_org('reglas_empaque', 'articulo_id', 'articulos'),
    sa.PrimaryKeyConstraint('id', name='pk_reglas_empaque'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_reglas_empaque_id_org'),
    )
    with op.batch_alter_table('reglas_empaque', schema=None) as b:
        b.create_index(b.f('ix_reglas_empaque_articulo_id'), ['articulo_id'], unique=False)
        b.create_index(b.f('ix_reglas_empaque_eliminada_en'), ['eliminada_en'], unique=False)
        b.create_index(b.f('ix_reglas_empaque_familia_id'), ['familia_id'], unique=False)
        b.create_index(b.f('ix_reglas_empaque_organizacion_id'), ['organizacion_id'], unique=False)
        b.create_index(b.f('ix_reglas_empaque_producto_id'), ['producto_id'], unique=False)
        b.create_index(b.f('ix_reglas_empaque_receta_id'), ['receta_id'], unique=False)

    with op.batch_alter_table('factura_lineas', schema=None) as b:
        b.add_column(sa.Column('receta_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('receta_foto', sa.JSON(), nullable=True))
        b.create_index(b.f('ix_factura_lineas_receta_id'), ['receta_id'], unique=False)
        b.create_foreign_key('fk_factura_lineas_receta_id_recetas_empaque', 'recetas_empaque', ['receta_id'], ['id'])
        b.create_foreign_key('fk_factura_lineas_receta_id_org', 'recetas_empaque', ['receta_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])

    with op.batch_alter_table('posiciones_oc', schema=None) as b:
        b.add_column(sa.Column('receta_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('receta_origen', sa.String(length=10), nullable=True))
        b.add_column(sa.Column('receta_regla_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('receta_foto', sa.JSON(), nullable=True))
        b.create_index(b.f('ix_posiciones_oc_receta_id'), ['receta_id'], unique=False)
        b.create_foreign_key('fk_posiciones_oc_receta_id_recetas_empaque', 'recetas_empaque', ['receta_id'], ['id'])
        b.create_foreign_key('fk_posiciones_oc_receta_regla_id_reglas_empaque', 'reglas_empaque', ['receta_regla_id'], ['id'])
        b.create_foreign_key('fk_posiciones_oc_receta_id_org', 'recetas_empaque', ['receta_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
        b.create_foreign_key('fk_posiciones_oc_receta_regla_id_org', 'reglas_empaque', ['receta_regla_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
        b.create_check_constraint('ck_posiciones_oc_receta_origen',
                                  "receta_origen IS NULL OR receta_origen IN ('MANUAL', 'REGLA', 'DATOS')")
    rls(op, 'recetas_empaque', 'receta_niveles', 'reglas_empaque')
    _convertir(con)


def _convertir(con) -> None:
    """Una receta automática por combinación de casepack e inner pack de los sólidos."""
    from datetime import datetime, timezone

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    tipos = con.execute(sa.text(
        "SELECT id, organizacion_id, codigo, nombre, nivel, cuenta_como, contiene_productos, largo, ancho, alto, tara "
        "FROM tipos_empaque WHERE activo ORDER BY nivel, codigo")).mappings().all()
    contiene = {}
    for padre, hijo in con.execute(sa.text("SELECT padre_id, hijo_id FROM tipo_empaque_contiene")).all():
        contiene.setdefault(padre, set()).add(hijo)
    combos = con.execute(sa.text(
        "SELECT DISTINCT organizacion_id, casepack, inner_pack FROM posiciones_oc "
        "WHERE casepack IS NOT NULL AND casepack > 0 AND (tipo_empaque IS NULL OR tipo_empaque <> 'PREPACK')")).all()
    foto_param = sa.bindparam('f', type_=sa.JSON)
    for org, casepack, inner in combos:
        de_org = [t for t in tipos if t['organizacion_id'] == org]
        bulto = next((t for t in de_org if t['cuenta_como'] == 'BULTO' and t['contiene_productos']), None)
        if bulto is None:
            continue
        interior = None
        if inner and inner < casepack:
            if casepack % inner:
                continue  # no cierra: se deja como está
            interior = next((t for t in de_org if t['id'] in contiene.get(bulto['id'], set()) and t['contiene_productos']
                             and t['nivel'] < bulto['nivel']), None)
            if interior is None:
                continue
        niveles = ([(interior, inner), (bulto, casepack // inner)] if interior else [(bulto, casepack)])
        codigo = f"CP{casepack}" + (f"-IN{inner}" if interior else "")
        nombre = f"{bulto['nombre']} {casepack}" + (f" · {interior['nombre']} {inner}" if interior else "")
        rid = con.execute(sa.text("SELECT id FROM recetas_empaque WHERE organizacion_id = :o AND codigo = :c"),
                          {"o": org, "c": codigo}).scalar()
        if rid is None:
            con.execute(sa.text(
                "INSERT INTO recetas_empaque (organizacion_id, codigo, nombre, activa, automatica, creada_en, "
                "actualizada_en, version) VALUES (:o, :c, :n, :a, :a, :t, :t, 1)"),
                {"o": org, "c": codigo, "n": nombre[:100], "a": True, "t": ahora})
            rid = con.execute(sa.text("SELECT id FROM recetas_empaque WHERE organizacion_id = :o AND codigo = :c"),
                              {"o": org, "c": codigo}).scalar()
            for i, (t, n) in enumerate(niveles, start=1):
                con.execute(sa.text("INSERT INTO receta_niveles (organizacion_id, receta_id, orden, tipo_empaque_id, cantidad, "
                                    "opcional) VALUES (:o, :r, :i, :t, :n, :op)"),
                            {"o": org, "r": rid, "i": i, "t": t['id'], "n": n, "op": False})
        unidades, foto_niveles = 1, []
        for i, (t, n) in enumerate(niveles, start=1):
            unidades *= n
            foto_niveles.append({"orden": i, "tipo_empaque_id": t['id'], "codigo": t['codigo'], "nombre": t['nombre'],
                                 "cuenta_como": t['cuenta_como'], "cantidad": n, "unidades": unidades,
                                 "largo": t['largo'], "ancho": t['ancho'], "alto": t['alto'], "tara": t['tara'],
                                 "opcional": False})
        foto = {"receta_id": rid, "codigo": codigo, "nombre": nombre[:100], "niveles": foto_niveles}
        filtro_inner = "inner_pack = :i" if inner else "inner_pack IS NULL"
        params = {"o": org, "c": casepack, "i": inner, "r": rid}
        con.execute(sa.text(
            f"UPDATE posiciones_oc SET receta_id = :r, receta_origen = 'DATOS', receta_foto = :f WHERE organizacion_id = :o "
            f"AND casepack = :c AND {filtro_inner} AND (tipo_empaque IS NULL OR tipo_empaque <> 'PREPACK')"
            ).bindparams(foto_param), {**params, "f": foto})
        con.execute(sa.text(
            f"UPDATE factura_lineas SET receta_id = :r, receta_foto = :f WHERE organizacion_id = :o "
            f"AND casepack = :c AND {filtro_inner} AND (tipo_empaque IS NULL OR tipo_empaque <> 'PREPACK')"
            ).bindparams(foto_param), {**params, "f": foto})


def downgrade() -> None:
    with op.batch_alter_table('posiciones_oc', schema=None) as b:
        b.drop_constraint('ck_posiciones_oc_receta_origen', type_='check')
        b.drop_constraint('fk_posiciones_oc_receta_regla_id_org', type_='foreignkey')
        b.drop_constraint('fk_posiciones_oc_receta_id_org', type_='foreignkey')
        b.drop_constraint('fk_posiciones_oc_receta_regla_id_reglas_empaque', type_='foreignkey')
        b.drop_constraint('fk_posiciones_oc_receta_id_recetas_empaque', type_='foreignkey')
        b.drop_index(b.f('ix_posiciones_oc_receta_id'))
        b.drop_column('receta_foto')
        b.drop_column('receta_regla_id')
        b.drop_column('receta_origen')
        b.drop_column('receta_id')
    with op.batch_alter_table('factura_lineas', schema=None) as b:
        b.drop_constraint('fk_factura_lineas_receta_id_org', type_='foreignkey')
        b.drop_constraint('fk_factura_lineas_receta_id_recetas_empaque', type_='foreignkey')
        b.drop_index(b.f('ix_factura_lineas_receta_id'))
        b.drop_column('receta_foto')
        b.drop_column('receta_id')
    op.drop_table('reglas_empaque')
    op.drop_table('receta_niveles')
    op.drop_table('recetas_empaque')
