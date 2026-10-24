"""La ficha de comercio exterior vive aparte del producto del catálogo
(producto_comex, 1:1): todo producto tiene la suya, se borra con él y la
migración 0096 la saca de productos sin perder datos."""
import sqlite3
import subprocess
import sys
import tempfile

from sqlalchemy import select
from test_oficial import RAIZ

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion
from app.modelos import Producto, ProductoComex


def test_todo_producto_tiene_su_ficha_y_se_borra_con_el(client):
    with en_organizacion(1), SessionLocal() as db:
        p = Producto(codigo_generico="COMEX-1", nombre="Prueba")
        db.add(p)
        db.flush()
        assert p.comex is not None and p.comex.estado == "borrador" and p.comex.ficha == {}
        assert db.get(ProductoComex, p.id) is p.comex and p.comex.organizacion_id == p.organizacion_id
        # Los datos de clasificación se escriben desde la ficha y crean su fila
        p.comex.sugerido = "990011"
        db.flush()
        assert p.clasificacion is not None and p.clasificacion.sugerido == "990011"
        assert db.scalar(select(ProductoComex.producto_id).where(ProductoComex.sugerido == "990011")) == p.id
        db.delete(p)
        db.flush()
        assert db.get(ProductoComex, p.id) is None
        db.rollback()


def test_migracion_saca_la_ficha_de_productos():
    """0096: tipo, ficha, estado, código aprobado… pasan a producto_comex; revertir los devuelve."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        r = subprocess.run(alembic + ["upgrade", "0095"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        c = sqlite3.connect(f"{tmp}/m.db")
        if not c.execute("SELECT id FROM organizaciones WHERE id = 1").fetchone():
            c.execute("INSERT INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en)"
                      " VALUES (1, 'UNO', 'UNO', '{}', 1, '2026-01-01')")
        c.execute("INSERT INTO productos (id, organizacion_id, codigo_generico, nombre, tipo, ficha, faltan, ficha_completa,"
                  " version_ficha, estado, codigo, sac_codigo, pais_origen, descripcion_comercial, notas, creado_en,"
                  " actualizado_en, version) VALUES (301, 1, 'G301', 'Zapato', 'calzado', '{\"uso\": \"x\"}', '[]', 1,"
                  " 2, 'aprobado', '640411', '64041100', 'VN', 'Zapato de lona', 'nota', '2026-01-01', '2026-01-01', 1)")
        c.commit()
        r = subprocess.run(alembic + ["upgrade", "0096"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert c.execute("SELECT producto_id, organizacion_id, tipo, ficha, estado, codigo, sac_codigo, pais_origen,"
                         " descripcion_comercial, notas, version_ficha, ficha_completa FROM producto_comex").fetchall() == [
            (301, 1, "calzado", '{"uso": "x"}', "aprobado", "640411", "64041100", "VN", "Zapato de lona", "nota", 2, 1)]
        cols = {x[1] for x in c.execute("PRAGMA table_info(productos)")}
        assert {"codigo_generico", "nombre"} <= cols and not {"tipo", "ficha", "estado", "codigo", "pais_origen"} & cols
        r = subprocess.run(alembic + ["downgrade", "0095"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert c.execute("SELECT tipo, estado, codigo, pais_origen, version_ficha FROM productos WHERE id = 301").fetchall() == [
            ("calzado", "aprobado", "640411", "VN", 2)]
        assert not c.execute("SELECT name FROM sqlite_master WHERE name = 'producto_comex'").fetchall()
        c.close()


def test_la_familia_elige_la_categoria_aduanera_de_sus_fichas(admin):
    """Sección «comex» de la familia: la categoría con que empiezan las fichas de sus productos;
    la subfamilia la hereda y el motor la usa mientras la ficha no tenga la suya."""
    from test_grupos_producto import _grupo

    from app.modelos import CategoriaProducto
    from app.modulos.productos.productos import entrada_producto

    fam = _grupo(admin, codigo="GP-CX", nombre="Customs family")
    sub = _grupo(admin, codigo="GP-CX-S", nombre="Customs subfamily", padre_id=fam["id"])
    with SessionLocal() as db:
        cat = db.scalar(select(CategoriaProducto.codigo).where(CategoriaProducto.activo.is_(True)).limit(1))
    secciones = {s["clave"]: s for s in admin.get(f"/grupos-producto/{fam['id']}/secciones").json()}
    assert secciones["comex"]["editable"] and secciones["comex"]["datos"]["efectiva"] is None
    assert cat in {c["codigo"] for c in secciones["comex"]["datos"]["categorias"]}
    assert admin.put(f"/grupos-producto/{fam['id']}/secciones/comex", {"categoria": "NO-EXISTE"}).status_code == 422
    r = admin.put(f"/grupos-producto/{fam['id']}/secciones/comex", {"categoria": cat})
    assert r.status_code == 200 and r.json()["datos"]["categoria"] == cat
    de_sub = next(s for s in admin.get(f"/grupos-producto/{sub['id']}/secciones").json() if s["clave"] == "comex")
    assert de_sub["datos"]["categoria"] is None and de_sub["datos"]["efectiva"] == cat and de_sub["datos"]["heredada"]
    with en_organizacion(1), SessionLocal() as db:
        p = Producto(codigo_generico="COMEX-CAT", nombre="Prueba", grupo_producto_id=sub["id"])
        db.add(p)
        db.flush()
        assert entrada_producto(p)["categoria"] == cat
        p.comex.tipo = "PROPIA"
        assert entrada_producto(p)["categoria"] == "PROPIA"
        db.rollback()
    # Vacía, vuelve a no tener (y la subfamilia tampoco)
    assert admin.put(f"/grupos-producto/{fam['id']}/secciones/comex", {"categoria": None}).json()["datos"]["efectiva"] is None
