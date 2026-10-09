"""Gobierno de los datos maestros: responsables por catálogo, datos que la
empresa vuelve obligatorios, historial por registro, borrado de registros que
los documentos usan y cargas que solo actualizan con permiso de editar."""
import pytest
from conftest import Api


def _rol(admin, nombre: str) -> dict:
    return next(r for r in admin.get("/roles").json()["roles"] if r["nombre"] == nombre)


def _catalogo(api, tipo: str) -> dict:
    return next(c for c in api.get("/catalogos").json() if c["tipo"] == tipo)


@pytest.fixture
def sin_gobierno(admin):
    yield
    for tipo in ("marcas", "proveedores"):
        admin.put(f"/catalogos/{tipo}/gobierno", {"responsables": [], "obligatorios": []})


def test_responsables_del_catalogo(admin, interno, sin_gobierno):
    # Sin responsables lo mantiene cualquier rol con los permisos
    assert _catalogo(interno, "marcas")["puede"]["crear"]
    assert not _catalogo(interno, "marcas")["puede"]["gobernar"]
    # Solo la administración lo configura
    assert interno.put("/catalogos/marcas/gobierno", {"responsables": []}).status_code == 403
    r = admin.put("/catalogos/marcas/gobierno", {"responsables": [_rol(admin, "Administrator")["id"]]})
    assert r.status_code == 200, r.text
    meta = _catalogo(interno, "marcas")
    assert [x["nombre"] for x in meta["gobierno"]["responsables"]] == ["Administrator"]
    assert not meta["puede"]["crear"] and not meta["puede"]["editar"] and not meta["puede"]["eliminar"]
    # El servidor lo exige: crear, editar y cargar
    r = interno.post("/catalogos/marcas", {"codigo": "GOB1", "nombre": "Governed"})
    assert r.status_code == 403 and r.json()["codigo"] == "sin_permiso" and "Administrator" in r.text
    marca = admin.post("/catalogos/marcas", {"codigo": "GOB1", "nombre": "Governed"})
    assert marca.status_code == 200, marca.text
    assert interno.patch(f"/catalogos/marcas/{marca.json()['id']}", {"nombre": "Other"}).status_code == 403
    r = interno.c.post("/api/catalogos/marcas/importar", headers=interno.h,
                       files={"archivo": ("m.csv", b"codigo,nombre\nGOB2,Uploaded\n", "text/csv")})
    assert r.status_code == 403
    # Otro catálogo sin responsables sigue igual
    assert _catalogo(interno, "grupos")["puede"]["crear"]
    # Roles que no existen o inactivos: no
    assert admin.put("/catalogos/marcas/gobierno", {"responsables": [999999]}).status_code == 422
    # Los catálogos compartidos entre organizaciones no se configuran aquí
    assert admin.put("/catalogos/paises/gobierno", {"responsables": []}).status_code == 403
    assert admin.delete_(f"/catalogos/marcas/{marca.json()['id']}").status_code == 200


def test_obligatorios_de_la_empresa(admin, interno, sin_gobierno):
    meta = _catalogo(admin, "proveedores")
    obligables = {x["nombre"] for x in meta["gobierno"]["obligables"]}
    assert "id_fiscal" in obligables and "codigo" not in obligables and "activo" not in obligables
    # Solo datos que se pueden volver obligatorios
    assert admin.put("/catalogos/proveedores/gobierno", {"obligatorios": ["codigo"]}).status_code == 422
    assert admin.put("/catalogos/proveedores/gobierno", {"obligatorios": ["id_fiscal"]}).status_code == 200
    campo = next(c for c in _catalogo(interno, "proveedores")["campos"] if c["nombre"] == "id_fiscal")
    assert campo["obligatorio"] and campo["obligatorio_empresa"]
    r = interno.post("/catalogos/proveedores", {"codigo": "GOBP", "nombre": "Governed supplier"})
    assert r.status_code == 422 and any(d["campo"] == "id_fiscal" for d in r.json()["detalle"])
    # La carga masiva aplica la misma regla
    r = interno.c.post("/api/catalogos/proveedores/importar", headers=interno.h,
                       files={"archivo": ("p.csv", b"codigo,nombre\nGOBP,Governed supplier\n", "text/csv")})
    assert r.status_code == 200 and r.json()["creados"] == 0 and r.json()["errores"]
    r = interno.post("/catalogos/proveedores", {"codigo": "GOBP", "nombre": "Governed supplier", "id_fiscal": "0614-1"})
    assert r.status_code == 200, r.text
    # Editar sin tocar el dato no lo pide; vaciarlo, sí
    pid = r.json()["id"]
    assert interno.patch(f"/catalogos/proveedores/{pid}", {"telefono": "2222-0000"}).status_code == 200
    assert interno.patch(f"/catalogos/proveedores/{pid}", {"id_fiscal": ""}).status_code == 422
    assert admin.delete_(f"/catalogos/proveedores/{pid}").status_code == 200


