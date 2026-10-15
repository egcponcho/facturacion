"""Matriz de casos de la resolución de diseños (auditoría P1): lo que la escalera de
test_etiquetado_reglas.py no cubre. Empates (dos excepciones del mismo peso que aplican a la
vez: gana la más antigua y se avisa), valores que se solapan (no se pueden guardar),
vigencias en sus bordes y en el futuro, el diseño normal sin fechas, la familia inactiva
(sigue aplicando a sus artículos: desactivar no cambia lo que se imprime) y sin coincidencia
(tipo obligatorio: error; opcional: no se imprime)."""
from datetime import date, timedelta

import pytest
from etiquetado_util import aprobada, problemas, tipo, trabajo, uso

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion
from app.modulos.etiquetado import reglas

TEXTO = [{"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 3, "w": 70, "h": 8, "estilo": {"tam": 10}}]


@pytest.fixture(scope="module")
def caso(interno, admin):
    from app.modelos import OrdenCompra, PosicionOC

    with SessionLocal() as db, en_organizacion(1):
        p = next(x for x in db.query(PosicionOC).order_by(PosicionOC.id.desc())
                 if x.articulo_id and x.oc.centro_destino and x.oc.estado != "BORRADOR")
        oc: OrdenCompra = p.oc
        datos = {"articulo_id": p.articulo_id, "oc_id": oc.id, "centro": oc.centro_destino, "posicion_id": p.id,
                 "sku": p.articulo.sku}
    t = tipo(interno, "CASOS")
    d = {k: aprobada(interno, admin, f"Cases {k}", t["id"], TEXTO, ancho=80, alto=30) for k in ("general", "a", "b", "c")}
    usos = [uso(interno, t["id"], d["general"]["id"])]
    yield {**datos, "tipo": t, "d": d, "usos": usos}
    for u in usos:
        interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "Test done"})


def _elige(interno, caso):
    q = {"sujeto": "ARTICULO", "articulo_id": caso["articulo_id"], "oc_id": caso["oc_id"]}
    return next(e for e in interno.get("/etiquetas/resolver", params=q).json()["elecciones"] if e["tipo_etiqueta_id"] == caso["tipo"]["id"])


def _exc(interno, caso, clave, esperado=200, **kw):
    r = interno.post("/etiquetas/usos", {"tipo_etiqueta_id": caso["tipo"]["id"], "plantilla_id": caso["d"][clave]["id"],
                                         "nivel": "GENERAL", "motivo": f"Case {clave}", **kw})
    assert r.status_code == esperado, r.text
    if r.status_code == 200:
        caso["usos"].append(r.json())
    return r.json()


def _baja(interno, caso, u):
    assert interno.post(f"/etiquetas/usos/{u['id']}/baja", {"motivo": "Case done"}).status_code == 200
    caso["usos"].remove(u)


def test_empate_de_excepciones_gana_la_mas_antigua_y_avisa(interno, caso):
    si = {"campo": "articulo.sku", "op": "existe"}
    a = _exc(interno, caso, "a", contexto_tipo="CONDICION", condiciones=[si])
    b = _exc(interno, caso, "b", contexto_tipo="CONDICION", condiciones=[{"campo": "articulo.sku", "op": "igual", "valor": caso["sku"]}])
    try:
        e = _elige(interno, caso)
        assert e["plantilla"] == "Cases a" and [x["plantilla"] for x in e["porque"]["empate"]] == ["Cases b"]
        # En el trabajo, el registro lo dice (advertencia)
        tr = trabajo(interno, "OC", {"oc_ids": [caso["oc_id"]], "posiciones": [caso["posicion_id"]], "tipos": [caso["tipo"]["id"]]})
        reg = next(r for r in tr["registros"] if r["tipo_etiqueta_id"] == caso["tipo"]["id"])
        assert reg["plantilla"] == "Cases a" and "excepciones_empatadas" in problemas(reg)
        # Con condiciones excluyentes ya no hay empate
        _baja(interno, caso, b)
        b = _exc(interno, caso, "b", contexto_tipo="CONDICION",
                 condiciones=[{"campo": "articulo.sku", "op": "igual", "valor": caso["sku"] + "-OTHER"}])
        e = _elige(interno, caso)
        assert e["plantilla"] == "Cases a" and not e["porque"]["empate"]
    finally:
        for u in (a, b):
            if u in caso["usos"]:
                _baja(interno, caso, u)


