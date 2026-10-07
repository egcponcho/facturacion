"""Ficha → hechos con el catálogo de atributos como datos.

Paridad con el antiguo clasificador del navegador (tests/paridad/atributos.json,
casos fijados al retirarlo, son la referencia de regresión): con los mismos datos de la ficha, el
normalizador del servidor deja los mismos valores, da los mismos avisos,
pregunta lo mismo (preguntar / definido) con las mismas opciones y pide las
mismas partes de la composición. Además, la resolución de ámbitos
(SHOW / REQUIRE / HIDE por especificidad y prioridad)."""
import json
from pathlib import Path

import pytest

from app.services.ficha import Ambito, Atributo, Catalogo, Categoria, Opcion

# El catálogo del motor más el conocimiento de la empresa de ejemplo: los nombres
# de sus modelos («old skool» es un tenis) son palabras clave de la empresa, no
# patrones del motor
_PALABRAS = [{"frase": x["frase"], "tipo": x["tipo"], "marca": x.get("marca"), **x["atributos"]}
             for x in json.loads((Path(__file__).parents[1] / "app/data/demo/palabras_empresa_demo.json").read_text(encoding="utf-8"))]
_BASE = Catalogo.desde_json()
CAT = Catalogo(_BASE.atributos, list(_BASE.categorias.values()), palabras=_PALABRAS)
CASOS = json.loads((Path(__file__).parent / "paridad/atributos.json").read_text(encoding="utf-8"))["casos"]


def _normalizado(e):
    ficha = {k: v for k, v in e.items() if k not in ("tipo", "comp")}
    ficha["comp"] = e.get("comp") or {}
    s = CAT.hechos_base(ficha, e["tipo"])
    return s, CAT.normalizar(s)


@pytest.mark.parametrize("i", range(0, len(CASOS)))
def test_paridad_normalizador(i):
    caso = CASOS[i]
    s, avisos = _normalizado(caso["entrada"])
    js = caso["valores"]
    valores = {k: (bool(s.get(k)) if CAT.por_codigo[k].booleano else (s.get(k) or "")) for k in js}
    assert valores == js
    assert {x["texto"] for x in avisos if x["campo"] in js} == set(caso["avisos"])
    estados = {}
    for k in js:
        a = CAT.por_codigo[k]
        e = CAT.estado(a, s)
        if e != "oculto":
            estados[k] = {"estado": e, "opciones": None if a.booleano else [o.codigo for o in CAT.opciones_validas(a, s)]}
    assert estados == caso["estados"]
    partes = {a.codigo[5:] for a in CAT.atributos if a.tipo_dato == "composition" and CAT.aplica(a, s)}
    assert partes == set(caso["partes"])


def _cat(*ambitos):
    a = Atributo("material", "Material", "select", opciones=[Opcion("x", "X")], ambitos=list(ambitos))
    return Catalogo([a], [Categoria("bateria", "Batteries", "ELECTRONICS")]), a


def test_ambito_mas_especifico_manda_y_hide_oculta():
    cat, a = _cat(Ambito("SYSTEM", "ALL", "SHOW", 900, id=1), Ambito("CATEGORY", "bateria", "HIDE", 100, id=2))
    assert cat.ambito(a, {"categoria": "otra"}).modo == "SHOW"
    assert not cat.aplica(a, {"categoria": "bateria", "dominio": "ELECTRONICS"})  # CATEGORY gana aunque tenga menos prioridad
    cat, a = _cat(Ambito("SYSTEM", "ALL", "REQUIRE", 1, id=1), Ambito("DOMAIN", "ELECTRONICS", "HIDE", 1, id=2))
    assert not cat.aplica(a, {"categoria": "bateria", "dominio": "ELECTRONICS"})
    assert cat.ambito(a, {"categoria": "x", "dominio": "OTRO"}).modo == "REQUIRE"


