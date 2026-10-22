"""Contenido de las etiquetas: campos lógicos con precedencia de fuentes,
política ante valores distintos y procedencia en la instantánea; tablas con
colecciones (contenido del bulto, componentes de prepacks y kits), totales
y desborde que nunca se corta en silencio; códigos compuestos con separador
y transformaciones que se leen con un lector; identificadores controlados
por una serie sin repetirse; empaque planificado frente a declarado."""
import io
import zipfile

import pytest
from etiquetado_util import aprobada, cambiar, generado, oc_con_articulos, tipo, trabajo, uso
from PIL import Image
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion
from app.modulos.etiquetado import diseno, render

zxingcpp = pytest.importorskip("zxingcpp")


def _aprobada(interno, admin, nombre, elementos, sujeto="ARTICULO", cantidad="POR_LINEA", ancho=100, alto=60):
    """Un tipo de etiqueta propio de la prueba con este diseño aprobado como el de toda la empresa."""
    t = tipo(interno, f"CONT_{nombre.upper().replace(' ', '_')[:20]}", sujeto=sujeto, cantidad=cantidad)
    p = aprobada(interno, admin, nombre, t["id"], elementos, ancho=ancho, alto=alto)
    uso(interno, t["id"], p["id"])
    return t, p


@pytest.fixture(scope="module")
def linea(interno):
    d = oc_con_articulos(interno, minimo=1)
    x = d["lineas"][0]
    return {**x, "oc_id": d["oc"]["id"], "oc": d["oc"]["numero"]}


@pytest.fixture
def limpiar(interno):
    campos_ = []
    yield campos_
    for i in campos_:
        interno.c.delete(f"/api/etiquetas/campos-logicos/{i}", headers=interno.h)


# ---- Tablas (motor de dibujo) ------------------------------------------------------------------
def _tabla(**kw):
    e = {"id": "t", "tipo": "tabla", "ajustar": "no", "coleccion": "bulto.lineas", "x": 2, "y": 2, "w": 90, "h": 30, "alto_fila": 5,
         "columnas": [{"campo": "sku", "titulo": "SKU", "ancho": 3}, {"campo": "atributo.TALLA", "titulo": "Size"},
                      {"campo": "cantidad", "titulo": "Qty", "alin": "der"}],
         "totales": ["cantidad"], "estilo": {"tam": 8, "tam_min": 6}, **kw}
    return diseno.validar({"ancho": 100, "alto": 40, "elementos": [e]})


def _filas(n):
    return [{"sku": f"SKU{i:03d}", "atributo.TALLA": str(30 + i), "cantidad": 2} for i in range(n)]


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
    filas = _filas(2) + [{"sku": "X", "atributo.TALLA": "1", "cantidad": None}]
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
         "condicion": {"campo": "producto.dato.MARCA", "op": "en", "valor": ["TNF", "VANS"]}}]})
    assert _textos(render.componer(d, {"linea.cantidad": 120, "producto.dato.MARCA": "vans"}, {})) == ["BIG", "BRAND"]
    assert _textos(render.componer(d, {"linea.cantidad": 5, "producto.dato.MARCA": "OTRA"}, {})) == []


