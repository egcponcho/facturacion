"""Grupos de producto: un solo árbol de familias y categorías, compartido por el
etiquetado y las reglas de empaque (migración 0081, alternativa A)."""
import sqlite3
import subprocess
import sys
import tempfile

from conftest import Api
from test_empaque_recetas import _oc, _receta
from test_oficial import RAIZ

from app.core.db import SessionLocal


def _grupo(api: Api, **d) -> dict:
    r = api.post("/grupos-producto", d)
    assert r.status_code == 200, r.text
    return r.json()


def test_el_arbol_es_el_mismo_que_ven_las_familias_y_categorias(admin):
    fam = _grupo(admin, codigo="GP-CALZ", nombre="Shared footwear")
    sub = _grupo(admin, codigo="GP-CALZ-TEC", nombre="Shared technical", padre_id=fam["id"])
    cat = _grupo(admin, clase="CATEGORIA", codigo="GP-SAND", nombre="Shared sandals", padre_id=fam["id"],
                 condiciones=[{"campo": "articulo.descripcion", "op": "contiene", "valor": "sandal"}])
    assert sub["ruta"] == "Shared footwear / Shared technical" and cat["clase"] == "CATEGORIA"
    # El etiquetado los ve como sus familias y categorías
    familias = {f["id"]: f for f in admin.get("/etiquetas/familias").json()}
    assert fam["id"] in familias and familias[sub["id"]]["padre_id"] == fam["id"] and cat["id"] not in familias
    cats = {c["id"]: c for c in admin.get("/etiquetas/categorias").json()}
    assert cats[cat["id"]]["familia_id"] == fam["id"]
    # El código es único en todo el árbol (familias y categorías)
    r = admin.post("/etiquetas/familias", {"codigo": "GP-SAND", "nombre": "Clash"})
    assert r.status_code == 422 and "Another family or category has this code." in r.text
    assert admin.post("/grupos-producto", {"codigo": "gp-calz", "nombre": "Clash"}).status_code == 422
    # Una categoría va dentro de una familia; una familia no puede quedar dentro de sí misma
    assert admin.post("/grupos-producto", {"clase": "CATEGORIA", "codigo": "GP-SUELTA", "nombre": "Loose"}).status_code == 422
    assert admin.post("/grupos-producto", {"clase": "CATEGORIA", "codigo": "GP-X", "nombre": "X",
                                           "padre_id": cat["id"]}).status_code == 422
    assert admin.patch(f"/grupos-producto/{fam['id']}", {"padre_id": sub["id"]}).status_code == 422
    # Solo una categoría se reconoce por condiciones
    assert admin.patch(f"/grupos-producto/{sub['id']}", {"condiciones": [
        {"campo": "articulo.descripcion", "op": "contiene", "valor": "x"}]}).status_code == 422
    # Lo que se usa no se borra: se desactiva
    assert admin.delete_(f"/grupos-producto/{fam['id']}").status_code == 409
    assert admin.patch(f"/grupos-producto/{fam['id']}", {"activa": False}).json()["activa"] is False
    assert admin.delete_(f"/grupos-producto/{cat['id']}").status_code == 200
    arbol = admin.get("/grupos-producto").json()
    ids = [g["id"] for g in arbol]
    assert ids.index(fam["id"]) < ids.index(sub["id"]) and cat["id"] not in ids


def test_proveedor_no_ve_el_arbol(vans):
    assert vans.get("/grupos-producto").status_code == 403
    assert vans.post("/grupos-producto", {"codigo": "X", "nombre": "X"}).status_code == 403


def _posicion_con_familia(api: Api):
    """Una posición de la demo cuyo artículo tiene familia, con su OC y la familia."""
    from app.modelos import PosicionOC

    for numero in ("4400003901", "4400003902", "4400003903"):
        oc = _oc(api, numero)
        with SessionLocal() as db:
            for p in oc["posiciones"]:
                x = db.get(PosicionOC, p["id"])
                f = x.articulo.familia_efectiva if x and x.articulo else None
                if f is not None:
                    return oc, p, f.id, x.articulo.sku
    raise AssertionError("La demo no tiene artículos con familia")


