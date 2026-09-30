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
    enc = [c.value for c in load_workbook(io.BytesIO(pl.content))["Data"][1]]
    assert enc[0] == "Item code *" and "Supplier SKU" in enc and "Category" in enc and "Upper" in enc
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
