"""Flujo de clasificación configurable: quién llena la ficha, qué ve el
proveedor y cómo se aprueba se cambia desde el sistema; el motor (familias,
atributos y reglas) tiene sus propios permisos."""
import pytest


@pytest.fixture
def flujo(admin):
    antes = admin.get("/flujo-clasificacion").json()["valores"]
    yield lambda **cambios: admin.put("/flujo-clasificacion", cambios)
    assert admin.put("/flujo-clasificacion", antes).status_code == 200


def _sugerido(interno, generico: str, estilo: str) -> dict:
    """Un artículo propio de Vans con la ficha completa (estado «sugerida»)."""
    m = {x["codigo"]: x["id"] for x in interno.get("/catalogos/marcas", params={"size": 100}).json()["items"]}
    g = {x["codigo"]: x["id"] for x in interno.get("/catalogos/grupos").json()["items"]}
    pv = {x["codigo"]: x["id"] for x in interno.get("/catalogos/proveedores").json()["items"]}
    r = interno.post("/catalogos/genericos", {"generico": generico, "estilo": estilo, "color": "Black", "marca_id": m["VANS"],
                                              "grupo_id": g["CALZ-CAS"], "proveedor_id": pv["VANS"], "unidad": "PAR",
                                              "nombre": "Leather skate shoe", "tallas": [{"talla": "8"}]})
    assert r.status_code == 200, r.text
    p = next(x for x in interno.get("/productos", params={"q": estilo}).json()["items"] if x["estilo"] == estilo)
    ficha = {"comp": {"corte": "100% leather", "suela": "100% rubber"}, "estiloCalz": "tenis", "altura": "bajo", "genero": "U",
             "edadNac": "adulto", "puntera": "ninguna"}
    p = interno.put(f"/productos/{p['id']}/ficha", {"version": p["version"], "tipo": "calzado", "ficha": ficha, "pais_origen": "VN",
                                                     "nombre": "Leather skate shoe",
                                                     "tocados": ["estiloCalz", "altura", "genero", "edadNac", "puntera"]}).json()
    assert p["estado"] == "sugerida", p.get("faltan")
    return p


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
    p = tnf.get("/productos", params={"estado": ""}).json()["items"][0]  # se rechaza antes de mirar el estado
    assert "producto.ficha" in tnf.get("/auth/me").json()["permisos"]
    assert flujo(proveedor_captura=False).status_code == 200
    assert "producto.ficha" not in tnf.get("/auth/me").json()["permisos"]
    r = tnf.put(f"/productos/{p['id']}/ficha", {"version": p["version"], "tipo": p["tipo"], "ficha": {}})
    assert r.status_code == 403
    assert tnf.get(f"/productos/{p['id']}").status_code == 200


def test_proveedor_sin_sugerencia(vans, interno, flujo):
    propio = _sugerido(interno, "98130001", "VNROL01")
    assert flujo(proveedor_ve_sugerencia=False).status_code == 200
    items = vans.get("/productos", params={"size": 100}).json()["items"]
    pendiente = next(x for x in items if x["id"] == propio["id"])
    aprobado = next(x for x in items if x["estado"] == "aprobado")
    assert pendiente["sugerido"] is None and pendiente["sugerencia_oculta"]
    assert aprobado["codigo"] and aprobado["sugerido"]  # la partida aprobada sí la ve
    d = vans.get(f"/productos/{pendiente['id']}").json()
    assert d["sugerido"] is None and d["confianza"] is None
    # Tampoco por el historial, la evidencia ni la opinión del especialista
    assert d["evidencia"] is None and d["opinion_ia"] is None
    assert all("sugerido" not in (h["detalle"] or {}) for h in d["historial"])
    assert interno.get(f"/productos/{pendiente['id']}").json()["sugerido"]
    # La sesión de clasificación le deja las preguntas, sin códigos ni candidatos
    s = vans.post("/clasificacion/sesion", {"categoria": "calzado", "ficha": {}, "estilo": "X"}).json()
    assert "hs6" not in s and "candidatos" not in s and "campos" in s and s["sugerencia_oculta"]
    assert "hs6" in interno.post("/clasificacion/sesion", {"categoria": "calzado", "ficha": {}, "estilo": "X"}).json()


def test_aprobacion_con_revision_y_cuatro_ojos(interno, flujo):
    p = _sugerido(interno, "98130002", "VNROL02")
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


def test_familias_con_su_salud(interno, tnf):
    fams = {f["codigo"]: f for f in interno.get("/familias").json()}
    calz = fams["FOOTWEAR"]
    assert calz["categorias"] >= 1 and calz["preguntas"] > 5 and calz["reglas_acotan"] > 0 and "64" in calz["capitulos_auto"]
    assert calz["productos"]["total"] >= 1 and calz["estado"] == "lista" and not calz["avisos"]
    assert all(isinstance(f["avisos"], list) and f["estado"] in ("lista", "incompleta") for f in fams.values())
    assert tnf.get("/familias").status_code == 403


