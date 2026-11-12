"""El módulo de productos no trae nada fijo de un rubro: la regla del código de
variante es de la empresa, el orden de los valores sale de sus opciones y
escalas, la lista filtra por cualquier atributo y por familia, la ficha muestra
sus atributos y el resumen solo cuenta códigos de barras si alguien los exige."""
import json
import sqlite3
import subprocess
import sys
import tempfile

from conftest import familia_demo
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import Producto


def _borrar(gen):
    with SessionLocal() as db:
        p = db.scalar(select(Producto).where(Producto.codigo_generico == gen))
        if p is not None:
            for a in list(p.articulos):
                db.delete(a)
            db.flush()
            db.delete(p)
        db.commit()


def test_regla_de_codigo_de_variante_de_la_empresa(admin, interno):
    """Sin escala, el código de la variante sale de la regla de la empresa (la demo usa valor × 10)."""
    org = admin.get("/organizacion").json()
    antes = org["productos"]["codigo_variante"]
    assert antes == {"regla": "MULTIPLICAR", "factor": 10, "longitud": 3}
    assert {r["clave"] for r in org["reglas_codigo"]} == {"MULTIPLICAR", "CONSECUTIVO", "VALOR"}
    # Una regla que no existe, o «valor × factor» sin factor, no se guarda; un proveedor no la cambia
    assert admin.put("/organizacion", {"productos": {"codigo_variante": {"regla": "TALLA"}}}).status_code == 422
    assert admin.put("/organizacion", {"productos": {"codigo_variante": {"regla": "MULTIPLICAR"}}}).status_code == 422
    assert admin.put("/organizacion", {"productos": {"otra": 1}}).status_code == 422
    assert interno.put("/organizacion", {"productos": {"codigo_variante": {"regla": "CONSECUTIVO"}}}).status_code == 403
    r = admin.put("/organizacion", {"productos": {"codigo_variante": {"regla": "CONSECUTIVO", "longitud": 2}}})
    assert r.status_code == 200, r.text
    assert r.json()["productos"]["codigo_variante"] == {"regla": "CONSECUTIVO", "factor": None, "longitud": 2}
    try:
        r = interno.post("/catalogos/genericos", {"generico": "REGLA01", "nombre": "Rule test", "unidad": "UN", "grupo_producto_id": familia_demo(),
                                                  "variantes": [{"valores": {"TALLA": "7"}}, {"valores": {"TALLA": "8"}}]})
        assert r.status_code == 200, r.text
        assert sorted(v["sku"] for v in r.json()["variantes"]) == ["REGLA0101", "REGLA0102"]
    finally:
        _borrar("REGLA01")
        admin.put("/organizacion", {"productos": {"codigo_variante": antes}})
    assert admin.get("/organizacion").json()["productos"]["codigo_variante"] == antes


def test_orden_de_los_valores_sin_lista_fija():
    from app.modulos.maestros import variantes

    # Números: como números, con tramos
    assert variantes.rango(["9", "7", "8", "11"]) == "7–9, 11"
    # Otros valores: sin orden de la empresa, como vienen (ninguna lista de tallas fija)
    assert variantes.rango(["M", "S", "L"]) == "M, S, L"
    # Con el orden de la empresa (sus opciones o escalas), en ese orden y con tramos
    assert variantes.rango(["M", "S", "L"], ["S", "M", "L", "XL"]) == "S–L"
    assert variantes.rango(["1 L", "250 ML"], ["250 ML", "500 ML", "1 L"]) == "250 ML, 1 L"
    with SessionLocal() as db:
        orden = variantes.orden_de_valores(db)["TALLA"]
        # La escala de letras de la demo ordena las tallas de ropa
        assert orden.index("S") < orden.index("M") < orden.index("L")


