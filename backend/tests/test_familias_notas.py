"""El catálogo escrito con las Notas Explicativas del SA (data/motor/familias):
cada caso de cada familia pasa por el motor de clasificación completo (ficha,
composición, reglas y árbol oficial) y debe dar su subpartida."""
import pytest

from app.services.semilla_familias import semilla

CASOS = semilla()["casos"]


@pytest.fixture(scope="module")
def db(client):
    from app.db import SessionLocal

    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def _entrada(hechos: dict) -> dict:
    h = dict(hechos)
    cat = h.pop("categoria")
    comp = {k[5:]: v for k, v in h.items() if k.startswith("comp.")}
    ficha = {k: v for k, v in h.items() if not k.startswith("comp.")}
    texto = h.get("nombre_quimico") or ""
    return {"categoria": cat, "ficha": {**ficha, "comp": comp}, "tocados": list(ficha), "texto": texto, "nombre": texto, "paises": False}


@pytest.mark.parametrize("caso", CASOS, ids=[f"{c['hechos']['categoria']}-{c['codigo']}-{i}" for i, c in enumerate(CASOS)])
def test_caso_de_las_notas(db, caso):
    from app.services.motor_clasificacion import clasificar_producto

    r = clasificar_producto(db, _entrada(caso["hechos"]), paises=False)
    esperado = caso["codigo"]
    assert r["hs6"] and r["hs6"].startswith(esperado), (r["hs6"], r.get("razones", [])[:6], r.get("faltantes"), r.get("revision_por"))


def test_familias_cargadas(client, db):
    from sqlalchemy import select

    from app.models import CategoriaProducto, DominioClasificacion, ReglaClasificacion

    doms = {d.codigo: d for d in db.scalars(select(DominioClasificacion))}
    base = {"FOOTWEAR", "APPAREL", "ACCESSORIES", "CHEMICALS", "RAW_MATERIALS"}
    assert base <= set(doms)  # otras pruebas pueden crear familias propias
    assert all(doms[d].estado == "PUBLICADA" for d in base)
    assert {c.capitulo for c in doms["FOOTWEAR"].capitulos} >= {"64"}
    cats = set(db.scalars(select(CategoriaProducto.codigo)))
    assert {"calzado", "camiseta", "mochila", "adhesivo", "cuero"} <= cats
    reglas = set(db.scalars(select(ReglaClasificacion.codigo).where(ReglaClasificacion.codigo.like("R-NE-%"))))
    assert reglas == {r["codigo"] for r in semilla()["reglas"]}
