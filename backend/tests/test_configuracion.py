"""Todo lo que define una familia se configura desde el sistema y se valida:
una configuración inválida nunca llega al motor y el mensaje dice qué y dónde."""
import pytest


def _attr(api, **datos):
    r = api.post("/aranceles/atributos", datos)
    assert r.status_code == 200, r.text
    return r.json()


def _rechazo(r, texto):
    assert r.status_code == 422, r.text
    assert texto in r.json()["mensaje"], r.json()["mensaje"]


def test_attribute_behavior_is_validated(interno):
    a = _attr(interno, codigo="cfg_box", etiqueta="Has a lid", tipo_dato="boolean")
    url = f"/aranceles/atributos/{a['id']}"
    _rechazo(interno.patch(url, {"patrones": [{"re": "(lid"}]}), "is not valid")
    _rechazo(interno.patch(url, {"patrones": [{"re": "lid", "en": "nowhere"}]}), "«en» must be one of")
    _rechazo(interno.patch(url, {"patrones": [{"re": "lid", "cuando": [{"campo": "no_such", "operador": "EQUAL", "valor": 1}]}]}),
             "no_such is not an attribute")
    _rechazo(interno.patch(url, {"bloqueo": [{"condiciones": [{"campo": "estilo_calzado", "operador": "EQUAL", "valor": "no_option"}],
                                              "mensaje": "x"}]}), "no_option is not an option of estilo_calzado")
    _rechazo(interno.patch(url, {"texto_aduana": {"orden": 3}}), "give a phrase")
    _rechazo(interno.patch(url, {"alias": ["estilo_calzado"]}), "estilo_calzado is already an attribute")
    _rechazo(interno.patch(url, {"seccion": "nowhere"}), "The section must be one of")
    ok = interno.patch(url, {"patrones": [{"re": r"\b(lid|tapa)\b", "en": "todo", "prioridad": 3}],
                             "texto_aduana": {"frase": "CON TAPA", "orden": 60}, "alias": ["has_lid"]})
    assert ok.status_code == 200, ok.text
    d = interno.get(url).json()
    assert d["patrones"][0]["re"] == r"\b(lid|tapa)\b" and d["texto_aduana"]["frase"] == "CON TAPA" and d["alias"] == ["has_lid"]


def test_option_derivation_and_scope_are_validated(interno):
    s = _attr(interno, codigo="cfg_body_mat", etiqueta="Body material", tipo_dato="select")
    url = f"/aranceles/atributos/{s['id']}"
    for o in ("ceramica", "vidrio", "otro"):
        assert interno.post(f"{url}/opciones", {"codigo": o, "etiqueta": o.title()}).status_code == 200
    opc = {o["codigo"]: o for o in interno.get(url).json()["opciones"]}
    _rechazo(interno.patch(f"{url}/opciones/{opc['vidrio']['id']}", {"implica": {"cfg_body_mat": "otro"}}), "cannot imply its own attribute")
    _rechazo(interno.patch(f"{url}/opciones/{opc['vidrio']['id']}", {"implica": {"estilo_calzado": "nope"}}), "nope is not an option of estilo_calzado")
    _rechazo(interno.patch(url, {"derivacion": {"modo": "clase", "parte": "no_part"}}), "no_part is not a composition part")
    _rechazo(interno.patch(url, {"derivacion": {"modo": "clase", "parte": "material", "mapa": {"vidrio": "glass"}}}), "glass is not an option")
    _rechazo(interno.patch(url, {"derivacion": {"modo": "magic"}}), "the derivation mode must be one of")
    assert interno.patch(url, {"derivacion": {"modo": "clase", "parte": "material", "mapa": {"vidrio": "vidrio", "*": "otro"}}}).status_code == 200
    _rechazo(interno.post(f"{url}/ambitos", {"tipo_ambito": "CATEGORY", "codigo_ambito": "no_such_category"}), "Category no_such_category does not exist")
    _rechazo(interno.post(f"{url}/ambitos", {"tipo_ambito": "HEADING", "codigo_ambito": "69"}), "must have 4 digits")
    r = interno.post(f"{url}/ambitos", {"tipo_ambito": "CATEGORY", "codigo_ambito": "mochila"})
    amb = next(x for x in r.json()["ambitos"] if x["codigo_ambito"] == "mochila")
    _rechazo(interno.patch(f"{url}/ambitos/{amb['id']}", {"condicion": [{"campo": "ghost", "operador": "EXISTS"}]}), "ghost is not an attribute")


