"""Los estados de liberación son datos de la empresa: códigos, nombres y
efecto se configuran en Datos maestros y el importador, la lista de OC, el
seguimiento y la plantilla los usan."""
from test_flujo import _oc


def test_estados_de_liberacion_configurables(interno):
    estados = interno.get("/catalogos/liberaciones").json()["items"]
    assert {(x["tipo"], x["codigo"]) for x in estados} >= {("COMERCIAL", "C"), ("LOGISTICA", "300"), ("LOGISTICA", "304")}
    # Solo un predeterminado por liberación
    r = interno.post("/catalogos/liberaciones", {"tipo": "LOGISTICA", "codigo": "REL", "nombre": "Liberada (ERP nuevo)",
                                                 "libera": True, "predeterminado": True, "orden": 9, "activo": True})
    assert r.status_code == 422
    r = interno.post("/catalogos/liberaciones", {"tipo": "LOGISTICA", "codigo": "REL", "nombre": "Liberada (ERP nuevo)",
                                                 "libera": True, "alias": "liberado por erp", "orden": 9, "activo": True})
    assert r.status_code == 200, r.text

    # El importador acepta el código nuevo (o su alias) y la OC queda liberada
    oc = _oc(interno, "4400003901")
    pos10, cab = oc["posiciones"][0], oc["oc"]
    enc = ("proveedor,oc,posicion,sociedad,centro,almacen,centro_destino,moneda,incoterm,sku,cantidad,precio,"
           "puerto,pais_origen,fecha_xf_original,fecha_tienda,liberacion_comercial,liberacion_logistica\n")
    fila = (f"VANS,4400009970,10,8000,8020,BF20,2220,USD,FOB,{pos10['codigo_sap']},12,25.5,VNSGN,VN,"
            f"{cab['fecha_xf_original']},{cab['fecha_tienda']},C,Liberado por ERP\n")
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h,
                       files={"archivo": ("ocs.csv", (enc + fila).encode(), "text/csv")})
    assert r.status_code == 200 and r.json()["resumen"]["nuevo"] == 1, r.text
    assert interno.post(f"/ordenes/importar/{r.json()['importacion_id']}/aplicar").status_code == 200
    nueva = interno.get("/ordenes", params={"q": "4400009970", "solo_disponible": False}).json()["items"][0]
    assert nueva["liberacion_logistica"] == "REL" and nueva["liberada"] is True
    assert nueva["liberacion_txt"] == "Liberada (ERP nuevo)"
    # Un código que la empresa no definió es un error, con la lista de los válidos
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h,
                       files={"archivo": ("x.csv", (enc + fila.replace("Liberado por ERP", "999")).encode(), "text/csv")})
    assert r.json()["resumen"]["error"] == 1 and "REL = Liberada (ERP nuevo)" in " ".join(r.json()["filas"][0]["mensajes"])
    # Filtro «no liberadas» y estados del seguimiento sin códigos de un ERP
    assert all(not o["liberada"] for o in interno.get("/ordenes", params={"liberada": False, "solo_disponible": False}).json()["items"])
    nombres = {e["nombre"] for e in interno.get("/seguimiento/ordenes").json()["estados"]}
    assert "No commercial release" in nombres and not any("304" in n or "(P)" in n for n in nombres)
    # La plantilla explica los códigos de la empresa
    assert interno.get("/ordenes/plantilla").status_code == 200
