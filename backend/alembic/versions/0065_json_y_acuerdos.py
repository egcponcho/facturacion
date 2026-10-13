"""Texto estructurado a JSON y países de los acuerdos en tablas

- reglas_leadtime.pasos: el JSON guardado como texto pasa a columna JSON.
- escalas_talla.tallas: la lista escrita («6, 6.5, 7-10, 12=120») pasa a
  JSON ya expandido: [{"talla": "6", "codigo": null}, …]. El formulario la
  sigue mostrando y recibiendo como texto.
- acuerdos_comerciales.origenes / destinos (ISO separados por coma, sin
  integridad) pasan a acuerdo_origenes y acuerdo_destinos, con llave al
  catálogo de países.

Revision ID: 0065
Revises: 0064
Create Date: 2026-10-13 00:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0065'
down_revision = '0064'
branch_labels = None
depends_on = None


def _tallas(texto: str) -> list[dict]:
    from app.modulos.maestros.tallas import tallas_de

    return [{"talla": t, "codigo": c} for t, c in tallas_de(texto)]


def _pasos(texto) -> dict:
    try:
        d = json.loads(texto) if isinstance(texto, str) else (texto or {})
    except ValueError:
        d = {}
    if isinstance(d, list):
        d = {"pasos": d}
    return {"pasos": [p for p in d.get("pasos") or [] if isinstance(p, dict)], "orden": d.get("orden") or None}


def upgrade() -> None:
    con = op.get_bind()
    postgres = con.dialect.name == "postgresql"
    for tabla, col, convertir in (('escalas_talla', 'tallas', _tallas), ('reglas_leadtime', 'pasos', _pasos)):
        for fila_id, valor in con.execute(sa.text(f"SELECT id, {col} FROM {tabla}")).all():
            con.execute(sa.text(f"UPDATE {tabla} SET {col} = :v WHERE id = :i"),
                        {"v": json.dumps(convertir(valor), ensure_ascii=False), "i": fila_id})
        with op.batch_alter_table(tabla, schema=None) as b:
            kw = {"postgresql_using": f"{col}::json"} if postgres else {}
            b.alter_column(col, existing_type=sa.TEXT(), type_=sa.JSON(), existing_nullable=False, **kw)

    for rol in ('origenes', 'destinos'):
        op.create_table(f'acuerdo_{rol}',
        sa.Column('acuerdo_id', sa.Integer(), nullable=False),
        sa.Column('pais_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['acuerdo_id'], ['acuerdos_comerciales.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pais_id'], ['paises.id'], ),
        sa.PrimaryKeyConstraint('acuerdo_id', 'pais_id')
        )
        with op.batch_alter_table(f'acuerdo_{rol}', schema=None) as batch_op:
            batch_op.create_index(batch_op.f(f'ix_acuerdo_{rol}_pais_id'), ['pais_id'], unique=False)
    paises = dict(con.execute(sa.text("SELECT codigo, id FROM paises")).all())
    for acuerdo_id, origenes, destinos in con.execute(sa.text("SELECT id, origenes, destinos FROM acuerdos_comerciales")).all():
        for rol, texto in (('origenes', origenes), ('destinos', destinos)):
            codigos = {c.strip().upper() for c in (texto or "").split(",") if c.strip()}
            faltan = sorted(codigos - set(paises))
            if faltan:
                raise RuntimeError(f"Acuerdo {acuerdo_id}: los países {faltan} no están en el catálogo; agréguelos primero.")
            for c in sorted(codigos):
                con.execute(sa.text(f"INSERT INTO acuerdo_{rol} (acuerdo_id, pais_id) VALUES (:a, :p)"),
                            {"a": acuerdo_id, "p": paises[c]})
    with op.batch_alter_table('acuerdos_comerciales', schema=None) as batch_op:
        batch_op.drop_column('destinos')
        batch_op.drop_column('origenes')


def downgrade() -> None:
    con = op.get_bind()
    postgres = con.dialect.name == "postgresql"
    with op.batch_alter_table('acuerdos_comerciales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origenes', sa.String(length=400), nullable=True))
        batch_op.add_column(sa.Column('destinos', sa.String(length=100), nullable=True))
    for (acuerdo_id,) in con.execute(sa.text("SELECT id FROM acuerdos_comerciales")).all():
        valores = {}
        for rol in ('origenes', 'destinos'):
            valores[rol] = ",".join(c for (c,) in con.execute(sa.text(
                f"SELECT p.codigo FROM acuerdo_{rol} x JOIN paises p ON p.id = x.pais_id WHERE x.acuerdo_id = :a "
                "ORDER BY p.codigo"), {"a": acuerdo_id}))
        con.execute(sa.text("UPDATE acuerdos_comerciales SET origenes = :o, destinos = :d WHERE id = :a"),
                    {"o": valores['origenes'], "d": valores['destinos'], "a": acuerdo_id})
    con.execute(sa.text("UPDATE acuerdos_comerciales SET origenes = '' WHERE origenes IS NULL"))
    con.execute(sa.text("UPDATE acuerdos_comerciales SET destinos = '' WHERE destinos IS NULL"))
    with op.batch_alter_table('acuerdos_comerciales', schema=None) as batch_op:
        batch_op.alter_column('origenes', existing_type=sa.String(length=400), nullable=False)
        batch_op.alter_column('destinos', existing_type=sa.String(length=100), nullable=False)
    op.drop_table('acuerdo_origenes')
    op.drop_table('acuerdo_destinos')

    for tabla, col in (('reglas_leadtime', 'pasos'), ('escalas_talla', 'tallas')):
        with op.batch_alter_table(tabla, schema=None) as b:
            kw = {"postgresql_using": f"{col}::text"} if postgres else {}
            b.alter_column(col, existing_type=sa.JSON(), type_=sa.TEXT(), existing_nullable=False, **kw)
    for fila_id, valor in con.execute(sa.text("SELECT id, tallas FROM escalas_talla")).all():
        lista = json.loads(valor) if isinstance(valor, str) else (valor or [])
        texto = ", ".join(f"{x['talla']}={x['codigo']}" if x.get("codigo") else x["talla"] for x in lista)
        con.execute(sa.text("UPDATE escalas_talla SET tallas = :t WHERE id = :i"), {"t": texto, "i": fila_id})
