"""Perfiles de importación: el archivo del ERP de la empresa se lee con sus
propios nombres de columna, su fila de encabezados, su formato de fecha y sus
valores por defecto. Sin perfil, el sistema reconoce nombres genéricos."""


def _oc(api, numero):
    oc = api.get("/ordenes", params={"q": numero, "solo_disponible": False}).json()["items"][0]
    return api.get(f"/ordenes/{oc['id']}/posiciones").json()


def _previa(api, csv, perfil_id=None):
    datos = {"perfil_id": str(perfil_id)} if perfil_id else None
    return api.c.post("/api/ordenes/importar/previa", headers=api.h, data=datos,
                      files={"archivo": ("erp.csv", csv.encode(), "text/csv")})


def test_campos_y_validaciones(interno):
    r = interno.get("/ordenes/importar/perfiles").json()
    campos = {c["campo"]: c for c in r["campos"]}
    assert campos["codigo_sap"]["requerido"] and not campos["codigo_sap"]["admite_defecto"]
    assert "sap" not in campos["codigo_sap"]["reconocidos"] and "sap_code" not in campos["codigo_sap"]["reconocidos"]
    assert "DD/MM/YYYY" in r["formatos_fecha"]
    malo = lambda datos, texto: (lambda x: x.status_code == 422 and texto in x.text)(interno.post("/ordenes/importar/perfiles", datos))  # noqa: E731
    assert malo({"codigo": "", "nombre": "X"}, "Code is required")
    assert malo({"codigo": "X", "nombre": "X", "columnas": {"no_existe": "A"}}, "Map only")
    assert malo({"codigo": "X", "nombre": "X", "valores": {"oc": "1"}}, "cannot have a default value")
    assert malo({"codigo": "X", "nombre": "X", "fila_encabezado": 0}, "header row")
    assert malo({"codigo": "X", "nombre": "X", "formato_fecha": "D.M.Y"}, "date format")


def test_archivo_del_erp_con_perfil(interno):
    base = _oc(interno, "4400003901")
    pos10, cab = base["posiciones"][0], base["oc"]
    xf = cab["fecha_xf_original"]  # ISO
    xf_dmy = f"{xf[8:10]}.{xf[5:7]}.{xf[0:4]}"
    # Archivo con dos filas de título, columnas en alemán y fechas DD.MM.YYYY
    csv = ("Bestellungen Export\n;;;\n"
           "Lieferant;Bestellnummer;Pos;Buchungskreis;Werk;Lagerort;Ziel;Artikelnummer;Menge;Preis;Liefertermin\n"
           f"VANS;4400009801;10;8000;8020;BF20;2220;{pos10['codigo_sap']};6;25,5;{xf_dmy}\n")
    sin_perfil = _previa(interno, csv)
    assert sin_perfil.status_code == 422 and "missing required columns" in sin_perfil.text
    r = interno.post("/ordenes/importar/perfiles", {
        "codigo": "ERP-DE", "nombre": "ERP alemán", "fila_encabezado": 3, "formato_fecha": "DD.MM.YYYY",
        "columnas": {"proveedor": "Lieferant", "oc": "Bestellnummer", "posicion": "Pos", "sociedad": "Buchungskreis",
                     "centro": "Werk", "almacen": "Lagerort", "centro_destino": "Ziel", "codigo_sap": "Artikelnummer, SKU",
                     "cantidad": "Menge", "precio": "Preis", "fecha_xf_original": "Liefertermin"},
        "valores": {"moneda": "USD", "incoterm": "FOB", "liberacion_comercial": "C"}})
    assert r.status_code == 422 and "date format" in r.text  # DD.MM.YYYY no es un formato del sistema
    perfil = interno.post("/ordenes/importar/perfiles", {
        "codigo": "ERP-DE", "nombre": "ERP alemán", "fila_encabezado": 3, "formato_fecha": "DD/MM/YYYY",
        "columnas": {"proveedor": "Lieferant", "oc": "Bestellnummer", "posicion": "Pos", "sociedad": "Buchungskreis",
                     "centro": "Werk", "almacen": "Lagerort", "centro_destino": "Ziel", "codigo_sap": "Artikelnummer, SKU",
                     "cantidad": "Menge", "precio": "Preis", "fecha_xf_original": "Liefertermin"},
        "valores": {"moneda": "USD", "incoterm": "FOB", "liberacion_comercial": "C"}}).json()
    try:
        csv = csv.replace(xf_dmy, f"{xf[8:10]}/{xf[5:7]}/{xf[0:4]}")
        r = _previa(interno, csv, perfil["id"])
        assert r.status_code == 200, r.text
        assert r.json()["resumen"]["nuevo"] == 1, r.json()["filas"]
        assert interno.post(f"/ordenes/importar/{r.json()['importacion_id']}/aplicar").status_code == 200
        nueva = _oc(interno, "4400009801")["oc"]
        assert nueva["moneda"] == "USD" and nueva["incoterm"] == "FOB" and nueva["fecha_xf_original"] == xf
        # Predeterminado: se usa sin elegirlo
        assert interno.patch(f"/ordenes/importar/perfiles/{perfil['id']}", {"predeterminado": True}).status_code == 200
        assert _previa(interno, csv).status_code == 200
        # Inactivo: no se puede elegir
        interno.patch(f"/ordenes/importar/perfiles/{perfil['id']}", {"activo": False, "predeterminado": False})
        assert _previa(interno, csv, perfil["id"]).status_code == 422
    finally:
        assert interno.delete_(f"/ordenes/importar/perfiles/{perfil['id']}").status_code == 200


def test_sin_perfil_se_leen_los_nombres_genericos(interno):
    """La plantilla del sistema sigue funcionando sin ningún perfil."""
    pos10 = _oc(interno, "4400003901")["posiciones"][0]
    csv = ("supplier,po_number,line,company,plant,storage_location,destination,currency,incoterm,item_code,quantity\n"
           f"VANS,4400009802,10,8000,8020,BF20,2220,USD,FOB,{pos10['codigo_sap']},6\n")
    r = _previa(interno, csv)
    assert r.status_code == 200 and r.json()["resumen"]["nuevo"] == 1, r.text