def test_historial_por_registro(interno):
    marca = interno.post("/catalogos/marcas", {"codigo": "HIS1", "nombre": "History"}).json()
    interno.patch(f"/catalogos/marcas/{marca['id']}", {"nombre": "History two"})
    h = interno.get(f"/catalogos/marcas/{marca['id']}/historial").json()
    assert [x["accion"] for x in h] == ["editar", "crear"]
    assert h[0]["detalle"]["nombre"] == ["History", "History two"] and h[0]["usuario"]
    assert interno.get("/catalogos/marcas/999999/historial").status_code == 404
    assert interno.delete_(f"/catalogos/marcas/{marca['id']}").status_code == 200


def test_no_se_borra_lo_que_usan_los_documentos(admin, interno):
    soc = interno.post("/catalogos/sociedades", {"codigo": "ZZ99", "nombre": "Unused company"})
    assert soc.status_code == 200, soc.text
    # Una OC guarda el código de la sociedad (sin llave foránea)
    oc = interno.post("/ordenes/borrador", {"cabecera": {"proveedor": "VANS", "oc": "GOB-SOC-1", "sociedad": "ZZ99"}}).json()
    r = admin.delete_(f"/catalogos/sociedades/{soc.json()['id']}")
    assert r.status_code == 409 and r.json()["codigo"] == "en_uso" and "ZZ99" in r.text
    # Sin documentos que la usen, se borra
    assert interno.delete_(f"/ordenes/{oc['oc']['id']}").status_code == 200
    assert admin.delete_(f"/catalogos/sociedades/{soc.json()['id']}").status_code == 200


def test_la_carga_solo_actualiza_con_permiso_de_editar(client, admin):
    rol = admin.post("/roles", {"nombre": "Master data loader", "permisos": ["catalogos.ver", "catalogos.crear"]}).json()
    u = admin.post("/usuarios", {"email": "cargador@demo.com", "nombre": "Loader", "rol_id": rol["id"],
                                 "telefono": "+50370000141", "dos_pasos": True}).json()
    api = Api(client, "cargador@demo.com", u["password_temporal"])
    api.post("/auth/password", {"actual": u["password_temporal"], "nueva": "Carga#Maestros2026"})
    existente = admin.get("/catalogos/marcas", params={"size": 1}).json()["items"][0]
    contenido = f"codigo,nombre\n{existente['codigo']},Renamed by upload\nCRG1,Loaded brand\n".encode()
    r = api.c.post("/api/catalogos/marcas/importar", headers=api.h, files={"archivo": ("m.csv", contenido, "text/csv")})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["creados"] == 1 and res["actualizados"] == 0
    assert any("cannot edit" in e["mensaje"] for e in res["errores"])
    assert admin.get("/catalogos/marcas", params={"q": existente["codigo"]}).json()["items"][0]["nombre"] == existente["nombre"]
    nueva = admin.get("/catalogos/marcas", params={"q": "CRG1"}).json()["items"][0]
    assert admin.delete_(f"/catalogos/marcas/{nueva['id']}").status_code == 200


def test_proveedores_en_un_solo_lugar(admin):
    """El maestro de proveedores se mantiene en Datos maestros, no en Administración."""
    assert admin.post("/proveedores", {"codigo": "DUP", "nombre": "Duplicate"}).status_code == 405
    assert admin.get("/proveedores").status_code == 200


def test_la_carga_de_ocs_valida_moneda_e_incoterm_contra_las_listas(interno):
    """Los códigos que trae el archivo del ERP se validan contra los maestros y las listas."""
    sku = interno.get("/ordenes/formulario/articulos", params={"proveedor": "VANS"}).json()[0]["valor"]
    enc = "proveedor,oc,posicion,sociedad,centro,moneda,incoterm,sku,cantidad,precio\n"
    csv = (enc + f"VANS,GOB-CUR-1,10,8000,8020,ZZZ,FOB,{sku},1,1\n"
           + f"VANS,GOB-CUR-2,10,8000,8020,USD,XYZ,{sku},1,1\n")
    r = interno.c.post("/api/ordenes/importar/previa", headers=interno.h, files={"archivo": ("o.csv", csv.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    mensajes = " ".join(m for f in r.json()["filas"] for m in f["mensajes"])
    assert "Currency ZZZ is not in the list" in mensajes and "Incoterm XYZ is not in the list" in mensajes
    assert r.json()["resumen"]["error"] == 2
