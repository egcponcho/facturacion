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
    ficha = {**s["ficha"], "_tipo": "calzado", "comp": {"corte": "100% leather", "suela": "100% rubber"}, "estiloCalz": "tenis",
             "altura": "bajo", "genero": "U", "edadNac": "adulto"}
    s = interno.post("/clasificacion/sesion", _entrada(p, ficha, origen="VN", tocados=["estiloCalz", "altura", "genero", "edadNac"])).json()
    # Todavía falta un dato que decide la subpartida: el motor lo pregunta
    assert [f["campo"] for f in s["faltantes"]] == ["puntera"] and any(q["codigo"] == "puntera" for q in s["preguntas"])
    ficha = {**s["ficha"], "_tipo": "calzado"}
    s = interno.post("/clasificacion/sesion", _entrada(p, ficha, origen="VN", tocados=["estiloCalz", "altura", "genero", "edadNac", "puntera"],
                                                        cambio={"campo": "puntera", "valor": "ninguna"})).json()
    assert s["hs6"] and s["hs6"].startswith("6403") and s["completa"], s["faltantes"]
    assert s["clasificacion"]["paises"] and all(x["version"] for x in s["clasificacion"]["paises"])
    sugerido = s["hs6"]

    # 3. Guardar la ficha natural: el servidor vuelve a clasificar con el mismo motor
    p = interno.put(f"/productos/{p['id']}/ficha", {"version": p["version"], "tipo": "calzado", "ficha": s["ficha"], "pais_origen": "VN",
                                                    "nombre": p["nombre"], "tocados": ["estiloCalz", "altura"]}).json()
    assert p["estado"] == "sugerida" and p["sugerido"].replace(".", "") == sugerido and p["ficha_completa"]
    assert "CUERO" in (p["descripcion_aduana"] or "")

    # 4. Enviar a revisión y aprobar (la aprobación re-valida con el motor)
    assert interno.post("/productos/enviar", {"ids": [p["id"]]}).json()["enviados"] == 1
    p = interno.get(f"/productos/{p['id']}").json()
    assert p["estado"] == "revision"
    r = interno.post(f"/productos/{p['id']}/aprobar", {"version": p["version"]})
    if r.status_code == 422 and r.json()["codigo"] == "faltan_paises":  # un país con varias líneas: se elige una de sus opciones
        partidas = {x["pais"]: {"codigo": x["opciones"][0], "manual": True} for x in r.json()["detalle"]}
        r = interno.post(f"/productos/{p['id']}/aprobar", {"version": p["version"], "partidas": partidas})
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
        assert {y["pais"] for y in ev["paises"]} == set(p["partidas"])
        assert all(f.version_id or f.manual for f in x.partidas if f.inciso_id)
