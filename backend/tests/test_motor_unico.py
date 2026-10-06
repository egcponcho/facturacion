"""Motor único de clasificación: el mismo servicio para toda categoría (histórica
o creada desde la configuración), versiones y vigencias, códigos nacionales por
versión, varias longitudes por país, overrides, ámbitos, acciones de reglas y
configuraciones que de verdad cambian el resultado."""
from datetime import date

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AtributoDef, ControlCapitulo, IncisoNacional, NodoArancel, PaisArancel, VersionDataset
from app.services import motor_clasificacion as MC

CALZADO = {"categoria": "calzado", "estilo": "Old Skool", "ficha": {"edadNac": "adulto", "genero": "U", "estiloCalz": "tenis", "disenio": "casual",
                                                                   "comp": {"corte": "100% canvas", "suela": "100% rubber"}}, "paises": True}


def _sesion(api, entrada):
    r = api.post("/clasificacion/sesion", entrada)
    assert r.status_code == 200, r.text
    return r.json()


def test_categoria_historica_usa_el_motor_del_servidor(interno):
    """Calzado (antes clasificado en el navegador): ficha natural → hechos derivados → reglas → HS6 → SAC → países, con evidencia."""
    s = _sesion(interno, CALZADO)
    assert s["hs6"] == "640419" and s["confianza"] == "high"
    assert s["hechos"]["upper"] == "textil" and s["hechos"]["sole"] == "caucho"  # derivados de la composición en Python
    assert s["descripciones"]["aduana"].startswith("TENIS CON CORTE DE TEXTIL Y SUELA DE SINTÉTICO")
    assert s["version"]["codigo"] == "SAC-2025-V6" and s["evidencia"]["version"]["ambito"] == "REGIONAL"
    paises = {p["pais"]: p for p in s["clasificacion"]["paises"]}
    # SV aplica el SAC regional a 10 dígitos: su línea sale de la versión regional oficial, con su fuente
    assert paises["SV"]["codigo"] and paises["SV"]["version"]["codigo"] == "SAC-2025-V6" and paises["SV"]["fuente_oficial"]
    # Sin arancel nacional oficial cargado, el país lo dice (no se rellena con datos de la empresa)
    assert paises["PA"]["codigo"] is None and paises["PA"]["sin_datos_oficiales"] and "not available" in paises["PA"]["error"]
    assert all(p["codigo"] is None or p["codigo"].startswith("640419") for p in paises.values())
    regla = next(t for t in s["evidencia"]["reglas"] if t.get("aplicada") and t["regla"].startswith("R-MJS-CALZADO"))
    assert regla["foto"]["condiciones"] and regla["firma"] and regla["revision"] == 1
    # Preguntas que vienen del servidor (la ficha solo las dibuja)
    campos = {c["codigo"]: c for c in s["campos"]}
    assert campos["estiloCalz"]["estado"] in ("preguntar", "definido") and campos["upper"]["derivado"]
    assert campos["comp.corte"]["modo"] == "REQUIRE"


def test_ficha_natural_detecta_y_normaliza(interno):
    s = _sesion(interno, {"estilo": "Men's Vectiv trail running shoe", "ficha": {"comp": {"corte": "100% polyester", "suela": "100% rubber"}}})
    assert s["categoria"]["codigo"] == "calzado" and "categoria" in s["autos"]
    assert s["ficha"]["disenio"] == "entrenamiento" and s["ficha"]["genero"] == "M"
    assert s["hs6"] == "640411"
    # Lo que eligió la persona no se pisa
    s = _sesion(interno, {"estilo": "Men's Vectiv trail running shoe", "categoria": "calzado", "tocados": ["disenio"],
                          "ficha": {"disenio": "casual", "comp": {"corte": "100% polyester", "suela": "100% rubber"}}})
    assert s["ficha"]["disenio"] == "casual" and s["hs6"] == "640419"
    assert any("suggests" in a["msg"] for a in s["alertas"])


