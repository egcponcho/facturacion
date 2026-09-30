"""Aranceles: países con sus dígitos, subpartidas SAC y códigos nacionales
editables, cargas desde Excel y exportación con filtros."""
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


def _subir(api, url, contenido, **params):
    return api.c.post(f"/api{url}", headers=api.h, params=params,
                      files={"archivo": ("datos.xlsx", io.BytesIO(contenido), "application/octet-stream")})


def test_paises_sac_y_codigos(interno, vans):
    ps = interno.get("/aranceles/paises").json()
    assert {p["iso"] for p in ps} >= {"GT", "SV", "HN", "NI", "CR", "PA"}
    assert next(p for p in ps if p["iso"] == "PA")["digitos"] == 12 and all(p["codigos"] > 0 for p in ps)
    # Un país nuevo con sus propios dígitos; el proveedor no puede
    assert vans.post("/aranceles/paises", {"iso": "DO", "nombre": "Dominican Republic", "digitos": 8}).status_code == 403
    r = interno.post("/aranceles/paises", {"iso": "DO", "nombre": "Dominican Republic", "digitos": 8, "impuesto": "ITBIS 18%"})
    assert r.status_code == 200, r.text
    ctx = interno.get("/clasificacion/contexto").json()
    assert any(d["iso"] == "DO" and d["digitos"] == 8 for d in ctx["destinos"])

    # SAC: filtros por capítulo y búsqueda; editar el texto de una subpartida
    sac = interno.get("/aranceles/sac", params={"capitulo": "64", "nivel": "6"}).json()
    assert sac["total"] > 5 and all(x["codigo"].startswith("64") for x in sac["items"])
    x = next(x for x in sac["items"] if x["codigo"] == "640419")
    assert x["nacionales"] >= 6
    assert interno.put(f"/aranceles/sac/{x['id']}", {"codigo": "640419", "descripcion": "Los demás (texto corregido)"}).status_code == 200
    assert any(y["codigo"] == "640419" for y in interno.get("/clasificacion/contexto").json()["sac"])

    # Códigos nacionales: agregar con condiciones y validar los dígitos del país
    assert interno.post("/aranceles/codigos", {"pais": "DO", "codigo": "6404199"}).status_code == 422
    r = interno.post("/aranceles/codigos", {"pais": "DO", "codigo": "6404.19.00", "dai": "20%",
                                            "cond": {"genero": "M", "edadNac": "adulto"}})
    assert r.status_code == 200, r.text
    lista = interno.get("/aranceles/codigos", params={"pais": "DO"}).json()
    assert lista["total"] == 1 and lista["items"][0]["cond_txt"].startswith("Gender: Men")
    # Varios países a la vez (filtro con varios valores)
    assert interno.get("/aranceles/codigos", params={"pais": "SV,PA", "capitulo": "64"}).json()["total"] > 0
    # Un país con códigos no se borra: se desactiva y deja de pedirse en las fichas
    do = next(p for p in interno.get("/aranceles/paises").json() if p["iso"] == "DO")
    assert interno.delete_(f"/aranceles/paises/{do['id']}").status_code == 409
    assert interno.put(f"/aranceles/paises/{do['id']}", {**{k: do[k] for k in ("iso", "nombre", "digitos", "mcca")},
                                                         "activo": False}).status_code == 200
    assert not any(d["iso"] == "DO" for d in interno.get("/clasificacion/contexto").json()["destinos"])


def test_cargar_y_exportar(interno):
    plantilla = interno.get("/aranceles/codigos/plantilla", params={"pais": "SV"})
    assert plantilla.status_code == 200
    wb = load_workbook(io.BytesIO(plantilla.content))
    enc = [c.value for c in wb["Data"][1]]
    assert enc[:2] == ["Country *", "Code *"] and "Gender" in enc and "Instructions" in wb.sheetnames
    contenido = _xlsx([["Country", "Code", "Description", "Duty (DAI %)", "Gender", "Footwear style"],
                       ["SV", "6402.99.10.00", "Para hombre", "15", "Men", "Sneaker"],
                       ["SV", "6402991", "Mal", "", "", ""],
                       ["XX", "6402.99.10.00", "", "", "", ""]])
    r = _subir(interno, "/aranceles/codigos/importar", contenido)
    assert r.status_code == 200, r.text
    r = r.json()
    assert r["creados"] == 1 and len(r["errores"]) == 2
    x = interno.get("/aranceles/codigos", params={"pais": "SV", "q": "6402991000", "fuente": "archivo"}).json()["items"][0]
    assert x["cond"] == {"genero": "M", "estiloCalz": "tenis"} and x["fuente"] == "archivo"
    # La misma fila actualiza (no duplica)
    assert _subir(interno, "/aranceles/codigos/importar", contenido).json()["actualizados"] == 1
    for formato in ("xlsx", "pdf"):
        r = interno.get("/aranceles/codigos/exportar", params={"pais": "SV", "formato": formato})
        assert r.status_code == 200 and len(r.content) > 1000
    r = _subir(interno, "/aranceles/sac/importar", _xlsx([["Code", "Description"], ["9999.99", "Prueba"]]))
    assert r.json()["creados"] == 1
    assert interno.get("/aranceles/sac/exportar", params={"q": "Prueba", "formato": "pdf"}).status_code == 200
    # Borrar códigos seleccionados
    assert interno.post("/aranceles/codigos/borrar", {"ids": [x["id"]]}).json()["borrados"] == 1
