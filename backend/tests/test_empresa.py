"""La ficha y las reglas de negocio de cada organización se guardan en la
base de datos y solo su administración las cambia."""
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


def test_administracion_de_la_plataforma(admin, interno):
    yo = admin.get("/auth/me").json()
    assert yo["plataforma"] is True and yo["organizacion"]["nombre"] == "Distribuidora de Marcas"
    assert yo["organizacion"]["propia"] is True
    assert interno.get("/auth/me").json()["plataforma"] is False
    assert interno.get("/plataforma/organizaciones").status_code == 403


def test_migraciones_de_empresas():
    """0037 quitó el aislamiento por empresa de la 0036 (y se detiene si hay
    datos de una segunda empresa); 0047 lo vuelve a poner: los datos quedan en
    la organización 1 y los códigos pasan a ser únicos por organización."""
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
        r = subprocess.run(alembic + ["upgrade", "0037"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode != 0 and "más de una empresa" in r.stderr

        con.execute("DELETE FROM proveedores")
        con.execute("UPDATE organizaciones SET configuracion = ? WHERE id = 1", (json.dumps({"reglas": {"DIAS_ALERTA_BORRADOR": 3}}),))
        con.commit()
        con.close()
        r = subprocess.run(alembic + ["upgrade", "0037"], cwd=RAIZ, env=env, capture_output=True, text=True)
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
        con.commit()
        con.close()

        r = subprocess.run(alembic + ["upgrade", "head"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        assert con.execute("SELECT organizacion_id FROM proveedores WHERE codigo = 'X'").fetchall() == [(1,)]
        con.execute("INSERT INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en)"
                    " VALUES (2, 'B', 'Otra', '{}', 1, CURRENT_TIMESTAMP)")
        # El mismo código en otra organización sí; repetido en la misma, no
        con.execute("INSERT INTO proveedores (codigo, nombre, activo, organizacion_id, extra) VALUES ('X', 'X', 1, 2, '{}')")
        try:
            con.execute("INSERT INTO proveedores (codigo, nombre, activo, organizacion_id, extra) VALUES ('X', 'Z', 1, 2, '{}')")
            duplicado = False
        except sqlite3.IntegrityError:
            duplicado = True
        assert duplicado, "el código de proveedor es único dentro de cada organización"


def test_reglas_de_compatibilidad_configurables(admin):
    reglas = {r["clave"]: r["valor"] for r in admin.get("/organizacion").json()["reglas"]}
    assert set(reglas["COMPATIBILIDAD_BLOQUEANTE"]) == {"sociedad", "moneda", "centro"}
    assert admin.put("/organizacion", {"reglas": {"COMPATIBILIDAD_BLOQUEANTE": ["no_existe"]}}).status_code == 422
    # Un dato no puede bloquear y solo avisar a la vez
    assert admin.put("/organizacion", {"reglas": {"COMPATIBILIDAD_BLOQUEANTE": ["incoterm"]}}).status_code == 422
    r = admin.put("/organizacion", {"reglas": {"COMPATIBILIDAD_BLOQUEANTE": ["moneda", "sociedad"],
                                               "COMPATIBILIDAD_ADVERTENCIA": ["incoterm", "centro"]}})
    assert r.status_code == 200, r.text
    reglas = {x["clave"]: x["valor"] for x in r.json()["reglas"]}
    assert reglas["COMPATIBILIDAD_BLOQUEANTE"] == ["sociedad", "moneda"] and "centro" in reglas["COMPATIBILIDAD_ADVERTENCIA"]
    assert {c["clave"] for c in r.json()["campos_compatibilidad"]} >= {"sociedad", "centro", "moneda", "incoterm"}
    admin.put("/organizacion", {"reglas": {"COMPATIBILIDAD_BLOQUEANTE": ["sociedad", "centro", "moneda"],
                                           "COMPATIBILIDAD_ADVERTENCIA": ["incoterm", "centro_destino"]}})
