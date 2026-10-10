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
