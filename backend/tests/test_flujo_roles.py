"""Flujo de clasificación configurable: quién llena la ficha, qué ve el
proveedor y cómo se aprueba se cambia desde el sistema; el motor (familias,
atributos y reglas) tiene sus propios permisos."""
import pytest


@pytest.fixture
def flujo(admin):
    antes = admin.get("/flujo-clasificacion").json()["valores"]
    yield lambda **cambios: admin.put("/flujo-clasificacion", cambios)
    assert admin.put("/flujo-clasificacion", antes).status_code == 200


def _producto(api, estilo_estado):
    return next(x for x in api.get("/productos", params={"size": 100}).json()["items"] if x["estado"] == estilo_estado)


def test_interruptores_y_permisos(admin, interno, flujo):
    r = admin.get("/flujo-clasificacion").json()
    assert {x["clave"] for x in r["interruptores"]} == set(r["valores"])
    assert r["valores"]["proveedor_captura"] and not r["valores"]["cuatro_ojos"]
    assert interno.put("/flujo-clasificacion", {"cuatro_ojos": True}).status_code == 403
    assert flujo(nada=True).status_code == 422
    # Alguien tiene que llenar las fichas
    assert flujo(proveedor_captura=False, interno_captura=False).status_code == 422
    assert interno.get("/auth/me").json()["flujo"]["proveedor_captura"] is True


def test_proveedor_sin_captura_solo_ve(tnf, flujo):
    p = _producto(tnf, "observado")
    assert "producto.ficha" in tnf.get("/auth/me").json()["permisos"]
    assert flujo(proveedor_captura=False).status_code == 200
    assert "producto.ficha" not in tnf.get("/auth/me").json()["permisos"]
    r = tnf.put(f"/productos/{p['id']}/ficha", {"version": p["version"], "tipo": p["tipo"], "ficha": {}})
    assert r.status_code == 403
    assert tnf.get(f"/productos/{p['id']}").status_code == 200


def test_proveedor_sin_sugerencia(vans, interno, flujo):
    assert flujo(proveedor_ve_sugerencia=False).status_code == 200
    items = vans.get("/productos", params={"size": 100}).json()["items"]
    pendiente = next(x for x in items if x["estado"] == "sugerida")
    aprobado = next(x for x in items if x["estado"] == "aprobado")
    assert pendiente["sugerido"] is None and pendiente["sugerencia_oculta"]
    assert aprobado["codigo"] and aprobado["sugerido"]  # la partida aprobada sí la ve
    d = vans.get(f"/productos/{pendiente['id']}").json()
    assert d["sugerido"] is None and d["confianza"] is None
    assert interno.get(f"/productos/{pendiente['id']}").json()["sugerido"]
    # La sesión de clasificación le deja las preguntas, sin códigos ni candidatos
    s = vans.post("/clasificacion/sesion", {"categoria": "calzado", "ficha": {}, "estilo": "X"}).json()
    assert "hs6" not in s and "candidatos" not in s and "campos" in s and s["sugerencia_oculta"]
    assert "hs6" in interno.post("/clasificacion/sesion", {"categoria": "calzado", "ficha": {}, "estilo": "X"}).json()


def test_aprobacion_con_revision_y_cuatro_ojos(interno, flujo):
    p = _producto(interno, "sugerida")
    assert flujo(revision_obligatoria=True).status_code == 200
    r = interno.post(f"/productos/{p['id']}/aprobar", {"version": p["version"]})
    assert r.status_code == 422 and r.json()["codigo"] == "requiere_envio"
    assert flujo(revision_obligatoria=False, cuatro_ojos=True).status_code == 200
    assert interno.post("/productos/enviar", {"ids": [p["id"]]}).json()["enviados"] == 1
    d = interno.get(f"/productos/{p['id']}").json()
    assert d["enviado_por_mi"]
    r = interno.post(f"/productos/{p['id']}/aprobar", {"version": d["version"]})
    assert r.status_code == 422 and r.json()["codigo"] == "cuatro_ojos"
    assert interno.post(f"/productos/{p['id']}/retirar").status_code == 200
    assert flujo(cuatro_ojos=False, aprobacion_lote=False).status_code == 200
    assert interno.post("/productos/aprobar", {"ids": [p["id"]]}).json()["codigo"] == "lote_apagado"


