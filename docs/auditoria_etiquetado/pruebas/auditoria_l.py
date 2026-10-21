"""Pruebas de auditoría (solo lectura del repo): confirman comportamientos del etiquetado."""
import pytest
from etiquetado_util import aprobada, tipo, uso

ELEM = [{"id": "sku", "tipo": "campo", "campo": "articulo.sku", "x": 3, "y": 3, "w": 70, "h": 8, "estilo": {"tam": 10}}]


def _r(nombre, fn):
    try:
        r = fn()
        print(f"\n[{nombre}] status={r.status_code} body={r.text[:300]}")
        return r
    except Exception as e:  # noqa: BLE001
        print(f"\n[{nombre}] EXCEPCION NO CAPTURADA (500): {type(e).__name__}: {str(e)[:200]}")
        return None


@pytest.fixture(scope="module")
def oc_tnf(interno):
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        d = interno.get(f"/ordenes/{o['id']}").json()
        lineas = [x for x in d["posiciones"] if x.get("codigo_articulo")]
        if d["oc"]["proveedor"] == "The North Face" and d["oc"]["estado"] != "BORRADOR" and len(lineas) >= 2:
            return {"oc": d["oc"], "lineas": lineas}
    pytest.skip("sin OC")


@pytest.fixture(scope="module")
def t_aud(interno, admin):
    t = tipo(interno, "AUD_L", cantidad="POR_LINEA")
    p = aprobada(interno, admin, "AUD design", t["id"], ELEM, ancho=80, alto=30)
    u = uso(interno, t["id"], p["id"])
    return t, p, u


def test_parametros_sin_validar(interno, oc_tnf, t_aud):
    t, _, _ = t_aud
    oc = oc_tnf["oc"]["id"]
    _r("oc_ids no numérico", lambda: interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": ["abc"], "tipos": [t["id"]]}}))
    _r("articulos sin articulo_id", lambda: interno.post("/etiquetas/trabajos", {"origen": "ARTICULOS", "parametros": {"articulos": [{}], "tipos": [t["id"]]}}))
    _r("elegidas no numérico", lambda: interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "tipos": [t["id"]], "elegidas": {"x": "abc"}}}))
    # dpi y hoja no se validan al crear; fallan al generar
    r = _r("dpi texto (crear)", lambda: interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "tipos": [t["id"]], "dpi": "abc", "formato": "PNG"}}))
    if r is not None and r.status_code == 200:
        tid = r.json()["id"]
        v = interno.post(f"/etiquetas/trabajos/{tid}/validar").json()
        print("estado tras validar:", v["estado"], v["resumen"].get("problemas"))
        _r("dpi texto (generar)", lambda: interno.post(f"/etiquetas/trabajos/{tid}/generar", {"formato": "PNG", "aceptar_advertencias": True}))
    r = _r("hoja inválida (crear)", lambda: interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "tipos": [t["id"]], "hoja": {"modo": "hoja", "columnas": 0}}}))
    if r is not None and r.status_code == 200:
        tid = r.json()["id"]
        interno.post(f"/etiquetas/trabajos/{tid}/validar")
        _r("hoja inválida (generar)", lambda: interno.post(f"/etiquetas/trabajos/{tid}/generar", {"formato": "PDF", "aceptar_advertencias": True}))
    r = _r("dpi enorme (crear)", lambda: interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "tipos": [t["id"]], "dpi": 5000}}))
    if r is not None:
        print("dpi guardado:", r.json().get("parametros", {}).get("dpi"))


def test_proveedor_ve_configuracion(tnf, interno, t_aud):
    t, p, u = t_aud
    _r("tnf GET /etiquetas/usos/valores PROVEEDOR", lambda: tnf.get("/etiquetas/usos/valores", params={"contexto": "PROVEEDOR"}))
    _r("tnf GET /etiquetas/usos", lambda: tnf.get("/etiquetas/usos"))
    r = _r("tnf POST /etiquetas/usos/simular", lambda: tnf.post("/etiquetas/usos/simular", {"tipo_etiqueta_id": t["id"], "nivel": "GENERAL",
                                                                                              "normal": {"accion": "NO_LLEVA"}}))
    if r is not None and r.status_code == 200:
        ej = r.json().get("ejemplos", [])
        print("ejemplos SKU devueltos al proveedor:", len(ej), [x["sku"] for x in ej[:8]])
    _r("tnf GET /etiquetas/matriz", lambda: tnf.get("/etiquetas/matriz"))
    _r("tnf GET /etiquetas/celda", lambda: tnf.get("/etiquetas/celda", params={"tipo": t["id"], "nivel": "GENERAL"}))