def test_lista_de_productos_por_atributo_y_familia(interno):
    op = interno.get("/productos/opciones").json()
    assert {a["codigo"] for a in op["atributos"]} >= {"MARCA", "MODELO"}
    total = interno.get("/productos", params={"estado": "", "size": 1}).json()["total"]
    marcas = interno.get("/productos/valores", params={"estado": "", "columna": "atr.MARCA"}).json()
    assert {v["valor"] for v in marcas} >= {"VANS", "TNF"}
    vans = next(v for v in marcas if v["valor"] == "VANS")
    r = interno.get("/productos", params={"estado": "", "size": 200, "f": json.dumps({"atr.MARCA": ["VANS"]})}).json()
    assert r["total"] == vans["n"] and all(p["atributos"]["MARCA"] == "VANS" for p in r["items"])
    # La familia: valor de la fila y filtro por su nombre
    familias = interno.get("/productos/valores", params={"estado": "", "columna": "familia"}).json()
    assert sum(v["n"] for v in familias) == total
    fam = next(v for v in familias if v["valor"])
    r = interno.get("/productos", params={"estado": "", "size": 200, "f": json.dumps({"familia": [fam["valor"]]})}).json()
    assert r["total"] == fam["n"] and {p["familia"] for p in r["items"]} == {fam["valor"]}
    # Se ordena por familia
    r = interno.get("/productos", params={"estado": "", "size": 200, "orden": "familia:asc"}).json()["items"]
    nombres = [p["familia"] for p in r if p["familia"]]
    assert nombres == sorted(nombres)


def test_la_ficha_muestra_la_familia_y_los_atributos(interno):
    p = next(x for x in interno.get("/productos", params={"estado": "", "size": 50}).json()["items"]
             if x["atributos"].get("MODELO") == "VN000EE3")
    d = interno.get(f"/productos/{p['id']}").json()
    atr = {a["codigo"]: a for a in d["atributos_txt"]}
    assert atr["MARCA"]["valor"] == "Vans" and atr["MODELO"]["valor"] == "VN000EE3" and atr["MARCA"]["nombre"]
    assert d["familia"]


def test_el_resumen_cuenta_codigos_de_barras_solo_si_se_exigen(admin, interno):
    antes = next(c for c in interno.get("/catalogos").json() if c["tipo"] == "articulos")["gobierno"]
    base = interno.get("/productos/resumen").json()["exige_codigo_barras"]
    assert admin.put("/catalogos/articulos/gobierno", {"responsables": [], "obligatorios": ["codigo_barras"]}).status_code == 200
    try:
        assert interno.get("/productos/resumen").json()["exige_codigo_barras"] is True
    finally:
        admin.put("/catalogos/articulos/gobierno", {"responsables": [x["id"] for x in antes["responsables"]],
                                                     "obligatorios": antes["obligatorios"]})
    assert interno.get("/productos/resumen").json()["exige_codigo_barras"] is base


def test_plantilla_de_caja_sin_unidad_toma_la_de_los_articulos(vans):
    from app.modulos.maestros.unidades import de_articulo

    r = vans.post("/plantillas", {"nombre": "Sin unidad", "cantidad_por_caja": 6})
    assert r.status_code == 200, r.text
    assert r.json()["unidad"] == de_articulo()[0]


def test_migracion_conserva_la_regla_de_las_empresas_con_articulos():
    """0093: la empresa que ya tenía artículos conserva la regla de antes (valor × 10); la que no
    tenía ninguno toma la de fábrica. Revertir quita la opción."""
    from test_oficial import RAIZ

    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        r = subprocess.run(alembic + ["upgrade", "0092"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        c = sqlite3.connect(f"{tmp}/m.db")
        for oid, cod in ((1, "UNO"), (2, "DOS")):
            if not c.execute("SELECT id FROM organizaciones WHERE id = ?", (oid,)).fetchone():
                c.execute("INSERT INTO organizaciones (id, codigo, nombre, configuracion, activa, creada_en)"
                          " VALUES (?, ?, ?, '{}', 1, '2026-01-01')", (oid, cod, cod))
        c.execute("INSERT INTO productos (id, organizacion_id, codigo_generico, nombre, ficha, faltan, estado, version,"
                  " version_ficha, ficha_completa, creado_en, actualizado_en)"
                  " VALUES (1, 1, 'P1', 'P1', '{}', '[]', 'borrador', 1, 1, 0, '2026-01-01', '2026-01-01')")
        c.execute("INSERT INTO articulos (id, organizacion_id, sku, producto_id, unidad, tipo, activo)"
                  " VALUES (1, 1, 'P1070', 1, 'UN', 'SOLIDO', 1)")
        c.commit()
        r = subprocess.run(alembic + ["upgrade", "0093"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        conf = {i: json.loads(x or "{}") for i, x in c.execute("SELECT id, configuracion FROM organizaciones")}
        assert conf[1]["productos"]["codigo_variante"] == {"regla": "MULTIPLICAR", "factor": 10, "longitud": 3}
        assert "productos" not in conf[2]
        r = subprocess.run(alembic + ["downgrade", "0092"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        conf = {i: json.loads(x or "{}") for i, x in c.execute("SELECT id, configuracion FROM organizaciones")}
        assert "productos" not in conf[1]
        c.close()
