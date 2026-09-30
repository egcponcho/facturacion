"""Vocabulario del motor de clasificación (categorías, atributos, partes y
condiciones de los códigos nacionales), exportado del motor del navegador a
data/motor_meta.json para que las plantillas y las cargas usen los mismos
valores."""
import json
from functools import lru_cache
from pathlib import Path

from .plantillas import norm


@lru_cache
def meta() -> dict:
    ruta = Path(__file__).resolve().parent.parent / "data" / "motor_meta.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


@lru_cache
def tipos() -> dict[str, dict]:
    """{clave: {l, corto, grupoTipo, partes}}"""
    return {t["k"]: t for g in meta()["tipos"] for t in g["tipos"]}


def tipo_de(valor: str) -> str | None:
    """Categoría por su clave, su nombre o su nombre corto."""
    v = norm(valor)
    if not v:
        return None
    for k, t in tipos().items():
        if v in (norm(k), norm(t["l"]), norm(t["corto"])):
            return k
    return None


@lru_cache
def attrs() -> dict[str, dict]:
    return {a["id"]: a for a in meta()["attrs"]}


@lru_cache
def opciones_cond() -> dict[str, dict]:
    """Por cada condición de los códigos nacionales: etiqueta, tipo
    (opciones | sino | numero) y sus opciones {valor: etiqueta}."""
    out = {}
    nac = {q["id"]: q for q in meta()["nac"]}
    for k, lbl in meta()["cond"]:
        if k == "valorCIF":
            continue
        a = attrs().get(k)
        q = nac.get(k)
        if q and q.get("ops"):
            out[k] = {"label": lbl, "tipo": "opciones", "ops": {v: t for v, t in q["ops"]}}
        elif a and a.get("ops"):
            out[k] = {"label": lbl, "tipo": "opciones", "ops": {o["v"]: o["l"] for o in a["ops"]}}
        else:
            out[k] = {"label": lbl, "tipo": "sino", "ops": {}}
    out["genero"] = {"label": "Gender", "tipo": "opciones", "ops": {"M": "Men", "F": "Women", "U": "Unisex"}}
    out["edadNac"] = {"label": "Age", "tipo": "opciones", "ops": {"adulto": "Adult", "nino": "Child", "bebe": "Baby"}}
    out["cifMax"] = {"label": "CIF value up to (US$)", "tipo": "numero", "ops": {}}
    out["cifMin"] = {"label": "CIF value over (US$)", "tipo": "numero", "ops": {}}
    return out


def valor_opcion(ops: dict, texto: str) -> str | None:
    t = norm(texto)
    for v, lbl in ops.items():
        if t in (norm(v), norm(lbl)):
            return v
    return None


def cond_texto(cond: dict) -> str:
    """Condiciones en palabras, para listas y reportes."""
    oc = opciones_cond()
    partes = []
    for k, v in (cond or {}).items():
        d = oc.get(k, {"label": k, "ops": {}, "tipo": ""})
        if d["tipo"] == "numero":
            partes.append(f"{d['label']} {v}")
        elif isinstance(v, bool):
            partes.append(("" if v else "no ") + d["label"].lower())
        else:
            vals = v if isinstance(v, list) else [v]
            partes.append(f"{d['label']}: " + " or ".join(str(d["ops"].get(x, x)) for x in vals))
    return "; ".join(partes) or "Whole subheading"
