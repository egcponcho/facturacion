"""Semilla del motor por familia (data/motor/familias/*.json).

Cada familia (calzado, ropa, accesorios, químicos, materias primas) trae su
dominio con los capítulos donde se clasifica, sus categorías, preguntas
(atributos con opciones y ámbitos), reglas y casos de prueba, escritos con las
Notas Explicativas del SA (backend/scripts/familias genera estos archivos).
`comun.json` trae lo compartido: la composición por partes, lo que se lee de
ella (fibra, materia del corte y de la suela, clase de material), para quién
es la prenda y las palabras aduaneras de cada clase de material.

Aquí solo se leen y se juntan; cada servicio siembra lo suyo (atributos,
categorías, reglas, clases de material) y nunca pisa lo que alguien editó.
"""
import json
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..datos import MOTOR

CARPETA = MOTOR / "familias"
ORDEN = ("calzado", "ropa", "accesorios", "quimicos", "materias_primas")


def _leer(nombre: str) -> dict:
    return json.loads((CARPETA / f"{nombre}.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def semilla() -> dict:
    """Todo junto: dominios, categorías, atributos (los comunes con los ámbitos
    que les da cada familia), reglas, casos, clases de material y vocabulario."""
    comun = _leer("comun")
    comunes = {a["codigo"]: {**a, "ambitos": list(a.get("ambitos") or [])} for a in comun["atributos"]}
    out = {"dominios": [], "categorias": list(comun.get("categorias") or []), "atributos": [], "reglas": [], "casos": [],
           "clases_material": comun["clases_material"], "vocabulario_aduana": comun["vocabulario_aduana"]}
    for nombre in ORDEN:
        f = _leer(nombre)
        out["dominios"].append(f["dominio"])
        out["categorias"] += f["categorias"]
        out["atributos"] += f["atributos"]
        out["reglas"] += [{**r, "familia": nombre} for r in f["reglas"]]
        out["casos"] += f.get("casos", [])
        for codigo, ambitos in (f.get("ambitos_comunes") or {}).items():
            comunes[codigo]["ambitos"] += ambitos
    out["atributos"] = list(comunes.values()) + out["atributos"]
    return out


def sembrar_dominios(db: Session) -> int:
    """Las familias y los capítulos donde se clasifican. Crea lo que falta (en
    uso, no en borrador: son las familias de base) y nunca pisa lo editado."""
    from ..models import ControlCapitulo, DominioCapitulo, DominioClasificacion

    existentes = {d.codigo: d for d in db.scalars(select(DominioClasificacion))}
    capitulos = set(db.scalars(select(ControlCapitulo.capitulo)))
    n = 0
    for d in semilla()["dominios"]:
        x = existentes.get(d["codigo"])
        if not x:
            x = DominioClasificacion(codigo=d["codigo"], nombre=d["nombre"], descripcion=d.get("descripcion"), modo="AUTO", activo=True,
                                     orden=d.get("orden", 0), estado="PUBLICADA")
            db.add(x)
            db.flush()
            n += 1
        ya = {c.capitulo for c in x.capitulos}
        for c in d.get("capitulos") or []:
            if c["capitulo"] not in ya and (not capitulos or c["capitulo"] in capitulos):
                x.capitulos.append(DominioCapitulo(capitulo=c["capitulo"], relevancia=c.get("relevancia") or "PRIMARY", habilitado=True,
                                                   proposito="Explanatory Notes of the Harmonized System"))
    db.flush()
    return n
