"""Módulos activables (Configuración → Empresa → Módulos): un módulo apagado
quita sus permisos a todos, en el servidor y en las pantallas; al encenderlo
vuelven, sin perder datos."""


def test_modulos_activables(admin, interno):
    org = admin.get("/organizacion").json()
    assert {m["clave"] for m in org["modulos"]} == {"transporte", "clasificacion", "seguimiento", "etiquetado"}
    assert all(m["activo"] for m in org["modulos"])
    assert admin.put("/organizacion", {"modulos": {"contabilidad": False}}).status_code == 422
    assert admin.put("/organizacion", {"modulos": {"transporte": "no"}}).status_code == 422
    embarques = len(interno.get("/embarques").json())
    try:
        assert admin.put("/organizacion", {"modulos": {"transporte": False, "clasificacion": False}}).status_code == 200
        yo = interno.get("/auth/me").json()
        assert yo["config"]["modulos"] == {"transporte": False, "clasificacion": False, "seguimiento": True, "etiquetado": True}
        assert not {"transporte.gestionar", "aranceles.ver", "clasificacion.ver"} & set(yo["permisos"])
        assert "seguimiento.ver" in yo["permisos"]
        assert interno.get("/embarques").status_code == 403
    finally:
        admin.put("/organizacion", {"modulos": {"transporte": True, "clasificacion": True}})
    assert len(interno.get("/embarques").json()) == embarques
    assert "aranceles.ver" in interno.get("/auth/me").json()["permisos"]


def test_ninguna_ruta_de_un_modulo_tapa_a_la_de_otro():
    """main.py monta los módulos en orden alfabético. Ese orden no debe importar:
    ninguna ruta de un módulo puede atender una URL de otro (por ejemplo
    «/embarques/{id}» de uno y «/embarques/resumen» de otro)."""
    from app.core import modulos
    rutas = [(m.clave, r) for m in modulos.cargar() for router in m.rutas() for r in router.routes
             if getattr(r, "methods", None)]
    choques = sorted({f"{a} {ra.path} ↔ {b} {rb.path}" for a, ra in rutas for b, rb in rutas
                      if a != b and ra.methods & rb.methods and ra.path_regex.match(rb.path)})
    assert not choques, choques
