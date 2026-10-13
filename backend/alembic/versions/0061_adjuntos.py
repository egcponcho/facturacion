"""Adjuntos en una sola tabla y archivos fuera de la base

- adjuntos: nombre, clave en el almacén, tipo, tamaño y huella SHA-256 de
  cada archivo subido. Los archivos de la factura, las fotos y los documentos
  del producto pasan a referenciarlo (adjunto_id, único) en vez de repetir
  nombre, ruta, tamaño, tipo y quién lo subió.
- lotes_oficiales.contenido (el Excel completo en la base) pasa al almacén:
  clave_archivo.
- importaciones_oc.filas (la previa leída del archivo, en JSON) pasa al
  almacén: clave_filas.

Revision ID: 0061
Revises: 0060
Create Date: 2026-10-13 00:00:00
"""
import hashlib
import json
import mimetypes
import os
import uuid

from alembic import op
import sqlalchemy as sa

from app.instalacion.esquema import rls


revision = '0061'
down_revision = '0060'
branch_labels = None
depends_on = None

USOS = ('archivos', 'producto_fotos', 'producto_documentos')


def _directorio() -> str:
    from app.core.config import settings

    return settings.UPLOAD_DIR


def _guardar(contenido: bytes, carpeta: str, extension: str) -> str:
    destino = os.path.join(_directorio(), carpeta)
    os.makedirs(destino, exist_ok=True)
    clave = os.path.join(carpeta, uuid.uuid4().hex + extension)
    with open(os.path.join(_directorio(), clave), "wb") as fh:
        fh.write(contenido)
    return clave


