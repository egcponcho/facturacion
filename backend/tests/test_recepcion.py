"""Recepción en bodega por contenedor (docs/FLUJOS.md §3): cada unidad de
carga se recibe en una bodega o bodega fiscal, en una o varias partes, con la
fecha en que se recibió; lo imposible se rechaza, las diferencias abren una
sola alerta por contenedor y proveedor, y con todos sus contenedores
recibidos el embarque queda recibido. Auditoría integral: L-01 a L-06."""
from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion
from app.modelos import Alerta, Embarque, PackingList, RecepcionRegistro, UnidadCarga

HOY = date.today().isoformat()


def _ahora(minutos=0):
    """Un momento de hoy, unos minutos después de ahora: los hitos van en orden
    y después de los que otras pruebas registraron «ahora»."""
    return (datetime.now() + timedelta(minutes=minutos)).replace(microsecond=0).isoformat()


def _en_transito(interno, minimo_pls=1):
    for e in interno.get("/embarques").json():
        if e["estado"] == "EN_TRANSITO":
            det = interno.get(f"/embarques/{e['id']}").json()
            pls = [p for u in det["unidades"] for p in interno.get(f"/unidades/{u['id']}").json()["asignados"]]
            if len(pls) >= minimo_pls:
                return det, pls
    raise AssertionError("La demostración no tiene un embarque en tránsito con carga")


def _con_carga(det):
    return [u for u in det["unidades"] if u["packing_lists"]]


def _alertas_de(unidad_id):
    with SessionLocal() as db, en_organizacion(1):
        return [a for a in db.scalars(select(Alerta).where(Alerta.tipo == "recepcion_diferencia", Alerta.resuelta.is_(False)))
                if (a.referencia or {}).get("unidad_id") == unidad_id]


