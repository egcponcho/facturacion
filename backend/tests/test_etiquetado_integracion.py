"""Etiquetado e información operativa: generar, descargar y marcar impresas
las etiquetas lee las OC, sus líneas, las listas de empaque y la recepción,
pero no cambia cantidades, saldos, estados ni movimientos. Y en los datos de
la etiqueta lo pedido (OC) y lo empacado (bulto) no se confunden."""
import pytest
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
    p = interno.post("/etiquetas/plantillas", {"nombre": "Integration design", "modalidad": "OC_ARTICULO", "diseno": DISENO}).json()
    v = p["versiones"][0]["id"]
    assert interno.post(f"/etiquetas/versiones/{v}/enviar", {}).status_code == 200
    assert admin.post(f"/etiquetas/versiones/{v}/aprobar", {}).status_code == 200
    r = interno.post("/etiquetas/asignaciones", {"plantilla_id": p["id"], "ambito": "REGLA", "prioridad": 9991, "nombre": "Integration",
                                                 "condiciones": [{"campo": "contexto.origen", "op": "existe"}]}).json()
    yield p
    interno.c.delete(f"/api/etiquetas/asignaciones/{r['id']}", headers=interno.h)


def test_generar_no_modifica_ordenes_listas_ni_recepcion(interno, regla):
    ocs = []
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        lineas = [x for x in interno.get(f"/etiquetas/oc/{o['id']}").json()["lineas"] if x["articulo_id"] and not x["bloqueada"]]
        if lineas:
            ocs.append((o["id"], lineas))
        if len(ocs) == 2:
            break
    assert ocs, "the demo has POs with items"
    antes = _foto()
    # Trabajo desde varias OC: validar, generar, descargar el ZIP y confirmar la impresión
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {
        "oc_ids": [o for o, _ in ocs], "posiciones": [x["id"] for _, ls in ocs for x in ls[:2]], "unidad": "UNIDAD"}}).json()
    assert interno.post(f"/etiquetas/trabajos/{t['id']}/validar").status_code == 200
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True, "parcial": True})
    assert g.status_code == 200, g.text
    assert g.json()["estado"] in ("GENERADO", "PARCIAL") and g.json()["ejecuciones"]
    assert interno.get(f"/etiquetas/trabajos/{t['id']}/archivo").status_code == 200
    for e in interno.get(f"/etiquetas/trabajos/{t['id']}").json()["ejecuciones"]:
        interno.post(f"/etiquetas/generaciones/{e['id']}/impresion", {"confirmo": True, "cantidad": e["total"]})
    # Por bulto desde una lista de empaque
    pls = [x for x in interno.get("/etiquetas/masivo/packing").json()
           if interno.get(f"/etiquetas/masivo/packing/{x['id']}").json()["superiores"]]
    if pls:
        r = interno.post("/etiquetas/generaciones", {"pl_id": pls[0]["id"], "modalidad": "OC_ARTICULO", "unidad": "BULTO",
                                                     "aceptar_advertencias": True})
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
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        lineas = [x for x in interno.get(f"/etiquetas/oc/{o['id']}").json()["lineas"] if x["articulo_id"] and not x["bloqueada"]]
        if lineas:
            break
    r = interno.post("/etiquetas/generaciones", {"oc_id": o["id"], "modalidad": "OC_ARTICULO", "unidad": "LINEA",
                                                 "posiciones": [lineas[0]["id"]], "aceptar_advertencias": True})
    assert r.status_code == 200, r.text
    gen = r.json()
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
    assert lector.get(f"/etiquetas/masivo/{gen.get('lote') or 'x'}/archivo").status_code == 403
