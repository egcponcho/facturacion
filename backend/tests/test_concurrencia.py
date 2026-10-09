"""Dos usuarios intentan facturar el mismo saldo al mismo tiempo.
Con el bloqueo de filas (SELECT ... FOR UPDATE) solo uno lo logra.
Solo aplica en PostgreSQL; SQLite es para desarrollo local."""
import threading
import time

import pytest
from sqlalchemy import select

from app.core.db import ES_SQLITE, SessionLocal
from app.core.errores import ErrorNegocio
from app.esquemas import FacturaCrear
from app.modelos import OrdenCompra, Usuario
from app.modulos.facturacion.facturas import crear_factura


@pytest.mark.skipif(ES_SQLITE, reason="La prueba de bloqueo de filas requiere PostgreSQL")
def test_mismo_saldo_en_paralelo(client):
    with SessionLocal() as db:
        oc = db.scalar(select(OrdenCompra).where(OrdenCompra.numero == "4400003902"))
        pos = next(p for p in oc.posiciones if p.talla == "10")
        pid, cantidad = pos.id, pos.cantidad
        uid = db.scalar(select(Usuario.id).where(Usuario.email == "vans@demo.com"))

    barrera = threading.Barrier(2)
    resultados = []

    def intentar():
        with SessionLocal() as db:
            user = db.get(Usuario, uid)
            barrera.wait()
            try:
                crear_factura(db, user, FacturaCrear(lineas=[{"posicion_id": pid, "cantidad": cantidad}]))
                time.sleep(0.4)  # mantiene el bloqueo mientras el otro espera
                db.commit()
                resultados.append("ok")
            except ErrorNegocio as e:
                db.rollback()
                resultados.append(e.codigo)

    hilos = [threading.Thread(target=intentar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(resultados) == ["ok", "validacion"]
