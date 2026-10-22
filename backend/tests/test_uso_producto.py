"""Ficha del producto: dónde se usa (OCs, facturas, embarques) y cómo se
empaca (reglas candidatas y recetas en uso), con el alcance de cada usuario."""


def _producto(api, estilo, color):
    items = api.get("/productos", params={"q": estilo, "size": 50}).json()["items"]
    return next(p for p in items if p["estilo"] == estilo and p["color"] == color)


def test_uso_del_producto_con_su_alcance(interno, tnf, vans):
    p = _producto(interno, "VN000EE3", "BLK Black")
    u = interno.get(f"/productos/{p['id']}/uso").json()
    assert u["ordenes"]["total"] >= 1 and all(o["lineas"] >= 1 and o["cantidad"] for o in u["ordenes"]["items"])
    assert u["facturas"] is not None and u["embarques"] is not None
    # Cada OC listada contiene de verdad una variante del producto
    oc = u["ordenes"]["items"][0]
    skus = {a["sku"] for a in interno.get(f"/productos/{p['id']}").json()["articulos"]}
    assert skus & {x["codigo_articulo"] for x in interno.get(f"/ordenes/{oc['id']}/posiciones").json()["posiciones"]}
    # El proveedor dueño lo ve; otro proveedor no ve el producto
    assert vans.get(f"/productos/{p['id']}/uso").status_code == 200
    assert tnf.get(f"/productos/{p['id']}/uso").status_code == 404


def test_empaque_del_producto(interno, vans):
    p = _producto(interno, "VN000EE3", "BLK Black")
    e = interno.get(f"/productos/{p['id']}/empaque").json()
    assert set(e) == {"reglas", "en_uso"}
    for r in e["reglas"]:
        assert r["receta"] and r["destino"]
    especificidades = [r["especificidad"] for r in e["reglas"]]
    assert especificidades == sorted(especificidades, reverse=True)
    # Las reglas son configuración interna
    assert vans.get(f"/productos/{p['id']}/empaque").status_code == 403
