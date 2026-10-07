"""Un solo vocabulario de atributos: un paquete que trae un atributo que ya
existe con otro código lo declara «Same as» y se reutiliza (alias), nunca se
duplica; las condiciones solo nombran atributos o campos del producto."""
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AtributoDef, ReglaClasificacion
from test_oficial import _cargar, _libro

ATTRS = ["Attribute code", "Label", "Data type", "Default unit", "Multi-select", "Used by classification", "Domain hint", "Description", "Same as"]
REGLAS = ["Rule ID", "Scope type", "Scope code", "Rule type", "Priority", "Source type", "Rule family", "Rationale / effect", "Active", "Requires review"]
CONDS = ["Rule ID", "Group", "Attribute/system field", "Operator", "Value", "Value to", "Negated"]


def _rechazo(api, hojas) -> list[str]:
    r = api.c.post("/api/aranceles/oficial/importar", headers=api.h,
                   files={"archivo": ("p.xlsx", _libro(hojas), "application/octet-stream")})
    assert r.status_code == 422 and r.json()["codigo"] == "lote_con_errores", r.text
    return [e["mensaje"] for e in r.json()["detalle"]]


def test_same_as_reuses_the_attribute_and_resolves_conditions(interno):
    _cargar(interno, {
        "Attributes": [ATTRS, ["upper_mix", "Upper mix", "composition", None, "No", "Yes", "CORE", None, "comp.corte"]],
        "Classification_Rules": [REGLAS, ["R-ALIAS-1", "CATEGORY", "CALZADO", "SOFT_SIGNAL", 10, "COMPANY", "TEST", "alias", "No", "No"]],
        "Rule_Conditions": [CONDS, ["R-ALIAS-1", 1, "upper_mix", "EXISTS", None, None, "No"]],
    })
    with SessionLocal() as db:
        assert db.scalar(select(AtributoDef).where(AtributoDef.codigo == "upper_mix")) is None  # no se duplicó
        assert "upper_mix" in db.scalar(select(AtributoDef).where(AtributoDef.codigo == "comp.corte")).alias
        r = db.scalar(select(ReglaClasificacion).where(ReglaClasificacion.codigo == "R-ALIAS-1"))
        assert r.codigo_ambito == "calzado"  # el código de la categoría, como existe (no en mayúsculas)
        assert [c.campo for c in r.condiciones] == ["comp.corte"]  # el alias se resolvió
    # Una ficha o una SDS que trae el alias llega al atributo de la ficha
    s = interno.post("/clasificacion/sesion", {"categoria": "calzado", "nombre": "Canvas sneaker", "paises": False,
                                                "ficha": {"upper_mix": "100% canvas"}}).json()
    assert s["ficha"]["comp"]["corte"] == "100% canvas" and "upper_mix" not in s["ficha"]


def test_package_errors_name_the_problem(interno):
    errores = _rechazo(interno, {
        "Attributes": [ATTRS, ["sole_flag", "Sole", "boolean", None, "No", "Yes", "CORE", None, "comp.suela"],
                       ["ghost", "Ghost", "text", None, "No", "Yes", "CORE", None, "no_such_attribute"]],
        "Attribute_Scope": [["Attribute code", "Scope type", "Scope code", "Mode", "Priority", "Condition / dependency", "Active"],
                            ["cas_number", "CATEGORY", "not_a_category", "SHOW", 500, None, "Yes"],
                            ["cas_number", "HEADING", "29", "SHOW", 500, None, "Yes"]],
        "Classification_Rules": [REGLAS, ["R-BAD-1", "DOMAIN", "NOPE", "SOFT_SIGNAL", 10, "COMPANY", "TEST", "x", "No", "No"],
                                 ["R-BAD-2", "SYSTEM", "ALL", "SOFT_SIGNAL", 10, "COMPANY", "TEST", "x", "No", "No"]],
        "Rule_Conditions": [CONDS, ["R-BAD-2", 1, "no_such_field", "EQUAL", "x", None, "No"]],
    })
    texto = " | ".join(errores)
    assert "sole_flag is boolean but comp.suela is composition" in texto
    assert "no_such_attribute is not an attribute" in texto
    assert "Category not_a_category does not exist" in texto
    assert "Heading 29 must have 4 digits" in texto
    assert "Domain NOPE does not exist" in texto
    assert "no_such_field is not an attribute" in texto


