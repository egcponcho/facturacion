"""Recepción en bodega y anulación de embarques (docs/FLUJOS.md §3): se
recibe por línea cuando el embarque ya llegó, las diferencias crean una
alerta y, con todas sus listas recibidas, el embarque queda recibido."""
from datetime import datetime

from app.core.db import SessionLocal
from app.modelos import Alerta


def _ahora():
    return datetime.now().replace(microsecond=0).isoformat()


def _en_transito(interno):
    for e in interno.get("/embarques").json():
        if e["estado"] == "EN_TRANSITO":
            det = interno.get(f"/embarques/{e['id']}").json()
            pls = [p for u in det["unidades"] for p in interno.get(f"/unidades/{u['id']}").json()["asignados"]]
            if pls:
                return det, pls
    raise AssertionError("La demostración no tiene un embarque en tránsito con carga")


def test_recepcion_solo_al_llegar_y_cierra_el_embarque(interno):
    e, pls = _en_transito(interno)
    pl = interno.get(f"/packing-lists/{pls[0]['id']}").json()
    assert pl["puede"]["recepcion"] is False
    lineas = [{"pl_linea_id": ln["id"], "cantidad_recibida": ln["cantidad"], "cantidad_danada": 0} for ln in pl["lineas"]]
    r = interno.post(f"/packing-lists/{pl['id']}/recepcion", {"lineas": lineas})
    assert r.status_code == 409 and r.json()["codigo"] == "embarque_no_llego"
    # Llega: ya se recibe
    assert interno.post(f"/embarques/{e['id']}/eventos", {"tipo": "ARRIBO", "fecha": _ahora()}).json()["estado"] == "ARRIBADO"
    assert interno.get(f"/packing-lists/{pl['id']}").json()["puede"]["recepcion"] is True
    # Con diferencias: queda la alerta para reclamar
    con_faltante = [{**lineas[0], "cantidad_recibida": lineas[0]["cantidad_recibida"] - 1, "cantidad_danada": 1}] + lineas[1:]
    r = interno.post(f"/packing-lists/{pl['id']}/recepcion", {"lineas": con_faltante})
    assert r.status_code == 200, r.text
    assert len(r.json()["diferencias"]) == 1
    with SessionLocal() as db:
        alerta = db.query(Alerta).filter(Alerta.tipo == "recepcion_diferencia").order_by(Alerta.id.desc()).first()
        assert alerta and alerta.referencia["pl_id"] == pl["id"]
    recibido = r.json()["embarque_recibido"]
    # Con todas sus listas recibidas el embarque queda recibido (y el hito queda registrado)
    for otro in pls[1:]:
        d = interno.get(f"/packing-lists/{otro['id']}").json()
        r = interno.post(f"/packing-lists/{otro['id']}/recepcion", {"lineas": [
            {"pl_linea_id": ln["id"], "cantidad_recibida": ln["cantidad"], "cantidad_danada": 0} for ln in d["lineas"]]})
        assert r.status_code == 200, r.text
        recibido = r.json()["embarque_recibido"]
    assert recibido is True
    det = interno.get(f"/embarques/{e['id']}").json()
    assert det["estado"] == "RECIBIDO" and any(ev["tipo"] == "RECEPCION" for ev in det["eventos"])


def test_hito_de_recepcion_recibe_sin_novedad(interno):
    e, pls = _en_transito(interno)
    interno.post(f"/embarques/{e['id']}/eventos", {"tipo": "ARRIBO", "fecha": _ahora()})
    interno.post(f"/embarques/{e['id']}/eventos", {"tipo": "ENTREGA", "fecha": _ahora()})
    r = interno.post(f"/embarques/{e['id']}/eventos", {"tipo": "RECEPCION", "fecha": _ahora()})
    assert r.status_code == 200 and r.json()["estado"] == "RECIBIDO"
    for p in pls:
        d = interno.get(f"/packing-lists/{p['id']}").json()
        assert all(ln["recepcion"] and ln["recepcion"]["cantidad_recibida"] == ln["cantidad"] for ln in d["lineas"])


def test_anular_un_embarque(interno):
    e = interno.post("/embarques", {"tipo_transporte": "MARITIMO"}).json()
    assert interno.post(f"/embarques/{e['id']}/cancelar", {}).status_code == 422  # pide motivo
    r = interno.post(f"/embarques/{e['id']}/cancelar", {"motivo": "Booking cancelled by the carrier"})
    assert r.status_code == 200 and r.json()["estado"] == "CANCELADO"
    r = interno.post(f"/embarques/{e['id']}/cancelar", {"motivo": "otra vez"})
    assert r.status_code == 409 and r.json()["codigo"] == "transicion_invalida"
    # Uno que ya salió no se anula
    salido = next((x for x in interno.get("/embarques").json() if x["estado"] not in ("PLANIFICADO", "CANCELADO")), None)
    if salido:
        assert interno.post(f"/embarques/{salido['id']}/cancelar", {"motivo": "x"}).status_code == 409
