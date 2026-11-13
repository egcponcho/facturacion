"""Inicio del diseño v3: cuatro indicadores elegidos por la persona, la gráfica
de comprado contra recibido y los bloques que cada quien agrega en
«Personalizar panel»."""


def test_inicio_trae_cuatro_indicadores_de_punta_a_punta(interno):
    t = interno.get("/tableros/inicio").json()
    assert t["elegidos"] == ["importe_comprado", "oc_abiertas", "puntualidad", "embarques_en_transito"]
    assert t["origen"] == "sistema" and len(t["indicadores"]) == 4
    comprado = next(i for i in t["indicadores"] if i["clave"] == "importe_comprado")
    # Un indicador del período trae su serie para dibujar la tendencia
    assert comprado["serie"] and comprado["moneda"]
    # El Inicio no aparece como un tablero más de Análisis
    assert "inicio" not in {m["clave"] for m in interno.get("/tableros").json()}


def test_cada_persona_elige_hasta_cuatro_indicadores(interno):
    r = interno.put("/tableros/inicio/propios", {"claves": ["oc_atrasadas", "importe_comprado"]})
    assert r.status_code == 200 and r.json()["elegidos"] == ["oc_atrasadas", "importe_comprado"]
    assert interno.get("/tableros/inicio").json()["origen"] == "usuario"
    cinco = ["oc_atrasadas", "importe_comprado", "oc_abiertas", "puntualidad", "arribos"]
    assert interno.put("/tableros/inicio/propios", {"claves": cinco}).status_code == 422
    assert interno.put("/tableros/inicio/propios", {"claves": None}).json()["elegidos"][0] == "importe_comprado"


def test_un_proveedor_ve_solo_lo_que_su_rol_permite(tnf):
    t = tnf.get("/tableros/inicio").json()
    # Sin permiso de transporte, sus cuatro se completan con otros que sí ve
    assert "embarques_en_transito" not in t["elegidos"] and len(t["elegidos"]) <= 4


def test_comprado_contra_recibido_por_mes(interno):
    r = interno.get("/dashboard/compras-recepcion", params={"meses": 6}).json()
    assert r["meses"] == 6 and len(r["serie"]) == 6 and r["moneda"]
    assert all(set(x) == {"mes", "comprado", "recibido"} for x in r["serie"])
    # Los meses van del más viejo al actual, sin huecos
    meses = [x["mes"] for x in r["serie"]]
    assert meses == sorted(meses) and len(set(meses)) == 6
    # La demostración tiene OC aprobadas: algo se compró en el último año
    anio = interno.get("/dashboard/compras-recepcion").json()
    assert anio["meses"] == 12 and sum(x["comprado"] for x in anio["serie"]) > 0
    # Un número de meses que no existe vuelve a 12
    assert interno.get("/dashboard/compras-recepcion", params={"meses": 7}).json()["meses"] == 12


def test_bloques_del_inicio_por_persona(interno):
    assert interno.put("/perfil/inicio", {"bloques": ["envios", "bandeja", "grafico"]}).json()["bloques"] == \
        ["bandeja", "grafico", "envios"]
    assert interno.get("/auth/me").json()["preferencias"]["inicio_bloques"] == ["bandeja", "grafico", "envios"]
    assert interno.put("/perfil/inicio", {"bloques": ["otro"]}).status_code == 422
    assert interno.put("/perfil/inicio", {"bloques": None}).json()["bloques"] == ["bandeja", "indicadores", "grafico"]