def test_atributo_custom_en_categoria_historica_show_require_hide(interno):
    a = interno.post("/aranceles/atributos", {"codigo": "drop_mm", "etiqueta": "Heel drop", "tipo_dato": "number", "dominio": "FOOTWEAR"}).json()
    r = interno.post(f"/aranceles/atributos/{a['id']}/ambitos", {"tipo_ambito": "CATEGORY", "codigo_ambito": "calzado", "modo": "REQUIRE", "prioridad": 600})
    assert r.status_code == 200, r.text
    s = _sesion(interno, CALZADO)
    campo = next(c for c in s["campos"] if c["codigo"] == "drop_mm")
    assert campo["modo"] == "REQUIRE" and any(f["campo"] == "drop_mm" for f in s["faltantes"])
    # HIDE más específico (condicionado) lo oculta
    interno.post(f"/aranceles/atributos/{a['id']}/ambitos", {"tipo_ambito": "SYSTEM", "codigo_ambito": "ALL", "modo": "SHOW", "prioridad": 999})
    s = _sesion(interno, {**CALZADO, "ficha": {**CALZADO["ficha"], "estiloCalz": "sandalia"}})
    assert any(c["codigo"] == "drop_mm" for c in s["campos"])
    d = interno.get(f"/aranceles/atributos/{a['id']}").json()
    cat = next(x for x in d["ambitos"] if x["tipo_ambito"] == "CATEGORY")
    interno.patch(f"/aranceles/atributos/{a['id']}/ambitos/{cat['id']}", {"modo": "HIDE"})
    s = _sesion(interno, CALZADO)
    assert not any(c["codigo"] == "drop_mm" for c in s["campos"])  # CATEGORY gana a SYSTEM aunque tenga menos prioridad
    s = _sesion(interno, {"categoria": "mochila", "ficha": {"comp": {"exterior": "100% polyester"}}})
    assert any(c["codigo"] == "drop_mm" for c in s["campos"])  # en otra categoría manda SYSTEM


def test_acciones_ask_review_warn_boost_exclude(interno):
    cond = [{"campo": "estiloCalz", "operador": "EQUAL", "valor": "tenis"}]
    reglas = []

    def regla(**d):
        r = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "calzado", **d})
        assert r.status_code == 200, r.text
        reglas.append(r.json())
        return r.json()

    regla(tipo_regla="QUESTION_GATE", condiciones=cond, accion={"tipo": "ASK", "atributos": ["impermeable"]}, prioridad=700)
    regla(tipo_regla="REVIEW_GATE", condiciones=cond, accion={"tipo": "REVIEW", "mensaje": "Check sneakers by hand"}, prioridad=700)
    regla(tipo_regla="REVIEW_GATE", condiciones=cond, accion={"tipo": "WARN", "mensaje": "Sneaker warning"}, prioridad=700)
    s = _sesion(interno, CALZADO)
    assert any(p["codigo"] == "impermeable" for p in s["preguntas"])
    assert s["requiere_revision"] and "Check sneakers by hand" in s["revision_por"]
    assert any(a["msg"] == "Sneaker warning" for a in s["alertas"])
    # EXCLUDE con mayor precedencia que la regla extraída: quita la subpartida; BOOST no agrega lo excluido
    regla(tipo_regla="HARD_CONSTRAINT", condiciones=cond, accion={"tipo": "EXCLUDE", "codigos": ["640419"]}, prioridad=990)
    regla(tipo_regla="SOFT_SIGNAL", condiciones=cond, accion={"tipo": "BOOST", "codigos": ["640419", "640411"], "peso": 50}, prioridad=980)
    s = _sesion(interno, CALZADO)
    t = next(t for t in s["reglas"] if t["regla"].startswith("R-MJS-CALZADO") and t["resultado"] is True)
    assert t["aplicada"] is False  # el RESTRICT a 640419 queda superado por el EXCLUDE de mayor precedencia
    assert s["hs6"] == "640411" and "640419" not in [c["codigo"] for c in s["candidatos"]]
    # requiere_revision en la regla aplicada
    r = reglas[-1]
    interno.patch(f"/aranceles/reglas/{r['id']}", {"requiere_revision": True})
    assert _sesion(interno, CALZADO)["requiere_revision"]
    for r in reglas:
        interno.patch(f"/aranceles/reglas/{r['id']}", {"activo": False})
    assert _sesion(interno, CALZADO)["hs6"] == "640419"