def test_categories_and_rules_are_validated(interno):
    _rechazo(interno.post("/aranceles/categorias", {"nombre": "Cfg mugs", "capitulos": ["691"]}), "These are not chapters")
    _rechazo(interno.post("/aranceles/categorias", {"nombre": "Cfg mugs", "patrones": [{"re": "(mug"}]}), "is not valid")
    _rechazo(interno.post("/aranceles/categorias", {"nombre": "Cfg mugs", "plantilla_aduana": {"material": "DE {no_attr}"}}), "no_attr is not an attribute")
    _rechazo(interno.post("/aranceles/categorias", {"nombre": "Cfg mugs", "plantilla_aduana": {"colour": "x"}}), "unknown keys colour")
    _rechazo(interno.post("/aranceles/reglas", {"tipo_ambito": "CATEGORY", "codigo_ambito": "no_cat", "tipo_regla": "SOFT_SIGNAL",
                                                "accion": {"tipo": "BOOST", "codigos": ["6912"]}}), "Category no_cat does not exist")
    _rechazo(interno.post("/aranceles/reglas", {"tipo_ambito": "SYSTEM", "tipo_regla": "SOFT_SIGNAL", "accion": {"tipo": "BOOST", "codigos": ["6912"]},
                                                "condiciones": [{"campo": "ghost_field", "operador": "EQUAL", "valor": 1}]}),
             "ghost_field is not an attribute")


def test_material_classes_are_configurable(interno):
    """Una clase de material nueva (cerámica) se reconoce en la composición, deriva
    la opción de un atributo y va con su palabra en la descripción aduanera."""
    from app.db import SessionLocal
    from app.services.ficha import Catalogo

    _rechazo(interno.post("/aranceles/materiales", {"nombre": "Ceramic", "palabras": "ceramica (porcelana"}), "is not valid")
    _rechazo(interno.post("/aranceles/materiales", {"nombre": "Cork 2", "palabras": "vidrio_x madera"}), "is not a word")
    r = interno.post("/aranceles/materiales", {"codigo": "ceramica", "nombre": "Ceramic",
                                               "palabras": "ceramica ceramic porcelanas? porcelain gres stoneware loza", "texto_aduana": "CERÁMICA"})
    assert r.status_code == 200, r.text
    _rechazo(interno.post("/aranceles/materiales", {"nombre": "Porcelain", "palabras": "porcelain"}), "already in another class")
    assert any(x["codigo"] == "vidrio" and x["origen"] == "MOTOR" for x in interno.get("/aranceles/materiales").json())
    with SessionLocal() as db:
        cat = Catalogo.desde_db(db)
        assert cat.lector.clase_mat("100% porcelain")["pred"] == "ceramica"
        assert not cat.lector.prep("100% porcelain")["desconocidas"]
        assert [f["m"] for f in cat.lector.filas("90% porcelain 10% steel")] == ["Porcelain", "Steel"]
        assert cat.vocabulario["ceramica"] == "CERÁMICA"


@pytest.mark.parametrize("hoja,fila,mensaje", [
    ("Attributes", ["cfg_pkg_flag", "Flag", "boolean", None, "No", "Yes", "CORE", None, None, "{not json"], "is not valid JSON"),
    ("Attributes", ["cfg_pkg_flag2", "Flag", "boolean", None, "No", "Yes", "CORE", None, None, '[{"re": "(x"}]'], "is not valid"),
])
def test_package_behavior_columns_are_validated(interno, hoja, fila, mensaje):
    from test_vocabulario import ATTRS, _rechazo as rechazo_paquete

    errores = rechazo_paquete(interno, {"Attributes": [ATTRS + ["Patterns JSON"], fila]})
    assert any(mensaje in e for e in errores), errores


def test_integrity_audit_reports_broken_configuration(interno):
    """Lo guardado antes (o tocado fuera de la pantalla) pasa por la misma
    validación en el auditor: una referencia rota se reporta, no rompe una ficha."""
    from app.db import SessionLocal
    from app.models import AtributoDef

    limpio = interno.get("/aranceles/oficial/integridad").json()
    assert next(c for c in limpio["checks"] if c["codigo"] == "CONFIG_INVALID")["total"] == 0
    a = _attr(interno, codigo="cfg_broken", etiqueta="Broken", tipo_dato="boolean")
    with SessionLocal() as db:
        x = db.get(AtributoDef, a["id"])
        x.patrones = [{"re": "(unclosed"}]
        x.derivacion = {"modo": "valor", "desde": "attribute_that_was_deleted", "mapa": {"*": True}}
        db.commit()
    c = next(c for c in interno.get("/aranceles/oficial/integridad").json()["checks"] if c["codigo"] == "CONFIG_INVALID")
    msgs = [h["mensaje"] for h in c["hallazgos"] if h["ref"] == "cfg_broken"]
    assert c["estado"] == "ERROR" and any("is not valid" in m for m in msgs) and any("attribute_that_was_deleted" in m for m in msgs)
    with SessionLocal() as db:
        x = db.get(AtributoDef, a["id"])
        x.patrones, x.derivacion, x.activo = [], None, False
        db.commit()
