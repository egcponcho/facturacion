"""Una línea de factura copia los datos de la posición de la OC, y la línea de
la lista de empaque los de la factura: cada dato copiado debe caber en su
destino (antes el color de la OC tenía 60 caracteres y el de la factura 40, y
en PostgreSQL facturar un color largo fallaba). Los valores de la variante y los
atributos del producto se copian como su foto completa."""
from sqlalchemy import String, select

from app.core.db import SessionLocal
from app.modelos import FacturaLinea, OrdenCompra, PLLinea, PosicionOC, Proveedor


def _largos(modelo):
    return {c.name: c.type.length for c in modelo.__table__.columns if isinstance(c.type, String) and c.type.length}


def test_cada_dato_copiado_cabe_en_su_destino():
    for origen, destino in ((PosicionOC, FacturaLinea), (FacturaLinea, PLLinea)):
        a, b = _largos(origen), _largos(destino)
        cortos = {k: (a[k], b[k]) for k in set(a) & set(b) if b[k] < a[k]}
        assert not cortos, f"{destino.__name__} guarda más corto que {origen.__name__}: {cortos}"


def test_se_factura_una_posicion_con_un_valor_de_variante_largo(vans):
    color = "Heather grey / true black / university red (limited)"[:60]
    with SessionLocal() as db:
        usadas = select(FacturaLinea.posicion_oc_id)
        pos = db.scalar(select(PosicionOC).join(OrdenCompra).join(Proveedor)
                        .where(Proveedor.codigo == "VANS", OrdenCompra.liberada.is_(True), ~PosicionOC.id.in_(usadas),
                               PosicionOC.bloqueada.is_(False)).order_by(PosicionOC.id.desc()))
        pid, antes = pos.id, dict(pos.variante or {})
        pos.variante = {**antes, "COLOR": color}
        db.commit()
    try:
        r = vans.post("/facturas", {"lineas": [{"posicion_id": pid, "cantidad": 1}]})
        assert r.status_code == 200, r.text
        fid = r.json()["id"]
        with SessionLocal() as db:
            fl = db.scalar(select(FacturaLinea).where(FacturaLinea.factura_id == fid, FacturaLinea.posicion_oc_id == pid))
            assert fl.variante["COLOR"] == color and fl.atributos == db.get(PosicionOC, pid).atributos
        assert vans.post(f"/facturas/{fid}/cancelar", {"motivo": "prueba"}).status_code in (200, 409)
    finally:
        with SessionLocal() as db:
            db.get(PosicionOC, pid).variante = antes
            db.commit()
