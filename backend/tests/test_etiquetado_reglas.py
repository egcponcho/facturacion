"""Motor de reglas de etiquetado: condiciones declarativas sobre los datos,
prioridad numérica, vigencia, contexto, conflictos (nunca se elige al azar),
predeterminada, elección del usuario, prueba con explicación (con una regla
en borrador), subfamilias que heredan reglas y campos obligatorios, y una
OC con diseños distintos por línea."""
from datetime import date, timedelta

import pytest

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion

TEXTO = [{"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 3, "w": 70, "h": 8, "estilo": {"tam": 10}}]


def _aprobada(interno, admin, nombre, modalidad="OC_ARTICULO", elementos=None, variables=None):
    r = interno.post("/etiquetas/plantillas", {"nombre": nombre, "modalidad": modalidad,
                                               "diseno": {"ancho": 80, "alto": 30, "elementos": elementos or TEXTO,
                                                          "variables": variables or []}})
    assert r.status_code == 200, r.text
    v = r.json()["versiones"][0]
    assert interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {}).status_code == 200
    assert admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {}).status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def oc(interno):
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        r = interno.get(f"/etiquetas/oc/{o['id']}").json()
        lineas = [x for x in r["lineas"] if x["articulo_id"] and not x["bloqueada"]]
        if len(lineas) >= 2 and len({x["articulo_id"] for x in lineas}) >= 2:
            return {**r, "lineas": lineas}
    pytest.skip("no PO with two different items")


@pytest.fixture
def reglas_creadas(interno):
    ids = []
    yield ids
    for i in ids:
        interno.c.delete(f"/api/etiquetas/asignaciones/{i}", headers=interno.h)


def _regla(interno, ids, **datos):
    r = interno.post("/etiquetas/asignaciones", datos)
    assert r.status_code == 200, r.text
    ids.append(r.json()["id"])
    return r.json()


def _sku(articulo_id):
    from app.modelos import Articulo

    with SessionLocal() as db, en_organizacion(1):
        return db.get(Articulo, articulo_id).sku


