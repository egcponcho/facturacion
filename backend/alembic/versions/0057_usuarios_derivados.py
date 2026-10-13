"""Usuarios: tipo y empresa derivados, alcance en tablas de asociación

- usuarios.rol (texto heredado, que duplicaba el tipo del rol asignado) se
  elimina: el tipo se deriva del rol y del proveedor. Un usuario sin rol
  asignado recibe el rol de fábrica de su tipo.
- usuarios.empresa (texto que duplicaba el proveedor o la organización) se
  elimina: se deriva de ellos.
- usuarios.alcance (JSON con ids y códigos sin integridad) pasa a
  usuario_proveedores, usuario_sociedades y usuario_transportistas.

Revision ID: 0057
Revises: 0056
Create Date: 2026-10-13 00:00:00
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    con = op.get_bind()
    op.create_table('usuario_proveedores',
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('proveedor_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['proveedor_id'], ['proveedores.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('usuario_id', 'proveedor_id')
    )
    with op.batch_alter_table('usuario_proveedores', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usuario_proveedores_proveedor_id'), ['proveedor_id'], unique=False)

    op.create_table('usuario_sociedades',
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('sociedad_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['sociedad_id'], ['sociedades.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('usuario_id', 'sociedad_id')
    )
    with op.batch_alter_table('usuario_sociedades', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usuario_sociedades_sociedad_id'), ['sociedad_id'], unique=False)

    op.create_table('usuario_transportistas',
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('transportista_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['transportista_id'], ['transportistas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('usuario_id', 'transportista_id')
    )
    with op.batch_alter_table('usuario_transportistas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_usuario_transportistas_transportista_id'), ['transportista_id'], unique=False)

    for uid, org, rol in con.execute(sa.text("SELECT id, organizacion_id, rol FROM usuarios WHERE rol_id IS NULL")).all():
        rid = con.execute(sa.text("SELECT id FROM roles WHERE organizacion_id = :o AND sistema = :si AND tipo = :t ORDER BY id"),
                          {"o": org, "si": True, "t": rol}).scalar()
        if rid is None:
            raise RuntimeError(f"El usuario {uid} no tiene rol y su organización no tiene el rol de fábrica «{rol}»: "
                               "asígnele un rol antes de migrar.")
        con.execute(sa.text("UPDATE usuarios SET rol_id = :r WHERE id = :u"), {"r": rid, "u": uid})
    for uid, org, alcance in con.execute(sa.text("SELECT id, organizacion_id, alcance FROM usuarios")).all():
        a = json.loads(alcance) if isinstance(alcance, str) else (alcance or {})
        for pid in a.get("proveedores") or []:
            if con.execute(sa.text("SELECT 1 FROM proveedores WHERE id = :p"), {"p": int(pid)}).first():
                con.execute(sa.text("INSERT INTO usuario_proveedores (usuario_id, proveedor_id) VALUES (:u, :p)"), {"u": uid, "p": int(pid)})
        for tid in a.get("transportistas") or []:
            if con.execute(sa.text("SELECT 1 FROM transportistas WHERE id = :t"), {"t": int(tid)}).first():
                con.execute(sa.text("INSERT INTO usuario_transportistas (usuario_id, transportista_id) VALUES (:u, :t)"),
                            {"u": uid, "t": int(tid)})
        for codigo in a.get("sociedades") or []:
            sid = con.execute(sa.text("SELECT id FROM sociedades WHERE organizacion_id = :o AND codigo = :c"),
                              {"o": org, "c": str(codigo)}).scalar()
            if sid:
                con.execute(sa.text("INSERT INTO usuario_sociedades (usuario_id, sociedad_id) VALUES (:u, :s)"), {"u": uid, "s": sid})
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.drop_column('alcance')
        b.drop_column('rol')
        b.drop_column('empresa')


def downgrade() -> None:
    con = op.get_bind()
    with op.batch_alter_table('usuarios', schema=None) as b:
        b.add_column(sa.Column('empresa', sa.String(length=200), nullable=True))
        b.add_column(sa.Column('rol', sa.String(length=20), nullable=False, server_default='interno'))
        b.add_column(sa.Column('alcance', sa.JSON(), nullable=False, server_default='{}'))
    for uid, prov, permisos in con.execute(sa.text(
            "SELECT u.id, u.proveedor_id, r.permisos FROM usuarios u LEFT JOIN roles r ON r.id = u.rol_id")).all():
        p = json.loads(permisos) if isinstance(permisos, str) else (permisos or [])
        rol = "proveedor" if prov else ("admin" if "admin" in p else "interno")
        a = {"proveedores": [x for (x,) in con.execute(sa.text("SELECT proveedor_id FROM usuario_proveedores WHERE usuario_id = :u"), {"u": uid})],
             "sociedades": [x for (x,) in con.execute(sa.text("SELECT s.codigo FROM usuario_sociedades us JOIN sociedades s ON s.id = us.sociedad_id "
                                                               "WHERE us.usuario_id = :u"), {"u": uid})],
             "transportistas": [x for (x,) in con.execute(sa.text("SELECT transportista_id FROM usuario_transportistas WHERE usuario_id = :u"),
                                                          {"u": uid})]}
        con.execute(sa.text("UPDATE usuarios SET rol = :r, alcance = :a WHERE id = :u"),
                    {"r": rol, "a": json.dumps({k: v for k, v in a.items() if v}), "u": uid})
    for tabla, col in (("usuario_transportistas", "transportista_id"), ("usuario_sociedades", "sociedad_id"),
                       ("usuario_proveedores", "proveedor_id")):
        with op.batch_alter_table(tabla, schema=None) as b:
            b.drop_index(b.f(f'ix_{tabla}_{col}'))
        op.drop_table(tabla)
