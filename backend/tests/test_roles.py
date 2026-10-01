"""Roles con permisos por módulo y acción: se crean, se asignan y limitan lo
que el usuario ve y puede hacer; el proveedor sigue limitado a lo suyo."""
from conftest import Api, PASSWORD


def test_roles_y_permisos(client, admin, interno, tnf):
    r = admin.get("/roles").json()
    assert {x["modulo"] for x in r["catalogo"]} >= {"Orders", "Products", "Master data", "Tracking"}
    fab = {x["nombre"]: x for x in r["roles"]}
    assert "seguimiento.ver" not in fab["Supplier"]["permisos"] and "seguimiento.ver" in fab["Internal team"]["permisos"]
    assert "tipo" not in fab["Supplier"]
    assert interno.get("/roles").status_code == 403
    # Un rol libre: nombre, descripción y los permisos que se marquen
    nuevo = admin.post("/roles", {"nombre": "Master data viewer", "descripcion": "Looks up master data",
                                  "permisos": ["catalogos.ver", "catalogos.eliminar", "nada"]}).json()
    assert nuevo["permisos"] == ["catalogos.eliminar", "catalogos.ver"] and nuevo["descripcion"] == "Looks up master data"
    assert admin.post("/roles", {"nombre": "master data VIEWER"}).status_code == 409
    # El mismo rol sirve para un proveedor: ahí solo aplican los permisos de sus propios datos
    mixto = admin.post("/roles", {"nombre": "Sheets", "permisos": ["producto.ver", "producto.ficha", "catalogos.ver"]}).json()
    assert mixto["permisos"] == ["catalogos.ver", "producto.ficha", "producto.ver"]
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
    # Un rol con usuarios no se borra
    assert admin.delete_(f"/roles/{nuevo['id']}").status_code == 422
    # Con proveedor asignado el usuario ve solo lo suyo y pierde los permisos globales del rol
    tnf_id = next(p["id"] for p in admin.get("/proveedores").json() if p["nombre"] == "The North Face")
    assert admin.patch(f"/usuarios/{u['id']}", {"rol_id": mixto["id"], "proveedor_id": tnf_id}).status_code == 200
    yo = visor.get("/auth/me").json()
    assert yo["rol"] == "proveedor" and "catalogos.ver" not in yo["permisos"] and "producto.ver" in yo["permisos"]
    # Nunca queda el sistema sin administrador
    adm = next(x for x in admin.get("/usuarios").json() if x["email"] == "admin@demo.com")
    assert admin.patch(f"/usuarios/{adm['id']}", {"rol_id": nuevo["id"]}).status_code == 422
    assert admin.patch(f"/roles/{fab['Administrator']['id']}", {"permisos": ["oc.ver"]}).status_code == 422
    assert admin.patch(f"/roles/{fab['Administrator']['id']}", {"activo": False}).status_code == 422
    # Los roles iniciales se editan y se borran como cualquier otro
    assert admin.patch(f"/roles/{fab['Internal team']['id']}", {"nombre": "Imports", "descripcion": "Imports team"}).status_code == 200
    admin.patch(f"/usuarios/{u['id']}", {"rol_id": fab["Internal team"]["id"], "proveedor_id": None})
    assert visor.get("/auth/me").json()["rol"] == "interno"
    assert admin.delete_(f"/roles/{mixto['id']}").status_code == 200
    assert admin.delete_(f"/roles/{nuevo['id']}").status_code == 200
