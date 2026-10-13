"""Datos maestros normalizados (auditoría, prioridad media): correos, teléfonos,
direcciones y personas de contacto en sus tablas, uno por fila."""
import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.core.db import SessionLocal, engine
from app.modelos import MedioContacto, Proveedor, Tercero


def _id(api, catalogo, codigo):
    items = api.get(f"/catalogos/{catalogo}", params={"size": 200}).json()["items"]
    return next(x for x in items if x.get("codigo") == codigo)


def test_correos_de_un_proveedor_uno_por_fila(interno):
    vans = _id(interno, "proveedores", "VANS")
    assert vans["correos"] == "export.vans@vans.demo" and vans["contacto"] == "Wei Chen" and vans["telefono"]
    r = interno.patch(f"/catalogos/proveedores/{vans['id']}", {"correos": "a@vans.demo; b@vans.demo, a@vans.demo",
                                                               "telefono": "+86 1", "contacto": "Li Wang"})
    assert r.status_code == 200, r.text
    assert r.json()["correos"] == "a@vans.demo, b@vans.demo" and r.json()["contacto"] == "Li Wang"
    with SessionLocal() as db:
        p = db.scalar(select(Proveedor).where(Proveedor.codigo == "VANS"))
        valores = sorted(m.valor for m in db.scalars(select(MedioContacto).where(MedioContacto.tercero_id == p.tercero_id,
                                                                                MedioContacto.tipo == "CORREO")))
        assert valores == ["a@vans.demo", "b@vans.demo"]
    # El filtro por columna busca en los medios de contacto
    f = interno.get("/catalogos/proveedores", params={"f": json.dumps({"correos": ["b@vans.demo"]})}).json()
    assert [x["codigo"] for x in f["items"]] == ["VANS"]
    valores = interno.get("/catalogos/proveedores/valores", params={"columna": "correos"}).json()
    assert "b@vans.demo" in {v["valor"] for v in valores} and "+86 1" not in {v["valor"] for v in valores}
    interno.patch(f"/catalogos/proveedores/{vans['id']}", {"correos": "export.vans@vans.demo", "contacto": "Wei Chen"})


def test_proveedor_nuevo_crea_su_tercero(interno):
    r = interno.post("/catalogos/proveedores", {"codigo": "NUEVO-TER", "nombre": "New supplier", "id_fiscal": "X-1",
                                                "pais": "CN", "correos": "ventas@nuevo.demo", "direccion": "Road 1"})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        p = db.scalar(select(Proveedor).where(Proveedor.codigo == "NUEVO-TER"))
        t = db.get(Tercero, p.tercero_id)
        assert t.nombre == "New supplier" and t.id_fiscal == "X-1" and t.tiene_rol("PROVEEDOR")
        assert p.correos == "ventas@nuevo.demo" and p.direccion == "Road 1"


def test_sociedad_y_centro_en_documentos(interno):
    soc = _id(interno, "sociedades", "8000")
    assert soc["correos"] and soc["direccion"]
    with engine.connect() as con:
        columnas = {c[1] for c in con.exec_driver_sql("SELECT * FROM sociedades LIMIT 0").cursor.description}
    assert "correos" not in columnas and "direccion" not in columnas


def test_un_medio_tiene_un_solo_dueno(client):
    with engine.connect() as con:
        with pytest.raises(IntegrityError):
            con.execute(text("INSERT INTO medios_contacto (tipo, valor, principal, organizacion_id) VALUES ('CORREO', 'x@y.z', :f, 1)"),
                        {"f": False})
        con.rollback()


def test_alcance_del_usuario_en_tablas(admin):
    from app.modelos import Usuario

    soc = admin.get("/catalogos/sociedades", params={"size": 50}).json()["items"][0]
    r = admin.post("/usuarios", {"nombre": "Scope test", "email": "alcance.tablas@demo.com", "rol_id":
                                 next(x["id"] for x in admin.get("/roles").json()["roles"] if x["nombre"] == "Internal team"),
                                 "telefono": "+50370009999", "alcance": {"sociedades": [soc["codigo"]]}})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    with engine.connect() as con:
        filas = con.execute(text("SELECT sociedad_id FROM usuario_sociedades WHERE usuario_id = :u"), {"u": uid}).scalars().all()
        assert filas == [soc["id"]]
        columnas = {c[1] for c in con.exec_driver_sql("SELECT * FROM usuarios LIMIT 0").cursor.description}
    assert not {"rol", "alcance", "empresa"} & columnas
    usuario = next(u for u in admin.get("/usuarios").json() if u["id"] == uid)
    assert usuario["alcance"] == {"sociedades": [soc["codigo"]]} and usuario["rol"] == "interno"
    assert usuario["empresa"]  # su organización
    r = admin.patch(f"/usuarios/{uid}", {"alcance": {}})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(Usuario, uid).alcance == {}


def test_lineas_de_articulo_con_su_dominio(interno):
    """Taxonomía única: la línea comercial apunta a su dominio de
    clasificación (llave foránea); los dominios se eligen, no se editan aquí."""
    calzado = _id(interno, "categorias", "CALZADO")
    assert calzado["dominio"] == "FOOTWEAR"
    opciones = {o["codigo"] for o in interno.get("/catalogos/dominios/opciones").json()}
    assert {"FOOTWEAR", "APPAREL"} <= opciones
    r = interno.patch(f"/catalogos/categorias/{calzado['id']}", {"dominio": "NO_EXISTE"})
    assert r.status_code == 422
    assert interno.post("/catalogos/dominios", {"codigo": "X", "nombre": "X"}).status_code in (403, 409)
    with SessionLocal() as db, pytest.raises(IntegrityError):
        db.execute(text("UPDATE categorias_articulo SET dominio = 'NO_EXISTE' WHERE codigo = 'CALZADO'"))
        db.flush()


def test_pais_del_arancel_es_un_pais_iso(interno):
    r = interno.post("/aranceles/paises", {"iso": "ZZ", "nombre": "Nowhere", "digitos": 8})
    assert r.status_code == 422 and "country catalog" in r.text
    with SessionLocal() as db, pytest.raises(IntegrityError):
        db.execute(text("UPDATE paises_arancel SET iso = 'ZZ' WHERE iso = 'GT'"))
        db.flush()
