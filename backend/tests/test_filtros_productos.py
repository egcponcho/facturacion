"""Filtros por columna de la tabla de productos (app/modulos/comun/tabla.py):
la lista filtra por uno o varios valores de cada columna (`f` en JSON) y
`/productos/valores` da los valores únicos de una columna con cuántos
productos tienen cada uno, bajo los demás filtros y el alcance del usuario."""
import json

import pytest

TODOS = {"estado": ""}  # sin la vista de estado de la bandeja


def _f(**kw):
    return {"f": json.dumps(kw)}


def _valores(api, columna, **params):
    r = api.get("/productos/valores", params={**TODOS, "columna": columna, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _lista(api, **params):
    r = api.get("/productos", params={**TODOS, "size": 200, **params})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def flujo(admin):
    antes = admin.get("/flujo-clasificacion").json()["valores"]
    yield lambda **cambios: admin.put("/flujo-clasificacion", cambios)
    assert admin.put("/flujo-clasificacion", antes).status_code == 200


def test_valores_unicos_con_su_cuenta(interno):
    total = _lista(interno, size=1)["total"]
    for columna in ("estado", "producto", "proveedor", "tipo", "codigo", "origen", "generico"):
        vals = _valores(interno, columna)
        assert vals and sum(v["n"] for v in vals) == total, columna
        assert len({v["valor"] for v in vals}) == len(vals), columna


def test_varios_valores_y_el_filtro_de_la_columna_no_limita_sus_valores(interno):
    estados = [v["valor"] for v in _valores(interno, "estado")]
    assert len(estados) >= 2
    elegidos = estados[:2]
    r = _lista(interno, **_f(estado=elegidos))
    assert r["items"] and {x["estado"] for x in r["items"]} <= set(elegidos)
    # Como en Excel: con el estado filtrado, su filtro sigue mostrando todos los estados
    con = _valores(interno, "estado", **_f(estado=elegidos[:1]))
    assert {v["valor"] for v in con} == set(estados)
    # Pero las demás columnas solo muestran lo que queda con ese estado
    prov = _valores(interno, "proveedor", **_f(estado=elegidos[:1]))
    solo = _lista(interno, **_f(estado=elegidos[:1]))
    assert {v["valor"] for v in prov} == {x["proveedor"] for x in solo["items"]}
    # Los indicadores de la bandeja cuentan con los filtros por columna
    assert solo["kpis"]["total"] == solo["total"]


def _nombre(x) -> str:
    """Lo que muestra la columna Producto: el nombre o, sin nombre, el código."""
    return x["nombre"] or x["codigo_generico"]


def test_la_vista_de_estado_y_la_busqueda_limitan_los_valores(interno):
    revision = _lista(interno, estado="borradores")
    vals = _valores(interno, "estado", estado="borradores")
    assert sum(v["n"] for v in vals) == revision["total"]
    assert {v["valor"] for v in vals} <= {"borrador", "sugerida", "observado"}
    # La columna Producto muestra el nombre (o el código, si no tiene)
    primero = _lista(interno, size=1)["items"][0]
    nombre = primero["nombre"] or primero["codigo_generico"]
    con_q = _valores(interno, "producto", q=nombre)
    assert nombre in {v["valor"] for v in con_q}
    assert sum(v["n"] for v in con_q) == _lista(interno, q=nombre)["total"]


def test_filtrar_por_producto_y_buscar_dentro_de_los_valores(interno):
    todos = _valores(interno, "producto")
    uno = todos[0]
    r = _lista(interno, **_f(producto=[uno["valor"]]))
    assert r["total"] == uno["n"] and {_nombre(x) for x in r["items"]} == {uno["valor"]}
    parte = uno["valor"][:3].lower()
    algunos = _valores(interno, "producto", buscar=parte)
    assert algunos and all(parte in v["valor"].lower() for v in algunos)


def test_codigo_aprobado_o_sugerido(interno):
    vals = _valores(interno, "codigo")
    con = next(v for v in vals if v["valor"])
    r = _lista(interno, **_f(codigo=[con["valor"]]))
    digitos = con["valor"].replace(".", "")
    assert r["total"] == con["n"]
    assert all((x["codigo"] or x["sugerido"] or "").replace(".", "") == digitos for x in r["items"])


def test_valor_vacio(interno):
    vals = _valores(interno, "origen")
    vacios = sum(v["n"] for v in vals if v["valor"] is None)
    assert _lista(interno, **_f(origen=["__vacio__"]))["total"] == vacios
    otro = next(v for v in vals if v["valor"])
    r = _lista(interno, **_f(origen=["__vacio__", otro["valor"]]))
    assert r["total"] == vacios + otro["n"]
    assert all(x["pais_origen"] in (None, otro["valor"]) for x in r["items"])


def test_columnas_y_filtros_invalidos(interno):
    assert interno.get("/productos/valores", params={"columna": "inventada"}).status_code == 422
    assert interno.get("/productos", params={"f": "{no es json"}).status_code == 422
    # Una columna desconocida en `f` se ignora
    assert interno.get("/productos", params=_f(inventada=["x"])).status_code == 200


def test_orden_por_proveedor(interno):
    items = _lista(interno, orden="proveedor:asc")["items"]
    assert [x["proveedor"] for x in items] == sorted(x["proveedor"] for x in items)


def test_exportar_con_filtros_por_columna(interno):
    uno = _valores(interno, "producto")[0]["valor"]
    r = interno.get("/productos/exportar", params={**TODOS, "formato": "xlsx", **_f(producto=[uno])})
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_el_proveedor_solo_ve_sus_productos_y_sus_valores(tnf, interno):
    assert [v["valor"] for v in _valores(tnf, "proveedor")] == ["The North Face"]
    propios = _lista(tnf)
    estilos = _valores(tnf, "producto")
    assert sum(v["n"] for v in estilos) == propios["total"]
    assert {v["valor"] for v in estilos} == {_nombre(x) for x in propios["items"]}
    # Pedir otro proveedor no amplía el alcance
    otros = {x["proveedor_id"] for x in _lista(interno)["items"]} - {x["proveedor_id"] for x in propios["items"]}
    assert otros
    ajeno = otros.pop()
    assert [v["valor"] for v in _valores(tnf, "proveedor", proveedor_id=ajeno)] == ["The North Face"]
    # Filtrar por un producto ajeno no trae nada
    ajenos = {_nombre(x) for x in _lista(interno, proveedor_id=ajeno)["items"]} - {_nombre(x) for x in propios["items"]}
    assert _lista(tnf, **_f(producto=sorted(ajenos)))["total"] == 0


def test_sin_la_sugerencia_el_codigo_filtra_solo_el_aprobado(tnf, flujo):
    con = {v["valor"] for v in _valores(tnf, "codigo") if v["valor"]}
    assert flujo(proveedor_ve_sugerencia=False).status_code == 200
    vals = _valores(tnf, "codigo")
    aprobados = {(x["codigo"] or "").replace(".", "") for x in _lista(tnf)["items"] if x["codigo"]}
    assert {v["valor"] for v in vals if v["valor"]} == aprobados
    assert aprobados <= con
