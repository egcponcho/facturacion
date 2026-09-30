"""Cargas masivas: artículos con su ficha técnica y cualquier catálogo de
datos maestros desde Excel; exportación con filtros."""
import io

from openpyxl import Workbook, load_workbook


def _xlsx(filas):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    for f in filas:
        ws.append(f)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _subir(api, url, contenido):
    return api.c.post(f"/api{url}", headers=api.h, files={"archivo": ("datos.xlsx", io.BytesIO(contenido), "application/octet-stream")})


def test_articulos_con_ficha(interno):
    pl = interno.get("/catalogos/articulos/plantilla")
    wb = load_workbook(io.BytesIO(pl.content))
    enc = [c.value for c in wb["Generics"][1]]
    assert enc[0] == "Generic code *" and "Category" in enc and "Upper" in enc
    assert "Supplier SKU" in [c.value for c in wb["Sizes"][1]]
    # También se acepta una hoja con una fila por artículo (formato anterior)
    enc = ["Item code", "Supplier SKU", "Style", "Color", "Size", "Brand", "Item group", "Supplier", "Unit",
           "Commercial name", "Category", "Gender", "Who it is for", "Country of origin", "Upper", "Sole", "Footwear style"]
    filas = [enc,
             ["30099980001", "VN0A5KRFBLK-8", "VN0A5KRF", "Black", "8", "VANS", "CALZ-CAS", "VANS", "PAR", "Sk8-Hi canvas sneaker",
              "Footwear: sneakers, boots, shoes, sandals", "Unisex", "Adult", "Vietnam", "100% canvas", "100% rubber", "Sneaker"],
             ["30099980002", "VN0A5KRFBLK-9", "VN0A5KRF", "Black", "9", "VANS", "CALZ-CAS", "VANS", "PAR", "", "", "", "", "", "", "", ""],
             ["99", "", "X", "Y", "1", "VANS", "CALZ-CAS", "VANS", "PAR", "", "", "", "", "", "", "", ""],
             ["30099980003", "", "VN0A5KRF", "Black", "10", "NOPE", "CALZ-CAS", "VANS", "PAR", "", "", "", "", "", "", "", ""]]
    r = _subir(interno, "/catalogos/articulos/importar", _xlsx(filas))
    assert r.status_code == 200, r.text
    r = r.json()
    assert r["creados"] == 2 and len(r["errores"]) == 2 and len(r["productos"]) == 1
    det = interno.get(f"/productos/{r['productos'][0]}").json()
    assert det["tipo"] == "calzado" and det["pais_origen"] == "VN" and det["nombre"] == "Sk8-Hi canvas sneaker"
    assert det["ficha"]["comp"] == {"corte": "100% canvas", "suela": "100% rubber"} and det["ficha"]["estiloCalz"] == "tenis"
    assert det["ficha"]["genero"] == "U" and {a["sku_proveedor"] for a in det["articulos"]} == {"VN0A5KRFBLK-8", "VN0A5KRFBLK-9"}
    # El navegador completa la ficha con el motor y guarda la clasificación
    resultado = {"sugerido": "640419", "confianza": "high", "completa": True, "descripcion_comercial": "Vans Sk8-Hi · Unisex sneaker",
                 "partidas": {"SV": {"codigo": "6404199000", "estado": "ok"}}}
    x = interno.post("/productos/clasificar", {"items": [{"id": det["id"], "tipo": "calzado", "resultado": resultado,
                                                          "ficha": {"altura": "tobillo", "genero": "M", "comp": {"forro": "100% textile"}}}]})
    assert x.status_code == 200, x.text
    det = interno.get(f"/productos/{det['id']}").json()
    # Completa lo que faltaba sin pisar lo cargado
    assert det["estado"] == "sugerida" and det["ficha"]["altura"] == "tobillo" and det["ficha"]["genero"] == "U"
    assert det["ficha"]["comp"]["forro"] == "100% textile" and det["descripcion_comercial"] == "Vans Sk8-Hi · Unisex sneaker"
    # El código de artículo tiene 11 dígitos y empieza con 3
    assert any("11 digits starting with 3" in e["mensaje"] for e in r["errores"])


