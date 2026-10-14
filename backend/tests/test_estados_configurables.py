"""Estados configurables: la empresa elige etiqueta, color y orden de los
estados de cada documento; los códigos son fijos."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import EstadoDocumento


def test_personalizar_estados(admin, interno):
    o = admin.get("/organizacion").json()
    docs = {d["clave"]: d for d in o["documentos_estados"]}
    assert docs["oc"]["codigos"][0] == "BORRADOR" and "cobro" not in docs
    assert set(o["tonos"]) == {"neutro", "info", "ok", "aviso", "error"}

    r = admin.put("/organizacion", {"estados": {"oc": [
        {"codigo": "APROBADA", "etiqueta": "Released to supplier", "tono": "info"}, {"codigo": "BORRADOR"}]}})
    assert r.status_code == 200, r.text
    oc = r.json()["estados"]["oc"]
    assert oc["APROBADA"] == {"etiqueta": "Released to supplier", "tono": "info", "orden": 1}
    assert oc["BORRADOR"]["orden"] == 2 and oc["CANCELADA"]["orden"] == 6
    # La sesión lo trae para mostrarlo en todas las pantallas
    assert interno.get("/auth/me").json()["organizacion"]["estados"]["oc"]["APROBADA"]["etiqueta"] == "Released to supplier"

    # Los códigos son fijos; el color, de la lista
    assert admin.put("/organizacion", {"estados": {"oc": [{"codigo": "PAUSADA"}]}}).status_code == 422
    assert admin.put("/organizacion", {"estados": {"oc": [{"codigo": "BORRADOR", "tono": "rosa"}]}}).status_code == 422
    assert admin.put("/organizacion", {"estados": {"pedido": []}}).status_code == 422
    assert admin.put("/organizacion", {"estados": {"oc": [{"codigo": "BORRADOR"}, {"codigo": "BORRADOR"}]}}).status_code == 422

    # Volver a fábrica no deja filas
    assert admin.put("/organizacion", {"estados": {"oc": []}}).json()["estados"].get("oc") is None
    with SessionLocal() as db:
        assert not db.scalars(select(EstadoDocumento).where(EstadoDocumento.documento == "oc")).all()
