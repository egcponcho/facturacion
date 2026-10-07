"""Búsqueda en el texto oficial: raíces de palabras, vocabulario de búsqueda
configurable (inglés → español) y, como el texto nunca confirma un código, un
candidato que solo sale del texto queda siempre con confianza baja y revisión."""


def _sesion(api, **e):
    r = api.post("/clasificacion/sesion", {"paises": False, **e})
    assert r.status_code == 200, r.text
    return r.json()


def test_text_only_is_low_confidence_and_points_to_manual_chapters(interno):
    s = _sesion(interno, nombre="Cordless drill 18V")
    assert s["confianza"] == "low" and s["requiere_revision"]
    assert any("chapter 84" in a["msg"] and "by hand" in a["msg"] for a in s["alertas"]), s["alertas"]
    # Con reglas de una familia configurada la confianza sí puede ser alta
    s = _sesion(interno, nombre="Running shoes mesh upper rubber sole")
    assert s["categoria"]["codigo"] == "calzado" and s["confianza"] == "high"


def test_word_stems_match_the_official_text(interno):
    """«lámpara» encuentra «lámparas», y una palabra en inglés del vocabulario de
    base («lamp») encuentra lo mismo que en español."""
    es = _sesion(interno, nombre="Lámpara de escritorio")
    en = _sesion(interno, nombre="Desk lamp")
    assert es["candidatos"] and en["candidatos"]
    assert {c["codigo"] for c in es["candidatos"][:3]} & {c["codigo"] for c in en["candidatos"][:3]}


def test_search_vocabulary_is_configurable(interno):
    assert not _sesion(interno, nombre="Gizmoflask")["candidatos"]
    r = interno.post("/aranceles/busqueda", {"palabra": "Gizmoflask", "equivale": "botella termo"})
    assert r.status_code == 200, r.text
    assert r.json()["palabra"] == "gizmoflask"
    s = _sesion(interno, nombre="Gizmoflask")
    assert s["candidatos"] and "gizmoflask" in s["candidatos"][0]["terminos"]
    assert interno.post("/aranceles/busqueda", {"palabra": "gizmoflask", "equivale": "x y z"}).status_code == 422
    assert interno.post("/aranceles/busqueda", {"palabra": "other", "equivale": ""}).status_code == 422
    assert any(x["palabra"] == "drill" and x["origen"] == "MOTOR" for x in interno.get("/aranceles/busqueda").json())