def test_regla_desde_decision_y_su_impacto(interno, flujo):
    """Una decisión de aduanas se vuelve borrador de regla; antes de guardarla se
    ve qué artículos cambiarían, y la simulación no deja nada guardado."""
    p = _sugerido(interno, "98130003", "VNROL03")
    hs6 = p["sugerido"].replace(".", "")[:6]
    r = interno.post(f"/productos/{p['id']}/aprobar", {"version": p["version"], "codigo": hs6})
    assert r.status_code == 200, r.text
    b = interno.get(f"/aranceles/reglas/desde-producto/{p['id']}").json()
    assert b["tipo_ambito"] == "CATEGORY" and b["codigo_ambito"] == "calzado" and b["accion"] == {"tipo": "RESTRICT", "codigos": [hs6]}
    assert {c["campo"] for c in b["condiciones"]} >= {"estiloCalz", "altura"}
    antes = interno.get("/aranceles/reglas", params={"size": 1}).json()["total"]
    sim = interno.post("/aranceles/reglas/simular", {**b, "prioridad": 5000}).json()
    assert sim["evaluados"] >= 1 and sim["en_ambito"] >= sim["evaluados"]
    assert not any(x["id"] == p["id"] for x in sim["cambian"])  # la regla confirma lo aprobado: ese artículo no cambia
    assert interno.get("/aranceles/reglas", params={"size": 1}).json()["total"] == antes  # nada guardado
    # Con una regla que manda todo el calzado a otra subpartida, los artículos de la categoría cambian
    otra = interno.post("/aranceles/reglas/simular", {**b, "condiciones": [], "accion": {"tipo": "RESTRICT", "codigos": ["640411"]},
                                                      "prioridad": 9000}).json()
    assert otra["cambian"] and all(x["despues"] == "6404.11" for x in otra["cambian"])
    assert interno.get(f"/aranceles/reglas/desde-producto/{p['id'] + 99999}").status_code == 404


def test_familia_borrador_probar_y_publicar(interno):
    """Una familia nueva nace en borrador: no aparece en la ficha ni clasifica
    artículos reales, pero se prueba con un artículo de ejemplo; al publicarla
    queda en uso."""
    d = interno.post("/aranceles/oficial/dominios", {"codigo": "TOYS_TEST", "nombre": "Toys", "modo": "AUTO"}).json()
    assert d["estado"] == "BORRADOR"
    assert interno.post("/familias/TOYS_TEST/publicar").json()["codigo"] == "validacion"  # sin capítulos
    interno.put(f"/aranceles/oficial/dominios/{d['id']}/capitulos/95", {"relevancia": "PRIMARY", "habilitado": True})
    assert interno.post("/familias/TOYS_TEST/publicar").json()["codigo"] == "validacion"  # sin categorías
    c = interno.post("/aranceles/categorias", {"codigo": "toy_test", "nombre": "Toy vehicles", "dominio": "TOYS_TEST", "capitulos": ["95"],
                                                "patrones": [{"re": r"\btoy (car|truck)s?\b", "prioridad": 1}]}).json()
    fam = {f["codigo"]: f for f in interno.get("/familias").json()}["TOYS_TEST"]
    assert fam["publicada"] is False
    # La ficha no la ofrece ni la detecta en un artículo real
    assert not any(x["codigo"] == c["codigo"] for x in interno.get("/clasificacion/contexto").json()["categorias"])
    s = interno.post("/clasificacion/sesion", {"nombre": "Red toy car with lights", "paises": False}).json()
    assert (s.get("categoria") or {}).get("codigo") != "toy_test"
    # Probar sí la usa (sin guardar nada)
    pr = interno.post("/familias/TOYS_TEST/probar", {"nombre": "Red toy car with lights"}).json()
    assert pr["categoria"]["codigo"] == "toy_test" and (pr["hs6"] or "").startswith("95")
    det = interno.get("/familias/TOYS_TEST").json()
    assert [c["capitulo"] for c in det["capitulos"]] == ["95"] and [c["codigo"] for c in det["categorias"]] == ["toy_test"]
    assert det["publicada"] is False and det["preguntas"] == [] and det["reglas"] == []
    assert interno.post("/familias/TOYS_TEST/publicar").json()["publicada"] is True
    assert any(x["codigo"] == c["codigo"] for x in interno.get("/clasificacion/contexto").json()["categorias"])
    assert interno.post("/familias/NOPE/probar", {"nombre": "x"}).status_code == 404


def test_traducciones_del_catalogo(interno, tnf):
    """Las preguntas, opciones y categorías se traducen como datos: la semilla
    cubre el catálogo incluido en español y se editan desde el sistema."""
    es = interno.get("/i18n/catalogo/es").json()
    assert es["Footwear style"] == "Estilo de calzado" and es["Upper"] == "Corte" and es["Sneaker"] == "Tenis"
    assert tnf.get("/i18n/catalogo/es").status_code == 200  # cualquiera con sesión la lee
    assert interno.get("/i18n/catalogo/xx").json() == {}
    lista = interno.get("/familias/traducciones/es", params={"pendientes": True}).json()
    assert lista["total"] > 600 and all(not x["traduccion"] for x in lista["items"])
    assert interno.put("/familias/traducciones/zh", {"texto": "Sneaker", "traduccion": "运动鞋"}).json()["traduccion"] == "运动鞋"
    assert interno.get("/i18n/catalogo/zh").json()["Sneaker"] == "运动鞋"
    assert interno.put("/familias/traducciones/zh", {"texto": "Sneaker", "traduccion": ""}).json()["traduccion"] is None
    assert "Sneaker" not in interno.get("/i18n/catalogo/zh").json()
    assert interno.put("/familias/traducciones/fr", {"texto": "Sneaker", "traduccion": "x"}).status_code == 422
    assert tnf.put("/familias/traducciones/es", {"texto": "Sneaker", "traduccion": "x"}).status_code == 403