def test_catalogos_por_excel(interno):
    pl = interno.get("/catalogos/marcas/plantilla")
    assert pl.status_code == 200 and "Instructions" in load_workbook(io.BytesIO(pl.content)).sheetnames
    r = _subir(interno, "/catalogos/marcas/importar", _xlsx([["Code", "Name", "Active"], ["TIMB", "Timberland", "Yes"],
                                                             ["VANS", "Vans Off The Wall", "Yes"], ["", "", ""]]))
    assert r.status_code == 200, r.text
    assert r.json()["creados"] == 1 and r.json()["actualizados"] == 1
    r = _subir(interno, "/catalogos/centros/importar", _xlsx([["Code", "Company", "Name", "Country", "Type"],
                                                              ["0999", "8000", "Test DC", "SV", "Local warehouse"],
                                                              ["0998", "XXXX", "Bad", "SV", "Store"]]))
    assert r.json()["creados"] == 1 and "XXXX" in r.json()["errores"][0]["mensaje"], r.text
    nuevo = interno.get("/catalogos/centros", params={"q": "Test DC"}).json()["items"][0]
    assert interno.delete_(f"/catalogos/centros/{nuevo['id']}").status_code == 200
    for formato in ("xlsx", "pdf"):
        r = interno.get("/catalogos/marcas/exportar", params={"q": "Vans", "formato": formato})
        assert r.status_code == 200 and len(r.content) > 800
    r = interno.get("/catalogos/articulos/exportar", params={"marca_id": 1, "formato": "xlsx"})
    assert r.status_code == 200


def test_tablero_por_periodo(interno, tnf):
    from datetime import date, timedelta

    hoy = date.today()
    d = interno.get("/dashboard").json()["periodo"]
    assert d["desde"] == hoy.replace(day=1).isoformat() and d["facturado"]["grano"] in ("dia", "semana")
    assert {x["clave"] for x in d["resumen"]} == {"facturado", "pls", "llegadas", "clasificados"}
    anio = interno.get("/dashboard", params={"desde": (hoy - timedelta(days=364)).isoformat(), "hasta": hoy.isoformat()}).json()
    assert anio["periodo"]["facturado"]["grano"] == "mes" and len(anio["periodo"]["facturado"]["serie"]) >= 12
    total = sum(x["importe"] for x in anio["periodo"]["facturado"]["serie"])
    assert total > 0
    # Filtrar por marca reduce el total
    solo = interno.get("/dashboard", params={"desde": (hoy - timedelta(days=364)).isoformat(), "marcas": "VANS"}).json()
    assert sum(x["importe"] for x in solo["periodo"]["facturado"]["serie"]) < total
    semana = tnf.get("/dashboard", params={"desde": (hoy - timedelta(days=6)).isoformat()}).json()["periodo"]
    assert semana["facturado"]["grano"] == "dia" and len(semana["facturado"]["serie"]) == 7
    # Seguimiento con varios valores en un filtro
    r = interno.get("/seguimiento/ordenes", params={"proveedor": "The North Face,Vans"}).json()
    assert r["total"] >= interno.get("/seguimiento/ordenes", params={"proveedor": "Vans"}).json()["total"]


