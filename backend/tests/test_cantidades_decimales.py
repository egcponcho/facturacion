"""Cantidades con decimales: lo que se mide (kg, litros, metros) admite hasta 3
decimales de punta a punta (OC → factura → packing list); lo que se cuenta
(pares, unidades) sigue en enteros."""
from app.core.db import SessionLocal
from app.modelos import Factura, FacturaLinea, Historial, PackingList, PLLinea, PosicionOC, cant
from app.modulos.maestros.unidades import error_cantidad


def test_reglas_por_unidad():
    assert cant(12.0) == 12 and isinstance(cant(12.0), int) and cant(12.5004) == 12.5
    assert error_cantidad(12.5, "KG") is None and error_cantidad(12.5, "L") is None
    assert "whole numbers" in error_cantidad(2.5, "PAR") and "whole numbers" in error_cantidad(1.5, "UN")
    assert error_cantidad(1.2345, "KG").startswith("At most 3 decimals")
    assert error_cantidad(0, "KG") == "The quantity must be greater than zero."


def test_factura_y_pl_con_kilos(interno):
    # Una posición medida en kg (se cambia la unidad de una posición libre de la demo)
    with SessionLocal() as db:
        p = db.query(PosicionOC).filter(~PosicionOC.id.in_(db.query(FacturaLinea.posicion_oc_id)), PosicionOC.prepack.is_(None),
                                         PosicionOC.inner_pack.is_(None)).first()
        pid, oc_prov, antes = p.id, p.oc.proveedor_id, (p.unidad, p.cantidad, p.casepack)
        p.unidad, p.cantidad, p.casepack = "KG", 250.5, None
        db.commit()
    try:
        _kilos(interno, pid, oc_prov)
    finally:  # deja la demo como estaba (otras pruebas usan esta posición)
        with SessionLocal() as db:
            for f in db.query(Factura).filter(Factura.lineas.any(FacturaLinea.posicion_oc_id == pid)).all():
                for pl in db.query(PackingList).filter(PackingList.factura_id == f.id).all():
                    db.delete(pl)
                db.query(Historial).filter(Historial.factura_id == f.id).delete()
                db.delete(f)
            p = db.get(PosicionOC, pid)
            p.unidad, p.cantidad, p.casepack = antes
            db.commit()


def _kilos(interno, pid, oc_prov):
    r = interno.post("/facturas", {"proveedor_id": oc_prov, "lineas": [{"posicion_id": pid, "cantidad": 100.25}]})
    assert r.status_code == 200, r.text
    f = interno.get(f"/facturas/{r.json()['id']}").json()
    linea = next(x for x in f["lineas"] if x["cantidad"] == 100.25)
    # Lo que queda en la OC se calcula con decimales, sin redondear a enteros
    with SessionLocal() as db:
        assert db.get(PosicionOC, pid).cantidad == 250.5
    pl = interno.post(f"/facturas/{f['id']}/packing-lists", {"lineas": [{"factura_linea_id": linea["id"], "cantidad": 40.1}]})
    assert pl.status_code == 200, pl.text
    with SessionLocal() as db:
        assert db.query(PLLinea).filter(PLLinea.factura_linea_id == linea["id"]).one().cantidad == 40.1
    # En pares o unidades no se aceptan decimales
    with SessionLocal() as db:
        otra = db.query(PosicionOC).filter(~PosicionOC.id.in_(db.query(FacturaLinea.posicion_oc_id)), PosicionOC.unidad == "PAR",
                                            PosicionOC.inner_pack.is_(None)).first()
        otra_id, otra_prov = otra.id, otra.oc.proveedor_id
    r = interno.post("/facturas", {"proveedor_id": otra_prov, "lineas": [{"posicion_id": otra_id, "cantidad": 1.5}]})
    assert r.status_code == 422 and "whole numbers" in r.text, r.text
