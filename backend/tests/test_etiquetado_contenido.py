"""Contenido de las etiquetas: campos lógicos con precedencia de fuentes,
política ante valores distintos y procedencia en la instantánea; tablas con
colecciones (contenido del bulto, componentes de prepacks y kits), totales
y desborde que nunca se corta en silencio; códigos compuestos con separador
y transformaciones que se leen con un lector; identificadores controlados
por una serie sin repetirse; empaque planificado frente a declarado."""
import io
import zipfile

import pytest
from PIL import Image
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion
from app.modulos.etiquetado import diseno, render

zxingcpp = pytest.importorskip("zxingcpp")


def _aprobada(interno, admin, nombre, elementos, modalidad="OC_ARTICULO", ancho=100, alto=60):
    r = interno.post("/etiquetas/plantillas", {"nombre": nombre, "modalidad": modalidad,
                                               "diseno": {"ancho": ancho, "alto": alto, "elementos": elementos}})
    assert r.status_code == 200, r.text
    v = r.json()["versiones"][0]
    assert interno.post(f"/etiquetas/versiones/{v['id']}/enviar", {}).status_code == 200
    assert admin.post(f"/etiquetas/versiones/{v['id']}/aprobar", {}).status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def linea(interno):
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        r = interno.get(f"/etiquetas/oc/{o['id']}").json()
        for x in r["lineas"]:
            if x["articulo_id"] and not x["bloqueada"]:
                return {**x, "oc_id": r["oc"]["id"], "oc": r["oc"]["numero"]}
    pytest.skip("no PO line with an item")


@pytest.fixture
def limpiar(interno):
    reglas, campos_ = [], []
    yield reglas, campos_
    for i in reglas:
        interno.c.delete(f"/api/etiquetas/asignaciones/{i}", headers=interno.h)
    for i in campos_:
        interno.c.delete(f"/api/etiquetas/campos-logicos/{i}", headers=interno.h)


def _solo_esta(interno, limpiar, plantilla_id, condicion, prioridad=5000):
    r = interno.post("/etiquetas/asignaciones", {"plantilla_id": plantilla_id, "ambito": "REGLA", "prioridad": prioridad,
                                                 "condiciones": [condicion]})
    assert r.status_code == 200, r.text
    limpiar[0].append(r.json()["id"])


# ---- Tablas (motor de dibujo) ------------------------------------------------------------------
def _tabla(**kw):
    e = {"id": "t", "tipo": "tabla", "coleccion": "bulto.lineas", "x": 2, "y": 2, "w": 90, "h": 30, "alto_fila": 5,
         "columnas": [{"campo": "sku", "titulo": "SKU", "ancho": 3}, {"campo": "talla", "titulo": "Size"},
                      {"campo": "cantidad", "titulo": "Qty", "alin": "der"}],
         "totales": ["cantidad"], "estilo": {"tam": 8, "tam_min": 6}, **kw}
    return diseno.validar({"ancho": 100, "alto": 40, "elementos": [e]})


def _filas(n):
    return [{"sku": f"SKU{i:03d}", "talla": str(30 + i), "cantidad": 2} for i in range(n)]


def _textos(lz):
    return [t for p in lz.prims if p.tipo == "texto" for t, *_ in p.lineas]


