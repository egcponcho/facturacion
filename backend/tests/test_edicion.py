"""Edición exclusiva: una persona edita un documento y las demás lo ven en
solo lectura; el servidor rechaza sus cambios hasta que se libere."""
from datetime import timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.modelos import Edicion, FacturaLinea, OrdenCompra, PosicionOC, Proveedor, ahora


def _factura_borrador(vans) -> int:
    with SessionLocal() as db:
        usadas = select(FacturaLinea.posicion_oc_id)
        pos = db.scalar(select(PosicionOC).join(OrdenCompra).join(Proveedor)
                        .where(Proveedor.codigo == "VANS", OrdenCompra.liberada.is_(True), ~PosicionOC.id.in_(usadas),
                               PosicionOC.bloqueada.is_(False)).order_by(PosicionOC.id))
        pid = pos.id
    r = vans.post("/facturas", {"lineas": [{"posicion_id": pid, "cantidad": 1}]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_uno_edita_los_demas_leen(vans, interno, admin):
    fid = _factura_borrador(vans)
    try:
        # Vans toma la edición; la renueva sin problema
        r = vans.post(f"/edicion/factura/{fid}")
        assert r.status_code == 200 and r.json()["propio"], r.text
        assert vans.post(f"/edicion/factura/{fid}").status_code == 200

        # El equipo interno la ve en solo lectura, con quién y desde cuándo
        det = interno.get(f"/facturas/{fid}").json()
        assert det["edicion"]["usuario"] == "Vans supplier"
        assert det["puede"]["editar"] is False and det["puede"]["finalizar"] is False
        assert vans.get(f"/facturas/{fid}").json()["edicion"] is None  # para quien edita no hay aviso

        # No puede tomarla ni guardar cambios
        r = interno.post(f"/edicion/factura/{fid}")
        assert r.status_code == 423 and r.json()["codigo"] == "en_edicion", r.text
        r = interno.patch(f"/facturas/{fid}", {"version": det["version"], "observaciones": "cambio ajeno"})
        assert r.status_code == 423, r.text

        # Quien la tiene sí guarda
        r = vans.patch(f"/facturas/{fid}", {"version": det["version"], "observaciones": "mío"})
        assert r.status_code == 200, r.text

        # Liberar el permiso de otro: solo un administrador, y queda en el historial
        assert interno.delete_(f"/edicion/factura/{fid}?forzar=true").status_code == 403
        assert admin.delete_(f"/edicion/factura/{fid}?forzar=true").json()["liberado"] is True
        acciones = [h["accion"] for h in interno.get(f"/facturas/{fid}/historial").json()]
        assert "liberar_edicion" in acciones

        # Libre: ahora la toma el equipo interno y Vans queda en lectura
        assert interno.post(f"/edicion/factura/{fid}").status_code == 200
        assert vans.get(f"/facturas/{fid}").json()["puede"]["editar"] is False
        assert interno.delete_(f"/edicion/factura/{fid}").json()["liberado"] is True
        assert vans.get(f"/facturas/{fid}").json()["puede"]["editar"] is True
    finally:
        with SessionLocal() as db:
            db.query(Edicion).delete()
            db.commit()
        vans.post(f"/facturas/{fid}/cancelar", {"motivo": "prueba de edición"})


def test_el_permiso_vence_solo(vans, interno):
    fid = _factura_borrador(vans)
    try:
        assert vans.post(f"/edicion/factura/{fid}").status_code == 200
        with SessionLocal() as db:  # simula que la pestaña se cerró hace rato
            e = db.scalar(select(Edicion).where(Edicion.entidad == "factura", Edicion.entidad_id == fid))
            e.vence = ahora() - timedelta(seconds=1)
            db.commit()
        assert interno.get(f"/facturas/{fid}").json()["edicion"] is None
        assert interno.post(f"/edicion/factura/{fid}").status_code == 200
    finally:
        with SessionLocal() as db:
            db.query(Edicion).delete()
            db.commit()
        vans.post(f"/facturas/{fid}/cancelar", {"motivo": "prueba de edición"})


def test_solo_quien_ve_el_documento_lo_toma(vans, tnf):
    fid = _factura_borrador(vans)
    try:
        assert tnf.post(f"/edicion/factura/{fid}").status_code == 404  # factura de otro proveedor
        assert tnf.get(f"/edicion/factura/{fid}").status_code == 404
        assert vans.post(f"/edicion/otra-cosa/{fid}").status_code == 404
    finally:
        vans.post(f"/facturas/{fid}/cancelar", {"motivo": "prueba de edición"})


def test_cerrar_sesion_libera(client, vans, interno):
    from conftest import iniciar_sesion

    fid = _factura_borrador(vans)
    try:
        token = iniciar_sesion(client, "vans@demo.com")
        h = {"Authorization": f"Bearer {token}"}
        assert client.post(f"/api/edicion/factura/{fid}", headers=h).status_code == 200
        assert interno.get(f"/facturas/{fid}").json()["edicion"] is not None
        client.cookies.set("sesion", token)
        client.post("/api/auth/logout", headers={"X-Requested-With": "fetch"})
        client.cookies.clear()
        assert interno.get(f"/facturas/{fid}").json()["edicion"] is None
    finally:
        vans.post(f"/facturas/{fid}/cancelar", {"motivo": "prueba de edición"})


def test_tambien_protege_las_partes_del_documento(interno, admin):
    """Un evento del embarque es parte del embarque: si otro lo edita, no se
    puede agregar (la verificación es central, al guardar)."""
    emb = next(e for e in interno.get("/embarques").json() if e["codigo"] == "EMB-0003")
    try:
        assert interno.post(f"/edicion/embarque/{emb['id']}").status_code == 200
        assert admin.get(f"/embarques/{emb['id']}").json()["edicion"]["usuario"] == "Import team"
        r = admin.post(f"/embarques/{emb['id']}/eventos",
                       {"tipo": "OTRO", "fecha": "2026-10-08T10:00:00", "observacion": "ajeno"})
        assert r.status_code == 423, r.text
        r = admin.patch(f"/embarques/{emb['id']}", {"observaciones": "ajeno"})
        assert r.status_code == 423, r.text
    finally:
        interno.delete_(f"/edicion/embarque/{emb['id']}")