def test_products_without_category_get_the_generic_sheet(interno):
    """Sin categoría configurada se pregunta lo genérico (descripción técnica y
    composición); con categoría, solo su ficha propia. El país destino nunca se pregunta."""
    s = interno.post("/clasificacion/sesion", {"nombre": "LED desk lamp", "paises": False}).json()
    campos = {c["codigo"] for c in s["campos"]}
    assert {"technical_description", "comp.material"} <= campos and "destination_country" not in campos
    s = interno.post("/clasificacion/sesion", {"categoria": "calzado", "nombre": "Canvas sneaker", "paises": False}).json()
    campos = {c["codigo"] for c in s["campos"]}
    assert not {"technical_description", "comp.material", "destination_country"} & campos and "comp.corte" in campos


def test_migration_removes_duplicates_and_keeps_captured_values():
    """La migración 0024 quita los duplicados del paquete y pasa lo capturado en
    uno con equivalente a la ficha (sin pisar lo que la ficha ya tenía)."""
    import json
    import sqlite3
    import subprocess
    import sys
    import tempfile

    from test_oficial import RAIZ

    with tempfile.TemporaryDirectory() as tmp:
        env = {"DATABASE_URL": f"sqlite:///{tmp}/m.db", "PATH": "/usr/bin:/bin"}
        alembic = [sys.executable, "-m", "alembic"]
        assert subprocess.run(alembic + ["upgrade", "0023"], cwd=RAIZ, env=env, capture_output=True).returncode == 0
        con = sqlite3.connect(f"{tmp}/m.db")
        for i, (cod, tipo) in enumerate((("upper_material", "composition"), ("footwear_type", "select"), ("cas_number", "text"),
                                         ("comp.corte", "composition")), start=1):
            con.execute("INSERT INTO atributos_def (id, codigo, etiqueta, tipo_dato, multiple, usado_clasificacion, origen, de_composicion,"
                        " informativo, orden, activo, seccion) VALUES (?, ?, ?, ?, 0, 1, ?, 0, 0, 0, 1, 'caracteristicas')",
                        (i, cod, cod, tipo, "MOTOR" if cod == "comp.corte" else "PAQUETE"))
        con.execute("INSERT INTO atributo_ambitos (atributo_id, tipo_ambito, codigo_ambito, modo, prioridad, activo) VALUES (1, 'DOMAIN', 'FOOTWEAR', 'SHOW', 9, 1)")
        def insertar(tabla, fila):
            for k, r in {r[1]: r for r in con.execute(f"PRAGMA table_info({tabla})")}.items():
                if k not in fila and r[3] and r[4] is None:  # obligatorias sin valor por defecto
                    fila[k] = 0 if "INT" in r[2].upper() or "BOOL" in r[2].upper() else "x"
            con.execute(f"INSERT INTO {tabla} ({', '.join(fila)}) VALUES ({', '.join('?' * len(fila))})", list(fila.values()))
        insertar("proveedores", {"id": 1})
        insertar("productos", {"id": 1, "proveedor_id": 1, "estilo": "S1",
                               "ficha": json.dumps({"upper_material": "100% canvas", "footwear_type": "X", "comp": {"suela": "rubber"}})})
        con.commit()
        con.close()
        r = subprocess.run(alembic + ["upgrade", "head"], cwd=RAIZ, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        con = sqlite3.connect(f"{tmp}/m.db")
        codigos = {x[0] for x in con.execute("SELECT codigo FROM atributos_def")}
        assert codigos == {"cas_number", "comp.corte"}
        assert not con.execute("SELECT 1 FROM atributo_ambitos WHERE atributo_id = 1").fetchall()
        assert json.loads(con.execute("SELECT alias FROM atributos_def WHERE codigo = 'comp.corte'").fetchone()[0]) == ["upper_material"]
        ficha = json.loads(con.execute("SELECT ficha FROM productos WHERE id = 1").fetchone()[0])
        assert ficha == {"comp": {"suela": "rubber", "corte": "100% canvas"}}