def test_usado_clasificacion_falso_no_altera_el_resultado(interno):
    with SessionLocal() as db:
        aid = db.scalar(select(AtributoDef.id).where(AtributoDef.codigo == "disenio"))
    entrada = {**CALZADO, "ficha": {**CALZADO["ficha"], "disenio": "entrenamiento"}}
    assert _sesion(interno, entrada)["hs6"] == "640411"
    interno.patch(f"/aranceles/atributos/{aid}", {"usado_clasificacion": False})
    s = _sesion(interno, entrada)
    assert s["hs6"] == "640419" and s["ficha"]["disenio"] == "entrenamiento"  # se recoge, no decide
    interno.patch(f"/aranceles/atributos/{aid}", {"usado_clasificacion": True})


def test_candidato_auto_falso_no_se_elige_solo(interno):
    with SessionLocal() as db:
        c = db.scalar(select(ControlCapitulo).where(ControlCapitulo.capitulo == "64"))
        c.candidato_auto = False
        db.commit()
    try:
        s = _sesion(interno, CALZADO)
        assert s["clasificacion"]["hs6"]["automatico"] is False and s["requiere_revision"]
    finally:
        with SessionLocal() as db:
            db.scalar(select(ControlCapitulo).where(ControlCapitulo.capitulo == "64")).candidato_auto = True
            db.commit()


def test_codigo_inexistente_no_aprobable(interno):
    s = _sesion(interno, {**CALZADO, "codigo_final": "640418"})
    assert any(a["nivel"] == "error" and "does not exist" in a["msg"] for a in s["alertas"])
    s = _sesion(interno, {**CALZADO, "codigo_final": "640411"})
    assert any(a["nivel"] == "error" and "contradicts rule" in a["msg"] for a in s["alertas"])
    s = _sesion(interno, {**CALZADO, "codigo_final": "610910"})
    assert any(a["nivel"] == "error" and "chapter 61" in a["msg"] for a in s["alertas"])


def _nueva_version(db, ambito, codigo, desde, copiar_de=None, sin=()):
    v = VersionDataset(codigo=codigo, dataset=f"{ambito} test", etiqueta=codigo, estado="PUBLICADA", vigente_desde=desde, ambito=ambito)
    db.add(v)
    db.flush()
    if copiar_de:
        ids = {}
        for n in db.scalars(select(NodoArancel).where(NodoArancel.version_id == copiar_de.id, NodoArancel.pais.is_(None),
                                                      NodoArancel.codigo_norm.startswith("64")).order_by(NodoArancel.id)):
            if any(n.codigo_norm.startswith(x) for x in sin):
                continue
            m = NodoArancel(version_id=v.id, nomenclatura=n.nomenclatura, nivel=n.nivel, codigo=n.codigo, codigo_norm=n.codigo_norm,
                            padre_id=ids.get(n.padre_id), descripcion=n.descripcion, dai=n.dai)
            db.add(m)
            db.flush()
            ids[n.id] = m.id
        for n in db.scalars(select(ControlCapitulo)):
            pass
    return v


