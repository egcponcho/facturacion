"""Productos y variantes genéricos: lo que no es de todos los rubros pasa a
ser atributo, código o componente

Antes la variante (articulos) guardaba datos de un rubro (estilo, color,
talla, marca, grupo, prepack, upc, código del proveedor) y había tres
clasificaciones paralelas (grupos de artículos, categorías de artículo y la
familia). Ahora:

- atributos (antes atributos_variante): cada atributo es del PRODUCTO (marca,
  modelo, material…) o de la VARIANTE (talla, color, sabor, presentación…),
  con su tipo (texto, número, opción, fecha, sí/no o un registro de un
  catálogo: la marca apunta a «marcas»). Mismos ids.
- producto_atributos: los valores de los atributos de producto. Se crean el
  atributo MODELO (desde estilo) y MARCA (catálogo «marcas», desde marca_id)
  solo en las empresas que los usaban.
- articulo_codigos: los códigos de la variante, varios por variante: BARRAS
  (desde upc), PROVEEDOR (desde sku_proveedor, con su proveedor) y PACK (el
  identificador de un pack, desde el prepack).
- articulo_componentes: el contenido de un pack o un kit (desde
  prepack_componentes); el compuesto es la variante misma.
- escalas_valores (antes escalas_talla): escalas de cualquier atributo; la
  regla TALLA se llama VALOR y la categoría de artículo desaparece.
- La familia del producto es la única clasificación: el producto sin familia
  toma la de su grupo de artículos (o la de sus variantes). Los días extra del
  grupo pasan a la familia (el mayor si varios grupos comparten familia); un
  grupo con días extra y sin familia se vuelve una familia.
- productos.proveedor_id se completa con el de sus variantes; articulos.producto_id
  pasa a ser obligatorio (una variante sin producto recibe uno con su código).
- Líneas de OC y de factura: codigo_barras, codigo_pack y atributos (foto de
  los atributos del producto: MARCA, MODELO); la variante ya tenía su foto.
- Campos propios de artículos → atributos de variante con sus valores.
- Claves de los campos en diseños de etiqueta, reglas de etiquetado y de
  empaque, campos lógicos, campos exigidos por las familias y nombres propios
  de campos: articulo.upc → articulo.codigo_barras, articulo.talla →
  articulo.atributo.TALLA, articulo.estilo → producto.dato.MODELO,
  articulo.marca → producto.marca, linea.color → linea.atributo.COLOR… (y las
  columnas talla/color/upc de las tablas de las etiquetas). Los grupos de
  artículos y las categorías dejan de existir: sus claves quedan sin valor.
- Datos obligatorios de la empresa para artículos y columnas de las líneas de
  sus documentos: upc → codigo_barras, sku_proveedor → codigo_proveedor,
  marca_id/estilo/color/talla → atributo.<código>.

Se borran: grupos_articulos, categorias_articulo, prepacks,
prepack_componentes, familias_etiquetado y categorias_etiquetado (congeladas
desde 0081), las columnas de rubro de articulos, productos y líneas, y las
referencias congeladas de usos_diseno, generacion_items y grupos_producto.

Todo lo borrado se guarda antes en respaldos_migracion (filas y valores tal
como estaban). La vuelta atrás recrea la estructura anterior, devuelve lo
respaldado y completa lo creado después con los datos nuevos (códigos,
atributos y producto de cada variante).

Revision ID: 0092
Revises: 0091
Create Date: 2026-10-22 12:16:39
"""
import json
import re
from datetime import date, datetime

import sqlalchemy as sa

from alembic import op
from app.instalacion.esquema import rls, sin_violaciones

revision = '0092'
down_revision = '0091'
branch_labels = None
depends_on = None

# Lo que se retira (se respalda antes)
TABLAS_BORRADAS = ('escalas_talla', 'prepack_componentes', 'prepacks', 'grupos_articulos', 'categorias_articulo',
                   'categorias_etiquetado', 'familias_etiquetado', 'atributos_variante')
COLUMNAS_BORRADAS = {
    'articulos': ('generico', 'sku_proveedor', 'upc', 'estilo', 'color', 'talla', 'marca_id', 'grupo_id', 'proveedor_id',
                  'prepack_id', 'extra', 'familia_etiquetado_id', 'grupo_producto_id'),
    'productos': ('estilo', 'color', 'marca_id', 'grupo_id', 'familia_etiquetado_id', 'categoria_etiquetado_id'),
    'posiciones_oc': ('upc', 'estilo', 'color', 'talla', 'marca', 'grupo', 'categoria', 'prepack'),
    'factura_lineas': ('upc', 'estilo', 'color', 'talla', 'marca', 'categoria', 'prepack'),
    'grupos_producto': ('legado_familia_id', 'legado_categoria_id'),
    'usos_diseno': ('familia_id', 'categoria_id'),
    'generacion_items': ('familia_id',),
}
OBLIGATORIOS = {'upc': 'codigo_barras', 'sku_proveedor': 'codigo_proveedor'}
NUEVAS = ('atributos', 'producto_atributos', 'articulo_codigos', 'articulo_componentes', 'escalas_valores')
# JSON que guardan claves de campos (diseños, condiciones, campos exigidos, configuración)
CON_CLAVES = (('versiones_plantilla', 'diseno'), ('usos_diseno', 'condiciones'), ('campos_etiqueta', 'fuentes'),
              ('grupos_producto', 'campos'), ('grupos_producto', 'condiciones'), ('reglas_empaque', 'condiciones'),
              ('organizaciones', 'configuracion'))
# SQLite no nombra las llaves foráneas declaradas en la columna: batch les da este nombre
CONVENCION = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


# ---- Ayudas ---------------------------------------------------------------------------------------
def _sqlite() -> bool:
    return op.get_bind().dialect.name == 'sqlite'


