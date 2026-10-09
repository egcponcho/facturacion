"""Perfil del usuario: datos básicos y preferencias (idioma inglés y fecha
MM/DD/YYYY por defecto) que se aplican también a lo que genera el servidor
y a la lectura de fechas de los archivos que se suben."""
import io
from datetime import date

from openpyxl import load_workbook

from app.modulos.acceso import preferencias


def test_perfil_y_preferencias(interno):
    p = interno.get("/perfil").json()
    # Sin elección propia, el idioma es el predeterminado de la empresa (la demo: español)
    assert p["preferencias"]["idioma"] == "es" and p["preferencias"]["formato_fecha"] == "MM/DD/YYYY"
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


def test_busqueda_inteligente(interno):
    """Términos en cualquier orden, partes de palabras, sin acentos ni mayúsculas."""
    for q in ("cat ho", "LAI chi", "hó chí  cat"):
        r = interno.get("/catalogos/puertos", params={"q": q}).json()["items"]
        assert "VNSGN" in {p["codigo"] for p in r}, q
    r = interno.get("/catalogos/paises", params={"q": "víetnam"}).json()["items"]
    assert [p["codigo"] for p in r] == ["VN"]
    # Las opciones traen el nombre de lo referido para buscar por él (país del puerto)
    ops = {o["codigo"]: o for o in interno.get("/catalogos/puertos/opciones").json()}
    assert ops["VNSGN"]["sub"] == "Vietnam"


def test_campos_dependientes(interno):
    """Las opciones dependientes traen el dato con el que se filtran y el
    servidor rechaza una combinación que no corresponde."""
    marcas = interno.get("/catalogos/marcas/opciones").json()
    provs = {p["codigo"]: p["id"] for p in interno.get("/catalogos/proveedores/opciones").json()}
    vans = next(m for m in marcas if m["codigo"] == "VANS")
    assert vans["proveedores"] == [provs["VANS"]]
    centros = interno.get("/catalogos/centros/opciones").json()
    assert all("sociedad_id" in c and "pais" in c for c in centros)
    # Una marca que el proveedor no tiene autorizada no se acepta
    grupo = interno.get("/catalogos/grupos/opciones").json()[0]["id"]
    r = interno.post("/catalogos/articulos", {"sku": "DEP-TEST-1", "estilo": "DEPTEST", "marca_id": vans["id"], "grupo_id": grupo,
                                              "proveedor_id": provs["TNF"], "tipo": "SOLIDO", "unidad": "UN"})
    assert r.status_code == 422 and any(e["campo"] == "marca_id" for e in r.json()["detalle"])
    r = interno.post("/catalogos/genericos", {"generico": "DEPTEST-X", "estilo": "DEPTEST", "color": "X", "marca_id": vans["id"],
                                              "grupo_id": grupo, "proveedor_id": provs["TNF"], "unidad": "UN", "tallas": []})
    assert r.status_code == 422


def test_normalizacion_en_cargas(interno):
    """Valores escritos de otra forma se enlazan con lo que ya existe y los
    nombres en MAYÚSCULAS o minúsculas se ordenan; los códigos no cambian."""
    oc = interno.get("/ordenes", params={"q": "4400003901", "solo_disponible": False}).json()["items"][0]
    sku = interno.get(f"/ordenes/{oc['id']}/posiciones").json()["posiciones"][0]["codigo_sap"]
    csv = ("supplier,po,po_line,company,destination,sku,quantity\n"
           f"  vans ,PO-NORM-1,10, 8000 ,el salvador distribution center,{sku},6\n")
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h, files={"archivo": ("n.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["resumen"]["nuevo"] == 1, r.text
    # Catálogo: la marca escrita en minúsculas actualiza la existente, no crea otra
    antes = len(interno.get("/catalogos/marcas/opciones").json())
    contenido = "code,name\nvans,Vans\n"
    r = interno.c.post("/api/catalogos/marcas/importar", headers=interno.h,
                       files={"archivo": ("m.csv", contenido.encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["creados"] == 0 and r.json()["actualizados"] == 1, r.text
    assert len(interno.get("/catalogos/marcas/opciones").json()) == antes
    # Nombres de personas: de MAYÚSCULAS a nombre propio; el país por su nombre
    socs = {s["codigo"]: s["id"] for s in interno.get("/catalogos/sociedades/opciones").json()}
    r = interno.post("/catalogos/contactos", {"nombre": "  MARÍA   DE LOS ÁNGELES  ", "rol": "NOTIFY", "sociedad_id": socs["8000"]})
    assert r.status_code == 200, r.text
    c = next(x for x in interno.get("/catalogos/contactos", params={"q": "Ángeles"}).json()["items"])
    assert c["nombre"] == "María de los Ángeles"
    r = interno.post("/catalogos/puertos", {"codigo": "svx01", "nombre": "PUERTO DE PRUEBA", "pais": "el salvador", "tipo": "MARITIMO"})
    assert r.status_code == 200, r.text
    p = interno.get("/catalogos/puertos", params={"q": "SVX01"}).json()["items"][0]
    assert p["codigo"] == "SVX01" and p["pais"] == "SV" and p["nombre"] == "Puerto de Prueba"


def test_escalas_de_tallas(interno):
    """Escalas de tallas reutilizables: tallas en orden y códigos por regla o escritos."""
    escalas = {e["codigo"]: e for e in interno.get("/catalogos/escalas/opciones").json()}
    calz = interno.get(f"/catalogos/escalas/{escalas['US-CALZ']['id']}/tallas").json()["tallas"]
    assert calz[:3] == [{"talla": "5", "codigo": "050"}, {"talla": "5.5", "codigo": "055"}, {"talla": "6", "codigo": "060"}]
    letras = interno.get(f"/catalogos/escalas/{escalas['LETRAS']['id']}/tallas").json()["tallas"]
    assert [x["codigo"] for x in letras[:3]] == ["001", "002", "003"] and letras[2]["talla"] == "S"
    r = interno.post("/catalogos/escalas", {"codigo": "test", "nombre": "Test", "regla": "TALLA", "tallas": "S=1, M=1"})
    assert r.status_code == 422 and "same code" in str(r.json()["detalle"])
    r = interno.post("/catalogos/escalas", {"codigo": "kids", "nombre": "Kids", "regla": "CONSECUTIVO", "longitud": 2, "tallas": "2T, 3T, 4T"})
    assert r.status_code == 200, r.text
    # Un genérico parte de la escala: los códigos de talla salen de ella
    provs = {p["codigo"]: p["id"] for p in interno.get("/catalogos/proveedores/opciones").json()}
    marca = next(m for m in interno.get("/catalogos/marcas/opciones").json() if m["codigo"] == "TNF")["id"]
    grupo = interno.get("/catalogos/grupos/opciones").json()[0]["id"]
    r = interno.post("/catalogos/genericos", {"generico": "ESC-TEST", "estilo": "ESCTEST", "color": "Black", "marca_id": marca,
                                              "grupo_id": grupo, "proveedor_id": provs["TNF"], "unidad": "UN",
                                              "escala_id": escalas["LETRAS"]["id"], "tallas": [{"talla": "M"}, {"talla": "L"}]})
    assert r.status_code == 200, r.text
    skus = sorted(t["sku"] for t in interno.get("/catalogos/genericos/ESC-TEST").json()["tallas"])
    assert skus == ["ESC-TEST004", "ESC-TEST005"]
