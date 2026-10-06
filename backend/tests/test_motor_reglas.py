"""Paridad: el motor del servidor, con las reglas de la ficha
(data/motor_reglas.json), da el mismo código que daba el antiguo clasificador
del navegador. Los casos esperados (uno por regla y uno por fibra en las
reglas con mapa de subpartidas) quedaron fijos en ese archivo al retirarlo:
son la referencia de regresión."""
import json

from app.db import SessionLocal
from app.models import ControlCapitulo, ReglaClasificacion
from app.services import motor_clasificacion, reglas
from sqlalchemy import select

DATOS = json.loads(reglas.DATOS_MOTOR.read_text(encoding="utf-8"))


def test_reglas_del_motor_sembradas(interno):
    with SessionLocal() as db:
        n = db.scalar(select(ReglaClasificacion.id).where(ReglaClasificacion.tipo_fuente == "SHEET_RULES").limit(1))
        assert n, "las reglas de la ficha no se sembraron"
        total = len(list(db.scalars(select(ReglaClasificacion).where(ReglaClasificacion.tipo_fuente == "SHEET_RULES",
                                                                    ReglaClasificacion.activo.is_(True)))))
        assert total == len(DATOS["reglas"])
        # Volver a cargar no cambia nada
        assert reglas.cargar_reglas_ficha(db) == {"nuevas": 0, "actualizadas": 0, "editadas": 0, "retiradas": 0}
    r = interno.get("/aranceles/reglas", params={"q": "R-MJS-CHAQUETA"}).json()
    assert r["total"] > 10 and all(x["tipo_ambito"] == "CATEGORY" and x["codigo_ambito"] == "chaqueta" for x in r["items"])


def test_paridad_con_motor_js(interno):
    """Todos los casos posibles: el servidor llega al mismo código esperado.
    Los estados que la ficha nunca permite (p. ej. camiseta de tejido plano) los
    corrige el normalizador antes de las reglas: esos se omiten."""
    from app.services.ficha import Catalogo

    malos, probados = [], 0
    with SessionLocal() as db:
        cat = Catalogo.desde_db(db)
        habilitados = {c.capitulo for c in db.scalars(select(ControlCapitulo)) if c.activo and c.clasificacion and not c.archivado and not c.solo_manual}
        for caso in DATOS["casos"]:
            h, esperado = dict(caso["hechos"]), caso["codigo"]
            if esperado[:2] not in habilitados:
                continue  # capítulo apagado en la configuración: el servidor no lo propone (R-SYS-001)
            ficha = {k: v for k, v in h.items() if k != "categoria"}
            if "edad" in ficha:
                ficha["edadNac"] = "bebe" if ficha["edad"] == "bebe" else "adulto"
            s = cat.hechos_base(ficha, h["categoria"])
            cat.normalizar(s)
            if any(s.get(k) != v for k, v in ficha.items()):
                continue
            probados += 1
            r = motor_clasificacion.clasificar_producto(db, {"categoria": h["categoria"], "ficha": ficha, "detectar": False}, catalogo=cat,
                                                        paises=False, limite=50)
            cods = [c["codigo"] for c in r["candidatos"]]
            ok = (r["hs6"] == esperado and r["confianza"] == "high") if len(esperado) == 6 else (cods and all(c.startswith(esperado) for c in cods))
            if not ok:
                malos.append((h, esperado, cods[:5]))
    assert probados > 1000 and not malos, f"{len(malos)} de {probados} casos sin paridad, p. ej. {malos[:3]}"


