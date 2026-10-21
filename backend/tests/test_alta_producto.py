"""Alta de un producto de cualquier tipo y sus variantes: valores de cualquier
atributo, escritos o combinados, con el código del artículo armado solo."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import Articulo, Producto


def _cat(api, catalogo, **params):
    return api.get(f"/catalogos/{catalogo}", params={"size": 200, **params}).json()["items"]


def _borrar(gen):
    with SessionLocal() as db:
        for a in db.scalars(select(Articulo).where(Articulo.generico == gen)):
            db.delete(a)
        db.flush()
        p = db.scalar(select(Producto).where(Producto.codigo_generico == gen))
        if p is not None:
            db.delete(p)
        db.commit()


def test_quimico_con_concentraciones_y_envases(interno):
    base = _cat(interno, "articulos", tipo="SOLIDO")[0]
    conc = interno.post("/catalogos/atributos_variante", {"codigo": "CONCQ", "nombre": "Concentration", "orden": 50}).json()
    env = interno.post("/catalogos/atributos_variante", {"codigo": "ENVQ", "nombre": "Container", "tipo": "opcion",
                                                         "opciones": "1 L, 5 L", "orden": 51}).json()
    try:
        r = interno.post("/catalogos/genericos", {
            "generico": "CLORO", "nombre": "Sodium hypochlorite", "marca_id": base["marca_id"], "grupo_id": base["grupo_id"],
            "proveedor_id": base["proveedor_id"], "unidad": "UN",
            "combinar": {"CONCQ": ["5 %", "10 %"], "ENVQ": ["1 L", "5 L"]}})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["estilo"] is None and len(d["tallas"]) == 4
        assert {(x["valores"]["CONCQ"], x["valores"]["ENVQ"]) for x in d["tallas"]} == {
            ("5 %", "1 L"), ("5 %", "5 L"), ("10 %", "1 L"), ("10 %", "5 L")}
        assert all(x["sku"].startswith("CLORO") and x["talla"] is None for x in d["tallas"])
        # Una combinación que ya existe no se repite; un valor fuera de las opciones no entra
        r = interno.post("/catalogos/genericos/CLORO/tallas", {"tallas": [{"valores": {"CONCQ": "5 %", "ENVQ": "1 L"}}]})
        assert r.status_code == 422 and "already exists" in r.text
        r = interno.post("/catalogos/genericos/CLORO/tallas", {"tallas": [{"valores": {"CONCQ": "12 %", "ENVQ": "20 L"}}]})
        assert r.status_code == 422
        r = interno.post("/catalogos/genericos/CLORO/tallas", {"tallas": [{"valores": {"CONCQ": "12 %", "ENVQ": "5 L"},
                                                                           "sku": "CLORO-12-5"}]})
        assert r.status_code == 200, r.text
        assert any(x["sku"] == "CLORO-12-5" for x in r.json()["tallas"])
        # Demasiadas combinaciones de una vez: se avisa
        r = interno.post("/catalogos/genericos/CLORO/tallas", {"combinar": {"CONCQ": [str(i) for i in range(30)],
                                                                            "ENVQ": ["1 L"] * 1 + [str(i) for i in range(30)]}})
        assert r.status_code == 422
    finally:
        _borrar("CLORO")
        interno.delete_(f"/catalogos/atributos_variante/{conc['id']}")
        interno.delete_(f"/catalogos/atributos_variante/{env['id']}")


def test_calzado_sigue_igual_con_tallas(interno):
    """El calzado usa estilo, color fijo y tallas: el código de cada talla sale de la regla usual."""
    base = _cat(interno, "articulos", tipo="SOLIDO")[0]
    try:
        r = interno.post("/catalogos/genericos", {
            "generico": "ZAP0001", "estilo": "RUNNER", "color": "BLACK", "marca_id": base["marca_id"], "grupo_id": base["grupo_id"],
            "proveedor_id": base["proveedor_id"], "unidad": "PAR", "tallas": [{"talla": "7"}, {"talla": "7.5"}]})
        assert r.status_code == 200, r.text
        tallas = {x["talla"]: x for x in r.json()["tallas"]}
        assert tallas["7"]["sku"] == "ZAP0001070" and tallas["7.5"]["sku"] == "ZAP0001075"
        assert tallas["7"]["valores"]["COLOR"] == "BLACK" and tallas["7"]["valores"]["TALLA"] == "7"
    finally:
        _borrar("ZAP0001")


def test_documentos_con_variante_y_columnas_de_linea(admin):
    """La factura y la lista de empaque llevan la variante de cada línea y los datos
    que la empresa elige (cualquier atributo de variante por separado)."""
    from app.core.empresa import usar_configuracion
    from app.modelos import Factura, Organizacion
    from app.modulos.documentos import documentos

    assert admin.put("/organizacion", {"documentos": {"columnas_linea": "variante,nada"}}).status_code == 422
    r = admin.put("/organizacion", {"documentos": {"columnas_linea": "variante,atributo.TALLA,upc"}})
    assert r.status_code == 200, r.text
    try:
        with SessionLocal() as db:
            o = db.get(Organizacion, 1)
            usar_configuracion(o.configuracion or {})
            f = db.scalars(select(Factura).where(Factura.lineas.any())).first()
            d = documentos.datos_factura(db, f)
            assert [k for k, _ in d["columnas_linea"]] == ["variante", "atributo.TALLA", "upc"]
            linea = next(x for x, fl in zip(d["lineas"], f.lineas, strict=True) if fl.talla)
            assert linea["datos"]["atributo.TALLA"] and linea["datos"]["variante"]
            assert documentos.pdf_factura(d)[:4] == b"%PDF"
    finally:
        admin.put("/organizacion", {"documentos": {"columnas_linea": "estilo,variante"}})
