"""Filtros por columna de los tableros de seguimiento (TablaDatos): las OCs, los
embarques, la facturación y empaque y la lista de lead times filtran por uno o
varios valores de cada columna (`f` en JSON) y dan los valores únicos de una
columna con cuántas filas tienen cada uno, bajo los demás filtros (los de la
pantalla y los de las otras columnas) y el alcance del usuario. Los tableros se
calculan en memoria, así que el filtro es el de seguimiento.filtrar_columnas."""
import json

import pytest


def _f(**kw):
    return {"f": json.dumps(kw)}


TODO = {"size": 200}


@pytest.mark.parametrize("lista, columna", [
    ("ordenes", "estado"), ("embarques", "estado"), ("documentos", "estado_factura"), ("leadtimes", "origen"),
])
def test_valores_con_su_cuenta_y_filtro_de_uno_o_varios(interno, lista, columna):
    total = interno.get(f"/seguimiento/{lista}", params=TODO).json()["total"]
    vals = interno.get(f"/seguimiento/{lista}/valores", params={"columna": columna}).json()
    assert vals and sum(v["n"] for v in vals) == total
    assert len({json.dumps(v["valor"]) for v in vals}) == len(vals)
    uno = next(v for v in vals if v["valor"] is not None)
    r = interno.get(f"/seguimiento/{lista}", params={**TODO, **_f(**{columna: [uno["valor"]]})}).json()
    assert r["total"] == uno["n"]
    # Varios valores: suman sus filas
    if len(vals) > 1:
        dos = [v for v in vals if v["valor"] is not None][:2]
        r = interno.get(f"/seguimiento/{lista}", params={**TODO, **_f(**{columna: [v["valor"] for v in dos]})}).json()
        assert r["total"] == sum(v["n"] for v in dos)


def test_ordenes_como_excel(interno):
    estados = interno.get("/seguimiento/ordenes/valores", params={"columna": "estado"}).json()
    elegido = estados[0]["valor"]
    r = interno.get("/seguimiento/ordenes", params={**TODO, **_f(estado=[elegido])}).json()
    assert r["items"] and {o["estado"] for o in r["items"]} == {elegido}
    # Con el estado filtrado, su propio filtro sigue mostrando todos los estados
    con = interno.get("/seguimiento/ordenes/valores", params={"columna": "estado", **_f(estado=[elegido])}).json()
    assert {v["valor"] for v in con} == {v["valor"] for v in estados}
    # Las demás columnas solo muestran lo que queda con ese estado
    ocs = interno.get("/seguimiento/ordenes/valores", params={"columna": "oc", **_f(estado=[elegido])}).json()
    assert {v["valor"] for v in ocs} == {o["oc"] for o in r["items"]}
    # Los indicadores y el resumen por estado no cambian con el filtro de una columna
    sin = interno.get("/seguimiento/ordenes", params=TODO).json()
    assert r["kpis"] == sin["kpis"] and r["estados"] == sin["estados"]


def test_ordenes_fechas_avance_y_listas(interno):
    xf = interno.get("/seguimiento/ordenes/valores", params={"columna": "fecha_xf"}).json()
    dia = next(v for v in xf if v["valor"])
    r = interno.get("/seguimiento/ordenes", params={**TODO, **_f(fecha_xf=[dia["valor"]])}).json()
    assert r["total"] == dia["n"] and all(o["fecha_xf"] == dia["valor"] for o in r["items"])
    av = interno.get("/seguimiento/ordenes/valores", params={"columna": "avance"}).json()
    assert all(isinstance(v["valor"], int) for v in av)
    # Una columna con varios datos por fila (los embarques de la OC): pasa si alguno coincide
    emb = interno.get("/seguimiento/ordenes/valores", params={"columna": "embarques"}).json()
    codigo = next(v for v in emb if v["valor"])
    r = interno.get("/seguimiento/ordenes", params={**TODO, **_f(embarques=[codigo["valor"]])}).json()
    assert r["total"] == codigo["n"] and all(codigo["valor"] in o["embarques"] for o in r["items"])


def test_valor_vacio(interno):
    # Las facturas sin packing list tienen el estado del PL vacío
    vals = interno.get("/seguimiento/documentos/valores", params={"columna": "estado_pl"}).json()
    vacio = next((v for v in vals if v["valor"] is None), None)
    r = interno.get("/seguimiento/documentos", params={**TODO, **_f(estado_pl=["__vacio__"])}).json()
    assert r["total"] == (vacio["n"] if vacio else 0)
    assert all(x["pl_id"] is None for x in r["items"])
    if vacio:  # el vacío va primero en la lista de valores
        assert vals[0]["valor"] is None


def test_buscar_dentro_de_los_valores(interno):
    todos = interno.get("/seguimiento/embarques/valores", params={"columna": "embarque"}).json()
    parte = todos[0]["valor"][-3:].lower()
    algunos = interno.get("/seguimiento/embarques/valores", params={"columna": "embarque", "buscar": parte}).json()
    assert algunos and all(parte in v["valor"].lower() for v in algunos)


def test_con_los_filtros_de_la_pantalla(interno):
    # La búsqueda de la pantalla también limita los valores de cada columna
    docs = interno.get("/seguimiento/documentos", params=TODO).json()["items"]
    factura = docs[0]["factura"]
    vals = interno.get("/seguimiento/documentos/valores", params={"columna": "factura", "q": factura}).json()
    assert factura in {v["valor"] for v in vals}
    assert len(vals) < len({d["factura"] for d in docs}) or len(docs) == 1
    # El filtro de varios embarques de la pantalla (antes solo aceptaba uno)
    assert interno.get("/seguimiento/documentos", params={"embarque_id": "1,2"}).status_code == 200


def test_columnas_y_filtros_invalidos(interno):
    for lista in ("ordenes", "embarques", "documentos", "leadtimes"):
        assert interno.get(f"/seguimiento/{lista}/valores", params={"columna": "inventada"}).status_code == 422
        assert interno.get(f"/seguimiento/{lista}", params={"f": "{no es json"}).status_code == 422
        # Una columna desconocida en `f` se ignora
        assert interno.get(f"/seguimiento/{lista}", params=_f(inventada=["x"])).status_code == 200


def test_alcance_del_proveedor_y_permiso(interno, tnf):
    # Con un proveedor elegido, los valores son solo los suyos
    provs = interno.get("/proveedores").json()
    provs = provs.get("items", provs) if isinstance(provs, dict) else provs
    tnf_id = next(p["id"] for p in provs if p["nombre"] == "The North Face")
    for lista, columna in (("ordenes", "proveedor"), ("leadtimes", "proveedor"), ("documentos", "proveedor")):
        todos = interno.get(f"/seguimiento/{lista}/valores", params={"columna": columna}).json()
        assert len(todos) >= 2
        vals = interno.get(f"/seguimiento/{lista}/valores", params={"columna": columna, "proveedor_id": tnf_id}).json()
        assert {v["valor"] for v in vals} == {"The North Face"}
    # Sin permiso de seguimiento (el rol de proveedor) no hay valores
    assert tnf.get("/seguimiento/ordenes/valores", params={"columna": "estado"}).status_code == 403


def test_la_exportacion_respeta_los_filtros_de_columna(interno):
    vals = interno.get("/seguimiento/documentos/valores", params={"columna": "estado_factura"}).json()
    r = interno.get("/seguimiento/documentos/exportar", params={"formato": "xlsx", **_f(estado_factura=[vals[0]["valor"]])})
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert interno.get("/seguimiento/ordenes/exportar", params={"formato": "pdf", **_f(estado=["RECIBIDA"])}).status_code == 200
