"""Aislamiento por empresa en el etiquetado: una organización no ve ni usa los
tipos, diseños, usos, trabajos ni datos de origen de otra. Dos barreras: el
servicio (cada consulta se limita a la organización: un id ajeno «no existe»)
y la base de datos (llaves compuestas (id, organizacion_id): una fila no puede
apuntar a una fila de otra organización aunque el servicio fallara)."""
import pytest
from conftest import Api
from etiquetado_util import aprobada, oc_con_articulos, tipo, trabajo, uso
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal
from app.core.organizacion import en_organizacion

TEXTO = [{"id": "t", "tipo": "texto", "contenido": "{{articulo.sku}}", "x": 3, "y": 3, "w": 50, "h": 8}]


@pytest.fixture(scope="module")
def segunda(client, admin):
    r = admin.post("/plataforma/organizaciones", {"codigo": "ETQ2", "nombre": "Second labels company", "pais": "gt",
                                                  "admin_email": "etq2@demo.com", "admin_nombre": "Labels admin 2",
                                                  "admin_telefono": "+50200000002"})
    assert r.status_code == 200, r.text
    org = r.json()
    api = Api(client, "etq2@demo.com", org["password_temporal"])
    assert api.post("/auth/password", {"actual": org["password_temporal"], "nueva": "Etiquetas#2026x"}).status_code == 200
    yield org, api
    admin.patch(f"/plataforma/organizaciones/{org['id']}", {"activa": False})


def test_otra_empresa_no_ve_ni_usa_lo_ajeno(interno, admin, segunda):
    org2, api2 = segunda
    t1 = tipo(interno, "AISLADO")
    d1 = aprobada(interno, admin, "Isolated design", t1["id"], TEXTO)
    u1 = uso(interno, t1["id"], d1["id"])
    datos = oc_con_articulos(interno)
    tr1 = trabajo(interno, "OC", {"oc_ids": [datos["oc"]["id"]], "tipos": [t1["id"]]})

    # No ve nada de la primera empresa
    assert all(x["id"] != t1["id"] for x in api2.get("/etiquetas/tipos", params={"todos": True}).json())
    assert all(x["id"] != d1["id"] for x in api2.get("/etiquetas/plantillas").json()["items"])
    assert api2.get(f"/etiquetas/plantillas/{d1['id']}").status_code == 404
    assert api2.get(f"/etiquetas/trabajos/{tr1['id']}").status_code == 404
    assert api2.get(f"/etiquetas/usos/{u1['id']}/historial").status_code == 404
    # Ni puede usarlo: un uso con el tipo y el diseño ajenos, un trabajo con la OC ajena
    t2 = tipo(api2, "AISLADO")
    assert t2["id"] != t1["id"]
    r = api2.post("/etiquetas/usos", {"tipo_etiqueta_id": t2["id"], "plantilla_id": d1["id"], "nivel": "GENERAL",
                                      "contexto_tipo": "NINGUNO"})
    assert r.status_code in (404, 422), r.text
    r = api2.post("/etiquetas/usos", {"tipo_etiqueta_id": t1["id"], "plantilla_id": d1["id"], "nivel": "GENERAL",
                                      "contexto_tipo": "NINGUNO"})
    assert r.status_code in (404, 422), r.text
    r = api2.post("/etiquetas/trabajos", {"origen": "OC", "parametros": {"oc_ids": [datos["oc"]["id"]], "tipos": [t2["id"]]}})
    if r.status_code == 200:  # se crea vacío: al revisarlo, la OC ajena no existe
        v = api2.post(f"/etiquetas/trabajos/{r.json()['id']}/validar").json()
        assert not v["registros"]
    else:
        assert r.status_code in (404, 422)
    # Ni cambiar lo ajeno
    assert api2.post(f"/etiquetas/usos/{u1['id']}/baja", {"motivo": "x"}).status_code == 404
    assert api2.post(f"/etiquetas/trabajos/{tr1['id']}/generar", {"formato": "PDF", "version": tr1["version"]}).status_code == 404
    # La primera empresa sigue igual
    assert interno.get(f"/etiquetas/trabajos/{tr1['id']}").status_code == 200


def test_la_base_rechaza_filas_que_cruzan_empresas(interno, admin, segunda):
    """Aun escribiendo directo (sin el servicio), un uso de la segunda empresa no puede apuntar al
    diseño de la primera: lo impide la llave compuesta (plantilla_id, organizacion_id)."""
    from app.modelos import UsoDiseno

    org2, api2 = segunda
    t1 = tipo(interno, "AISLADO_BD")
    d1 = aprobada(interno, admin, "Isolated DB design", t1["id"], TEXTO)
    t2 = tipo(api2, "AISLADO_BD")
    with SessionLocal() as db, en_organizacion(org2["id"]):
        db.add(UsoDiseno(organizacion_id=org2["id"], tipo_etiqueta_id=t2["id"], plantilla_id=d1["id"], nivel="GENERAL",
                         celda=f"{t2['id']}:GENERAL:", contexto_tipo="NINGUNO"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