def test_ambito_misma_especificidad_por_prioridad_y_desempate_estable():
    cat, a = _cat(Ambito("CATEGORY", "bateria", "SHOW", 500, id=1), Ambito("CATEGORY", "bateria", "REQUIRE", 600, id=2))
    assert cat.ambito(a, {"categoria": "bateria"}).modo == "REQUIRE"
    cat, a = _cat(Ambito("CATEGORY", "bateria", "SHOW", 500, id=7), Ambito("CATEGORY", "bateria", "HIDE", 500, id=3))
    assert cat.ambito(a, {"categoria": "bateria"}).modo == "HIDE"  # a igual prioridad, HIDE > REQUIRE > SHOW
    cat, a = _cat(Ambito("DOMAIN", "ELECTRONICS", "SHOW", 1, id=1), Ambito("HEADING", "8507", "HIDE", 999, id=2))
    assert cat.aplica(a, {"categoria": "bateria", "dominio": "ELECTRONICS"}, ["850760"])  # DOMAIN > HEADING


def test_ambito_condicional():
    cond = [{"campo": "quimica", "operador": "EQUAL", "valor": "litio"}]
    cat, a = _cat(Ambito("SYSTEM", "ALL", "SHOW", 1, id=1), Ambito("CATEGORY", "bateria", "HIDE", 1, condicion=cond, id=2))
    assert cat.aplica(a, {"categoria": "bateria"})  # la condición no se cumple (falta el dato): no oculta
    assert not cat.aplica(a, {"categoria": "bateria", "quimica": "litio"})
    assert cat.aplica(a, {"categoria": "bateria", "quimica": "plomo"})


DETECCION = json.loads((Path(__file__).parent / "paridad/deteccion.json").read_text(encoding="utf-8"))["casos"]


def test_paridad_deteccion():
    """Lo que se deduce del nombre, el uso, las tallas y la composición: igual
    que el antiguo clasificador del navegador (categoría y respuestas que aplican)."""
    malos = []
    for c in DETECCION:
        js, py = c["detectado"], CAT.detectar({"comp": c["comp"]}, c["estilo"], uso=c["uso"], tallas=c["tallas"])
        if (js.get("tipo") or None) != py.get("categoria"):
            malos.append((c["estilo"], "categoria", js.get("tipo"), py.get("categoria")))
            continue
        for a in CAT._candidatos_attr(py["categoria"]) if py.get("categoria") else []:
            if a.codigo in ("upper", "sole") and (c["comp"].get("corte") or c["comp"].get("suela")):
                continue  # con composición los fija la derivación, no el texto
            if js.get(a.codigo) != py.get(a.codigo):
                malos.append((c["estilo"], a.codigo, js.get(a.codigo), py.get(a.codigo)))
    assert not malos, malos[:5]


def test_palabra_clave_aprendida_manda():
    cat = Catalogo(CAT.atributos, list(CAT.categorias.values()), palabras=[{"frase": "Ultra Range", "tipo": "calzado", "marca": None, "estiloCalz": "senderismo"}])
    d = cat.detectar({}, "Ultra Range Exo")
    assert d["categoria"] == "calzado" and d["estiloCalz"] == "senderismo" and d["_palabra"] == "Ultra Range"


def test_catalogo_de_la_base_igual_al_sembrado(interno):
    """El catálogo que lee el motor de la base (sembrado) se comporta igual que los datos."""
    from app.db import SessionLocal

    with SessionLocal() as db:
        cat = Catalogo.desde_db(db)
    for caso in CASOS[:300]:
        e = caso["entrada"]
        ficha = {k: v for k, v in e.items() if k not in ("tipo", "comp")}
        ficha["comp"] = e.get("comp") or {}
        s = cat.hechos_base(ficha, e["tipo"])
        cat.normalizar(s)
        assert {k: (bool(s.get(k)) if cat.por_codigo[k].booleano else (s.get(k) or "")) for k in caso["valores"]} == caso["valores"]
