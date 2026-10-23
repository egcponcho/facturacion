"""Cada atributo vale en sus familias (y en sus subfamilias y categorías) o, si es
general, en todas: un producto solo lleva los atributos de su familia, y ningún
cambio (de las familias de un atributo, de los atributos de una familia, de la
familia de un producto) deja valores guardados fuera de ella."""
import json
import sqlite3
import subprocess
import sys
import tempfile

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import Producto


def _borrar(*gens):
    with SessionLocal() as db:
        for gen in gens:
            p = db.scalar(select(Producto).where(Producto.codigo_generico == gen))
            if p is not None:
                for a in list(p.articulos):
                    db.delete(a)
                db.delete(p)
        db.commit()


def _familia(api, codigo, padre=None):
    r = api.post("/grupos-producto", {"clase": "FAMILIA", "codigo": codigo, "nombre": f"Family {codigo}", "padre_id": padre})
    assert r.status_code == 200, r.text
    return r.json()


def test_un_atributo_vale_solo_en_sus_familias(admin, interno):
    quim, alim = _familia(admin, "QUIM-F"), _familia(admin, "ALIM-F")
    sub = _familia(admin, "QUIM-SUB", quim["id"])
    # Un atributo nuevo dice dónde vale: en sus familias o en todas
    r = interno.post("/catalogos/atributos", {"nivel": "VARIANTE", "codigo": "CONCF", "nombre": "Concentration F"})
    assert r.status_code == 422 and any(e["campo"] == "familias" for e in r.json()["detalle"]), r.text
    conc = interno.post("/catalogos/atributos", {"nivel": "VARIANTE", "codigo": "CONCF", "nombre": "Concentration F",
                                                 "familias": [quim["id"]]})
    assert conc.status_code == 200, conc.text
    conc = conc.json()
    assert conc["general"] is False and conc["familias"] == [quim["id"]]
    onu = interno.post("/catalogos/atributos", {"nivel": "PRODUCTO", "codigo": "ONUF", "nombre": "UN number F",
                                                "familias": [quim["id"]]}).json()
    try:
        # La familia y su subfamilia los llevan; la otra familia no
        arbol = {g["codigo"]: g for g in interno.get("/grupos-producto").json()}
        assert arbol["QUIM-F"]["atributos"] == ["ONUF", "CONCF"] and "CONCF" in arbol["QUIM-SUB"]["ejes"]
        assert "CONCF" not in arbol["ALIM-F"]["ejes"] and "ONUF" not in arbol["ALIM-F"]["atributos_producto"]
        perfil = interno.get("/productos/perfil", params={"grupo_id": alim["id"]}).json()
        assert "ONUF" not in [a["codigo"] for a in perfil["atributos"]] and "CONCF" not in perfil["ejes"]
        perfil = interno.get("/productos/perfil", params={"grupo_id": sub["id"]}).json()
        assert "ONUF" in [a["codigo"] for a in perfil["atributos"]] and perfil["ejes"] == ["CONCF"]
        # Un producto de otra familia (o sin familia) no los lleva
        datos = {"generico": "ACIDO-F1", "nombre": "Acid", "unidad": "UN", "atributos": {"ONUF": "1789"},
                 "variantes": [{"valores": {"CONCF": "30"}}]}
        for familia in (alim["id"], None):
            r = interno.post("/catalogos/genericos", {**datos, "grupo_producto_id": familia})
            assert r.status_code == 422 and "does not apply" in r.text, r.text
        # En la subfamilia sí (la hereda de su familia)
        r = interno.post("/catalogos/genericos", {**datos, "grupo_producto_id": sub["id"]})
        assert r.status_code == 200, r.text
        # El producto no se pasa a una familia donde sus atributos no valen…
        cambio = {"unidad": "UN", "grupo_producto_id": alim["id"]}
        r = interno.put("/catalogos/genericos/ACIDO-F1", cambio)
        assert r.status_code == 422 and "does not apply" in r.text, r.text
        # …ni se le quita al atributo la familia de un producto que lo usa
        r = interno.patch(f"/catalogos/atributos/{onu['id']}", {"familias": [alim["id"]]})
        assert r.status_code == 422 and "ACIDO-F1" in r.text, r.text
        # …ni a la familia sus atributos
        r = admin.patch(f"/grupos-producto/{quim['id']}", {"atributos": ["CONCF"]})
        assert r.status_code == 422 and "ACIDO-F1" in r.text, r.text
        # …ni la subfamilia se mueve fuera de la familia que se los da
        r = admin.patch(f"/grupos-producto/{sub['id']}", {"padre_id": alim["id"]})
        assert r.status_code == 422, r.text
        # Volverlo general sí: vale en todas
        r = interno.patch(f"/catalogos/atributos/{onu['id']}", {"general": True})
        assert r.status_code == 200 and r.json()["familias"] == [], r.text
        # Desde la familia se le asignan atributos: ahora la de alimentos lleva la concentración
        r = admin.patch(f"/grupos-producto/{alim['id']}", {"atributos": ["CONCF"]})
        assert r.status_code == 200 and r.json()["ejes"] == ["CONCF"], r.text
        r = interno.put("/catalogos/genericos/ACIDO-F1", cambio)
        assert r.status_code == 200, r.text
    finally:
        _borrar("ACIDO-F1")
        interno.delete_(f"/catalogos/atributos/{conc['id']}")
        interno.delete_(f"/catalogos/atributos/{onu['id']}")
        for g in (sub, quim, alim):
            admin.delete_(f"/grupos-producto/{g['id']}")


