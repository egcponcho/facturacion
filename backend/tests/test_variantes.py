"""Atributos configurables, kits y escalas de valores."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import ArticuloAtributo


def _cat(api, catalogo, **params):
    return api.get(f"/catalogos/{catalogo}", params={"size": 200, **params}).json()["items"]


def test_atributos_en_uso_y_propios(interno):
    atributos = {a["codigo"]: a for a in _cat(interno, "atributos")}
    assert {"TALLA", "COLOR", "MARCA", "MODELO"} <= set(atributos)
    assert atributos["TALLA"]["nivel"] == "VARIANTE" and atributos["MARCA"]["nivel"] == "PRODUCTO"
    talla = atributos["TALLA"]
    # En uso: se renombra, pero no cambia de código ni de nivel y no se borra
    assert interno.patch(f"/catalogos/atributos/{talla['id']}", {"nombre": "Size / capacity"}).status_code == 200
    assert interno.patch(f"/catalogos/atributos/{talla['id']}", {"codigo": "TAMANO"}).status_code == 422
    assert interno.patch(f"/catalogos/atributos/{talla['id']}", {"nivel": "PRODUCTO"}).status_code == 422
    assert interno.delete_(f"/catalogos/atributos/{talla['id']}").status_code == 409
    interno.patch(f"/catalogos/atributos/{talla['id']}", {"nombre": talla["nombre"]})

    r = interno.post("/catalogos/atributos", {"codigo": "MATERIAL", "nombre": "Material", "nivel": "VARIANTE", "orden": 3})
    assert r.status_code == 200, r.text
    material = r.json()
    try:
        # El artículo tiene el campo y su valor se guarda en su propia fila
        meta = {c["tipo"]: c for c in interno.get("/catalogos").json()}
        campo = next(c for c in meta["articulos"]["campos"] if c["nombre"] == "atr.MATERIAL")
        assert campo["seccion"] == "variante"
        art = _cat(interno, "articulos", tipo="SOLIDO")[0]
        r = interno.patch(f"/catalogos/articulos/{art['id']}", {"atr.MATERIAL": "Canvas"})
        assert r.status_code == 200, r.text
        assert r.json()["atr.MATERIAL"] == "Canvas"
        with SessionLocal() as db:
            filas = db.scalars(select(ArticuloAtributo).where(ArticuloAtributo.articulo_id == art["id"])).all()
            valores = {f.atributo.codigo: f.valor for f in filas}
            assert valores["MATERIAL"] == "Canvas"
            # Talla y color son valores de variante como cualquier otro
            assert valores.get("TALLA") == art["atr.TALLA"] and valores.get("COLOR") == art["atr.COLOR"]
        # Se filtra por su valor como cualquier columna
        import json
        items = interno.get("/catalogos/articulos", params={"f": json.dumps({"atr.MATERIAL": ["Canvas"]})}).json()["items"]
        assert [x["id"] for x in items] == [art["id"]]
        # Un atributo en uso no cambia de código ni se borra
        assert interno.patch(f"/catalogos/atributos/{material['id']}", {"codigo": "TELA"}).status_code == 422
        assert interno.delete_(f"/catalogos/atributos/{material['id']}").status_code == 409
        assert interno.patch(f"/catalogos/articulos/{art['id']}", {"atr.NOEXISTE": "x"}).status_code == 422
        # Un atributo de producto no se escribe en la variante
        assert interno.patch(f"/catalogos/articulos/{art['id']}", {"atr.MODELO": "x"}).status_code == 422
        # Vaciar el valor quita la fila
        assert interno.patch(f"/catalogos/articulos/{art['id']}", {"atr.MATERIAL": ""}).json()["atr.MATERIAL"] is None
    finally:
        interno.delete_(f"/catalogos/atributos/{material['id']}")


def test_kit_con_articulos_de_varios_productos(interno):
    solidos = _cat(interno, "articulos", tipo="SOLIDO")
    a = solidos[0]
    b = next(x for x in solidos if x["generico"] != a["generico"])
    datos = {"tipo": "KIT", "sku": "KIT0000001", "codigo": "KT01",
             "componentes": [{"articulo_id": a["id"], "cantidad": 1}, {"articulo_id": b["id"], "cantidad": 2}]}
    # Como pack no se puede: son de productos distintos
    r = interno.post("/catalogos/compuestos", {**datos, "tipo": "PACK"})
    assert r.status_code == 422
    r = interno.post("/catalogos/compuestos", datos)
    assert r.status_code == 200, r.text
    kit = r.json()
    assert kit["total"] == 3 and kit["kit"] and kit["codigo"] == "KT01"
    art = _cat(interno, "articulos", q="KIT0000001")[0]
    assert art["tipo"] == "PREPACK" and art["generico"] == "KIT0000001"
    assert interno.get("/catalogos/explosion/KIT0000001").json()["total"] == 3
    assert interno.get(f"/catalogos/compuestos/{kit['id']}/componentes").json()["total"] == 3
    # El tipo no cambia después
    assert interno.patch(f"/catalogos/articulos/{kit['id']}", {"tipo": "SOLIDO"}).status_code == 422


def test_escala_de_valores_en_json(interno):
    """Los valores de una escala se guardan como lista JSON ya expandida y el
    formulario los sigue leyendo y escribiendo como texto."""
    from app.modelos import EscalaValores

    escalas = {e["codigo"]: e for e in _cat(interno, "escalas")}
    assert escalas["US-CALZ-ENT"]["valores"] == "6, 7, 8, 9, 10, 11, 12, 13"
    r = interno.post("/catalogos/escalas", {"codigo": "PRUEBA", "nombre": "Prueba", "atributo": "TALLA", "regla": "VALOR",
                                            "valores": "S, M=MED, 1-3"})
    assert r.status_code == 200, r.text
    assert r.json()["valores"] == "S, M=MED, 1, 2, 3"
    with SessionLocal() as db:
        e = db.scalar(select(EscalaValores).where(EscalaValores.codigo == "PRUEBA"))
        assert e.lista_valores[1] == {"valor": "M", "codigo": "MED"} and len(e.lista_valores) == 5
    # El atributo de la escala es uno de variante
    assert interno.post("/catalogos/escalas", {"codigo": "PRUEBA2", "nombre": "Prueba", "atributo": "MODELO", "regla": "VALOR",
                                               "valores": "A"}).status_code == 422
    interno.delete_(f"/catalogos/escalas/{r.json()['id']}")
