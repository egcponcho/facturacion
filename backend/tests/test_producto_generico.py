"""Producto genérico: unidades que convierten entre sí, atributos de variante con
tipo, atributos de la ficha en las etiquetas, códigos y valores de variante,
packs y kits, y la versión del artículo (y la foto de sus atributos) que usa
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
    assert interno.post("/catalogos/atributos", {"general": True, "nivel": "VARIANTE", "codigo": "VOLTAJE", "nombre": "Voltage", "tipo": "opcion"}
                        ).status_code == 422  # sin opciones
    assert interno.post("/catalogos/atributos", {"general": True, "nivel": "VARIANTE", "codigo": "VOLTAJE", "nombre": "Voltage", "tipo": "texto",
                                                          "unidad": "UN"}).status_code == 422  # unidad solo en números
    volt = interno.post("/catalogos/atributos", {"general": True, "nivel": "VARIANTE", "codigo": "VOLTAJE", "nombre": "Voltage", "tipo": "opcion",
                                                          "opciones": "110 V, 220 V"}).json()
    cap = interno.post("/catalogos/atributos", {"general": True, "nivel": "VARIANTE", "codigo": "CAPML", "nombre": "Capacity", "tipo": "numero",
                                                         "unidad": "ML"}).json()
    try:
        meta = {c["tipo"]: c for c in interno.get("/catalogos").json()}
        campo = next(c for c in meta["articulos"]["campos"] if c["nombre"] == "atr.VOLTAJE")
        assert campo["tipo"] == "opcion" and [o[0] for o in campo["opciones"]] == ["110 V", "220 V"]
        art = _cat(interno, "articulos", tipo="SOLIDO")[0]
        guardados = {k: v for k, v in art.items() if k.startswith("atr.")}
        url = f"/catalogos/articulos/{art['id']}"
        assert interno.patch(url, {"atr.VOLTAJE": "380 V"}).status_code == 422
        assert interno.patch(url, {"atr.CAPML": "mucho"}).status_code == 422
        r = interno.patch(url, {"atr.VOLTAJE": "220 v", "atr.CAPML": "500,0"})
        assert r.status_code == 200, r.text
        assert r.json()["atr.VOLTAJE"] == "220 V" and r.json()["atr.CAPML"] == "500"
        # Con valores guardados, el tipo solo cambia si siguen valiendo
        assert interno.patch(f"/catalogos/atributos/{volt['id']}", {"opciones": "110 V"}).status_code == 422
        assert interno.patch(f"/catalogos/atributos/{cap['id']}", {"tipo": "texto", "unidad": None}).status_code == 200
        # En las etiquetas, el número es número
        campos = {c["clave"]: c for c in interno.get("/etiquetas/campos").json()["campos"]}
        assert campos["articulo.atributo.VOLTAJE"]["tipo"] == "texto"
        interno.patch(f"/catalogos/atributos/{cap['id']}", {"tipo": "numero", "unidad": "ML"})
        campos = {c["clave"]: c for c in interno.get("/etiquetas/campos").json()["campos"]}
        assert campos["articulo.atributo.CAPML"]["tipo"] == "numero"
        interno.patch(url, {"atr.VOLTAJE": "", "atr.CAPML": "", **guardados})
    finally:
        interno.delete_(f"/catalogos/atributos/{volt['id']}")
        interno.delete_(f"/catalogos/atributos/{cap['id']}")


def test_atributos_de_la_ficha_en_las_etiquetas(interno):
    from app.modulos.catalogo import servicio as catalogo
    from app.modulos.comex import servicio as comex
    from app.modulos.etiquetado import campos

    with SessionLocal() as db:
        defs = comex.defs_ficha(db)
        a = next(x for x in db.scalars(select(Articulo).where(Articulo.producto_id.is_not(None)))
                 if x.producto.comex.ficha and set(x.producto.comex.ficha) & set(defs))
        v = campos.valores_articulo(db, catalogo.articulo(db, a.id))
        clave = next(k for k in a.producto.comex.ficha if k in defs and a.producto.comex.ficha[k] not in (None, "", [], {}))
        d = defs[clave]
        assert v[f"producto.atributo.{clave}"] == comex.texto_ficha(d, a.producto.comex.ficha[clave])
        if d["tipo"] == "select":
            assert v[f"producto.atributo.{clave}"] == d["opciones"].get(a.producto.comex.ficha[clave], a.producto.comex.ficha[clave])
    claves = {c["clave"] for c in interno.get("/etiquetas/campos", params={"sujeto": "ARTICULO"}).json()["campos"]}
    assert f"producto.atributo.{clave}" in claves
    assert comex.texto_ficha({"tipo": "multi_select", "opciones": {"a": "Alpha"}}, ["a", "b"]) == "Alpha, b"
    assert comex.texto_ficha({"tipo": "boolean", "opciones": {}}, False) == "No"


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


def test_producto_sin_atributos_de_moda(interno):
    """Un químico o una materia prima: sin marca, modelo, color ni talla. Sus variantes se
    distinguen por los atributos que la empresa define."""
    from app.modelos import Producto

    conc = interno.post("/catalogos/atributos", {"general": True, "nivel": "VARIANTE", "codigo": "CONC", "nombre": "Concentration",
                                                 "tipo": "numero", "unidad": "UN"}).json()
    try:
        r = interno.post("/catalogos/genericos", {"generico": "QUIM-001", "nombre": "Solvent", "unidad": "L",
                                                  "variantes": [{"valores": {"CONC": "30"}}, {"valores": {"CONC": "50,0"}}]})
        assert r.status_code == 200, r.text
        assert r.json()["atributos"] == {} and r.json()["creadas"] == 2
        assert sorted(v["valores"]["CONC"] for v in r.json()["variantes"]) == ["30", "50"]
        # Dos variantes del mismo producto no repiten sus valores
        r = interno.post("/catalogos/genericos/QUIM-001/variantes", {"variantes": [{"valores": {"CONC": "50"}}]})
        assert r.status_code == 422 and "already exists" in r.text
        # Un atributo de variante que no existe, o un valor que no vale para su tipo
        r = interno.post("/catalogos/genericos/QUIM-001/variantes", {"variantes": [{"valores": {"NOEXISTE": "1"}}]})
        assert r.status_code == 422
        r = interno.post("/catalogos/genericos/QUIM-001/variantes", {"variantes": [{"valores": {"CONC": "mucho"}}]})
        assert r.status_code == 422
        with SessionLocal() as db:
            p = db.scalar(select(Producto).where(Producto.codigo_generico == "QUIM-001"))
            assert p.atributos == [] and p.marca_codigo is None and len(p.articulos) == 2
            assert all(a.generico == "QUIM-001" and a.unidad == "L" for a in p.articulos)
        # Un producto sin variantes: su código es el del artículo
        r = interno.post("/catalogos/articulos", {"sku": "RESINA-9", "tipo": "SOLIDO", "unidad": "KG"})
        assert r.status_code == 200, r.text
        with SessionLocal() as db:
            assert db.scalar(select(Articulo).where(Articulo.sku == "RESINA-9")).producto.codigo_generico == "RESINA-9"
    finally:
        with SessionLocal() as db:
            for gen in ("QUIM-001", "RESINA-9"):
                p = db.scalar(select(Producto).where(Producto.codigo_generico == gen))
                if p is not None:
                    for a in list(p.articulos):
                        db.delete(a)
                    db.flush()
                    db.delete(p)
            db.commit()
        interno.delete_(f"/catalogos/atributos/{conc['id']}")


def test_codigos_y_valores_de_variante():
    """Los valores de variante viven en articulo_atributos y los códigos en articulo_codigos
    (barras, proveedor, pack); el artículo no tiene columnas de talla, color ni códigos."""
    from app.modelos import ArticuloCodigo

    with SessionLocal() as db:
        a = db.scalars(select(Articulo).where(Articulo.tipo == "SOLIDO")).first()
        assert set(a.variantes) == {"COLOR", "TALLA"}
        for col in ("talla", "color", "estilo", "upc", "sku_proveedor", "marca_id", "grupo_id"):
            assert col not in Articulo.__table__.c, col
        barras = a.codigo_barras
        assert barras and a.codigo("BARRAS") == barras
        # Cambiar un valor de variante y un código
        a.variantes = {**a.variantes, "TALLA": "ZZ"}
        a.poner_codigo("BARRAS", "7790000000001")
        db.flush()
        db.expire(a)
        assert a.variantes["TALLA"] == "ZZ" and a.codigo_barras == "7790000000001"
        assert db.scalar(select(ArticuloCodigo.valor).where(ArticuloCodigo.articulo_id == a.id,
                                                            ArticuloCodigo.tipo == "BARRAS")) == "7790000000001"
        # Sin valor, el código se quita
        a.poner_codigo("BARRAS", None)
        db.flush()
        db.expire(a)
        assert a.codigo_barras is None
        db.rollback()


def test_ejes_de_variante_por_familia(interno):
    """Las variantes de una familia se distinguen por los atributos de variante que valen en ella
    (los suyos y los de las familias que la contienen), en el orden de los atributos."""
    from app.modelos import GrupoProducto
    from app.modulos.maestros import variantes

    arbol = interno.get("/grupos-producto").json()
    calzado = next(g for g in arbol if g["codigo"] == "FOOTWEAR")
    tecnico = next(g for g in arbol if g["codigo"] == "FOOTWEAR-TECH")
    accesorios = next(g for g in arbol if g["codigo"] == "ACCESSORIES")
    assert calzado["ejes"] == ["COLOR", "TALLA"] and tecnico["ejes"] == ["COLOR", "TALLA"] and accesorios["ejes"] == ["COLOR"]
    assert tecnico["atributos"] == [] and "CORTE" in tecnico["atributos_producto"]  # heredados de Footwear
    assert "CAPACIDAD" in accesorios["atributos_producto"] and "CORTE" not in accesorios["atributos_producto"]
    assert interno.patch(f"/grupos-producto/{calzado['id']}", {"atributos": ["NOEXISTE"]}).status_code == 422
    with SessionLocal() as db:
        hija = db.get(GrupoProducto, tecnico["id"])
        assert variantes.ejes_de_grupo(db, hija) == ["COLOR", "TALLA"]
        assert variantes.ejes_de_grupo(db, None) == []  # sin familia: solo los generales (ninguno de variante)
        assert variantes.texto(variantes.ordenar(db, {"TALLA": "9", "COLOR": "BLACK"})) == "BLACK · 9"


def test_las_lineas_guardan_su_variante():
    """Cada línea guarda la foto de los atributos del producto y de su variante al crearse."""
    with SessionLocal() as db:
        p = db.scalars(select(PosicionOC).where(PosicionOC.articulo_id.is_not(None))
                       .join(Articulo, Articulo.id == PosicionOC.articulo_id).where(Articulo.tipo == "SOLIDO")).first()
        assert p.variante and p.variante == p.articulo.variantes
        assert p.atributos and p.atributos.get("MODELO") == p.articulo.producto.valores.get("MODELO")
        assert p.codigo_barras == p.articulo.codigo_barras
        f = db.scalars(select(FacturaLinea).where(FacturaLinea.posicion_oc_id == p.id)).first() \
            or db.scalars(select(FacturaLinea)).first()
        assert f.variante == f.posicion_oc.variante and f.atributos == f.posicion_oc.atributos


def test_packs_y_kits_genericos(interno):
    """Un pack junta variantes de un mismo producto (no hace falta modelo ni color);
    un kit junta artículos de cualquier producto y es su propio producto."""
    from app.modelos import Producto
    from app.modulos.maestros import unidades as u

    base = _cat(interno, "articulos", tipo="SOLIDO")[0]
    sabor = interno.post("/catalogos/atributos", {"general": True, "nivel": "VARIANTE", "codigo": "SABOR", "nombre": "Flavor"}).json()
    try:
        r = interno.post("/catalogos/genericos", {"generico": "SALSA-01", "nombre": "Sauce", "unidad": "UN",
                                                  "combinar": {"SABOR": ["Hot", "Mild"]}})
        assert r.status_code == 200, r.text
        ids = [v["id"] for v in r.json()["variantes"]]
        r = interno.post("/catalogos/compuestos", {"tipo": "PACK", "sku": "SALSA-01-MIX", "codigo": "MX6",
                                                   "codigo_barras": "7790000000099",
                                                   "componentes": [{"articulo_id": ids[0], "cantidad": 3},
                                                                   {"articulo_id": ids[1], "cantidad": 3}]})
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 6 and r.json()["unidad"] == u.de_compuesto() and r.json()["codigo"] == "MX6"
        assert r.json()["generico"] == "SALSA-01" and not r.json()["kit"]
        with SessionLocal() as db:
            pack = db.scalar(select(Articulo).where(Articulo.sku == "SALSA-01-MIX"))
            assert pack.producto_id == db.get(Articulo, ids[0]).producto_id
            assert pack.codigo_pack == "MX6" and pack.codigo_barras == "7790000000099"
        # El mismo identificador no se repite en el producto
        r = interno.post("/catalogos/compuestos", {"tipo": "PACK", "sku": "SALSA-01-MIX2", "codigo": "MX6",
                                                   "componentes": [{"articulo_id": ids[0], "cantidad": 1}]})
        assert r.status_code == 422 and "MX6" in r.text
        # Otro producto no entra en el pack: va en un kit
        mixto = [{"articulo_id": ids[0], "cantidad": 1}, {"articulo_id": base["id"], "cantidad": 1}]
        r = interno.post("/catalogos/compuestos", {"tipo": "PACK", "sku": "SALSA-01-MAL", "codigo": "MX7",
                                                   "componentes": mixto})
        assert r.status_code == 422 and "kit" in r.text.lower()
        r = interno.post("/catalogos/compuestos", {"tipo": "KIT", "sku": "KIT-SALSA", "codigo": "KS1", "componentes": mixto})
        assert r.status_code == 200, r.text
        assert r.json()["kit"] and r.json()["generico"] == "KIT-SALSA"
        # Un pack no lleva otro pack
        with SessionLocal() as db:
            pid = db.scalar(select(Articulo.id).where(Articulo.sku == "SALSA-01-MIX"))
        r = interno.post("/catalogos/compuestos", {"tipo": "KIT", "sku": "KIT-MAL", "codigo": "KM1",
                                                   "componentes": [{"articulo_id": pid, "cantidad": 1}]})
        assert r.status_code == 422
    finally:
        with SessionLocal() as db:
            for gen in ("KIT-SALSA", "SALSA-01"):
                p = db.scalar(select(Producto).where(Producto.codigo_generico == gen))
                if p is None:
                    continue
                # Primero los compuestos (su contenido apunta a las variantes)
                for a in sorted(p.articulos, key=lambda x: x.tipo != "PREPACK"):
                    db.delete(a)
                    db.flush()
                db.delete(p)
                db.flush()
            db.commit()
        interno.delete_(f"/catalogos/atributos/{sabor['id']}")