def test_tabla_columnas_totales_y_desborde():
    d = _tabla()
    # 30 mm / 5 mm = 6 filas: encabezado + 4 + total
    lz = render.componer(d, {"bulto.lineas": _filas(4)}, {"bulto.lineas.cantidad": "numero"})
    assert not lz.problemas and "SKU" in _textos(lz) and "SKU003" in _textos(lz) and "8" in _textos(lz)
    # Más filas de las que caben: error (nunca se cortan sin avisar)
    lz = render.componer(d, {"bulto.lineas": _filas(9)}, {})
    assert [p["codigo"] for p in lz.errores] == ["tabla_desborda"]
    # Resumir: las que caben y «… +N» con advertencia; el total suma todas las filas
    lz = render.componer(_tabla(desborde="resumir"), {"bulto.lineas": _filas(9)}, {"bulto.lineas.cantidad": "numero"})
    assert not lz.errores and [p["codigo"] for p in lz.advertencias] == ["tabla_resumida"]
    assert "… +6" in _textos(lz) and "18" in _textos(lz) and "SKU008" not in _textos(lz)
    # Reducir: letra más chica si alcanza; si ni con la mínima caben, error
    lz = render.componer(_tabla(desborde="reducir"), {"bulto.lineas": _filas(6)}, {})
    assert not lz.problemas and "SKU005" in _textos(lz)
    lz = render.componer(_tabla(desborde="reducir"), {"bulto.lineas": _filas(40)}, {})
    assert [p["codigo"] for p in lz.errores] == ["tabla_desborda"]
    # Un total con una fila sin número no se inventa
    filas = _filas(2) + [{"sku": "X", "talla": "1", "cantidad": None}]
    lz = render.componer(d, {"bulto.lineas": filas}, {})
    assert "total_incompleto" in [p["codigo"] for p in lz.advertencias]
    # Lista vacía: aviso (o error si el diseño lo exige)
    assert [p["codigo"] for p in render.componer(d, {}, {}).advertencias] == ["tabla_vacia"]
    assert [p["codigo"] for p in render.componer(_tabla(si_vacio="error"), {}, {}).errores] == ["tabla_vacia"]
    # Los totales tienen que ser columnas de la tabla
    from app.core.errores import ErrorNegocio

    with pytest.raises(ErrorNegocio):
        _tabla(totales=["peso"])


def test_condicion_de_visibilidad_con_los_operadores_de_las_reglas():
    d = diseno.validar({"ancho": 50, "alto": 20, "elementos": [
        {"id": "a", "tipo": "texto", "contenido": "BIG", "x": 1, "y": 1, "w": 40, "h": 6,
         "condicion": {"campo": "linea.cantidad", "op": "mayor", "valor": 100}},
        {"id": "b", "tipo": "texto", "contenido": "BRAND", "x": 1, "y": 8, "w": 40, "h": 6,
         "condicion": {"campo": "articulo.marca_codigo", "op": "en", "valor": ["TNF", "VANS"]}}]})
    assert _textos(render.componer(d, {"linea.cantidad": 120, "articulo.marca_codigo": "vans"}, {})) == ["BIG", "BRAND"]
    assert _textos(render.componer(d, {"linea.cantidad": 5, "articulo.marca_codigo": "OTRA"}, {})) == []


# ---- Códigos compuestos ----------------------------------------------------------------------------
def test_codigo_compuesto_con_separador_y_transformaciones_se_lee():
    e = {"id": "c", "tipo": "codigo", "simbologia": "code128", "x": 2, "y": 2, "w": 96, "h": 26, "margen": 2,
         "partes": [{"tipo": "fijo", "texto": "po"}, {"campo": "oc.numero", "transformar": ["solo_digitos"], "rellenar": 10},
                    {"campo": "articulo.talla", "transformar": ["mayus", "sin_espacios"]}],
         "separador": "|"}
    d = diseno.validar({"ancho": 100, "alto": 30, "elementos": [e]})
    valores = {"oc.numero": "PO-4512", "articulo.talla": "x l"}
    assert render.valor_codigo(d["elementos"][0], valores, {})[0] == "po|0000004512|XL"
    lz = render.componer(d, valores, {})
    assert not lz.errores
    from app.modulos.etiquetado import salidas

    with Image.open(io.BytesIO(salidas.png(lz, 300))) as im:
        assert [x.text for x in zxingcpp.read_barcodes(im.convert("L"))] == ["po|0000004512|XL"]
    # Una parte vacía es un error (no se codifica un valor incompleto)
    lz = render.componer(d, {"oc.numero": "PO-4512"}, {})
    assert [p["codigo"] for p in lz.errores] == ["codigo_sin_valor"]
    # La verificación con el lector encuentra lo que dice cada código
    from app.modulos.etiquetado import verificacion

    lz = render.componer(d, valores, {})
    assert verificacion.verificar(lz, d, valores, {}) == []