def _texto(v):
    """Valor guardable en JSON (fechas como texto ISO)."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v if v is None or isinstance(v, (int, float, str, bool, list, dict)) else str(v)


def _tabla(con, nombre: str) -> sa.Table:
    return sa.Table(nombre, sa.MetaData(), autoload_with=con)


def _respaldar(con, tabla: str, columnas: tuple[str, ...] | None = None) -> None:
    """Guarda las filas (o los valores no vacíos de esas columnas) en respaldos_migracion."""
    t = _tabla(con, tabla)
    cols = [t.c[c] for c in (columnas or [c.name for c in t.columns])]
    consulta = sa.select(t.c.id, *cols)
    if columnas:
        consulta = consulta.where(sa.or_(*[c.is_not(None) for c in cols]))
    filas = [{'migracion': revision, 'tabla': tabla, 'fila_id': f.id, 'creado_en': datetime.utcnow(),
              'datos': {c.name: _texto(f._mapping[c.name]) for c in cols}} for f in con.execute(consulta)]
    if filas:
        con.execute(_tabla(con, 'respaldos_migracion').insert(), filas)


def _respaldo(con, tabla: str) -> list[dict]:
    if not sa.inspect(con).has_table('respaldos_migracion'):
        return []
    t = _tabla(con, 'respaldos_migracion')
    return [{**(f.datos if isinstance(f.datos, dict) else json.loads(f.datos)), '_id': f.fila_id} for f in
            con.execute(sa.select(t.c.fila_id, t.c.datos).where(t.c.migracion == revision, t.c.tabla == tabla).order_by(t.c.id))]


def _tipado(t: sa.Table, fila: dict) -> dict:
    """Los valores respaldados con el tipo de su columna (fechas, JSON)."""
    res = {}
    for k, v in fila.items():
        if k not in t.c:
            continue
        tipo = t.c[k].type
        if v is not None and isinstance(tipo, sa.DateTime) and isinstance(v, str):
            v = datetime.fromisoformat(v)
        elif v is not None and isinstance(tipo, sa.Date) and isinstance(v, str):
            v = date.fromisoformat(v[:10])
        res[k] = v
    return res


def _quitar_columnas(tabla: str, columnas: tuple[str, ...]) -> None:
    """Borra columnas con sus índices; sus llaves foráneas se van con ellas."""
    con = op.get_bind()
    insp = sa.inspect(con)
    indices = [i['name'] for i in insp.get_indexes(tabla) if set(i['column_names']) & set(columnas)]
    with op.batch_alter_table(tabla, schema=None) as b:
        for i in indices:
            b.drop_index(i)
        for c in columnas:
            b.drop_column(c)


def _nombre_fk(con, tabla: str, columna: str, referida: str) -> str:
    for fk in sa.inspect(con).get_foreign_keys(tabla):
        if fk['constrained_columns'] == [columna] and fk['referred_table'] == referida:
            return fk['name'] or CONVENCION['fk'] % {'table_name': tabla, 'column_0_name': columna,
                                                     'referred_table_name': referida}
    raise RuntimeError(f'{tabla}.{columna} no tiene llave foránea a {referida}')


def _cambiar_fk(tabla: str, columna: str, antes: str, despues: str, nombre: str, coherencia: bool) -> None:
    """La columna apunta a otra tabla: su llave foránea y la de coherencia de organización."""
    con = op.get_bind()
    viejo = _nombre_fk(con, tabla, columna, antes)
    nombres = {fk['name'] for fk in sa.inspect(con).get_foreign_keys(tabla)}
    with op.batch_alter_table(tabla, schema=None, naming_convention=CONVENCION) as b:
        b.drop_constraint(viejo, type_='foreignkey')
        if f'fk_{tabla}_{columna}_org' in nombres:
            b.drop_constraint(f'fk_{tabla}_{columna}_org', type_='foreignkey')
        b.create_foreign_key(nombre, despues, [columna], ['id'])
        if coherencia:
            b.create_foreign_key(f'fk_{tabla}_{columna}_org', despues, [columna, 'organizacion_id'],
                                 ['id', 'organizacion_id'])


def _org(t: str, *cols: tuple[str, str]) -> list:
    """Llaves de coherencia: el registro referido es de la misma organización."""
    return [sa.ForeignKeyConstraint([c, 'organizacion_id'], [f'{p}.id', f'{p}.organizacion_id'], name=f'fk_{t}_{c}_org')
            for c, p in cols]


def _base(t: str) -> list:
    return [sa.Column('organizacion_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], name=f'fk_{t}_organizacion_id_organizaciones'),
            sa.PrimaryKeyConstraint('id', name=f'pk_{t}')]


def _indices(t: str, *cols: str) -> None:
    for c in ('organizacion_id', *cols):
        op.create_index(f'ix_{t}_{c}', t, [c], unique=False)


def _secuencia(tabla: str) -> None:
    """PostgreSQL: la secuencia del id sigue después de los ids copiados."""
    if not _sqlite():
        op.execute(f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), coalesce((SELECT max(id) FROM {tabla}), 0) + 1, false)")


def _codigo_libre(con, org: int, base: str) -> str:
    usados = set(con.execute(sa.text('SELECT codigo FROM atributos WHERE organizacion_id = :o'), {'o': org}).scalars())
    codigo, n = base, 2
    while codigo in usados:
        codigo, n = f'{base}{n}', n + 1
    return codigo


# ---- Subir ------------------------------------------------------------------------------------------
def upgrade() -> None:
    con = op.get_bind()
    op.create_table('respaldos_migracion',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('migracion', sa.String(length=10), nullable=False),
                    sa.Column('tabla', sa.String(length=60), nullable=False),
                    sa.Column('fila_id', sa.Integer(), nullable=True),
                    sa.Column('datos', sa.JSON(), nullable=False),
                    sa.Column('creado_en', sa.DateTime(), nullable=False),
                    sa.PrimaryKeyConstraint('id', name='pk_respaldos_migracion'))
    op.create_index('ix_respaldos_migracion_migracion', 'respaldos_migracion', ['migracion'], unique=False)
    for t in TABLAS_BORRADAS:
        _respaldar(con, t)
    for t, cols in COLUMNAS_BORRADAS.items():
        _respaldar(con, t, cols)
    _respaldar(con, 'definiciones_campo')
    _respaldar(con, 'organizaciones', ('configuracion',))

    _crear_tablas()
    _copiar_atributos(con)
    _cambiar_fk('articulo_atributos', 'atributo_id', 'atributos_variante', 'atributos',
                'fk_articulo_atributos_atributo_id_atributos', True)
    _productos_de_variantes(con)
    _valores_de_variante(con)
    _valores_de_producto(con)
    _campos_propios(con)
    _codigos(con)
    _componentes(con)
    _familias(con)
    _escalas(con)
    _lineas(con)
    _obligatorios(con)
    _claves_de_campos(con, subir=True)

    # Variante: producto obligatorio, tipo con regla
    sin_violaciones(con, 'articulos', "tipo IN ('SOLIDO', 'PREPACK')", 'tipo SOLIDO o PREPACK')
    viejo = _nombre_fk(con, 'articulos', 'producto_id', 'productos')
    with op.batch_alter_table('articulos', schema=None, naming_convention=CONVENCION) as b:
        b.drop_constraint(viejo, type_='foreignkey')
        b.alter_column('producto_id', existing_type=sa.Integer(), nullable=False)
        b.create_foreign_key('fk_articulos_producto_id', 'productos', ['producto_id'], ['id'])
        b.create_foreign_key('fk_articulos_producto_id_org', 'productos', ['producto_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
        b.create_check_constraint('ck_articulos_tipo', "tipo IN ('SOLIDO', 'PREPACK')")
    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.add_column(sa.Column('dias_extra', sa.Integer(), nullable=True))
    _dias_extra(con)
    with op.batch_alter_table('definiciones_campo', schema=None) as b:
        b.drop_constraint('ck_definiciones_campo_entidad', type_='check')
        b.create_check_constraint('ck_definiciones_campo_entidad', "entidad IN ('proveedores', 'sociedades', 'centros', "
                                  "'marcas', 'transportistas', 'ordenes', 'facturas')")

    # Contraer: columnas y tablas retiradas (ya respaldadas)
    for t, cols in COLUMNAS_BORRADAS.items():
        _quitar_columnas(t, cols)
    for t in TABLAS_BORRADAS:
        op.drop_table(t)
    rls(op, *NUEVAS)


def _crear_tablas() -> None:
    op.create_table('atributos',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=20), nullable=False),
                    sa.Column('nombre', sa.String(length=60), nullable=False),
                    sa.Column('nivel', sa.String(length=10), server_default='VARIANTE', nullable=False),
                    sa.Column('tipo', sa.String(length=10), server_default='texto', nullable=False),
                    sa.Column('opciones', sa.String(length=500), nullable=True),
                    sa.Column('catalogo', sa.String(length=30), nullable=True),
                    sa.Column('unidad', sa.String(length=10), nullable=True),
                    sa.Column('orden', sa.Integer(), nullable=False),
                    sa.Column('activo', sa.Boolean(), nullable=False),
                    *_base('atributos'),
                    sa.CheckConstraint("(tipo = 'catalogo') = (catalogo IS NOT NULL)", name='ck_atributos_catalogo'),
                    sa.CheckConstraint("nivel IN ('PRODUCTO', 'VARIANTE')", name='ck_atributos_nivel'),
                    sa.CheckConstraint("tipo IN ('texto', 'numero', 'opcion', 'fecha', 'bool', 'catalogo')",
                                       name='ck_atributos_tipo'),
                    sa.ForeignKeyConstraint(['organizacion_id', 'unidad'],
                                            ['unidades_medida.organizacion_id', 'unidades_medida.codigo'],
                                            name='fk_atributos_unidad'),
                    sa.UniqueConstraint('id', 'organizacion_id', name='uq_atributos_id_org'),
                    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_atributos_org_codigo'))
    _indices('atributos')
    op.create_table('producto_atributos',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('producto_id', sa.Integer(), nullable=False),
                    sa.Column('atributo_id', sa.Integer(), nullable=False),
                    sa.Column('valor', sa.String(length=200), nullable=False),
                    *_base('producto_atributos'),
                    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ondelete='CASCADE',
                                            name='fk_producto_atributos_producto_id_productos'),
                    sa.ForeignKeyConstraint(['atributo_id'], ['atributos.id'], name='fk_producto_atributos_atributo_id_atributos'),
                    *_org('producto_atributos', ('producto_id', 'productos'), ('atributo_id', 'atributos')),
                    sa.UniqueConstraint('producto_id', 'atributo_id', name='uq_producto_atributos_producto_atributo'))
    _indices('producto_atributos', 'producto_id', 'atributo_id')
    op.create_table('articulo_codigos',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('articulo_id', sa.Integer(), nullable=False),
                    sa.Column('tipo', sa.String(length=10), nullable=False),
                    sa.Column('valor', sa.String(length=60), nullable=False),
                    sa.Column('proveedor_id', sa.Integer(), nullable=True),
                    *_base('articulo_codigos'),
                    sa.CheckConstraint("tipo IN ('BARRAS', 'PROVEEDOR', 'PACK')", name='ck_articulo_codigos_tipo'),
                    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], ondelete='CASCADE',
                                            name='fk_articulo_codigos_articulo_id_articulos'),
                    sa.ForeignKeyConstraint(['proveedor_id'], ['proveedores.id'], name='fk_articulo_codigos_proveedor_id_proveedores'),
                    *_org('articulo_codigos', ('articulo_id', 'articulos'), ('proveedor_id', 'proveedores')),
                    sa.UniqueConstraint('articulo_id', 'tipo', 'valor', name='uq_articulo_codigos_articulo_tipo_valor'))
    _indices('articulo_codigos', 'articulo_id', 'proveedor_id', 'valor')
    op.create_table('articulo_componentes',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('compuesto_id', sa.Integer(), nullable=False),
                    sa.Column('componente_id', sa.Integer(), nullable=False),
                    sa.Column('cantidad', sa.Integer(), nullable=False),
                    *_base('articulo_componentes'),
                    sa.CheckConstraint('cantidad >= 1', name='ck_articulo_componentes_cantidad'),
                    sa.ForeignKeyConstraint(['compuesto_id'], ['articulos.id'], ondelete='CASCADE',
                                            name='fk_articulo_componentes_compuesto_id_articulos'),
                    sa.ForeignKeyConstraint(['componente_id'], ['articulos.id'], name='fk_articulo_componentes_componente_id_articulos'),
                    *_org('articulo_componentes', ('compuesto_id', 'articulos'), ('componente_id', 'articulos')),
                    sa.UniqueConstraint('compuesto_id', 'componente_id', name='uq_articulo_componentes_compuesto_componente'))
    _indices('articulo_componentes', 'compuesto_id', 'componente_id')
    op.create_table('escalas_valores',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=20), nullable=False),
                    sa.Column('nombre', sa.String(length=120), nullable=False),
                    sa.Column('atributo', sa.String(length=20), nullable=False),
                    sa.Column('regla', sa.String(length=15), nullable=False),
                    sa.Column('factor', sa.Integer(), nullable=True),
                    sa.Column('longitud', sa.Integer(), nullable=True),
                    sa.Column('valores', sa.JSON(), nullable=False),
                    sa.Column('activo', sa.Boolean(), nullable=False),
                    *_base('escalas_valores'),
                    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_escalas_valores_org_codigo'))
    _indices('escalas_valores')


def _copiar_atributos(con) -> None:
    """atributos_variante → atributos (de variante), con los mismos ids."""
    con.execute(sa.text("INSERT INTO atributos (id, codigo, nombre, nivel, tipo, opciones, catalogo, unidad, orden, activo, "
                        "organizacion_id) SELECT id, codigo, nombre, 'VARIANTE', tipo, opciones, NULL, unidad, orden, activo, "
                        "organizacion_id FROM atributos_variante"))
    _secuencia('atributos')


def _nuevo_atributo(con, org: int, base: str, nombre: str, nivel: str, orden: int, catalogo: str | None = None,
                    tipo: str = 'texto', opciones: str | None = None) -> int:
    codigo = _codigo_libre(con, org, base)
    t = _tabla(con, 'atributos')
    return con.execute(t.insert().values(codigo=codigo, nombre=nombre, nivel=nivel, tipo='catalogo' if catalogo else tipo,
                                         catalogo=catalogo, opciones=opciones, orden=orden, activo=True,
                                         organizacion_id=org).returning(t.c.id)).scalar_one()


def _productos_de_variantes(con) -> None:
    """Cada variante tiene producto: la que no tenía toma el de su código de producto o uno nuevo."""
    huerfanas = con.execute(sa.text("SELECT id, organizacion_id, coalesce(generico, sku) AS codigo, descripcion, unidad, "
                                    "proveedor_id FROM articulos WHERE producto_id IS NULL ORDER BY id")).all()
    t = _tabla(con, 'productos')
    for a in huerfanas:
        pid = con.execute(sa.text("SELECT id FROM productos WHERE organizacion_id = :o AND codigo_generico = :c"),
                          {'o': a.organizacion_id, 'c': a.codigo}).scalar()
        if pid is None:
            ahora = datetime.utcnow()
            pid = con.execute(t.insert().values(
                organizacion_id=a.organizacion_id, codigo_generico=a.codigo, nombre=a.descripcion or a.codigo,
                unidad=a.unidad, proveedor_id=a.proveedor_id, ficha={}, faltan=[], ficha_completa=False, version_ficha=1,
                estado='borrador', creado_en=ahora, actualizado_en=ahora, version=1).returning(t.c.id)).scalar_one()
        con.execute(sa.text('UPDATE articulos SET producto_id = :p WHERE id = :a'), {'p': pid, 'a': a.id})
    # El proveedor del producto: el suyo o el de sus variantes
    con.execute(sa.text("UPDATE productos SET proveedor_id = (SELECT min(a.proveedor_id) FROM articulos a "
                        "WHERE a.producto_id = productos.id) WHERE proveedor_id IS NULL"))


def _valores_de_variante(con) -> None:
    """Talla y color que solo estaban en las columnas del artículo (o el color del producto) pasan a sus atributos."""
    atrs = {(f.organizacion_id, f.columna): f.id for f in con.execute(sa.text(
        "SELECT id, organizacion_id, columna FROM atributos_variante WHERE columna IS NOT NULL"))}
    filas = con.execute(sa.text(
        "SELECT a.id, a.organizacion_id, a.tipo, a.talla, coalesce(a.color, p.color) AS color FROM articulos a "
        "LEFT JOIN productos p ON p.id = a.producto_id")).all()
    existentes = set(con.execute(sa.text('SELECT articulo_id, atributo_id FROM articulo_atributos')).all())
    nuevos = []
    for f in filas:
        for columna, valor in (('talla', f.talla if f.tipo == 'SOLIDO' else None), ('color', f.color)):
            atr = atrs.get((f.organizacion_id, columna))
            if valor and atr and (f.id, atr) not in existentes:
                nuevos.append({'articulo_id': f.id, 'atributo_id': atr, 'valor': str(valor)[:60], 'organizacion_id': f.organizacion_id})
    if nuevos:
        con.execute(_tabla(con, 'articulo_atributos').insert(), nuevos)


def _valores_de_producto(con) -> None:
    """Modelo (estilo) y marca pasan a atributos de producto, solo en las empresas que los usaban."""
    filas = con.execute(sa.text(
        "SELECT p.id, p.organizacion_id, coalesce(p.estilo, (SELECT min(a.estilo) FROM articulos a WHERE a.producto_id = p.id)) "
        "AS modelo, (SELECT m.codigo FROM marcas m WHERE m.id = coalesce(p.marca_id, (SELECT min(a.marca_id) FROM articulos a "
        "WHERE a.producto_id = p.id))) AS marca FROM productos p ORDER BY p.id")).all()
    atributos: dict[tuple[int, str], int] = {}
    valores = []
    for f in filas:
        for clave, nombre, valor, catalogo, orden in (('MARCA', 'Brand', f.marca, 'marcas', 1),
                                                      ('MODELO', 'Model', f.modelo, None, 2)):
            if not valor:
                continue
            if (f.organizacion_id, clave) not in atributos:
                atributos[(f.organizacion_id, clave)] = _nuevo_atributo(con, f.organizacion_id, clave, nombre, 'PRODUCTO',
                                                                        orden, catalogo)
            valores.append({'producto_id': f.id, 'atributo_id': atributos[(f.organizacion_id, clave)],
                            'valor': str(valor)[:200], 'organizacion_id': f.organizacion_id})
    if valores:
        con.execute(_tabla(con, 'producto_atributos').insert(), valores)


def _campos_propios(con) -> None:
    """Los campos propios de artículos pasan a atributos de variante (con sus valores)."""
    defs = con.execute(sa.text("SELECT id, organizacion_id, clave, etiqueta, tipo, opciones, orden FROM definiciones_campo "
                               "WHERE entidad = 'articulos' ORDER BY organizacion_id, orden, id")).all()
    for d in defs:
        opciones = d.opciones if isinstance(d.opciones, list) else json.loads(d.opciones or '[]')
        atr = _nuevo_atributo(con, d.organizacion_id, d.clave.upper()[:20], d.etiqueta[:60], 'VARIANTE', 100 + (d.orden or 0),
                              tipo=d.tipo, opciones=', '.join(str(o.get('valor', o) if isinstance(o, dict) else o)
                                                              for o in opciones)[:500] or None)
        filas = con.execute(sa.text('SELECT id, extra FROM articulos WHERE organizacion_id = :o'), {'o': d.organizacion_id}).all()
        nuevos = []
        for f in filas:
            extra = f.extra if isinstance(f.extra, dict) else json.loads(f.extra or '{}')
            v = extra.get(d.clave)
            if v not in (None, ''):
                nuevos.append({'articulo_id': f.id, 'atributo_id': atr, 'valor': str(v)[:60], 'organizacion_id': d.organizacion_id})
        if nuevos:
            con.execute(_tabla(con, 'articulo_atributos').insert(), nuevos)
    con.execute(sa.text("DELETE FROM definiciones_campo WHERE entidad = 'articulos'"))


def _codigos(con) -> None:
    """upc → BARRAS, sku_proveedor → PROVEEDOR (con su proveedor), prepack → PACK."""
    filas = con.execute(sa.text(
        "SELECT a.id, a.organizacion_id, a.tipo, a.upc, a.sku_proveedor, a.talla, coalesce(a.proveedor_id, p.proveedor_id) "
        "AS proveedor_id, (SELECT k.codigo FROM prepacks k WHERE k.id = a.prepack_id) AS pack "
        "FROM articulos a JOIN productos p ON p.id = a.producto_id ORDER BY a.id")).all()
    nuevos = []
    for f in filas:
        pack = (f.pack or f.talla) if f.tipo == 'PREPACK' else None
        for tipo, valor, prov in (('BARRAS', f.upc, None), ('PROVEEDOR', f.sku_proveedor, f.proveedor_id), ('PACK', pack, None)):
            if valor and str(valor).strip():
                nuevos.append({'articulo_id': f.id, 'tipo': tipo, 'valor': str(valor).strip()[:60], 'proveedor_id': prov,
                               'organizacion_id': f.organizacion_id})
    if nuevos:
        con.execute(_tabla(con, 'articulo_codigos').insert(), nuevos)


def _componentes(con) -> None:
    """El contenido de cada prepack pasa a la variante compuesta que lo usa."""
    con.execute(sa.text(
        "INSERT INTO articulo_componentes (compuesto_id, componente_id, cantidad, organizacion_id) "
        "SELECT a.id, c.articulo_id, c.cantidad, a.organizacion_id FROM articulos a "
        "JOIN prepack_componentes c ON c.prepack_id = a.prepack_id WHERE a.prepack_id IS NOT NULL AND c.cantidad >= 1"))
    con.execute(sa.text("UPDATE articulos SET descripcion = (SELECT k.descripcion FROM prepacks k WHERE k.id = articulos.prepack_id) "
                        "WHERE prepack_id IS NOT NULL AND (descripcion IS NULL OR descripcion = '')"))


def _familias(con) -> None:
    """La familia del producto: la suya, la de sus variantes o la de su grupo de artículos."""
    con.execute(sa.text(
        "UPDATE productos SET grupo_producto_id = coalesce("
        "(SELECT min(a.grupo_producto_id) FROM articulos a WHERE a.producto_id = productos.id), "
        "(SELECT g.grupo_producto_id FROM grupos_articulos g WHERE g.id = productos.grupo_id), "
        "(SELECT min(g.grupo_producto_id) FROM articulos a JOIN grupos_articulos g ON g.id = a.grupo_id "
        "WHERE a.producto_id = productos.id)) WHERE grupo_producto_id IS NULL"))


def _dias_extra(con) -> None:
    """Los días extra del grupo de artículos pasan a la familia; un grupo con días y sin familia se vuelve familia."""
    grupos = con.execute(sa.text("SELECT id, organizacion_id, codigo, nombre, dias_extra, grupo_producto_id FROM grupos_articulos "
                                 "WHERE dias_extra IS NOT NULL ORDER BY id")).all()
    t = _tabla(con, 'grupos_producto')
    for g in grupos:
        fam = g.grupo_producto_id
        if fam is None:
            usados = set(con.execute(sa.text('SELECT codigo FROM grupos_producto WHERE organizacion_id = :o'),
                                     {'o': g.organizacion_id}).scalars())
            codigo, n = g.codigo[:20], 2
            while codigo in usados:
                codigo, n = f'{g.codigo[:17]}-{n}', n + 1
            fam = con.execute(t.insert().values(clase='FAMILIA', codigo=codigo, nombre=g.nombre[:100], condiciones=[], campos=[],
                                                ejes_variante=[], orden=0, activa=True, creada_en=datetime.utcnow(),
                                                organizacion_id=g.organizacion_id).returning(t.c.id)).scalar_one()
            con.execute(sa.text(
                "UPDATE productos SET grupo_producto_id = :f WHERE grupo_producto_id IS NULL AND (grupo_id = :g OR id IN "
                "(SELECT producto_id FROM articulos WHERE grupo_id = :g))"), {'f': fam, 'g': g.id})
        con.execute(sa.text('UPDATE grupos_producto SET dias_extra = :d WHERE id = :f AND (dias_extra IS NULL OR dias_extra < :d)'),
                    {'d': g.dias_extra, 'f': fam})


def _escalas(con) -> None:
    """escalas_talla → escalas_valores (cada valor como «valor»; la regla TALLA se llama VALOR)."""
    t = _tabla(con, 'escalas_valores')
    filas = []
    for f in con.execute(sa.text('SELECT id, codigo, nombre, atributo, regla, factor, longitud, tallas, activo, organizacion_id '
                                 'FROM escalas_talla ORDER BY id')):
        lista = f.tallas if isinstance(f.tallas, list) else json.loads(f.tallas or '[]')
        filas.append({'id': f.id, 'codigo': f.codigo, 'nombre': f.nombre, 'atributo': f.atributo or 'TALLA',
                      'regla': 'VALOR' if f.regla == 'TALLA' else f.regla, 'factor': f.factor, 'longitud': f.longitud,
                      'valores': [{'valor': x.get('talla', x.get('valor')), 'codigo': x.get('codigo')} for x in lista],
                      'activo': f.activo, 'organizacion_id': f.organizacion_id})
    if filas:
        con.execute(t.insert(), filas)
    _secuencia('escalas_valores')


def _lineas(con) -> None:
    """Líneas de OC y de factura: código de barras, código del pack y foto de los atributos del producto."""
    codigos = {(f.organizacion_id, f.clave): f.codigo for f in con.execute(sa.text(
        "SELECT organizacion_id, codigo, CASE WHEN catalogo = 'marcas' THEN 'MARCA' ELSE 'MODELO' END AS clave FROM atributos "
        "WHERE nivel = 'PRODUCTO' ORDER BY id"))}
    for tabla in ('posiciones_oc', 'factura_lineas'):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.add_column(sa.Column('codigo_barras', sa.String(length=40), nullable=True))
            b.add_column(sa.Column('atributos', sa.JSON(), nullable=True))
            b.add_column(sa.Column('codigo_pack', sa.String(length=30), nullable=True))
        con.execute(sa.text(f'UPDATE {tabla} SET codigo_barras = upc, codigo_pack = prepack'))
        t = _tabla(con, tabla)
        cambios = []
        for f in con.execute(sa.select(t.c.id, t.c.organizacion_id, t.c.marca, t.c.estilo, t.c.talla, t.c.color, t.c.variante,
                                       t.c.tipo_empaque)):
            atrs = {codigos[(f.organizacion_id, k)]: v for k, v in (('MARCA', f.marca), ('MODELO', f.estilo))
                    if v and (f.organizacion_id, k) in codigos}
            variante = f.variante
            if variante is None and (f.talla or f.color):
                variante = {k: v for k, v in (('TALLA', f.talla if f.tipo_empaque != 'PREPACK' else None), ('COLOR', f.color)) if v}
            if atrs or variante != f.variante:
                cambios.append({'_id': f.id, 'atributos': atrs or None, 'variante': variante or None})
        if cambios:
            con.execute(t.update().where(t.c.id == sa.bindparam('_id')).values(atributos=sa.bindparam('atributos'),
                                                                                  variante=sa.bindparam('variante')), cambios)


def _obligatorios(con) -> None:
    """Datos que la empresa exige a sus artículos y columnas de las líneas de sus documentos: los que
    cambiaron de nombre (upc → codigo_barras) o pasaron a atributo (estilo → atributo.MODELO)."""
    t = _tabla(con, 'organizaciones')
    for f in con.execute(sa.select(t.c.id, t.c.configuracion)).all():
        conf = f.configuracion if isinstance(f.configuracion, dict) else json.loads(f.configuracion or '{}')
        conf = dict(conf or {})
        codigos = dict(con.execute(sa.text("SELECT CASE WHEN catalogo = 'marcas' THEN 'marca_id' WHEN codigo = 'MODELO' "
                                           "THEN 'estilo' WHEN codigo = 'TALLA' THEN 'talla' WHEN codigo = 'COLOR' THEN 'color' "
                                           "ELSE codigo END, codigo FROM atributos WHERE organizacion_id = :o"), {'o': f.id}).all())

        def nuevo(c: str) -> str:
            return OBLIGATORIOS.get(c, f'atributo.{codigos[c]}' if c in codigos else c)

        cambio = False
        arts = (conf.get('maestros') or {}).get('articulos')
        if arts and arts.get('obligatorios'):
            nuevos = [x for x in map(nuevo, arts['obligatorios'])
                      if x in ('codigo_barras', 'codigo_proveedor', 'peso_unitario', 'proveedor_id') or x.startswith('atributo.')]
            conf['maestros'] = {**conf['maestros'], 'articulos': {**arts, 'obligatorios': nuevos}}
            cambio = True
        docs = conf.get('documentos') or {}
        if docs.get('columnas_linea'):
            cols = [nuevo(x.strip()) for x in docs['columnas_linea'].split(',') if x.strip()]
            cols = [x for x in cols if x in ('variante', 'codigo_barras') or x.startswith('atributo.')]
            conf['documentos'] = {**docs, 'columnas_linea': ','.join(dict.fromkeys(cols))}
            cambio = True
        if cambio:
            con.execute(t.update().where(t.c.id == f.id).values(configuracion=conf))


def _mapas(con, org: int, desde_atributos_variante: bool) -> tuple[dict, dict]:
    """Claves anteriores → nuevas de la empresa: (campos, columnas de las tablas de las etiquetas)."""
    tabla = 'atributos_variante' if desde_atributos_variante else 'atributos'
    col = "columna" if desde_atributos_variante else "lower(codigo)"
    var = dict(con.execute(sa.text(f"SELECT {col}, codigo FROM {tabla} WHERE organizacion_id = :o AND {col} IN "
                                   "('talla', 'color')"), {'o': org}).all())
    prod = dict(con.execute(sa.text("SELECT CASE WHEN catalogo = 'marcas' THEN 'marca' ELSE 'modelo' END, codigo FROM atributos "
                                    "WHERE organizacion_id = :o AND nivel = 'PRODUCTO' AND (catalogo = 'marcas' OR codigo = "
                                    "'MODELO') ORDER BY id"), {'o': org}).all())
    campos = {'articulo.upc': 'articulo.codigo_barras', 'linea.upc': 'linea.codigo_barras',
              'articulo.sku_proveedor': 'articulo.codigo_proveedor', 'articulo.prepack': 'articulo.codigo_pack',
              'linea.prepack': 'linea.codigo_pack', 'articulo.marca': 'producto.marca'}
    for viejo, clave in (('talla', 'talla'), ('color', 'color')):
        if var.get(clave):
            campos[f'articulo.{viejo}'] = f'articulo.atributo.{var[clave]}'
            campos[f'linea.{viejo}'] = f'linea.atributo.{var[clave]}'
    if prod.get('marca'):
        campos['articulo.marca_codigo'] = f"producto.dato.{prod['marca']}"
        campos['linea.marca'] = f"linea.atributo.{prod['marca']}"
    if prod.get('modelo'):
        campos['articulo.estilo'] = f"producto.dato.{prod['modelo']}"
        campos['linea.estilo'] = f"linea.atributo.{prod['modelo']}"
    columnas = {'upc': 'codigo_barras', **{c: f'atributo.{var[c]}' for c in ('talla', 'color') if var.get(c)}}
    return campos, columnas


def _renombrar(obj, campos: dict, columnas: dict, patron):
    """El JSON con las claves de campos cambiadas (en textos, en llaves y en las columnas de las tablas)."""
    if isinstance(obj, dict):
        res = {}
        for k, v in obj.items():
            if k == 'columnas' and 'coleccion' in obj and isinstance(v, list):
                v = [{**c, 'campo': columnas.get(c.get('campo'), c.get('campo'))} if isinstance(c, dict) else c for c in v]
            elif k == 'totales' and 'coleccion' in obj and isinstance(v, list):
                v = [columnas.get(x, x) for x in v]
            res[_renombrar(k, campos, columnas, patron)] = _renombrar(v, campos, columnas, patron)
        return res
    if isinstance(obj, list):
        return [_renombrar(x, campos, columnas, patron) for x in obj]
    if isinstance(obj, str) and patron is not None:
        return patron.sub(lambda m: campos[m.group(0)], obj)
    return obj


def _claves_de_campos(con, subir: bool) -> None:
    """Cambia las claves de campos guardadas (subir) o las devuelve a las anteriores (bajar)."""
    for (org,) in con.execute(sa.text('SELECT id FROM organizaciones')).all():
        campos, columnas = _mapas(con, org, desde_atributos_variante=subir)
        if not subir:
            campos, columnas = {v: k for k, v in campos.items()}, {v: k for k, v in columnas.items()}
        patron = re.compile(r'(?<![A-Za-z0-9_.])(' + '|'.join(re.escape(k) for k in sorted(campos, key=len, reverse=True))
                            + r')(?![A-Za-z0-9_])') if campos else None
        for tabla, col in CON_CLAVES:
            t = _tabla(con, tabla)
            cond = t.c.id == org if tabla == 'organizaciones' else t.c.organizacion_id == org
            cambios = []
            for f in con.execute(sa.select(t.c.id, t.c[col]).where(cond)):
                v = f._mapping[col]
                v = json.loads(v) if isinstance(v, str) else v
                nuevo = _renombrar(v, campos, columnas, patron)
                if nuevo != v:
                    cambios.append({'_id': f.id, 'v': nuevo})
            if cambios:
                con.execute(t.update().where(t.c.id == sa.bindparam('_id')).values({col: sa.bindparam('v')}), cambios)


# ---- Bajar ------------------------------------------------------------------------------------------
def downgrade() -> None:
    con = op.get_bind()
    _recrear_tablas()
    for tabla in ('categorias_articulo', 'familias_etiquetado', 'categorias_etiquetado', 'grupos_articulos', 'prepacks'):
        _devolver_tabla(con, tabla)
    # Atributos de variante: los mismos ids; los de producto vuelven a ser columnas
    con.execute(sa.text(
        "INSERT INTO atributos_variante (id, codigo, nombre, columna, orden, activo, organizacion_id, tipo, opciones, unidad) "
        "SELECT id, codigo, nombre, NULL, orden, activo, organizacion_id, CASE WHEN tipo IN ('numero', 'opcion') THEN tipo "
        "ELSE 'texto' END, opciones, unidad FROM atributos WHERE nivel = 'VARIANTE'"))
    _secuencia('atributos_variante')
    for f in _respaldo(con, 'atributos_variante'):
        con.execute(sa.text('UPDATE atributos_variante SET columna = :c WHERE id = :i'), {'c': f.get('columna'), 'i': f['_id']})
    con.execute(sa.text("UPDATE atributos_variante SET columna = lower(codigo) WHERE columna IS NULL AND codigo IN ('TALLA', 'COLOR') "
                        "AND NOT EXISTS (SELECT 1 FROM atributos_variante x WHERE x.organizacion_id = atributos_variante.organizacion_id "
                        "AND x.columna = lower(atributos_variante.codigo))"))
    _cambiar_fk('articulo_atributos', 'atributo_id', 'atributos', 'atributos_variante',
                'fk_articulo_atributos_atributo_id_atributos_variante', True)
    _claves_de_campos(con, subir=False)

    # Columnas anteriores
    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.add_column(sa.Column('legado_familia_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('legado_categoria_id', sa.Integer(), nullable=True))
    with op.batch_alter_table('usos_diseno', schema=None) as b:
        b.add_column(sa.Column('familia_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('categoria_id', sa.Integer(), nullable=True))
        b.create_index('ix_usos_diseno_familia_id', ['familia_id'], unique=False)
        b.create_index('ix_usos_diseno_categoria_id', ['categoria_id'], unique=False)
        b.create_foreign_key('fk_usos_diseno_familia_id_familias_etiquetado', 'familias_etiquetado', ['familia_id'], ['id'])
        b.create_foreign_key('fk_usos_diseno_categoria_id_categorias_etiquetado', 'categorias_etiquetado', ['categoria_id'], ['id'])
        b.create_foreign_key('fk_usos_diseno_familia_id_org', 'familias_etiquetado', ['familia_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
        b.create_foreign_key('fk_usos_diseno_categoria_id_org', 'categorias_etiquetado', ['categoria_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
    with op.batch_alter_table('generacion_items', schema=None) as b:
        b.add_column(sa.Column('familia_id', sa.Integer(), nullable=True))
        b.create_index('ix_generacion_items_familia_id', ['familia_id'], unique=False)
        b.create_foreign_key('fk_generacion_items_familia_id_familias_etiquetado', 'familias_etiquetado', ['familia_id'], ['id'])
        b.create_foreign_key('fk_generacion_items_familia_id_org', 'familias_etiquetado', ['familia_id', 'organizacion_id'],
                             ['id', 'organizacion_id'])
    with op.batch_alter_table('productos', schema=None) as b:
        b.add_column(sa.Column('estilo', sa.String(length=40), nullable=True))
        b.add_column(sa.Column('color', sa.String(length=60), nullable=True))
        b.add_column(sa.Column('marca_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('grupo_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('familia_etiquetado_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('categoria_etiquetado_id', sa.Integer(), nullable=True))
        for c, ref in (('marca_id', 'marcas'), ('grupo_id', 'grupos_articulos')):
            b.create_index(f'ix_productos_{c}', [c], unique=False)
            b.create_foreign_key(f'fk_productos_{c}', ref, [c], ['id'])
        for c, ref in (('familia_etiquetado_id', 'familias_etiquetado'), ('categoria_etiquetado_id', 'categorias_etiquetado')):
            b.create_index(f'ix_productos_{c}', [c], unique=False)
            b.create_foreign_key(f'fk_productos_{c}', ref, [c], ['id'])
            b.create_foreign_key(f'fk_productos_{c}_org', ref, [c, 'organizacion_id'], ['id', 'organizacion_id'])
    viejo = _nombre_fk(con, 'articulos', 'producto_id', 'productos')
    with op.batch_alter_table('articulos', schema=None, naming_convention=CONVENCION) as b:
        b.drop_constraint('ck_articulos_tipo', type_='check')
        b.drop_constraint('fk_articulos_producto_id_org', type_='foreignkey')
        b.drop_constraint(viejo, type_='foreignkey')
        b.alter_column('producto_id', existing_type=sa.Integer(), nullable=True)
        b.create_foreign_key('fk_articulos_producto_id_productos', 'productos', ['producto_id'], ['id'])
        b.add_column(sa.Column('generico', sa.String(length=40), nullable=True))
        b.add_column(sa.Column('sku_proveedor', sa.String(length=60), nullable=True))
        b.add_column(sa.Column('upc', sa.String(length=40), nullable=True))
        b.add_column(sa.Column('estilo', sa.String(length=40), nullable=True))
        b.add_column(sa.Column('color', sa.String(length=60), nullable=True))
        b.add_column(sa.Column('talla', sa.String(length=20), nullable=True))
        b.add_column(sa.Column('marca_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('grupo_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('proveedor_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('prepack_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('extra', sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
        b.add_column(sa.Column('familia_etiquetado_id', sa.Integer(), nullable=True))
        b.add_column(sa.Column('grupo_producto_id', sa.Integer(), nullable=True))
        for c in ('generico', 'sku_proveedor', 'marca_id', 'grupo_id', 'proveedor_id', 'prepack_id', 'familia_etiquetado_id',
                  'grupo_producto_id'):
            b.create_index(f'ix_articulos_{c}', [c], unique=False)
        for c, ref in (('marca_id', 'marcas'), ('grupo_id', 'grupos_articulos'), ('proveedor_id', 'proveedores'),
                       ('prepack_id', 'prepacks'), ('familia_etiquetado_id', 'familias_etiquetado'),
                       ('grupo_producto_id', 'grupos_producto')):
            b.create_foreign_key(f'fk_articulos_{c}', ref, [c], ['id'])
        for c, ref in (('familia_etiquetado_id', 'familias_etiquetado'), ('grupo_producto_id', 'grupos_producto')):
            b.create_foreign_key(f'fk_articulos_{c}_org', ref, [c, 'organizacion_id'], ['id', 'organizacion_id'])
    for tabla, extra in (('posiciones_oc', ('grupo',)), ('factura_lineas', ())):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.add_column(sa.Column('upc', sa.String(length=40), nullable=True))
            b.add_column(sa.Column('estilo', sa.String(length=40), nullable=True))
            b.add_column(sa.Column('color', sa.String(length=60), nullable=True))
            b.add_column(sa.Column('talla', sa.String(length=20), nullable=True))
            b.add_column(sa.Column('marca', sa.String(length=10), nullable=True))
            b.add_column(sa.Column('categoria', sa.String(length=10), nullable=True))
            b.add_column(sa.Column('prepack', sa.String(length=30), nullable=True))
            if extra:
                b.add_column(sa.Column('grupo', sa.String(length=15), nullable=True))
                for c, ref in (('marca', 'marcas'), ('grupo', 'grupos_articulos'), ('categoria', 'categorias_articulo')):
                    b.create_foreign_key(f'fk_posiciones_oc_{c}', ref, ['organizacion_id', c], ['organizacion_id', 'codigo'])
    for tabla, cols in COLUMNAS_BORRADAS.items():
        _devolver_columnas(con, tabla, cols)
    _completar_columnas(con)
    _devolver_tabla(con, 'escalas_talla')
    _escalas_de_vuelta(con)
    _devolver_tabla(con, 'prepack_componentes')
    with op.batch_alter_table('definiciones_campo', schema=None) as b:
        b.drop_constraint('ck_definiciones_campo_entidad', type_='check')
        b.create_check_constraint('ck_definiciones_campo_entidad', "entidad IN ('articulos', 'proveedores', 'sociedades', "
                                  "'centros', 'marcas', 'transportistas', 'ordenes', 'facturas')")
    defs = _tabla(con, 'definiciones_campo')
    for f in _respaldo(con, 'definiciones_campo'):
        if f.get('entidad') == 'articulos':
            con.execute(defs.insert(), [{k: v for k, v in _tipado(defs, f).items() if k != 'id'}])
    t = _tabla(con, 'organizaciones')
    for f in _respaldo(con, 'organizaciones'):
        antes = f.get('configuracion') or {}
        actual = con.execute(sa.select(t.c.configuracion).where(t.c.id == f['_id'])).scalar()
        actual = actual if isinstance(actual, dict) else json.loads(actual or '{}')
        arts = (antes.get('maestros') or {}).get('articulos')
        if arts is not None:
            actual = {**actual, 'maestros': {**(actual.get('maestros') or {}), 'articulos': arts}}
        cols = (antes.get('documentos') or {}).get('columnas_linea')
        if cols is not None:
            actual = {**actual, 'documentos': {**(actual.get('documentos') or {}), 'columnas_linea': cols}}
        con.execute(t.update().where(t.c.id == f['_id']).values(configuracion=actual))

    for tabla in ('posiciones_oc', 'factura_lineas'):
        _quitar_columnas(tabla, ('codigo_barras', 'atributos', 'codigo_pack'))
    _quitar_columnas('grupos_producto', ('dias_extra',))
    for t in ('escalas_valores', 'articulo_componentes', 'articulo_codigos', 'producto_atributos', 'atributos',
              'respaldos_migracion'):
        op.drop_table(t)
    rls(op, 'atributos_variante', 'prepacks', 'prepack_componentes', 'escalas_talla', 'grupos_articulos',
        'categorias_articulo', 'familias_etiquetado', 'categorias_etiquetado')


def _recrear_tablas() -> None:
    op.create_table('categorias_articulo',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=10), nullable=False),
                    sa.Column('nombre', sa.String(length=100), nullable=False),
                    sa.Column('activo', sa.Boolean(), nullable=False),
                    sa.Column('dominio', sa.String(length=30), nullable=True),
                    *_base('categorias_articulo'),
                    sa.ForeignKeyConstraint(['dominio'], ['dominios_clasificacion.codigo'], onupdate='CASCADE',
                                            name='fk_categorias_articulo_dominio'),
                    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_categorias_articulo_org_codigo'))
    _indices('categorias_articulo', 'dominio')
    op.create_table('familias_etiquetado',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=20), nullable=False),
                    sa.Column('nombre', sa.String(length=100), nullable=False),
                    sa.Column('descripcion', sa.String(length=300), nullable=True),
                    sa.Column('campos', sa.JSON(), nullable=False),
                    sa.Column('orden', sa.Integer(), nullable=False),
                    sa.Column('activa', sa.Boolean(), nullable=False),
                    sa.Column('creada_en', sa.DateTime(), nullable=False),
                    sa.Column('padre_id', sa.Integer(), nullable=True),
                    *_base('familias_etiquetado'),
                    sa.ForeignKeyConstraint(['padre_id'], ['familias_etiquetado.id'],
                                            name='fk_familias_etiquetado_padre_id_familias_etiquetado'),
                    *_org('familias_etiquetado', ('padre_id', 'familias_etiquetado')),
                    sa.UniqueConstraint('id', 'organizacion_id', name='uq_familias_etiquetado_id_org'),
                    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_familias_etiquetado_org_codigo'))
    _indices('familias_etiquetado', 'padre_id')
    op.create_table('categorias_etiquetado',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('familia_id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=20), nullable=False),
                    sa.Column('nombre', sa.String(length=100), nullable=False),
                    sa.Column('descripcion', sa.String(length=300), nullable=True),
                    sa.Column('condiciones', sa.JSON(), nullable=False),
                    sa.Column('orden', sa.Integer(), nullable=False),
                    sa.Column('activa', sa.Boolean(), nullable=False),
                    sa.Column('creada_en', sa.DateTime(), nullable=False),
                    *_base('categorias_etiquetado'),
                    sa.ForeignKeyConstraint(['familia_id'], ['familias_etiquetado.id'],
                                            name='fk_categorias_etiquetado_familia_id_familias_etiquetado'),
                    *_org('categorias_etiquetado', ('familia_id', 'familias_etiquetado')),
                    sa.UniqueConstraint('id', 'organizacion_id', name='uq_categorias_etiquetado_id_org'),
                    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_categorias_etiquetado_org_codigo'))
    _indices('categorias_etiquetado', 'familia_id')
    op.create_table('grupos_articulos',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=15), nullable=False),
                    sa.Column('nombre', sa.String(length=100), nullable=False),
                    sa.Column('categoria', sa.String(length=10), nullable=False),
                    sa.Column('dias_extra', sa.Integer(), nullable=True),
                    sa.Column('activo', sa.Boolean(), nullable=False),
                    sa.Column('familia_etiquetado_id', sa.Integer(), nullable=True),
                    sa.Column('grupo_producto_id', sa.Integer(), nullable=True),
                    *_base('grupos_articulos'),
                    sa.ForeignKeyConstraint(['organizacion_id', 'categoria'],
                                            ['categorias_articulo.organizacion_id', 'categorias_articulo.codigo'],
                                            name='fk_grupos_articulos_categoria'),
                    sa.ForeignKeyConstraint(['familia_etiquetado_id'], ['familias_etiquetado.id'],
                                            name='fk_grupos_articulos_familia_etiquetado_id'),
                    sa.ForeignKeyConstraint(['grupo_producto_id'], ['grupos_producto.id'], name='fk_grupos_articulos_grupo_producto_id'),
                    *_org('grupos_articulos', ('familia_etiquetado_id', 'familias_etiquetado'),
                          ('grupo_producto_id', 'grupos_producto')),
                    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_grupos_articulos_org_codigo'))
    _indices('grupos_articulos', 'familia_etiquetado_id', 'grupo_producto_id')
    op.create_table('prepacks',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=10), nullable=False),
                    sa.Column('estilo', sa.String(length=40), nullable=True),
                    sa.Column('color', sa.String(length=60), nullable=True),
                    sa.Column('descripcion', sa.String(length=200), nullable=True),
                    sa.Column('activo', sa.Boolean(), nullable=False),
                    sa.Column('tipo', sa.String(length=10), server_default='CURVA', nullable=False),
                    *_base('prepacks'),
                    sa.CheckConstraint("tipo IN ('CURVA', 'KIT')", name='ck_prepacks_tipo'),
                    sa.UniqueConstraint('organizacion_id', 'estilo', 'color', 'codigo', name='uq_prepacks_org_estilo_color_codigo'))
    _indices('prepacks')
    op.create_table('prepack_componentes',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('prepack_id', sa.Integer(), nullable=False),
                    sa.Column('articulo_id', sa.Integer(), nullable=False),
                    sa.Column('cantidad', sa.Integer(), nullable=False),
                    *_base('prepack_componentes'),
                    sa.ForeignKeyConstraint(['prepack_id'], ['prepacks.id'], name='fk_prepack_componentes_prepack_id_prepacks'),
                    sa.ForeignKeyConstraint(['articulo_id'], ['articulos.id'], name='fk_prepack_componentes_articulo_id_articulos'),
                    sa.UniqueConstraint('prepack_id', 'articulo_id', name='uq_prepack_componentes_prepack_id'))
    _indices('prepack_componentes', 'prepack_id', 'articulo_id')
    op.create_table('escalas_talla',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=20), nullable=False),
                    sa.Column('nombre', sa.String(length=120), nullable=False),
                    sa.Column('categoria', sa.String(length=20), nullable=True),
                    sa.Column('regla', sa.String(length=15), nullable=False),
                    sa.Column('factor', sa.Integer(), nullable=True),
                    sa.Column('longitud', sa.Integer(), nullable=True),
                    sa.Column('tallas', sa.JSON(), nullable=False),
                    sa.Column('activo', sa.Boolean(), nullable=False),
                    sa.Column('atributo', sa.String(length=20), server_default='TALLA', nullable=False),
                    *_base('escalas_talla'),
                    sa.ForeignKeyConstraint(['organizacion_id', 'categoria'],
                                            ['categorias_articulo.organizacion_id', 'categorias_articulo.codigo'],
                                            name='fk_escalas_talla_categoria'),
                    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_escalas_talla_org_codigo'))
    _indices('escalas_talla')
    op.create_table('atributos_variante',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('codigo', sa.String(length=20), nullable=False),
                    sa.Column('nombre', sa.String(length=60), nullable=False),
                    sa.Column('columna', sa.String(length=10), nullable=True),
                    sa.Column('orden', sa.Integer(), nullable=False),
                    sa.Column('activo', sa.Boolean(), nullable=False),
                    sa.Column('tipo', sa.String(length=10), server_default='texto', nullable=False),
                    sa.Column('opciones', sa.String(length=500), nullable=True),
                    sa.Column('unidad', sa.String(length=10), nullable=True),
                    *_base('atributos_variante'),
                    sa.CheckConstraint("columna IS NULL OR columna IN ('talla', 'color')", name='ck_atributos_variante_columna'),
                    sa.CheckConstraint("tipo IN ('texto', 'numero', 'opcion')", name='ck_atributos_variante_tipo'),
                    sa.ForeignKeyConstraint(['organizacion_id', 'unidad'],
                                            ['unidades_medida.organizacion_id', 'unidades_medida.codigo'],
                                            name='fk_atributos_variante_unidad'),
                    sa.UniqueConstraint('id', 'organizacion_id', name='uq_atributos_variante_id_org'),
                    sa.UniqueConstraint('organizacion_id', 'codigo', name='uq_atributos_variante_org_codigo'))
    _indices('atributos_variante')


def _devolver_tabla(con, tabla: str) -> None:
    t = _tabla(con, tabla)
    filas = [_tipado(t, f) for f in _respaldo(con, tabla)]
    if filas:
        con.execute(t.insert(), filas)
        _secuencia(tabla)


def _devolver_columnas(con, tabla: str, cols: tuple[str, ...]) -> None:
    t = _tabla(con, tabla)
    filas = [{'_id': f['_id'], **{c: _tipado(t, {c: f.get(c)}).get(c) for c in cols}} for f in _respaldo(con, tabla)]
    if filas:
        con.execute(t.update().where(t.c.id == sa.bindparam('_id')).values({c: sa.bindparam(c) for c in cols}), filas)


def _completar_columnas(con) -> None:
    """Lo creado después de subir (sin respaldo) se completa con los datos nuevos."""
    sql = [
        "UPDATE articulos SET generico = (SELECT p.codigo_generico FROM productos p WHERE p.id = articulos.producto_id) "
        "WHERE generico IS NULL",
        "UPDATE articulos SET proveedor_id = (SELECT p.proveedor_id FROM productos p WHERE p.id = articulos.producto_id) "
        "WHERE proveedor_id IS NULL",
        "UPDATE articulos SET upc = (SELECT min(c.valor) FROM articulo_codigos c WHERE c.articulo_id = articulos.id "
        "AND c.tipo = 'BARRAS') WHERE upc IS NULL",
        "UPDATE articulos SET sku_proveedor = (SELECT min(c.valor) FROM articulo_codigos c WHERE c.articulo_id = articulos.id "
        "AND c.tipo = 'PROVEEDOR') WHERE sku_proveedor IS NULL",
        "UPDATE articulos SET talla = (SELECT min(c.valor) FROM articulo_codigos c WHERE c.articulo_id = articulos.id "
        "AND c.tipo = 'PACK') WHERE talla IS NULL AND tipo = 'PREPACK'",
        "UPDATE articulos SET talla = (SELECT min(x.valor) FROM articulo_atributos x JOIN atributos_variante v ON v.id = x.atributo_id "
        "WHERE x.articulo_id = articulos.id AND v.columna = 'talla') WHERE talla IS NULL",
        "UPDATE articulos SET color = (SELECT min(x.valor) FROM articulo_atributos x JOIN atributos_variante v ON v.id = x.atributo_id "
        "WHERE x.articulo_id = articulos.id AND v.columna = 'color') WHERE color IS NULL",
        "UPDATE articulos SET estilo = (SELECT min(x.valor) FROM producto_atributos x JOIN atributos v ON v.id = x.atributo_id "
        "WHERE x.producto_id = articulos.producto_id AND v.codigo = 'MODELO') WHERE estilo IS NULL",
        "UPDATE articulos SET marca_id = (SELECT min(m.id) FROM producto_atributos x JOIN atributos v ON v.id = x.atributo_id "
        "JOIN marcas m ON m.organizacion_id = x.organizacion_id AND m.codigo = x.valor WHERE x.producto_id = articulos.producto_id "
        "AND v.catalogo = 'marcas') WHERE marca_id IS NULL",
        "UPDATE productos SET estilo = (SELECT min(a.estilo) FROM articulos a WHERE a.producto_id = productos.id) WHERE estilo IS NULL",
        "UPDATE productos SET marca_id = (SELECT min(a.marca_id) FROM articulos a WHERE a.producto_id = productos.id) "
        "WHERE marca_id IS NULL",
        "UPDATE posiciones_oc SET upc = codigo_barras WHERE upc IS NULL",
        "UPDATE posiciones_oc SET prepack = codigo_pack WHERE prepack IS NULL",
        "UPDATE factura_lineas SET upc = codigo_barras WHERE upc IS NULL",
        "UPDATE factura_lineas SET prepack = codigo_pack WHERE prepack IS NULL",
    ]
    for s in sql:
        con.execute(sa.text(s))


def _escalas_de_vuelta(con) -> None:
    respaldadas = {f['_id'] for f in _respaldo(con, 'escalas_talla')}
    t = _tabla(con, 'escalas_talla')
    for f in con.execute(sa.text('SELECT id, codigo, nombre, atributo, regla, factor, longitud, valores, activo, organizacion_id '
                                 'FROM escalas_valores ORDER BY id')):
        lista = f.valores if isinstance(f.valores, list) else json.loads(f.valores or '[]')
        datos = {'codigo': f.codigo, 'nombre': f.nombre, 'atributo': f.atributo, 'regla': 'TALLA' if f.regla == 'VALOR' else f.regla,
                 'factor': f.factor, 'longitud': f.longitud, 'activo': f.activo,
                 'tallas': [{'talla': x.get('valor'), 'codigo': x.get('codigo')} for x in lista]}
        if f.id in respaldadas:
            con.execute(t.update().where(t.c.id == f.id).values(**datos))
        else:
            con.execute(t.insert().values(id=f.id, organizacion_id=f.organizacion_id, **datos))
    _secuencia('escalas_talla')