def test_precedencia_de_reglas(interno):
    """Mayor prioridad = mayor precedencia; una regla de menor prioridad que
    choca queda superada (no se aplica, y la evidencia dice por qué); una
    regla legal es un límite que ninguna otra viola, tenga la prioridad que tenga."""
    base = {"categoria": "falda", "ficha": {"tejido": "plano", "edadNac": "adulto", "comp": {"exterior": "100% cotton"}}, "paises": False}
    s = interno.post("/clasificacion/sesion", base).json()
    assert s["hs6"] == "620452" and s["confianza"] == "high"
    aplicada = next(t for t in s["reglas"] if t["regla"].startswith("R-MJS-FALDA") and t.get("aplicada"))
    assert aplicada["codigos"] == ["620452"] and aplicada["foto"]["condiciones"] and aplicada["firma"]
    cond = [{"campo": "fibra", "operador": "EQUAL", "valor": "algodon"}, {"campo": "tejido", "operador": "EQUAL", "valor": "plano"}]
    # Propia de menor prioridad (800 < 900): queda superada
    r = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "falda", "tipo_regla": "HARD_CONSTRAINT", "prioridad": 800,
                                            "condiciones": cond, "accion": {"tipo": "RESTRICT", "codigos": ["620459"]}}).json()
    s = interno.post("/clasificacion/sesion", base).json()
    t = next(t for t in s["reglas"] if t["regla"] == r["codigo"])
    assert s["hs6"] == "620452" and t["aplicada"] is False and t["motivo"].startswith("overridden_by:R-MJS-FALDA")
    # Con mayor prioridad (950) manda
    interno.patch(f"/aranceles/reglas/{r['id']}", {"prioridad": 950})
    s = interno.post("/clasificacion/sesion", base).json()
    assert s["hs6"] == "620459"
    assert next(t for t in s["reglas"] if t["regla"] == r["codigo"])["revision"] == 2  # cada cambio sube la revisión
    # Una regla legal (con su nota) es un límite: la propia de prioridad 950 no la puede violar
    nota = next(n for n in interno.get("/aranceles/notas", params={"capitulo": "62"}).json()["items"] if n["oficial"])
    # Una guía del clasificador (resumen propio) no funda una regla legal
    guia = next(n for n in interno.get("/aranceles/notas").json()["items"] if n["tipo_fuente"] == "CLASSIFIER_GUIDANCE")
    r_guia = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "falda", "tipo_regla": "HARD_CONSTRAINT",
                                                "tipo_fuente": "LEGAL_NOTE", "nota_id": guia["id"], "condiciones": cond,
                                                "accion": {"tipo": "RESTRICT", "codigos": ["620452"]}})
    assert r_guia.status_code == 422 and r_guia.json()["codigo"] == "nota_no_oficial"
    legal = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "falda", "tipo_regla": "HARD_CONSTRAINT", "prioridad": 10,
                                                "tipo_fuente": "LEGAL_NOTE", "nota_id": nota["id"], "condiciones": cond,
                                                "accion": {"tipo": "RESTRICT", "codigos": ["620452"]}}).json()
    assert legal["capa"] == "LEGAL"
    s = interno.post("/clasificacion/sesion", base).json()
    t = next(t for t in s["reglas"] if t["regla"] == r["codigo"])
    assert s["hs6"] == "620452" and t["aplicada"] is False and t["motivo"] == "blocked_by_legal"
    assert any(n["id"] == nota["id"] for n in s["evidencia"]["notas"])
    # Sin nota no hay regla legal
    sin = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "falda", "tipo_fuente": "LEGAL_NOTE",
                                              "accion": {"tipo": "RESTRICT", "codigos": ["6204"]}})
    assert sin.status_code == 422
    for x in (r, legal):
        interno.patch(f"/aranceles/reglas/{x['id']}", {"activo": False})
    # Apagar la extraída: deja de restringir
    rid = next(x["id"] for x in interno.get("/aranceles/reglas", params={"q": aplicada["regla"]}).json()["items"])
    interno.patch(f"/aranceles/reglas/{rid}", {"activo": False})
    s = interno.post("/clasificacion/sesion", base).json()
    assert aplicada["regla"] not in {t["regla"] for t in s["reglas"] if t.get("aplicada")}
    interno.patch(f"/aranceles/reglas/{rid}", {"activo": True})
    # Editada, la carga no la pisa
    with SessionLocal() as db:
        x = db.scalar(select(ReglaClasificacion).where(ReglaClasificacion.codigo == aplicada["regla"]))
        assert reglas.cargar_reglas_ficha(db)["editadas"] == 0
        x.condiciones[0].valor = ["general"]
        db.flush()
        assert reglas.cargar_reglas_ficha(db)["editadas"] == 1
        db.rollback()


def test_codigos_de_reglas_se_validan_contra_el_arbol(interno):
    r = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "falda", "accion": {"tipo": "RESTRICT", "codigos": ["999999"]}})
    assert r.status_code == 422 and "999999" in r.json()["mensaje"]
    r = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "falda", "tipo_regla": "SOFT_SIGNAL",
                                            "accion": {"tipo": "BOOST", "codigos": ["6204", "620452"]}})
    assert r.status_code == 200, r.text
    interno.patch(f"/aranceles/reglas/{r.json()['id']}", {"activo": False})
