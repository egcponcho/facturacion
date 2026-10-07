"""Descripciones del producto armadas con la ficha (parte del motor de clasificación).

- Aduanera (en español, como se declara): qué es, sus materiales por categoría
  (CUERO, TEXTIL, SINTÉTICO…), las características que pide el arancel y para
  quién. Sin porcentajes ni marca.
- Comercial: el tipo de producto y la marca, como va en la factura y el PL.

Todo sale de los datos: el nombre de la categoría (CategoriaProducto.nombre_aduana)
o el de una opción elegida (AtributoOpcion.texto_aduana.nombre), la plantilla de
material de la categoría (CategoriaProducto.plantilla_aduana) y las frases de
las opciones y casillas (texto_aduana.frase, con su orden y condición).
tests/test_descripciones.py fija el resultado esperado (casos de referencia en tests/paridad).
"""
import re

# Vocabulario aduanero de las clases de material (presentación, no clasificación)
CAT_MAT = {"textil": "TEXTIL", "cuero": "CUERO", "plastico": "SINTÉTICO", "sintetica": "SINTÉTICO", "artificial": "SINTÉTICO", "caucho": "SINTÉTICO"}
MAT_TXT = {"plastico": "CAUCHO O PLÁSTICO", "cuero": "CUERO", "textil": "MATERIA TEXTIL", "otro": "OTRAS MATERIAS", "metal": "METAL", "madera": "MADERA",
           "papel": "PAPEL O CARTÓN", "vidrio": "VIDRIO", "paja": "PAJA"}


def _mat(m, defecto: str = "") -> str:
    return CAT_MAT.get(m) or MAT_TXT.get(m) or defecto


def _cumple(cond, s) -> bool:
    from .ficha import _cumple as cumple

    return cumple(cond, s)


def _para(s: dict) -> str:
    e = "bebe" if s.get("edad") == "bebe" else (s.get("edadNac") or (s.get("edad") if s.get("edad") in ("adulto", "nino") else ""))
    g = s.get("genero")
    if e == "bebe":
        return "PARA BEBÉ"
    nino = e == "nino"
    return {"M": "PARA NIÑO" if nino else "PARA HOMBRE", "F": "PARA NIÑA" if nino else "PARA MUJER",
            "U": "PARA NIÑO O NIÑA" if nino else "UNISEX"}.get(g, "PARA NIÑO O NIÑA" if nino else "")


def _textos(cat, s: dict):
    """Textos de aduana de lo elegido: (orden, texto_aduana) de opciones y casillas."""
    for a in cat.atributos:
        v = s.get(a.codigo)
        if a.booleano:
            t = a.texto_aduana if v is True else None
        else:
            o = a.opcion(v) if v not in (None, "", []) and not isinstance(v, list) else None
            t = o.texto_aduana if o else None
        if t and _cumple(t.get("cuando"), s):
            yield a, t


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
    ext = [f for _, _, f in frases]
    para = _para(s)
    if para:
        ext.append(para)
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
