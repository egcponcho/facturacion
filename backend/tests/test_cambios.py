"""Cambios de datos (app/core/cambios.py), igual en SQLite y PostgreSQL:

- la versión de una tabla sube al confirmar un alta, cambio o baja (ORM o SQL
  directo) y no sube si se revierte; las tablas técnicas no cuentan;
- un GET repetido sin cambios responde 304 sin volver a consultar los datos;
  cualquier cambio en lo que leyó (en cualquier organización) da 200 nuevo;
- la ETag es de un usuario: otro usuario, una sesión cerrada o un permiso
  quitado nunca reciben 304;
- el canal de cambios avisa a cada organización solo de lo suyo.
"""
import json
import threading
import time

from sqlalchemy import event, select, text

from app.core import cambios
from app.core.db import SessionLocal, engine
from app.core.organizacion import en_organizacion
from app.modelos import OrdenCompra

URL = "/api/ordenes?solo_disponible=false&page=1&size=5"


def _version(tabla, ambito=None):
    with SessionLocal() as db:
        q = "SELECT COALESCE(SUM(version), 0) FROM versiones_datos WHERE tabla = :t" + (" AND ambito = :a" if ambito is not None else "")
        return int(db.execute(text(q), {"t": tabla, "a": ambito}).scalar())


def _tocar_oc(org=1, revertir=False):
    """Un cambio real en una OC de la organización (y lo deja como estaba)."""
    with SessionLocal() as db, en_organizacion(org):
        oc = db.scalar(select(OrdenCompra).order_by(OrdenCompra.id))
        oc.extra = {**(oc.extra or {}), "prueba_cambios": time.time()}
        if revertir:
            db.rollback()
        else:
            db.commit()


def _get(api, url=URL, etag=None):
    h = dict(api.h)
    if etag:
        h["If-None-Match"] = etag
    return api.c.get(url, headers=h)


def _con_etag(api, url=URL):
    """La primera vez la ruta se aprende; desde la segunda lleva ETag."""
    r = _get(api, url)
    if "etag" not in r.headers:
        r = _get(api, url)
    assert r.status_code == 200 and r.headers.get("etag"), r.headers
    return r


def test_version_sube_al_confirmar_y_no_al_revertir(client):
    antes = _version("ordenes_compra", 1)
    _tocar_oc()
    assert _version("ordenes_compra", 1) == antes + 1
    _tocar_oc(revertir=True)
    assert _version("ordenes_compra", 1) == antes + 1
    # SQL directo y actualización masiva también cuentan
    with SessionLocal() as db:
        db.execute(text("UPDATE ordenes_compra SET actualizado_en = actualizado_en WHERE id = (SELECT MIN(id) FROM ordenes_compra)"))
        db.commit()
    assert _version("ordenes_compra") >= antes + 2
    # Las tablas técnicas no cuentan
    assert _version("sesiones") == 0 and _version("idempotencia") == 0


def test_304_sin_volver_a_consultar(interno):
    r = _con_etag(interno)
    assert "ordenes_compra" in r.headers["x-tablas"].split(",")
    consultas = []

    def contar(_c, _cur, sql, *_a):
        if "ordenes_compra" in sql:
            consultas.append(sql)
    event.listen(engine, "before_cursor_execute", contar)
    try:
        r2 = _get(interno, etag=r.headers["etag"])
    finally:
        event.remove(engine, "before_cursor_execute", contar)
    assert r2.status_code == 304 and r2.content == b"" and r2.headers["etag"] == r.headers["etag"]
    assert consultas == [], "a 304 must not run the query"
    # Un cambio en lo que leyó: 200 con datos y otra ETag
    _tocar_oc()
    r3 = _get(interno, etag=r.headers["etag"])
    assert r3.status_code == 200 and r3.json()["items"] and r3.headers["etag"] != r.headers["etag"]
    # Un cambio en otra organización también invalida (la versión es de toda la tabla)
    r4 = _con_etag(interno)
    _tocar_oc(org=2 if _hay_oc(2) else 1)
    assert _get(interno, etag=r4.headers["etag"]).status_code == 200


def _hay_oc(org):
    with SessionLocal() as db, en_organizacion(org):
        return db.scalar(select(OrdenCompra.id).limit(1)) is not None


