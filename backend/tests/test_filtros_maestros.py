"""Filtros por columna de los datos maestros y de la bitácora (TablaDatos en
modo servidor; app/modulos/comun/tabla.py): cada catálogo, la vista por
genérico y la bitácora filtran por uno o varios valores de cada columna (`f`
en JSON) y dan los valores únicos de una columna con cuántos registros tienen
cada uno, bajo los demás filtros y el alcance del usuario."""
import json


def _f(**kw):
    return {"f": json.dumps(kw)}


# ---- Catálogos -------------------------------------------------------------------

def test_catalogo_da_los_valores_de_una_columna_con_su_cuenta(interno):
    total = interno.get("/catalogos/puertos", params={"size": 200}).json()["total"]
    vals = interno.get("/catalogos/puertos/valores", params={"columna": "pais"}).json()
    assert vals and sum(v["n"] for v in vals) == total
    assert len({v["valor"] for v in vals}) == len(vals)


def test_catalogo_filtra_por_varios_valores_y_su_filtro_no_limita_sus_valores(interno):
    paises = interno.get("/catalogos/puertos/valores", params={"columna": "pais"}).json()
    assert len(paises) >= 2
    elegidos = [paises[0]["valor"], paises[1]["valor"]]
    r = interno.get("/catalogos/puertos", params={"size": 200, **_f(pais=elegidos)}).json()
    assert r["total"] == paises[0]["n"] + paises[1]["n"]
    assert {x["pais"] for x in r["items"]} == set(elegidos)
    # Como en Excel: con el país filtrado, su filtro sigue mostrando todos los países
    con = interno.get("/catalogos/puertos/valores", params={"columna": "pais", **_f(pais=elegidos[:1])}).json()
    assert {v["valor"] for v in con} == {v["valor"] for v in paises}
    # Las demás columnas solo muestran lo que queda con ese país
    tipos = interno.get("/catalogos/puertos/valores", params={"columna": "tipo", **_f(pais=elegidos[:1])}).json()
    solo = interno.get("/catalogos/puertos", params={"size": 200, **_f(pais=elegidos[:1])}).json()["items"]
    assert {v["valor"] for v in tipos} == {x["tipo"] for x in solo}


def test_catalogo_combina_busqueda_filtros_de_campo_y_de_columna(interno):
    base = interno.get("/catalogos/puertos", params={"size": 200}).json()["items"]
    uno = base[0]
    r = interno.get("/catalogos/puertos", params={"q": uno["codigo"], **_f(pais=[uno["pais"]])}).json()
    assert any(x["id"] == uno["id"] for x in r["items"]) and all(x["pais"] == uno["pais"] for x in r["items"])
    # Valores bajo la búsqueda: solo los de lo encontrado
    vals = interno.get("/catalogos/puertos/valores", params={"columna": "codigo", "q": uno["codigo"]}).json()
    assert uno["codigo"] in {v["valor"] for v in vals}
    assert sum(v["n"] for v in vals) == interno.get("/catalogos/puertos", params={"q": uno["codigo"]}).json()["total"]


def test_catalogo_booleano_y_vacio(interno):
    vals = interno.get("/catalogos/marcas/valores", params={"columna": "activa"}).json()
    assert {v["valor"] for v in vals} <= {True, False}
    activas = next(v["n"] for v in vals if v["valor"] is True)
    assert interno.get("/catalogos/marcas", params=_f(activa=["true"])).json()["total"] == activas
    # Ningún puerto tiene el país vacío; con «vacío» y un país, solo ese país
    puertos = interno.get("/catalogos/puertos", params={"size": 200}).json()["items"]
    assert interno.get("/catalogos/puertos", params=_f(pais=["__vacio__"])).json()["total"] == 0
    r = interno.get("/catalogos/puertos", params=_f(pais=["__vacio__", puertos[0]["pais"]])).json()
    assert r["total"] > 0 and all(x["pais"] == puertos[0]["pais"] for x in r["items"])


def test_catalogo_referencia_varios_y_numeros(interno):
    # Una referencia (id) filtra por su id; la pantalla muestra su nombre
    centros = interno.get("/catalogos/centros", params={"size": 200}).json()["items"]
    soc = centros[0]["sociedad_id"]
    vals = interno.get("/catalogos/centros/valores", params={"columna": "sociedad_id"}).json()
    assert soc in {v["valor"] for v in vals}
    r = interno.get("/catalogos/centros", params={"size": 200, **_f(sociedad_id=[soc])}).json()
    assert r["total"] == next(v["n"] for v in vals if v["valor"] == soc)
    # Varios (marcas de un proveedor): la fila pasa si tiene alguna de las elegidas
    marcas = interno.get("/catalogos/proveedores/valores", params={"columna": "marcas"}).json()
    assert marcas
    m = marcas[0]
    r = interno.get("/catalogos/proveedores", params={"size": 200, **_f(marcas=[str(m["valor"])])}).json()
    assert r["total"] == m["n"] and all(m["valor"] in x["marcas"] for x in r["items"])
    # Un número con decimales se elige por su texto, igual que lo devuelve el servidor
    caps = interno.get("/catalogos/tipos_unidad/valores", params={"columna": "capacidad_cbm"}).json()
    con = [v for v in caps if v["valor"] is not None]
    assert con and all(isinstance(v["valor"], str) for v in con)
    r = interno.get("/catalogos/tipos_unidad", params=_f(capacidad_cbm=[con[0]["valor"]])).json()
    assert r["total"] == con[0]["n"]