# ---- Códigos compuestos ----------------------------------------------------------------------------
def test_codigo_compuesto_con_separador_y_transformaciones_se_lee():
    e = {"id": "c", "tipo": "codigo", "simbologia": "code128", "x": 2, "y": 2, "w": 96, "h": 26, "margen": 2,
         "partes": [{"tipo": "fijo", "texto": "po"}, {"campo": "oc.numero", "transformar": ["solo_digitos"], "rellenar": 10},
                    {"campo": "articulo.atributo.TALLA", "transformar": ["mayus", "sin_espacios"]}],
         "separador": "|"}
    d = diseno.validar({"ancho": 100, "alto": 30, "elementos": [e]})
    valores = {"oc.numero": "PO-4512", "articulo.atributo.TALLA": "x l"}
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
                                                   "fuentes": ["linea.codigo_barras", "articulo.codigo_barras"], "politica": "ADVERTIR"})
    assert r.status_code == 200, r.text
    campo = r.json()
    limpiar.append(campo["id"])
    # Validación: fuentes que no existen, clave inválida, repetida
    assert interno.post("/etiquetas/campos-logicos", {"clave": "x", "etiqueta": "X", "fuentes": ["no.existe"]}).status_code == 422
    assert interno.post("/etiquetas/campos-logicos", {"clave": "Mal Clave", "etiqueta": "X", "fuentes": ["articulo.codigo_barras"]}).status_code == 422
    assert interno.post("/etiquetas/campos-logicos", {"clave": "upc_etq", "etiqueta": "X", "fuentes": ["articulo.codigo_barras"]}).status_code == 422
    # Está en el catálogo de campos de las etiquetas de artículo
    catalogo = {c["clave"]: c for c in interno.get("/etiquetas/campos", params={"sujeto": "ARTICULO"}).json()["campos"]}
    assert "logico.upc_etq" in catalogo and "linea.codigo_barras → articulo.codigo_barras" in catalogo["logico.upc_etq"]["origen"]

    with SessionLocal() as db, en_organizacion(1):
        p = db.get(PosicionOC, linea["id"])
        antes = p.codigo_barras
        art_upc = p.articulo.codigo_barras or "000000000000"
        if not p.articulo.codigo_barras:
            p.articulo.poner_codigo("BARRAS", art_upc)
        p.codigo_barras = None
        db.commit()
    try:
        texto = [{"id": "u", "tipo": "texto", "contenido": "UPC {{logico.upc_etq}}", "x": 2, "y": 2, "w": 90, "h": 8}]
        t_, dis = _aprobada(interno, admin, "Logical field design", texto)
        base = {"oc_ids": [linea["oc_id"]], "tipos": [t_["id"]], "posiciones": [linea["id"]]}

        def registro():
            t = trabajo(interno, "OC", base)
            r = t["registros"][0]
            pv = interno.get(f"/etiquetas/trabajos/{t['id']}/registros/{r['id']}/vista-previa").json()
            return t, r, pv

        # Sin UPC en la línea sale del artículo, y se dice de dónde
        _, r, pv = registro()
        assert r["plantilla"] == "Logical field design" and pv["procedencia"]["logico.upc_etq"] == "articulo.codigo_barras"
        # Fuentes con valores distintos: ADVERTIR avisa, BLOQUEAR impide generar
        with SessionLocal() as db, en_organizacion(1):
            db.get(PosicionOC, linea["id"]).codigo_barras = "999999999999"
            db.commit()
        _, r, pv = registro()
        assert pv["procedencia"]["logico.upc_etq"] == "linea.codigo_barras"
        aviso = [x for x in r["problemas"] if x["codigo"] == "fuentes_distintas"]
        assert aviso and aviso[0]["nivel"] == "advertencia" and aviso[0]["categoria"] == "conflicto"
        r = interno.patch(f"/etiquetas/campos-logicos/{campo['id']}", {"politica": "BLOQUEAR", "version": campo["version"]})
        assert r.status_code == 200, r.text
        assert interno.patch(f"/etiquetas/campos-logicos/{campo['id']}", {"politica": "PRIMERA", "version": campo["version"]}).status_code == 409
        _, r, _ = registro()
        assert [x["nivel"] for x in r["problemas"] if x["codigo"] == "fuentes_distintas"] == ["error"]
        # PRIMERA: usa el primero sin avisar; la instantánea guarda la procedencia
        interno.patch(f"/etiquetas/campos-logicos/{campo['id']}", {"politica": "PRIMERA"})
        t, _, _ = registro()
        gen = generado(interno, t)["ejecuciones"][0]
        with SessionLocal() as db, en_organizacion(1):
            it = db.scalars(select(GeneracionItem).where(GeneracionItem.generacion_id == gen["id"])).one()
            assert it.valores["logico.upc_etq"] == "999999999999" and it.valores["_procedencia"] == {"logico.upc_etq": "linea.codigo_barras"}
        # Un campo que usa un diseño no se borra
        assert interno.c.delete(f"/api/etiquetas/campos-logicos/{campo['id']}", headers=interno.h).status_code == 409
        interno.patch(f"/etiquetas/campos-logicos/{campo['id']}", {"activo": False})
        limpiar.remove(campo["id"])
    finally:
        with SessionLocal() as db, en_organizacion(1):
            db.get(PosicionOC, linea["id"]).codigo_barras = antes
            db.commit()


# ---- Identificador controlado ---------------------------------------------------------------------------
def test_serie_controlada_sin_repetir_y_reproducible(interno, admin, linea):
    elementos = [{"id": "c", "tipo": "codigo", "simbologia": "code128", "x": 2, "y": 2, "w": 96, "h": 26, "margen": 2,
                  "partes": [{"tipo": "fijo", "texto": "LBL"}, {"campo": "etiqueta.serie"}], "separador": "-"}]
    t_, _ = _aprobada(interno, admin, "Controlled ID design", elementos, cantidad="MANUAL", ancho=100, alto=30)

    def nuevo():
        t = trabajo(interno, "OC", {"oc_ids": [linea["oc_id"]], "tipos": [t_["id"]], "posiciones": [linea["id"]]})
        return cambiar(interno, t, {"cantidades": {t["registros"][0]["clave"]: 3}})

    # Sin serie de etiquetas configurada no se genera
    r = nuevo()["registros"][0]
    assert any(x["codigo"] == "sin_serie" and x["categoria"] == "configuracion" for x in r["problemas"])
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

    g1 = generado(interno, nuevo(), formato="ZIP")["ejecuciones"][0]
    g2 = generado(interno, nuevo(), formato="ZIP")["ejecuciones"][0]
    primeros, segundos = leer(g1["id"]), leer(g2["id"])
    assert len(primeros) == 3 and len(set(primeros + segundos)) == 6, (primeros, segundos)
    numeros = [int(x.rsplit("-", 1)[1]) for x in primeros + segundos]
    assert numeros == list(range(numeros[0], numeros[0] + 6)) and all(x.startswith("LBL-E") for x in primeros)
    # Descargar de nuevo da los mismos números (no se vuelven a reservar)
    assert leer(g1["id"]) == primeros


