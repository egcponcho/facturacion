"""Etiquetado e información operativa: generar, descargar y marcar impresas
las etiquetas lee las OC, sus líneas, las listas de empaque y la recepción,
pero no cambia cantidades, saldos, estados ni movimientos. Y en los datos de
la etiqueta lo pedido (OC) y lo empacado (bulto) no se confunden."""
import pytest
from etiquetado_util import aprobada, tipo, uso
from sqlalchemy import text

from app.core.db import engine
from app.modulos.etiquetado import campos

OPERATIVAS = ("ordenes_compra", "posiciones_oc", "packing_lists", "pl_lineas", "facturas", "factura_lineas", "embarques",
              "eventos_embarque", "unidades_carga", "recepciones", "recepcion_registros", "recepcion_movimientos", "articulos")
DISENO = {"ancho": 60, "alto": 25, "elementos": [{"id": "s", "tipo": "campo", "campo": "articulo.sku", "x": 2, "y": 2, "w": 50, "h": 8}]}


def _foto() -> dict:
    """Cada fila de las tablas operativas, tal cual (sin el filtro de organización)."""
    with engine.connect() as c:
        return {t: [tuple(r) for r in c.execute(text(f"SELECT * FROM {t} ORDER BY id"))] for t in OPERATIVAS}


@pytest.fixture(scope="module")
def regla(interno, admin):
    """Tipos de esta prueba (artículo por unidad y caja) con su diseño en toda la empresa."""
    art = tipo(interno, "INT_UNIDAD", cantidad="POR_UNIDAD")
    caja = tipo(interno, "INT_CAJA", sujeto="BULTO", cantidad="POR_BULTO")
    for t in (art, caja):
        uso(interno, t["id"], aprobada(interno, admin, f"Integration design {t['codigo']}", t["id"], DISENO["elementos"],
                                         ancho=DISENO["ancho"], alto=DISENO["alto"])["id"])
    return {"articulo": art, "caja": caja}


def _ordenes(interno, n=2):
    res = []
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        d = interno.get(f"/ordenes/{o['id']}").json()
        lineas = [x for x in d["posiciones"] if x.get("codigo_articulo")]
        if d["oc"]["estado"] != "BORRADOR" and lineas:
            res.append((o["id"], lineas))
        if len(res) == n:
            break
    return res


def test_generar_no_modifica_ordenes_listas_ni_recepcion(interno, regla):
    ocs = _ordenes(interno)
    assert ocs, "the demo has POs with items"
    antes = _foto()
    # Trabajo desde varias OC: validar, generar, descargar el ZIP y confirmar la impresión
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {
        "oc_ids": [o for o, _ in ocs], "posiciones": [x["id"] for _, ls in ocs for x in ls[:2]], "tipos": [regla["articulo"]["id"]]}}).json()
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/validar").status_code == 200
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True, "parcial": True})
    assert g.status_code == 200, g.text
    assert g.json()["estado"] in ("GENERADO", "PARCIAL") and g.json()["ejecuciones"]
    assert interno.get(f"/etiquetas/trabajos/{t['id']}/archivo").status_code == 200
    for e in interno.get(f"/etiquetas/trabajos/{t['id']}").json()["ejecuciones"]:
        interno.post(f"/etiquetas/generaciones/{e['id']}/impresion", {"confirmo": True, "cantidad": e["total"]})
    # Por bulto desde una lista de empaque
    pls = [x for x in interno.get("/etiquetas/packing").json()
           if x["etiquetas_reales"] and interno.get(f"/etiquetas/packing/{x['id']}").json()["superiores"]]
    if pls:
        t = interno.post("/etiquetas/trabajos", {"origen": "PACKING", "parametros": {"pl_id": pls[0]["id"], "tipos": [regla["caja"]["id"]]}}).json()
        interno.post(f"/etiquetas/trabajos/{t['id']}/validar")
        r = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True})
        assert r.status_code in (200, 422), r.text  # 422: datos del bulto incompletos; lo que importa es que nada cambie
    assert _foto() == antes


def test_lo_pedido_y_lo_empacado_no_se_confunden():
    """Misma clave «cantidad» en las dos colecciones (compatibilidad con los
    diseños), pero títulos que dicen qué cantidad es."""
    col = {c.clave: {x[0]: x[1] for x in c.columnas} for c in campos.COLECCIONES}
    assert col["oc.lineas"]["cantidad"] == "Quantity ordered"
    assert col["bulto.lineas"]["cantidad"] == "Quantity packed in the package"
    nombres = {c.clave: c.etiqueta for c in campos._FIJOS}
    assert nombres["linea.cantidad"] == "Quantity ordered" and nombres["bulto.unidades"] == "Units in the package"


def test_ver_no_es_descargar(client, admin, interno, regla):
    """«etiquetas.ver» deja consultar lo generado; descargar (y con eso marcar
    la ejecución como descargada) es de «etiquetas.generar», como dice el permiso."""
    from conftest import Api

    rol = admin.post("/roles", {"nombre": "Labels reader", "permisos": ["etiquetas.ver"]}).json()
    u = admin.post("/usuarios", {"email": "lector.etq@demo.com", "nombre": "Lector", "rol_id": rol["id"],
                                 "telefono": "+50370000178", "dos_pasos": True}).json()
    lector = Api(client, "lector.etq@demo.com", u["password_temporal"])
    assert lector.post("/auth/password", {"actual": u["password_temporal"], "nueva": "Segura#Clave2026"}).status_code == 200
    (oc_id, lineas), = _ordenes(interno, 1)
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [oc_id], "posiciones": [lineas[0]["id"]],
                                                                           "tipos": [regla["articulo"]["id"]]}}).json()
    interno.post(f"/etiquetas/trabajos/{t['id']}/validar")
    r = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True})
    assert r.status_code == 200, r.text
    gen = r.json()["ejecuciones"][0]
    def descargas():
        from app.core.db import SessionLocal
        from app.modelos import GeneracionEtiquetas

        with SessionLocal() as db:
            return db.get(GeneracionEtiquetas, gen["id"]).descargas

    antes = descargas()
    assert lector.get(f"/etiquetas/generaciones/{gen['id']}").status_code == 200
    assert lector.get(f"/etiquetas/generaciones/{gen['id']}/archivo").status_code == 403
    assert descargas() == antes
    assert lector.get("/etiquetas/trabajos").status_code == 403
    assert lector.get(f"/etiquetas/trabajos/{t['id']}/archivo").status_code in (403, 404)
    # Ver deja consultar la configuración, no cambiarla
    assert lector.get("/etiquetas/matriz").status_code == 200
    assert lector.put("/etiquetas/usos/celda", {"tipo_etiqueta_id": regla["articulo"]["id"], "nivel": "GENERAL", "normal": None}).status_code == 403
