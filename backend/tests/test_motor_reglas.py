"""Paridad: el motor del servidor, con las reglas extraídas de motor.js
(data/motor_reglas.json), da el mismo código que la ficha del navegador.

Los casos los genera frontend/scripts/motor-reglas.mjs ejecutando motor.js
(uno por regla y uno por fibra en las reglas con mapa de subpartidas). La
prueba de node test_motor_atributos.py comprueba a su vez que el JSON sigue
al día con motor.js."""
import json

from app.db import SessionLocal
from app.models import ControlCapitulo, ReglaClasificacion
from app.services import motor_clasificacion, reglas
from sqlalchemy import select

DATOS = json.loads(reglas.DATOS_MOTOR.read_text(encoding="utf-8"))


def test_reglas_del_motor_sembradas(interno):
    with SessionLocal() as db:
        n = db.scalar(select(ReglaClasificacion.id).where(ReglaClasificacion.tipo_fuente == "MOTOR_JS").limit(1))
        assert n, "las reglas de la ficha no se sembraron"
        total = len(list(db.scalars(select(ReglaClasificacion).where(ReglaClasificacion.tipo_fuente == "MOTOR_JS",
                                                                    ReglaClasificacion.activo.is_(True)))))
        assert total == len(DATOS["reglas"])
        # Volver a cargar no cambia nada
        assert reglas.cargar_motor_js(db) == {"nuevas": 0, "actualizadas": 0, "editadas": 0, "retiradas": 0}
    r = interno.get("/aranceles/reglas", params={"q": "R-MJS-CHAQUETA"}).json()
    assert r["total"] > 10 and all(x["tipo_ambito"] == "CATEGORY" and x["codigo_ambito"] == "chaqueta" for x in r["items"])


def test_paridad_con_motor_js(interno):
    """Todos los casos: el servidor llega al mismo código que motor.js."""
    malos = []
    with SessionLocal() as db:
        habilitados = {c.capitulo for c in db.scalars(select(ControlCapitulo)) if c.activo and c.clasificacion and not c.archivado and not c.solo_manual}
        for caso in DATOS["casos"]:
            h, esperado = caso["hechos"], caso["codigo"]
            if esperado[:2] not in habilitados:
                continue  # capítulo apagado en la configuración: el servidor no lo propone (R-SYS-001)
            r = motor_clasificacion.clasificar(db, "", None, h["categoria"], h, paises=False, limite=50)
            cods = [c["codigo"] for c in r["candidatos"]]
            ok = (r["hs6"] == esperado and r["confianza"] == "high") if len(esperado) == 6 else (cods and all(c.startswith(esperado) for c in cods))
            if not ok:
                malos.append((h, esperado, cods[:5]))
    assert not malos, f"{len(malos)} casos sin paridad, p. ej. {malos[:3]}"


def test_regla_propia_manda_sobre_la_extraida(interno):
    """Las reglas de la ficha son datos: una regla propia de la categoría las
    corrige, y apagar la extraída deja de aplicarla."""
    base = {"categoria": "falda", "respuestas": {"tejido": "plano", "edad": "general", "fibra": "algodon"}, "paises": False}
    s = interno.post("/clasificacion/sesion", base).json()
    assert s["hs6"] == "620452" and s["confianza"] == "high"
    aplicada = next(t for t in s["reglas"] if t["regla"].startswith("R-MJS-FALDA") and t["resultado"] is True)
    assert aplicada["codigos"] == ["620452"]
    # Sin fibra: queda la partida (todas sus subpartidas) y la fibra es lo que discrimina
    s = interno.post("/clasificacion/sesion", {**base, "respuestas": {"tejido": "plano"}}).json()
    assert s["hs6"].startswith("6204") and all(c["codigo"].startswith("6204") for c in s["candidatos"]) and s["confianza"] != "high"
    # Regla propia de la categoría (después de las extraídas: prioridad menor) que la corrige
    r = interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "falda", "tipo_regla": "HARD_CONSTRAINT", "prioridad": 800,
                                            "condiciones": [{"campo": "fibra", "operador": "EQUAL", "valor": "algodon"}, {"campo": "tejido", "operador": "EQUAL", "valor": "plano"}],
                                            "accion": {"tipo": "RESTRICT", "codigos": ["620459"]}}).json()
    s = interno.post("/clasificacion/sesion", base).json()
    assert s["hs6"] == "620459"
    interno.patch(f"/aranceles/reglas/{r['id']}", {"activo": False})
    # Apagar la extraída: deja de restringir
    interno.patch(f"/aranceles/reglas/{next(x['id'] for x in interno.get('/aranceles/reglas', params={'q': aplicada['regla']}).json()['items'])}", {"activo": False})
    s = interno.post("/clasificacion/sesion", base).json()
    assert aplicada["regla"] not in {t["regla"] for t in s["reglas"] if t["resultado"] is True}
    interno.patch(f"/aranceles/reglas/{next(x['id'] for x in interno.get('/aranceles/reglas', params={'q': aplicada['regla']}).json()['items'])}", {"activo": True})
    # Editada, la carga no la pisa
    with SessionLocal() as db:
        x = db.scalar(select(ReglaClasificacion).where(ReglaClasificacion.codigo == aplicada["regla"]))
        assert reglas.cargar_motor_js(db)["editadas"] == 0
        x.condiciones[0].valor = ["general"]
        db.flush()
        assert reglas.cargar_motor_js(db)["editadas"] == 1
        db.rollback()