def test_regla_de_empaque_por_categoria_gana_sobre_su_familia(admin):
    """Las reglas de empaque recorren los grupos del artículo como el etiquetado: su categoría
    (reconocida por condiciones) es más específica que su familia."""
    oc, pos, familia_id, sku = _posicion_con_familia(admin)
    cat = _grupo(admin, clase="CATEGORIA", codigo="GP-CAT-EMP", nombre="Packing category", padre_id=familia_id,
                 condiciones=[{"campo": "articulo.sku", "op": "igual", "valor": sku}])
    de_familia = _receta(admin, "GP-FAM", [("CAJA", 10)])
    de_categoria = _receta(admin, "GP-CAT", [("CAJA", 5)])
    creadas = []
    try:
        for receta, grupo in ((de_familia, familia_id), (de_categoria, cat["id"])):
            r = admin.post("/reglas-empaque", {"receta_id": receta["id"], "destino": "GRUPO", "grupo_id": grupo})
            assert r.status_code == 200, r.text
            creadas.append(r.json()["id"])
        filas = admin.post("/reglas-empaque/probar", {"oc_id": oc["oc"]["id"]}).json()["posiciones"]
        fila = next(f for f in filas if f["posicion_id"] == pos["id"])
        assert fila["reglas"]["receta"] == de_categoria["nombre"]
        assert admin.get("/reglas-empaque/campos").json()["grupos"]
        # Destino de grupo sin grupo: no se guarda
        assert admin.post("/reglas-empaque", {"receta_id": de_familia["id"], "destino": "GRUPO"}).status_code == 422
    finally:
        for rid in creadas:
            admin.delete_(f"/reglas-empaque/{rid}")
        admin.patch(f"/grupos-producto/{cat['id']}", {"activa": False})


def test_otra_empresa_no_ve_los_grupos(admin, client):
    fam = _grupo(admin, codigo="GP-AISLADO", nombre="Isolated group")
    r = admin.post("/plataforma/organizaciones", {"codigo": "GPAIS", "nombre": "Second groups company", "pais": "gt",
                                                  "admin_email": "gpais@demo.com", "admin_nombre": "Groups admin 2",
                                                  "admin_telefono": "+50200000027"})
    assert r.status_code == 200, r.text
    org = r.json()
    try:
        api = Api(client, "gpais@demo.com", org["password_temporal"])
        assert api.post("/auth/password", {"actual": org["password_temporal"], "nueva": "Grupos#2026xy"}).status_code == 200
        assert all(g["id"] != fam["id"] for g in api.get("/grupos-producto").json())
        assert api.patch(f"/grupos-producto/{fam['id']}", {"nombre": "Mine"}).status_code == 404
        # El mismo código sirve en otra empresa
        assert api.post("/grupos-producto", {"codigo": "GP-AISLADO", "nombre": "Their group"}).status_code == 200
        assert api.post("/grupos-producto", {"clase": "CATEGORIA", "codigo": "GP-AJENA", "nombre": "x",
                                             "padre_id": fam["id"]}).status_code == 422
    finally:
        admin.patch(f"/plataforma/organizaciones/{org['id']}", {"activa": False})


