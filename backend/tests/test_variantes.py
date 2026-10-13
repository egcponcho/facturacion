"""Atributos de variante configurables y kits (auditoría, prioridad media)."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import ArticuloAtributo


def _cat(api, catalogo, **params):
    return api.get(f"/catalogos/{catalogo}", params={"size": 200, **params}).json()["items"]


def test_atributos_de_sistema_y_propios(interno):
    atributos = {a["codigo"]: a for a in _cat(interno, "atributos_variante")}
    assert {"TALLA", "COLOR"} <= set(atributos)
    talla = atributos["TALLA"]
    # Los de sistema se renombran pero no se borran ni cambian de código
    assert interno.patch(f"/catalogos/atributos_variante/{talla['id']}", {"nombre": "Size / capacity"}).status_code == 200
    assert interno.patch(f"/catalogos/atributos_variante/{talla['id']}", {"codigo": "TAMANO"}).status_code == 422
    assert interno.delete_(f"/catalogos/atributos_variante/{talla['id']}").status_code == 409
    interno.patch(f"/catalogos/atributos_variante/{talla['id']}", {"nombre": "Size"})

    r = interno.post("/catalogos/atributos_variante", {"codigo": "MATERIAL", "nombre": "Material", "orden": 3})
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
            assert [(f.atributo.codigo, f.valor) for f in filas] == [("MATERIAL", "Canvas")]
        # Se filtra por su valor como cualquier columna
        import json
        items = interno.get("/catalogos/articulos", params={"f": json.dumps({"atr.MATERIAL": ["Canvas"]})}).json()["items"]
        assert [x["id"] for x in items] == [art["id"]]
        # Un atributo en uso no cambia de código ni se borra
        assert interno.patch(f"/catalogos/atributos_variante/{material['id']}", {"codigo": "TELA"}).status_code == 422
        assert interno.delete_(f"/catalogos/atributos_variante/{material['id']}").status_code == 409
        assert interno.patch(f"/catalogos/articulos/{art['id']}", {"atr.NOEXISTE": "x"}).status_code == 422
        # Vaciar el valor quita la fila
        assert interno.patch(f"/catalogos/articulos/{art['id']}", {"atr.MATERIAL": ""}).json()["atr.MATERIAL"] is None
    finally:
        interno.delete_(f"/catalogos/atributos_variante/{material['id']}")


def test_kit_con_articulos_de_varios_estilos(interno):
    solidos = _cat(interno, "articulos", tipo="SOLIDO")
    a = solidos[0]
    b = next(x for x in solidos if x["estilo"] != a["estilo"])
    datos = {"tipo": "KIT", "sku": "KIT0000001", "codigo": "KT01", "estilo": "GIFTSET",
             "componentes": [{"articulo_id": a["id"], "cantidad": 1}, {"articulo_id": b["id"], "cantidad": 2}]}
    # Como curva no se puede: los estilos no coinciden
    r = interno.post("/catalogos/prepacks", {**datos, "tipo": "CURVA", "color": "X"})
    assert r.status_code == 422
    r = interno.post("/catalogos/prepacks", datos)
    assert r.status_code == 200, r.text
    kit = r.json()
    assert kit["total"] == 3
    fila = next(p for p in _cat(interno, "prepacks") if p["id"] == kit["id"])
    assert fila["tipo"] == "KIT"
    art = _cat(interno, "articulos", q="KIT0000001")[0]
    assert art["tipo"] == "PREPACK" and art["estilo"] == "GIFTSET"
    assert interno.get("/catalogos/explosion/KIT0000001").json()["total"] == 3
    # El tipo no cambia después
    assert interno.patch(f"/catalogos/prepacks/{kit['id']}", {"tipo": "CURVA"}).status_code == 422


def test_escala_de_tallas_en_json(interno):
    """Las tallas de una escala se guardan como lista JSON ya expandida y el
    formulario las sigue leyendo y escribiendo como texto."""
    from app.modelos import EscalaTalla

    escalas = {e["codigo"]: e for e in _cat(interno, "escalas")}
    assert escalas["US-CALZ-ENT"]["tallas"] == "6, 7, 8, 9, 10, 11, 12, 13"
    r = interno.post("/catalogos/escalas", {"codigo": "PRUEBA", "nombre": "Prueba", "regla": "TALLA", "tallas": "S, M=MED, 1-3"})
    assert r.status_code == 200, r.text
    assert r.json()["tallas"] == "S, M=MED, 1, 2, 3"
    with SessionLocal() as db:
        e = db.scalar(select(EscalaTalla).where(EscalaTalla.codigo == "PRUEBA"))
        assert e.lista_tallas[1] == {"talla": "M", "codigo": "MED"} and len(e.lista_tallas) == 5
    interno.delete_(f"/catalogos/escalas/{r.json()['id']}")