def _plan(interno, oc, **extra):
    r = interno.post("/etiquetas/plan", {"oc_id": oc["oc"]["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA",
                                         "posiciones": [x["id"] for x in oc["lineas"][:2]], **extra})
    assert r.status_code == 200, r.text
    return {g["posicion_id"]: g for g in r.json()["grupos"]}


def test_condiciones_prioridad_vigencia_contexto_y_mezcla_de_disenos(interno, admin, oc, reglas_creadas):
    l1, l2 = oc["lineas"][0], oc["lineas"][1]
    sku1 = _sku(l1["articulo_id"])
    p1 = _aprobada(interno, admin, "Rules design one")
    p2 = _aprobada(interno, admin, "Rules design two")
    a = _regla(interno, reglas_creadas, plantilla_id=p1["id"], ambito="REGLA", nombre="By SKU", prioridad=900,
               condiciones=[{"campo": "articulo.sku", "op": "en", "valor": [sku1, "OTHER"]}])
    assert a["prioridad"] == 900 and a["condiciones"][0]["valor"] == [sku1, "OTHER"]
    b = _regla(interno, reglas_creadas, plantilla_id=p2["id"], ambito="REGLA", nombre="By PO line", prioridad=900,
               condiciones=[{"campo": "linea.posicion", "op": "igual", "valor": l2["posicion"]}])
    # Una OC con dos diseños: cada línea toma el de su regla, con la regla y el motivo
    g = _plan(interno, oc)
    assert g[l1["id"]]["plantilla"] == "Rules design one" and g[l1["id"]]["regla_id"] == a["id"]
    assert g[l2["id"]]["plantilla"] == "Rules design two" and g[l2["id"]]["regla_id"] == b["id"]
    assert "By SKU" in g[l1["id"]]["motivo"] and "900" in g[l1["id"]]["motivo"]

    # Vigencia: desde mañana la regla de la línea no aplica (sale otro diseño o ninguno, nunca ese)
    manana = (date.today() + timedelta(days=1)).isoformat()
    r = interno.patch(f"/etiquetas/asignaciones/{b['id']}", {"vigente_desde": manana, "version": b["version"]})
    assert r.status_code == 200, r.text
    assert _plan(interno, oc)[l2["id"]]["plantilla"] != "Rules design two"
    # Concurrencia: con la versión vieja no se pisa el cambio de otro
    assert interno.patch(f"/etiquetas/asignaciones/{b['id']}", {"prioridad": 1, "version": b["version"]}).status_code == 409
    # Contexto: una regla solo para bultos no aplica al etiquetar por línea
    r = interno.patch(f"/etiquetas/asignaciones/{b['id']}", {"vigente_desde": None, "contexto": {"unidades": ["BULTO"]},
                                                             "version": b["version"] + 1})
    assert r.status_code == 200, r.text
    assert _plan(interno, oc)[l2["id"]]["plantilla"] != "Rules design two"

    # Condiciones inválidas: campo o operador desconocido, valores mal formados (nunca código)
    malas = [{"campo": "no.existe", "op": "igual", "valor": "x"}, {"campo": "articulo.sku", "op": "eval", "valor": "1"},
             {"campo": "linea.cantidad", "op": "mayor", "valor": "mucho"}, {"campo": "articulo.sku", "op": "en", "valor": []},
             {"campo": "articulo.sku", "op": "coincide", "valor": "("},
             # Patrones que hacen retroceder sin fin al motor de expresiones regulares (ReDoS)
             {"campo": "articulo.sku", "op": "coincide", "valor": "(a+)+$"},
             {"campo": "articulo.sku", "op": "coincide", "valor": "(a|aa)*b"},
             {"campo": "articulo.sku", "op": "coincide", "valor": "(a)\\1"},
             {"campo": "articulo.sku", "op": "coincide", "valor": "(?=a)a"},
             {"campo": "articulo.sku", "op": "coincide", "valor": "A" * 101}]
    for c in malas:
        r = interno.post("/etiquetas/asignaciones", {"plantilla_id": p1["id"], "ambito": "REGLA", "condiciones": [c]})
        assert r.status_code == 422, (c, r.text)
    # Sin destino ni condiciones no es una regla
    assert interno.post("/etiquetas/asignaciones", {"plantilla_id": p1["id"], "ambito": "REGLA"}).status_code == 422


def test_empate_es_conflicto_predeterminada_y_eleccion_del_usuario(interno, admin, oc, reglas_creadas):
    l1 = oc["lineas"][0]
    sku1 = _sku(l1["articulo_id"])
    p1 = _aprobada(interno, admin, "Tie design one")
    p2 = _aprobada(interno, admin, "Tie design two")
    a = _regla(interno, reglas_creadas, plantilla_id=p1["id"], ambito="REGLA", nombre="Tie A", prioridad=950,
               condiciones=[{"campo": "articulo.sku", "op": "igual", "valor": sku1}])
    b = _regla(interno, reglas_creadas, plantilla_id=p2["id"], ambito="REGLA", nombre="Tie B", prioridad=950,
               condiciones=[{"campo": "articulo.sku", "op": "empieza", "valor": sku1[:3]}])
    # Al guardar se avisa del conflicto
    assert any({x["id"] for x in c["reglas"]} == {a["id"], b["id"]} for c in b["conflictos"])
    conflictos = interno.get("/etiquetas/reglas/conflictos").json()
    par = [c for c in conflictos if {x["id"] for x in c["reglas"]} == {a["id"], b["id"]}]
    assert par and par[0]["nivel"] == "error"
    # Con la misma prioridad y diseños distintos no se elige: error y las candidatas
    g = _plan(interno, oc)[l1["id"]]
    assert g["plantilla_id"] is None and {c["plantilla"] for c in g["candidatas"]} == {"Tie design one", "Tie design two"}
    assert any(p["codigo"] == "elegir_plantilla" and p["categoria"] == "conflicto" for p in g["problemas"])
    # El usuario elige para ese registro
    g = _plan(interno, oc, elegidas={f"p{l1['id']}": p2["id"]})[l1["id"]]
    assert g["plantilla"] == "Tie design two"
    # Una predeterminada resuelve el empate (y el conflicto pasa a aviso)
    interno.patch(f"/etiquetas/asignaciones/{a['id']}", {"predeterminada": True})
    assert _plan(interno, oc)[l1["id"]]["plantilla"] == "Tie design one"
    par = [c for c in interno.get("/etiquetas/reglas/conflictos").json() if {x["id"] for x in c["reglas"]} == {a["id"], b["id"]}]
    assert par[0]["nivel"] == "advertencia"
    # Condiciones excluyentes no son conflicto
    interno.patch(f"/etiquetas/asignaciones/{b['id']}", {"condiciones": [{"campo": "articulo.sku", "op": "igual", "valor": "ZZZ"}]})
    assert not [c for c in interno.get("/etiquetas/reglas/conflictos").json() if {x["id"] for x in c["reglas"]} == {a["id"], b["id"]}]


def test_probar_explica_regla_por_regla_y_con_borrador(interno, admin, oc, reglas_creadas):
    l1 = oc["lineas"][0]
    sku1 = _sku(l1["articulo_id"])
    p1 = _aprobada(interno, admin, "Probe design one")
    p2 = _aprobada(interno, admin, "Probe design two")
    a = _regla(interno, reglas_creadas, plantilla_id=p1["id"], ambito="REGLA", nombre="Probe big lines", prioridad=970,
               condiciones=[{"campo": "linea.cantidad", "op": "mayor", "valor": 0}, {"campo": "articulo.sku", "op": "igual", "valor": sku1}])
    r = interno.post("/etiquetas/reglas/probar", {"modalidad": "OC_ARTICULO", "posicion_id": l1["id"]})
    assert r.status_code == 200, r.text
    x = r.json()
    assert x["plantilla"] == "Probe design one" and x["regla_id"] == a["id"]
    mia = next(e for e in x["explicacion"] if e["regla_id"] == a["id"])
    assert mia["resultado"] == "aplica" and mia["elegida"] and all(d["cumple"] for d in mia["detalle"])
    assert {d["campo"] for d in mia["detalle"]} == {"linea.cantidad", "articulo.sku"}
    # Con valores de muestra la condición deja de cumplirse y se explica cuál falló
    x = interno.post("/etiquetas/reglas/probar", {"modalidad": "OC_ARTICULO", "posicion_id": l1["id"],
                                                  "valores": {"linea.cantidad": 0}}).json()
    mia = next(e for e in x["explicacion"] if e["regla_id"] == a["id"])
    assert mia["resultado"] == "condiciones" and [d["cumple"] for d in mia["detalle"]] == [False, True]
    # Una regla en borrador (sin guardar) de mayor prioridad se prueba antes de crearla
    x = interno.post("/etiquetas/reglas/probar", {"modalidad": "OC_ARTICULO", "posicion_id": l1["id"],
                                                  "regla": {"plantilla_id": p2["id"], "ambito": "REGLA", "prioridad": 980,
                                                            "nombre": "Draft",
                                                            "condiciones": [{"campo": "articulo.sku", "op": "existe"}]}}).json()
    assert x["plantilla"] == "Probe design two" and x["regla"] == "Draft" and x["regla_id"] is None
    # En una fecha fuera de la vigencia no aplica
    interno.patch(f"/etiquetas/asignaciones/{a['id']}", {"vigente_hasta": date.today().isoformat()})
    x = interno.post("/etiquetas/reglas/probar", {"modalidad": "OC_ARTICULO", "posicion_id": l1["id"],
                                                  "fecha": (date.today() + timedelta(days=5)).isoformat()}).json()
    assert next(e for e in x["explicacion"] if e["regla_id"] == a["id"])["resultado"] == "fuera_de_vigencia"


def test_subfamilias_heredan_reglas_y_campos_obligatorios(interno, admin, oc, reglas_creadas):
    from app.modelos import Articulo

    l1 = oc["lineas"][0]
    with SessionLocal() as db, en_organizacion(1):
        a = db.get(Articulo, l1["articulo_id"])
        vacio = next((c for c, v in (("articulo.sku_proveedor", a.sku_proveedor), ("articulo.peso_unitario", a.peso_unitario),
                                     ("articulo.generico", a.generico), ("articulo.upc", a.upc)) if v in (None, "")), None)
        familia_antes = a.familia_etiquetado_id
    padre = interno.post("/etiquetas/familias", {"codigo": "RG-PADRE", "nombre": "Rules parent",
                                                 "campos": [{"campo": vacio, "obligatorio": True}] if vacio else []}).json()
    hija = interno.post("/etiquetas/familias", {"codigo": "RG-HIJA", "nombre": "Rules child", "padre_id": padre["id"]}).json()
    assert hija["padre_id"] == padre["id"] and hija["ruta"] == "Rules parent / Rules child"
    # Sin ciclos
    assert interno.patch(f"/etiquetas/familias/{padre['id']}", {"padre_id": hija["id"]}).status_code == 422
    interno.post("/etiquetas/articulos/familia", {"familia_id": hija["id"], "ids": [l1["articulo_id"]]})
    try:
        p = _aprobada(interno, admin, "Parent family design")
        _regla(interno, reglas_creadas, plantilla_id=p["id"], ambito="FAMILIA", familia_id=padre["id"], prioridad=990)
        g = _plan(interno, oc)[l1["id"]]
        # La regla de la familia padre aplica al artículo de la subfamilia
        assert g["plantilla"] == "Parent family design" and "Rules parent" in g["motivo"]
        if vacio:
            assert any(x["codigo"] == "dato_obligatorio" and vacio in x["mensaje"] and x["categoria"] == "dato_obligatorio"
                       for x in g["problemas"])
        # Una condición por familia (con sus subfamilias)
        x = interno.post("/etiquetas/reglas/probar", {
            "modalidad": "OC_ARTICULO", "posicion_id": l1["id"],
            "regla": {"plantilla_id": p["id"], "ambito": "REGLA", "prioridad": 995,
                      "condiciones": [{"campo": "articulo.familia_ruta", "op": "en_familia", "valor": "RG-PADRE"}]}}).json()
        assert x["regla"] and x["regla_id"] is None
        # No se borra una familia con subfamilias
        assert interno.c.delete(f"/api/etiquetas/familias/{padre['id']}", headers=interno.h).status_code == 409
    finally:
        interno.post("/etiquetas/articulos/familia", {"familia_id": familia_antes, "ids": [l1["articulo_id"]]})


def test_patrones_seguros_y_acotados(interno):
    """«coincide» no puede dejar al servidor calculando: se rechazan las
    repeticiones anidadas al guardar una regla o un diseño, y un patrón
    peligroso guardado antes (o un texto enorme) no se evalúa."""
    import time

    from app.modulos.etiquetado import reglas, render

    assert reglas.validar_patron(r"^[A-Z]{3}-\d{4}$") is None and reglas.validar_patron("NIKE.*") is None
    c = {"campo": "articulo.sku", "op": "coincide", "valor": "(a+)+$"}
    inicio = time.perf_counter()
    assert reglas.cumple_condicion(c, {"articulo.sku": "a" * 40 + "!"}) is False
    assert render.cumple(c, {"articulo.sku": "a" * 40 + "!"}) is False
    assert time.perf_counter() - inicio < 0.5
    assert reglas.cumple_condicion({**c, "valor": "A.*"}, {"articulo.sku": "A" * 5000}) is False  # texto fuera del tope
    assert reglas.cumple_condicion({**c, "valor": "a[0-9]+"}, {"articulo.sku": "A123"}) is True
    # La condición de visibilidad de un elemento del diseño usa la misma validación
    r = interno.post("/etiquetas/plantillas", {"nombre": "Unsafe pattern", "modalidad": "OC_ARTICULO", "diseno": {
        "ancho": 50, "alto": 20, "elementos": [{"id": "t", "tipo": "texto", "contenido": "x", "x": 1, "y": 1, "w": 20, "h": 5,
                                                "condicion": {"campo": "articulo.sku", "op": "coincide", "valor": "(\\w+\\s?)*$"}}]}})
    assert r.status_code == 422 and "repeat" in r.text, r.text