def test_cambio_de_version_y_clasificacion_historica(interno):
    """2027 trae otra versión del SAC (sin la subpartida 6404.19): el motor la
    usa sola en esa fecha; una clasificación de 2026 se reproduce con la anterior."""
    from datetime import datetime

    with SessionLocal() as db:
        v6 = MC.resolver_version_vigente(db, "REGIONAL", date(2026, 6, 1))
        v6.vigente_hasta = date(2026, 12, 31)
        v27 = _nueva_version(db, "REGIONAL", "SAC-2027-T1", date(2027, 1, 1), copiar_de=v6, sin=("640419",))
        v27.importado_en = datetime(2027, 1, 1)
        db.commit()
        v6_id, v27_id = v6.id, v27.id
    try:
        assert _sesion(interno, {**CALZADO, "fecha": "2026-06-01"})["version"]["codigo"] == "SAC-2025-V6"
        s = _sesion(interno, {**CALZADO, "fecha": "2027-03-01", "paises": False})
        assert s["version"]["codigo"] == "SAC-2027-T1" and s["hs6"] != "640419"
        assert MC.resolver_version_vigente(SessionLocal(), "REGIONAL", date(2027, 3, 1)).id == v27_id
        # Reproducir la de 2026 con su versión
        with SessionLocal() as db:
            r = MC.clasificar_producto(db, {**CALZADO, "version_id": v6_id, "fecha": date(2027, 3, 1)}, paises=False)
        assert r["hs6"] == "640419" and r["version"]["id"] == v6_id
    finally:
        with SessionLocal() as db:
            db.get(VersionDataset, v27_id).estado = "ARCHIVADA"
            db.get(VersionDataset, v6_id).vigente_hasta = None
            db.commit()


def test_codigos_nacionales_por_version_y_varias_longitudes(interno):
    with SessionLocal() as db:
        cr = db.scalar(select(PaisArancel).where(PaisArancel.iso == "CR"))
        cr.longitudes = "8,10,12"
        vieja = MC.resolver_version_vigente(db, "CR")
        nueva = _nueva_version(db, "CR", "CR-2027-T", date(2027, 1, 1))
        db.add(IncisoNacional(pais="CR", codigo="640419909911", sub6="640419", fuente="oficial", version_id=nueva.id, descripcion="Nueva línea 2027"))
        db.add(IncisoNacional(pais="CR", codigo="640419909922", sub6="640419", fuente="oficial", version_id=vieja.id if vieja else None,
                              descripcion="Línea 2026", vigente_hasta=date(2026, 12, 31)))
        db.commit()
        nueva_id = nueva.id
    try:
        p26 = next(p for p in _sesion(interno, {**CALZADO, "fecha": "2026-06-01"})["clasificacion"]["paises"] if p["pais"] == "CR")
        p27 = next(p for p in _sesion(interno, {**CALZADO, "fecha": "2027-06-01"})["clasificacion"]["paises"] if p["pais"] == "CR")
        cods26 = {o["codigo"] for o in p26["opciones"]} | {p26["codigo"]}
        cods27 = {o["codigo"] for o in p27["opciones"]} | {p27["codigo"]}
        assert "640419909911" not in cods26 and "640419909911" in cods27  # nunca se mezclan versiones
        assert "640419909922" in cods26 and "640419909922" not in cods27  # ni se usa una línea vencida
        assert p27["version"]["codigo"] == "CR-2027-T" and p27["longitudes"] == [8, 10, 12]
        # Elegir una línea oficial vigente es válido; un código que no es línea oficial no (la empresa no crea códigos)
        ok = next(p for p in _sesion(interno, {**CALZADO, "partidas": {"CR": {"codigo": "640419909922", "manual": True}}})["clasificacion"]["paises"]
                  if p["pais"] == "CR")
        assert ok["estado"] == "ok" and ok["codigo"] == "640419909922"
        propio = next(p for p in _sesion(interno, {**CALZADO, "partidas": {"CR": {"codigo": "64041999", "manual": True}}})["clasificacion"]["paises"]
                      if p["pais"] == "CR")
        assert propio["estado"] == "invalido" and propio["codigo"] is None and "not an official national line" in propio["error"]
        mal = next(p for p in _sesion(interno, {**CALZADO, "partidas": {"CR": {"codigo": "640419999", "manual": True}}})["clasificacion"]["paises"]
                   if p["pais"] == "CR")
        assert mal["estado"] == "invalido" and mal["codigo"] is None
    finally:
        with SessionLocal() as db:
            db.get(VersionDataset, nueva_id).estado = "ARCHIVADA"
            db.scalar(select(PaisArancel).where(PaisArancel.iso == "CR")).longitudes = None
            db.commit()