def test_roles_sugeridos_y_permisos_del_motor(admin):
    roles = {x["nombre"]: x for x in admin.get("/roles").json()["roles"]}
    assert "clasificacion.configurar" in roles["Classification specialist"]["permisos"]
    assert "clasificacion.configurar" not in roles["Buyer"]["permisos"] and "producto.ficha" in roles["Buyer"]["permisos"]
    modulos = {m["modulo"]: [p["clave"] for p in m["permisos"]] for m in admin.get("/roles").json()["catalogo"]}
    assert modulos["Classification engine"] == ["clasificacion.ver", "clasificacion.configurar"]


def test_migraciones_de_permisos_y_condiciones():
    """0029: quien editaba el arancel también configura el motor y se agregan los
    roles sugeridos. 0030: las condiciones guardadas en el formato anterior pasan
    al formato del motor."""
    import json
    import sqlite3
    import subprocess
    import sys
    import tempfile

    from test_oficial import RAIZ

    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        assert subprocess.run(alembic + ["upgrade", "0028"], cwd=RAIZ, env=env, capture_output=True).returncode == 0
        con = sqlite3.connect(f"{tmp}/m.db")
        con.execute("INSERT INTO roles (id, nombre, tipo, permisos, sistema, activo) VALUES (1, 'Customs', 'interno', ?, 0, 1)",
                    (json.dumps(["aranceles.ver", "aranceles.editar", "producto.ver"]),))
        con.execute("INSERT INTO atributos_def (id, codigo, etiqueta, tipo_dato, multiple, usado_clasificacion, origen, de_composicion,"
                    " informativo, orden, activo, seccion, bloqueo) VALUES (1, 'uso', 'Use', 'select', 0, 1, 'MOTOR', 0, 0, 0, 1, 'producto', ?)",
                    (json.dumps([{"condiciones": [{"genero": "M"}], "mensaje": "No"}]),))
        con.execute("INSERT INTO atributo_ambitos (atributo_id, tipo_ambito, codigo_ambito, modo, prioridad, activo, condicion)"
                    " VALUES (1, 'DOMAIN', 'FOOTWEAR', 'SHOW', 9, 1, ?)", (json.dumps([{"genero": ["M", "F"]}, {"edad": "adulto"}]),))
        con.commit()
        con.close()
        r = subprocess.run(alembic + ["upgrade", "head"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        roles = {n: json.loads(p) for n, p in con.execute("SELECT nombre, permisos FROM roles")}
        assert {"clasificacion.ver", "clasificacion.configurar"} <= set(roles["Customs"])
        assert {"Classification specialist", "Buyer"} <= set(roles)
        cond = json.loads(con.execute("SELECT condicion FROM atributo_ambitos").fetchone()[0])
        assert cond == [{"grupo": 1, "campo": "genero", "operador": "IN", "valor": ["M", "F"]},
                        {"grupo": 2, "campo": "edad", "operador": "EQUAL", "valor": "adulto"}]
        bloqueo = json.loads(con.execute("SELECT bloqueo FROM atributos_def").fetchone()[0])
        assert bloqueo == [{"condiciones": [{"grupo": 1, "campo": "genero", "operador": "EQUAL", "valor": "M"}], "mensaje": "No"}]


def test_bandeja_baja_confianza(interno, vans, flujo):
    k = interno.get("/productos").json()["kpis"]
    assert isinstance(k["baja_confianza"], int)
    items = interno.get("/productos", params={"estado": "baja_confianza", "size": 100}).json()["items"]
    assert len(items) == k["baja_confianza"] and all(x["confianza"] == "low" and x["estado"] != "aprobado" for x in items)
    assert flujo(proveedor_ve_sugerencia=False).status_code == 200
    assert vans.get("/productos").json()["kpis"]["baja_confianza"] is None
