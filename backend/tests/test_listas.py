"""Listas de valores configurables (Datos maestros → Listas de valores):
unidades, monedas, incoterms, modos y modalidades de transporte y tipos. Ni el
servidor ni las pantallas tienen esos valores fijos en el código."""
import re

from test_oficial import RAIZ

from app.core import listas


def _valores(api, lista):
    return {v["codigo"]: v for v in api.get("/listas").json()[lista]}


def _id_valor(api, lista, codigo):
    items = api.get("/catalogos/listas", params={"lista": lista, "size": 200}).json()["items"]
    return next(x["id"] for x in items if x["codigo"] == codigo)


def test_listas_de_fabrica(interno):
    r = interno.get("/listas").json()
    assert set(r) == set(listas.LISTAS)
    for lista, valores in listas.FABRICA.items():
        assert [v["codigo"] for v in r[lista]] == [v["codigo"] for v in valores], lista
    assert r["moneda"][0] == {"codigo": "USD", "nombre": "US dollar", "simbolo": "$", "decimales": 2,
                              "letras_en": "US DOLLAR|US DOLLARS", "letras_es": "DÓLAR|DÓLARES"}
    aereo = next(m for m in r["modo_transporte"] if m["codigo"] == "AEREO")
    assert aereo["calculo"] == "PESO_COBRABLE" and aereo["factor"] == 167


def test_unidades_salen_de_la_lista():
    from app.modulos.maestros.unidades import codigos, de_articulo, normalizar

    assert codigos() == [v["codigo"] for v in listas.FABRICA["unidad"]]
    assert "CJ" not in de_articulo() and {"KG", "L", "M", "DOC"} <= set(de_articulo())
    assert normalizar("pcs") == "UN" and normalizar("Kgs") == "KG" and normalizar("LTS") == "L" and normalizar("xyz") is None


def test_pantallas_sin_listas_fijas():
    """Las pantallas leen las listas de la empresa: ni las unidades ni los modos
    de transporte están escritos en el código."""
    src = RAIZ.parent / "frontend" / "src"
    unidades = (src / "nucleo" / "unidades.js").read_text(encoding="utf-8")
    assert not re.search(r"\b(PAR|DOC|JGO|KG|ROL)\b", unidades)
    for archivo in src.rglob("*.*"):
        if archivo.suffix in (".vue", ".js"):
            assert not re.search(r"'(MARITIMO|AEREO|TERRESTRE)'", archivo.read_text(encoding="utf-8")), archivo


def test_una_unidad_nueva_se_usa_en_todo(interno):
    r = interno.post("/catalogos/listas", {"lista": "unidad", "codigo": "BOT", "nombre": "bottle", "nombre_plural": "bottles",
                                           "alias": "BOTELLA, BOTELLAS", "contable": True, "orden": 50})
    assert r.status_code == 200, r.text
    try:
        assert _valores(interno, "unidad")["BOT"]["nombre_plural"] == "bottles"
        # El catálogo de artículos ofrece la unidad nueva y el formulario de genéricos la acepta
        meta = {c["tipo"]: c for c in interno.get("/catalogos").json()}
        unidad = next(c for c in meta["articulos"]["campos"] if c["nombre"] == "unidad")
        assert ["BOT", "bottle"] in unidad["opciones"]
        assert "listas" in meta and "liberaciones" in meta and "categorias" in meta
    finally:
        assert interno.delete_(f"/catalogos/listas/{r.json()['id']}").status_code == 200
    assert "BOT" not in _valores(interno, "unidad")


def test_valores_de_sistema(interno):
    cj = _id_valor(interno, "unidad", "CJ")
    assert interno.delete_(f"/catalogos/listas/{cj}").status_code == 409
    r = interno.patch(f"/catalogos/listas/{cj}", {"activo": False})
    assert r.status_code == 422 and "cannot be deactivated" in r.text
    r = interno.patch(f"/catalogos/listas/{cj}", {"codigo": "CTN"})
    assert r.status_code == 422 and "code cannot change" in r.text
    # Renombrarlo sí se puede
    assert interno.patch(f"/catalogos/listas/{cj}", {"nombre": "carton"}).status_code == 200
    assert interno.patch(f"/catalogos/listas/{cj}", {"nombre": "prepack carton"}).status_code == 200


def test_validaciones_de_las_listas(interno):
    def rechazo(datos, texto):
        r = interno.post("/catalogos/listas", datos)
        assert r.status_code == 422 and texto in r.text, r.text

    rechazo({"lista": "modo_transporte", "codigo": "DRON", "nombre": "Drone", "calculo": "PESO_COBRABLE"}, "volumetric factor")
    rechazo({"lista": "moneda", "codigo": "BTC", "nombre": "Bitcoin", "letras_en": "BITCOIN"}, "separated by |")
    rechazo({"lista": "moneda", "codigo": "BTC", "nombre": "Bitcoin", "decimales": 8}, "At most 4 decimals")
    rechazo({"lista": "modalidad_transporte", "codigo": "PAQ", "nombre": "Parcel"}, "transport mode of this modality")
    rechazo({"lista": "no_existe", "codigo": "X", "nombre": "X"}, "invalid value")
    usd = _id_valor(interno, "moneda", "USD")
    r = interno.patch(f"/catalogos/listas/{usd}", {"lista": "incoterm"})
    assert r.status_code == 422 and "another list" in r.text


def test_atributos_ajenos_no_se_guardan(interno):
    r = interno.post("/catalogos/listas", {"lista": "incoterm", "codigo": "XYZ", "nombre": "Test term", "simbolo": "$",
                                           "factor": 3})
    assert r.status_code == 200, r.text
    try:
        assert r.json()["simbolo"] is None and r.json()["factor"] is None
    finally:
        interno.delete_(f"/catalogos/listas/{r.json()['id']}")


def test_monto_en_letras_y_modos_segun_la_lista():
    from app.modulos.documentos import idioma_doc
    from app.modulos.documentos.letras import monto_en_letras

    propias = {**listas.FABRICA, "moneda": [{"codigo": "XAU", "nombre": "Gold", "letras_en": "OUNCE|OUNCES",
                                              "letras_es": "ONZA|ONZAS", "decimales": 2}]}
    listas.usar_listas(propias)
    try:
        idioma_doc.usar("es")
        assert monto_en_letras(2, "XAU") == "DOS ONZAS CON 00/100"
        idioma_doc.usar("en")
        assert monto_en_letras(1, "XAU") == "ONE OUNCE AND 00/100"
        assert monto_en_letras(1, "USD") == "ONE USD AND 00/100"  # sin la moneda en la lista: su código
    finally:
        listas.usar_listas(None)


def test_sugerencia_con_modo_desconocido(interno):
    r = interno.get("/sugerencia-unidades", params={"cbm": 10, "kg": 100, "modo": "DRON"})
    assert r.status_code == 422
    r = interno.get("/sugerencia-unidades", params={"cbm": 10, "kg": 1000, "modo": "AEREO"}).json()
    assert r["modos"]["AEREO"][0]["peso_cobrable"] == 1670.0
