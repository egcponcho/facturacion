"""Filtros por columna de las tablas (app/modulos/comun/tabla.py): cada lista
del servidor filtra por uno o varios valores de cada columna (`f` en JSON) y
devuelve los valores únicos de una columna con cuántas filas tienen cada uno,
bajo los demás filtros y el alcance del usuario."""
import json


def _f(**kw):
    return {"f": json.dumps(kw)}


def test_valores_unicos_con_su_cuenta(interno):
    total = interno.get("/facturas", params={"size": 200}).json()["total"]
    vals = interno.get("/facturas/valores", params={"columna": "estado"}).json()
    assert vals and sum(v["n"] for v in vals) == total
    assert len({v["valor"] for v in vals}) == len(vals)


def test_varios_valores_y_el_filtro_de_la_columna_no_limita_sus_valores(interno):
    estados = [v["valor"] for v in interno.get("/facturas/valores", params={"columna": "estado"}).json()]
    elegidos = estados[:2]
    r = interno.get("/facturas", params={"size": 200, **_f(estado=elegidos)}).json()
    assert r["items"] and {x["estado"] for x in r["items"]} <= set(elegidos)
    # Como en Excel: con el estado filtrado, su filtro sigue mostrando todos los estados
    con = interno.get("/facturas/valores", params={"columna": "estado", **_f(estado=elegidos[:1])}).json()
    assert {v["valor"] for v in con} == set(estados)
    # Pero las demás columnas solo muestran lo que queda con ese estado
    prov = interno.get("/facturas/valores", params={"columna": "proveedor", **_f(estado=elegidos[:1])}).json()
    solo = interno.get("/facturas", params={"size": 200, **_f(estado=elegidos[:1])}).json()["items"]
    assert {v["valor"] for v in prov} == {x["proveedor"] for x in solo}


def test_buscar_dentro_de_los_valores(interno):
    todos = interno.get("/facturas/valores", params={"columna": "nombre"}).json()
    parte = todos[0]["valor"][:4].lower()
    algunos = interno.get("/facturas/valores", params={"columna": "nombre", "buscar": parte}).json()
    assert algunos and all(parte in v["valor"].lower() for v in algunos)


def test_valor_vacio(interno):
    # Ninguna factura tiene moneda vacía: filtrar por «vacío» no trae ninguna
    r = interno.get("/facturas", params=_f(moneda=["__vacio__"])).json()
    assert r["total"] == 0
    r = interno.get("/facturas", params=_f(moneda=["__vacio__", "USD"])).json()
    assert r["total"] > 0 and all(x["moneda"] == "USD" for x in r["items"])


def test_columnas_y_filtros_invalidos(interno):
    assert interno.get("/facturas/valores", params={"columna": "inventada"}).status_code == 422
    assert interno.get("/facturas", params={"f": "{no es json"}).status_code == 422
    # Una columna desconocida en `f` se ignora
    assert interno.get("/facturas", params=_f(inventada=["x"])).status_code == 200


def test_el_proveedor_solo_ve_sus_valores(tnf):
    vals = tnf.get("/facturas/valores", params={"columna": "proveedor"}).json()
    assert [v["valor"] for v in vals] == ["The North Face"]


# ---- Órdenes de compra -------------------------------------------------------------

def test_ordenes_filtran_por_columna_y_dan_sus_valores(interno):
    base = {"solo_disponible": "false", "size": 200}
    total = interno.get("/ordenes", params=base).json()["total"]
    provs = interno.get("/ordenes/valores", params={"columna": "proveedor", "solo_disponible": "false"}).json()
    assert sum(v["n"] for v in provs) == total and len(provs) >= 2
    uno = provs[0]["valor"]
    r = interno.get("/ordenes", params={**base, **_f(proveedor=[uno])}).json()
    assert r["total"] == provs[0]["n"] and {x["proveedor"] for x in r["items"]} == {uno}
    # El avance se filtra en % entero; las XF por fecha
    av = interno.get("/ordenes/valores", params={"columna": "avance", "solo_disponible": "false"}).json()
    assert all(isinstance(v["valor"], int) for v in av)
    xf = interno.get("/ordenes/valores", params={"columna": "xf", "solo_disponible": "false"}).json()
    dia = next(v for v in xf if v["valor"])
    r = interno.get("/ordenes", params={**base, **_f(xf=[dia["valor"]])}).json()
    assert r["total"] == dia["n"] and all(x["fecha_xf"] == dia["valor"] for x in r["items"])


def test_ordenes_valores_respetan_el_alcance_del_proveedor(vans):
    provs = vans.get("/ordenes/valores", params={"columna": "proveedor", "solo_disponible": "false"}).json()
    assert [v["valor"] for v in provs] == ["Vans"]


# ---- Reglas de clasificación (incluye una columna en tabla hija: sus condiciones) ---------

