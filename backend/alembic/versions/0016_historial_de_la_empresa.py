"""Capas separadas: historial de la empresa fuera de las líneas oficiales

- Tabla historial_clasificacion (COMPANY KNOWLEDGE).
- Las líneas nacionales que no venían de una fuente oficial (base de artículos
  de la empresa, aprendidas, escritas a mano o de un archivo sin fuente) pasan
  al historial y se quitan de incisos_nacionales.
- Las líneas oficiales copiadas del ACI quedan en la versión regional con su
  fuente; su país se marca nivel_base SAC10.
- Las condiciones de selección que la base de la empresa había puesto sobre
  líneas oficiales pasan al historial; quedan solo las que el clasificador lee
  del texto oficial, como reglas del motor (CLASSIFIER), nunca legales.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-07 12:00:00
"""
import json
from datetime import datetime
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None

ACI = Path(__file__).resolve().parents[2] / "app" / "data" / "aci_incisos.json"


def _cond(con, regla_id) -> dict:
    out = {}
    for campo, operador, valor in con.execute(sa.text("SELECT campo, operador, valor FROM reglas_condiciones WHERE regla_id = :r"), {"r": regla_id}):
        v = json.loads(valor) if isinstance(valor, str) else valor
        out[campo] = v
    return out


def upgrade() -> None:
    op.create_table(
        'historial_clasificacion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pais', sa.String(length=2), nullable=True),
        sa.Column('codigo', sa.String(length=14), nullable=False),
        sa.Column('sub6', sa.String(length=6), nullable=False),
        sa.Column('categoria', sa.String(length=40), nullable=True),
        sa.Column('condiciones', sa.JSON(), nullable=False),
        sa.Column('origen', sa.String(length=12), nullable=False),
        sa.Column('conteo', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=True),
        sa.Column('nota', sa.String(length=300), nullable=True),
        sa.Column('creado_por', sa.Integer(), nullable=True),
        sa.Column('creado_en', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['creado_por'], ['usuarios.id']),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('historial_clasificacion', schema=None) as b:
        b.create_index('ix_historial_clasificacion_pais', ['pais'], unique=False)
        b.create_index('ix_historial_clasificacion_codigo', ['codigo'], unique=False)
        b.create_index('ix_historial_clasificacion_sub6', ['sub6'], unique=False)

    con = op.get_bind()
    hist = sa.table("historial_clasificacion", *(sa.column(c) for c in ("pais", "codigo", "sub6", "condiciones", "origen", "conteo", "nota",
                                                                         "creado_por", "creado_en")))
    ahora = datetime.utcnow()
    origen_de = {"aprendido": "ENSENADO"}

    # 1. Líneas sin procedencia oficial → historial de la empresa
    filas = con.execute(sa.text("SELECT id, pais, codigo, fuente, nota, creado_por FROM incisos_nacionales "
                                "WHERE fuente <> 'oficial' OR (fuente_id IS NULL AND version_id IS NULL)")).all()
    for iid, pais, codigo, fuente, nota, creado_por in filas:
        regla = con.execute(sa.text("SELECT id FROM reglas_clasificacion WHERE inciso_id = :i"), {"i": iid}).scalar()
        cond = _cond(con, regla) if regla else {}
        con.execute(hist.insert().values(pais=pais, codigo=codigo, sub6=codigo[:6], condiciones=cond, origen=origen_de.get(fuente, "IMPORTADO"),
                                         conteo=1, nota=(f"Former national code ({fuente}). " + (nota or ""))[:300], creado_por=creado_por, creado_en=ahora))
        if regla:
            con.execute(sa.text("DELETE FROM reglas_condiciones WHERE regla_id = :r"), {"r": regla})
            con.execute(sa.text("DELETE FROM reglas_clasificacion WHERE id = :r"), {"r": regla})
        con.execute(sa.text("UPDATE partidas_pais SET inciso_id = NULL WHERE inciso_id = :i"), {"i": iid})
        con.execute(sa.text("DELETE FROM overrides_arancel WHERE tipo = 'INCISO' AND objetivo = :o"), {"o": str(iid)})
        con.execute(sa.text("DELETE FROM incisos_nacionales WHERE id = :i"), {"i": iid})

    # 2. Líneas oficiales del ACI puestas en una versión nacional «dinámica» sin datos propios → versión regional
    reg = con.execute(sa.text("SELECT id, fuente_id FROM versiones_dataset WHERE ambito = 'REGIONAL' AND estado = 'PUBLICADA' "
                              "ORDER BY vigente_desde DESC, id DESC")).first()
    if reg:
        dinamicas = [r[0] for r in con.execute(sa.text("SELECT id FROM versiones_dataset WHERE estado = 'DINAMICA'"))]
        en_arbol = {r[0] for r in con.execute(sa.text("SELECT codigo_norm FROM nodos_arancel WHERE version_id = :v AND nivel = 'INCISO'"),
                                              {"v": reg[0]})}
        paises = set()
        for iid, pais, codigo, vid in con.execute(sa.text("SELECT id, pais, codigo, version_id FROM incisos_nacionales WHERE fuente = 'oficial'")).all():
            if (vid is None or vid in dinamicas) and codigo in en_arbol:
                con.execute(sa.text("UPDATE incisos_nacionales SET version_id = :v, fuente_id = COALESCE(fuente_id, :f) WHERE id = :i"),
                            {"v": reg[0], "f": reg[1], "i": iid})
                paises.add(pais)
        for iso in paises:
            con.execute(sa.text("UPDATE paises_arancel SET nivel_base = 'SAC10' WHERE iso = :p"), {"p": iso})

    # 3. Condiciones de selección sobre líneas oficiales: solo las que el clasificador lee del texto oficial
    interpretacion = {x["codigo"]: x["cond"] for x in json.loads(ACI.read_text(encoding="utf-8")) if x.get("cond")} if ACI.exists() else {}
    reglas = con.execute(sa.text("SELECT r.id, i.pais, i.codigo FROM reglas_clasificacion r JOIN incisos_nacionales i ON i.id = r.inciso_id "
                                 "WHERE r.tipo_regla = 'NATIONAL_SELECT' AND r.tipo_fuente IN ('LEARNED', 'NATIONAL_TARIFF')")).all()
    for rid, pais, codigo in reglas:
        cond = _cond(con, rid)
        texto = interpretacion.get(codigo)
        if texto and cond == texto:
            con.execute(sa.text("UPDATE reglas_clasificacion SET tipo_fuente = 'CLASSIFIER' WHERE id = :r"), {"r": rid})
            continue
        if cond:
            con.execute(hist.insert().values(pais=pais, codigo=codigo, sub6=codigo[:6], condiciones=cond, origen="IMPORTADO", conteo=1,
                                             nota="Selection conditions from the company item base (moved out of the official line)",
                                             creado_en=ahora))
        con.execute(sa.text("DELETE FROM reglas_condiciones WHERE regla_id = :r"), {"r": rid})
        if texto:
            for campo, valor in texto.items():
                con.execute(sa.text("INSERT INTO reglas_condiciones (regla_id, grupo, campo, operador, valor, negado) "
                                    "VALUES (:r, 1, :c, 'EQUAL', :v, :n)"), {"r": rid, "c": campo, "v": json.dumps(valor), "n": False})
            con.execute(sa.text("UPDATE reglas_clasificacion SET tipo_fuente = 'CLASSIFIER' WHERE id = :r"), {"r": rid})
        else:
            con.execute(sa.text("DELETE FROM reglas_clasificacion WHERE id = :r"), {"r": rid})


def downgrade() -> None:
    with op.batch_alter_table('historial_clasificacion', schema=None) as b:
        b.drop_index('ix_historial_clasificacion_sub6')
        b.drop_index('ix_historial_clasificacion_codigo')
        b.drop_index('ix_historial_clasificacion_pais')
    op.drop_table('historial_clasificacion')
