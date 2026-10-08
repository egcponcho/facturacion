"""Una empresa por instalación: su ficha y sus reglas de negocio se guardan en
la base de datos y solo la administración las cambia."""
import json
import sqlite3
import subprocess
import sys
import tempfile


def test_configuracion_de_la_empresa(interno, admin):
    datos = admin.get("/organizacion").json()
    assert datos["nombre"] == "Distribuidora de Marcas"
    reglas = {r["clave"]: r["valor"] for r in datos["reglas"]}
    assert reglas["PROVEEDOR_PUEDE_FINALIZAR"] is True

    # Solo la administración cambia la configuración, y se valida
    assert interno.put("/organizacion", {"nombre": "Otra"}).status_code == 403
    assert admin.put("/organizacion", {"reglas": {"DIAS_ALERTA_BORRADOR": "x"}}).status_code == 422
    assert admin.put("/organizacion", {"reglas": {"NO_EXISTE": 1}}).status_code == 422
    r = admin.put("/organizacion", {"reglas": {"DIAS_ALERTA_BORRADOR": 3}, "preferencias": {"moneda": "EUR"}})
    assert r.status_code == 200, r.text
    assert r.json()["preferencias"]["moneda"] == "EUR"
    # La regla aplica de inmediato a todos
    assert interno.get("/auth/me").json()["config"]["dias_alerta_borrador"] == 3
    admin.put("/organizacion", {"reglas": {"DIAS_ALERTA_BORRADOR": 7}, "preferencias": {"moneda": "USD"}})


def test_sin_plataforma_multiempresa(admin):
    assert admin.get("/organizaciones").status_code in (404, 405)
    assert admin.post("/organizaciones/1/entrar").status_code in (404, 405)
    yo = admin.get("/auth/me").json()
    assert "plataforma" not in yo and yo["organizacion"]["nombre"] == "Distribuidora de Marcas"


def test_migracion_vuelve_a_una_empresa():
    """0037 quita el aislamiento por empresa de la 0036 y conserva la ficha de
    la empresa; con datos de una segunda empresa se detiene sin cambiar nada."""
    from test_oficial import RAIZ

    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        r = subprocess.run(alembic + ["upgrade", "0036"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        con.execute("INSERT INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en)"
                    " VALUES (2, 'B', 'Otra', '{}', 1, CURRENT_TIMESTAMP)")
        con.execute("INSERT INTO proveedores (codigo, nombre, activo, organizacion_id) VALUES ('X', 'X', 1, 2)")
        con.commit()
        r = subprocess.run(alembic + ["upgrade", "head"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode != 0 and "más de una empresa" in r.stderr

        con.execute("DELETE FROM proveedores")
        con.execute("UPDATE organizaciones SET configuracion = ? WHERE id = 1", (json.dumps({"reglas": {"DIAS_ALERTA_BORRADOR": 3}}),))
        con.commit()
        con.close()
        r = subprocess.run(alembic + ["upgrade", "head"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        columnas = {c[1] for c in con.execute("PRAGMA table_info(proveedores)")}
        assert "organizacion_id" not in columnas
        assert con.execute("SELECT id, configuracion FROM organizaciones").fetchall() == [
            (1, json.dumps({"reglas": {"DIAS_ALERTA_BORRADOR": 3}}))]
        con.execute("INSERT INTO proveedores (codigo, nombre, activo) VALUES ('X', 'X', 1)")
        try:
            con.execute("INSERT INTO proveedores (codigo, nombre, activo) VALUES ('X', 'Y', 1)")
            duplicado = False
        except sqlite3.IntegrityError:
            duplicado = True
        assert duplicado, "el código de proveedor vuelve a ser único"
