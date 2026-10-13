"""Campos propios (Configuración → Empresa → Campos propios): datos que la
empresa agrega a artículos y demás datos maestros, OCs y facturas."""
import io

import pytest
from openpyxl import load_workbook


def _textos(contenido: bytes) -> str:
    wb = load_workbook(io.BytesIO(contenido))
    return " ".join(str(c.value) for ws in wb for fila in ws.iter_rows() for c in fila if c.value)


@pytest.fixture
def campos(admin):
    r = admin.put("/organizacion", {"campos_propios": {
        "articulos": [{"etiqueta": "Season", "tipo": "opcion", "opciones": ["SS26", "FW26"]}],
        "ordenes": [{"etiqueta": "Buyer", "tipo": "texto"}, {"etiqueta": "Budget", "tipo": "numero"}],
        "facturas": [{"etiqueta": "Letter of credit", "tipo": "texto", "obligatorio": True}],
    }})
    assert r.status_code == 200, r.text
    yield r.json()["campos_propios"]
    admin.put("/organizacion", {"campos_propios": {}})


def test_definiciones_validas(admin):
    malo = lambda d: admin.put("/organizacion", {"campos_propios": d}).status_code  # noqa: E731
    assert malo({"pedidos": []}) == 422
    assert malo({"articulos": [{"etiqueta": "X", "tipo": "color"}]}) == 422
    assert malo({"articulos": [{"etiqueta": "X", "tipo": "opcion"}]}) == 422
    assert malo({"articulos": [{"etiqueta": "Season"}, {"etiqueta": "season"}]}) == 422


def test_campo_propio_en_articulos(interno, campos):
    assert campos["articulos"][0]["clave"] == "season"
    meta = {c["tipo"]: c for c in interno.get("/catalogos").json()}
    campo = next(c for c in meta["articulos"]["campos"] if c["nombre"] == "extra.season")
    assert campo["tipo"] == "opcion" and ["FW26", "FW26"] in campo["opciones"]
    art = interno.get("/catalogos/articulos", params={"size": 1}).json()["items"][0]
    r = interno.patch(f"/catalogos/articulos/{art['id']}", {"extra.season": "verano"})
    assert r.status_code == 422 and "Season" in r.text
    r = interno.patch(f"/catalogos/articulos/{art['id']}", {"extra.season": "fw26"})
    assert r.status_code == 200 and r.json()["extra.season"] == "FW26"
    interno.patch(f"/catalogos/articulos/{art['id']}", {"extra.season": ""})


def test_campos_propios_en_oc_y_factura(interno, campos):
    base = interno.get("/ordenes", params={"q": "4400003901", "solo_disponible": False}).json()["items"][0]
    pos10 = interno.get(f"/ordenes/{base['id']}/posiciones").json()["posiciones"][0]
    csv = ("supplier,po_number,line,company,plant,storage_location,destination,currency,incoterm,item_code,quantity,unit_price,"
           "commercial_release,logistics_release,Buyer,Budget\n"
           f"VANS,4400009803,10,8000,8020,BF20,2220,USD,FOB,{pos10['codigo_sap']},6,25.5,C,300,Ana López,12500\n")
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h, files={"archivo": ("o.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["resumen"]["nuevo"] == 1, r.text
    assert interno.post(f"/ordenes/importar/{r.json()['importacion_id']}/aplicar").status_code == 200
    oc = interno.get("/ordenes", params={"q": "4400009803", "solo_disponible": False}).json()["items"][0]
    det_oc = interno.get(f"/ordenes/{oc['id']}/posiciones").json()
    assert det_oc["oc"]["extra"] == {"buyer": "Ana López", "budget": 12500.0}
    # Un número que no es número se rechaza en la previa
    malo = csv.replace("12500", "doce mil")
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h, files={"archivo": ("o.csv", malo.encode(), "text/csv")})
    assert r.json()["resumen"]["error"] == 1 and "Budget" in str(r.json()["filas"])

    f = interno.post("/facturas", {"lineas": [{"posicion_id": det_oc["posiciones"][0]["id"], "cantidad": 6}]})
    assert f.status_code == 200, f.text
    f = f.json()
    det = interno.get(f"/facturas/{f['id']}").json()
    assert "Letter of credit is missing." in [e["mensaje"] for e in det["pendientes"]]  # obligatorio para finalizar
    r = interno.patch(f"/facturas/{f['id']}", {"version": det["version"], "extra": {"letter_of_credit": "LC-2026-77"}})
    assert r.status_code == 200, r.text
    assert interno.get(f"/facturas/{f['id']}").json()["extra"] == {"letter_of_credit": "LC-2026-77"}
    assert "LC-2026-77" in _textos(interno.get(f"/facturas/{f['id']}/exportar").content)
    assert "Letter of credit is missing." not in [e["mensaje"] for e in interno.get(f"/facturas/{f['id']}").json()["pendientes"]]
