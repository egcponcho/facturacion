"""Ejecución duradera de los trabajos de etiquetado (corre igual en SQLite y,
con TEST_DATABASE_URL, en PostgreSQL):

- la toma de un trabajo es atómica aunque varios procesos la intenten a la vez;
- un ejecutor que perdió el arriendo no confirma nada;
- un registro produce un solo grupo de etiquetas (restricción única en la base);
- tras un reinicio (arriendo vencido o trabajo nunca tomado) otra instancia lo
  retoma y termina sin duplicar; un arriendo vigente no se roba;
- un error en una parte deja PARCIAL lo hecho y el reintento genera solo lo que falta;
- un trabajo que agotó sus intentos queda en ERROR;
- dos reintentos simultáneos no duplican;
- otra organización no ve, descarga ni retoma los trabajos ajenos.
"""
import contextvars
import threading
from datetime import timedelta

import pytest
from conftest import Api
from etiquetado_util import aprobada, tipo, uso
from sqlalchemy import func, select, text

from app.core.db import SessionLocal, engine
from app.core.organizacion import en_organizacion
from app.modelos import GeneracionEtiquetas, GeneracionItem, TrabajoEtiquetas, TrabajoRegistro, Usuario
from app.modelos.base import ahora
from app.modulos.etiquetado import generacion, trabajos

DISENO = {"ancho": 50, "alto": 20, "elementos": [{"id": "s", "tipo": "campo", "campo": "articulo.sku", "x": 2, "y": 2, "w": 40, "h": 8}]}


@pytest.fixture(scope="module")
def regla(interno, admin):
    """El tipo de etiqueta de estas pruebas con su diseño aprobado en toda la empresa."""
    t = tipo(interno, "DUR_LINEA")
    p = aprobada(interno, admin, "Durable job design", t["id"], DISENO["elementos"], ancho=DISENO["ancho"], alto=DISENO["alto"])
    uso(interno, t["id"], p["id"])
    return {"tipo": t, "plantilla": p}


@pytest.fixture(scope="module")
def ordenes(interno):
    res = []
    for o in interno.get("/ordenes", params={"solo_disponible": False, "size": 100}).json()["items"]:
        d = interno.get(f"/ordenes/{o['id']}").json()
        lineas = [x for x in d["posiciones"] if x.get("codigo_articulo")]
        if d["oc"]["estado"] != "BORRADOR" and lineas:
            res.append({"id": o["id"], "lineas": lineas})
        if len(res) == 2:
            return res
    pytest.skip("two POs with items are needed")


def _en_proceso(interno, ordenes, monkeypatch, n=2):
    """Un trabajo que generar() deja EN_PROCESO para el segundo plano, sin que este proceso lo tome."""
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {
        "oc_ids": [o["id"] for o in ordenes[:n]], "posiciones": [o["lineas"][0]["id"] for o in ordenes[:n]],
        "tipos": [tipo(interno, "DUR_LINEA")["id"]]}}).json()
    from app.core import empresa

    real = empresa.regla
    monkeypatch.setattr(trabajos, "lanzar", lambda *a, **k: False)
    monkeypatch.setattr(trabajos, "regla", lambda k: 1 if k == "ETIQUETAS_ASINCRONO_DESDE" else real(k))
    r = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "EN_PROCESO" and r.json()["asincrono"]
    monkeypatch.undo()
    return t["id"]


def _fila(tid):
    with SessionLocal() as db:
        t = db.get(TrabajoEtiquetas, tid)
        regs = db.scalars(select(TrabajoRegistro).where(TrabajoRegistro.trabajo_id == tid)).all()
        items = db.scalars(select(GeneracionItem).join(TrabajoRegistro, TrabajoRegistro.id == GeneracionItem.trabajo_registro_id)
                           .where(TrabajoRegistro.trabajo_id == tid)).all()
        ejecs = db.scalar(select(func.count()).select_from(GeneracionEtiquetas).where(GeneracionEtiquetas.trabajo_id == tid))
        return t, regs, items, ejecs


