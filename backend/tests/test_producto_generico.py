"""Producto genérico: unidades que convierten entre sí, atributos de variante con
tipo, atributos de la ficha en las etiquetas y la versión del artículo que usa
cada línea de OC y de factura."""
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import Articulo, ArticuloVersion, FacturaLinea, PosicionOC


def _cat(api, catalogo, **params):
    return api.get(f"/catalogos/{catalogo}", params={"size": 200, **params}).json()["items"]


def test_unidades_que_convierten(interno):
    from app.core import listas
    from app.modulos.maestros import unidades

    unidades_ = {u["codigo"]: u for u in _cat(interno, "unidades")}
    assert unidades_["DOC"]["base"] == "UN" and unidades_["DOC"]["equivale"] == 12
    # Fuera de una petición se usan los valores de fábrica, que también convierten
    listas.usar_listas(None)
    assert unidades.a_base(3, "DOC") == (36, "UN")
    assert unidades.convertir(500, "G", "KG") == 0.5
    assert unidades.convertir(2, "DOC", "KG") is None  # magnitudes distintas
    # Una base de un solo paso, las dos partes juntas y nunca a sí misma
    jgo = unidades_["JGO"]
    for datos in ({"base": "UN"}, {"base": "JGO", "equivale": 2}, {"base": "DOC", "equivale": 2},
                  {"base": "UN", "equivale": 0}):
        assert interno.patch(f"/catalogos/unidades/{jgo['id']}", datos).status_code == 422, datos
    assert interno.patch(f"/catalogos/unidades/{unidades_['UN']['id']}", {"base": "PAR", "equivale": 2}).status_code == 422
    r = interno.patch(f"/catalogos/unidades/{jgo['id']}", {"base": "UN", "equivale": 4})
    assert r.status_code == 200, r.text
    interno.patch(f"/catalogos/unidades/{jgo['id']}", {"base": None, "equivale": None})


def test_atributos_de_variante_con_tipo(interno):
    assert interno.post("/catalogos/atributos_variante", {"codigo": "VOLTAJE", "nombre": "Voltage", "tipo": "opcion"}
                        ).status_code == 422  # sin opciones
    assert interno.post("/catalogos/atributos_variante", {"codigo": "VOLTAJE", "nombre": "Voltage", "tipo": "texto",
                                                          "unidad": "UN"}).status_code == 422  # unidad solo en números
    volt = interno.post("/catalogos/atributos_variante", {"codigo": "VOLTAJE", "nombre": "Voltage", "tipo": "opcion",
                                                          "opciones": "110 V, 220 V"}).json()
    cap = interno.post("/catalogos/atributos_variante", {"codigo": "CAPACIDAD", "nombre": "Capacity", "tipo": "numero",
                                                         "unidad": "ML"}).json()
    try:
        meta = {c["tipo"]: c for c in interno.get("/catalogos").json()}
        campo = next(c for c in meta["articulos"]["campos"] if c["nombre"] == "atr.VOLTAJE")
        assert campo["tipo"] == "opcion" and [o[0] for o in campo["opciones"]] == ["110 V", "220 V"]
        art = _cat(interno, "articulos", tipo="SOLIDO")[0]
        url = f"/catalogos/articulos/{art['id']}"
        assert interno.patch(url, {"atr.VOLTAJE": "380 V"}).status_code == 422
        assert interno.patch(url, {"atr.CAPACIDAD": "mucho"}).status_code == 422
        r = interno.patch(url, {"atr.VOLTAJE": "220 v", "atr.CAPACIDAD": "500,0"})
        assert r.status_code == 200, r.text
        assert r.json()["atr.VOLTAJE"] == "220 V" and r.json()["atr.CAPACIDAD"] == "500"
        # Con valores guardados, el tipo solo cambia si siguen valiendo
        assert interno.patch(f"/catalogos/atributos_variante/{volt['id']}", {"opciones": "110 V"}).status_code == 422
        assert interno.patch(f"/catalogos/atributos_variante/{cap['id']}", {"tipo": "texto", "unidad": None}).status_code == 200
        # En las etiquetas, el número es número
        campos = {c["clave"]: c for c in interno.get("/etiquetas/campos").json()["campos"]}
        assert campos["articulo.atributo.VOLTAJE"]["tipo"] == "texto"
        interno.patch(f"/catalogos/atributos_variante/{cap['id']}", {"tipo": "numero", "unidad": "ML"})
        campos = {c["clave"]: c for c in interno.get("/etiquetas/campos").json()["campos"]}
        assert campos["articulo.atributo.CAPACIDAD"]["tipo"] == "numero"
        interno.patch(url, {"atr.VOLTAJE": "", "atr.CAPACIDAD": ""})
    finally:
        interno.delete_(f"/catalogos/atributos_variante/{volt['id']}")
        interno.delete_(f"/catalogos/atributos_variante/{cap['id']}")


