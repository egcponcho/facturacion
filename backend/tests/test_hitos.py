"""Hitos del embarque configurables (Datos maestros → Listas de valores →
Shipment milestones): los de sistema mantienen sus reglas; la empresa agrega
los suyos con los estados en que se registran."""
from datetime import date


def _id_valor(api, codigo):
    items = api.get("/catalogos/listas", params={"lista": "evento_embarque", "size": 200}).json()["items"]
    return next(x["id"] for x in items if x["codigo"] == codigo)


def test_hitos_de_fabrica(interno):
    hitos = {v["codigo"]: v for v in interno.get("/listas").json()["evento_embarque"]}
    assert hitos["SALIDA"]["estados"] == "PLANIFICADO" and "RECIBIDO" in hitos["OTRO"]["estados"]


def test_hitos_de_sistema_mantienen_sus_reglas(interno):
    salida = _id_valor(interno, "SALIDA")
    r = interno.patch(f"/catalogos/listas/{salida}", {"estados": ["PLANIFICADO", "ARRIBADO"]})
    assert r.status_code == 422 and "system milestone" in r.text
    assert interno.patch(f"/catalogos/listas/{salida}", {"nombre": "Zarpe"}).status_code == 200
    assert interno.patch(f"/catalogos/listas/{salida}", {"nombre": "Departure"}).status_code == 200
    assert interno.delete_(f"/catalogos/listas/{salida}").status_code == 409


def test_hito_propio(interno):
    r = interno.post("/catalogos/listas", {"lista": "evento_embarque", "codigo": "INSPECCION", "nombre": "Port inspection",
                                           "estados": ["NO_EXISTE"]})
    assert r.status_code == 422
    r = interno.post("/catalogos/listas", {"lista": "evento_embarque", "codigo": "INSPECCION", "nombre": "Port inspection"})
    assert r.status_code == 422 and "statuses" in r.text
    r = interno.post("/catalogos/listas", {"lista": "evento_embarque", "codigo": "INSPECCION", "nombre": "Port inspection",
                                           "estados": ["EN_TRANSITO", "PLANIFICADO"]})
    assert r.status_code == 200, r.text
    assert r.json()["estados"] == ["PLANIFICADO", "EN_TRANSITO"]
    hito = r.json()["id"]
    try:
        emb = next(e for e in interno.get("/embarques").json() if e["estado"] == "PLANIFICADO")
        det = interno.get(f"/embarques/{emb['id']}").json()
        assert "INSPECCION" in det["eventos_permitidos"]
        r = interno.post(f"/embarques/{emb['id']}/eventos", {"tipo": "INSPECCION", "fecha": f"{date.today()}T08:00:00"})
        assert r.status_code == 200 and r.json()["estado"] == "PLANIFICADO"  # un hito propio no cambia el estado
        r = interno.post(f"/embarques/{emb['id']}/eventos", {"tipo": "ENTREGA", "fecha": f"{date.today()}T09:00:00"})
        assert r.status_code == 409
    finally:
        interno.patch(f"/catalogos/listas/{hito}", {"activo": False})


def test_paneles_del_inicio_por_rol(admin, vans):
    roles = admin.get("/roles").json()
    assert {p["clave"] for p in roles["paneles"]} >= {"indicadores", "envios", "periodo"}
    rol = next(r for r in roles["roles"] if r["id"] == vans.yo.get("rol_id") or r["nombre"] == vans.yo.get("rol_nombre"))
    try:
        r = admin.patch(f"/roles/{rol['id']}", {"inicio_oculto": ["periodo", "no_existe", "envios"]})
        assert r.status_code == 200 and r.json()["inicio_oculto"] == ["envios", "periodo"]
        assert vans.get("/auth/me").json()["inicio_oculto"] == ["envios", "periodo"]
    finally:
        admin.patch(f"/roles/{rol['id']}", {"inicio_oculto": []})