def _vencer(tid, ejecutor="otra-instancia:999:caida"):
    with SessionLocal() as db:
        db.execute(text("UPDATE trabajos_etiqueta SET ejecutor = :e, arriendo_hasta = :h WHERE id = :i"),
                   {"e": ejecutor, "h": ahora() - timedelta(minutes=5), "i": tid})
        db.commit()


def _sin_duplicados(tid):
    t, regs, items, ejecs = _fila(tid)
    assert len({i.trabajo_registro_id for i in items}) == len(items), "a record produced two label groups"
    return t, regs, items, ejecs


def test_toma_atomica_entre_varios_procesos(interno, regla, ordenes, monkeypatch):
    tid = _en_proceso(interno, ordenes, monkeypatch)
    fichas, barrera = [], threading.Barrier(6)

    def intentar():
        barrera.wait()
        with SessionLocal() as db:
            try:
                fichas.append(trabajos._tomar(db, tid))
            except Exception as e:  # noqa: BLE001 - SQLite puede rechazar a un escritor concurrente
                fichas.append(f"error:{type(e).__name__}")
    hilos = [threading.Thread(target=intentar) for _ in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    ganadas = [f for f in fichas if f and not f.startswith("error:")]
    assert len(ganadas) == 1, fichas
    # Quien la tomó la termina; nadie más pudo
    trabajos.ejecutar_tomado(tid, ganadas[0])
    t, regs, items, ejecs = _sin_duplicados(tid)
    assert t.estado == "GENERADO" and t.ejecutor is None and len(items) == len(regs) == ejecs == 2


def test_ejecutor_que_perdio_el_arriendo_no_confirma(interno, regla, ordenes, monkeypatch):
    tid = _en_proceso(interno, ordenes, monkeypatch)
    with SessionLocal() as db:
        vieja = trabajos._tomar(db, tid)
    _vencer(tid, vieja)
    with SessionLocal() as db:
        nueva = trabajos._tomar(db, tid)  # otra instancia lo retoma al vencer el arriendo
    assert vieja and nueva and vieja != nueva
    # El ejecutor anterior seguía vivo e intenta confirmar una parte
    ctx = contextvars.copy_context()

    def viejo():
        db = SessionLocal()
        try:
            t = db.get(TrabajoEtiquetas, tid)
            user = db.get(Usuario, t.resumen["pedido"]["por"])
            trabajos._contexto(db, user)
            t = db.get(TrabajoEtiquetas, tid)
            with pytest.raises(trabajos.ArriendoPerdido):
                trabajos._ejecutar(db, user, t, t.resumen["pedido"]["claves"], "PDF", vieja)
            db.rollback()
        finally:
            db.close()
    ctx.run(viejo)
    t, regs, items, ejecs = _fila(tid)
    assert items == [] and ejecs == 0 and t.ejecutor == nueva, "the old executor must not commit anything"
    trabajos.ejecutar_tomado(tid, nueva)
    t, regs, items, ejecs = _sin_duplicados(tid)
    assert t.estado == "GENERADO" and len(items) == len(regs) == ejecs


def test_un_registro_no_se_genera_dos_veces(interno, regla, ordenes, monkeypatch):
    tid = _en_proceso(interno, ordenes, monkeypatch, n=1)
    with SessionLocal() as db:
        ficha = trabajos._tomar(db, tid)
    trabajos.ejecutar_tomado(tid, ficha)
    t, regs, items, _ = _fila(tid)
    assert len(items) == 1
    # Volver a generar ese registro (como haría una ejecución repetida) choca con la base
    from sqlalchemy.exc import IntegrityError

    ctx = contextvars.copy_context()

    def repetir():
        db = SessionLocal()
        try:
            t = db.get(TrabajoEtiquetas, tid)
            user = db.get(Usuario, t.resumen["pedido"]["por"])
            trabajos._contexto(db, user)
            t = db.get(TrabajoEtiquetas, tid)
            prefijo, pedido = trabajos._partes(db, t)[0]
            interna = regs[0].clave.split(":", 1)[1]
            grupos = [g for g in generacion.planear(db, user, pedido, solo={interna})["_grupos"] if g.clave == interna]
            with pytest.raises(IntegrityError):
                generacion.producir(db, user, grupos, {**pedido, "formato": "PDF", "_registros": {interna: regs[0].id},
                                                       "_trabajo_id": tid})
            db.rollback()
        finally:
            db.close()
    ctx.run(repetir)
    assert len(_fila(tid)[2]) == 1


def test_reinicio_otra_instancia_retoma_y_no_roba_un_arriendo_vigente(interno, regla, ordenes, monkeypatch):
    # Arriendo vigente de otro proceso: no se toca
    viva = _en_proceso(interno, ordenes, monkeypatch, n=1)
    with SessionLocal() as db:
        db.execute(text("UPDATE trabajos_etiqueta SET ejecutor = 'viva:1:x', arriendo_hasta = :h WHERE id = :i"),
                   {"h": ahora() + timedelta(minutes=5), "i": viva})
        db.commit()
    # Proceso que cayó a mitad (arriendo vencido) y otro que cayó antes de tomarlo
    caido = _en_proceso(interno, ordenes, monkeypatch)
    _vencer(caido)
    nunca = _en_proceso(interno, ordenes, monkeypatch, n=1)
    with SessionLocal() as db:
        db.execute(text("UPDATE trabajos_etiqueta SET actualizado_en = :h WHERE id = :i"),
                   {"h": ahora() - timedelta(hours=1), "i": nunca})
        db.commit()
    retomados = trabajos.recuperar()
    assert caido in retomados and nunca in retomados and viva not in retomados
    for tid in (caido, nunca):
        t, regs, items, ejecs = _sin_duplicados(tid)
        assert t.estado == "GENERADO" and len(items) == len(regs) and t.ejecutor is None and t.intentos >= 1
    t, regs, items, _ = _fila(viva)
    assert t.estado == "EN_PROCESO" and t.ejecutor == "viva:1:x" and items == []
    # Una segunda pasada no vuelve a generar nada
    assert trabajos.recuperar() == []
    with SessionLocal() as db:  # se deja como abandonado para no afectar a otras pruebas
        db.execute(text("UPDATE trabajos_etiqueta SET estado = 'CANCELADO', ejecutor = NULL, arriendo_hasta = NULL WHERE id = :i"),
                   {"i": viva})
        db.commit()


def test_error_en_una_parte_deja_parcial_y_el_reintento_completa(interno, regla, ordenes, monkeypatch):
    tid = _en_proceso(interno, ordenes, monkeypatch)
    original, llamadas = generacion.producir, []

    def falla_la_segunda(db, user, grupos, pedido):
        llamadas.append(pedido.get("oc_id"))
        if len(llamadas) == 2:
            raise RuntimeError("printer driver exploded")
        return original(db, user, grupos, pedido)
    monkeypatch.setattr(generacion, "producir", falla_la_segunda)
    with SessionLocal() as db:
        ficha = trabajos._tomar(db, tid)
    trabajos.ejecutar_tomado(tid, ficha)
    monkeypatch.undo()
    t, regs, items, ejecs = _sin_duplicados(tid)
    assert t.estado == "PARCIAL" and "printer driver exploded" in t.error and t.ejecutor is None
    assert len(items) == 1 and ejecs == 1
    assert sorted(r.estado for r in regs) in (["GENERADO", "LISTO"], ["ADVERTENCIA", "GENERADO"])
    # Reintento: solo lo que faltaba
    g = interno.post(f"/etiquetas/trabajos/{tid}/generar", {"aceptar_advertencias": True})
    assert g.status_code == 200, g.text
    t, regs, items, ejecs = _sin_duplicados(tid)
    assert t.estado == "GENERADO" and len(items) == len(regs) == ejecs == 2


def test_intentos_agotados_quedan_en_error(interno, regla, ordenes, monkeypatch):
    tid = _en_proceso(interno, ordenes, monkeypatch, n=1)
    _vencer(tid)
    with SessionLocal() as db:
        db.execute(text("UPDATE trabajos_etiqueta SET intentos = 99 WHERE id = :i"), {"i": tid})
        db.commit()
    assert tid not in trabajos.recuperar()
    t, _, items, _ = _fila(tid)
    assert t.estado == "ERROR" and items == [] and "several times" in t.error


def test_reintentos_simultaneos_no_duplican(interno, regla, ordenes):
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {
        "oc_ids": [o["id"] for o in ordenes], "posiciones": [o["lineas"][0]["id"] for o in ordenes],
        "tipos": [regla["tipo"]["id"]]}}).json()
    interno.post(f"/etiquetas/trabajos/{t['id']}/validar")
    resultados, barrera = [], threading.Barrier(3)

    def pedir():
        ctx = contextvars.copy_context()

        def correr():
            db = SessionLocal()
            try:
                user = db.get(Usuario, interno.yo["id"])
                trabajos._contexto(db, user)
                barrera.wait()
                trabajos.generar(db, user, t["id"], {"aceptar_advertencias": True})
                db.commit()
                resultados.append("ok")
            except Exception as e:  # noqa: BLE001
                db.rollback()
                resultados.append(getattr(e, "codigo", type(e).__name__))
            finally:
                db.close()
        ctx.run(correr)
    hilos = [threading.Thread(target=pedir) for _ in range(3)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert resultados.count("ok") >= 1, resultados
    tr, regs, items, ejecs = _sin_duplicados(t["id"])
    assert tr.estado == "GENERADO" and len(items) == len(regs) == ejecs == 2, (resultados, ejecs)


@pytest.fixture(scope="module")
def otra_org(client, admin):
    r = admin.post("/plataforma/organizaciones", {"codigo": "ETQ2", "nombre": "Etiquetas Dos", "pais": "sv",
                                                  "admin_email": "etq2@demo.com", "admin_nombre": "Etq admin",
                                                  "admin_telefono": "+50370000177"})
    assert r.status_code == 200, r.text
    org = r.json()
    api = Api(client, "etq2@demo.com", org["password_temporal"])
    assert api.post("/auth/password", {"actual": org["password_temporal"], "nueva": "Etiquetas#2026x"}).status_code == 200
    yield org, api
    admin.patch(f"/plataforma/organizaciones/{org['id']}", {"activa": False})


def test_otra_organizacion_no_ve_ni_descarga_ni_retoma(interno, regla, ordenes, otra_org):
    org, otra = otra_org
    t = interno.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [ordenes[0]["id"]],
                                                                            "posiciones": [ordenes[0]["lineas"][0]["id"]],
                                                                            "tipos": [regla["tipo"]["id"]]}}).json()
    g = interno.post(f"/etiquetas/trabajos/{t['id']}/generar", {"aceptar_advertencias": True}).json()
    assert g["estado"] == "GENERADO"
    reg, ejec = g["registros"][0], g["ejecuciones"][0]
    for url in (f"/etiquetas/trabajos/{t['id']}", f"/etiquetas/trabajos/{t['id']}/estado", f"/etiquetas/trabajos/{t['id']}/archivo",
                f"/etiquetas/trabajos/{t['id']}/registros/{reg['id']}/vista-previa", f"/etiquetas/generaciones/{ejec['id']}",
                f"/etiquetas/generaciones/{ejec['id']}/archivo"):
        assert otra.get(url).status_code == 404, url
    assert otra.post(f"/etiquetas/trabajos/{t['id']}/generar", {}).status_code == 404
    assert otra.post(f"/etiquetas/trabajos/{t['id']}/cancelar").status_code == 404
    assert otra.post(f"/etiquetas/generaciones/{ejec['id']}/impresion", {"confirmo": True, "cantidad": 1}).status_code == 404
    assert otra.get("/etiquetas/trabajos", params={"estado": ""}).json()["items"] == []
    # Un trabajo de la otra organización no puede apuntar a una OC de esta
    assert otra.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [ordenes[0]["id"]]}}).status_code == 404
    # Lo que recupera un proceso queda en la organización del trabajo
    with SessionLocal() as db, en_organizacion(1):
        assert {i.organizacion_id for i in db.scalars(select(GeneracionItem).where(
            GeneracionItem.trabajo_registro_id == reg["id"]))} == {1}


