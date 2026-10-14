"""Etiquetado genérico: tipos de etiqueta y usos de diseño (docs/ETIQUETADO_EVALUACION.md §7)

- tipos_etiqueta: cada empresa define sus tipos (colgante, precio, caja,
  contenido de OC…) con qué se etiqueta (artículo, bulto o documento) y
  cuántas salen. Reemplazan la modalidad y la unidad de los diseños: cada
  combinación (modalidad, unidad) de los diseños existentes se convierte en un
  tipo; ARTICULO y OC_ARTICULO con la misma unidad caen en el mismo tipo
  (el artículo lleva la misma etiqueta venga o no de una OC).
- plantillas_etiqueta: tipo_etiqueta_id en lugar de modalidad, unidad y
  familia_id (la familia de un diseño ahora es un uso de diseño).
- usos_diseno reemplaza a asignaciones_etiqueta. Cada regla se convierte:
  GENERAL → toda la empresa; FAMILIA, PRODUCTO, ARTICULO → su nivel; OC →
  excepción de esa OC; REGLA o con condiciones o vigencia → excepción por
  condición; tipos de empaque → nivel tipo de empaque. La prioridad numérica y
  la predeterminada desaparecen: si en una celda quedaban varios diseños
  normales, sigue el de mayor prioridad (luego la predeterminada, luego la más
  antigua) y los demás quedan dados de baja. Lo que no tiene equivalente (un
  bulto o documento por familia, producto o artículo) también queda de baja.
  Cada conversión queda en el historial (entidad uso_diseno, acción migrar)
  con la regla original y qué pasó con ella.
- productos.familia_etiquetado_id: la familia del estilo-color (la heredan
  sus tallas que no tienen una propia).
- trabajo_etiqueta_registros: tipo_etiqueta_id y uso_id (en lugar de regla_id).
- generaciones_etiqueta: sin modalidad ni unidad (el tipo va en cada ítem).
- generacion_items: tipo_etiqueta_id y la identidad del bulto (pl_id,
  grupo_cajas_id, bulto_indice): el «ya impreso» de un bulto ya no se cruza por
  su texto.
- campos_etiqueta.modalidades → sujetos.
- Permiso etiquetas.asignar → etiquetas.configurar (mismo alcance, nombre nuevo).

Revertir: el downgrade vuelve a crear asignaciones_etiqueta con una regla por
uso vigente (prioridad por nivel) y la modalidad y unidad de cada diseño desde
su tipo; los tipos, usos dados de baja y la familia de los productos se pierden.

Revision ID: 0076
Revises: 0075
Create Date: 2026-10-17 09:00:00
"""
import json
import logging
from datetime import datetime

import sqlalchemy as sa

from alembic import op
from app.instalacion.esquema import rls

revision = '0076'
down_revision = '0075'
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.0076")

# (modalidad, unidad) del diseño → (sujeto, cantidad) del tipo
CANTIDAD = {"UNIDAD": "POR_UNIDAD", "LINEA": "POR_LINEA", "ARTICULO": "POR_ARTICULO", "MANUAL": "MANUAL",
            "BULTO": "POR_BULTO", "ORDEN": "POR_DOCUMENTO"}
TIPOS = {("ARTICULO", "POR_UNIDAD"): ("ART-UNIDAD", "Item label (one per unit)"),
         ("ARTICULO", "POR_LINEA"): ("ART-LINEA", "Item label (one per line)"),
         ("ARTICULO", "POR_ARTICULO"): ("ART-ARTICULO", "Item label (one per item)"),
         ("ARTICULO", "MANUAL"): ("ART-MANUAL", "Item label (quantity written by hand)"),
         ("BULTO", "POR_BULTO"): ("BULTO", "Package label"),
         ("DOCUMENTO", "POR_DOCUMENTO"): ("DOCUMENTO", "Document label"),
         ("DOCUMENTO", "MANUAL"): ("DOC-MANUAL", "Document label (quantity written by hand)")}
PRIORIDAD_NIVEL = {"OC": 500, "SKU": 400, "PRODUCTO": 300, "TIPO_EMPAQUE": 250, "FAMILIA": 200, "GENERAL": 100}


def _sujeto(modalidad: str, unidad: str) -> tuple[str, str]:
    if unidad == "BULTO":
        return "BULTO", "POR_BULTO"
    if modalidad == "OC":
        return "DOCUMENTO", "MANUAL" if unidad == "MANUAL" else "POR_DOCUMENTO"
    return "ARTICULO", CANTIDAD.get(unidad, "POR_LINEA")


def _json(v, defecto):
    if v is None:
        return defecto
    return json.loads(v) if isinstance(v, str) else v