# ---- Bulto: contenido, componentes y planificado vs declarado ---------------------------------------
def test_bulto_contenido_componentes_y_empaque_planificado(interno, admin):
    from app.modelos import Articulo, ArticuloComponente, GrupoCajas, PackingList, PosicionOC

    pls = interno.get("/etiquetas/packing").json()
    con = [x for x in pls if x["etiquetas_reales"] and interno.get(f"/etiquetas/packing/{x['id']}").json()["superiores"]]
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
        tipo_antes = art.tipo
        # El artículo de la línea pasa a ser un kit con dos componentes para ver el reparto
        otros = db.scalars(select(Articulo).where(Articulo.id != art.id, Articulo.tipo == "SOLIDO").limit(2)).all()
        art.tipo = "PREPACK"
        art.componentes.extend([ArticuloComponente(componente=otros[0], cantidad=2, organizacion_id=art.organizacion_id),
                                ArticuloComponente(componente=otros[1], cantidad=3, organizacion_id=art.organizacion_id)])
        db.commit()
        art_id, comp = art.id, [otros[0].sku, otros[1].sku]
        posicion = pos.posicion
    try:
        tabla = {"id": "t", "tipo": "tabla", "coleccion": "bulto.componentes", "x": 2, "y": 2, "w": 96, "h": 50, "alto_fila": 5,
                 "columnas": [{"campo": "sku", "titulo": "SKU", "ancho": 3}, {"campo": "cantidad", "titulo": "Qty"}],
                 "totales": ["cantidad"], "desborde": "resumir"}
        t_, _ = _aprobada(interno, admin, "Package contents design", [tabla], sujeto="BULTO", cantidad="POR_BULTO")
        pedido = {"pl_id": pl_id, "tipos": [t_["id"]], "tipo_empaque_id": tipo}
        plan = trabajo(interno, "PACKING", pedido)
        assert all(x["plantilla"] == "Package contents design" for x in plan["registros"]), plan["registros"][0]
        if es_bulto:
            g = next(x for x in plan["registros"] if any(p["codigo"] == "casepack_distinto" for p in x["problemas"]))
            aviso = next(p for p in g["problemas"] if p["codigo"] == "casepack_distinto")
            assert aviso["categoria"] == "inconsistencia" and f"Line {posicion}" in aviso["mensaje"] and f"{q:g}" in aviso["mensaje"]
        # El diseño de cada caja y por qué (el mismo resolvedor que la generación)
        r = interno.get("/etiquetas/resolver", params={"sujeto": "BULTO", "tipo_empaque_id": tipo})
        assert r.status_code == 200, r.text
        assert next(x for x in r.json()["elecciones"] if x["tipo_etiqueta_id"] == t_["id"])["plantilla"] == "Package contents design"
        # La tabla reparte el kit en sus componentes (cantidad del componente × paquetes)
        with SessionLocal() as db, en_organizacion(1):
            from app.modulos.etiquetado import campos

            unidades = campos.unidades_pl(db.get(PackingList, pl_id), tipo)
            u = next(x for x in unidades if x.grupo_id == caja.id)
            filas = {f["sku"]: f["cantidad"] for f in u.valores["bulto.componentes"]}
            assert filas[comp[0]] == 2 * q and filas[comp[1]] == 3 * q
            assert sum(f["cantidad"] for f in u.valores["bulto.lineas"] if f["linea"] == posicion) == q
        # Un pack sin contenido no se reparte: se avisa
        with SessionLocal() as db, en_organizacion(1):
            for c in list(db.get(Articulo, art_id).componentes):
                db.delete(c)
            db.commit()
        plan = trabajo(interno, "PACKING", pedido)
        assert any(p["codigo"] == "prepack_sin_componentes" for x in plan["registros"] for p in x["problemas"])
    finally:
        with SessionLocal() as db, en_organizacion(1):
            p = db.scalars(select(PosicionOC).where(PosicionOC.posicion == posicion, PosicionOC.id == pos.id)).one()
            p.casepack = antes[0]
            db.get(GrupoCajas, caja.id).es_parcial = antes[1]
            a = db.get(Articulo, art_id)
            for c in list(a.componentes):
                db.delete(c)
            a.tipo = tipo_antes
            db.commit()
