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
