"""Familias por configuración: químicos y materias primas con sus reglas, y una
familia nueva (vajilla) armada solo con un paquete Excel, sin tocar código."""
import json

from sqlalchemy import select
from test_oficial import _cargar
from test_vocabulario import ATTRS, CONDS, REGLAS

from app.core.db import SessionLocal
from app.modelos import ReglaClasificacion


def _sesion(api, **e):
    r = api.post("/clasificacion/sesion", {"paises": False, **e})
    assert r.status_code == 200, r.text
    return r.json()


def test_family_rules_point_to_codes_of_the_tariff_in_force(interno):
    from app.modulos.clasificacion.motor_clasificacion import codigos_invalidos
    from app.modulos.clasificacion.semilla_familias import semilla

    reglas = semilla()["reglas"]
    with SessionLocal() as db:
        malos = {r["codigo"]: codigos_invalidos(db, r["accion"].get("codigos") or []) for r in reglas}
        assert not {k: v for k, v in malos.items() if v}
        cargadas = {r.codigo for r in db.scalars(select(ReglaClasificacion).where(ReglaClasificacion.codigo.like("R-NE-%")))}
    assert cargadas == {r["codigo"] for r in reglas}


def test_chemicals_and_raw_materials_are_decided_by_rules(interno):
    s = _sesion(interno, nombre="Acido acetico glacial", categoria="quimico_organico", ficha={"compuesto_definido": True, "grupo_organico": "acido"})
    assert s["hs6"].startswith("2915") and any(t["regla"] == "R-NE-QUI-ORG-ACIDO" and t["aplicada"] for t in s["reglas"])
    s = _sesion(interno, nombre="Polyethylene pellets", categoria="resina_plastica", ficha={"polimero": "polietileno"})
    assert s["hs6"].startswith("3901") and any(t["regla"] == "R-NE-MP-RESINA-POLIETILENO" and t["aplicada"] for t in s["reglas"])
    s = _sesion(interno, nombre="Finished cow leather", categoria="cuero", ficha={"animal": "bovino", "estado_cuero": "terminado"})
    assert s["hs6"].startswith("4107")
    s = _sesion(interno, nombre="PVC coated polyester fabric", categoria="tela_recubierta",
                ficha={"soporte": "tejido", "recubrimiento": "pvc", "comp": {"material": "100% polyester"}})
    assert s["hs6"] == "590310"
    s = _sesion(interno, nombre="Disperse dye", categoria="colorante", ficha={"clase_colorante": "dispersos"})
    assert s["hs6"] == "320411" and s["confianza"] == "high"
    # Sin el dato que decide, la regla lo pregunta
    s = _sesion(interno, nombre="Dye powder", categoria="colorante")
    assert any(q["codigo"] == "clase_colorante" for q in s["preguntas"][:3]) and s["requiere_revision"]


def test_new_family_only_with_configuration(interno):
    """Vajilla: dominio, clase de material «cerámica», parte de la composición,
    atributo derivado, categoría con su detección y descripción aduanera, y una
    regla con su acción. Todo en un paquete; el motor lo clasifica tal cual."""
    attrs_cols = ATTRS + ["Section", "Informative", "Default value", "Aliases", "Derivation JSON"]
    deriv = json.dumps({"modo": "clase", "parte": "cuerpo", "mapa": {"ceramica": "ceramica", "vidrio": "vidrio", "plastico": "plastico"}})
    plantilla = json.dumps({"nombre": "TAZA", "material": "DE {clase}", "clase": ["cuerpo"], "comercial": "TAZA"})
    r = _cargar(interno, {
        "Domains": [["Domain code", "Label", "Description", "Active", "Default mode"], ["HOUSEWARES", "Housewares", "Tableware and kitchenware", "Yes", "AUTO"]],
        "Material_Classes": [["Class code", "Name", "Words", "Customs word", "Active"],
                             ["ceramica", "Ceramic", "ceramica ceramic porcelanas? porcelain gres stoneware loza earthenware", "CERÁMICA", "Yes"]],
        "Categories": [["Category code", "Name", "Domain", "Short name", "Customs name", "Chapters", "Patterns JSON", "Customs template JSON", "Active"],
                       ["taza", "Mug or cup", "HOUSEWARES", "Mug", "TAZA", "69, 70, 39", json.dumps([{"re": r"\b(mugs?|tazas?)\b", "prioridad": 5}]),
                        plantilla, "Yes"]],
        "Attributes": [attrs_cols,
                       ["comp.cuerpo", "Body", "composition", None, "No", "Yes", "HOUSEWARES", None, None, "composicion", None, None, None, None],
                       ["material_taza", "Body material", "select", None, "No", "Yes", "HOUSEWARES", None, None, "derivado", None, None, None, deriv]],
        "Attribute_Options": [["Attribute code", "Option code", "Label", "Aliases / synonyms", "Sort order", "Active"],
                              ["material_taza", "ceramica", "Ceramic", None, 10, "Yes"], ["material_taza", "vidrio", "Glass", None, 20, "Yes"],
                              ["material_taza", "plastico", "Plastic", None, 30, "Yes"]],
        "Attribute_Scope": [["Attribute code", "Scope type", "Scope code", "Mode", "Priority", "Condition / dependency", "Active"],
                            ["comp.cuerpo", "CATEGORY", "taza", "REQUIRE", 900, None, "Yes"],
                            ["material_taza", "CATEGORY", "taza", "SHOW", 800, None, "Yes"]],
        "Classification_Rules": [REGLAS + ["Action", "Codes", "By attribute", "Code map JSON"],
                                 ["R-HW-001", "CATEGORY", "taza", "HARD_CONSTRAINT", 600, "SHEET_RULES", "HOUSEWARES", "Mug by body material",
                                  "Yes", "No", "RESTRICT", None, "material_taza", json.dumps({"ceramica": "691200", "vidrio": "701337", "plastico": "392410"})]],
        "Rule_Conditions": [CONDS, ["R-HW-001", 1, "material_taza", "EXISTS", None, None, "No"]],
    })
    assert not r["errores"], r["errores"]
    s = _sesion(interno, nombre="Coffee mug 12 oz", ficha={"comp": {"cuerpo": "100% stoneware"}})
    assert s["categoria"]["codigo"] == "taza" and s["dominio"] == "HOUSEWARES"
    assert s["hechos"]["material_taza"] == "ceramica"
    assert s["hs6"] == "691200" and s["confianza"] == "high", (s["hs6"], s["revision_por"])
    assert s["descripciones"]["aduana"].startswith("TAZA DE CERÁMICA")
    assert not [a for a in s["alertas"] if "do not recognize" in a["msg"]]
    s = _sesion(interno, nombre="Glass mug", ficha={"comp": {"cuerpo": "100% glass"}})
    assert s["hs6"] == "701337"
    # Un paquete con una acción hacia un código que no existe no se publica
    r = interno.c.post("/api/aranceles/oficial/importar", headers=interno.h, files={"archivo": ("p.xlsx", __import__("test_oficial")._libro({
        "Classification_Rules": [REGLAS + ["Action", "Codes"], ["R-HW-002", "CATEGORY", "taza", "HARD_CONSTRAINT", 600, "SHEET_RULES", "HW", "x", "Yes", "No",
                                                            "RESTRICT", "999999"]]}), "application/octet-stream")})
    assert r.status_code == 422 and any("do not exist" in e["mensaje"] for e in r.json()["detalle"]), r.text
