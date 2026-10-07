"""Descripciones del producto armadas con la ficha (parte del motor de clasificación).

- Aduanera (en español, como se declara): qué es, sus materiales por categoría
  (CUERO, TEXTIL, SINTÉTICO…), las características que pide el arancel y para
  quién. Sin porcentajes ni marca.
- Comercial: el tipo de producto y la marca, como va en la factura y el PL.

Todo sale de los datos: el nombre de la categoría (CategoriaProducto.nombre_aduana)
o el de una opción elegida (AtributoOpcion.texto_aduana.nombre), la plantilla de
material de la categoría (CategoriaProducto.plantilla_aduana) y las frases de
las opciones y casillas (texto_aduana.frase, con su orden y condición).
Para quién es (PARA HOMBRE, PARA NIÑA, UNISEX…) también son frases de las
opciones (una lista de alternativas con condición: la primera que se cumple).
tests/test_descripciones.py fija el resultado esperado (casos de referencia en tests/paridad).
"""
import json
import re
from functools import lru_cache

from ..datos import MOTOR


@lru_cache(maxsize=1)
def _vocabulario() -> dict:
    """Palabras aduaneras por defecto de las clases de material (presentación, no
    clasificación); cada categoría las cambia en su plantilla («como»)."""
    d = json.loads((MOTOR / "motor_atributos.json").read_text(encoding="utf-8")).get("vocabulario_aduana") or {}
    return {**(d.get("material") or {}), **(d.get("clase_material") or {})}


def _mat(m, defecto: str = "") -> str:
    return _vocabulario().get(m) or defecto


def _cumple(cond, s) -> bool:
    from .ficha import _cumple as cumple

    return cumple(cond, s)


def _textos(cat, s: dict):
    """Textos de aduana de lo elegido: (atributo, texto_aduana) de opciones y
    casillas. Un texto puede ser una lista de alternativas: va la primera cuya
    condición se cumple."""
    for a in cat.atributos:
        v = s.get(a.codigo)
        if a.booleano:
            t = a.texto_aduana if v is True else None
        else:
            o = a.opcion(v) if v not in (None, "", []) and not isinstance(v, list) else None
            t = o.texto_aduana if o else None
        for x in (t if isinstance(t, list) else [t] if t else []):
            if _cumple(x.get("cuando"), s):
                yield a, x
                break


def descripcion_aduana(cat, s: dict, categoria) -> str:
    if not categoria:
        return ""
    plantilla = categoria.plantilla_aduana or {}
    nombre = plantilla.get("nombre") or (categoria.nombre_aduana or categoria.nombre or "").upper()
    for _, t in _textos(cat, s):
        if t.get("nombre"):
            nombre = t["nombre"]
            break
    cab = [nombre]
    mat = _material(cat, s, plantilla)
    if mat:
        cab.append(mat)
    frases = sorted(((t.get("orden", 50), i, t["frase"]) for i, (_, t) in enumerate(_textos(cat, s)) if t.get("frase")))
    ext = list(dict.fromkeys(f for _, _, f in frases))  # la misma frase de dos respuestas va una vez
    return ", ".join([" ".join(x for x in cab if x)] + [x for x in ext if x])


def _material(cat, s: dict, p: dict) -> str:
    plantilla = p.get("material")
    if not plantilla:
        return ""
    for alt in p.get("si") or []:
        if _cumple(alt.get("cuando"), s):
            return alt.get("material") or ""
    if p.get("clase"):
        # La clase de material de la primera parte de la composición que aplica
        for parte in p["clase"]:
            a = cat.por_codigo.get(f"comp.{parte}")
            txt = s.get(f"comp.{parte}")
            if a and cat.aplica(a, s) and txt and str(txt).strip():
                c = cat.lector.clase_mat(txt)
                return plantilla.replace("{clase}", _mat(c["pred"], c["pred"].upper())) if c else ""
            if a and cat.aplica(a, s):
                return ""
        return ""
    if any(not s.get(k) for k in p.get("requiere") or []):
        return ""
    como = p.get("como") or {}

    def valor(m):
        k = m.group(1)
        v = s.get(k) or (p.get("si_falta") or {}).get(k)
        mapa = como.get(k)
        if mapa:
            return mapa.get(v) or mapa.get("*") or ""
        return _mat(v, str(v or "").upper())

    return re.sub(r"\{(\w+)\}", valor, plantilla)


def descripcion_comercial(cat, s: dict, categoria, marca: str | None = None) -> str:
    if not categoria:
        return ""
    plantilla = categoria.plantilla_aduana or {}
    tipo = plantilla.get("comercial") or re.split(r" o ", categoria.nombre_aduana or categoria.nombre or "")[0].upper()
    for _, t in _textos(cat, s):
        if t.get("comercial"):
            tipo = t["comercial"]
            break
    return f"{tipo} {str(marca or '').strip()}".strip().upper()