def _huella(ruta: str) -> str | None:
    try:
        with open(ruta if os.path.isabs(ruta) else os.path.join(_directorio(), ruta), "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def upgrade() -> None:
    con = op.get_bind()
    op.create_table('adjuntos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=300), nullable=False),
    sa.Column('clave', sa.String(length=500), nullable=False),
    sa.Column('tipo_mime', sa.String(length=100), nullable=False),
    sa.Column('tamano', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('subido_por', sa.Integer(), nullable=True),
    sa.Column('subido_en', sa.DateTime(), nullable=False),
    sa.Column('organizacion_id', sa.Integer(), nullable=False),
    sa.Column('uso_id', sa.Integer(), nullable=True),  # temporal: fila de origen
    sa.Column('uso', sa.String(length=30), nullable=True),
    sa.CheckConstraint('tamano >= 0', name='ck_adjuntos_tamano'),
    sa.ForeignKeyConstraint(['organizacion_id'], ['organizaciones.id'], ),
    sa.ForeignKeyConstraint(['subido_por'], ['usuarios.id'], name='fk_adjuntos_subido_por'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('adjuntos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_adjuntos_organizacion_id'), ['organizacion_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_adjuntos_subido_por'), ['subido_por'], unique=False)

    # Una fila de adjunto por cada archivo, foto y documento existentes
    adjuntos = sa.table('adjuntos', *(sa.column(c) for c in (
        'nombre', 'clave', 'tipo_mime', 'tamano', 'sha256', 'subido_por', 'subido_en', 'organizacion_id', 'uso_id', 'uso')))
    for tabla in USOS:
        mime = "NULL" if tabla == 'archivos' else "tipo_mime"
        filas = con.execute(sa.text(f"SELECT id, nombre, ruta, {mime} AS tipo_mime, tamano, subido_por, subido_en, "
                                    f"organizacion_id FROM {tabla}")).mappings().all()
        if filas:
            op.bulk_insert(adjuntos, [{
                'nombre': f['nombre'], 'clave': f['ruta'],
                'tipo_mime': f['tipo_mime'] or mimetypes.guess_type(f['nombre'])[0] or 'application/octet-stream',
                'tamano': f['tamano'] or 0, 'sha256': _huella(f['ruta']), 'subido_por': f['subido_por'],
                'subido_en': f['subido_en'], 'organizacion_id': f['organizacion_id'], 'uso_id': f['id'], 'uso': tabla}
                for f in filas])
        with op.batch_alter_table(tabla, schema=None) as b:
            b.add_column(sa.Column('adjunto_id', sa.Integer(), nullable=True))
        con.execute(sa.text(f"UPDATE {tabla} SET adjunto_id = (SELECT a.id FROM adjuntos a WHERE a.uso = :t "
                            f"AND a.uso_id = {tabla}.id)"), {"t": tabla})
        with op.batch_alter_table(tabla, schema=None) as b:
            b.alter_column('adjunto_id', existing_type=sa.Integer(), nullable=False)
            b.create_index(b.f(f'ix_{tabla}_adjunto_id'), ['adjunto_id'], unique=True)
            b.create_foreign_key(f'fk_{tabla}_adjunto_id', 'adjuntos', ['adjunto_id'], ['id'])
            for c in ('nombre', 'ruta', 'tamano', 'subido_por', 'subido_en') + (() if tabla == 'archivos' else ('tipo_mime',)):
                b.drop_column(c)
    with op.batch_alter_table('adjuntos', schema=None) as b:
        b.drop_column('uso_id')
        b.drop_column('uso')
    rls(op, 'adjuntos')

    # El Excel de cada lote oficial, al almacén
    with op.batch_alter_table('lotes_oficiales', schema=None) as b:
        b.add_column(sa.Column('clave_archivo', sa.String(length=500), nullable=True))
    for lote_id, contenido in con.execute(sa.text("SELECT id, contenido FROM lotes_oficiales")).all():
        con.execute(sa.text("UPDATE lotes_oficiales SET clave_archivo = :c WHERE id = :i"),
                    {"c": _guardar(bytes(contenido or b""), "oficial", ".xlsx"), "i": lote_id})
    with op.batch_alter_table('lotes_oficiales', schema=None) as b:
        b.alter_column('clave_archivo', existing_type=sa.String(length=500), nullable=False)
        b.drop_column('contenido')

    # La previa de cada importación de OCs, al almacén
    with op.batch_alter_table('importaciones_oc', schema=None) as b:
        b.add_column(sa.Column('clave_filas', sa.String(length=500), nullable=True))
    for imp_id, filas in con.execute(sa.text("SELECT id, filas FROM importaciones_oc")).all():
        datos = json.loads(filas) if isinstance(filas, str) else (filas or [])
        con.execute(sa.text("UPDATE importaciones_oc SET clave_filas = :c WHERE id = :i"),
                    {"c": _guardar(json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8"), "importaciones", ".json"),
                     "i": imp_id})
    with op.batch_alter_table('importaciones_oc', schema=None) as b:
        b.drop_column('filas')


def _leer(clave: str | None) -> bytes:
    try:
        with open(clave if os.path.isabs(clave) else os.path.join(_directorio(), clave), "rb") as fh:
            return fh.read()
    except (OSError, TypeError):
        return b""


def downgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table('importaciones_oc', schema=None) as b:
        b.add_column(sa.Column('filas', sa.JSON(), nullable=True))
    for imp_id, clave in con.execute(sa.text("SELECT id, clave_filas FROM importaciones_oc")).all():
        con.execute(sa.text("UPDATE importaciones_oc SET filas = :f WHERE id = :i"),
                    {"f": _leer(clave).decode("utf-8") or "[]", "i": imp_id})
    with op.batch_alter_table('importaciones_oc', schema=None) as b:
        b.alter_column('filas', existing_type=sa.JSON(), nullable=False)
        b.drop_column('clave_filas')

    with op.batch_alter_table('lotes_oficiales', schema=None) as b:
        b.add_column(sa.Column('contenido', sa.LargeBinary(), nullable=True))
    for lote_id, clave in con.execute(sa.text("SELECT id, clave_archivo FROM lotes_oficiales")).all():
        con.execute(sa.text("UPDATE lotes_oficiales SET contenido = :c WHERE id = :i"), {"c": _leer(clave), "i": lote_id})
    with op.batch_alter_table('lotes_oficiales', schema=None) as b:
        b.alter_column('contenido', existing_type=sa.LargeBinary(), nullable=False)
        b.drop_column('clave_archivo')

    for tabla in USOS:
        with op.batch_alter_table(tabla, schema=None) as b:
            b.add_column(sa.Column('nombre', sa.String(length=300), nullable=True))
            b.add_column(sa.Column('ruta', sa.String(length=500), nullable=True))
            b.add_column(sa.Column('tamano', sa.Integer(), nullable=True))
            b.add_column(sa.Column('subido_por', sa.Integer(), nullable=True))
            b.create_foreign_key(f'fk_{tabla}_subido_por', 'usuarios', ['subido_por'], ['id'])
            b.add_column(sa.Column('subido_en', sa.DateTime(), nullable=True))
            if tabla != 'archivos':
                b.add_column(sa.Column('tipo_mime', sa.String(length=60), nullable=True))
        for c in ('nombre', 'tamano', 'subido_por', 'subido_en'):
            con.execute(sa.text(f"UPDATE {tabla} SET {c} = (SELECT a.{c} FROM adjuntos a WHERE a.id = {tabla}.adjunto_id)"))
        con.execute(sa.text(f"UPDATE {tabla} SET ruta = (SELECT a.clave FROM adjuntos a WHERE a.id = {tabla}.adjunto_id)"))
        if tabla != 'archivos':
            con.execute(sa.text(f"UPDATE {tabla} SET tipo_mime = (SELECT substr(a.tipo_mime, 1, 60) FROM adjuntos a "
                                f"WHERE a.id = {tabla}.adjunto_id)"))
        with op.batch_alter_table(tabla, schema=None) as b:
            tipos = {'nombre': sa.String(300), 'ruta': sa.String(500), 'tamano': sa.Integer(), 'subido_en': sa.DateTime(),
                     'tipo_mime': sa.String(60)}
            for c in ('nombre', 'ruta', 'tamano', 'subido_en') + (() if tabla == 'archivos' else ('tipo_mime',)):
                b.alter_column(c, existing_type=tipos[c], nullable=False)
            b.drop_constraint(f'fk_{tabla}_adjunto_id', type_='foreignkey')
            b.drop_index(b.f(f'ix_{tabla}_adjunto_id'))
            b.drop_column('adjunto_id')
    op.drop_table('adjuntos')
