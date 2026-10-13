"""Módulos activables (Configuración → Empresa → Módulos): un módulo apagado
quita sus permisos a todos, en el servidor y en las pantallas; al encenderlo
vuelven, sin perder datos."""


def test_modulos_activables(admin, interno):
    org = admin.get("/organizacion").json()
    assert {m["clave"] for m in org["modulos"]} == {"transporte", "clasificacion", "seguimiento"}
    assert all(m["activo"] for m in org["modulos"])
    assert admin.put("/organizacion", {"modulos": {"contabilidad": False}}).status_code == 422
    assert admin.put("/organizacion", {"modulos": {"transporte": "no"}}).status_code == 422
    embarques = len(interno.get("/embarques").json())
    try:
        assert admin.put("/organizacion", {"modulos": {"transporte": False, "clasificacion": False}}).status_code == 200
        yo = interno.get("/auth/me").json()
        assert yo["config"]["modulos"] == {"transporte": False, "clasificacion": False, "seguimiento": True}
        assert not {"transporte.gestionar", "aranceles.ver", "clasificacion.ver"} & set(yo["permisos"])
        assert "seguimiento.ver" in yo["permisos"]
        assert interno.get("/embarques").status_code == 403
    finally:
        admin.put("/organizacion", {"modulos": {"transporte": True, "clasificacion": True}})
    assert len(interno.get("/embarques").json()) == embarques
    assert "aranceles.ver" in interno.get("/auth/me").json()["permisos"]