def test_catalogo_articulos_por_tipo_y_codigo(interno):
    """Los packs y kits son artículos de tipo compuesto: se filtran por tipo y por su código."""
    tipos = {v["valor"]: v["n"] for v in interno.get("/catalogos/articulos/valores", params={"columna": "tipo"}).json()}
    assert tipos.get("PREPACK") and tipos.get("SOLIDO")
    r = interno.get("/catalogos/articulos", params={"size": 200, **_f(tipo=["PREPACK"])}).json()
    assert r["total"] == tipos["PREPACK"] and {x["tipo"] for x in r["items"]} == {"PREPACK"}
    sku = r["items"][0]["sku"]
    r = interno.get("/catalogos/articulos", params=_f(sku=[sku])).json()
    assert r["total"] == 1 and r["items"][0]["sku"] == sku


def test_catalogo_columnas_y_filtros_invalidos(interno):
    assert interno.get("/catalogos/puertos/valores", params={"columna": "inventada"}).status_code == 422
    # La regla de lead time no se filtra
    assert interno.get("/catalogos/leadtimes/valores", params={"columna": "pasos"}).status_code == 422
    assert interno.get("/catalogos/puertos", params={"f": "{no es json"}).status_code == 422
    assert interno.get("/catalogos/inventado/valores", params={"columna": "codigo"}).status_code == 404
    # Una columna desconocida en `f` se ignora
    assert interno.get("/catalogos/puertos", params=_f(inventada=["x"])).status_code == 200


def test_catalogo_exporta_con_los_filtros_de_columna(interno):
    paises = interno.get("/catalogos/puertos/valores", params={"columna": "pais"}).json()
    r = interno.get("/catalogos/puertos/exportar", params={"formato": "xlsx", **_f(pais=[paises[0]["valor"]])})
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_catalogo_valores_exigen_permiso(tnf):
    # Un usuario sin acceso a los datos maestros no ve sus valores
    assert tnf.get("/catalogos/puertos/valores", params={"columna": "pais"}).status_code == 403


# ---- Vista por genérico -------------------------------------------------------------

def test_genericos_filtran_por_columna_y_dan_sus_valores(interno):
    total = interno.get("/catalogos/genericos", params={"size": 200}).json()["total"]
    provs = interno.get("/catalogos/genericos/valores", params={"columna": "proveedor_id"}).json()
    assert provs and sum(v["n"] for v in provs) == total
    uno = provs[0]
    r = interno.get("/catalogos/genericos", params={"size": 200, **_f(proveedor_id=[uno["valor"]])}).json()
    assert r["total"] == uno["n"] and {x["proveedor_id"] for x in r["items"]} == {uno["valor"]}
    # Un valor de variante: el producto pasa si alguna de sus variantes lo tiene
    tallas = interno.get("/catalogos/genericos/valores", params={"columna": "var.TALLA"}).json()
    t = next(v for v in tallas if v["valor"])
    r = interno.get("/catalogos/genericos", params={"size": 200, **_f(**{"var.TALLA": [t["valor"]]})}).json()
    assert r["total"] == t["n"]
    # Un atributo del producto
    modelos = interno.get("/catalogos/genericos/valores", params={"columna": "atr.MODELO"}).json()
    m = next(v for v in modelos if v["valor"])
    r = interno.get("/catalogos/genericos", params={"size": 200, **_f(**{"atr.MODELO": [m["valor"]]})}).json()
    assert r["total"] == m["n"] and all(x["atributos"].get("MODELO") == m["valor"] for x in r["items"])
    # Orden por el nombre del proveedor
    r = interno.get("/catalogos/genericos", params={"size": 200, "orden": "proveedor_id:desc"}).json()["items"]
    nombres = [x["proveedor"] or "" for x in r]
    assert nombres == sorted(nombres, reverse=True)
    assert interno.get("/catalogos/genericos/valores", params={"columna": "inventada"}).status_code == 422


# ---- Bitácora -------------------------------------------------------------------------

def test_bitacora_valores_y_filtros_por_columna(admin):
    total = admin.get("/auditoria", params={"size": 200}).json()["total"]
    ents = admin.get("/auditoria/valores", params={"columna": "entidad"}).json()
    assert ents and sum(v["n"] for v in ents) == total
    elegidas = [e["valor"] for e in ents[:2]]
    r = admin.get("/auditoria", params={"size": 200, **_f(entidad=elegidas)}).json()
    assert r["total"] == sum(e["n"] for e in ents[:2]) and {x["entidad"] for x in r["items"]} <= set(elegidas)
    # Por día: la fecha se filtra por su día
    dias = admin.get("/auditoria/valores", params={"columna": "fecha"}).json()
    d = next(v for v in dias if v["valor"])
    r = admin.get("/auditoria", params={"size": 200, **_f(fecha=[str(d["valor"])])}).json()
    assert r["total"] == d["n"] and all(str(x["fecha"]).startswith(str(d["valor"])) for x in r["items"])
    # Por usuario (su nombre) y combinado con los filtros de la pantalla
    usuarios = admin.get("/auditoria/valores", params={"columna": "usuario", "entidad": elegidas[0]}).json()
    assert sum(v["n"] for v in usuarios) == ents[0]["n"]
    # Orden por una columna
    r = admin.get("/auditoria", params={"size": 50, "orden": "entidad:asc"}).json()["items"]
    assert [x["entidad"] for x in r] == sorted(x["entidad"] for x in r)


def test_bitacora_valores_solo_para_la_administracion(admin, interno):
    assert interno.get("/auditoria/valores", params={"columna": "entidad"}).status_code == 403
    assert admin.get("/auditoria/valores", params={"columna": "inventada"}).status_code == 422
    assert admin.get("/auditoria", params={"f": "[1]"}).status_code == 422
