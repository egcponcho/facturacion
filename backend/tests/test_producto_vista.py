"""Lo que la página del producto y el catálogo muestran sale de los datos, ya
ordenado y sin textos armados: los datos que pide la familia (con su valor o
vacío) y las variantes por atributo (sus valores en orden, sin repetir)."""
from app.modulos.maestros.variantes import ordenados, rango


def test_valores_sin_repetir_con_el_texto_como_se_escribio():
    assert ordenados(["BLK Black", "blk black", "White"]) == ["BLK Black", "White"]
    assert rango(["BLK Black", "BLK BLACK"]) == "BLK Black"
    assert ordenados(["10", "7", "9.5", "8"]) == ["7", "8", "9.5", "10"]
    # Sin números, en el orden de sus opciones o escalas; lo que no está ahí, al final y como aparece
    assert ordenados(["XL", "S", "Otro", "M"], ["S", "M", "L", "XL"]) == ["S", "M", "XL", "Otro"]


def test_producto_trae_sus_datos_y_variantes_por_atributo(interno):
    prods = interno.get("/productos", params={"estado": "", "size": 50}).json()["items"]
    p = next(x for x in prods if x["atributos"].get("MODELO") == "VN000EE3")
    ejes = [{"codigo": "COLOR", "nombre": "Color", "valores": ["BLK Black"], "texto": "BLK Black"},
            {"codigo": "TALLA", "nombre": "Size", "valores": ["7", "8", "9", "10", "11", "12"], "texto": "7–12"}]
    assert p["variantes_atributos"] == ejes
    det = interno.get(f"/productos/{p['id']}").json()
    assert det["ejes"] == ejes
    datos = {a["codigo"]: a for a in det["atributos_familia"]}
    assert datos["MARCA"]["valor"] == "Vans" and datos["MARCA"]["general"]
    assert datos["GENERO"]["valor"] and not datos["GENERO"]["general"] and not datos["GENERO"]["fuera"]
    # Cada componente de un pack trae sus valores por atributo (no solo el texto)
    comp = det["compuestos"][0]["componentes"][0]
    assert set(comp["valores"]) == {"COLOR", "TALLA"}
    # La mochila (accesorios) no lleva talla: sus variantes solo se distinguen por color
    b = next(x for x in prods if x["codigo_generico"] == "30095123")
    assert [e["codigo"] for e in interno.get(f"/productos/{b['id']}").json()["ejes"]] == ["COLOR"]


def test_familia_nueva_muestra_datos_vacios_y_ejes_sin_valores(admin, interno):
    fam = admin.post("/grupos-producto", {"clase": "FAMILIA", "codigo": "VISTA-F", "nombre": "Family view"}).json()
    dato = interno.post("/catalogos/atributos", {"nivel": "PRODUCTO", "codigo": "PUREZAV", "nombre": "Purity V",
                                                 "familias": [fam["id"]]}).json()
    eje = interno.post("/catalogos/atributos", {"nivel": "VARIANTE", "codigo": "ENVASEV", "nombre": "Container V",
                                                "familias": [fam["id"]]}).json()
    try:
        r = interno.post("/catalogos/genericos", {"generico": "VISTA-1", "nombre": "Solvent", "unidad": "UN",
                                                  "grupo_producto_id": fam["id"]})
        assert r.status_code == 200, r.text
        pid = next(x["id"] for x in interno.get("/productos", params={"estado": "", "q": "VISTA-1"}).json()["items"])
        det = interno.get(f"/productos/{pid}").json()
        pureza = next(a for a in det["atributos_familia"] if a["codigo"] == "PUREZAV")
        assert not pureza["valor"] and not pureza["fuera"] and not pureza["general"]
        # El eje de la familia aparece aunque todavía no haya variantes con ese valor
        assert {"codigo": "ENVASEV", "nombre": "Container V", "valores": [], "texto": ""} in det["ejes"]
    finally:
        from test_atributos_por_familia import _borrar

        _borrar("VISTA-1")
        interno.delete_(f"/catalogos/atributos/{dato['id']}")
        interno.delete_(f"/catalogos/atributos/{eje['id']}")
        admin.delete_(f"/grupos-producto/{fam['id']}")