def test_migracion_copia_familias_y_categorias_y_vuelve_atras():
    """0081: cada familia y categoría pasa 1:1 al árbol (con el mapa), las asignaciones y
    las reglas se reapuntan y la celda se recalcula. Al volver, lo cambiado en el árbol
    regresa a las tablas anteriores y los nodos nuevos se agregan a ellas."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]

        def migrar(*args):
            r = subprocess.run(alembic + list(args), cwd=RAIZ, env=env, capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr

        migrar("upgrade", "0080")
        c = sqlite3.connect(f"{tmp}/m.db")
        c.execute("PRAGMA foreign_keys=OFF")
        q = c.execute
        q("INSERT OR IGNORE INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en)"
          " VALUES (1, 'O1', 'Org', '{}', 1, '2026-01-01')")
        q("INSERT INTO marcas (id, organizacion_id, codigo, nombre, activa) VALUES (1, 1, 'M', 'Brand', 1)")
        q("INSERT OR IGNORE INTO categorias_articulo (id, organizacion_id, codigo, nombre, activo) VALUES (999, 1, 'X', 'Cat', 1)")
        q("INSERT INTO proveedores (id, organizacion_id, codigo, nombre, activo, extra) VALUES (1, 1, 'P1', 'Prov', 1, '{}')")
        for tid in (5, 6):
            q("INSERT INTO tipos_etiqueta (id, organizacion_id, codigo, nombre, sujeto, cantidad, obligatoria, orden, activo,"
              " creado_en, version) VALUES (?, 1, ?, 'Tag', 'ARTICULO', 'POR_UNIDAD', 0, 0, 1, '2026-01-01', 1)", (tid, f"T{tid}"))
        q("INSERT INTO plantillas_etiqueta (id, organizacion_id, tipo_etiqueta_id, nombre, estado, creada_en, actualizada_en)"
          " VALUES (1, 1, 5, 'Design', 'ACTIVA', '2026-01-01', '2026-01-01')")
        q("INSERT INTO versiones_plantilla (id, organizacion_id, plantilla_id, numero, estado, diseno, ancho_mm, alto_mm,"
          " creada_en, actualizada_en, version) VALUES (1, 1, 1, 1, 'APROBADA', '{}', 50, 30, '2026-01-01', '2026-01-01', 1)")
        q("INSERT INTO generaciones_etiqueta (id, organizacion_id, formato, estado, total, parametros, advertencias, creada_en)"
          " VALUES (1, 1, 'PDF', 'GENERADA', 1, '{}', '[]', '2026-01-01')")
        for fid, cod, nom, padre in ((1, "CALZ", "Footwear", None), (2, "CALZ-TEC", "Technical", 1), (3, "ROPA", "Apparel", None)):
            q("INSERT INTO familias_etiquetado (id, organizacion_id, codigo, nombre, campos, orden, activa, creada_en, padre_id)"
              " VALUES (?, 1, ?, ?, '[]', 10, 1, '2026-01-01', ?)", (fid, cod, nom, padre))
        for cid, fam, cod, cond in ((1, 1, "SAND", '[{"campo": "articulo.descripcion", "op": "contiene", "valor": "sandal"}]'),
                                    (2, 3, "ROPA", "[]")):
            q("INSERT INTO categorias_etiquetado (id, organizacion_id, familia_id, codigo, nombre, condiciones, orden, activa,"
              " creada_en) VALUES (?, 1, ?, ?, ?, ?, 10, 1, '2026-01-01')", (cid, fam, cod, cod.title(), cond))
        q("INSERT INTO grupos_articulos (id, organizacion_id, codigo, nombre, categoria, activo, familia_etiquetado_id)"
          " VALUES (1, 1, 'G1', 'Group', 'X', 1, 1)")
        q("INSERT INTO articulos (id, organizacion_id, sku, estilo, marca_id, grupo_id, unidad, tipo, activo, familia_etiquetado_id)"
          " VALUES (1, 1, 'SKU1', 'E', 1, 1, 'PAR', 'SOLIDO', 1, 3)")
        for pid, fam, cat in ((1, None, 1), (2, 2, 2)):  # 1: categoría de su familia (por el grupo); 2: ajena, no cuenta
            q("INSERT INTO productos (id, organizacion_id, proveedor_id, estilo, ficha, ficha_completa, faltan, version_ficha,"
              " estado, creado_en, actualizado_en, version, grupo_id, familia_etiquetado_id, categoria_etiquetado_id)"
              " VALUES (?, 1, 1, ?, '{}', 0, '[]', 1, 'pendiente', '2026-01-01', '2026-01-01', 1, 1, ?, ?)",
              (pid, f"E{pid}", fam, cat))
        for uid, nivel, fam, cat in ((1, "FAMILIA", 2, None), (2, "CATEGORIA", None, 1), (3, "GENERAL", None, None)):
            destino = fam or cat or 0
            q("INSERT INTO usos_diseno (id, organizacion_id, tipo_etiqueta_id, plantilla_id, nivel, familia_id, categoria_id,"
              " celda, contexto_tipo, contexto_valores, condiciones, creado_en, version, accion, prioridad)"
              " VALUES (?, 1, 5, 1, ?, ?, ?, ?, 'NINGUNO', '[]', '[]', '2026-01-01', 1, 'USAR', 0)",
              (uid, nivel, fam, cat, f"5:{nivel}:{destino}"))
        q("INSERT INTO generacion_items (id, organizacion_id, generacion_id, plantilla_id, version_id, cantidad, valores,"
          " familia_id) VALUES (1, 1, 1, 1, 1, 1, '{}', 3)")
        c.commit()
        c.close()

        migrar("upgrade", "0081")
        c = sqlite3.connect(f"{tmp}/m.db")
        nodos = {cod: (gid, clase, padre, lf, lc) for gid, clase, cod, padre, lf, lc in c.execute(
            "SELECT id, clase, codigo, padre_id, legado_familia_id, legado_categoria_id FROM grupos_producto")}
        assert set(nodos) == {"CALZ", "CALZ-TEC", "ROPA", "SAND", "ROPA-C"}  # la categoría ROPA choca con la familia
        g = {cod: v[0] for cod, v in nodos.items()}
        assert nodos["CALZ-TEC"][1:4] == ("FAMILIA", g["CALZ"], 2)
        assert nodos["SAND"][1:] == ("CATEGORIA", g["CALZ"], None, 1) and nodos["ROPA-C"][2] == g["ROPA"]
        assert c.execute("SELECT condiciones FROM grupos_producto WHERE id = ?", (g["SAND"],)).fetchone()[0].count("sandal") == 1
        assert c.execute("SELECT grupo_producto_id FROM articulos").fetchone()[0] == g["ROPA"]
        assert c.execute("SELECT grupo_producto_id FROM grupos_articulos").fetchone()[0] == g["CALZ"]
        prods = dict(c.execute("SELECT id, grupo_producto_id FROM productos"))
        assert prods == {1: g["SAND"], 2: g["CALZ-TEC"]}
        usos = {uid: (gid, celda) for uid, gid, celda in c.execute("SELECT id, grupo_id, celda FROM usos_diseno")}
        assert usos[1] == (g["CALZ-TEC"], f"5:FAMILIA:{g['CALZ-TEC']}") and usos[2] == (g["SAND"], f"5:CATEGORIA:{g['SAND']}")
        assert usos[3] == (None, "5:GENERAL:0")
        assert c.execute("SELECT grupo_id FROM generacion_items").fetchone()[0] == g["ROPA"]
        # Las tablas anteriores quedan como estaban
        assert c.execute("SELECT familia_etiquetado_id FROM articulos").fetchone()[0] == 3
        # Cambios en el árbol nuevo: un nombre, una familia nueva con un artículo y una regla
        c.execute("UPDATE grupos_producto SET nombre = 'Shoes' WHERE codigo = 'CALZ'")
        c.execute("INSERT INTO grupos_producto (clase, codigo, nombre, condiciones, campos, orden, activa, creada_en,"
                  " organizacion_id) VALUES ('FAMILIA', 'NUEVA', 'New', '[]', '[]', 20, 1, '2026-02-01', 1)")
        nueva = c.execute("SELECT id FROM grupos_producto WHERE codigo = 'NUEVA'").fetchone()[0]
        c.execute("UPDATE articulos SET grupo_producto_id = ?", (nueva,))
        c.execute("INSERT INTO usos_diseno (id, organizacion_id, tipo_etiqueta_id, plantilla_id, nivel, grupo_id, celda,"
                  " contexto_tipo, contexto_valores, condiciones, creado_en, version, accion, prioridad)"
                  " VALUES (4, 1, 6, 1, 'FAMILIA', ?, ?, 'NINGUNO', '[]', '[]', '2026-02-01', 1, 'USAR', 0)",
                  (nueva, f"6:FAMILIA:{nueva}"))
        c.commit()
        c.close()

        migrar("downgrade", "0080")
        c = sqlite3.connect(f"{tmp}/m.db")
        assert c.execute("SELECT nombre FROM familias_etiquetado WHERE id = 1").fetchone()[0] == "Shoes"
        nueva_ant = c.execute("SELECT id FROM familias_etiquetado WHERE codigo = 'NUEVA'").fetchone()[0]
        assert c.execute("SELECT familia_etiquetado_id FROM articulos").fetchone()[0] == nueva_ant
        assert dict(c.execute("SELECT id, categoria_etiquetado_id FROM productos")) == {1: 1, 2: None}
        celdas = dict(c.execute("SELECT id, celda FROM usos_diseno"))
        assert celdas == {1: "5:FAMILIA:2", 2: "5:CATEGORIA:1", 3: "5:GENERAL:0", 4: f"6:FAMILIA:{nueva_ant}"}
        assert not c.execute("SELECT name FROM sqlite_master WHERE name = 'grupos_producto'").fetchall()
        c.close()
        migrar("upgrade", "head")