def test_override_de_inciso_nacional_sin_tocar_el_oficial(interno):
    s = _sesion(interno, CALZADO)
    sv = next(p for p in s["clasificacion"]["paises"] if p["pais"] == "SV")
    iid = sv["inciso_id"]
    r = interno.patch(f"/aranceles/codigos/{iid}/override", {"descripcion": "Línea interna de tenis", "motivo": "Uso interno de la empresa"})
    assert r.status_code == 200, r.text
    sv2 = next(p for p in _sesion(interno, CALZADO)["clasificacion"]["paises"] if p["pais"] == "SV")
    assert sv2["descripcion"] == "Línea interna de tenis" and sv2["overrides"]
    with SessionLocal() as db:
        assert db.get(IncisoNacional, iid).descripcion != "Línea interna de tenis"  # el oficial no cambia
    interno.delete_(f"/aranceles/codigos/{iid}/override")
    sv3 = next(p for p in _sesion(interno, CALZADO)["clasificacion"]["paises"] if p["pais"] == "SV")
    assert sv3["descripcion"] != "Línea interna de tenis"


def test_categoria_nueva_solo_con_configuracion(interno):
    """Criterio de aceptación: dominio, categoría, atributos, opciones,
    dependencia, ámbitos, regla con condiciones y prioridad, código nacional →
    se clasifica sin tocar código, con el mismo motor que calzado."""
    d = interno.post("/aranceles/oficial/dominios", {"codigo": "POWER", "nombre": "Power and batteries", "modo": "AUTO"})
    assert d.status_code == 200, d.text
    r = interno.put(f"/aranceles/oficial/dominios/{d.json()['id']}/capitulos/85", {"relevancia": "PRIMARY", "habilitado": True})
    assert r.status_code == 200, r.text
    c = interno.post("/aranceles/categorias", {"codigo": "bateria", "nombre": "Batteries and power banks", "dominio": "POWER", "capitulos": ["85"],
                                                "patrones": [{"re": r"\b(power ?banks?|batter(y|ies))\b", "prioridad": 1}], "nombre_aduana": "Batería"})
    assert c.status_code == 200, c.text
    q = interno.post("/aranceles/atributos", {"codigo": "battery_chem", "etiqueta": "Chemistry", "tipo_dato": "select", "dominio": "POWER"}).json()
    for cod in ("LITHIUM_ION", "LEAD_ACID", "NIMH"):
        interno.post(f"/aranceles/atributos/{q['id']}/opciones", {"codigo": cod, "etiqueta": cod.title()})
    interno.post(f"/aranceles/atributos/{q['id']}/ambitos", {"tipo_ambito": "CATEGORY", "codigo_ambito": "bateria", "modo": "REQUIRE", "prioridad": 900})
    w = interno.post("/aranceles/atributos", {"codigo": "watt_hours", "etiqueta": "Watt-hours", "tipo_dato": "number", "dominio": "POWER"}).json()
    interno.post(f"/aranceles/atributos/{w['id']}/ambitos", {"tipo_ambito": "CATEGORY", "codigo_ambito": "bateria", "modo": "SHOW",
                                                           "condicion": [{"campo": "battery_chem", "operador": "EQUAL", "valor": "LITHIUM_ION"}]})
    for chem, cod in (("LITHIUM_ION", "850760"), ("LEAD_ACID", "850710")):
        r = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "bateria", "tipo_regla": "HARD_CONSTRAINT", "prioridad": 900,
                                                "condiciones": [{"campo": "battery_chem", "operador": "EQUAL", "valor": chem}],
                                                "accion": {"tipo": "RESTRICT", "codigos": [cod]}})
        assert r.status_code == 200, r.text
    # La línea nacional entra como dato oficial: con la fuente y la versión de su publicación
    r = interno.post("/aranceles/codigos", {"pais": "CR", "codigo": "850760001000", "descripcion": "Baterías de iones de litio", "dai": "0",
                                            "fuente": "SRC-CR-ATENA", "version": "CR-ATENA"})
    assert r.status_code in (200, 201), r.text
    # La categoría se reconoce por el nombre, la pregunta aparece, la dependiente no
    s = _sesion(interno, {"estilo": "Slim power bank 10000 mAh", "ficha": {}})
    assert s["categoria"]["codigo"] == "bateria" and s["categoria"]["dominio"] == "POWER"
    pregs = [p["codigo"] for p in s["preguntas"]]
    assert pregs[0] == "battery_chem" and "watt_hours" not in pregs
    # Respondo: aparece la dependiente, se restringe a 8507.60 y CR elige su línea
    s = _sesion(interno, {"estilo": "Slim power bank 10000 mAh", "categoria": "bateria", "ficha": {"battery_chem": "LITHIUM_ION"}})
    assert s["hs6"] == "850760" and s["confianza"] == "high" and "watt_hours" in [c["codigo"] for c in s["campos"]]
    cr = next(p for p in s["clasificacion"]["paises"] if p["pais"] == "CR")
    assert "850760001000" in [cr["codigo"]] + [o["codigo"] for o in cr["opciones"]]
    assert s["descripciones"]["aduana"].startswith("BATERÍA")
    s = _sesion(interno, {"estilo": "Car battery", "categoria": "bateria", "ficha": {"battery_chem": "LEAD_ACID"}})
    assert s["hs6"] == "850710"


