"""Perfil del usuario: datos básicos y preferencias (idioma inglés y fecha
MM/DD/YYYY por defecto) que se aplican también a lo que genera el servidor
y a la lectura de fechas de los archivos que se suben."""
import io
from datetime import date

from openpyxl import load_workbook

from app.services import preferencias


def test_perfil_y_preferencias(interno):
    p = interno.get("/perfil").json()
    assert p["preferencias"]["idioma"] == "en" and p["preferencias"]["formato_fecha"] == "MM/DD/YYYY"
    assert "DD/MM/YYYY" in p["opciones"]["formatos_fecha"]
    assert interno.get("/auth/me").json()["preferencias"]["formato_hora"] == "12"
    # Opciones inválidas no se guardan
    r = interno.patch("/perfil", {"formato_fecha": "YY.MM.DD"})
    assert r.status_code == 422
    r = interno.patch("/perfil", {"nombre": "  Import   team ", "formato_fecha": "DD/MM/YYYY", "idioma": "es", "filas": 50})
    assert r.status_code == 200, r.text
    assert r.json()["nombre"] == "Import team" and r.json()["preferencias"]["filas"] == 50
    # El formato del usuario rige la lectura de fechas de la carga de OC: 05/10 es el 5 de octubre
    oc = interno.get("/ordenes", params={"q": "4400003901", "solo_disponible": False}).json()["items"][0]
    sku = interno.get(f"/ordenes/{oc['id']}/posiciones").json()["posiciones"][0]["codigo_sap"]
    csv = ("supplier,po,po_line,company,sku,quantity,xf_date,in_store_date\n"
           f"VANS,PO-FECHA-1,10,8000,{sku},12,05/10/2026,20/12/2026\n")
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h, files={"archivo": ("f.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["resumen"]["nuevo"] == 1, r.text
    interno.post(f"/ordenes/importar/{r.json()['importacion_id']}/aplicar")
    nueva = interno.get("/ordenes", params={"q": "PO-FECHA-1", "solo_disponible": False}).json()["items"][0]
    assert nueva["fecha_xf"] == "2026-10-05" and nueva["fecha_tienda"] == "2026-12-20"
    # La plantilla de OC trae las fechas de ejemplo en ese formato
    r = interno.c.get("/api/ordenes/plantilla", headers=interno.h)
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content))["Data"]
    cab = [c.value for c in ws[1]]
    xf = ws.cell(row=2, column=cab.index("xf_date") + 1).value
    assert xf.count("/") == 2 and int(xf.split("/")[1]) <= 12
    # De vuelta a los valores por defecto
    r = interno.patch("/perfil", {"formato_fecha": None, "idioma": None, "filas": None})
    assert r.json()["preferencias"]["formato_fecha"] == "MM/DD/YYYY"


def test_formatos_de_fecha():
    preferencias._actual.set({**preferencias.DEFECTO})
    d = date(2026, 3, 7)
    assert preferencias.fecha_txt(d) == "03/07/2026"
    assert preferencias.leer_fecha("03/07/2026") == d and preferencias.leer_fecha("2026-03-07") == d
    preferencias._actual.set({**preferencias.DEFECTO, "formato_fecha": "DD/MM/YYYY"})
    assert preferencias.fecha_txt(d) == "07/03/2026" and preferencias.leer_fecha("07/03/2026") == d
    preferencias._actual.set({**preferencias.DEFECTO, "formato_fecha": "DD-MMM-YYYY"})
    assert preferencias.fecha_txt(d) == "07-Mar-2026" and preferencias.leer_fecha("07-Mar-2026") == d
    preferencias._actual.set({**preferencias.DEFECTO})


def test_busqueda_de_varios_codigos(interno):
    """Varios códigos pegados (con espacios, comas o saltos de línea) traen
    todos; varias palabras deben estar todas."""
    r = interno.get("/ordenes", params={"q": "4400003904 4400003850", "solo_disponible": False}).json()["items"]
    assert {o["numero"] for o in r} == {"4400003904", "4400003850"}
    r = interno.get("/ordenes", params={"q": "4400003904,\n4400003850;4400003851", "solo_disponible": False}).json()["items"]
    assert {o["numero"] for o in r} == {"4400003904", "4400003850", "4400003851"}