def test_proveedor_fuerza_diseno(tnf, interno, admin, oc_tnf, t_aud):
    t, p, u = t_aud
    otra = aprobada(interno, admin, "AUD design B", t["id"], ELEM, ancho=80, alto=30)
    oc = oc_tnf["oc"]["id"]
    r = _r("tnf crea trabajo", lambda: tnf.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "tipos": [t["id"]]}}))
    if r is None or r.status_code != 200:
        return
    tr = r.json()
    v = tnf.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    clave = v["registros"][0]["clave"]
    r2 = _r("tnf elegidas (forzar diseño)", lambda: tnf.patch(f"/etiquetas/trabajos/{tr['id']}", {"version": v["version"], "parametros": {"elegidas": {clave: otra["id"]}}}))
    v2 = tnf.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    reg = next(x for x in v2["registros"] if x["clave"] == clave)
    print("plantilla tras forzar:", reg["plantilla"], "regla:", p["nombre"], "motivo:", reg["motivo"], "estado:", reg["estado"])


def test_sin_version_aprobada_no_cae(interno, admin, oc_tnf, t_aud):
    t, p, u = t_aud
    # Un diseño nuevo sin aprobar asignado a la celda GENERAL: ¿se cae al anterior o bloquea?
    r = interno.post("/etiquetas/plantillas", {"nombre": "AUD borrador", "tipo_etiqueta_id": t["id"],
                                               "diseno": {"ancho": 80, "alto": 30, "elementos": ELEM}})
    nueva = r.json()
    ru = _r("asignar diseño sin aprobar", lambda: interno.post("/etiquetas/usos", {"tipo_etiqueta_id": t["id"], "plantilla_id": nueva["id"],
                                                                                    "nivel": "GENERAL", "contexto_tipo": "NINGUNO", "reemplazar": True}))
    oc = oc_tnf["oc"]["id"]
    tr = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "tipos": [t["id"]]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    print("estados:", v["resumen"]["conteo"], "problema:", v["registros"][0]["problemas"][:1])
    uso(interno, t["id"], p["id"])  # restaurar


def test_previas_incluye_anuladas(interno, oc_tnf, t_aud):
    t, p, u = t_aud
    oc = oc_tnf["oc"]["id"]
    pos = oc_tnf["lineas"][-1]["id"]
    tr = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "posiciones": [pos], "tipos": [t["id"]]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    g = interno.post(f"/etiquetas/trabajos/{tr['id']}/generar", {"formato": "PDF", "aceptar_advertencias": True, "version": v["version"]})
    assert g.status_code == 200, g.text
    gen = g.json()["ejecuciones"][-1]
    a = _r("anular", lambda: interno.post(f"/etiquetas/generaciones/{gen['id']}/anular", {"motivo": "Prueba de auditoría"}))
    v2 = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    print("problemas tras anular:", [(x["codigo"], x["mensaje"][:80]) for r in v2["registros"] for x in r["problemas"]])
    # un trabajo nuevo de la misma línea
    tr2 = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "posiciones": [pos], "tipos": [t["id"]]}}).json()
    v3 = interno.post(f"/etiquetas/trabajos/{tr2['id']}/validar").json()
    print("trabajo nuevo, problemas:", [(x["codigo"]) for r in v3["registros"] for x in r["problemas"]])
    res = interno.get("/etiquetas/resumen", params={"origen": "OC", "id": oc}).json()
    print("resumen.ya_generadas (incluye anuladas?):", res.get("ya_generadas"))


def test_resumen_vs_trabajo(interno, oc_tnf, t_aud):
    """¿El resumen de la OC (pantalla OC) dice lo mismo que el trabajo?"""
    t, p, u = t_aud
    oc = oc_tnf["oc"]["id"]
    res = interno.get("/etiquetas/resumen", params={"origen": "OC", "id": oc}).json()
    tr = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    print("resumen tipos:", [(x["tipo"]["nombre"], x["etiquetas"]) for x in res["tipos"]])
    print("trabajo (sin tipos) tipos:", [(x["tipo"], x["etiquetas"]) for x in v["resumen"]["tipos"]], "parametros.tipos:", tr["parametros"]["tipos"])


def test_vista_previa_proveedor_otra_oc(tnf, interno):
    """La vista previa con datos reales filtra por proveedor."""
    otras = [o for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]]
    ajena = next((o for o in otras if o.get("proveedor") and "North" not in str(o.get("proveedor"))), None)
    if ajena:
        _r("tnf vista previa con OC ajena", lambda: tnf.post("/etiquetas/vista-previa", {"oc_id": ajena["id"], "version_id": 1}))


def test_imagen_de_otro_modulo(interno, tnf, vans):
    """¿Un proveedor lee por /etiquetas/imagenes una foto de producto de otro proveedor?"""
    import io
    from PIL import Image
    prods = interno.get("/productos", params={"size": 100}).json()
    items = prods["items"] if isinstance(prods, dict) else prods
    ajeno = next((p for p in items if "vans" in str(p.get("proveedor", "")).lower()), None)
    if ajeno is None:
        print("sin producto de Vans", [p.get("proveedor") for p in items[:5]])
        return
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "PNG")
    r = interno.c.post(f"/api/productos/{ajeno['id']}/fotos", headers=interno.h, files={"archivo": ("x.png", buf.getvalue(), "image/png")})
    print("subir foto:", r.status_code, r.text[:200])
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modelos import Adjunto
    with SessionLocal() as db, en_organizacion(1):
        ultimo = max(a.id for a in db.query(Adjunto).all())
        clave = db.get(Adjunto, ultimo).clave
    print("adjunto", ultimo, clave)
    _r("tnf GET /etiquetas/imagenes/<foto de Vans>", lambda: tnf.get(f"/etiquetas/imagenes/{ultimo}"))
    _r("tnf GET /productos/{id} de Vans (control)", lambda: tnf.get(f"/productos/{ajeno['id']}"))