def test_composicion_y_campos_salen_del_servidor(interno):
    """La ficha recibe del motor cada parte de la composición ya leída: filas
    con su clase, total, lo que se deriva (material del corte), sugerencias
    (lo que nombra el producto, lo típico de la categoría y el estilo) y las
    composiciones ya usadas; cada campo dice si es principal."""
    s = interno.post("/clasificacion/sesion", {"categoria": "calzado", "nombre": "Suede skate shoe", "paises": False,
                                               "ficha": {"estiloCalz": "tenis", "comp": {"corte": "60% canvas, 40% suede", "suela": ""}}}).json()
    corte = next(c for c in s["campos"] if c["codigo"] == "comp.corte")["composicion"]
    assert [f["m"] for f in corte["filas"]] == ["Canvas", "Suede"] and corte["total"] == 100
    assert {f["clase"]["clase"] for f in corte["filas"]} == {"textil", "cuero"}
    assert any(x["campo"] == "upper" for x in corte["lectura"])
    suela = next(c for c in s["campos"] if c["codigo"] == "comp.suela")["composicion"]
    assert suela["sugerencias"][0]["m"] == "Rubber" and all(x["fuente"] in ("rel", "base", "tipico") for x in suela["sugerencias"])
    assert suela["usadas"] and all(u["txt"] for u in suela["usadas"])  # del seed: calzado ya clasificado
    cor = interno.post("/clasificacion/sesion", {"categoria": "calzado", "nombre": "Suede skate shoe", "paises": False}).json()
    sug = next(c for c in cor["campos"] if c["codigo"] == "comp.corte")["composicion"]["sugerencias"]
    assert sug[0] == {"m": "Suede", "fuente": "rel"}  # lo nombra el producto
    campos = {c["codigo"]: c for c in s["campos"]}
    assert campos["estiloCalz"]["principal"] and not campos["technical_description"]["principal"]
    assert all(a.get("clave") for a in s["alertas"])


def test_especialista_recibe_la_ficha_del_motor(interno):
    """La opinión del especialista se arma en el servidor con el motor único
    (sin texto armado por el navegador): ficha legible, sugerencia, razones y
    los campos que puede corregir con sus valores válidos."""
    from app.models import Producto
    from app.services import especialista

    with SessionLocal() as db:
        p = db.scalar(select(Producto).where(Producto.estilo == "VN000EE3"))
        d = especialista.entrada(db, p)
    assert "Footwear style: " in d["ficha_texto"] and d["sugerido"] == "6404.19"
    assert "- estiloCalz (Footwear style): tenis = Sneaker" in d["campos"] and "comp.corte" in d["campos"]
    texto = especialista._prompt(d)
    assert "Rule engine suggestion: 6404.19" in texto