def test_la_etag_es_del_usuario_y_respeta_sesion_y_permisos(client, admin, interno, tnf):
    r = _con_etag(interno)
    # Otro usuario con la misma ETag: sus datos, no un 304
    otro = _get(tnf, etag=r.headers["etag"])
    assert otro.status_code == 200
    # Sesión cerrada: 401, no 304
    from conftest import Api

    nuevo = Api(client, "interno@demo.com")
    e = _con_etag(nuevo).headers["etag"]
    from app.modulos.acceso.autenticacion import cerrar_sesion

    with SessionLocal() as db:  # el cierre por la API lee la cookie; aquí la sesión viaja como Bearer
        cerrar_sesion(db, nuevo.h["Authorization"][7:])
    assert _get(nuevo, etag=e).status_code == 401
    # Permiso quitado: 403, no 304
    rol = admin.post("/roles", {"nombre": "Cache PO reader", "permisos": ["oc.ver"]}).json()
    u = admin.post("/usuarios", {"email": "cache.oc@demo.com", "nombre": "Cache", "rol_id": rol["id"],
                                 "telefono": "+50370000179", "dos_pasos": True}).json()
    lector = Api(client, "cache.oc@demo.com", u["password_temporal"])
    assert lector.post("/auth/password", {"actual": u["password_temporal"], "nueva": "Segura#Clave2026"}).status_code == 200
    e = _con_etag(lector).headers["etag"]
    assert _get(lector, etag=e).status_code == 304
    assert admin.patch(f"/roles/{rol['id']}", {"nombre": "Cache PO reader", "permisos": ["factura.ver"]}).status_code == 200
    assert _get(lector, etag=e).status_code == 403


def test_canal_de_cambios_avisa_lo_que_cambia(interno):
    """Integración: el navegador conectado recibe la tabla que cambió en su organización."""
    eventos = []

    def escribir():
        time.sleep(1.2)
        _tocar_oc(org=1)

    # TestClient entrega la respuesta completa al cerrarse el canal: el cambio se hace desde otro hilo
    hilo = threading.Thread(target=escribir)
    hilo.start()
    with interno.c.stream("GET", "/api/cambios", params={"max_seg": 3}, headers=interno.h) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        for linea in r.iter_lines():
            if linea.startswith("data: "):
                eventos.append(json.loads(linea[6:])["tablas"])
    hilo.join()
    assert eventos and all("ordenes_compra" in e for e in eventos), eventos
    assert not cambios.difusor.clientes, "the client is removed when the stream ends"


def test_el_canal_avisa_a_cada_organizacion_solo_lo_suyo():
    import asyncio

    d = cambios.Difusor()
    d._leer = lambda: {("ordenes_compra", 1): 5, ("ordenes_compra", 2): 3, ("paises", 0): 1, ("sesiones", 1): 9}
    a, b = asyncio.run(d.conectar(1)), asyncio.run(d.conectar(2))  # la base se toma al conectarse el primero
    assert a.cola.empty() and b.cola.empty()
    d.revisar({("ordenes_compra", 1): 5, ("ordenes_compra", 2): 4, ("paises", 0): 1, ("sesiones", 1): 10})
    assert a.cola.empty(), "a change of organization 2 is not announced to organization 1"
    assert b.cola.get_nowait() == ["ordenes_compra"]
    d.revisar({("ordenes_compra", 1): 6, ("ordenes_compra", 2): 4, ("paises", 0): 2, ("sesiones", 1): 10})
    assert a.cola.get_nowait() == ["ordenes_compra", "paises"]  # lo suyo y lo compartido
    assert b.cola.get_nowait() == ["paises"]


def test_iniciar_sesion_no_invalida_lo_guardado(client, interno):
    """El último ingreso es un dato de rastreo: que alguien entre no obliga a
    todos a volver a pedir sus datos. Un cambio real del usuario sí cuenta."""
    from conftest import Api

    e = _con_etag(interno).headers["etag"]
    antes = _version("usuarios")
    Api(client, "admin@demo.com")
    assert _version("usuarios") == antes
    assert _get(interno, etag=e).status_code == 304
    with SessionLocal() as db:
        db.execute(text("UPDATE usuarios SET nombre = nombre WHERE email = 'interno@demo.com'"))
        db.commit()
    assert _version("usuarios") == antes + 1


def test_la_etag_sale_desde_la_primera_visita(interno):
    url = "/api/ordenes?solo_disponible=false&page=1&size=3&q=etag-primera"
    r = _get(interno, url)
    assert r.status_code == 200 and r.headers.get("etag"), "first visit already carries an ETag"
    assert _get(interno, url, etag=r.headers["etag"]).status_code == 304
