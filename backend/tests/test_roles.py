"""Roles con permisos por módulo y acción: se crean, se asignan y limitan lo
que el usuario ve y puede hacer; el proveedor sigue limitado a lo suyo."""
from conftest import Api, PASSWORD


def test_roles_y_permisos(client, admin, interno, tnf):
    r = admin.get("/roles").json()
    assert {x["modulo"] for x in r["catalogo"]} >= {"Orders", "Products", "Master data", "Tracking"}
    fab = {x["tipo"]: x for x in r["roles"] if x["sistema"]}
    assert "seguimiento.ver" not in fab["proveedor"]["permisos"] and "seguimiento.ver" in fab["interno"]["permisos"]
    assert interno.get("/roles").status_code == 403
    # Un rol interno que solo consulta datos maestros
    nuevo = admin.post("/roles", {"nombre": "Master data viewer", "tipo": "interno",
                                  "permisos": ["catalogos.ver", "catalogos.eliminar", "admin", "nada"]}).json()
    assert nuevo["permisos"] == ["catalogos.eliminar", "catalogos.ver"]
    assert admin.post("/roles", {"nombre": "master data VIEWER", "tipo": "interno"}).status_code == 409
    # A un rol de proveedor no se le dan permisos de datos globales
    prov = admin.post("/roles", {"nombre": "Supplier sheets", "tipo": "proveedor",
                                 "permisos": ["producto.ver", "producto.ficha", "catalogos.ver", "aranceles.editar"]}).json()
    assert prov["permisos"] == ["producto.ficha", "producto.ver"]
    # Se asigna a un usuario nuevo y limita lo que hace
    u = admin.post("/usuarios", {"email": "visor@demo.com", "nombre": "Viewer", "rol_id": nuevo["id"],
                                 "password": PASSWORD, "telefono": "+50370000099", "dos_pasos": True}).json()
    visor = Api(client, "visor@demo.com")
    yo = visor.get("/auth/me").json()
    assert yo["rol"] == "interno" and yo["rol_nombre"] == "Master data viewer" and "oc.ver" not in yo["permisos"]
    assert visor.get("/catalogos/marcas").status_code == 200
    marca = visor.get("/catalogos/marcas").json()["items"][0]
    assert visor.patch(f"/catalogos/marcas/{marca['id']}", {"nombre": marca["nombre"]}).status_code == 403
    assert visor.post("/catalogos/marcas", {"codigo": "ZZ", "nombre": "Z"}).status_code == 403
    assert visor.get("/seguimiento").status_code == 403
    # Con el permiso agregado al rol, ya puede editar (sin volver a iniciar sesión)
    admin.patch(f"/roles/{nuevo['id']}", {"permisos": ["catalogos.ver", "catalogos.editar"]})
    assert visor.patch(f"/catalogos/marcas/{marca['id']}", {"nombre": marca["nombre"]}).status_code == 200
    # Un rol con usuarios no se borra ni cambia de tipo; uno de fábrica no se borra
    assert admin.delete_(f"/roles/{nuevo['id']}").status_code == 422
    assert admin.patch(f"/roles/{nuevo['id']}", {"tipo": "proveedor"}).status_code == 422
    assert admin.delete_(f"/roles/{fab['interno']['id']}").status_code == 422
    # Cambiar de rol: a uno de proveedor exige proveedor
    assert admin.patch(f"/usuarios/{u['id']}", {"rol_id": prov["id"]}).status_code == 422
    admin.patch(f"/usuarios/{u['id']}", {"rol_id": fab["interno"]["id"]})
    assert admin.delete_(f"/roles/{prov['id']}").status_code == 200
    assert admin.delete_(f"/roles/{nuevo['id']}").status_code == 200