def test_pais_configurable_y_lineas_oficiales_con_override(interno):
    """Todo el esquema del país se configura desde la pantalla (longitudes,
    nivel base, modelo, contexto, fuente) y las líneas oficiales se ven como
    oficiales, con el ajuste propio aparte."""
    ps = {p["iso"]: p for p in interno.get("/aranceles/paises").json()}
    cr = ps["CR"]
    base = {k: cr[k] for k in ("iso", "nombre", "digitos", "mcca", "impuesto", "nota", "base_legal", "activo")}
    fuentes = interno.get("/aranceles/opciones").json()["fuentes_oficiales"]
    assert fuentes
    r = interno.put(f"/aranceles/paises/{cr['id']}", {**base, "digitos": 12, "longitudes": [10, 12], "nivel_base": "SAC8",
                                                       "modelo_arancel": "SAC + national precision", "contexto": "test", "fuente": fuentes[0]["codigo"]})
    assert r.status_code == 200, r.text
    cr2 = next(p for p in interno.get("/aranceles/paises").json() if p["iso"] == "CR")
    assert cr2["longitudes"] == [10, 12] and cr2["nivel_base"] == "SAC8" and cr2["fuente"] == fuentes[0]["codigo"]
    assert interno.put(f"/aranceles/paises/{cr['id']}", {**base, "longitudes": [5]}).status_code == 422
    assert interno.put(f"/aranceles/paises/{cr['id']}", {**base, "digitos": 8, "longitudes": [10, 12]}).status_code == 422
    interno.put(f"/aranceles/paises/{cr['id']}", {**base, "longitudes": [], "nivel_base": None, "fuente": None})
    # Línea oficial: se marca como tal y su ajuste propio se ve aparte del texto oficial
    gt = interno.get("/aranceles/codigos", params={"pais": "GT", "q": "6404199000"}).json()["items"][0]
    assert gt["oficial"] and not gt["override"]
    interno.patch(f"/aranceles/codigos/{gt['id']}/override", {"descripcion": "Tenis de lona (compras)", "motivo": "Texto interno"})
    gt2 = interno.get("/aranceles/codigos", params={"pais": "GT", "q": "6404199000"}).json()["items"][0]
    assert gt2["descripcion"] == "Tenis de lona (compras)" and gt2["descripcion_oficial"] == gt["descripcion"] and gt2["override"]
    interno.delete_(f"/aranceles/codigos/{gt['id']}/override")


def test_dominio_manual_no_se_aprueba_solo(interno):
    """Domain.modo = MANUAL: el motor sigue sugiriendo, pero no elige solo; la
    clasificación queda para revisión y lo dice. En AUTO vuelve a decidir."""
    dom = next(d for d in interno.get("/aranceles/oficial/dominios").json() if d["codigo"] == "FOOTWEAR")
    base = {"categoria": "calzado", "ficha": {"estiloCalz": "tenis", "altura": "bajo", "puntera": "ninguna", "genero": "U", "edadNac": "adulto",
                                              "comp": {"corte": "100% canvas", "suela": "100% rubber"}}, "origen": "CN", "paises": False}
    s = interno.post("/clasificacion/sesion", base).json()
    assert s["hs6"] == "640419" and s["clasificacion"]["hs6"]["automatico"] and not s["requiere_revision"]
    assert interno.patch(f"/aranceles/oficial/dominios/{dom['id']}", {"modo": "MANUAL"}).status_code == 200
    s = interno.post("/clasificacion/sesion", base).json()
    assert s["hs6"] == "640419" and not s["clasificacion"]["hs6"]["automatico"] and s["requiere_revision"]
    assert any("by hand" in x for x in s["revision_por"])
    interno.patch(f"/aranceles/oficial/dominios/{dom['id']}", {"modo": "AUTO"})
    assert not interno.post("/clasificacion/sesion", base).json()["requiere_revision"]