def test_reglas_filtran_por_tipo_activo_y_atributo_de_sus_condiciones(interno):
    total = interno.get("/aranceles/reglas", params={"size": 1}).json()["total"]
    tipos = interno.get("/aranceles/reglas/valores", params={"columna": "tipo"}).json()
    assert sum(v["n"] for v in tipos) == total
    # Sí / no: activas
    act = {v["valor"]: v["n"] for v in interno.get("/aranceles/reglas/valores", params={"columna": "activo"}).json()}
    assert True in act and interno.get("/aranceles/reglas", params={"size": 1, **_f(activo=["true"])}).json()["total"] == act[True]
    # Atributo de las condiciones: cuenta reglas (no condiciones) y filtra las que lo usan
    conds = interno.get("/aranceles/reglas/valores", params={"columna": "condiciones"}).json()
    uno = next(v for v in conds if v["valor"])
    r = interno.get("/aranceles/reglas", params={"size": 200, **_f(condiciones=[uno["valor"]])}).json()
    assert r["total"] == uno["n"]
    assert all(any(c["campo"] == uno["valor"] for c in x["condiciones"]) for x in r["items"])
    # Orden por columna
    r = interno.get("/aranceles/reglas", params={"size": 20, "orden": "prioridad:asc"}).json()["items"]
    assert [x["prioridad"] for x in r] == sorted(x["prioridad"] for x in r)


# ---- Arancel: códigos nacionales y partidas SAC (paginados en el servidor) ----------------

def test_codigos_nacionales_por_columna(interno):
    total = interno.get("/aranceles/codigos", params={"size": 1}).json()["total"]
    paises = interno.get("/aranceles/codigos/valores", params={"columna": "pais"}).json()
    assert total and sum(v["n"] for v in paises) == total
    uno = paises[0]
    r = interno.get("/aranceles/codigos", params={"size": 500, **_f(pais=[uno["valor"]])}).json()
    assert r["total"] == uno["n"] and {x["pais"] for x in r["items"]} == {uno["valor"]}
    # La fuente oficial vive en otra tabla: filtra y cuenta códigos, no fuentes
    fuentes = interno.get("/aranceles/codigos/valores", params={"columna": "fuente"}).json()
    assert sum(v["n"] for v in fuentes) == total
    f1 = fuentes[0]
    r = interno.get("/aranceles/codigos", params={"size": 500, **_f(fuente=[f1["valor"] if f1["valor"] is not None else "__vacio__"])}).json()
    assert r["total"] == f1["n"] and all(x["fuente_oficial"] == f1["valor"] for x in r["items"])
    # Con el país filtrado, los valores de la fuente son solo los de ese país
    del_pais = interno.get("/aranceles/codigos/valores", params={"columna": "fuente", **_f(pais=[uno["valor"]])}).json()
    assert sum(v["n"] for v in del_pais) == uno["n"]
    assert interno.get("/aranceles/codigos/valores", params={"columna": "descripcion"}).status_code == 422


def test_partidas_sac_por_columna(interno):
    total = interno.get("/aranceles/sac", params={"size": 1}).json()["total"]
    niveles = {v["valor"]: v["n"] for v in interno.get("/aranceles/sac/valores", params={"columna": "nivel"}).json()}
    assert set(niveles) <= {"PARTIDA", "SUBPARTIDA"} and sum(niveles.values()) == total
    r = interno.get("/aranceles/sac", params={"size": 500, **_f(nivel=["PARTIDA"])}).json()
    assert r["total"] == niveles["PARTIDA"] and all(len(x["codigo"]) == 4 for x in r["items"])
    fuentes = {v["valor"]: v["n"] for v in interno.get("/aranceles/sac/valores", params={"columna": "fuente"}).json()}
    assert sum(fuentes.values()) == total and "oficial" in fuentes


# ---- Conocimiento de la empresa: historial paginado con filtros por columna ---------------

def test_historial_de_clasificacion_por_columna(interno):
    total = interno.get("/conocimiento/historial", params={"size": 1}).json()["total"]
    paises = interno.get("/conocimiento/historial/valores", params={"columna": "pais"}).json()
    assert total > 50 and sum(v["n"] for v in paises) == total
    uno = next(v for v in paises if v["valor"])
    r = interno.get("/conocimiento/historial", params={"size": 200, **_f(pais=[uno["valor"]])}).json()
    assert r["total"] == uno["n"] and {x["pais"] for x in r["items"]} == {uno["valor"]}
    # Se llega a la segunda página (antes la pantalla solo mostraba las primeras 50)
    p2 = interno.get("/conocimiento/historial", params={"size": 50, "page": 2}).json()["items"]
    assert p2 and not {x["id"] for x in p2} & {x["id"] for x in interno.get("/conocimiento/historial", params={"size": 50}).json()["items"]}
    r = interno.get("/conocimiento/historial", params={"size": 30, "orden": "codigo:asc"}).json()["items"]
    assert [x["codigo"] for x in r] == sorted(x["codigo"] for x in r)