def test_genericos(interno):
    """El código de artículo: 8 dígitos de genérico (estilo-color) + 3 de talla.
    La clasificación es del genérico; sus tallas y prepacks la comparten."""
    m = {x["codigo"]: x["id"] for x in interno.get("/catalogos/marcas", params={"size": 100}).json()["items"]}
    g = {x["codigo"]: x["id"] for x in interno.get("/catalogos/grupos").json()["items"]}
    pv = {x["codigo"]: x["id"] for x in interno.get("/catalogos/proveedores").json()["items"]}
    base = {"estilo": "vn0a3wm3", "color": "Navy", "marca_id": m["VANS"], "grupo_id": g["CALZ-CAS"], "proveedor_id": pv["VANS"],
            "unidad": "PAR"}
    assert interno.post("/catalogos/genericos", {**base, "generico": "2009997"}).status_code == 422
    r = interno.post("/catalogos/genericos", {**base, "generico": "30099970", "nombre": "Era",
                                              "tallas": [{"talla": "8", "upc": "0196999000001", "sku_proveedor": "VN0A3WM3NVY-8"},
                                                         {"talla": "9"}, {"talla": "10", "sufijo": "010"}]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [t["sku"] for t in d["tallas"]] == ["30099970001", "30099970002", "30099970010"] and d["siguiente"] == "011"
    assert d["estilo"] == "VN0A3WM3"
    # Agregar tallas: heredan los datos del genérico; una talla repetida no entra
    r = interno.post("/catalogos/genericos/30099970/tallas", {"tallas": [{"talla": "11"}]})
    assert r.status_code == 200 and r.json()["tallas"][-1]["sku"] == "30099970011"
    assert interno.post("/catalogos/genericos/30099970/tallas", {"tallas": [{"talla": "8"}]}).status_code == 422
    # Un artículo suelto con ese genérico debe ser del mismo estilo-color
    r = interno.post("/catalogos/articulos", {**base, "sku": "30099970020", "talla": "12", "color": "Red", "tipo": "SOLIDO"})
    assert r.status_code == 422 and "Generic 30099970" in r.json()["detalle"][0]["mensaje"]
    # Todas las tallas son un solo producto (la clasificación es del genérico)
    prod = interno.get("/productos", params={"q": "30099970"}).json()["items"]
    assert len(prod) == 1 and prod[0]["codigo_generico"] == "30099970" and prod[0]["skus"] == 4
    # Un prepack debe llevar el genérico de sus sólidos
    sol = interno.get("/catalogos/articulos", params={"q": "30099970001"}).json()["items"][0]
    r = interno.post("/catalogos/prepacks", {"sku": "30099971001", "codigo": "EE04", "estilo": "VN0A3WM3", "color": "Navy",
                                             "componentes": [{"articulo_id": sol["id"], "cantidad": 4}]})
    assert r.status_code == 422 and "generic of its solids" in r.text
    r = interno.post("/catalogos/prepacks", {"sku": "30099970900", "codigo": "EE04", "estilo": "VN0A3WM3", "color": "Navy",
                                             "componentes": [{"articulo_id": sol["id"], "cantidad": 4}]})
    assert r.status_code == 200, r.text
    assert interno.get("/productos", params={"q": "30099970"}).json()["items"][0]["prepacks"] == 1


def test_carga_por_generico(interno):
    pl = load_workbook(io.BytesIO(interno.get("/catalogos/articulos/plantilla").content))
    assert pl.sheetnames[:2] == ["Generics", "Sizes"] and pl["Generics"]["A1"].value == "Generic code *"
    wb = Workbook()
    ws = wb.active
    ws.title = "Generics"
    ws.append(["Generic code", "Style", "Color", "Brand", "Item group", "Supplier", "Unit", "Commercial name",
               "Country of origin", "Upper", "Sole"])
    ws.append(["30099960", "VN0A4U39", "True White", "VANS", "CALZ-CAS", "VANS", "PAR", "Old Skool Pro", "China",
               "100% suede", "100% rubber"])
    ws.append(["3009996", "X", "Y", "VANS", "CALZ-CAS", "VANS", "PAR", "", "", "", ""])
    t = wb.create_sheet("Sizes")
    t.append(["Generic code", "Size", "Size code", "UPC", "Supplier SKU"])
    t.append(["30099960", "7", "", "0196888000007", "VN0A4U39W-7"])
    t.append(["30099960", "8", "", "0196888000008", "VN0A4U39W-8"])
    t.append(["30099961", "9", "", "", ""])
    b = io.BytesIO()
    wb.save(b)
    r = _subir(interno, "/catalogos/articulos/importar", b.getvalue()).json()
    assert r["genericos_creados"] == 1 and r["creados"] == 2 and len(r["errores"]) == 2, r
    det = interno.get(f"/productos/{r['productos'][0]}").json()
    assert det["codigo_generico"] == "30099960" and det["ficha"]["comp"]["corte"] == "100% suede"
    assert sorted(a["sku"] for a in det["articulos"]) == ["30099960001", "30099960002"]
    # La misma carga otra vez actualiza (no duplica)
    b.seek(0)
    r = _subir(interno, "/catalogos/articulos/importar", b.getvalue()).json()
    assert r["genericos_actualizados"] == 1 and r["actualizados"] == 2 and r["creados"] == 0