def test_cantidad_a_mano_ignorada(interno, oc_tnf, t_aud):
    """La pantalla deja escribir la cantidad de cualquier registro; ¿el servidor la usa si el tipo no es MANUAL?"""
    t, p, u = t_aud
    oc = oc_tnf["oc"]["id"]
    tr = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "tipos": [t["id"]]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    r0 = v["registros"][0]
    print("antes:", r0["clave"], r0["cantidad"])
    v2 = interno.patch(f"/etiquetas/trabajos/{tr['id']}", {"version": v["version"], "parametros": {"cantidades": {r0["clave"]: 7}}}).json()
    v3 = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    r1 = next(x for x in v3["registros"] if x["clave"] == r0["clave"])
    print("después de escribir 7:", r1["cantidad"], "parametros.cantidades:", v3["parametros"].get("cantidades"))


def test_generar_dos_trabajos_misma_oc(interno, oc_tnf, t_aud):
    """Dos trabajos de la misma línea validados antes de generar: el segundo genera sin bloqueo (solo aviso)."""
    t, p, u = t_aud
    oc = oc_tnf["oc"]["id"]
    pos = oc_tnf["lineas"][0]["id"]
    a = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "posiciones": [pos], "tipos": [t["id"]]}}).json()
    b = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc], "posiciones": [pos], "tipos": [t["id"]]}}).json()
    va = interno.post(f"/etiquetas/trabajos/{a['id']}/validar").json()
    vb = interno.post(f"/etiquetas/trabajos/{b['id']}/validar").json()
    ga = interno.post(f"/etiquetas/trabajos/{a['id']}/generar", {"formato": "PDF", "aceptar_advertencias": True, "version": va["version"]})
    gb = interno.post(f"/etiquetas/trabajos/{b['id']}/generar", {"formato": "PDF", "aceptar_advertencias": True, "version": vb["version"]})
    print("A:", ga.status_code, "B:", gb.status_code, gb.text[:200])


def test_ficha_producto_vs_trabajo(interno, admin, oc_tnf, t_aud):
    """Excepción por condición sobre articulo.sku: ¿la ficha del producto y /resolver dicen lo mismo que el trabajo?"""
    from etiquetado_util import articulo_de
    t, p, u = t_aud
    linea = oc_tnf["lineas"][0]
    aid = articulo_de(linea["id"])
    art = interno.get("/etiquetas/articulos", params={"ids": str(aid)}).json()["items"][0]
    exc_p = aprobada(interno, admin, "AUD exception", t["id"], ELEM, ancho=80, alto=30)
    e = uso(interno, t["id"], exc_p["id"], contexto_tipo="CONDICION", reemplazar=False, motivo="by sku",
            condiciones=[{"campo": "articulo.sku", "op": "igual", "valor": art["sku"]}])
    res = interno.get("/etiquetas/resolver", params={"articulo_id": aid}).json()["elecciones"]
    el = next(x for x in res if x["tipo_etiqueta_id"] == t["id"])
    print("resolver:", el["plantilla"])
    prod_id = art.get("producto_id")
    if prod_id:
        fp = interno.get(f"/etiquetas/productos/{prod_id}").json()
        x = next(x for x in fp["tipos"] if x["tipo"]["id"] == t["id"])
        print("ficha producto:", x["eleccion"]["plantilla"] if x["eleccion"] else None, "distintas:", [d["sku"] for d in x["distintas"]])
    tr = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc_tnf["oc"]["id"]], "posiciones": [linea["id"]], "tipos": [t["id"]]}}).json()
    v = interno.post(f"/etiquetas/trabajos/{tr['id']}/validar").json()
    print("trabajo:", [r["plantilla"] for r in v["registros"]])
    interno.post(f"/etiquetas/usos/{e['id']}/baja", {"motivo": "fin"})


def test_vista_previa_ejemplo_proveedor(tnf, vans, t_aud):
    t, p, u = t_aud
    vid = p["vigente"]["id"]
    for quien, api in (("tnf", tnf), ("vans", vans)):
        r = api.post("/etiquetas/vista-previa", {"version_id": vid})
        print(quien, r.status_code, {k: v for k, v in (r.json().get("valores") or {}).items()})
    # el diseño solo usa articulo.sku; miro los ejemplos completos con un diseño sin guardar no está permitido a proveedor
    from app.core.db import SessionLocal
    from app.core.organizacion import en_organizacion
    from app.modulos.etiquetado import campos
    with SessionLocal() as db, en_organizacion(1):
        ej = campos.ejemplos(db, "ARTICULO")
        print("ejemplos: oc.proveedor=", ej.get("oc.proveedor"), "articulo.sku=", ej.get("articulo.sku"), "linea.precio=", ej.get("linea.precio"))
