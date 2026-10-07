"""Versión de la configuración: cada cambio del motor la sube en la misma
transacción; el catálogo se comparte en el proceso mientras no cambie y una
transacción deshecha no deja nada compartido."""
from app.db import SessionLocal
from app.models import SinonimoBusqueda
from app.services import version_config
from app.services.ficha import catalogo


def test_catalogo_compartido_hasta_que_cambia_la_configuracion(interno):
    with SessionLocal() as a, SessionLocal() as b:
        v = version_config.actual(a)
        assert catalogo(a) is catalogo(b)  # sin cambios: el mismo catálogo en el proceso
    with SessionLocal() as db:
        db.add(SinonimoBusqueda(palabra="zzprueba", equivale="prueba", origen="MANUAL"))
        db.flush()
        assert version_config.actual(db) == v + 1 and version_config.con_cambios(db)
        propio = catalogo(db)
        db.rollback()
    with SessionLocal() as db:
        assert version_config.actual(db) == v  # deshecho: la versión no cambió
        assert catalogo(db) is not propio  # y lo no confirmado no quedó compartido
    with SessionLocal() as db:
        db.add(SinonimoBusqueda(palabra="zzprueba", equivale="prueba", origen="MANUAL"))
        db.add(SinonimoBusqueda(palabra="zzprueba2", equivale="prueba", origen="MANUAL"))
        db.commit()  # una sola subida por transacción
        antes = catalogo(db)
    with SessionLocal() as db:
        assert version_config.actual(db) == v + 1
        assert catalogo(db) is antes and "zzprueba" in antes.sinonimos_busqueda
        for x in db.query(SinonimoBusqueda).filter(SinonimoBusqueda.palabra.like("zzprueba%")):
            db.delete(x)
        db.commit()
    # La evidencia de una clasificación dice con qué versión de la configuración se hizo
    s = interno.post("/clasificacion/sesion", {"categoria": "calzado", "ficha": {}, "estilo": "X", "paises": False}).json()
    with SessionLocal() as db:
        assert s["evidencia"]["configuracion"] == version_config.actual(db)