def test_recepcion_por_contenedor_de_principio_a_fin(admin, interno, client):
    """Un embarque con dos contenedores: permisos (L-01), cantidades
    imposibles (L-02), conteos parciales que suman (L-03), una alerta por
    contenedor y proveedor (L-04), bodega elegida al recibir (L-05), hitos y
    recepción por contenedor y regla de liberación (L-06, L-07)."""
    from conftest import Api

    e, pls = _en_transito(interno, minimo_pls=2)
    # Un segundo contenedor con la otra lista (preparación de la prueba)
    with SessionLocal() as db, en_organizacion(1):
        emb = db.get(Embarque, e["id"])
        nueva = UnidadCarga(tipo="40HC", etiqueta="40HC #9", numero="TEST 0000009", sello="T-9")
        emb.unidades.append(nueva)
        db.flush()
        db.get(PackingList, pls[-1]["id"]).unidad_carga_id = nueva.id
        db.commit()
    det = interno.get(f"/embarques/{e['id']}").json()
    a, b = _con_carga(det)[:2]
    url = f"/unidades/{a['id']}/recepcion"
    cuerpo = lambda **kw: {"fecha": HOY, "centro": e["centro"], **kw}  # noqa: E731

    # Quien solo gestiona transporte ve la recepción pero no la registra
    r = admin.post("/roles", {"nombre": "Solo transporte (prueba)", "permisos": ["transporte.gestionar"]})
    assert r.status_code == 200, r.text
    r = admin.post("/usuarios", {"email": "recepcion.sinpermiso@demo.com", "nombre": "Solo transporte", "rol_id": r.json()["id"],
                                 "telefono": "+50370000141", "dos_pasos": True})
    assert r.status_code == 200, r.text
    nuevo = r.json()
    trans = Api(client, "recepcion.sinpermiso@demo.com", nuevo["password_temporal"])
    assert trans.post("/auth/password", {"actual": nuevo["password_temporal"], "nueva": "Transporte#Clave2026"}).status_code == 200
    r = trans.get(url)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["acciones"]["contar"]["permitida"] is False and d["acciones"]["contar"]["motivo"]
    ln = d["lineas"][0]
    assert trans.post(url, cuerpo(lineas=[{"pl_linea_id": ln["pl_linea_id"], "cantidad": 1}])).status_code == 403

    # Antes del arribo no se recibe
    r = interno.post(url, cuerpo(lineas=[{"pl_linea_id": ln["pl_linea_id"], "cantidad": 1}]))
    assert r.status_code == 409 and r.json()["codigo"] == "embarque_no_llego"
    assert interno.post(f"/embarques/{e['id']}/eventos", {"tipo": "ARRIBO", "fecha": _ahora(1)}).status_code == 200
    arribo = interno.get(f"/embarques/{e['id']}").json()["arribo_real"]

    # Liberación y entrega por contenedor, con la regla de la empresa
    assert admin.put("/organizacion", {"reglas": {"EXIGIR_LIBERACION_ANTES_ENTREGA": True}}).status_code == 200
    evento = lambda tipo, minutos, unidad=None: interno.post(f"/embarques/{e['id']}/eventos", {  # noqa: E731
        "tipo": tipo, "fecha": _ahora(minutos), **({"unidad_carga_id": unidad} if unidad else {})})
    r = evento("ENTREGA", 2, a["id"])
    assert r.status_code == 409 and r.json()["codigo"] == "sin_liberacion"
    assert evento("LIBERACION", 2, a["id"]).status_code == 200
    r = evento("ENTREGA", 3, a["id"])
    assert r.status_code == 200 and r.json()["estado"] == "ARRIBADO"  # falta el otro contenedor
    assert evento("SALIDA", 3, a["id"]).status_code in (409, 422)  # la salida es del embarque
    assert admin.put("/organizacion", {"reglas": {"EXIGIR_LIBERACION_ANTES_ENTREGA": False}}).status_code == 200

    # Lo imposible no entra
    for lineas, que in (([{"pl_linea_id": ln["pl_linea_id"], "cantidad": 1, "danada": 5}], "dañado > contado"),
                        ([{"pl_linea_id": ln["pl_linea_id"], "cantidad": -2}], "negativo en un conteo"),
                        ([{"pl_linea_id": ln["pl_linea_id"], "cantidad": ln["enviado"] + 5}], "sobrante sin explicar"),
                        ([{"pl_linea_id": 999999, "cantidad": 1}], "línea ajena")):
        r = interno.post(url, cuerpo(lineas=lineas))
        assert r.status_code == 422, (que, r.text)
    for fecha in ((date.today() + timedelta(days=2)).isoformat(), (date.fromisoformat(arribo) - timedelta(days=1)).isoformat()):
        r = interno.post(url, {**cuerpo(lineas=[{"pl_linea_id": ln["pl_linea_id"], "cantidad": 1}]), "fecha": fecha})
        assert r.status_code == 422 and r.json()["codigo"] == "fecha_recepcion"
    r = interno.post(url, cuerpo(centro="NOEXISTE", lineas=[{"pl_linea_id": ln["pl_linea_id"], "cantidad": 1}]))
    assert r.status_code == 422

    # Dos conteos parciales suman (antes el segundo borraba el primero), en otra bodega
    otra = next((x["codigo"] for x in d["bodegas"] if x["codigo"] != e["centro"]), e["centro"])
    mitad = int(ln["enviado"] // 2)
    r = interno.post(url, cuerpo(centro=otra, lineas=[{"pl_linea_id": ln["pl_linea_id"], "cantidad": mitad}]))
    assert r.status_code == 200, r.text
    assert r.json()["unidad"]["recepcion_estado"] == "EN_RECEPCION" and r.json()["unidad"]["centro"] == otra
    r = interno.post(url, cuerpo(centro=otra, lineas=[{"pl_linea_id": ln["pl_linea_id"], "cantidad": 1, "danada": 1}]))
    fila = next(x for x in r.json()["lineas"] if x["pl_linea_id"] == ln["pl_linea_id"])
    assert fila["recibido"] == mitad + 1 and fila["danado"] == 1 and len(r.json()["registros"]) == 2

    # Cerrar con faltantes pide motivo; luego queda recibida con su alerta
    assert interno.post(f"{url}/cerrar", {}).status_code == 422
    r = interno.post(f"{url}/cerrar", {"motivo": "Short-shipped by the supplier"})
    assert r.status_code == 200 and r.json()["unidad"]["recepcion_estado"] == "RECIBIDA"
    assert "FALTANTE" in {x["tipo"] for x in r.json()["diferencias"]}
    alertas = _alertas_de(a["id"])
    assert alertas and len(alertas) == len({x.proveedor_id for x in alertas})  # una por proveedor
    assert interno.get(f"/embarques/{e['id']}").json()["estado"] == "ARRIBADO"  # falta el contenedor B

    # Ya cerrada: ni otro conteo ni «sin conteo»; se corrige con un ajuste con motivo
    r = interno.post(url, cuerpo(centro=otra, lineas=[{"pl_linea_id": ln["pl_linea_id"], "cantidad": 1}]))
    assert r.status_code == 409 and r.json()["codigo"] == "recepcion_cerrada"
    assert interno.post(f"{url}/sin-conteo", {"fecha": HOY}).status_code == 409
    ajuste = lambda cantidad, motivo=None: interno.post(url, cuerpo(  # noqa: E731
        centro=otra, tipo="AJUSTE", observacion=motivo, lineas=[{"pl_linea_id": ln["pl_linea_id"], "cantidad": cantidad}]))
    assert ajuste(1).status_code == 422  # sin motivo
    assert ajuste(1, "Carton found in the container").status_code == 200
    assert ajuste(-(mitad + 2), "x").status_code == 422  # dejaría lo dañado por encima de lo recibido
    despues = _alertas_de(a["id"])
    assert {x.id for x in despues} == {x.id for x in alertas}  # la misma alerta, actualizada

    # El contenedor B: entrega y, con el evento de recepción, confirmación sin conteo
    assert evento("ENTREGA", 4, b["id"]).json()["estado"] == "ENTREGADO"
    assert trans.post(f"/embarques/{e['id']}/eventos", {"tipo": "RECEPCION", "fecha": _ahora(5)}).status_code == 403
    r = evento("RECEPCION", 5)
    assert r.status_code == 200 and r.json()["estado"] == "RECIBIDO", r.text
    db_ = interno.get(f"/unidades/{b['id']}/recepcion").json()
    assert db_["unidad"]["recepcion_estado"] == "RECIBIDA" and db_["totales"]["pendiente"] == 0
    assert any(g["tipo"] == "SIN_CONTEO" and g["usuario"] for g in db_["registros"])
    det = interno.get(f"/embarques/{e['id']}").json()
    assert sum(1 for ev in det["eventos"] if ev["tipo"] == "RECEPCION") == 1
    with SessionLocal() as db, en_organizacion(1):
        centros = {g.unidad_carga_id: g.centro for g in db.scalars(select(RecepcionRegistro).where(
            RecepcionRegistro.unidad_carga_id.in_([a["id"], b["id"]])))}
        assert db.get(UnidadCarga, a["id"]).recibida_en.isoformat() == HOY  # la fecha operativa
    assert centros == {a["id"]: otra, b["id"]: e["centro"]}

    # Existencias por bodega y su kardex
    inv = interno.get("/existencias", params={"centro": otra}).json()
    assert any(it["codigo"] == ln["codigo"] and it["recibido"] == mitad + 2 and it["danado"] == 1 for it in inv["items"])
    kardex = interno.get("/existencias/movimientos", params={"centro": otra, "codigo": ln["codigo"],
                                                             }).json()
    assert {m["tipo"] for m in kardex} == {"CONTEO", "AJUSTE"}
    assert trans.get("/existencias").status_code == 403

    # La pantalla del PL muestra la recepción de su contenedor y por qué no se reabre
    pl = interno.get(f"/packing-lists/{pls[0]['id']}").json()
    assert pl["recepcion_unidad"]["recepcion_estado"] == "RECIBIDA"
    assert pl["bloqueos"]["reabrir"] and pl["bloqueos"]["cancelar"]


def test_anular_un_embarque(interno):
    e = interno.post("/embarques", {"tipo_transporte": "MARITIMO"}).json()
    assert interno.post(f"/embarques/{e['id']}/cancelar", {}).status_code == 422  # pide motivo
    r = interno.post(f"/embarques/{e['id']}/cancelar", {"motivo": "Booking cancelled by the carrier"})
    assert r.status_code == 200 and r.json()["estado"] == "CANCELADO"
    r = interno.post(f"/embarques/{e['id']}/cancelar", {"motivo": "otra vez"})
    assert r.status_code == 409 and r.json()["codigo"] == "transicion_invalida"
    # Uno que ya salió no se anula
    salido = next((x for x in interno.get("/embarques").json() if x["estado"] not in ("PLANIFICADO", "CANCELADO")), None)
    if salido:
        assert interno.post(f"/embarques/{salido['id']}/cancelar", {"motivo": "x"}).status_code == 409