def test_atributos_de_la_ficha_en_las_etiquetas(interno):
    from app.modulos.etiquetado import campos

    with SessionLocal() as db:
        defs = campos.defs_ficha(db)
        a = next(x for x in db.scalars(select(Articulo).where(Articulo.producto_id.is_not(None)))
                 if x.producto.ficha and set(x.producto.ficha) & set(defs))
        v = campos.valores_articulo(a)
        clave = next(k for k in a.producto.ficha if k in defs and a.producto.ficha[k] not in (None, "", [], {}))
        d = defs[clave]
        assert v[f"producto.atributo.{clave}"] == campos.texto_ficha(d, a.producto.ficha[clave])
        if d["tipo"] == "select":
            assert v[f"producto.atributo.{clave}"] == d["opciones"].get(a.producto.ficha[clave], a.producto.ficha[clave])
    claves = {c["clave"] for c in interno.get("/etiquetas/campos", params={"sujeto": "ARTICULO"}).json()["campos"]}
    assert f"producto.atributo.{clave}" in claves
    assert campos.texto_ficha({"tipo": "multi_select", "opciones": {"a": "Alpha"}}, ["a", "b"]) == "Alpha, b"
    assert campos.texto_ficha({"tipo": "boolean", "opciones": {}}, False) == "No"


def test_cada_linea_guarda_la_version_del_articulo(interno):
    with SessionLocal() as db:
        p = db.scalars(select(PosicionOC).where(PosicionOC.articulo_id.is_not(None))).first()
        assert p.articulo_version_id is not None, "las líneas de la demo toman su versión al crearse"
        a = p.articulo
        vieja = p.articulo_version_id

        def linea(n):
            x = PosicionOC(oc_id=p.oc_id, posicion=n, articulo_id=a.id, codigo_articulo=a.sku, cantidad=1, unidad=p.unidad,
                           organizacion_id=p.organizacion_id)
            db.add(x)
            db.flush()
            return x

        antes = linea("9900").articulo_version
        assert antes.datos["articulo"]["sku"] == a.sku
        # Sin cambios en el artículo, una línea nueva comparte la versión
        nueva = linea("9901")
        assert nueva.articulo_version_id == antes.id
        # El artículo cambia: la línea vieja conserva su versión y la nueva lleva otra
        descripcion = a.descripcion
        a.descripcion = (descripcion or "") + " v2"
        otra = linea("9902")
        assert otra.articulo_version.numero == antes.numero + 1
        assert otra.articulo_version.datos["articulo"]["descripcion"] == a.descripcion
        db.refresh(p)
        assert p.articulo_version_id == vieja and nueva.articulo_version_id == antes.id
        # Una línea de factura toma la versión del artículo al facturar
        f = db.scalars(select(FacturaLinea)).first()
        assert f.articulo_version_id is not None
        assert db.get(ArticuloVersion, f.articulo_version_id).articulo_id == f.posicion_oc.articulo_id
        db.commit()
        aid, numero = a.id, otra.articulo_version.numero
        ids = [x.id for x in db.scalars(select(PosicionOC).where(PosicionOC.posicion.in_(("9900", "9901", "9902")),
                                                                 PosicionOC.oc_id == p.oc_id))]
    try:
        versiones = interno.get(f"/catalogos/articulos/{aid}/versiones").json()
        assert versiones[0]["numero"] == numero and versiones[0]["lineas_oc"] == 1
        assert {"campo": "articulo.descripcion", "antes": descripcion, "despues": (descripcion or "") + " v2"} \
            in versiones[0]["cambios"]
    finally:
        with SessionLocal() as db:
            for i in ids:
                db.delete(db.get(PosicionOC, i))
            db.get(Articulo, aid).descripcion = descripcion
            db.commit()


def test_un_proveedor_no_ve_las_versiones_de_otro(tnf, vans):
    from app.modelos import Proveedor

    with SessionLocal() as db:
        nf = db.scalar(select(Proveedor.id).where(Proveedor.nombre == "The North Face"))
        propio = db.scalar(select(Articulo.id).where(Articulo.proveedor_id == nf))
    assert tnf.get(f"/catalogos/articulos/{propio}/versiones").status_code == 200
    assert vans.get(f"/catalogos/articulos/{propio}/versiones").status_code == 404