def _org(tabla: str) -> list:
    return [sa.Column('organizacion_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name=f'fk_{tabla}_organizacion_id_organizaciones')]


def _quitar_columnas(tabla: str, columnas: list[str]) -> None:
    """Quita columnas con sus índices, llaves y restricciones con nombre (en SQLite
    la tabla se copia; en PostgreSQL la base quita lo que dependía de ellas)."""
    con = op.get_bind()
    insp = sa.inspect(con)
    cols = set(columnas)
    fks = [f["name"] for f in insp.get_foreign_keys(tabla) if f.get("name") and cols & set(f["constrained_columns"])]
    ixs = [i["name"] for i in insp.get_indexes(tabla) if cols & set(i["column_names"] or [])]
    cks = [c["name"] for c in insp.get_check_constraints(tabla)
           if c.get("name") and any(col in (c.get("sqltext") or "") for col in cols)]
    with op.batch_alter_table(tabla, schema=None) as b:
        for n in fks:
            b.drop_constraint(n, type_='foreignkey')
        for n in ixs:
            b.drop_index(n)
        for n in cks:
            b.drop_constraint(n, type_='check')
        for c in columnas:
            b.drop_column(c)


def _historial(con, org: int, uso_id: int, detalle: dict) -> None:
    con.execute(sa.text("INSERT INTO historial (organizacion_id, entidad, entidad_id, accion, detalle, fecha) "
                        "VALUES (:o, 'uso_diseno', :i, 'migrar', :d, :f)"),
                {"o": org, "i": uso_id, "d": json.dumps(detalle, ensure_ascii=False, default=str), "f": datetime.utcnow()})


def _permisos(con, de: str, a: str) -> None:
    for rid, permisos in con.execute(sa.text("SELECT id, permisos FROM roles")).all():
        lista = _json(permisos, [])
        if de in lista:
            nuevos = sorted((set(lista) - {de}) | {a})
            con.execute(sa.text("UPDATE roles SET permisos = :p WHERE id = :i"), {"p": json.dumps(nuevos), "i": rid})


def upgrade() -> None:
    con = op.get_bind()
    ahora = datetime.utcnow()

    # ---- Tipos de etiqueta ------------------------------------------------------------------
    op.create_table('tipos_etiqueta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('codigo', sa.String(length=30), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('descripcion', sa.String(length=300), nullable=True),
    sa.Column('sujeto', sa.String(length=10), nullable=False),
    sa.Column('cantidad', sa.String(length=14), nullable=False),
    sa.Column('obligatoria', sa.Boolean(), nullable=False),
    sa.Column('orden', sa.Integer(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_en', sa.DateTime(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    *_org('tipos_etiqueta'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], name='fk_tipos_etiqueta_creado_por_usuarios'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id'], name='fk_tipos_etiqueta_actualizado_por_usuarios'),
    sa.PrimaryKeyConstraint('id', name='pk_tipos_etiqueta'),
    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_tipos_etiqueta_org_codigo'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_tipos_etiqueta_id_org'),
    sa.CheckConstraint("sujeto IN ('ARTICULO', 'BULTO', 'DOCUMENTO')", name='ck_tipos_etiqueta_sujeto'),
    sa.CheckConstraint("cantidad IN ('POR_UNIDAD', 'POR_LINEA', 'POR_ARTICULO', 'POR_BULTO', 'POR_DOCUMENTO', 'MANUAL')",
                       name='ck_tipos_etiqueta_cantidad'),
    )
    with op.batch_alter_table('tipos_etiqueta', schema=None) as b:
        b.create_index(b.f('ix_tipos_etiqueta_organizacion_id'), ['organizacion_id'], unique=False)

    # Un tipo por cada (sujeto, cantidad) de los diseños de cada organización
    tipo_de: dict = {}  # (org, modalidad, unidad) → tipo_id
    filas = con.execute(sa.text("SELECT DISTINCT organizacion_id, modalidad, unidad FROM plantillas_etiqueta "
                                "ORDER BY organizacion_id, modalidad, unidad")).all()
    por_org: dict = {}
    for org, modalidad, unidad in filas:
        clave = _sujeto(modalidad, unidad)
        if (org, clave) not in por_org:
            codigo, nombre = TIPOS[clave]
            orden = len([k for k in por_org if k[0] == org])
            por_org[(org, clave)] = con.execute(sa.text(
                "INSERT INTO tipos_etiqueta (organizacion_id, codigo, nombre, descripcion, sujeto, cantidad, obligatoria, orden,"
                " activo, creado_en, version) VALUES (:o, :c, :n, :d, :s, :q, :ob, :od, :a, :f, 1) RETURNING id"),
                {"o": org, "c": codigo, "n": nombre, "d": "Created from the data mode and unit of the existing designs.",
                 "s": clave[0], "q": clave[1], "ob": False, "od": orden, "a": True, "f": ahora}).scalar()
        tipo_de[(org, modalidad, unidad)] = por_org[(org, clave)]

    with op.batch_alter_table('plantillas_etiqueta', schema=None) as b:
        b.add_column(sa.Column('tipo_etiqueta_id', sa.Integer(), nullable=True))
    for (org, modalidad, unidad), tid in tipo_de.items():
        con.execute(sa.text("UPDATE plantillas_etiqueta SET tipo_etiqueta_id = :t WHERE organizacion_id = :o AND modalidad = :m "
                            "AND unidad = :u"), {"t": tid, "o": org, "m": modalidad, "u": unidad})
    tipo_plantilla = dict(con.execute(sa.text("SELECT id, tipo_etiqueta_id FROM plantillas_etiqueta")).all())
    sujeto_tipo = dict(con.execute(sa.text("SELECT id, sujeto FROM tipos_etiqueta")).all())

    # ---- Familia del producto ----------------------------------------------------------------
    with op.batch_alter_table('productos', schema=None) as b:
        b.add_column(sa.Column('familia_etiquetado_id', sa.Integer(), nullable=True))
        b.create_index(b.f('ix_productos_familia_etiquetado_id'), ['familia_etiquetado_id'], unique=False)
        b.create_foreign_key('fk_productos_familia_etiquetado_id', 'familias_etiquetado', ['familia_etiquetado_id'], ['id'])
        b.create_foreign_key('fk_productos_familia_etiquetado_id_org', 'familias_etiquetado',
                             ['familia_etiquetado_id', 'organizacion_id'], ['id', 'organizacion_id'])

    # Padres nuevos de llaves de coherencia
    for tabla in ('tipos_empaque',):
        insp = sa.inspect(con)
        if f'uq_{tabla}_id_org' not in {u["name"] for u in insp.get_unique_constraints(tabla)}:
            with op.batch_alter_table(tabla, schema=None) as b:
                b.create_unique_constraint(f'uq_{tabla}_id_org', ['id', 'organizacion_id'])

    # ---- Usos de diseño --------------------------------------------------------------------------
    op.create_table('usos_diseno',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo_etiqueta_id', sa.Integer(), nullable=False),
    sa.Column('plantilla_id', sa.Integer(), nullable=False),
    sa.Column('nivel', sa.String(length=12), nullable=False),
    sa.Column('familia_id', sa.Integer(), nullable=True),
    sa.Column('producto_id', sa.Integer(), nullable=True),
    sa.Column('articulo_id', sa.Integer(), nullable=True),
    sa.Column('tipo_empaque_id', sa.Integer(), nullable=True),
    sa.Column('celda', sa.String(length=60), nullable=False),
    sa.Column('contexto_tipo', sa.String(length=14), nullable=False),
    sa.Column('contexto_valores', sa.JSON(), nullable=False),
    sa.Column('oc_id', sa.Integer(), nullable=True),
    sa.Column('condiciones', sa.JSON(), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=True),
    sa.Column('vigente_hasta', sa.Date(), nullable=True),
    sa.Column('motivo', sa.String(length=300), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=True),
    sa.Column('creado_en', sa.DateTime(), nullable=False),
    sa.Column('actualizado_por', sa.Integer(), nullable=True),
    sa.Column('actualizado_en', sa.DateTime(), nullable=True),
    sa.Column('eliminado_por', sa.Integer(), nullable=True),
    sa.Column('eliminado_en', sa.DateTime(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    *_org('usos_diseno'),
    sa.ForeignKeyConstraint(['tipo_etiqueta_id'], ['tipos_etiqueta.id'], name='fk_usos_diseno_tipo_etiqueta_id_tipos_etiqueta'),
    sa.ForeignKeyConstraint(['plantilla_id'], ['plantillas_etiqueta.id'], name='fk_usos_diseno_plantilla_id_plantillas_etiqueta'),
    sa.ForeignKeyConstraint(['familia_id'], ['familias_etiquetado.id'], name='fk_usos_diseno_familia_id_familias_etiquetado'),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], name='fk_usos_diseno_producto_id_productos'),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], name='fk_usos_diseno_articulo_id_articulos'),
    sa.ForeignKeyConstraint(['tipo_empaque_id'], ['tipos_empaque.id'], name='fk_usos_diseno_tipo_empaque_id_tipos_empaque'),
    sa.ForeignKeyConstraint(['oc_id'], ['ordenes_compra.id'], name='fk_usos_diseno_oc_id_ordenes_compra'),
    sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id'], name='fk_usos_diseno_creado_por_usuarios'),
    sa.ForeignKeyConstraint(['actualizado_por'], ['usuarios.id'], name='fk_usos_diseno_actualizado_por_usuarios'),
    sa.ForeignKeyConstraint(['eliminado_por'], ['usuarios.id'], name='fk_usos_diseno_eliminado_por_usuarios'),
    *[sa.ForeignKeyConstraint([col, 'organizacion_id'], [f'{padre}.id', f'{padre}.organizacion_id'], name=f'fk_usos_diseno_{col}_org')
      for col, padre in (('tipo_etiqueta_id', 'tipos_etiqueta'), ('plantilla_id', 'plantillas_etiqueta'),
                         ('familia_id', 'familias_etiquetado'), ('producto_id', 'productos'),
                         ('articulo_id', 'articulos'), ('tipo_empaque_id', 'tipos_empaque'), ('oc_id', 'ordenes_compra'))],
    sa.PrimaryKeyConstraint('id', name='pk_usos_diseno'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_usos_diseno_id_org'),
    sa.CheckConstraint("nivel IN ('SKU', 'PRODUCTO', 'FAMILIA', 'TIPO_EMPAQUE', 'GENERAL')", name='ck_usos_diseno_nivel'),
    sa.CheckConstraint("contexto_tipo IN ('NINGUNO', 'OC', 'CENTRO_DESTINO', 'PAIS_DESTINO', 'SOCIEDAD', 'PROVEEDOR', 'CONDICION')",
                       name='ck_usos_diseno_contexto_tipo'),
    sa.CheckConstraint(
        "(nivel = 'GENERAL' AND familia_id IS NULL AND producto_id IS NULL AND articulo_id IS NULL AND tipo_empaque_id IS NULL)"
        " OR (nivel = 'FAMILIA' AND familia_id IS NOT NULL AND producto_id IS NULL AND articulo_id IS NULL"
        " AND tipo_empaque_id IS NULL)"
        " OR (nivel = 'PRODUCTO' AND producto_id IS NOT NULL AND familia_id IS NULL AND articulo_id IS NULL"
        " AND tipo_empaque_id IS NULL)"
        " OR (nivel = 'SKU' AND articulo_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL"
        " AND tipo_empaque_id IS NULL)"
        " OR (nivel = 'TIPO_EMPAQUE' AND tipo_empaque_id IS NOT NULL AND familia_id IS NULL AND producto_id IS NULL"
        " AND articulo_id IS NULL)", name='ck_usos_diseno_destino'),
    sa.CheckConstraint("(contexto_tipo = 'OC') = (oc_id IS NOT NULL)", name='ck_usos_diseno_oc'),
    sa.CheckConstraint("contexto_tipo <> 'NINGUNO' OR (vigente_desde IS NULL AND vigente_hasta IS NULL)",
                       name='ck_usos_diseno_normal_sin_vigencia'),
    sa.CheckConstraint("vigente_hasta IS NULL OR vigente_desde IS NULL OR vigente_hasta >= vigente_desde",
                       name='ck_usos_diseno_vigencia'),
    )
    with op.batch_alter_table('usos_diseno', schema=None) as b:
        for col in ('organizacion_id', 'tipo_etiqueta_id', 'plantilla_id', 'familia_id', 'producto_id', 'articulo_id',
                    'tipo_empaque_id', 'oc_id', 'eliminado_en'):
            b.create_index(b.f(f'ix_usos_diseno_{col}'), [col], unique=False)
        b.create_index('ix_usos_diseno_celda', ['celda'], unique=False)
    op.create_index('uq_usos_diseno_normal', 'usos_diseno', ['organizacion_id', 'celda'], unique=True,
                    sqlite_where=sa.text("contexto_tipo = 'NINGUNO' AND eliminado_en IS NULL"),
                    postgresql_where=sa.text("contexto_tipo = 'NINGUNO' AND eliminado_en IS NULL"))

    _convertir_reglas(con, tipo_plantilla, sujeto_tipo, ahora)

    # ---- Registros de trabajos e ítems generados ---------------------------------------------
    with op.batch_alter_table('trabajo_etiqueta_registros', schema=None) as b:
        b.add_column(sa.Column('tipo_etiqueta_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('uso_id', sa.Integer(), nullable=True))
    uso_de_regla = {d["regla"]: uid for uid, d in _usos_migrados(con)}
    for rid, regla_id, plantilla_id in con.execute(sa.text(
            "SELECT id, regla_id, plantilla_id FROM trabajo_etiqueta_registros")).all():
        con.execute(sa.text("UPDATE trabajo_etiqueta_registros SET uso_id = :u, tipo_etiqueta_id = :t WHERE id = :i"),
                    {"u": uso_de_regla.get(regla_id), "t": tipo_plantilla.get(plantilla_id), "i": rid})
    _quitar_columnas('trabajo_etiqueta_registros', ['regla_id'])
    with op.batch_alter_table('trabajo_etiqueta_registros', schema=None) as b:
        b.create_index(b.f('ix_trabajo_etiqueta_registros_tipo_etiqueta_id'), ['tipo_etiqueta_id'], unique=False)
        b.create_index(b.f('ix_trabajo_etiqueta_registros_uso_id'), ['uso_id'], unique=False)
        b.create_foreign_key('fk_trabajo_etiqueta_registros_tipo_etiqueta_id_tipos_etiqueta', 'tipos_etiqueta',
                             ['tipo_etiqueta_id'], ['id'])
        b.create_foreign_key('fk_trabajo_etiqueta_registros_uso_id_usos_diseno', 'usos_diseno', ['uso_id'], ['id'],
                             ondelete='SET NULL')
        b.create_foreign_key('fk_trabajo_etiqueta_registros_tipo_etiqueta_id_org', 'tipos_etiqueta',
                             ['tipo_etiqueta_id', 'organizacion_id'], ['id', 'organizacion_id'])
        b.create_foreign_key('fk_trabajo_etiqueta_registros_uso_id_org', 'usos_diseno',
                             ['uso_id', 'organizacion_id'], ['id', 'organizacion_id'])

    with op.batch_alter_table('generacion_items', schema=None) as b:
        b.add_column(sa.Column('tipo_etiqueta_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('pl_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('grupo_cajas_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('bulto_indice', sa.Integer(), nullable=True))
    for pid, tid in tipo_plantilla.items():
        con.execute(sa.text("UPDATE generacion_items SET tipo_etiqueta_id = :t WHERE plantilla_id = :p"), {"t": tid, "p": pid})
    with op.batch_alter_table('generacion_items', schema=None) as b:
        for col in ('tipo_etiqueta_id', 'pl_id', 'grupo_cajas_id'):
            b.create_index(b.f(f'ix_generacion_items_{col}'), [col], unique=False)
        b.create_foreign_key('fk_generacion_items_tipo_etiqueta_id_tipos_etiqueta', 'tipos_etiqueta', ['tipo_etiqueta_id'], ['id'])
        b.create_foreign_key('fk_generacion_items_pl_id_packing_lists', 'packing_lists', ['pl_id'], ['id'])
        b.create_foreign_key('fk_generacion_items_grupo_cajas_id_grupos_cajas', 'grupos_cajas', ['grupo_cajas_id'], ['id'],
                             ondelete='SET NULL')
        b.create_foreign_key('fk_generacion_items_tipo_etiqueta_id_org', 'tipos_etiqueta',
                             ['tipo_etiqueta_id', 'organizacion_id'], ['id', 'organizacion_id'])
        b.create_foreign_key('fk_generacion_items_pl_id_org', 'packing_lists', ['pl_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
        b.create_foreign_key('fk_generacion_items_grupo_cajas_id_org', 'grupos_cajas', ['grupo_cajas_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])

    _quitar_columnas('generaciones_etiqueta', ['modalidad', 'unidad'])

    # ---- Diseños: tipo en lugar de modalidad, unidad y familia ----------------------------------
    _quitar_columnas('plantillas_etiqueta', ['modalidad', 'unidad', 'familia_id'])
    with op.batch_alter_table('plantillas_etiqueta', schema=None) as b:
        b.alter_column('tipo_etiqueta_id', existing_type=sa.Integer(), nullable=False)
        b.create_index(b.f('ix_plantillas_etiqueta_tipo_etiqueta_id'), ['tipo_etiqueta_id'], unique=False)
        b.create_foreign_key('fk_plantillas_etiqueta_tipo_etiqueta_id_tipos_etiqueta', 'tipos_etiqueta', ['tipo_etiqueta_id'], ['id'])
        b.create_foreign_key('fk_plantillas_etiqueta_tipo_etiqueta_id_org', 'tipos_etiqueta',
                             ['tipo_etiqueta_id', 'organizacion_id'], ['id', 'organizacion_id'])

    # ---- Campos lógicos: modalidades → sujetos ---------------------------------------------------
    with op.batch_alter_table('campos_etiqueta', schema=None) as b:
        b.add_column(sa.Column('sujetos', sa.JSON(), nullable=True))
    a_sujetos = {"ARTICULO": {"ARTICULO"}, "OC_ARTICULO": {"ARTICULO", "BULTO"}, "OC": {"DOCUMENTO", "BULTO"}}
    for cid, modalidades in con.execute(sa.text("SELECT id, modalidades FROM campos_etiqueta")).all():
        sujetos = sorted(set().union(*[a_sujetos.get(m, set()) for m in _json(modalidades, [])]) or set())
        con.execute(sa.text("UPDATE campos_etiqueta SET sujetos = :s WHERE id = :i"), {"s": json.dumps(sujetos), "i": cid})
    with op.batch_alter_table('campos_etiqueta', schema=None) as b:
        b.alter_column('sujetos', existing_type=sa.JSON(), nullable=False)
        b.drop_column('modalidades')

    op.drop_table('asignaciones_etiqueta')
    rls(op, 'tipos_etiqueta', 'usos_diseno')
    _permisos(con, "etiquetas.asignar", "etiquetas.configurar")


def _usos_migrados(con) -> list[tuple[int, dict]]:
    """(uso, detalle) de las conversiones guardadas en el historial."""
    return [(uid, _json(d, {})) for uid, d in con.execute(sa.text(
        "SELECT entidad_id, detalle FROM historial WHERE entidad = 'uso_diseno' AND accion = 'migrar' ORDER BY id")).all()]


def _convertir_reglas(con, tipo_plantilla: dict, sujeto_tipo: dict, ahora: datetime) -> None:
    reglas = con.execute(sa.text(
        "SELECT id, organizacion_id, plantilla_id, ambito, familia_id, producto_id, articulo_id, oc_id, predeterminada, activa,"
        " motivo, creada_por, creada_en, nombre, prioridad, condiciones, contexto, vigente_desde, vigente_hasta,"
        " actualizada_por, actualizada_en FROM asignaciones_etiqueta ORDER BY id")).mappings().all()
    empaques = {(o, c): i for i, o, c in con.execute(sa.text("SELECT id, organizacion_id, codigo FROM tipos_empaque")).all()}
    nuevos = []  # dict con los datos del uso y de dónde salió
    for r in reglas:
        tipo = tipo_plantilla.get(r["plantilla_id"])
        sujeto = sujeto_tipo.get(tipo)
        condiciones = _json(r["condiciones"], [])
        contexto = _json(r["contexto"], {})
        base = {"organizacion_id": r["organizacion_id"], "tipo_etiqueta_id": tipo, "plantilla_id": r["plantilla_id"],
                "condiciones": condiciones, "vigente_desde": r["vigente_desde"], "vigente_hasta": r["vigente_hasta"],
                "motivo": r["motivo"], "creado_por": r["creada_por"], "creado_en": r["creada_en"] or ahora,
                "actualizado_por": r["actualizada_por"], "actualizado_en": r["actualizada_en"], "oc_id": None,
                "nivel": "GENERAL", "destino": {}, "contexto_tipo": "NINGUNO", "baja": None, "notas": [],
                "regla": {"id": r["id"], "nombre": r["nombre"], "ambito": r["ambito"], "prioridad": r["prioridad"],
                          "predeterminada": bool(r["predeterminada"]), "contexto": contexto, "activa": bool(r["activa"])}}
        ambito = r["ambito"]
        destinos = {"FAMILIA": ("FAMILIA", "familia_id", r["familia_id"]), "PRODUCTO": ("PRODUCTO", "producto_id", r["producto_id"]),
                    "ARTICULO": ("SKU", "articulo_id", r["articulo_id"])}
        if ambito in destinos:
            if sujeto != "ARTICULO":
                que = {"BULTO": "package", "DOCUMENTO": "document"}.get(sujeto, "label")
                donde = {"FAMILIA": "labeling family", "PRODUCTO": "product", "ARTICULO": "item"}[ambito]
                base["baja"] = (f"A {que} label cannot depend on a {donde}: "
                                "add an exception with a condition if it is still needed.")
            nivel, col, valor = destinos[ambito]
            base["nivel"], base["destino"] = nivel, {col: valor}
        elif ambito == "OC":
            base["contexto_tipo"], base["oc_id"] = "OC", r["oc_id"]
        if not r["activa"]:
            base["baja"] = base["baja"] or "The rule was inactive."
        if any(contexto.get(k) for k in ("origenes", "unidades", "modalidades")):
            base["notas"].append("The origin, unit or data mode of the rule no longer exist: the design applies to every origin.")
        codigos = contexto.get("tipos_empaque") or []
        variantes = [base]
        if codigos:
            if sujeto == "BULTO" and base["nivel"] == "GENERAL":
                variantes = []
                for codigo in codigos:
                    eid = empaques.get((r["organizacion_id"], codigo))
                    v = {**base, "notas": list(base["notas"])}
                    if eid is None:
                        v["baja"] = v["baja"] or f"The package type {codigo} does not exist."
                    else:
                        v["nivel"], v["destino"] = "TIPO_EMPAQUE", {"tipo_empaque_id": eid}
                    variantes.append(v)
            else:
                base["notas"].append(f"The rule was limited to package types {', '.join(codigos)}: the limit no longer applies.")
        for v in variantes:
            if v["contexto_tipo"] == "NINGUNO" and (v["condiciones"] or v["vigente_desde"] or v["vigente_hasta"]
                                                      or ambito == "REGLA" and v["condiciones"]):
                v["contexto_tipo"] = "CONDICION"
            nuevos.append(v)

    # Un solo diseño normal por celda: el de mayor prioridad, luego el predeterminado, luego el más antiguo
    def celda(v):
        dest = next(iter(v["destino"].values()), None)
        return f"{v['tipo_etiqueta_id']}:{v['nivel']}:{dest or 0}"

    normales: dict = {}
    for v in nuevos:
        if v["contexto_tipo"] == "NINGUNO" and not v["baja"]:
            normales.setdefault((v["organizacion_id"], celda(v)), []).append(v)
    for lista in normales.values():
        lista.sort(key=lambda v: (-v["regla"]["prioridad"], not v["regla"]["predeterminada"], v["regla"]["id"]))
        for v in lista[1:]:
            v["baja"] = (f"Several rules gave a design to the same place; the one with the highest priority stays "
                         f"(rule {lista[0]['regla']['id']}).")

    for v in nuevos:
        motivo = v["motivo"] or (f"Converted from the rule «{v['regla']['nombre']}»." if v["regla"]["nombre"] else None)
        if v["contexto_tipo"] == "OC" and not motivo:
            motivo = "Exception of the purchase order (converted)."
        uid = con.execute(sa.text(
            "INSERT INTO usos_diseno (organizacion_id, tipo_etiqueta_id, plantilla_id, nivel, familia_id, producto_id,"
            " articulo_id, tipo_empaque_id, celda, contexto_tipo, contexto_valores, oc_id, condiciones, vigente_desde,"
            " vigente_hasta, motivo, creado_por, creado_en, actualizado_por, actualizado_en, eliminado_en, version)"
            " VALUES (:organizacion_id, :tipo_etiqueta_id, :plantilla_id, :nivel, :familia_id, :producto_id,"
            " :articulo_id, :tipo_empaque_id, :celda, :contexto_tipo, :contexto_valores, :oc_id, :condiciones, :vigente_desde,"
            " :vigente_hasta, :motivo, :creado_por, :creado_en, :actualizado_por, :actualizado_en, :eliminado_en, 1)"
            " RETURNING id"),
            {"organizacion_id": v["organizacion_id"], "tipo_etiqueta_id": v["tipo_etiqueta_id"], "plantilla_id": v["plantilla_id"],
             "nivel": v["nivel"], "familia_id": v["destino"].get("familia_id"),
             "producto_id": v["destino"].get("producto_id"), "articulo_id": v["destino"].get("articulo_id"),
             "tipo_empaque_id": v["destino"].get("tipo_empaque_id"), "celda": celda(v), "contexto_tipo": v["contexto_tipo"],
             "contexto_valores": "[]", "oc_id": v["oc_id"], "condiciones": json.dumps(v["condiciones"]),
             "vigente_desde": v["vigente_desde"] if v["contexto_tipo"] != "NINGUNO" else None,
             "vigente_hasta": v["vigente_hasta"] if v["contexto_tipo"] != "NINGUNO" else None,
             "motivo": (motivo or "")[:300] or None, "creado_por": v["creado_por"], "creado_en": v["creado_en"],
             "actualizado_por": v["actualizado_por"], "actualizado_en": v["actualizado_en"],
             "eliminado_en": ahora if v["baja"] else None}).scalar()
        detalle = {"regla": v["regla"]["id"], "nombre": v["regla"]["nombre"], "ambito": v["regla"]["ambito"],
                   "prioridad": v["regla"]["prioridad"], "resultado": "baja" if v["baja"] else "convertida",
                   "nivel": v["nivel"], "contexto_tipo": v["contexto_tipo"], "motivo_baja": v["baja"], "notas": v["notas"]}
        _historial(con, v["organizacion_id"], uid, detalle)
        if v["baja"] or v["notas"]:
            log.warning("Regla %s → uso %s: %s %s", v["regla"]["id"], uid, v["baja"] or "", " ".join(v["notas"]))


def downgrade() -> None:
    con = op.get_bind()
    tipos = {i: (s, q) for i, s, q in con.execute(sa.text("SELECT id, sujeto, cantidad FROM tipos_etiqueta")).all()}
    a_unidad = {"POR_UNIDAD": "UNIDAD", "POR_LINEA": "LINEA", "POR_ARTICULO": "ARTICULO", "MANUAL": "MANUAL",
                "POR_BULTO": "BULTO", "POR_DOCUMENTO": "ORDEN"}

    def modalidad(tid):
        s, q = tipos.get(tid, ("ARTICULO", "POR_LINEA"))
        return ("OC" if s == "DOCUMENTO" else "OC_ARTICULO" if s == "BULTO" else "OC_ARTICULO" if q != "POR_UNIDAD" else "ARTICULO",
                a_unidad[q])

    with op.batch_alter_table('plantillas_etiqueta', schema=None) as b:
        b.add_column(sa.Column('modalidad', sa.String(length=12), nullable=True))
        b.add_column(sa.Column('unidad', sa.String(length=10), nullable=True))
        b.add_column(sa.Column('familia_id', sa.Integer(), nullable=True))
    for pid, tid in con.execute(sa.text("SELECT id, tipo_etiqueta_id FROM plantillas_etiqueta")).all():
        m, u = modalidad(tid)
        con.execute(sa.text("UPDATE plantillas_etiqueta SET modalidad = :m, unidad = :u WHERE id = :i"), {"m": m, "u": u, "i": pid})
    _quitar_columnas('plantillas_etiqueta', ['tipo_etiqueta_id'])
    with op.batch_alter_table('plantillas_etiqueta', schema=None) as b:
        b.alter_column('modalidad', existing_type=sa.String(length=12), nullable=False)
        b.alter_column('unidad', existing_type=sa.String(length=10), nullable=False)
        b.create_index(b.f('ix_plantillas_etiqueta_familia_id'), ['familia_id'], unique=False)
        b.create_foreign_key('fk_plantillas_etiqueta_familia_id_familias_etiquetado', 'familias_etiquetado', ['familia_id'], ['id'])
        b.create_foreign_key('fk_plantillas_etiqueta_familia_id_org', 'familias_etiquetado', ['familia_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
        b.create_check_constraint('ck_plantillas_etiqueta_modalidad', "modalidad IN ('ARTICULO', 'OC', 'OC_ARTICULO')")
        b.create_check_constraint('ck_plantillas_etiqueta_unidad',
                                  "unidad IN ('ORDEN', 'LINEA', 'ARTICULO', 'UNIDAD', 'BULTO', 'MANUAL')")

    op.create_table('asignaciones_etiqueta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('plantilla_id', sa.Integer(), nullable=False),
    sa.Column('ambito', sa.String(length=10), nullable=False),
    sa.Column('familia_id', sa.Integer(), nullable=True),
    sa.Column('producto_id', sa.Integer(), nullable=True),
    sa.Column('articulo_id', sa.Integer(), nullable=True),
    sa.Column('oc_id', sa.Integer(), nullable=True),
    sa.Column('predeterminada', sa.Boolean(), nullable=False),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('motivo', sa.String(length=300), nullable=True),
    sa.Column('creada_por', sa.Integer(), nullable=True),
    sa.Column('creada_en', sa.DateTime(), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=True),
    sa.Column('prioridad', sa.Integer(), server_default='100', nullable=False),
    sa.Column('condiciones', sa.JSON(), nullable=False),
    sa.Column('contexto', sa.JSON(), nullable=False),
    sa.Column('vigente_desde', sa.Date(), nullable=True),
    sa.Column('vigente_hasta', sa.Date(), nullable=True),
    sa.Column('actualizada_por', sa.Integer(), nullable=True),
    sa.Column('actualizada_en', sa.DateTime(), nullable=True),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    *_org('asignaciones_etiqueta'),
    sa.ForeignKeyConstraint(['plantilla_id'], ['plantillas_etiqueta.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['familia_id'], ['familias_etiquetado.id']),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id']),
    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id']),
    sa.ForeignKeyConstraint(['oc_id'], ['ordenes_compra.id']),
    sa.ForeignKeyConstraint(['creada_por'], ['usuarios.id']),
    sa.PrimaryKeyConstraint('id', name='pk_asignaciones_etiqueta'),
    sa.UniqueConstraint('id', 'organizacion_id', name='uq_asignaciones_etiqueta_id_org'),
    )
    a_ambito = {"GENERAL": "GENERAL", "FAMILIA": "FAMILIA", "PRODUCTO": "PRODUCTO", "SKU": "ARTICULO"}
    for u in con.execute(sa.text("SELECT * FROM usos_diseno WHERE eliminado_en IS NULL ORDER BY id")).mappings().all():
        ambito = "OC" if u["contexto_tipo"] == "OC" else a_ambito.get(u["nivel"], "REGLA")
        con.execute(sa.text(
            "INSERT INTO asignaciones_etiqueta (organizacion_id, plantilla_id, ambito, familia_id, producto_id, articulo_id, oc_id,"
            " predeterminada, activa, motivo, creada_por, creada_en, nombre, prioridad, condiciones, contexto, vigente_desde,"
            " vigente_hasta, version) VALUES (:o, :p, :a, :f, :pr, :ar, :oc, :pd, :ac, :m, :cp, :ce, NULL, :pri, :c, '{}', :vd,"
            " :vh, 1)"),
            {"o": u["organizacion_id"], "p": u["plantilla_id"], "a": ambito,
             "f": u["familia_id"] if ambito == "FAMILIA" else None, "pr": u["producto_id"] if ambito == "PRODUCTO" else None,
             "ar": u["articulo_id"] if ambito == "ARTICULO" else None, "oc": u["oc_id"] if ambito == "OC" else None,
             "pd": False, "ac": True, "m": u["motivo"], "cp": u["creado_por"], "ce": u["creado_en"],
             "pri": PRIORIDAD_NIVEL["OC" if ambito == "OC" else u["nivel"]], "c": json.dumps(_json(u["condiciones"], [])),
             "vd": u["vigente_desde"], "vh": u["vigente_hasta"]})

    with op.batch_alter_table('campos_etiqueta', schema=None) as b:
        b.add_column(sa.Column('modalidades', sa.JSON(), nullable=True))
    op.execute("UPDATE campos_etiqueta SET modalidades = '[]'")
    with op.batch_alter_table('campos_etiqueta', schema=None) as b:
        b.alter_column('modalidades', existing_type=sa.JSON(), nullable=False)
        b.drop_column('sujetos')

    with op.batch_alter_table('generaciones_etiqueta', schema=None) as b:
        b.add_column(sa.Column('modalidad', sa.String(length=12), nullable=True))
        b.add_column(sa.Column('unidad', sa.String(length=10), nullable=True))
    op.execute("UPDATE generaciones_etiqueta SET modalidad = 'OC_ARTICULO', unidad = 'LINEA'")
    with op.batch_alter_table('generaciones_etiqueta', schema=None) as b:
        b.alter_column('modalidad', existing_type=sa.String(length=12), nullable=False)
        b.alter_column('unidad', existing_type=sa.String(length=10), nullable=False)

    _quitar_columnas('generacion_items', ['tipo_etiqueta_id', 'pl_id', 'grupo_cajas_id', 'bulto_indice'])
    with op.batch_alter_table('trabajo_etiqueta_registros', schema=None) as b:
        b.add_column(sa.Column('regla_id', sa.Integer(), nullable=True))
    _quitar_columnas('trabajo_etiqueta_registros', ['tipo_etiqueta_id', 'uso_id'])
    with op.batch_alter_table('trabajo_etiqueta_registros', schema=None) as b:
        b.create_index(b.f('ix_trabajo_etiqueta_registros_regla_id'), ['regla_id'], unique=False)
        b.create_foreign_key('fk_trabajo_etiqueta_registros_regla_id_asignaciones_etiqueta', 'asignaciones_etiqueta',
                             ['regla_id'], ['id'], ondelete='SET NULL')

    rls(op, 'asignaciones_etiqueta')
    op.drop_table('usos_diseno')
    op.execute("DELETE FROM historial WHERE entidad = 'uso_diseno'")
    _quitar_columnas('productos', ['familia_etiquetado_id'])
    op.drop_table('tipos_etiqueta')
    _permisos(con, "etiquetas.configurar", "etiquetas.asignar")
