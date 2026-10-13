"""Lead time: cada paso pertenece a un documento; revisión de documentos del embarque

- pasos_leadtime.documento: qué documento debe cumplir el paso (OC, factura,
  lista de empaque o embarque). Los pasos con fecha medida toman el documento
  que la registra; los demás, el del paso medido que los precede en la regla
  global (aduana tras el arribo → embarque) o la OC si van primero. Se pueden
  cambiar en el catálogo.
- Hito y evento nuevo del embarque: revisión y entrega de documentos
  (DOCUMENTOS), que se registra en tránsito o al arribo.

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-13 00:00:00
"""
import json

import sqlalchemy as sa

from alembic import op

revision = '0067'
down_revision = '0066'
branch_labels = None
depends_on = None

DOCUMENTO_HITO = {"lib_logistica": "OC", "xf": "OC", "salida": "EMBARQUE", "documentos": "EMBARQUE",
                  "arribo": "EMBARQUE", "entrega": "EMBARQUE", "ingreso": "EMBARQUE", "tienda": "OC"}


def upgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table('pasos_leadtime', schema=None) as b:
        b.add_column(sa.Column('documento', sa.String(length=10), nullable=True))
    for hito, doc in DOCUMENTO_HITO.items():
        con.execute(sa.text("UPDATE pasos_leadtime SET documento = :d WHERE hito = :h"), {"d": doc, "h": hito})
    # Pasos sin fecha medida: el documento del paso medido anterior en la regla global
    for (org,) in con.execute(sa.text("SELECT id FROM organizaciones")).all():
        pasos = {c: (h, d) for c, h, d in con.execute(sa.text(
            "SELECT codigo, hito, documento FROM pasos_leadtime WHERE organizacion_id = :o"), {"o": org}).all()}
        for (datos,) in con.execute(sa.text("SELECT pasos FROM reglas_leadtime WHERE organizacion_id = :o "
                                            "AND nivel = 'GLOBAL' ORDER BY id"), {"o": org}).all():
            datos = json.loads(datos) if isinstance(datos, str) else (datos or {})
            orden = datos.get("orden") or [x.get("paso") for x in datos.get("pasos") or []]
            doc = "OC"
            for codigo in orden:
                hito, actual = pasos.get(codigo, (None, None))
                if hito in DOCUMENTO_HITO:
                    doc = DOCUMENTO_HITO[hito]
                elif codigo in pasos and actual is None:
                    con.execute(sa.text("UPDATE pasos_leadtime SET documento = :d WHERE organizacion_id = :o "
                                        "AND codigo = :c"), {"d": doc, "o": org, "c": codigo})
                    pasos[codigo] = (hito, doc)
    con.execute(sa.text("UPDATE pasos_leadtime SET documento = 'OC' WHERE documento IS NULL"))
    with op.batch_alter_table('pasos_leadtime', schema=None) as b:
        b.create_check_constraint('ck_pasos_leadtime_documento',
                                  "documento IS NULL OR documento IN ('OC', 'FACTURA', 'PL', 'EMBARQUE')")
    # El evento de revisión y entrega de documentos en la lista de cada empresa
    for (org,) in con.execute(sa.text("SELECT id FROM organizaciones")).all():
        ya = con.execute(sa.text("SELECT 1 FROM valores_lista WHERE organizacion_id = :o AND lista = 'evento_embarque' "
                                 "AND codigo = 'DOCUMENTOS'"), {"o": org}).first()
        if ya:
            continue
        # En su lugar del proceso: después de «En tránsito» (o al final si no está)
        tras = con.execute(sa.text("SELECT orden FROM valores_lista WHERE organizacion_id = :o "
                                   "AND lista = 'evento_embarque' AND codigo = 'TRANSITO'"), {"o": org}).scalar()
        if tras is None:
            orden = con.execute(sa.text("SELECT COALESCE(MAX(orden), 0) + 1 FROM valores_lista WHERE organizacion_id = :o "
                                        "AND lista = 'evento_embarque'"), {"o": org}).scalar()
        else:
            orden = tras + 1
            con.execute(sa.text("UPDATE valores_lista SET orden = orden + 1 WHERE organizacion_id = :o "
                                "AND lista = 'evento_embarque' AND orden >= :n"), {"o": org, "n": orden})
        con.execute(sa.text("INSERT INTO valores_lista (organizacion_id, lista, codigo, nombre, orden, activo, estados) "
                            "VALUES (:o, 'evento_embarque', 'DOCUMENTOS', 'Document review and delivery', :n, :a, "
                            "'EN_TRANSITO,ARRIBADO')"), {"o": org, "n": orden, "a": True})


def downgrade() -> None:
    con = op.get_bind()
    for org, orden in con.execute(sa.text("SELECT organizacion_id, orden FROM valores_lista WHERE lista = 'evento_embarque' "
                                          "AND codigo = 'DOCUMENTOS'")).all():
        con.execute(sa.text("DELETE FROM valores_lista WHERE organizacion_id = :o AND lista = 'evento_embarque' "
                            "AND codigo = 'DOCUMENTOS'"), {"o": org})
        con.execute(sa.text("UPDATE valores_lista SET orden = orden - 1 WHERE organizacion_id = :o "
                            "AND lista = 'evento_embarque' AND orden > :n"), {"o": org, "n": orden})
    with op.batch_alter_table('pasos_leadtime', schema=None) as b:
        b.drop_constraint('ck_pasos_leadtime_documento', type_='check')
        b.drop_column('documento')
