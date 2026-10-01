"""Capa oficial del arancel (paquetes Excel 01 y 02) y migraciones."""
import io
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook

RAIZ = Path(__file__).resolve().parent.parent


def test_migraciones_al_dia_con_los_modelos():
    """Las migraciones de Alembic crean exactamente el esquema de los modelos:
    un cambio de modelo sin su migración hace fallar esta prueba."""
    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        for args in (["upgrade", "head"], ["check"], ["downgrade", "base"], ["upgrade", "head"]):
            r = subprocess.run(alembic + args, cwd=RAIZ, env=env, capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr


def test_paquete_oficial_cargado(interno):
    caps = interno.get("/aranceles/oficial/capitulos").json()
    assert caps["total"] == 99 and caps["habilitados"] > 60
    por = {c["capitulo"]: c for c in caps["items"]}
    assert por["64"]["clasificacion"] and por["01"]["activo"] is False
    assert {d["codigo"] for d in por["28"]["dominios"]} == {"CHEMICALS", "RAW_MATERIALS"}
    assert por["57"]["solo_manual"] and not por["57"]["candidato_auto"]
    fv = interno.get("/aranceles/oficial/fuentes").json()
    assert {"SRC-SIECA-ACI", "SRC-CR-ATENA", "SRC-PA-ANA"} <= {f["codigo"] for f in fv["fuentes"]}
    sac = next(v for v in fv["versiones"] if v["codigo"] == "SAC-2025-V6")
    assert sac["estado"] == "PUBLICADA" and sac["fuente"] == "SRC-SIECA-ACI" and sac["vigente_desde"] == "2025-08-01"
    doms = {d["codigo"]: d for d in interno.get("/aranceles/oficial/dominios").json()}
    assert set(doms) == {"CHEMICALS", "RAW_MATERIALS", "FOOTWEAR", "APPAREL", "ACCESSORIES_MERCH"}
    quim = {c["capitulo"]: c["relevancia"] for c in doms["CHEMICALS"]["capitulos"]}
    assert quim["29"] == "PRIMARY" and quim["39"] == "SECONDARY"
    # Búsqueda inteligente en capítulos
    assert [c["capitulo"] for c in interno.get("/aranceles/oficial/capitulos", params={"q": "quimicos organicos"}).json()["items"]] == ["28", "29"]
    assert [c["capitulo"] for c in interno.get("/aranceles/oficial/capitulos", params={"q": "calzado polainas"}).json()["items"]] == ["64"]


def test_control_de_capitulos_en_bloque(interno):
    caps = {c["capitulo"]: c for c in interno.get("/aranceles/oficial/capitulos").json()["items"]}
    ids = [caps["93"]["id"], caps["97"]["id"]]
    r = interno.patch("/aranceles/oficial/capitulos", {"ids": ids, "clasificacion": True, "candidato_auto": True})
    assert r.status_code == 200, r.text
    caps = {c["capitulo"]: c for c in interno.get("/aranceles/oficial/capitulos").json()["items"]}
    assert caps["97"]["activo"] and caps["97"]["clasificacion"]  # habilitar activa el capítulo
    r = interno.patch("/aranceles/oficial/capitulos", {"ids": ids, "archivado": True})
    caps = {c["capitulo"]: c for c in interno.get("/aranceles/oficial/capitulos").json()["items"]}
    assert caps["97"]["archivado"] and not caps["97"]["clasificacion"] and not caps["97"]["candidato_auto"]


def test_reimportar_es_idempotente_y_valida(interno):
    paquete = (RAIZ / "app/data/oficial/01_carga_oficial_catalogos_v3.xlsx").read_bytes()
    r = interno.c.post("/api/aranceles/oficial/importar", headers=interno.h,
                       files={"archivo": ("01.xlsx", io.BytesIO(paquete), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["creados"] == 0 and not r.json()["errores"], r.text
    wb = Workbook()
    ws = wb.active
    ws.title = "Versions"
    ws.append(["Version ID", "Dataset", "Version label", "Status", "Valid from", "Valid to", "Source ID"])
    ws.append(["GT-2026", "Guatemala national overlay", "2026 snapshot", "Draft", "2026-01-01", "2025-01-01", "SRC-GT-SAT"])
    ws.append(["X-1", "Nothing", "x", "Draft", "", "", "SRC-NO-EXISTE"])
    b = io.BytesIO()
    wb.save(b)
    r = interno.c.post("/api/aranceles/oficial/importar", headers=interno.h,
                       files={"archivo": ("v.xlsx", io.BytesIO(b.getvalue()), "application/octet-stream")})
    errores = [e["mensaje"] for e in r.json()["errores"]]
    assert any("Valid to" in m for m in errores) and any("SRC-NO-EXISTE" in m for m in errores)


def test_arbol_arancelario_completo(interno):
    r = interno.get("/aranceles/arbol/resumen").json()
    assert r["version"] == "SAC-2025-V6" and len(r["checksum"]) == 64
    assert r["niveles"]["CAPITULO"] == 99 and r["niveles"]["PARTIDA"] > 1000 and r["niveles"]["INCISO"] > 8000
    caps = interno.get("/aranceles/arbol").json()["items"]
    c64 = next(c for c in caps if c["codigo"] == "64")
    assert c64["capitulo_habilitado"] and c64["hijos"] == 6
    # Capítulos fuera del motor actual también tienen sus incisos (p. ej. químicos, cap. 29)
    c29 = next(c for c in caps if c["codigo"] == "29")
    partidas = interno.get("/aranceles/arbol", params={"padre_id": c29["id"]}).json()["items"]
    assert partidas[0]["codigo"].startswith("29") and partidas[0]["nivel"] == "PARTIDA"
    # Búsqueda por código (con puntos o varios) y por palabras en cualquier orden
    r = interno.get("/aranceles/arbol", params={"q": "6404.19"}).json()
    assert r["items"][0]["codigo"] == "6404.19" and all(i["codigo_norm"].startswith("640419") for i in r["items"])
    r = interno.get("/aranceles/arbol", params={"q": "6404.11 4202.92"}).json()
    assert {i["codigo_norm"][:6] for i in r["items"]} == {"640411", "420292"}
    r = interno.get("/aranceles/arbol", params={"q": "caucho suela calzado"}).json()
    assert r["total"] > 0 and any(i["codigo_norm"].startswith("64") for i in r["items"])
    n = interno.get(f"/aranceles/arbol/{r['items'][0]['id']}").json()
    assert n["ruta"][0]["nivel"] == "CAPITULO" and n["version"]["fuente"] == "SRC-SIECA-ACI"
    sub = next(i for i in interno.get("/aranceles/arbol", params={"q": "6404.19"}).json()["items"] if i["codigo"] == "6404.19")
    d = interno.get(f"/aranceles/arbol/{sub['id']}").json()
    assert d["hijos_lista"] and d["hijos_lista"][0]["dai"] is not None
    assert any(p["iso"] == "SV" and p["codigos"] for p in d["paises"]) and d["notas"]


def test_atributos_en_base_de_datos(interno):
    """Atributos oficiales (paquete 02) y de la ficha del motor, con opciones y ámbitos."""
    r = interno.get("/aranceles/atributos").json()
    assert r["por_origen"]["OFICIAL"] == 38 and r["por_origen"]["MOTOR"] == 57
    por = {a["codigo"]: a for a in r["items"]}
    assert por["cas_number"]["dominio"] == "CHEMICALS" and por["material_composition"]["tipo_dato"] == "composition"
    assert por["estiloCalz"]["dominio"] == "FOOTWEAR" and por["tejido"]["dominio"] == "APPAREL"
    d = interno.get(f"/aranceles/atributos/{por['physical_state']['id']}").json()
    assert [o["codigo"] for o in d["opciones"]] == ["SOLID", "LIQUID", "GAS", "POWDER", "PASTE"]
    assert d["ambitos"][0]["tipo_ambito"] == "DOMAIN" and d["ambitos"][0]["codigo_ambito"] == "CHEMICALS"
    # Ámbitos del motor: categorías donde aplica y respuestas que lo activan
    t = interno.get(f"/aranceles/atributos/{por['tejido']['id']}").json()
    cint = next(x for x in t["ambitos"] if x["codigo_ambito"] == "cinturon")
    assert {"materialCinturon": "textil"} in cint["condicion"]
    assert next(x for x in t["ambitos"] if x["codigo_ambito"] == "camiseta")["condicion"] is None
    # Búsqueda inteligente
    assert {a["codigo"] for a in interno.get("/aranceles/atributos", params={"q": "name chemic"}).json()["items"]} == {"chemical_name"}
    # La ficha recibe el catálogo en el contexto
    ctx = interno.get("/clasificacion/contexto").json()["atributos"]
    assert ctx["motor"]["tejido"]["opciones"]["punto"]["activo"] and len(ctx["genericos"]) == 38


def test_editar_atributos_opciones_y_ambitos(interno):
    por = {a["codigo"]: a for a in interno.get("/aranceles/atributos").json()["items"]}
    aid = por["physical_state"]["id"]
    d = interno.post(f"/aranceles/atributos/{aid}/opciones", {"codigo": "GRANULE", "etiqueta": "Granules", "alias": "pellets; granules"}).json()
    assert d["opciones"][-1]["codigo"] == "GRANULE"
    gas = next(o for o in d["opciones"] if o["codigo"] == "GAS")
    d = interno.patch(f"/aranceles/atributos/{aid}/opciones/{gas['id']}", {"activo": False}).json()
    assert not next(o for o in d["opciones"] if o["codigo"] == "GAS")["activo"]
    d = interno.post(f"/aranceles/atributos/{aid}/ambitos", {"tipo_ambito": "CHAPTER", "codigo_ambito": "28", "modo": "REQUIRE", "prioridad": 950}).json()
    amb = next(x for x in d["ambitos"] if x["tipo_ambito"] == "CHAPTER")
    assert amb["modo"] == "REQUIRE"
    r = interno.post(f"/aranceles/atributos/{aid}/ambitos", {"tipo_ambito": "CHAPTER", "codigo_ambito": "28"})
    assert r.status_code == 422
    d = interno.patch(f"/aranceles/atributos/{aid}/ambitos/{amb['id']}", {"quitar": True}).json()
    assert not any(x["tipo_ambito"] == "CHAPTER" for x in d["ambitos"])
    # Etiqueta editada y atributo apagado llegan a la ficha
    interno.patch(f"/aranceles/atributos/{por['polo']['id']}", {"etiqueta": "Polo collar", "activo": False})
    ctx = interno.get("/clasificacion/contexto").json()["atributos"]["motor"]["polo"]
    assert ctx["etiqueta"] == "Polo collar" and ctx["activo"] is False
    interno.patch(f"/aranceles/atributos/{por['polo']['id']}", {"etiqueta": "Has a collar and a buttoned placket at the neck (polo style)", "activo": True})
    # Nuevo atributo del usuario
    d = interno.post("/aranceles/atributos", {"codigo": "flash_point", "etiqueta": "Flash point", "tipo_dato": "number", "unidad": "°C", "dominio": "CHEMICALS"}).json()
    assert d["origen"] == "USUARIO" and d["unidad"] == "°C"
    assert interno.post("/aranceles/atributos", {"codigo": "flash_point", "etiqueta": "x"}).status_code == 422
    # Recargar el paquete no duplica
    paquete = (RAIZ / "app/data/oficial/02_carga_motor_dinamico_v3.xlsx").read_bytes()
    r = interno.c.post("/api/aranceles/oficial/importar", headers=interno.h,
                       files={"archivo": ("02.xlsx", io.BytesIO(paquete), "application/octet-stream")}).json()
    assert r["hojas"]["Attributes"]["creados"] == 0 and r["hojas"]["Attribute_Options"]["creados"] == 0 and not r["errores"]


def test_reglas_del_sistema_y_seleccion_nacional(interno):
    r = interno.get("/aranceles/reglas", params={"tipo": "HARD_CONSTRAINT"}).json()
    sis = {x["codigo"]: x for x in r["items"]}
    assert {"R-SYS-001", "R-SYS-006", "R-SYS-009"} <= set(sis)
    assert [(c["campo"], c["valor"]) for c in sis["R-SYS-001"]["condiciones"]] == [("chapter.active", True), ("chapter.classification_enabled", True)]
    assert r["por_tipo"]["NATIONAL_SELECT"] > 50 and r["por_tipo"]["REVIEW_GATE"] == 1
    # Las condiciones de los códigos nacionales son reglas NATIONAL_SELECT
    nac = interno.get("/aranceles/reglas", params={"tipo": "NATIONAL_SELECT", "pais": "SV", "q": "genero"}).json()["items"]
    assert nac and all(x["pais"] == "SV" and x["inciso"]["codigo"].startswith(x["codigo_ambito"]) for x in nac)
    assert any(c["campo"] == "genero" for c in nac[0]["condiciones"]) and nac[0]["cond_txt"]
    # Búsqueda por código nacional
    cod = nac[0]["inciso"]["codigo"]
    assert any(x["id"] == nac[0]["id"] for x in interno.get("/aranceles/reglas", params={"q": cod[:8]}).json()["items"])


def test_editar_regla_nacional_llega_al_motor(interno):
    # Un código con condiciones creado desde Aranceles queda como regla
    r = interno.post("/aranceles/codigos", {"pais": "SV", "codigo": "6404.19.90.99", "descripcion": "Prueba regla",
                                            "cond": {"genero": "F", "cifMax": 15}, "prio": 3})
    assert r.status_code == 200, r.text
    iid = r.json()["id"]
    regla = next(x for x in interno.get("/aranceles/reglas", params={"q": "6404199099"}).json()["items"] if x["inciso"]["id"] == iid)
    assert regla["prioridad"] == 3 and {(c["campo"], c["operador"], c["valor"]) for c in regla["condiciones"]} == {
        ("genero", "EQUAL", "F"), ("valorCIF", "LTE", 15)}
    # Editar las condiciones de la regla cambia lo que recibe la ficha
    r = interno.patch(f"/aranceles/reglas/{regla['id']}", {"condiciones": [
        {"campo": "genero", "operador": "IN", "valor": ["F", "U"]}, {"campo": "valorCIF", "operador": "GT", "valor": 10}]})
    assert r.status_code == 200, r.text
    ctx = next(x for x in interno.get("/clasificacion/contexto").json()["incisos"] if x["id"] == iid)
    assert ctx["cond"] == {"genero": ["F", "U"], "cifMin": 10} and ctx["prio"] == 3
    # Validaciones: en selección nacional solo los operadores del motor y un solo grupo
    assert interno.patch(f"/aranceles/reglas/{regla['id']}", {"condiciones": [{"campo": "genero", "operador": "NOT_EQUAL", "valor": "M"}]}).status_code == 422
    assert interno.patch(f"/aranceles/reglas/{regla['id']}", {"condiciones": [{"campo": "genero", "operador": "IN", "valor": "M"}]}).status_code == 422
    assert interno.patch(f"/aranceles/reglas/{regla['id']}", {"condiciones": [
        {"grupo": 1, "campo": "genero", "valor": "M"}, {"grupo": 2, "campo": "genero", "valor": "F"}]}).status_code == 422
    # Apagar la regla apaga su código
    interno.patch(f"/aranceles/reglas/{regla['id']}", {"activo": False})
    assert not any(x["id"] == iid for x in interno.get("/clasificacion/contexto").json()["incisos"])
    # Quitar condiciones y prioridad desde el código deja el código sin regla
    interno.put(f"/aranceles/codigos/{iid}", {"pais": "SV", "codigo": "6404.19.90.99", "cond": {}, "prio": 0, "activo": True})
    assert not [x for x in interno.get("/aranceles/reglas", params={"q": "6404199099"}).json()["items"] if x.get("inciso", {}).get("id") == iid]


def _libro(hojas: dict) -> io.BytesIO:
    wb = Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for f in filas:
            ws.append(f)
    b = io.BytesIO()
    wb.save(b)
    return io.BytesIO(b.getvalue())


def _cargar(api, hojas):
    r = api.c.post("/api/aranceles/oficial/importar", headers=api.h,
                   files={"archivo": ("p.xlsx", _libro(hojas), "application/octet-stream")})
    assert r.status_code == 200, r.text
    return r.json()


def test_paquete_nacional_codigos_regulaciones_impuestos(interno):
    # El paquete 03 incluido trae el mapa de fuentes por país
    paises = {p["iso"]: p for p in interno.get("/aranceles/paises").json()}
    assert paises["CR"]["modelo_arancel"]
    enc_cod = ["National code ID", "Country", "Version", "Base HS6", "Base SAC code", "Precision/additional code", "Full/display code",
               "Parent node ID", "Official description", "DAI %", "Active", "Status", "Valid from", "Valid to", "Source ID", "Source URL", "Internal note"]
    enc_reg = ["Regulation ID", "Country", "Version", "Scope type", "Code/pattern", "Regulation type", "Requirement name", "Authority",
               "Permit/license code", "Mandatory", "Condition JSON", "Legal basis", "Active", "Valid from", "Valid to", "Source ID", "Source URL", "Notes"]
    enc_imp = ["Tax rule ID", "Country", "Version", "Code/pattern", "Tax type", "Rate %", "Basis", "Threshold from", "Threshold to",
               "Formula / rule", "Active", "Valid from", "Valid to", "Source ID", "Source URL", "Legal basis / notes"]
    r = _cargar(interno, {
        "Versions": [["Version ID", "Dataset", "Version label", "Status", "Valid from", "Valid to", "Source ID"],
                     ["CR-2026", "Costa Rica national tariff", "2026", "Published", "2026-01-01", None, "SRC-CR-ATENA"]],
        "National_Codes": [enc_cod,
                           ["CR-1", "CR", "CR-2026", "330499", "33049900", None, "3304.99.00.00.10", None, "Cremas de belleza", "14", "Yes", "Published", "2026-01-01", None, "SRC-CR-ATENA", None, None],
                           ["CR-2", "CR", "CR-2026", None, "33049900", None, "3304.99.00.00.10", None, "Duplicado", "14", "Yes", None, None, None, "SRC-CR-ATENA", None, None],
                           ["CR-3", "CR", "CR-2026", None, "33049900", None, "3305.10.00.00.00", None, "Otra base", "x", "Yes", None, None, None, None, None, None],
                           ["CR-4", "CR", "NO-EXISTE", None, None, None, "3304.99.00.00.20", None, "Sin versión", None, None, None, None, None, None, None, None],
                           ["CR-5", "CR", "CR-2026", None, None, None, "3304990", None, "Corto", None, None, None, None, None, None, None, None],
                           ["CR-6", "CR", "CR-2026", None, None, None, "9999.99.00.00", None, "Sin padre", None, None, None, None, None, None, None, None]],
        "Regulations": [enc_reg,
                        ["REG-CR-1", "CR", None, "HEADING", "3304*", "SANITARY", "Registro sanitario de cosméticos", "Ministerio de Salud", "RS",
                         "Yes", '{"uso": "cosmetico"}', "Reglamento de cosméticos", "Yes", None, None, "SRC-CR-ATENA", None, None],
                        ["REG-CR-2", "CR", None, None, "", "PERMIT", "Sin patrón", None, None, None, None, None, None, None, None, None, None, None],
                        ["REG-CR-3", "CR", None, None, "33", "PERMIT", "JSON malo", None, None, None, "{malo", None, None, None, None, None, None, None]],
        "Taxes": [enc_imp,
                  ["TAX-CR-SEL", "CR", None, "3304", "SELECTIVO", "10", "CIF + DAI", None, None, None, "Yes", None, None, None, None, "Ley de impuesto selectivo de consumo"],
                  ["TAX-CR-X", "CR", None, "3304", "IVA", "13", None, None, None, None, None, None, None, None, None, None]],
    })
    assert r["hojas"]["National_Codes"]["creados"] == 1 and r["hojas"]["Regulations"]["creados"] == 1 and r["hojas"]["Taxes"]["creados"] == 1
    msgs = " | ".join(e["mensaje"] for e in r["errores"])
    for esperado in ("Duplicate country + version + code", "does not start with its base code", "Version NO-EXISTE does not exist",
                     "8 to 14 digits", "does not exist in the tariff tree", "needs a code or pattern", "not valid JSON", "official source or its legal basis"):
        assert esperado in msgs, esperado
    # El código oficial queda con versión, fuente, vigencia y código base
    cod = interno.get("/aranceles/codigos", params={"pais": "CR", "q": "330499000010"}).json()["items"][0]
    assert cod["dai"] == "14" and cod["descripcion"] == "Cremas de belleza"
    # Requisitos de ese código en Costa Rica: IVA general + selectivo + registro sanitario
    req = interno.get("/aranceles/requisitos", params={"pais": "CR", "codigo": "3304.99.00.00.10"}).json()
    tipos = {i["tipo"]: i for i in req["impuestos"]}
    assert tipos["IVA"]["tasa"] == 13 and tipos["SELECTIVO"]["tasa"] == 10
    assert [x["codigo"] for x in req["regulaciones"]] == ["REG-CR-1"] and req["regulaciones"][0]["condicion"] == {"uso": "cosmetico"}
    # Otro capítulo no lleva el registro sanitario
    assert not interno.get("/aranceles/requisitos", params={"pais": "CR", "codigo": "6404.19"}).json()["regulaciones"]
    # El árbol muestra impuestos y regulaciones por país
    sub = next(i for i in interno.get("/aranceles/arbol", params={"q": "3304.99"}).json()["items"] if i["codigo"] == "3304.99")
    cr = next(p for p in interno.get(f"/aranceles/arbol/{sub['id']}").json()["paises"] if p["iso"] == "CR")
    assert cr["regulaciones"] and {i["tipo"] for i in cr["impuestos"]} >= {"IVA", "SELECTIVO"}


def test_regulaciones_e_impuestos_crud(interno):
    r = interno.post("/aranceles/regulaciones", {"pais": "GT", "patron": "6404", "tipo": "labeling", "nombre": "Etiquetado de calzado",
                                                 "autoridad": "DIACO"})
    assert r.status_code == 200, r.text
    reg = r.json()
    assert reg["tipo"] == "LABELING" and reg["patron"] == "6404" and reg["codigo"].startswith("REG-GT-")
    assert interno.post("/aranceles/regulaciones", {"pais": "GT", "patron": "6", "tipo": "PERMIT", "nombre": "x"}).status_code == 422
    # Nunca se borra: se desactiva
    reg = interno.patch(f"/aranceles/regulaciones/{reg['id']}", {"activo": False}).json()
    assert not interno.get("/aranceles/requisitos", params={"pais": "GT", "codigo": "6404199000"}).json()["regulaciones"]
    assert any(x["id"] == reg["id"] for x in interno.get("/aranceles/regulaciones", params={"pais": "GT", "q": "etiquetado"}).json()["items"])
    imp = interno.post("/aranceles/impuestos", {"pais": "GT", "patron": "*", "tipo": "OTRO", "tasa": 1, "base_legal": "Prueba"}).json()
    assert imp["patron"] == "*" and imp["fuente"]
    # Impuesto general sembrado (demo): IVA de Guatemala
    assert any(x["tipo"] == "IVA" and x["tasa"] == 12 for x in interno.get("/aranceles/impuestos", params={"pais": "GT"}).json()["items"])


def test_longitud_de_codigo_configurable(interno):
    # Sin esquema configurado: 8 a 14 dígitos (no un número fijo)
    r = interno.post("/aranceles/codigos", {"pais": "SV", "codigo": "6404.19.90.00.01"})
    assert r.status_code == 200, r.text
    # Con esquema: solo las longitudes declaradas
    _cargar(interno, {"Countries": [["ISO", "Country", "National code length"], ["SV", "El Salvador", "10"]]})
    r = interno.post("/aranceles/codigos", {"pais": "SV", "codigo": "6404.19.90.00.02"})
    assert r.status_code == 422 and "10 digits" in r.json()["mensaje"]
    _cargar(interno, {"Countries": [["ISO", "Country", "National code length"], ["SV", "El Salvador", "CONFIGURABLE"]]})
