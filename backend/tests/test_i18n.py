"""Idiomas de la interfaz: cada idioma debe tener todos los textos, con los
mismos marcadores {0}…, en su propia escritura (no inglés olvidado) y con los
términos del glosario (traducción adaptada al sistema, no literal)."""
import json
import re
from pathlib import Path

import pytest

I18N = Path(__file__).resolve().parents[2] / "frontend" / "src" / "i18n"
IDIOMAS = ["es"]  # el inglés es la clave
ESCRITURA: dict[str, str] = {}


def _leer(nombre):
    return json.loads((I18N / nombre).read_text(encoding="utf-8"))


CLAVES = _leer("claves.json")
GLOSARIO = _leer("glosario.json")
PERMITIDOS = GLOSARIO.get("igual_permitido", {})


def _fuente_actual() -> set:
    """Textos que el código usa hoy (t('…') y tr('…')), para que claves.json no quede viejo."""
    raiz = I18N.parent
    claves = set()
    for p in list(raiz.rglob("*.vue")) + list(raiz.rglob("*.js")):
        if "i18n" in p.parts:
            continue
        for m in re.finditer(r"\b(?:t|tr)\(\s*'((?:[^'\\]|\\.)*)'", p.read_text(encoding="utf-8")):
            claves.add(re.sub(r"\\(.)", lambda x: "\n" if x.group(1) == "n" else x.group(1), m.group(1)))
    return claves


def test_claves_al_dia():
    util = {k for k in _fuente_actual() if re.search(r"[A-Za-z]{2}", re.sub(r"\{\d\}", "", k))
            and not re.fullmatch(r"[\w-]+\.\{\d\}", k) and not re.fullmatch(r"[\w.+-]+@[\w.-]+", k)}
    faltan = sorted(util - set(CLAVES))
    assert not faltan, f"Ejecuta node scripts/i18n-extraer.mjs; faltan {len(faltan)}: {faltan[:5]}"


@pytest.mark.parametrize("idioma", IDIOMAS)
def test_idioma_completo_y_bien_formado(idioma):
    dic = _leer(f"{idioma}.json")
    faltan = [k for k in CLAVES if not str(dic.get(k, "")).strip()]
    assert not faltan, f"{idioma}: faltan {len(faltan)} traducciones, p. ej. {faltan[:5]}"
    errores = []
    for k in CLAVES:
        v = dic[k]
        if sorted(re.findall(r"\{\d\}", k)) != sorted(re.findall(r"\{\d\}", v)):
            errores.append(f"marcadores distintos: {k!r} → {v!r}")
        if idioma != "zh" and (k[:1] == " " and v[:1] != " " or k[-1:] == " " and v[-1:] != " "):  # el chino no separa con espacios
            errores.append(f"espacio al inicio o al final: {k!r} → {v!r}")
        if v == k and k not in PERMITIDOS.get(idioma, []) and k not in PERMITIDOS.get("todos", []):
            errores.append(f"sin traducir: {k!r}")
        sin_marcas = re.sub(r"\{\d\}", "", v)
        if idioma in ESCRITURA and re.search(r"[A-Za-z]{3}", re.sub(r"\{\d\}", "", k)) \
                and not re.search(ESCRITURA[idioma], sin_marcas) and k not in PERMITIDOS.get("todos", []) \
                and k not in PERMITIDOS.get(idioma, []):
            errores.append(f"no está en la escritura del idioma: {k!r} → {v!r}")
    assert not errores, f"{idioma}: {len(errores)} problemas:\n" + "\n".join(errores[:20])


def _como_etiqueta(termino: str, k: str) -> bool:
    """El término usado como nombre de campo o encabezado («Type», «Type: all»,
    «Product type»), no como verbo dentro de una frase («Type the code…»)."""
    t = re.escape(termino.lower())
    return bool(re.fullmatch(rf"(?:[\w-]+ ){{0,2}}{t}(?:s)?(?:\s*[:(·*].*)?", k.lower()))


@pytest.mark.parametrize("idioma", IDIOMAS)
def test_glosario(idioma):
    """Los términos del sistema usan la traducción aprobada y nunca la literal
    equivocada (p. ej. «Type» de una columna no es «chico» ni «escribir»)."""
    dic = _leer(f"{idioma}.json")
    errores = []
    for term in GLOSARIO["terminos"]:
        if term["en"] in dic and dic[term["en"]] != term[idioma]:
            errores.append(f"{term['en']!r} debe ser {term[idioma]!r}, no {dic[term['en']]!r}")
        for malo in term.get("prohibido", {}).get(idioma, []):
            for k, v in dic.items():
                if _como_etiqueta(term["en"], k) and malo.lower() in v.lower():
                    errores.append(f"{k!r}: usa «{malo}» para {term['en']!r}")
    assert not errores, f"{idioma}:\n" + "\n".join(errores[:20])


def test_traduccion_de_documentos_al_dia():
    """backend/app/i18n_es.json (la traducción de los PDF y Excel) es la de
    es.json para los textos del servidor: node scripts/i18n-extraer.mjs la regenera."""
    es = _leer("es.json")
    servidor = json.loads((I18N.parents[2] / "backend" / "app" / "i18n_es.json").read_text(encoding="utf-8"))
    claves = json.loads((I18N.parents[2] / "backend" / "app" / "i18n_claves.json").read_text(encoding="utf-8"))
    esperado = {k: es[k] for k in claves if k in es}
    assert servidor == esperado, "Ejecuta node scripts/i18n-extraer.mjs"