def test_producto_sin_estilo_ni_talla(interno):
    """Un químico o una materia prima: sin estilo, color ni talla. Sus variantes se
    distinguen por los atributos que la empresa define."""
    base = _cat(interno, "articulos", tipo="SOLIDO")[0]
    conc = interno.post("/catalogos/atributos_variante", {"codigo": "CONC", "nombre": "Concentration", "tipo": "numero",
                                                          "unidad": "UN"}).json()
    comunes = {"generico": "QUIM-001", "marca_id": base["marca_id"], "grupo_id": base["grupo_id"],
               "proveedor_id": base["proveedor_id"], "tipo": "SOLIDO", "unidad": "L"}
    creados = []
    try:
        r = interno.post("/catalogos/articulos", {**comunes, "sku": "QUIM-001-30", "atr.CONC": "30"})
        assert r.status_code == 200, r.text
        creados.append(r.json()["id"])
        assert r.json()["estilo"] is None and r.json()["talla"] is None
        r = interno.post("/catalogos/articulos", {**comunes, "sku": "QUIM-001-50", "atr.CONC": "50"})
        assert r.status_code == 200, r.text
        creados.append(r.json()["id"])
        # Dos variantes del mismo producto no repiten sus valores
        r = interno.post("/catalogos/articulos", {**comunes, "sku": "QUIM-001-XX", "atr.CONC": "50"})
        assert r.status_code == 422 and "QUIM-001-50" in r.text
        with SessionLocal() as db:
            arts = [db.get(Articulo, i) for i in creados]
            assert {a.producto_id for a in arts} == {arts[0].producto_id} and arts[0].producto_id is not None
            assert arts[0].producto.codigo_generico == "QUIM-001" and arts[0].producto.estilo is None
        # Un producto sin variantes: su código es el del artículo
        r = interno.post("/catalogos/articulos", {**comunes, "generico": None, "sku": "RESINA-9"})
        assert r.status_code == 200, r.text
        creados.append(r.json()["id"])
        with SessionLocal() as db:
            assert db.get(Articulo, creados[-1]).producto.codigo_generico == "RESINA-9"
    finally:
        with SessionLocal() as db:
            for i in creados:
                a = db.get(Articulo, i)
                p = a.producto
                db.delete(a)
                db.flush()
                if p is not None and not p.articulos:
                    db.delete(p)
            db.commit()
        interno.delete_(f"/catalogos/atributos_variante/{conc['id']}")


def test_talla_y_color_son_valores_de_variante():
    with SessionLocal() as db:
        a = db.scalars(select(Articulo).where(Articulo.tipo == "SOLIDO", Articulo.talla.is_not(None))).first()
        assert a.variantes.get("TALLA") == a.talla and a.variantes.get("COLOR") == a.color
        talla = a.talla
        # Cambiar la columna pasa a su valor; cambiar el valor pasa a la columna
        a.talla = "ZZ"
        db.flush()
        assert a.variantes["TALLA"] == "ZZ"
        a.variantes = {**a.variantes, "TALLA": talla}
        db.flush()
        assert a.talla == talla
        db.rollback()


def test_ejes_de_variante_por_familia(interno):
    from app.modelos import GrupoProducto
    from app.modulos.maestros import variantes

    arbol = interno.get("/grupos-producto").json()
    familia = next(g for g in arbol if g["clase"] == "FAMILIA")
    assert interno.patch(f"/grupos-producto/{familia['id']}", {"ejes_variante": ["NOEXISTE"]}).status_code == 422
    r = interno.patch(f"/grupos-producto/{familia['id']}", {"ejes_variante": ["COLOR", "TALLA"]})
    assert r.status_code == 200, r.text
    try:
        with SessionLocal() as db:
            hija = db.scalars(select(GrupoProducto).where(GrupoProducto.padre_id == familia["id"])).first()
            if hija is not None:  # sin ejes propios, hereda los de la familia
                assert variantes.ejes_de_grupo(hija) == ["COLOR", "TALLA"]
            assert variantes.ejes_de_grupo(db.get(GrupoProducto, familia["id"])) == ["COLOR", "TALLA"]
            assert variantes.texto(variantes.ordenar(db, {"TALLA": "9", "COLOR": "BLACK"})) in ("BLACK · 9", "9 · BLACK")
    finally:
        interno.patch(f"/grupos-producto/{familia['id']}", {"ejes_variante": []})


def test_las_lineas_guardan_su_variante():
    with SessionLocal() as db:
        p = db.scalars(select(PosicionOC).where(PosicionOC.articulo_id.is_not(None), PosicionOC.talla.is_not(None))).first()
        assert p.variante and p.variante.get("TALLA") == p.talla
        f = db.scalars(select(FacturaLinea).where(FacturaLinea.posicion_oc_id == p.id)).first() \
            or db.scalars(select(FacturaLinea)).first()
        assert f.variante == f.posicion_oc.variante
