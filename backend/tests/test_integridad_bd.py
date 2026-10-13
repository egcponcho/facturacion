"""Integridad en la propia base: importes exactos, numeración sin
duplicados y restricciones CHECK (auditoría de datos, prioridad crítica)."""
import threading
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.core import dinero, numeracion
from app.core.db import ES_SQLITE, SessionLocal, engine
from app.core.organizacion import en_organizacion
from app.modelos import Embarque, PosicionOC
from app.modelos.restricciones import RESTRICCIONES, nombre
from app.modulos.transporte.transporte import codigo_embarque


def test_la_base_tiene_todas_las_restricciones(client):
    insp = inspect(engine)
    for tabla, lista in RESTRICCIONES.items():
        en_base = {c["name"] for c in insp.get_check_constraints(tabla)}
        faltan = {nombre(tabla, s) for s, _ in lista} - en_base
        assert not faltan, f"{tabla}: faltan {faltan}"


@pytest.mark.parametrize("sql", [
    "UPDATE posiciones_oc SET precio = -1 WHERE id = (SELECT min(id) FROM posiciones_oc)",
    "UPDATE posiciones_oc SET cantidad = -5 WHERE id = (SELECT min(id) FROM posiciones_oc)",
    "UPDATE factura_lineas SET precio_unitario = -0.01 WHERE id = (SELECT min(id) FROM factura_lineas)",
    "UPDATE facturas SET estado = 'PAGADA' WHERE id = (SELECT min(id) FROM facturas)",
    "UPDATE ordenes_compra SET estado = 'X' WHERE id = (SELECT min(id) FROM ordenes_compra)",
    "UPDATE embarques SET estado = 'PERDIDO' WHERE id = (SELECT min(id) FROM embarques)",
    "UPDATE versiones_dataset SET vigente_desde = '2030-01-01', vigente_hasta = '2020-01-01' "
    "WHERE id = (SELECT min(id) FROM versiones_dataset)",
])
def test_la_base_rechaza_datos_imposibles(client, sql):
    with engine.connect() as con:
        with pytest.raises(IntegrityError):
            con.execute(text(sql))
        con.rollback()


def test_importes_en_decimal():
    # 0.1 + 0.2 en coma flotante no da 0.3; en Decimal sí
    assert dinero.total([(1, 0.1), (1, 0.2)]) == Decimal("0.30")
    # Cada línea se redondea a la moneda (mitad hacia arriba) y el total es su suma
    assert dinero.importe(3, "0.125") == Decimal("0.38")
    assert dinero.total([(3, "0.125"), (3, "0.125")]) == Decimal("0.76")
    assert dinero.redondear("2.675", decimales_=2) == Decimal("2.68")  # round(2.675, 2) en float da 2.67
    assert dinero.numero(Decimal("12.50")) == 12.5 and dinero.numero(Decimal("12.00")) == 12


def test_precio_se_guarda_exacto(client):
    with SessionLocal() as db, en_organizacion(1):
        p = db.scalar(select(PosicionOC).where(PosicionOC.precio.is_not(None)).limit(1))
        anterior = p.precio
        p.precio = 19.123456
        db.flush()
        guardado = db.execute(text("SELECT precio FROM posiciones_oc WHERE id = :i"), {"i": p.id}).scalar()
        assert Decimal(str(guardado)) == Decimal("19.123456")
        p.precio = anterior
        db.rollback()


def test_detalle_de_factura_cuadra_al_centavo(interno):
    f = interno.get("/facturas", params={"size": 1}).json()["items"][0]
    d = interno.get(f"/facturas/{f['id']}").json()
    suma = sum(Decimal(str(l["importe"])) for l in d["lineas"])
    assert Decimal(str(d["totales"]["importe"])) == suma
    assert Decimal(str(f["importe"])) == suma  # la lista da el mismo total que el detalle


def test_codigos_de_embarque_de_la_serie(client, interno):
    with SessionLocal() as db, en_organizacion(1):
        existentes = set(db.scalars(select(Embarque.codigo)))
        a, b = codigo_embarque(db), codigo_embarque(db)
        db.rollback()
    assert a != b and a not in existentes and b not in existentes
    # El contador vive en la base: el siguiente embarque toma otro código y nunca uno repetido
    r1 = interno.post("/embarques", {"tipo_transporte": "MARITIMO"}).json()
    r2 = interno.post("/embarques", {"tipo_transporte": "MARITIMO"}).json()
    assert r1["codigo"] != r2["codigo"]
    assert int(r2["codigo"].split("-")[1]) == int(r1["codigo"].split("-")[1]) + 1


@pytest.mark.skipif(ES_SQLITE, reason="El bloqueo del contador se prueba en PostgreSQL")
def test_serie_en_paralelo_no_repite(client):
    with SessionLocal() as db, en_organizacion(1):
        serie_id = numeracion.asegurar_serie(db, "prueba_paralelo", "PAR", "Parallel", "P-").id
        db.commit()
    barrera = threading.Barrier(4)
    numeros = []

    def tomar():
        with SessionLocal() as db, en_organizacion(1):
            serie = db.get(numeracion.SerieDocumental, serie_id)
            barrera.wait()
            numeros.append(numeracion.siguiente(db, serie))
            db.commit()

    hilos = [threading.Thread(target=tomar) for _ in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert len(set(numeros)) == 4


def test_numero_de_pl_unico_en_su_factura(client):
    with engine.connect() as con:
        fila = con.execute(text("SELECT factura_id, numero FROM packing_lists LIMIT 1")).first()
        with pytest.raises(IntegrityError):
            con.execute(text("INSERT INTO packing_lists (factura_id, numero, estado, version, creado_en, actualizado_en, "
                             "organizacion_id) VALUES (:f, :n, 'BORRADOR', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)"),
                        {"f": fila.factura_id, "n": fila.numero})
        con.rollback()


def test_siguiente_numero_de_pl_no_repite():
    from types import SimpleNamespace as N

    from app.modulos.empaque.packing import _siguiente_numero

    assert _siguiente_numero([]) == "PL-001"
    # Con PL-001 cancelado y PL-002 vigente, contar daba PL-002 otra vez
    assert _siguiente_numero([N(numero="PL-001"), N(numero="PL-002")]) == "PL-003"
    assert _siguiente_numero([N(numero="PL-002")]) == "PL-003"
    assert _siguiente_numero([N(numero="MIO-7")]) == "PL-001"