def test_valores_que_se_solapan_no_se_guardan(interno, caso):
    with SessionLocal() as db, en_organizacion(1):
        from app.modelos import Centro

        otros = [c for (c,) in db.query(Centro.codigo).filter(Centro.codigo != caso["centro"]).limit(2)]
    a = _exc(interno, caso, "a", contexto_tipo="CENTRO_DESTINO", contexto_valores=[caso["centro"], otros[0]])
    try:
        # Otro centro distinto: sí; uno que comparte un centro: no (no se sabría cuál aplica)
        r = _exc(interno, caso, "b", esperado=409, contexto_tipo="CENTRO_DESTINO", contexto_valores=[otros[0], otros[1]])
        assert r["codigo"] == "excepcion_repetida"
        b = _exc(interno, caso, "b", contexto_tipo="CENTRO_DESTINO", contexto_valores=[otros[1]])
        assert _elige(interno, caso)["plantilla"] == "Cases a"
        _baja(interno, caso, b)
        # «a» no tiene fechas: se cruza con cualquier otra del mismo centro
        _exc(interno, caso, "c", esperado=409, contexto_tipo="CENTRO_DESTINO", contexto_valores=[caso["centro"]],
             vigente_desde=(date.today() + timedelta(days=30)).isoformat())
    finally:
        _baja(interno, caso, a)
    # El mismo centro en fechas que no se cruzan: sí se pueden guardar las dos
    hoy = date.today()
    x = _exc(interno, caso, "a", contexto_tipo="CENTRO_DESTINO", contexto_valores=[caso["centro"]],
             vigente_hasta=(hoy + timedelta(days=10)).isoformat())
    y = _exc(interno, caso, "c", contexto_tipo="CENTRO_DESTINO", contexto_valores=[caso["centro"]],
             vigente_desde=(hoy + timedelta(days=11)).isoformat())
    _baja(interno, caso, x)
    _baja(interno, caso, y)


def test_vigencias_en_sus_bordes_y_en_el_futuro(interno, caso):
    from app.modelos import UsoDiseno

    hoy = date(2026, 6, 15)
    assert reglas.vigente(UsoDiseno(vigente_desde=hoy, vigente_hasta=hoy), hoy)  # los dos días cuentan
    assert not reglas.vigente(UsoDiseno(vigente_hasta=hoy - timedelta(days=1)), hoy)
    assert not reglas.vigente(UsoDiseno(vigente_desde=hoy + timedelta(days=1)), hoy)
    assert reglas.vigente(UsoDiseno(), hoy)
    # Una excepción que empieza en el futuro todavía no aplica
    futura = _exc(interno, caso, "a", contexto_tipo="CENTRO_DESTINO", contexto_valores=[caso["centro"]],
                  vigente_desde=(date.today() + timedelta(days=5)).isoformat())
    try:
        assert _elige(interno, caso)["plantilla"] == "Cases general"
    finally:
        _baja(interno, caso, futura)
    # Fechas al revés y un diseño normal con fechas: no
    _exc(interno, caso, "a", esperado=422, contexto_tipo="CENTRO_DESTINO", contexto_valores=[caso["centro"]],
         vigente_desde="2026-02-01", vigente_hasta="2026-01-01")
    r = interno.post("/etiquetas/usos", {"tipo_etiqueta_id": caso["tipo"]["id"], "plantilla_id": caso["d"]["a"]["id"],
                                         "nivel": "SKU", "destino_id": caso["articulo_id"], "vigente_hasta": "2030-01-01"})
    assert r.status_code == 422


def test_familia_inactiva_sigue_aplicando_y_sin_coincidencia(interno, admin, caso):
    fam = interno.post("/etiquetas/familias", {"codigo": "CASOS-F", "nombre": "Cases family"}).json()
    assert interno.post("/etiquetas/articulos/familia", {"familia_id": fam["id"], "ids": [caso["articulo_id"]]}).status_code == 200
    u = uso(interno, caso["tipo"]["id"], caso["d"]["a"]["id"], "FAMILIA", fam["id"])
    caso["usos"].append(u)
    try:
        assert _elige(interno, caso)["plantilla"] == "Cases a"
        assert interno.patch(f"/etiquetas/familias/{fam['id']}", {"activa": False}).status_code == 200
        # Desactivar la familia no cambia lo que se imprime para los artículos que ya la tienen
        assert _elige(interno, caso)["plantilla"] == "Cases a"
        # ...pero ya no se asigna a otros
        assert interno.post("/etiquetas/articulos/familia", {"familia_id": fam["id"], "ids": [caso["articulo_id"]]}).status_code == 422
    finally:
        _baja(interno, caso, u)
        interno.post("/etiquetas/articulos/familia", {"familia_id": None, "ids": [caso["articulo_id"]]})
    # Sin ningún diseño que aplique: opcional → no se imprime; obligatorio → error
    general = caso["usos"][0]
    _baja(interno, caso, general)
    try:
        assert _elige(interno, caso)["porque"]["clase"] == "sin_diseno"
        tr = trabajo(interno, "OC", {"oc_ids": [caso["oc_id"]], "posiciones": [caso["posicion_id"]], "tipos": [caso["tipo"]["id"]]})
        reg = next(r for r in tr["registros"] if r["tipo_etiqueta_id"] == caso["tipo"]["id"])
        assert reg["estado"] == "OMITIDO"
        obligatorio = tipo(interno, "CASOS-OBL", obligatoria=True)
        tr = trabajo(interno, "OC", {"oc_ids": [caso["oc_id"]], "posiciones": [caso["posicion_id"]], "tipos": [obligatorio["id"]]})
        reg = next(r for r in tr["registros"] if r["tipo_etiqueta_id"] == obligatorio["id"])
        assert reg["estado"] == "ERROR" and "sin_plantilla" in problemas(reg)
    finally:
        caso["usos"].insert(0, uso(interno, caso["tipo"]["id"], caso["d"]["general"]["id"]))
