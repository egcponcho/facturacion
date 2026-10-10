"""Rendimiento de las listas principales (docs/DIAGNOSTICO.md §7): cuántas
consultas a la base hace cada una. Una lista que hace una consulta por fila
(N+1) se delata porque sus consultas crecen con el tamaño de la página; aquí se
compara la misma lista con 1 y con 25 filas."""
from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.core.db import engine


@contextmanager
def contar():
    n = [0]

    def uno(*_):
        n[0] += 1

    event.listen(engine, "before_cursor_execute", uno)
    try:
        yield n
    finally:
        event.remove(engine, "before_cursor_execute", uno)


def consultas(api, ruta):
    with contar() as n:
        r = api.get(ruta)
    assert r.status_code == 200, r.text
    return n[0], r.json()


def filas(datos):
    return len(datos["items"]) if isinstance(datos, dict) and "items" in datos else len(datos)


# Ruta con {size}; las listas paginadas en el servidor
LISTAS = [
    "/ordenes?solo_disponible=false&size={size}",
    "/facturas?size={size}",
    "/productos?estado=&size={size}",
    "/seguimiento/ordenes?size={size}",
    "/seguimiento/documentos?size={size}",
    "/seguimiento/embarques?size={size}",
]


@pytest.mark.parametrize("ruta", LISTAS)
def test_las_listas_no_hacen_una_consulta_por_fila(interno, ruta):
    pocas, d1 = consultas(interno, ruta.format(size=1))
    muchas, d25 = consultas(interno, ruta.format(size=25))
    print(ruta, filas(d1), pocas, filas(d25), muchas)
    assert filas(d25) > filas(d1), "la demostración debe tener más de una fila para que la prueba compare algo"
    # Una página 25 veces más grande no puede costar consultas por fila
    assert muchas - pocas <= 3, f"{ruta}: {pocas} consultas con 1 fila y {muchas} con {filas(d25)}"