def test_seguridad_por_fila_de_los_trabajos_en_postgresql(interno, regla, ordenes, otra_org):
    """Aun con SQL escrito a mano, otra organización no lee ni escribe trabajos,
    registros, campos lógicos, tipos ni usos de diseño ajenos, y las llaves de coherencia
    impiden enlazar un registro con una OC de otra organización."""
    if engine.dialect.name != "postgresql":
        pytest.skip("RLS solo existe en PostgreSQL")
    org, _ = otra_org
    fijar = text("SELECT set_config('app.organizacion_id', :o, true)")
    with engine.begin() as con:
        assert con.execute(text("SELECT count(*) FROM trabajos_etiqueta")).scalar() > 0
        un_trabajo = con.execute(text("SELECT id FROM trabajos_etiqueta ORDER BY id LIMIT 1")).scalar()
        una_oc = con.execute(text("SELECT id FROM ordenes_compra WHERE organizacion_id = 1 LIMIT 1")).scalar()
    with engine.begin() as con:
        con.execute(fijar, {"o": str(org["id"])})
        for tabla in ("trabajos_etiqueta", "trabajo_etiqueta_registros", "usos_diseno", "tipos_etiqueta", "generacion_items",
                      "generaciones_etiqueta"):
            assert con.execute(text(f"SELECT count(*) FROM {tabla}")).scalar() == 0, tabla
        assert con.execute(text("UPDATE trabajos_etiqueta SET nombre = 'x' WHERE id = :i"), {"i": un_trabajo}).rowcount == 0
    with pytest.raises(Exception, match="row-level security"):
        with engine.begin() as con:
            con.execute(fijar, {"o": str(org["id"])})
            con.execute(text("INSERT INTO campos_etiqueta (clave, etiqueta, tipo, fuentes, politica, sujetos, activo, creado_en,"
                             " version, organizacion_id) VALUES ('x', 'x', 'texto', '[]', 'PRIMERA', '[]', true, now(), 1, 1)"))
    # Sin RLS de por medio (mantenimiento), la llave de coherencia sigue impidiendo mezclar organizaciones
    with pytest.raises(Exception, match="fk_trabajos_etiqueta|fk_trabajo_etiqueta_registros_oc_id_org|foreign key"):
        with engine.begin() as con:
            t2 = con.execute(text("INSERT INTO trabajos_etiqueta (nombre, origen, estado, paso, parametros, resumen, total, progreso,"
                                  " version, creado_en, actualizado_en, intentos, organizacion_id) VALUES ('x', 'OC', 'BORRADOR', 0,"
                                  " '{}', '{}', 0, 0, 1, now(), now(), 0, :o) RETURNING id"), {"o": org["id"]}).scalar()
            con.execute(text("INSERT INTO trabajo_etiqueta_registros (trabajo_id, orden, clave, oc_id, cantidad, estado, problemas,"
                             " organizacion_id) VALUES (:t, 0, 'x', :oc, 1, 'LISTO', '[]', :o)"),
                        {"t": t2, "oc": una_oc, "o": org["id"]})
