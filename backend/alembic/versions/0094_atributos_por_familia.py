"""Atributos por familia

Hasta ahora un atributo valía para todos los productos: la familia solo decía,
con sus «ejes de variante» (grupos_producto.ejes_variante), con qué atributos
de variante se distinguían sus variantes, y una familia sin ejes usaba todos.
Ahora cada atributo vale en las familias que tiene (atributo_familias), y en
sus subfamilias y categorías, o en todas si es general (atributos.general).

Conversión, por organización, sin perder nada de lo que valía:

- los atributos de producto quedan generales (valían en todas);
- si ninguna familia tenía ejes, los de variante también quedan generales;
- si no, cada familia recibe los ejes que usaba (los suyos, los heredados o,
  sin ninguno, todos) que su familia padre no le da ya, y un atributo que
  valía en todas las familias queda general;
- además, cada atributo con valores guardados en productos de una familia
  donde no valdría se le asigna a esa familia: ningún valor queda fuera.

`ejes_variante` se respalda en respaldos_migracion y se borra. La vuelta atrás
recrea la columna con lo respaldado; una familia sin respaldo que tiene
atributos de variante asignados toma esos y los generales.

Revision ID: 0094
Revises: 0093
Create Date: 2026-10-23 16:00:00
"""
import json
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision = '0094'
down_revision = '0093'
branch_labels = None
depends_on = None


def _tabla(con, nombre: str) -> sa.Table:
    return sa.Table(nombre, sa.MetaData(), autoload_with=con)


def _lista(v) -> list:
    if isinstance(v, list):
        return v
    try:
        return json.loads(v) if v else []
    except (TypeError, ValueError):
        return []


def upgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table('atributos', schema=None) as b:
        b.add_column(sa.Column('general', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('atributo_familias',
                    sa.Column('atributo_id', sa.Integer(), nullable=False),
                    sa.Column('grupo_id', sa.Integer(), nullable=False),
                    sa.ForeignKeyConstraint(['atributo_id'], ['atributos.id'], ondelete='CASCADE',
                                            name='fk_atributo_familias_atributo_id_atributos'),
                    sa.ForeignKeyConstraint(['grupo_id'], ['grupos_producto.id'], ondelete='CASCADE',
                                            name='fk_atributo_familias_grupo_id_grupos_producto'),
                    sa.PrimaryKeyConstraint('atributo_id', 'grupo_id', name='pk_atributo_familias'))
    op.create_index('ix_atributo_familias_grupo_id', 'atributo_familias', ['grupo_id'], unique=False)

    grupos = _tabla(con, 'grupos_producto')
    filas = con.execute(sa.select(grupos.c.id, grupos.c.organizacion_id, grupos.c.clase, grupos.c.padre_id,
                                  grupos.c.ejes_variante)).all()
    respaldos = _tabla(con, 'respaldos_migracion')
    copia = [{'migracion': revision, 'tabla': 'grupos_producto', 'fila_id': g.id, 'creado_en': datetime.utcnow(),
              'datos': {'ejes_variante': _lista(g.ejes_variante)}} for g in filas if _lista(g.ejes_variante)]
    if copia:
        con.execute(respaldos.insert(), copia)
    _convertir(con, filas)

    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.drop_column('ejes_variante')


def _convertir(con, filas) -> None:
    atributos = _tabla(con, 'atributos')
    asignados = _tabla(con, 'atributo_familias')
    con.execute(atributos.update().where(atributos.c.nivel == 'PRODUCTO').values(general=True))
    nodos = {g.id: g for g in filas}
    filas_asignadas: set[tuple[int, int]] = set()
    for org in {g.organizacion_id for g in filas} | set(con.execute(sa.select(atributos.c.organizacion_id).distinct()).scalars()):
        de_variante = {a.codigo: a.id for a in con.execute(sa.select(atributos.c.id, atributos.c.codigo).where(
            atributos.c.organizacion_id == org, atributos.c.nivel == 'VARIANTE'))}
        familias = [g for g in filas if g.organizacion_id == org and g.clase == 'FAMILIA']
        if not de_variante:
            continue
        if not any(_lista(g.ejes_variante) for g in familias):
            con.execute(atributos.update().where(atributos.c.id.in_(de_variante.values())).values(general=True))
            continue

        def ruta(g):
            res, vistos = [], set()
            while g is not None and g.id not in vistos:
                res.insert(0, g)
                vistos.add(g.id)
                g = nodos.get(g.padre_id)
            return res

        def usaba(g) -> set[str]:
            for x in reversed(ruta(g)):
                if _lista(x.ejes_variante):
                    return {c for c in _lista(x.ejes_variante) if c in de_variante}
            return set(de_variante)

        generales = {c for c in de_variante if all(c in usaba(g) for g in familias)}
        if generales:
            con.execute(atributos.update().where(atributos.c.id.in_([de_variante[c] for c in generales])).values(general=True))
        # De la raíz a las hojas: cada familia recibe lo que usaba y su padre no le da
        nuevas: dict[int, set[str]] = {}
        for g in sorted(familias, key=lambda x: len(ruta(x))):
            padre = nodos.get(g.padre_id)
            del_padre = nuevas.get(padre.id, set()) if padre is not None else set()
            propias = usaba(g) - del_padre - generales
            nuevas[g.id] = del_padre | propias
            filas_asignadas |= {(de_variante[c], g.id) for c in propias}

    # Ningún valor guardado queda fuera: su atributo (no general) se asigna a la familia del producto
    gen = {a.id for a in con.execute(sa.select(atributos.c.id).where(atributos.c.general.is_(True)))}
    usados = con.execute(sa.text(
        "SELECT pa.atributo_id, p.grupo_producto_id FROM producto_atributos pa JOIN productos p ON p.id = pa.producto_id "
        "WHERE p.grupo_producto_id IS NOT NULL UNION "
        "SELECT aa.atributo_id, p.grupo_producto_id FROM articulo_atributos aa JOIN articulos a ON a.id = aa.articulo_id "
        "JOIN productos p ON p.id = a.producto_id WHERE p.grupo_producto_id IS NOT NULL")).all()

    def familia(gid):
        g = nodos.get(gid)
        return g.padre_id if g is not None and g.clase == 'CATEGORIA' else gid

    def cubre(atributo_id, gid) -> bool:
        vistos = set()
        while gid is not None and gid not in vistos:
            if (atributo_id, gid) in filas_asignadas:
                return True
            vistos.add(gid)
            gid = nodos[gid].padre_id if gid in nodos else None
        return False

    for atributo_id, gid in usados:
        if atributo_id not in gen and not cubre(atributo_id, gid) and familia(gid) is not None:
            filas_asignadas.add((atributo_id, familia(gid)))
    if filas_asignadas:
        con.execute(asignados.insert(), [{'atributo_id': a, 'grupo_id': g} for a, g in sorted(filas_asignadas)])


def downgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table('grupos_producto', schema=None) as b:
        b.add_column(sa.Column('ejes_variante', sa.JSON(), nullable=False, server_default='[]'))
    grupos = _tabla(con, 'grupos_producto')
    # Los ejes respaldados vuelven tal cual; una familia sin respaldo con atributos asignados toma
    # esos y los generales de variante (en el orden de los atributos); las demás quedan sin ejes
    respaldos = _tabla(con, 'respaldos_migracion')
    ejes: dict[int, list[str]] = {
        f.fila_id: _lista((f.datos if isinstance(f.datos, dict) else json.loads(f.datos)).get('ejes_variante'))
        for f in con.execute(sa.select(respaldos.c.fila_id, respaldos.c.datos).where(
            respaldos.c.migracion == revision, respaldos.c.tabla == 'grupos_producto'))}
    variante = con.execute(sa.text("SELECT id, organizacion_id, codigo, general FROM atributos WHERE nivel = 'VARIANTE' "
                                   "ORDER BY orden, codigo")).all()
    propios: dict[int, set[int]] = {}
    for gid, aid in con.execute(sa.text("SELECT grupo_id, atributo_id FROM atributo_familias")).all():
        propios.setdefault(gid, set()).add(aid)
    for g in con.execute(sa.select(grupos.c.id, grupos.c.organizacion_id)).all():
        if g.id not in ejes and propios.get(g.id, set()) & {a.id for a in variante}:
            ejes[g.id] = [a.codigo for a in variante if a.organizacion_id == g.organizacion_id
                          and (a.general or a.id in propios[g.id])]
    for gid, lista in ejes.items():
        con.execute(grupos.update().where(grupos.c.id == gid).values(ejes_variante=lista))
    op.drop_index('ix_atributo_familias_grupo_id', table_name='atributo_familias')
    op.drop_table('atributo_familias')
    with op.batch_alter_table('atributos', schema=None) as b:
        b.drop_column('general')
    con.execute(respaldos.delete().where(respaldos.c.migracion == revision))
