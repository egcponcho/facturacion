"""El servicio del catálogo: fichas armadas de artículos y productos, y consultas
de ids para filtrar, sobre la demostración."""
from app.core.db import SessionLocal
from app.modulos.catalogo import servicio as catalogo


def test_ficha_de_una_variante_y_de_un_pack(client):
    with SessionLocal() as db:
        v = catalogo.por_codigo(db, "30095125070")
        assert v is not None and not v.es_pack and v.activo
        assert v.valores == {"COLOR": "BLK Black", "TALLA": "7"} and v.texto_variante == "BLK Black · 7"
        assert v.producto_codigo == "30095125" and v.datos["MODELO"] == "VN000EE3" and v.marca == "VANS"
        assert v.familia is not None and v.familia.codigo == "FOOTWEAR" and v.familia.ruta_codigos[-1] == "FOOTWEAR"
        pack = next(a for a in catalogo.de_producto(db, v.producto_id) if a.es_pack)
        assert pack.codigo_pack == "AB12" and pack.total_componentes == 12 and not pack.es_kit
        assert {c.codigo for c in pack.componentes} >= {"30095125070", "30095125120"}
        assert pack.texto_variante == "pack AB12"
        # En lote: una ficha por id existente
        fichas = catalogo.articulos(db, [v.id, pack.id, None, 999999])
        assert set(fichas) == {v.id, pack.id}


def test_consultas_de_ids(client):
    with SessionLocal() as db:
        v = catalogo.por_codigo(db, "30095125070")

        def codigos(**filtros):
            return {f.codigo for f in catalogo.articulos(db, db.scalars(catalogo.ids(**filtros))).values()}

        vans = codigos(marca="VANS")
        assert "30095125070" in vans and not any(c.startswith("300951") and c[:8] in ("30095123", "30095124") for c in vans)
        # Por valores de variante, sin distinguir mayúsculas
        assert codigos(producto_id=v.producto_id, valores={"TALLA": ["7", "8"]}) == {"30095125070", "30095125080"}
        assert codigos(producto_id=v.producto_id, valores={"COLOR": ["blk black"], "TALLA": ["12"]}) == {"30095125120"}
        # La familia incluye sus subfamilias y categorías
        assert "30095125070" in codigos(familia_id=v.familia.id)
        assert codigos(texto="AB12", producto_id=v.producto_id) == {pack.codigo for pack in catalogo.de_producto(db, v.producto_id)
                                                                  if pack.es_pack}
        # Valores distintos por atributo, en su orden
        distintos = catalogo.valores_distintos(db, catalogo.ids(producto_id=v.producto_id))
        assert distintos["TALLA"] == ["7", "8", "9", "10", "11", "12"] and distintos["COLOR"] == ["BLK Black"]
        assert catalogo.marcas_de(db, catalogo.ids(producto_id=v.producto_id)) == ["VANS"]


def test_ruta_de_reglas_y_producto(client):
    with SessionLocal() as db:
        v = catalogo.por_codigo(db, "30095125070")
        ruta = catalogo.ruta_reglas(db, v)
        assert ruta and ruta[-1] == v.familia.ruta_ids[0] and v.familia.id in ruta
        p = catalogo.producto(db, v.producto_id)
        assert p.codigo == "30095125" and p.marca == "VANS" and p.familia == v.familia
        assert catalogo.producto_por_codigo(db, "30095125") == p
        assert [b.codigo for b in catalogo.buscar(db, "30095125", limite=3)] == ["30095125001", "30095125070", "30095125080"]


def test_atributos_y_valores(client):
    with SessionLocal() as db:
        variante = {a["codigo"]: a for a in catalogo.atributos(db)}
        assert {"COLOR", "TALLA"} <= set(variante) and "MARCA" not in variante
        assert "MARCA" in {a["codigo"] for a in catalogo.atributos(db, "PRODUCTO")}
        assert list(catalogo.ordenar(db, {"TALLA": "9", "COLOR": "RED"})) == ["COLOR", "TALLA"]
        assert catalogo.texto({"COLOR": "RED", "TALLA": "9"}) == "RED · 9" and catalogo.texto({}) is None
        assert catalogo.marca(db, {"MARCA": "TNF", "MODELO": "X"}) == "TNF"