def test_la_demo_tiene_cada_atributo_en_su_familia(interno):
    """La demostración: la talla es del calzado y la ropa, no de los accesorios; la mochila
    (accesorios) solo se distingue por su color y lleva su capacidad."""
    atrs = {a["codigo"]: a for a in interno.get("/catalogos/atributos", params={"size": 50}).json()["items"]}
    assert atrs["MARCA"]["general"] and atrs["MODELO"]["general"]
    assert not atrs["TALLA"]["general"] and not atrs["COLOR"]["general"] and not atrs["CORTE"]["general"]
    det = interno.get("/catalogos/genericos/30095123").json()
    assert det["atributos"]["CAPACIDAD"] == "28" and [v["valores"] for v in det["variantes"]] == [{"COLOR": "JK3 TNF Black"}]
    with SessionLocal() as db:
        assert all(p.grupo_producto_id for p in db.scalars(select(Producto)) if p.codigo_generico.startswith("300951"))


def test_migracion_pasa_los_ejes_a_atributos_por_familia():
    """0094: los ejes de cada familia pasan a ser sus atributos; los de producto y los que valían en
    todas quedan generales; un valor guardado fuera de los ejes se cubre asignando su familia. Revertir
    devuelve los ejes."""
    from test_oficial import RAIZ

    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        r = subprocess.run(alembic + ["upgrade", "0093"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        c = sqlite3.connect(f"{tmp}/m.db")
        if not c.execute("SELECT id FROM organizaciones WHERE id = 1").fetchone():
            c.execute("INSERT INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en)"
                      " VALUES (1, 'UNO', 'UNO', '{}', 1, '2026-01-01')")
        c.execute("DELETE FROM atributos")  # una base nueva puede traer atributos de migraciones anteriores
        for i, (cod, nivel) in enumerate((("MARCA", "PRODUCTO"), ("COLOR", "VARIANTE"), ("TALLA", "VARIANTE"),
                                          ("SABOR", "VARIANTE")), start=101):
            c.execute("INSERT INTO atributos (id, organizacion_id, codigo, nombre, nivel, tipo, orden, activo)"
                      " VALUES (?, 1, ?, ?, ?, 'texto', ?, 1)", (i, cod, cod, nivel, i))
        # Calzado distingue por color y talla (y su subfamilia los hereda); Alimentos no tiene ejes (usaba todos)
        for gid, cod, padre, ejes in ((101, "CALZ", None, ["COLOR", "TALLA"]), (102, "CALZ-T", 101, []),
                                      (103, "ALIM", None, []), (104, "ROPA", None, ["TALLA"])):
            c.execute("INSERT INTO grupos_producto (id, organizacion_id, clase, codigo, nombre, padre_id, condiciones, campos,"
                      " ejes_variante, orden, activa, creada_en) VALUES (?, 1, 'FAMILIA', ?, ?, ?, '[]', '[]', ?, 0, 1,"
                      " '2026-01-01')", (gid, cod, cod, padre, json.dumps(ejes)))
        # Una prenda con color (fuera de los ejes de Ropa): se conserva asignando el color a Ropa
        c.execute("INSERT INTO productos (id, organizacion_id, codigo_generico, nombre, ficha, faltan, estado, version,"
                  " version_ficha, ficha_completa, creado_en, actualizado_en, grupo_producto_id)"
                  " VALUES (1, 1, 'P1', 'P1', '{}', '[]', 'borrador', 1, 1, 0, '2026-01-01', '2026-01-01', 104)")
        c.execute("INSERT INTO articulos (id, organizacion_id, sku, producto_id, unidad, tipo, activo)"
                  " VALUES (1, 1, 'P1001', 1, 'UN', 'SOLIDO', 1)")
        c.execute("INSERT INTO articulo_atributos (organizacion_id, articulo_id, atributo_id, valor) VALUES (1, 1, 102, 'RED')")
        c.commit()
        r = subprocess.run(alembic + ["upgrade", "0094"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        general = dict(c.execute("SELECT codigo, general FROM atributos"))
        assert general == {"MARCA": 1, "COLOR": 0, "TALLA": 1, "SABOR": 0}  # TALLA valía en todas las familias
        filas = {(g, a) for g, a in c.execute("SELECT g.codigo, a.codigo FROM atributo_familias x JOIN grupos_producto g"
                                              " ON g.id = x.grupo_id JOIN atributos a ON a.id = x.atributo_id")}
        assert filas == {("CALZ", "COLOR"), ("ALIM", "COLOR"), ("ALIM", "SABOR"), ("ROPA", "COLOR")}
        assert "ejes_variante" not in [x[1] for x in c.execute("PRAGMA table_info(grupos_producto)")]
        assert c.execute("SELECT COUNT(*) FROM respaldos_migracion WHERE migracion = '0094'").fetchone()[0] == 2
        r = subprocess.run(alembic + ["downgrade", "0093"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        ejes = {cod: json.loads(e) for cod, e in c.execute("SELECT codigo, ejes_variante FROM grupos_producto")}
        assert ejes == {"CALZ": ["COLOR", "TALLA"], "CALZ-T": [], "ALIM": ["COLOR", "TALLA", "SABOR"], "ROPA": ["TALLA"]}
        assert "general" not in [x[1] for x in c.execute("PRAGMA table_info(atributos)")]
        c.close()
