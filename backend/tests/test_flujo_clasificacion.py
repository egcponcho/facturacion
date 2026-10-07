"""Flujo completo de clasificación con el motor único, de punta a punta por la API
que usa la pantalla: crear el producto → abrir la ficha → el motor pregunta →
se responde → sugiere → se guarda → se envía a revisión → se aprueba → el
producto guarda HS6, línea SAC, código de cada país y la evidencia completa."""
from app.db import SessionLocal
from app.models import Producto


def _producto_nuevo(api):
    m = {x["codigo"]: x["id"] for x in api.get("/catalogos/marcas", params={"size": 100}).json()["items"]}
    g = {x["codigo"]: x["id"] for x in api.get("/catalogos/grupos").json()["items"]}
    pv = {x["codigo"]: x["id"] for x in api.get("/catalogos/proveedores").json()["items"]}
    r = api.post("/catalogos/genericos", {"generico": "30077701", "estilo": "VN0E2E01", "color": "Black", "marca_id": m["VANS"],
                                          "grupo_id": g["CALZ-CAS"], "proveedor_id": pv["VANS"], "unidad": "PAR", "nombre": "Leather skate shoe",
                                          "tallas": [{"talla": "8"}, {"talla": "9"}]})
    assert r.status_code == 200, r.text
    p = next(x for x in api.get("/productos", params={"q": "VN0E2E01"}).json()["items"] if x["estilo"] == "VN0E2E01")
    return api.get(f"/productos/{p['id']}").json()


def _entrada(p, ficha, **extra):
    return {"categoria": ficha.get("_tipo"), "ficha": {k: v for k, v in ficha.items() if k != "_tipo"}, "estilo": p["estilo"],
            "nombre": p["nombre"], "producto_id": p["id"], "marca": p.get("marca_nombre"), **extra}


def test_flujo_completo_de_la_ficha_a_la_aprobacion(interno):
    p = _producto_nuevo(interno)
    assert p["estado"] == "borrador" and not p["codigo"]

    # 1. Abrir la ficha: el motor detecta la categoría por el nombre y dice qué falta
    s = interno.post("/clasificacion/sesion", _entrada(p, {"comp": {}})).json()
    assert s["categoria"]["codigo"] == "calzado" and s["detectado"]["categoria"] == "calzado"
    falt = {f["campo"] for f in s["faltantes"]}
    assert {"comp.corte", "comp.suela", "origen"} <= falt
    campos = {c["codigo"]: c for c in s["campos"]}
    assert campos["comp.corte"]["modo"] == "REQUIRE" and campos["comp.corte"]["composicion"]["sugerencias"][0]["m"] == "Leather"

    # 2. Responder lo que pregunta (composición, estilo) y el origen: el motor sugiere
    ficha = {**s["ficha"], "_tipo": "calzado", "comp": {"corte": "100% leather", "suela": "100% rubber"}, "estilo_calzado": "tenis",
             "altura": "bajo", "genero": "U", "edad": "adulto"}
    s = interno.post("/clasificacion/sesion", _entrada(p, ficha, origen="VN", tocados=["estilo_calzado", "altura", "genero", "edad"])).json()
    # El uso (deportivo o no) decide la subpartida: se supone «no deportivo» y se puede confirmar
    assert not s["faltantes"] and s["ficha"]["uso_deportivo"] == "no" and any(c["codigo"] == "uso_deportivo" for c in s["campos"])
    ficha = {**s["ficha"], "_tipo": "calzado"}
    s = interno.post("/clasificacion/sesion", _entrada(p, ficha, origen="VN", tocados=["estilo_calzado", "altura", "genero", "edad", "uso_deportivo"],
                                                        cambio={"campo": "uso_deportivo", "valor": "no"})).json()
    assert s["hs6"] and s["hs6"].startswith("6403") and s["completa"], s["faltantes"]
    # Todo país con código lo toma de una versión oficial; Panamá no tiene versión vigente (la suya sigue en borrador)
    assert s["clasificacion"]["paises"] and all(x["version"] for x in s["clasificacion"]["paises"] if x["codigo"])
    assert next(x for x in s["clasificacion"]["paises"] if x["pais"] == "PA")["sin_datos_oficiales"]
    sugerido = s["hs6"]

    # 3. Guardar la ficha natural: el servidor vuelve a clasificar con el mismo motor
    p = interno.put(f"/productos/{p['id']}/ficha", {"version": p["version"], "tipo": "calzado", "ficha": s["ficha"], "pais_origen": "VN",
                                                    "nombre": p["nombre"], "tocados": ["estilo_calzado", "altura"]}).json()
    assert p["estado"] == "sugerida" and p["sugerido"].replace(".", "") == sugerido and p["ficha_completa"]
    assert "CUERO" in (p["descripcion_aduana"] or "")

    # 4. Enviar a revisión y aprobar (la aprobación re-valida con el motor)
    assert interno.post("/productos/enviar", {"ids": [p["id"]]}).json()["enviados"] == 1
    p = interno.get(f"/productos/{p['id']}").json()
    assert p["estado"] == "revision"
    # Aprobar no exige las líneas nacionales: la OC y la factura llevan la subpartida de 6 dígitos
    r = interno.post(f"/productos/{p['id']}/aprobar", {"version": p["version"]})
    assert r.status_code == 200, r.text
    p = r.json()

    # 5. Lo aprobado: HS6, SAC, cada país con su línea y la evidencia reproducible
    assert p["estado"] == "aprobado" and p["codigo"].replace(".", "") == sugerido
    assert all(x["codigo"].startswith(sugerido) for x in p["partidas"].values())
    with SessionLocal() as db:
        x = db.get(Producto, p["id"])
        ev = x.evidencia
        assert x.version_arancel_id and ev["version"]["codigo"] and ev["hechos"]["categoria"] == "calzado"
        assert ev["aprobacion"]["hs6"] == sugerido and ev["aprobacion"]["sugerido"] == sugerido
        aplicadas = [t for t in ev["reglas"] if t.get("aplicada")]
        assert aplicadas and all(t["firma"] and t["revision"] for t in aplicadas)
        # Cada país con línea oficial la guarda; los que no tienen arancel nacional oficial cargado lo dicen
        assert {y["pais"] for y in ev["paises"] if y["codigo"]} == set(p["partidas"]) <= {"GT", "SV", "HN"}
        assert all(y["sin_datos_oficiales"] and not y["codigo"] for y in ev["paises"] if y["pais"] in ("NI", "CR", "PA"))
        assert all(f.version_id or f.manual for f in x.partidas if f.inciso_id)
    # Un país con varias líneas oficiales queda pendiente; una persona la confirma después
    for iso in {"GT", "SV", "HN"} - {k for k, v in p["partidas"].items() if v["estado"] == "ok"}:
        ops = interno.get(f"/productos/{p['id']}/partidas/{iso}").json()["opciones"]
        r = interno.post(f"/productos/{p['id']}/partidas/{iso}", {"codigo": ops[0]["codigo"]})
        assert r.status_code == 200, r.text
        p = r.json()
    assert {k for k, v in p["partidas"].items() if v["estado"] == "ok"} == {"GT", "SV", "HN"}