# ---- Campos lógicos -----------------------------------------------------------------------------------
def test_campos_logicos_precedencia_politica_y_procedencia(interno, admin, linea, limpiar):
    from app.modelos import GeneracionItem, PosicionOC

    r = interno.post("/etiquetas/campos-logicos", {"clave": "upc_etq", "etiqueta": "Label UPC",
                                                   "fuentes": ["linea.upc", "articulo.upc"], "politica": "ADVERTIR"})
    assert r.status_code == 200, r.text
    campo = r.json()
    limpiar[1].append(campo["id"])
    # Validación: fuentes que no existen, clave inválida, repetida
    assert interno.post("/etiquetas/campos-logicos", {"clave": "x", "etiqueta": "X", "fuentes": ["no.existe"]}).status_code == 422
    assert interno.post("/etiquetas/campos-logicos", {"clave": "Mal Clave", "etiqueta": "X", "fuentes": ["articulo.upc"]}).status_code == 422
    assert interno.post("/etiquetas/campos-logicos", {"clave": "upc_etq", "etiqueta": "X", "fuentes": ["articulo.upc"]}).status_code == 422
    # Está en el catálogo de campos de las etiquetas
    catalogo = {c["clave"]: c for c in interno.get("/etiquetas/campos", params={"modalidad": "OC_ARTICULO"}).json()["campos"]}
    assert "logico.upc_etq" in catalogo and "linea.upc → articulo.upc" in catalogo["logico.upc_etq"]["origen"]

    with SessionLocal() as db, en_organizacion(1):
        p = db.get(PosicionOC, linea["id"])
        antes = p.upc
        art_upc = p.articulo.upc or "000000000000"
        if not p.articulo.upc:
            p.articulo.upc = art_upc
        p.upc = None
        db.commit()
    try:
        texto = [{"id": "u", "tipo": "texto", "contenido": "UPC {{logico.upc_etq}}", "x": 2, "y": 2, "w": 90, "h": 8}]
        dis = _aprobada(interno, admin, "Logical field design", texto)
        _solo_esta(interno, limpiar, dis["id"], {"campo": "linea.posicion", "op": "igual", "valor": linea["posicion"]})
        base = {"oc_id": linea["oc_id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA", "posiciones": [linea["id"]]}
        g = interno.post("/etiquetas/plan", base).json()["grupos"][0]
        # Sin UPC en la línea sale del artículo, y se dice de dónde
        assert g["plantilla"] == "Logical field design" and g["procedencia"]["logico.upc_etq"] == "articulo.upc"
        # Fuentes con valores distintos: ADVERTIR avisa, BLOQUEAR impide generar
        with SessionLocal() as db, en_organizacion(1):
            db.get(PosicionOC, linea["id"]).upc = "999999999999"
            db.commit()
        g = interno.post("/etiquetas/plan", base).json()["grupos"][0]
        assert g["procedencia"]["logico.upc_etq"] == "linea.upc"
        aviso = [x for x in g["problemas"] if x["codigo"] == "fuentes_distintas"]
        assert aviso and aviso[0]["nivel"] == "advertencia" and aviso[0]["categoria"] == "conflicto"
        r = interno.patch(f"/etiquetas/campos-logicos/{campo['id']}", {"politica": "BLOQUEAR", "version": campo["version"]})
        assert r.status_code == 200, r.text
        assert interno.patch(f"/etiquetas/campos-logicos/{campo['id']}", {"politica": "PRIMERA", "version": campo["version"]}).status_code == 409
        g = interno.post("/etiquetas/plan", base).json()["grupos"][0]
        assert [x["nivel"] for x in g["problemas"] if x["codigo"] == "fuentes_distintas"] == ["error"]
        # PRIMERA: usa el primero sin avisar; la instantánea guarda la procedencia
        interno.patch(f"/etiquetas/campos-logicos/{campo['id']}", {"politica": "PRIMERA"})
        gen = interno.post("/etiquetas/generaciones", {**base, "formato": "PDF", "aceptar_advertencias": True})
        assert gen.status_code == 200, gen.text
        with SessionLocal() as db, en_organizacion(1):
            it = db.scalars(select(GeneracionItem).where(GeneracionItem.generacion_id == gen.json()["id"])).one()
            assert it.valores["logico.upc_etq"] == "999999999999" and it.valores["_procedencia"] == {"logico.upc_etq": "linea.upc"}
        # Un campo que usa un diseño no se borra
        assert interno.c.delete(f"/api/etiquetas/campos-logicos/{campo['id']}", headers=interno.h).status_code == 409
        interno.patch(f"/etiquetas/campos-logicos/{campo['id']}", {"activo": False})
        limpiar[1].remove(campo["id"])
    finally:
        with SessionLocal() as db, en_organizacion(1):
            db.get(PosicionOC, linea["id"]).upc = antes
            db.commit()


# ---- Identificador controlado ---------------------------------------------------------------------------
def test_serie_controlada_sin_repetir_y_reproducible(interno, admin, linea, limpiar):
    elementos = [{"id": "c", "tipo": "codigo", "simbologia": "code128", "x": 2, "y": 2, "w": 96, "h": 26, "margen": 2,
                  "partes": [{"tipo": "fijo", "texto": "LBL"}, {"campo": "etiqueta.serie"}], "separador": "-"}]
    dis = _aprobada(interno, admin, "Controlled ID design", elementos, ancho=100, alto=30)
    _solo_esta(interno, limpiar, dis["id"], {"campo": "linea.posicion", "op": "igual", "valor": linea["posicion"]}, 5100)
    base = {"oc_id": linea["oc_id"], "modalidad": "OC_ARTICULO", "unidad": "MANUAL", "posiciones": [linea["id"]],
            "cantidades": {str(linea["id"]): 3}}
    # Sin serie de etiquetas configurada no se genera
    g = interno.post("/etiquetas/plan", base).json()["grupos"][0]
    assert any(x["codigo"] == "sin_serie" and x["categoria"] == "configuracion" for x in g["problemas"])
    r = admin.post("/catalogos/series", {"codigo": "ETQ", "nombre": "Labels", "objeto": "etiqueta", "prefijo": "E{año}-",
                                        "digitos": 6, "reinicio": "NUNCA", "predeterminada": True, "activo": True})
    assert r.status_code == 200, r.text

    def leer(gen_id):
        z = zipfile.ZipFile(io.BytesIO(interno.get(f"/etiquetas/generaciones/{gen_id}/archivo", params={"formato": "ZIP"}).content))
        res = []
        for n in sorted(x for x in z.namelist() if x.startswith("png/")):
            with Image.open(io.BytesIO(z.read(n))) as im:
                res += [x.text for x in zxingcpp.read_barcodes(im.convert("L"))]
        return res

    g1 = interno.post("/etiquetas/generaciones", {**base, "formato": "ZIP", "aceptar_advertencias": True})
    assert g1.status_code == 200, g1.text
    g2 = interno.post("/etiquetas/generaciones", {**base, "formato": "ZIP", "aceptar_advertencias": True}).json()
    primeros, segundos = leer(g1.json()["id"]), leer(g2["id"])
    assert len(primeros) == 3 and len(set(primeros + segundos)) == 6, (primeros, segundos)
    numeros = [int(x.rsplit("-", 1)[1]) for x in primeros + segundos]
    assert numeros == list(range(numeros[0], numeros[0] + 6)) and all(x.startswith("LBL-E") for x in primeros)
    # Descargar de nuevo da los mismos números (no se vuelven a reservar)
    assert leer(g1.json()["id"]) == primeros


# ---- Bulto: contenido, componentes y planificado vs declarado ---------------------------------------
def test_bulto_contenido_componentes_y_empaque_planificado(interno, admin, limpiar):
    from app.modelos import Articulo, GrupoCajas, PackingList, PosicionOC, Prepack, PrepackComponente

    pls = interno.get("/etiquetas/masivo/packing").json()
    con = [x for x in pls if interno.get(f"/etiquetas/masivo/packing/{x['id']}").json()["superiores"]]
    if not con:
        pytest.skip("no packing lists with packages")
    pl_id = con[0]["id"]
    with SessionLocal() as db, en_organizacion(1):
        from app.modulos.etiquetado import campos as svc_campos

        pl = db.get(PackingList, pl_id)
        caja = next(g for g in pl.grupos if g.tipo_empaque is not None and g.tipo_empaque.cuenta_como == "BULTO")
        tipo = caja.tipo_empaque_id
        u0 = next(x for x in svc_campos.unidades_pl(pl, tipo) if x.grupo_id == caja.id)
        pid, q = next(iter(sorted(u0.por_posicion.items())))
        pos = db.get(PosicionOC, pid)
        es_bulto = True
        antes = (pos.casepack, caja.es_parcial)
        pos.casepack = int(q) + 1  # la OC planifica otra cantidad por caja
        caja.es_parcial = False
        art = pos.articulo
        prepack_antes = art.prepack_id
        # Un prepack con dos componentes para ver el reparto por talla
        otros = db.scalars(select(Articulo).where(Articulo.id != art.id).limit(2)).all()
        pp = Prepack(tipo="KIT", codigo="TKIT", estilo=art.estilo, descripcion="Test kit")
        db.add(pp)
        db.flush()
        db.add_all([PrepackComponente(prepack_id=pp.id, articulo_id=otros[0].id, cantidad=2),
                    PrepackComponente(prepack_id=pp.id, articulo_id=otros[1].id, cantidad=3)])
        art.prepack_id = pp.id
        db.commit()
        pp_id, comp = pp.id, [otros[0].sku, otros[1].sku]
        posicion = pos.posicion
    try:
        tabla = {"id": "t", "tipo": "tabla", "coleccion": "bulto.componentes", "x": 2, "y": 2, "w": 96, "h": 50, "alto_fila": 5,
                 "columnas": [{"campo": "sku", "titulo": "SKU", "ancho": 3}, {"campo": "cantidad", "titulo": "Qty"}],
                 "totales": ["cantidad"], "desborde": "resumir"}
        dis = _aprobada(interno, admin, "Package contents design", [tabla])
        _solo_esta(interno, limpiar, dis["id"], {"campo": "contexto.origen", "op": "igual", "valor": "PACKING"}, 5200)
        pedido = {"pl_id": pl_id, "modalidad": "OC_ARTICULO", "unidad": "BULTO", "tipo_empaque_id": tipo}
        plan = interno.post("/etiquetas/plan", pedido).json()
        assert all(x["plantilla"] == "Package contents design" for x in plan["grupos"]), plan["grupos"][0]
        if es_bulto:
            g = next(x for x in plan["grupos"] if any(p["codigo"] == "casepack_distinto" for p in x["problemas"]))
            aviso = next(p for p in g["problemas"] if p["codigo"] == "casepack_distinto")
            assert aviso["categoria"] == "inconsistencia" and f"Line {posicion}" in aviso["mensaje"] and f"{q:g}" in aviso["mensaje"]
        # La tabla reparte el kit en sus componentes (cantidad del componente × paquetes)
        r = interno.post("/etiquetas/reglas/probar", {"modalidad": "OC_ARTICULO", "pl_id": pl_id, "bulto": 1, "tipo_empaque_id": tipo})
        assert r.status_code == 200, r.text
        assert r.json()["plantilla"] == "Package contents design"
        with SessionLocal() as db, en_organizacion(1):
            from app.modulos.etiquetado import campos

            unidades = campos.unidades_pl(db.get(PackingList, pl_id), tipo)
            u = next(x for x in unidades if x.grupo_id == caja.id)
            filas = {f["sku"]: f["cantidad"] for f in u.valores["bulto.componentes"]}
            assert filas[comp[0]] == 2 * q and filas[comp[1]] == 3 * q
            assert sum(f["cantidad"] for f in u.valores["bulto.lineas"] if f["linea"] == posicion) == q
        # Un prepack sin componentes no se reparte: se avisa
        with SessionLocal() as db, en_organizacion(1):
            for c in db.scalars(select(PrepackComponente).where(PrepackComponente.prepack_id == pp_id)):
                db.delete(c)
            db.commit()
        plan = interno.post("/etiquetas/plan", pedido).json()
        assert any(p["codigo"] == "prepack_sin_componentes" for x in plan["grupos"] for p in x["problemas"])
    finally:
        with SessionLocal() as db, en_organizacion(1):
            p = db.scalars(select(PosicionOC).where(PosicionOC.posicion == posicion, PosicionOC.id == pos.id)).one()
            p.casepack = antes[0]
            db.get(GrupoCajas, caja.id).es_parcial = antes[1]
            db.get(Articulo, art.id).prepack_id = prepack_antes
            db.flush()
            for c in db.scalars(select(PrepackComponente).where(PrepackComponente.prepack_id == pp_id)):
                db.delete(c)
            db.delete(db.get(Prepack, pp_id))
            db.commit()
